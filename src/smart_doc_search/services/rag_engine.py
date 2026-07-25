"""RAG 引擎 — 协调文档检索和 LLM 生成的核心服务（同步版本）

增强管线（按配置开关控制）:
  query → [rewrite] → [hybrid search] → [rerank] → parent expansion
        → [context compression] → LLM generation

各阶段说明：
- Query Rewriting: 将用户查询改写为多个变体，提升召回率
- Hybrid Search: BM25 关键词检索 + 语义向量检索，RRF 融合
- Re-ranking: 使用 LLM 对检索结果重新排序，提升相关性
- Parent Expansion: 将匹配的子块扩展为对应的父块（上下文更完整）
- Context Compression: 句子级过滤，压缩上下文长度
- LLM Generation: 流式生成最终回答
"""
import time
from typing import Generator, List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from smart_doc_search.core.config import settings
from smart_doc_search.services.embedding_service import embedding_service, LLMError
from smart_doc_search.services.vector_store import vector_store
from smart_doc_search.services.llm_client import llm_client
from smart_doc_search.services.hybrid_search import hybrid_search
from smart_doc_search.services.reranker import reranker_service
from smart_doc_search.services.query_rewriter import query_rewriter
from smart_doc_search.services.context_compressor import context_compressor
from smart_doc_search.services.tag_service import tag_service
from smart_doc_search.services.data_service import data_service
from loguru import logger as log


# ============================================================
# 自定义异常类
# ============================================================
class RetrievalError(Exception):
    """文档检索失败时抛出的异常，用于区分检索错误和其他错误"""
    pass


# ============================================================
# 系统提示词模板
# ============================================================
RAG_SYSTEM_PROMPT = """你是一个文档检索助手，你的回答必须严格基于下面提供的文档内容。

## 规则
- 仅根据【文档内容】回答，禁止编造或猜测。
- 如果文档内容中包含相关信息，直接引用并回答，注明来源。
- 如果文档内容为空或确实没有相关信息，只需简短回复"文档中未找到相关信息"即可，不要要求用户提供更多资料。
- 使用 Markdown 格式。

## 文档内容
{context}"""

CHAT_SYSTEM_PROMPT = """你是一个智能文档助手。你可以帮助用户解答各种问题，提供建议和信息。

## 你的能力
- 回答各类知识性问题
- 提供分析和建议
- 帮助用户理解和总结信息
- 进行头脑风暴和创意讨论

请以友好、专业的态度回应用户。使用 Markdown 格式组织回答使内容更易读。"""


# ============================================================
# RAG 引擎核心类（增强版）
# ============================================================
class RAGEngine:
    """RAG 引擎核心类，协调文档检索和 LLM 生成

    增强管线（按配置开关控制）:
      1. Query Rewriting: 多查询改写 / HyDE（假设性文档嵌入）
      2. Hybrid Search: BM25 关键词检索 + 语义向量检索 → RRF 融合
      3. Re-ranking: LLM 重排序，提升结果相关性
      4. Parent Expansion: 将子块扩展为对应的父块（上下文更完整）
      5. Context Compression: 句子级过滤，压缩上下文长度
      6. LLM Generation: 流式生成最终回答
    """

    def __init__(self):
        """初始化检索参数，从配置文件读取默认值"""
        self.default_top_k = settings.RETRIEVAL_TOP_K              # 默认返回数量
        self.similarity_threshold = settings.SIMILARITY_THRESHOLD  # 相似度阈值（低于此值的结果被过滤）
        self.retrieval_multiplier = settings.RETRIEVAL_MULTIPLIER  # 增强检索时的过度获取倍数（用于重排序）

    # ============================================================
# 基础检索（单查询 → 语义搜索）
# ============================================================
    def retrieve(
        self, query: str, knowledge_base_id: int,
        top_k: int = None, similarity_threshold: float = None,
    ) -> List[Dict[str, Any]]:
        """基础语义检索：将查询向量化后在知识库中搜索匹配的子块"""
        top_k = top_k or self.default_top_k
        similarity_threshold = similarity_threshold or self.similarity_threshold

        try:
            # 步骤1: 将查询文本向量化
            log.info(f"RAG检索: 向量化查询 (知识库={knowledge_base_id})")
            query_embedding = embedding_service.embed_single(query)

            # 步骤2: 在向量库中搜索匹配的子块
            log.info(f"RAG检索: 语义搜索 top-{top_k}")
            results = vector_store.search(
                knowledge_base_id, query_embedding, top_k, similarity_threshold
            )
            results.extend(self._search_multimodal(query, knowledge_base_id, top_k, similarity_threshold))
            results.sort(key=lambda item: item.get("score", 0), reverse=True)
            results = results[:top_k]

            # 处理空结果
            if not results:
                log.info("RAG检索: 未找到相关结果")
                return []

            log.info(f"RAG检索: 找到 {len(results)} 个子块匹配")
            return results

        except Exception as e:
            log.error(f"RAG检索失败: {e}")
            raise RetrievalError(f"文档检索失败: {str(e)}")

    # ============================================================
# 增强检索（支持混合搜索 + 重排序）
# ============================================================
    def retrieve_enhanced(
        self, query: str, knowledge_base_id: int,
        top_k: int = None, similarity_threshold: float = None,
    ) -> Dict[str, Any]:
        """增强检索：query_rewrite → hybrid_search → rerank → 返回子块

        这是新的核心检索方法，集成了所有 RAGAS 优化。

        Returns:
            Dict with:
                - 'results': 最终排序后的子块结果
                - 'debug': 检索调试信息（用于存储在 Message.retrieval_details）
        """
        top_k = top_k or self.default_top_k
        similarity_threshold = similarity_threshold or self.similarity_threshold
        multiplier = self.retrieval_multiplier
        # 调试信息字典，记录检索过程中的各个阶段
        debug = {
            "pipeline_stages": [],   # 执行过的管线阶段
            "query_original": query, # 原始查询
        }

        try:
            # ── Stage 0: 查询改写 ────────────────────────────────
            # 将原始查询改写为多个变体（如同义词替换、扩写等）
            rewritten_queries = query_rewriter.rewrite(query)
            debug["query_variants"] = rewritten_queries
            if settings.QUERY_REWRITE_ENABLED and len(rewritten_queries) > 1:
                debug["pipeline_stages"].append("query_rewrite")
                log.info(f"RAG增强: 查询改写 → {len(rewritten_queries)} 个变体")

            # ── Stage 1: 按查询变体检索 ────────────────────────────
            all_results: List[List[Dict[str, Any]]] = []
            # 过度获取：为后续重排序预留更多候选（fetch_count = top_k * multiplier）
            fetch_count = top_k * multiplier

            # 对每个查询变体执行检索
            for q in rewritten_queries:
                query_embedding = embedding_service.embed_single(q)
                # 语义搜索
                semantic_results = vector_store.search(
                    knowledge_base_id, query_embedding, fetch_count, similarity_threshold
                )
                multimodal_results = self._search_multimodal(
                    q, knowledge_base_id, fetch_count, similarity_threshold
                )

                if not semantic_results and not multimodal_results:
                    continue

                # 混合搜索（如果启用）：BM25 + 语义向量 → RRF 融合
                if settings.HYBRID_SEARCH_ENABLED:
                    debug["pipeline_stages"].append("hybrid_search")
                    fused = hybrid_search.search(
                        knowledge_base_id, q, semantic_results,
                        top_k=fetch_count, fusion_method="rrf"
                    )
                    all_results.append(fused + multimodal_results)
                else:
                    all_results.append(semantic_results + multimodal_results)

            # ── Stage 1.5: 多查询结果融合 ────────────────────────
            # 使用 RRF（Reciprocal Rank Fusion）合并多个查询变体的结果
            # 原始查询获得 2 倍权重，避免被其他变体稀释
            if len(all_results) > 1:
                from smart_doc_search.services.hybrid_search import reciprocal_rank_fusion
                merged_results = reciprocal_rank_fusion(
                    all_results + [all_results[0]]  # 复制原始查询结果以获得 2× 权重
                )
                debug["pipeline_stages"].append("multi_query_fusion")
                debug["merged_from_variants"] = len(all_results)
            elif all_results:
                merged_results = all_results[0]
            else:
                merged_results = []

            # 处理空结果
            if not merged_results:
                log.info("RAG增强: 所有检索均无结果")
                debug["pipeline_stages"].append("no_results")
                return {"results": [], "debug": debug}

            debug["candidates_before_rerank"] = len(merged_results)

            # ── Stage 2: 重排序 ──────────────────────────────────
            # 使用 LLM 对候选结果重新排序，提升相关性
            if settings.RERANK_ENABLED:
                backend = reranker_service.backend_used
                debug["pipeline_stages"].append(f"rerank({backend})")
                final_results = reranker_service.rerank(
                    query, merged_results, top_k
                )
            else:
                # 未启用重排序，直接取前 top_k 个
                final_results = merged_results[:top_k]

            debug["final_count"] = len(final_results)
            debug["pipeline_stages"].append("complete")

            log.info(
                f"RAG增强完成: {debug.get('candidates_before_rerank', 0)} → "
                f"{len(final_results)} results "
                f"(stages: {debug['pipeline_stages']})"
            )

            return {"results": final_results, "debug": debug}

        except Exception as e:
            # 增强检索失败时回退到基础检索
            log.error(f"RAG增强检索失败: {e}，回退到基础检索")
            results = self.retrieve(query, knowledge_base_id, top_k, similarity_threshold)
            debug["pipeline_stages"].append("fallback_basic")
            debug["error"] = str(e)
            return {"results": results, "debug": debug}

    def _search_multimodal(
        self, query: str, knowledge_base_id: int, top_k: int, similarity_threshold: float,
    ) -> List[Dict[str, Any]]:
        """以文本查询多模态图片索引；未启用时保持原有文字检索行为。"""
        if not settings.MULTIMODAL_EMBEDDING_ENABLED:
            return []
        try:
            query_embedding = embedding_service.embed_multimodal([{"text": query}])
            results = vector_store.search_multimodal(knowledge_base_id, query_embedding, top_k)
            return [item for item in results if item.get("score", 0) >= similarity_threshold]
        except Exception as error:
            # 多模态是增强能力，服务不可用时文字问答仍可正常使用。
            log.warning(f"多模态图片检索不可用，已跳过: {error}")
            return []

    # ============================================================
# 完整检索（返回父块 + 来源信息） — 增强版
# ============================================================
    def retrieve_with_parents(
        self, query: str, knowledge_base_id: int, db: Session, top_k: int = None,
    ) -> Dict[str, Any]:
        """完整检索流程：增强检索 → 关联父块 → 返回来源信息

        返回值包含父块内容（用于 LLM 上下文）、来源信息（用于展示引用）、子块结果（用于调试）。
        """
        # 步骤1: 使用增强检索获取子块结果
        enhanced = self.retrieve_enhanced(query, knowledge_base_id, top_k)
        sub_results = enhanced["results"]
        debug = enhanced.get("debug", {})

        # 处理空结果
        if not sub_results:
            return {
                "parent_contents": [],
                "sources": [],
                "sub_results": [],
                "retrieval_details": debug,
            }

        # 步骤2: 收集父块 ID 和来源信息
        parent_ids = set()       # 需要查询的父块 ID 集合
        sources = []             # 来源信息列表（文档、页码、分数）
        seen_filenames = set()   # 已处理的来源 key（去重）

        for result in sub_results:
            meta = result.get("metadata", {})
            parent_id = meta.get("parent_chunk_id")
            if parent_id:
                parent_ids.add(int(parent_id))

            # 收集来源信息（去重）
            doc_id = meta.get("document_id")
            page = meta.get("page")
            source_key = f"{doc_id}_{page}"
            if source_key not in seen_filenames:
                seen_filenames.add(source_key)
                sources.append({
                    "document_id": doc_id,
                    "page": page,
                    "score": result.get("rerank_score") or result.get("score", 0),
                })

        # 步骤3: 从数据库查询父块内容和文档信息
        parent_contents = []  # 父块内容列表（用于 LLM 上下文）
        docs = {}             # 文档信息字典（文档 ID → 文档对象）
        doc_tags = {}         # 文档标签字典（文档 ID → 标签名称列表）

        if parent_ids:
            # 查询父块内容
            parent_chunks = data_service.get_parent_chunks_by_ids(
                list(parent_ids), db=db
            )

            # 查询关联的文档信息
            doc_ids = set(pc.document_id for pc in parent_chunks)
            if doc_ids:
                docs = data_service.get_documents_by_ids(list(doc_ids), db=db)

                # 提取每个文档的标签名称
                for d in docs.values():
                    if d.tags:
                        doc_tags[d.id] = [
                            t.get("name", t) if isinstance(t, dict) else t
                            for t in d.tags
                        ]

                # 构建父块内容列表
                for pc in parent_chunks:
                    doc = docs.get(pc.document_id)
                    filename = doc.original_filename if doc else f"Doc#{pc.document_id}"
                    parent_contents.append({
                        "content": pc.content,       # 父块文本内容
                        "document_id": pc.document_id,
                        "filename": filename,        # 来源文件名
                        "chunk_index": pc.chunk_index,
                        "token_count": pc.token_count,
                    })

            # 补充来源信息中的文件名和标签
            for source in sources:
                doc = docs.get(source.get("document_id"))
                if doc:
                    source["filename"] = doc.original_filename
                    did = source["document_id"]
                    if did in doc_tags:
                        source["tags"] = doc_tags[did]

        # 步骤4: 标签加分（可选）
        # 对来源文档标签匹配查询词的子块微调分数
        if doc_tags and query:
            for result in sub_results:
                did = result.get("metadata", {}).get("document_id")
                if did and did in doc_tags:
                    base = result.get("score", 0)
                    result["score"] = tag_service.compute_tag_boost(
                        query, int(did), base, db=db
                    )

        # 记录检索详情
        debug["parent_chunks_used"] = len(parent_contents)
        debug["sources_count"] = len(sources)

        return {
            "parent_contents": parent_contents,  # 父块内容（用于 LLM 上下文）
            "sources": sources,                  # 来源信息（用于展示引用）
            "sub_results": sub_results,          # 子块结果（用于调试）
            "retrieval_details": debug,          # 检索调试信息
        }

    # ============================================================
    # RAG 流式生成（增强版：上下文压缩替代字符截断）
    # ============================================================
    def generate_rag_stream(
        self, query: str, knowledge_base_id: int, db: Session,
        conversation_history: List[Dict[str, str]] = None, top_k: int = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """基于文档内容生成流式回答（RAG）

        完整流程：检索文档 → 上下文压缩 → 构建提示词 → 流式生成 → 返回来源信息
        """
        t_start = time.time()  # 记录开始时间
        try:
            # 步骤1: 检索相关文档（完整检索流程）
            yield {"type": "status", "content": "🔍 正在检索文档..."}
            t_retrieval_start = time.time()
            retrieval_result = self.retrieve_with_parents(
                query, knowledge_base_id, db, top_k
            )
            parent_contents = retrieval_result["parent_contents"]  # 父块内容（用于上下文）
            sources = retrieval_result["sources"]                  # 来源信息（用于展示引用）
            retrieval_details = retrieval_result.get("retrieval_details", {})
            t_retrieval = time.time() - t_retrieval_start
            retrieval_details["timing_retrieval"] = round(t_retrieval, 2)  # 记录检索耗时

            # 步骤2: 上下文压缩（如果启用）
            # 使用 LLM 对上下文进行句子级过滤，保留与查询相关的内容
            if settings.CONTEXT_COMPRESSION_ENABLED and parent_contents:
                yield {"type": "status", "content": "📦 正在压缩上下文..."}
                t_comp_start = time.time()
                parent_contents = context_compressor.compress(
                    query, parent_contents, max_chars=20000
                )
                t_comp = time.time() - t_comp_start
                retrieval_details["timing_compression"] = round(t_comp, 2)  # 记录压缩耗时

            # 步骤3: 构建上下文文本（拼接所有父块内容）
            if parent_contents:
                context_parts = []
                for pc in parent_contents:
                    compressed_tag = " [已压缩]" if pc.get("compressed") else ""
                    context_parts.append(
                        f"[来源: {pc['filename']}{compressed_tag}]\n{pc['content']}\n"
                    )
                context = "\n---\n".join(context_parts)
            else:
                context = "（未找到相关文档内容）"

            # 步骤4: 构建消息列表（系统提示词 + 历史对话 + 当前查询）
            system_prompt = RAG_SYSTEM_PROMPT.format(context=context)
            messages = [{"role": "system", "content": system_prompt}]

            # 添加历史对话（如果有）
            if conversation_history:
                messages.extend(conversation_history)

            # 添加当前查询
            messages.append({"role": "user", "content": query})

            # 步骤5: 长度截断（安全网）
            # 仅在未启用压缩或压缩后仍超限时生效，避免超出 LLM 上下文限制
            if not settings.CONTEXT_COMPRESSION_ENABLED:
                total_chars = sum(len(m["content"]) for m in messages)
                if total_chars > 30000:
                    context_chars = len(context)
                    if context_chars > 20000:
                        truncated_context = context[:20000] + "\n...(内容已截断)"
                        system_prompt = RAG_SYSTEM_PROMPT.format(context=truncated_context)
                        messages[0] = {"role": "system", "content": system_prompt}

            log.info(
                f"RAG生成: 使用 {len(parent_contents)} 个父块上下文 | "
                f"源文件数: {len(sources)} | "
                f"检索阶段: {retrieval_details.get('pipeline_stages', [])}"
            )

            # 记录生成前的总耗时
            retrieval_details["timing_total_pregen"] = round(time.time() - t_start, 2)

            # 步骤6: 流式生成回答（调用 LLM）
            yield {"type": "status", "content": "🤖 正在生成回答..."}
            for token in llm_client.chat_stream(messages=messages):
                yield {"type": "token", "content": token}

            # 步骤7: 返回上下文、来源信息和检索详情（用于前端展示）
            yield {"type": "contexts", "data": [
                pc.get("content", "") for pc in parent_contents
            ]}
            yield {"type": "sources", "data": sources}
            yield {"type": "retrieval_details", "data": retrieval_details}

        except RetrievalError:
            # 检索错误直接抛出（由上层处理）
            raise
        except Exception as e:
            # 其他错误：记录日志并返回错误信息
            log.error(f"RAG生成失败: {e}")
            yield {"type": "error", "content": f"生成回答失败: {str(e)}"}

    # ============================================================
    # 普通对话流式生成（不基于文档）
    # ============================================================
    def generate_chat_stream(
        self, query: str, conversation_history: List[Dict[str, str]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """普通对话模式（不基于文档），直接调用 LLM 生成回答

        适用于不需要文档上下文的通用对话场景。
        """
        try:
            # 构建消息列表（通用对话系统提示词 + 历史对话 + 当前查询）
            messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

            # 添加历史对话（如果有）
            if conversation_history:
                messages.extend(conversation_history)

            # 添加当前查询
            messages.append({"role": "user", "content": query})

            # 流式生成回答
            for token in llm_client.chat_stream(messages=messages):
                yield {"type": "token", "content": token}

        except Exception as e:
            log.error(f"对话生成失败: {e}")
            yield {"type": "error", "content": f"生成回答失败: {str(e)}"}


# ============================================================
# 单例实例
# ============================================================
# 创建全局单例，其他模块直接导入使用，避免重复创建引擎实例
rag_engine = RAGEngine()

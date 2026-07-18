"""混合检索: BM25 关键词 + 语义向量融合（RRF）.

提供支持中文的 BM25 实现（jieba 分词），补充现有的 ChromaDB 语义检索.
结果通过互反排序融合（RRF）进行融合，实现跨异构分数的稳健排序.
"""
import math
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional

import jieba
from loguru import logger as log

from smart_doc_search.core.config import settings


# ============================================================
# Chinese BM25 Implementation
# ============================================================

class ChineseBM25:
    """使用 jieba 中文分词的 BM25 评分.

    标准 BM25 公式:
        score(D,Q) = Σ IDF(qi) * (tf(qi,D) * (k1+1)) / (tf(qi,D) + k1*(1-b+b*|D|/avgdl))

    其中:
        k1 = 1.5  (词频饱和度)
        b  = 0.75 (长度归一化)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: List[str] = []           # original document texts
        self._doc_ids: List[str] = []        # chroma_id per document
        self._tokenized: List[List[str]] = []  # tokenized documents
        self._doc_len: List[int] = []        # token count per document
        self._idf: Dict[str, float] = {}     # IDF per term
        self._tf: List[Dict[str, int]] = []  # term frequency per document
        self._avgdl: float = 0.0
        self._built: bool = False

    # ── 索引构建 ──────────────────────────────────────────

    def index(self, documents: List[Dict[str, Any]]) -> None:
        """从文档构建 BM25 索引.

        每个文档字典必须包含:
            - 'chroma_id' (str): 唯一标识符
            - 'content'  (str): 文档文本
        """
        if not documents:
            log.warning("BM25: empty document list, skipping index build")
            return

        self._docs = [d["content"] for d in documents]
        self._doc_ids = [d.get("chroma_id", "") for d in documents]

        # 使用 jieba 对所有文档进行分词
        self._tokenized = [list(jieba.cut(doc)) for doc in self._docs]
        self._doc_len = [len(tokens) for tokens in self._tokenized]
        self.N = len(self._docs)
        self._avgdl = sum(self._doc_len) / max(self.N, 1)

        # 计算文档频率用于 IDF
        df: Dict[str, int] = defaultdict(int)
        for tokens in self._tokenized:
            for term in set(tokens):
                df[term] += 1

        # IDF 计算（带平滑）
        self._idf = {
            term: math.log((self.N - cnt + 0.5) / (cnt + 0.5) + 1.0)
            for term, cnt in df.items()
        }

        # 预计算每个文档的词频
        self._tf = []
        for tokens in self._tokenized:
            tf: Dict[str, int] = defaultdict(int)
            for t in tokens:
                tf[t] += 1
            self._tf.append(tf)

        self._built = True
        log.info(f"BM25 index built: {self.N} docs, "
                 f"avg_len={self._avgdl:.1f} tokens, "
                 f"vocab={len(self._idf)} terms")

    # ── 检索 ──────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """使用中文查询搜索索引.

        Returns:
            (文档索引, bm25_score) 列表，按分数降序排列.
        """
        if not self._built:
            log.warning("BM25: index not built, returning empty results")
            return []

        query_tokens = list(jieba.cut(query))
        scores: List[Tuple[int, float]] = []

        for idx in range(self.N):
            score = 0.0
            for term in query_tokens:
                idf = self._idf.get(term, 0.0)
                if idf == 0.0:
                    continue
                tf = self._tf[idx].get(term, 0)
                if tf == 0:
                    continue
                # BM25 词项评分
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (
                    1.0 - self.b + self.b * self._doc_len[idx] / self._avgdl
                )
                score += idf * numerator / denominator

            if score > 0:
                scores.append((idx, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def search_with_ids(
        self, query: str, top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """搜索并返回带文档 ID 的结果.

        Returns:
            包含 'id', 'content', 'bm25_score' 的字典列表.
        """
        ranked = self.search(query, top_k)
        results = []
        for idx, score in ranked:
            results.append({
                "id": self._doc_ids[idx],
                "content": self._docs[idx],
                "bm25_score": round(score, 4),
                "bm25_rank": len(results) + 1,
            })
        return results

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def doc_count(self) -> int:
        return self.N if self._built else 0


# ============================================================
# Reciprocal Rank Fusion
# ============================================================

def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    """使用互反排序融合（RRF）融合多个排序列表.

    RRF 分数 = Σ 1 / (k + rank_i)

    这是一种无需超参数的方法，能自然处理不同检索系统间的异构分数分布.

    Args:
        ranked_lists: 每个检索系统一个列表，按相关性降序排列. 每个项目必须有 'id' 键.
        k: RRF 常数（默认 60，来自文献）.

    Returns:
        单个融合列表，按 RRF 分数降序排列.
    """
    rrf_scores: Dict[str, float] = defaultdict(float)
    docs: Dict[str, Dict[str, Any]] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list):
            doc_id = item["id"]
            rrf_scores[doc_id] += 1.0 / (k + rank + 1.0)
            if doc_id not in docs:
                docs[doc_id] = dict(item)

    # 按 RRF 分数降序排序
    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    result = []
    for doc_id in sorted_ids:
        item = docs[doc_id].copy()
        item["rrf_score"] = round(rrf_scores[doc_id], 6)
        item["fusion_method"] = "rrf"
        result.append(item)

    return result


def linear_fusion(
    semantic_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    weight_semantic: float = 0.7,
    weight_bm25: float = 0.3,
) -> List[Dict[str, Any]]:
    """使用归一化分数的加权线性组合融合结果.

    Args:
        semantic_results: 向量检索结果（必须有 'score' 键）.
        bm25_results: BM25 检索结果（必须有 'bm25_score' 键）.
        weight_semantic: 语义分数权重.
        weight_bm25: BM25 分数权重.

    Returns:
        合并后的列表，按组合分数降序排列.
    """
    # 构建查找映射
    sem_map = {r["id"]: r.get("score", 0.0) for r in semantic_results}
    bm25_map = {r["id"]: r.get("bm25_score", 0.0) for r in bm25_results}

    all_ids = set(sem_map) | set(bm25_map)
    docs = {}
    for r in semantic_results + bm25_results:
        if r["id"] not in docs:
            docs[r["id"]] = dict(r)

    # 将分数归一化到每个列表内的 [0,1] 区间
    def normalize(scores: Dict[str, float]) -> Dict[str, float]:
        if not scores:
            return {}
        max_val = max(scores.values())
        min_val = min(scores.values())
        if max_val == min_val:
            return {k: 1.0 for k in scores}
        return {k: (v - min_val) / (max_val - min_val) for k, v in scores.items()}

    norm_sem = normalize(sem_map)
    norm_bm25 = normalize(bm25_map)

    combined = []
    for doc_id in all_ids:
        score = (
            weight_semantic * norm_sem.get(doc_id, 0.0)
            + weight_bm25 * norm_bm25.get(doc_id, 0.0)
        )
        item = docs[doc_id].copy()
        item["combined_score"] = round(score, 4)
        item["fusion_method"] = "linear"
        combined.append(item)

    combined.sort(key=lambda x: x["combined_score"], reverse=True)
    return combined


# ============================================================
# Hybrid Search Service
# ============================================================

class HybridSearchService:
    """管理每个知识库的 BM25 索引并提供混合检索."""

    def __init__(self):
        """初始化空索引注册表."""
        self._indices: Dict[int, ChineseBM25] = {}  # kb_id -> BM25 索引
        self._enabled = settings.HYBRID_SEARCH_ENABLED

    # ── 索引管理 ────────────────────────────────────────

    def build_index(
        self, knowledge_base_id: int, documents: List[Dict[str, Any]]
    ) -> None:
        """为知识库构建或重建 BM25 索引.

        Args:
            knowledge_base_id: 目标知识库.
            documents: {chroma_id, content} 字典列表.
        """
        bm25 = ChineseBM25()
        bm25.index(documents)
        self._indices[knowledge_base_id] = bm25
        log.info(
            f"HybridSearch: index built for kb_{knowledge_base_id} "
            f"({bm25.doc_count} docs)"
        )

    def add_documents(
        self, knowledge_base_id: int, documents: List[Dict[str, Any]]
    ) -> None:
        """向现有索引添加新文档.

        如果知识库没有索引，则构建新索引.
        注意: ChromaDB 当前仅支持完全重建. 对于增量更新，调用方应重建整个索引.
        """
        # 为简单起见，重建整个索引
        # 生产环境中可考虑定期重建或增量合并
        self.build_index(knowledge_base_id, documents)

    def rebuild_for_kb(self, knowledge_base_id: int, db) -> None:
        """从 MySQL 子块为知识库重建 BM25 索引.

        在文档接入 / KB 关联变更后调用，确保混合检索始终有最新的关键词索引.

        Args:
            knowledge_base_id: 目标知识库.
            db: SQLAlchemy Session（此方法不会关闭）.
        """
        from smart_doc_search.data.database import SubChunk, DocKbRelation, Document

        if knowledge_base_id <= 0:
            return

        # 收集所有链接到此知识库的文档 ID
        doc_ids: set = set()

        # 路径 1: 直接关联 Document.knowledge_base_id
        direct = db.query(Document.id).filter(
            Document.knowledge_base_id == knowledge_base_id
        ).all()
        doc_ids.update(d[0] for d in direct)

        # 路径 2: 通过 DocKbRelation 多对多关联
        rel = db.query(DocKbRelation.document_id).filter(
            DocKbRelation.knowledge_base_id == knowledge_base_id
        ).all()
        doc_ids.update(d[0] for d in rel)

        if not doc_ids:
            self.remove_index(knowledge_base_id)
            log.info(
                f"HybridSearch: kb_{knowledge_base_id} has no documents, "
                f"index removed"
            )
            return

        # Fetch every sub-chunk for these documents
        chunks = db.query(SubChunk).filter(
            SubChunk.document_id.in_(list(doc_ids))
        ).all()

        documents = [
            {"chroma_id": sc.chroma_id or f"chunk_{sc.document_id}_{sc.chunk_index}",
             "content": sc.content}
            for sc in chunks
        ]

        if documents:
            self.build_index(knowledge_base_id, documents)
        else:
            self.remove_index(knowledge_base_id)

    def remove_index(self, knowledge_base_id: int) -> None:
        """移除知识库的 BM25 索引."""
        self._indices.pop(knowledge_base_id, None)
        log.info(f"HybridSearch: index removed for kb_{knowledge_base_id}")

    def has_index(self, knowledge_base_id: int) -> bool:
        """检查给定知识库是否存在索引."""
        return knowledge_base_id in self._indices and self._indices[knowledge_base_id].is_built

    # ── 混合检索 ───────────────────────────────────────────

    def search(
        self,
        knowledge_base_id: int,
        query: str,
        semantic_results: List[Dict[str, Any]],
        top_k: int = None,
        fusion_method: str = "rrf",
    ) -> List[Dict[str, Any]]:
        """执行混合检索: BM25 + 语义 → 融合.

        Args:
            knowledge_base_id: 目标知识库.
            query: 原始用户查询字符串.
            semantic_results: ChromaDB 向量检索结果.
            top_k: 返回结果数量（默认从配置读取）.
            fusion_method: 'rrf' 或 'linear'.

        Returns:
            融合并重排序的结果列表.
        """
        top_k = top_k or settings.RETRIEVAL_TOP_K

        if not self._enabled:
            log.info("HybridSearch: disabled, returning semantic-only results")
            return semantic_results[:top_k]

        index = self._indices.get(knowledge_base_id)
        if index is None or not index.is_built:
            # 懒加载: 如果索引缺失则从 ChromaDB 自动构建（重启后首次使用
            # 或修复前创建的已存在知识库）
            if self._lazy_build(knowledge_base_id):
                index = self._indices.get(knowledge_base_id)
            else:
                log.info(
                    f"HybridSearch: no BM25 index for kb_{knowledge_base_id}, "
                    f"falling back to semantic-only"
                )
                return semantic_results[:top_k]

        # 执行 BM25 检索（获取更多候选用于融合）
        bm25_results = index.search_with_ids(query, top_k=top_k * 3)

        if not bm25_results:
            log.info("HybridSearch: BM25 returned no results, using semantic-only")
            return semantic_results[:top_k]

        # 融合结果
        if fusion_method == "linear":
            fused = linear_fusion(
                semantic_results,
                bm25_results,
                weight_semantic=settings.HYBRID_WEIGHT_SEMANTIC,
                weight_bm25=settings.HYBRID_WEIGHT_BM25,
            )
        else:
            fused = reciprocal_rank_fusion([semantic_results, bm25_results])

        log.info(
            f"HybridSearch: fused {len(semantic_results)} semantic + "
            f"{len(bm25_results)} BM25 → {len(fused)} results (method={fusion_method})"
        )

        return fused[:top_k]

    # ── 独立 BM25 检索 ──────────────────────────────────

    def bm25_search(
        self, knowledge_base_id: int, query: str, top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """仅运行 BM25 检索（用于调试 / 对比）."""
        index = self._indices.get(knowledge_base_id)
        if index is None or not index.is_built:
            return []
        return index.search_with_ids(query, top_k)

    # ── 懒初始化 ────────────────────────────────────────────

    def _lazy_build(self, knowledge_base_id: int) -> bool:
        """首次使用时从 ChromaDB 自动构建 BM25 索引.

        成功返回 True，无数据可用返回 False.
        """
        try:
            from smart_doc_search.services.vector_store import vector_store
            from smart_doc_search.data.database import SessionLocal
            collection = vector_store.get_or_create_collection(knowledge_base_id)
            data = collection.get(include=["documents", "metadatas"])
            if not data or not data.get("ids"):
                return False
            documents = [
                {"chroma_id": data["ids"][i],
                 "content": data["documents"][i] if data["documents"] else ""}
                for i in range(len(data["ids"]))
            ]
            if not documents:
                return False
            self.build_index(knowledge_base_id, documents)
            return True
        except Exception as e:
            log.warning(f"HybridSearch: lazy build failed for kb_{knowledge_base_id}: {e}")
            return False

    # ── 属性 ──────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value


# ============================================================
# Singleton
# ============================================================

hybrid_search = HybridSearchService()

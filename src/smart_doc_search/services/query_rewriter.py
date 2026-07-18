"""查询重写与扩展 — 提升检索召回率.

策略:
  1. 多查询: 从不同角度生成 2-3 个改写版本的用户查询. 每个变体独立搜索，结果通过 RRF 合并.
  2. HyDE（假设性文档嵌入）: 生成一个假设性的答案，然后嵌入该答案进行检索. 这可以弥合短查询与完整文档文本之间的词汇鸿沟.
  3. 实体提取: 从查询中提取关键实体，并在融合过程中提升包含这些实体的块的分数.

所有策略通过配置标志选择性启用，默认禁用.
"""
import re
from typing import List, Dict, Any, Optional

from loguru import logger as log

from smart_doc_search.core.config import settings
from smart_doc_search.services.llm_client import llm_client
from smart_doc_search.services.embedding_service import LLMError


# ============================================================
# Prompt 模板
# ============================================================

MULTI_QUERY_PROMPT = """你是一个搜索查询优化助手。请将以下用户问题改写成{count}个不同角度或表达方式的检索查询，以帮助从文档中检索到更全面的信息。

要求:
- 每个查询从不同角度提问
- 使用与原文不同的措辞和关键词
- 保持原问题的语义
- 每行一个查询，不要编号

原始问题: {query}

改写查询:"""

HYDE_PROMPT = """你是一个文档检索助手。请根据用户的问题，生成一段假设性的文档内容，该内容可能包含回答用户问题所需的信息。

要求:
- 使用客观、专业、学术的中文
- 包含具体的细节和术语
- 长度约200-300字
- 假设你是一篇相关文档

用户问题: {query}

假设文档内容:"""

ENTITY_EXTRACTION_PROMPT = """请从以下用户问题中提取关键的检索实体。

包含:
- 人名、地名、机构名
- 日期、时间
- 技术术语、专业名词
- 数字、编号
- 产品名、项目名

用户问题: {query}

关键实体（逗号分隔，无需解释）:"""


# ============================================================
# 查询重写器
# ============================================================

class QueryRewriter:
    """支持多种策略的查询重写服务."""

    def __init__(self):
        self._enabled = settings.QUERY_REWRITE_ENABLED
        self._strategy = settings.QUERY_REWRITE_STRATEGY
        self._expansion_count = settings.QUERY_EXPANSION_COUNT

    # ── 主入口 ────────────────────────────────────────

    def rewrite(self, query: str) -> List[str]:
        """将查询重写为多个搜索变体.

        Returns:
            查询字符串列表（始终包含原始查询）.
            禁用时返回 [original_query].
        """
        queries = [query]  # always include original

        if not self._enabled:
            return queries

        strategy = self._strategy

        try:
            if strategy in ("multi_query", "both"):
                expanded = self._multi_query_expand(query)
                queries.extend(expanded)

            if strategy in ("hyde", "both"):
                hyde_doc = self._hyde_generate(query)
                if hyde_doc:
                    queries.append(hyde_doc)

        except Exception as e:
            log.warning(f"QueryRewriter: rewrite failed ({e}), using original query")

        # 去重同时保留顺序
        seen = set()
        unique = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique.append(q)

        log.info(f"QueryRewriter: {len(queries)} → {len(unique)} unique queries "
                 f"(strategy={strategy})")
        return unique

    # ── 多查询扩展 ───────────────────────────────────

    def _multi_query_expand(self, query: str) -> List[str]:
        """生成多个改写后的查询."""
        prompt = MULTI_QUERY_PROMPT.format(
            query=query, count=min(self._expansion_count, 5)
        )
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(messages, temperature=0.3, max_tokens=512)
            return self._parse_queries(raw)
        except LLMError as e:
            log.warning(f"Multi-query expansion failed: {e}")
            return []

    def _parse_queries(self, raw: str) -> List[str]:
        """从 LLM 输出中解析换行分隔的查询列表."""
        queries = []
        for line in raw.strip().split("\n"):
            # 移除编号如 "1. " 或 "1、"
            line = re.sub(r'^[\d]+[\.\、\)]\s*', '', line.strip())
            line = line.strip().strip('"').strip("'")
            if line and len(line) > 2:
                queries.append(line)
        return queries[:self._expansion_count]

    # ── HyDE（假设性文档嵌入）─────────────────────────

    def _hyde_generate(self, query: str) -> Optional[str]:
        """为查询生成一个假设性的文档."""
        prompt = HYDE_PROMPT.format(query=query)
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(messages, temperature=0.5, max_tokens=512)
            doc = raw.strip()
            if len(doc) > 20:
                log.info(f"HyDE: generated hypothetical doc ({len(doc)} chars)")
                return doc
            return None
        except LLMError as e:
            log.warning(f"HyDE generation failed: {e}")
            return None

    # ── 实体提取 ───────────────────────────────────────

    def extract_entities(self, query: str) -> List[str]:
        """从查询中提取关键实体用于增强.

        在融合过程中使用: 包含这些实体的块会获得小幅分数提升，
        以改善特定实体密集型查询的召回率.
        """
        prompt = ENTITY_EXTRACTION_PROMPT.format(query=query)
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(messages, temperature=0.0, max_tokens=200)
            entities = [e.strip() for e in re.split(r'[,，、\n]', raw) if e.strip()]
            log.info(f"Entity extraction: {len(entities)} entities from query")
            return entities[:10]
        except LLMError as e:
            log.warning(f"Entity extraction failed: {e}")
            return []

    # ── 属性 ──────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def strategy(self) -> str:
        return self._strategy


# ============================================================
# Singleton
# ============================================================

query_rewriter = QueryRewriter()

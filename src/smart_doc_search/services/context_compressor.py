"""智能上下文压缩 — 通过句子级相关性过滤实现.

用语义方法替换当前 RAG 引擎中粗糙的字符计数截断:

  1. 将每个父块拆分为句子（中文感知的边界检测）.
  2. 嵌入每个句子.
  3. 计算每个句子嵌入与查询嵌入之间的余弦相似度.
  4. 只保留高于可配置相似度阈值的句子.
  5. 按原始顺序组装保留的句子.

这通过减少 LLM 上下文中的噪音同时保留最相关的信息来提高忠实度.

禁用时（默认），上下文原样传递.
"""
import re
import math
from typing import List, Dict, Any, Optional

from loguru import logger as log

from smart_doc_search.core.config import settings
from smart_doc_search.services.embedding_service import embedding_service


# ============================================================
# 中文句子分割器
# ============================================================

# 中文句子边界标记
_SENTENCE_BOUNDARY = re.compile(
    r'(?<=[。！？；\n])\s*'   # Chinese punctuation
    r'|(?<=[.!?;]\s)\s*'      # English punctuation (with trailing space)
)

# 独立嵌入的最小句子长度（字符）
_MIN_SENTENCE_LEN = 5

# 最大处理句子数（安全限制）
_MAX_SENTENCES = 200

# 短于此长度（字符）的句子始终保留 —— 短的事实片段（日期、金额、名称）
# 与查询向量的余弦相似度本质上很低，但它们通常是最关键的信息.
_SHORT_SENTENCE_KEEP = 30


def split_sentences(text: str) -> List[str]:
    """将文本分割为句子，支持中文感知的边界.

    通过将代码块和表格作为整体保留来尊重它们.
    """
    if not text or not text.strip():
        return []

    sentences = []
    for part in re.split(_SENTENCE_BOUNDARY, text):
        part = part.strip()
        if part and len(part) >= _MIN_SENTENCE_LEN:
            sentences.append(part)

    # 安全机制: 合并相邻的非常短的句子
    merged = []
    buffer = ""
    for s in sentences:
        if len(s) < 10 and buffer:
            buffer += s
        elif buffer:
            merged.append(buffer)
            buffer = s
        else:
            buffer = s

    if buffer:
        merged.append(buffer)

    return merged


# ============================================================
# 余弦相似度
# ============================================================

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量之间的余弦相似度."""
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


# ============================================================
# 上下文压缩器
# ============================================================

class ContextCompressor:
    """基于查询相关性的句子级上下文压缩.

    流程:
      1. 将父块内容拆分为句子.
      2. 嵌入每个句子.
      3. 通过与查询嵌入的余弦相似度为每个句子评分.
      4. 保留高于配置阈值的句子.
      5. 返回过滤后的文本.
    """

    def __init__(self, threshold: float = None):
        self._enabled = settings.CONTEXT_COMPRESSION_ENABLED
        self._threshold = threshold or settings.CONTEXT_SENTENCE_THRESHOLD

    # ── 主入口 ────────────────────────────────────────

    def compress(
        self,
        query: str,
        parent_contents: List[Dict[str, Any]],
        max_chars: int = 20000,
    ) -> List[Dict[str, Any]]:
        """通过过滤相关性较低的句子来压缩父块内容.

        Args:
            query: 用户的原始问题.
            parent_contents: 包含 'content' 和其他元数据的字典列表.
            max_chars: 上下文总字符数的硬限制（降级截断）.

        Returns:
            过滤后的 parent_contents，其中 'content' 被压缩文本替换.
        """
        if not self._enabled or not parent_contents:
            return parent_contents

        try:
            # 只嵌入查询一次
            query_embedding = embedding_service.embed_single(query)

            compressed = []
            total_chars = 0

            for pc in parent_contents:
                content = pc.get("content", "")
                if not content:
                    compressed.append(pc)
                    continue

                # 拆分为句子
                sentences = split_sentences(content)
                if len(sentences) <= 1:
                    compressed.append(pc)
                    total_chars += len(content)
                    continue

                # 安全限制
                if len(sentences) > _MAX_SENTENCES:
                    sentences = sentences[:_MAX_SENTENCES]

                # 一次性嵌入所有句子
                embeddings = embedding_service.embed_batch(sentences)

                # 为每个句子评分
                kept_sentences = []
                for sent, emb in zip(sentences, embeddings):
                    # 始终保留短的事实片段（日期、金额、名称）—— 它们的嵌入与查询的余弦相似度
                    # 本质上很低，但它们承载着关键信息.
                    if len(sent) <= _SHORT_SENTENCE_KEEP:
                        kept_sentences.append(sent)
                        continue
                    sim = cosine_similarity(query_embedding, emb)
                    if sim >= self._threshold:
                        kept_sentences.append(sent)

                # 构建压缩后的内容
                if kept_sentences:
                    compressed_content = "".join(kept_sentences)
                    new_pc = dict(pc)
                    new_pc["content"] = compressed_content
                    new_pc["compressed"] = True
                    new_pc["original_length"] = len(content)
                    new_pc["kept_sentences"] = len(kept_sentences)
                    new_pc["total_sentences"] = len(sentences)
                    compressed.append(new_pc)
                    total_chars += len(compressed_content)
                else:
                    # 如果没有句子通过阈值，保留原始内容
                    compressed.append(pc)
                    total_chars += len(content)

            # 硬截断安全网
            if total_chars > max_chars:
                log.info(
                    f"ContextCompressor: total {total_chars} chars exceeds "
                    f"limit {max_chars}, applying hard truncation"
                )
                compressed = self._hard_truncate(compressed, max_chars)

            kept = sum(1 for pc in compressed if pc.get("compressed"))
            log.info(
                f"ContextCompressor: {kept}/{len(parent_contents)} chunks "
                f"compressed, total {total_chars} chars "
                f"(threshold={self._threshold})"
            )
            return compressed

        except Exception as e:
            log.warning(f"ContextCompressor failed ({e}), returning original context")
            return parent_contents

    def _hard_truncate(
        self, parent_contents: List[Dict[str, Any]], max_chars: int
    ) -> List[Dict[str, Any]]:
        """截断内容以适应 max_chars 限制，保留顺序."""
        result = []
        remaining = max_chars
        for pc in parent_contents:
            content = pc.get("content", "")
            if len(content) <= remaining:
                result.append(pc)
                remaining -= len(content)
            elif remaining > 200:
                # 部分保留此块
                new_pc = dict(pc)
                new_pc["content"] = content[:remaining] + "\n...(内容已截断)"
                new_pc["truncated"] = True
                result.append(new_pc)
                break
            else:
                break
        return result

    # ── Properties ──────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def threshold(self) -> float:
        return self._threshold

    def set_threshold(self, value: float) -> None:
        self._threshold = max(0.0, min(1.0, value))


# ============================================================
# Singleton
# ============================================================

context_compressor = ContextCompressor()

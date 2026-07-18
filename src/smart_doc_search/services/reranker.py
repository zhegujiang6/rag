"""重排序模块 — 提升检索精度.

三种后端（自动选择最佳可用）:
  1. cross_attention_llm（默认）: LLM 作为交叉注意力评分器 — query+chunk
     拼接后让模型判断联合相关性. 每次重排序调用只需要一个批处理 prompt. 无需额外依赖.
  2. cross_encoder: 本地 BAAI/bge-reranker-v2-m3（通过 sentence-transformers）.
     需要 `pip install sentence-transformers` + ~2 GB 模型下载.
     质量最佳，无 API 成本，但首次设置较重.
  3. llm_legacy: 原始逐块评分 — 保留用于对比 / 降级.

通过 .env 配置:
  RERANK_BACKEND=cross_attention_llm   (默认，推荐)
  RERANK_BACKEND=cross_encoder         (本地模型)
  RERANK_BACKEND=llm_legacy            (原始行为)
"""
import math
import re
import json
from typing import List, Dict, Any, Optional

from loguru import logger as log

from smart_doc_search.core.config import settings
from smart_doc_search.services.llm_client import llm_client, LLMError


# ============================================================
# 交叉注意力 LLM Prompt
# ============================================================
# 此 prompt 将 query + 所有 chunks 拼接成单个上下文窗口，
# 让 LLM 能够对每个 (query, chunk) 对执行完整的交叉注意力 ——
# 这正是 cross-encoder 在内部所做的事情.

CROSS_ATTENTION_PROMPT = """你是一个专业的文档相关性评估器。下面有一个用户问题，以及若干候选文档片段。
请对每个片段与问题的相关程度进行评分。

用户问题:
{query}

候选片段:
{chunks}

评分标准（0-100分）:
- 90-100: 完全回答了问题，包含全部关键信息
- 70-89:  高度相关，包含大部分所需信息
- 50-69:  部分相关，包含一些有用信息
- 30-49:  弱相关，仅有少量关联或主题相近但未直接回答
- 0-29:   不相关

请输出严格的JSON格式（不要其他文字）:
{{"scores": [{{"id": "片段ID", "score": 分数, "reason": "一句话理由"}}]}}"""


# ============================================================
# 传统 LLM Prompt（保留用于向后兼容）
# ============================================================

RERANK_BATCH_PROMPT = """你需要为以下文档片段根据用户问题给出相关度评分(1-5)。

评分标准:
- 5: 完全相关，包含回答问题的关键信息
- 4: 高度相关，包含有用信息
- 3: 部分相关
- 2: 弱相关
- 1: 不相关

用户问题: {query}

{chunks}

请按照以下格式输出每个片段的相关度(JSON格式):
{{"scores": [{{"id": "片段ID", "score": 评分}}, ...]}}"""


# ============================================================
# 评分辅助函数
# ============================================================

def _sigmoid_normalize(raw_scores: List[float], k: float = 0.8) -> List[float]:
    """通过 sigmoid 将分数归一化到 [0, 1]，保留排序顺序.

    不同后端的原始分数有不同的范围:
      - Cross-encoder: 大约 -10 到 10
      - LLM 0-100: 0 到 100
    Sigmoid 归一化将所有分数映射到 [0, 1] 区间，曲线平滑.
    """
    if not raw_scores:
        return []
    mean = sum(raw_scores) / len(raw_scores)
    std = (sum((s - mean) ** 2 for s in raw_scores) / max(len(raw_scores), 1)) ** 0.5
    if std < 1e-6:
        return [0.5] * len(raw_scores)
    return [1.0 / (1.0 + math.exp(-k * (s - mean) / std)) for s in raw_scores]


# ============================================================
# 重排序器基类
# ============================================================

class BaseReranker:
    """重排序器的抽象基类."""

    def rerank(
        self, query: str, candidates: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError


# ============================================================
# 交叉注意力 LLM 重排序器（默认，推荐）
# ============================================================

class CrossAttentionLLMReranker(BaseReranker):
    """LLM 作为交叉注意力评分器.

    所有 (query, chunk) 对都放在一个 prompt 中，让 LLM 能够联合关注它们 ——
    这是 cross-encoder 内部交叉注意力机制的 API 等效实现.

    与传统 LLMReranker 的关键区别:
      - 每次重排序只调用一次 prompt（不是 N 次或 1 次批处理）
      - Query+chunks 拼接在一起 → 完整交叉注意力
      - 0-100 评分并提供理由用于校准
      - Sigmoid 归一化实现稳定的分数分布
    """

    def __init__(self, model: str = None):
        self.model = model or settings.LLM_MODEL

    def rerank(
        self, query: str, candidates: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        if len(candidates) <= top_k:
            for c in candidates:
                c["rerank_score"] = c.get("score", 0.5)
            return candidates

        log.info(
            f"CrossAttentionLLM: scoring {len(candidates)} candidates "
            f"→ top_k={top_k}"
        )

        try:
            scored = self._cross_attention_rerank(query, candidates)
            scored.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
            result = scored[:top_k]

            # Log top scores for debugging
            top_scores = [
                f"{r.get('id','?')[-8:]}:{r.get('rerank_score',0):.3f}"
                for r in result[:3]
            ]
            log.info(f"CrossAttentionLLM: top scores → {top_scores}")
            return result

        except Exception as e:
            log.error(f"CrossAttentionLLM failed ({e}), falling back to original order")
            return candidates[:top_k]

    def _cross_attention_rerank(
        self, query: str, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """为所有候选执行一次交叉注意力 LLM 调用."""
        # 构建带有稳定短 ID 的块内容
        chunk_parts = []
        id_map: Dict[str, str] = {}  # short_id → full_id

        for i, c in enumerate(candidates):
            short_id = f"c{i+1}"
            id_map[short_id] = c.get("id", str(i))
            content = c.get("content", "")
            if len(content) > 500:
                content = content[:250] + "\n...(省略)...\n" + content[-250:]
            chunk_parts.append(f"[ID:{short_id}]\n{content}")

        chunks_text = "\n\n---\n\n".join(chunk_parts)
        prompt = CROSS_ATTENTION_PROMPT.format(query=query, chunks=chunks_text)
        messages = [{"role": "user", "content": prompt}]

        raw = llm_client.chat_sync(
            messages, temperature=0.0, max_tokens=1024
        )

        # 解析分数
        scores_map = _parse_cross_attention_response(raw, id_map, len(candidates))

        # 构建结果
        scored = []
        raw_score_list = []
        for c in candidates:
            cid = c.get("id", "")
            raw_score = scores_map.get(cid, 50.0)
            raw_score_list.append(raw_score)
            item = dict(c)
            item["rerank_score_raw"] = raw_score
            scored.append(item)

        # Sigmoid 归一化，实现稳定的 [0,1] 分布
        normalized = _sigmoid_normalize(raw_score_list)
        for item, norm in zip(scored, normalized):
            item["rerank_score"] = round(norm, 4)

        return scored


# ============================================================
# 传统 LLM 重排序器（保留用于向后兼容 / 对比）
# ============================================================

class LLMReranker(BaseReranker):
    """原始逐块 / 批处理 LLM 评分.

    保留用于向后兼容. 推荐使用 CrossAttentionLLMReranker，
    质量更好且 API 调用更少.
    """

    def __init__(self, model: str = None):
        self.model = model or settings.LLM_MODEL

    def rerank(
        self, query: str, candidates: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        if len(candidates) <= top_k:
            for c in candidates:
                c["rerank_score"] = c.get("score", 0.5)
            return candidates

        log.info(f"LLMReranker (legacy): scoring {len(candidates)} candidates")
        try:
            scored = self._rerank_batch(query, candidates)
            scored.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
            result = scored[:top_k]
            return result
        except Exception as e:
            log.error(f"LLMReranker failed: {e}, returning original top_k")
            return candidates[:top_k]

    def _rerank_batch(
        self, query: str, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        chunk_parts = []
        for i, c in enumerate(candidates):
            content = c.get("content", "")
            if len(content) > 1500:
                content = content[:1500] + "..."
            chunk_parts.append(f"--- 片段 {i+1} (ID: {c.get('id', i)}) ---\n{content}")

        chunks_text = "\n\n".join(chunk_parts)
        prompt = RERANK_BATCH_PROMPT.format(query=query, chunks=chunks_text)
        messages = [{"role": "user", "content": prompt}]
        raw = llm_client.chat_sync(messages, temperature=0.0, max_tokens=512)

        scores_map = _parse_legacy_batch_response(raw, candidates)
        scored = []
        for c in candidates:
            item = dict(c)
            raw_score = scores_map.get(c.get("id", ""), 3.0)
            item["rerank_score"] = raw_score / 5.0
            scored.append(item)
        return scored


# ============================================================
# Cross-Encoder 重排序器（本地模型）
# ============================================================

class CrossEncoderReranker(BaseReranker):
    """通过 sentence-transformers 的本地 cross-encoder.

    使用 BAAI/bge-reranker-v2-m3 —— 最先进的多语言重排序器，
    对中文有很好的支持. 模型在其 transformer 层中执行真正的交叉注意力.

    首次设置:
      pip install sentence-transformers
      # 模型在首次使用时自动下载 (~1.5 GB)

    需要 ~2 GB 内存 + PyTorch. 推荐使用 GPU 加速.
    CPU 推理: 现代 CPU 上每对约 0.1s.
    """

    # 仅 CPU 环境的轻量级模型
    LIGHTWEIGHT_MODELS = [
        "BAAI/bge-reranker-v2-m3",       # best quality, 1.5 GB
        "BAAI/bge-reranker-base",         # smaller, 1.1 GB
    ]

    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.RERANK_MODEL_NAME
        self._model = None
        self._initialized = False
        self._init_error: Optional[str] = None

    def _init_model(self) -> bool:
        """懒加载 cross-encoder. 成功返回 True."""
        if self._initialized:
            return True
        if self._init_error:
            return False

        for model_name in [self.model_name] + self.LIGHTWEIGHT_MODELS:
            try:
                from sentence_transformers import CrossEncoder
                log.info(f"CrossEncoder: loading {model_name} (first use downloads ~1.5 GB)...")
                self._model = CrossEncoder(
                    model_name,
                    max_length=512,
                    device=None,  # auto-detect GPU/CPU
                )
                self.model_name = model_name
                self._initialized = True
                log.info(f"CrossEncoder: loaded {model_name}")
                return True
            except ImportError:
                self._init_error = (
                    "sentence-transformers 未安装。请运行: "
                    "pip install sentence-transformers"
                )
                log.warning(self._init_error)
                return False
            except Exception as e:
                log.warning(f"CrossEncoder: failed to load {model_name}: {e}")
                continue

        self._init_error = f"无法加载任何 CrossEncoder 模型"
        return False

    def rerank(
        self, query: str, candidates: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        if not self._init_model():
            raise RuntimeError(self._init_error or "CrossEncoder init failed")

        # 构建 (query, chunk) 对用于交叉注意力
        pairs = []
        for c in candidates:
            content = c.get("content", "")
            if len(content) > 512:
                content = content[:256] + content[-256:]
            pairs.append((query, content))

        # 交叉注意力预测 — 模型联合编码每个对
        try:
            scores = self._model.predict(
                pairs,
                batch_size=8,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except Exception as e:
            log.error(f"CrossEncoder predict failed: {e}")
            raise

        # 归一化分数
        raw_scores = [float(s) for s in scores]
        normalized = _sigmoid_normalize(raw_scores)

        for c, norm in zip(candidates, normalized):
            c["rerank_score"] = round(norm, 4)

        candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        result = candidates[:top_k]

        log.info(
            f"CrossEncoder: kept {len(result)}/{len(candidates)}, "
            f"top score={result[0].get('rerank_score',0):.4f}"
        )
        return result


# ============================================================
# 响应解析器
# ============================================================

def _parse_cross_attention_response(
    raw: str, id_map: Dict[str, str], expected_count: int
) -> Dict[str, float]:
    """解析交叉注意力 LLM 的 JSON 响应 → {full_id: score (0-100)}.

    处理: JSON 解析、短 ID→完整 ID 映射、缺失条目.
    """
    # 尝试提取 JSON
    try:
        json_match = re.search(
            r'\{[^{}]*"scores"[^{}]*\[.*?\][^{}]*\}', raw, re.DOTALL
        )
        if json_match:
            data = json.loads(json_match.group())
            scores = {}
            for s in data.get("scores", []):
                raw_id = str(s.get("id", ""))
                # 映射短 ID → 完整 ID
                full_id = id_map.get(raw_id, raw_id)
                score = float(s.get("score", 50))
                scores[full_id] = max(0.0, min(100.0, score))
            if scores:
                return scores
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        log.warning(f"CrossAttention JSON parse failed: {e}")

    # 降级: 正则提取 (ID: score) 对
    scores: Dict[str, float] = {}
    for short_id, full_id in id_map.items():
        pattern = rf'{re.escape(short_id)}.*?(\d{{1,3}})'
        match = re.search(pattern, raw)
        if match:
            scores[full_id] = float(match.group(1))
        else:
            scores[full_id] = 50.0

    return scores


def _parse_legacy_batch_response(
    raw: str, candidates: List[Dict[str, Any]]
) -> Dict[str, float]:
    """解析传统批处理 LLM 响应 → {id: score (1-5)}."""
    try:
        json_match = re.search(
            r'\{[^{}]*"scores"[^{}]*\[.*?\][^{}]*\}', raw, re.DOTALL
        )
        if json_match:
            data = json.loads(json_match.group())
            return {
                s.get("id", ""): float(s.get("score", 3))
                for s in data.get("scores", [])
            }
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    scores: Dict[str, float] = {}
    for i, c in enumerate(candidates):
        cid = c.get("id", str(i))
        pattern = rf'{re.escape(str(cid))}.*?([1-5])'
        match = re.search(pattern, raw)
        scores[cid] = float(match.group(1)) if match else 3.0
    return scores


# ============================================================
# 重排序器工厂
# ============================================================

class RerankerService:
    """统一重排序器，智能选择后端.

    优先级（当 backend="auto" 时）:
      1. cross_encoder — 如果 sentence-transformers 已安装
      2. cross_attention_llm — 始终可用（使用现有 LLM API）
    """

    def __init__(self):
        self._enabled = settings.RERANK_ENABLED
        self._backend = settings.RERANK_BACKEND
        self._reranker: Optional[BaseReranker] = None
        self._backend_used: Optional[str] = None

    @property
    def reranker(self) -> BaseReranker:
        """获取最佳可用重排序器（懒初始化）."""
        if self._reranker is None:
            self._reranker = self._create_reranker()
        return self._reranker

    def _create_reranker(self) -> BaseReranker:
        backend = self._backend

        if backend == "cross_encoder":
            r = CrossEncoderReranker()
            if r._init_model():
                self._backend_used = "cross_encoder"
                return r
            log.warning("CrossEncoder 不可用，回退到 cross_attention_llm")
            self._backend_used = "cross_attention_llm"
            return CrossAttentionLLMReranker()

        elif backend == "llm_legacy":
            self._backend_used = "llm_legacy"
            return LLMReranker()

        else:
            # "cross_attention_llm" or "auto"
            self._backend_used = "cross_attention_llm"
            return CrossAttentionLLMReranker()

    def rerank(
        self, query: str, candidates: List[Dict[str, Any]], top_k: int = None
    ) -> List[Dict[str, Any]]:
        top_k = top_k or settings.RETRIEVAL_TOP_K

        if not self._enabled:
            log.info("Reranker: disabled")
            return candidates[:top_k]

        result = self.reranker.rerank(query, candidates, top_k)
        log.info(f"Reranker ({self._backend_used}): {len(candidates)} → {len(result)}")
        return result

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def backend_used(self) -> str:
        """返回实际使用的后端名称."""
        if self._backend_used:
            return self._backend_used
        _ = self.reranker  # 触发懒初始化
        return self._backend_used or "cross_attention_llm"


# ============================================================
# Singleton
# ============================================================

reranker_service = RerankerService()

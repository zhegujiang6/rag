"""RAGAS 评估引擎 — LLM-as-judge 实现.

使用现有 LLM API 计算 5 个核心 RAGAS 指标:

  1. Context Precision  — 检索上下文的信噪比
  2. Context Recall     — 检索的完整性
  3. Faithfulness       — 答案基于上下文（无幻觉）
  4. Answer Relevancy   — 答案实际回答了问题
  5. Context Entity Recall — 关键实体覆盖度

还包含一个测试数据集生成器，从文档父块创建问答对用于可复现的评估.

所有评估都是同步的，并作为单独的工作流运行 —— 不影响生产 RAG 管道.
"""
import re
import json
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from loguru import logger as log

from smart_doc_search.core.config import settings
from smart_doc_search.services.llm_client import llm_client
from smart_doc_search.services.embedding_service import embedding_service, LLMError


# ============================================================
# 数据结构
# ============================================================

@dataclass
class RAGASMetrics:
    """RAGAS 评估结果容器."""
    context_precision: float = 0.0
    context_recall: float = 0.0
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_entity_recall: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "context_precision": round(self.context_precision, 4),
            "context_recall": round(self.context_recall, 4),
            "faithfulness": round(self.faithfulness, 4),
            "answer_relevancy": round(self.answer_relevancy, 4),
            "context_entity_recall": round(self.context_entity_recall, 4),
        }

    @property
    def average(self) -> float:
        vals = list(self.to_dict().values())
        return sum(vals) / len(vals) if vals else 0.0


# ============================================================
# Prompt 模板
# ============================================================

# ── Context Precision（上下文精确率）────────────────────────────────────────
CONTEXT_PRECISION_PROMPT = """判断以下文档片段是否与用户问题相关。仅回答"相关"或"不相关"。

用户问题: {question}

文档片段: {chunk}

是否相关? (相关/不相关):"""

# 批处理版本: 在一次 LLM 调用中评估所有块
CONTEXT_PRECISION_BATCH_PROMPT = """判断以下每个文档片段是否与用户问题相关。对每个片段仅回答"相关"或"不相关"，每行一个。

用户问题: {question}

{chunks}

每行回答 (相关/不相关)，按顺序:"""

# ── Context Recall（从标准答案提取声明）──────────────
CLAIM_EXTRACTION_PROMPT = """将以下标准答案拆分为独立的原子陈述（每行一个）:

标准答案: {answer}

原子陈述:"""

CLAIM_ATTRIBUTION_BATCH_PROMPT = """判断以下每个陈述是否可以从提供的文档内容中推导出来。每行回答"是"或"否"。

文档内容: {context}

{claims}

每行回答 (是/否)，按顺序:"""

# ── Faithfulness（忠实度）──────────────────────────────────────────────
FAITHFULNESS_CLAIMS_PROMPT = """将以下回答拆分为独立的原子陈述（每行一个）:

回答: {answer}

原子陈述:"""

FAITHFULNESS_VERIFY_BATCH_PROMPT = """判断以下每个陈述是否可以从提供的文档内容中推导出来。每行回答"是"或"否"。

文档内容: {context}

{claims}

每行回答 (是/否)，按顺序:"""

# ── Answer Relevancy（反向问题生成）────────────────────
REVERSE_QUESTION_PROMPT = """基于以下回答，生成3个可能导致这个回答的用户问题:

回答: {answer}

可能的问题:
1.
2.
3."""

# ── Entity Recall（实体召回）────────────────────────────────────────────
ENTITY_EXTRACT_PROMPT = """从以下文本中提取所有关键实体（人名、地名、日期、技术术语、数字、产品名等）。以逗号分隔。

文本: {text}

关键实体:"""

# ── 测试数据集生成 ───────────────────────────────────
QA_GENERATION_PROMPT = """基于以下文档片段，生成3个高质量问答对。

要求:
- 问题多样化: 包含事实型、推理型、比较型问题
- 答案应具体、准确，基于文档内容
- 使用中文
- 输出格式（JSON）:
{{"qa_pairs": [{{"question": "...", "answer": "..."}}, ...]}}

文档片段:
{chunk}

问答对:"""


# ============================================================
# RAGAS 评估器
# ============================================================

class RAGASEvaluator:
    """使用 LLM-as-judge 计算 RAGAS 指标.

    使用示例:
        evaluator = RAGASEvaluator()
        metrics = evaluator.evaluate(
            question="什么是机器学习?",
            answer="机器学习是AI的一个分支...",
            contexts=["机器学习是...", "AI包括..."],
            ground_truth="机器学习是人工智能的一个分支，研究如何让计算机从数据中学习。"
        )
    """

    def __init__(self, model: str = None):
        self.model = model or settings.EVALUATION_LLM_MODEL or settings.LLM_MODEL

    # ── 主评估（完整，5个指标）───────────────────────

    def evaluate(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: str = "",
    ) -> RAGASMetrics:
        """对单个问答对运行所有 5 个 RAGAS 指标."""
        metrics = RAGASMetrics()

        if contexts:
            metrics.context_precision = self._compute_context_precision_batch(
                question, contexts
            )
        if contexts and ground_truth:
            metrics.context_recall = self.compute_context_recall(
                question, contexts, ground_truth
            )
        if answer and contexts:
            metrics.faithfulness = self.compute_faithfulness(
                answer, " ".join(contexts)
            )
        if answer and question:
            metrics.answer_relevancy = self.compute_answer_relevancy(
                question, answer
            )
        if contexts and ground_truth:
            metrics.context_entity_recall = self.compute_entity_recall(
                contexts, ground_truth
            )

        return metrics

    # ── 快速评估（2个指标，约快5倍）───────────────

    def evaluate_quick(
        self,
        question: str,
        answer: str,
        contexts: List[str],
    ) -> RAGASMetrics:
        """快速评估: 仅 Context Precision + Answer Relevancy.

        这两个指标不需要标准答案，且使用批处理 LLM 调用，
        比完整的 5 指标评估快约 5 倍.
        """
        metrics = RAGASMetrics()

        if contexts:
            metrics.context_precision = self._compute_context_precision_batch(
                question, contexts
            )
        if answer and question:
            metrics.answer_relevancy = self.compute_answer_relevancy(
                question, answer
            )

        return metrics

    # ── 1. Context Precision（上下文精确率）───────────────────────────────────

    def compute_context_precision(
        self, question: str, contexts: List[str]
    ) -> float:
        """测量检索上下文的信噪比.

        对每个上下文块，询问 LLM 是否相关.
        Precision@k = relevant_chunks / total_chunks，按位置加权.
        """
        if not contexts:
            return 0.0

        relevance = []
        for i, chunk in enumerate(contexts):
            # 截断块以提高效率
            chunk_short = chunk[:2000] if len(chunk) > 2000 else chunk
            prompt = CONTEXT_PRECISION_PROMPT.format(
                question=question, chunk=chunk_short
            )
            messages = [{"role": "user", "content": prompt}]

            try:
                raw = llm_client.chat_sync(
                    messages, temperature=0.0, max_tokens=5
                )
                is_relevant = "相关" in raw and "不相关" not in raw
                relevance.append(is_relevant)
            except LLMError:
                relevance.append(False)

        if not any(relevance):
            return 0.0

        # 加权精确率: 前面的位置获得更高权重
        total = sum(
            (1.0 / (i + 1)) if rel else 0.0
            for i, rel in enumerate(relevance)
        )
        max_possible = sum(1.0 / (i + 1) for i in range(len(relevance)))
        return total / max_possible if max_possible > 0 else 0.0

    # ── 1b. Context Precision（批处理）— 一次 LLM 调用处理所有块 ─

    def _compute_context_precision_batch(
        self, question: str, contexts: List[str]
    ) -> float:
        """使用单次批处理 LLM 调用而非 N 次调用计算 Context Precision.

        当 top_k=5 时，比逐块版本快约 5 倍.
        """
        if not contexts:
            return 0.0

        # 为提高速度，仅评估前 3 个块
        eval_contexts = contexts[:3]

        # 构建批处理 prompt
        chunk_parts = []
        for i, chunk in enumerate(eval_contexts):
            chunk_short = chunk[:1500] if len(chunk) > 1500 else chunk
            chunk_parts.append(f"[片段{i+1}]\n{chunk_short}")

        chunks_text = "\n\n".join(chunk_parts)
        prompt = CONTEXT_PRECISION_BATCH_PROMPT.format(
            question=question, chunks=chunks_text
        )
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(
                messages, temperature=0.0, max_tokens=50
            )
            # 逐行解析
            relevance = []
            for line in raw.strip().split("\n"):
                line = line.strip()
                if "不相关" in line:
                    relevance.append(False)
                elif "相关" in line:
                    relevance.append(True)

            # 填充到 eval_contexts 长度
            while len(relevance) < len(eval_contexts):
                relevance.append(False)

            if not any(relevance):
                return 0.0

            total = sum(
                (1.0 / (i + 1)) if rel else 0.0
                for i, rel in enumerate(relevance)
            )
            max_possible = sum(1.0 / (i + 1) for i in range(len(relevance)))
            return total / max_possible if max_possible > 0 else 0.0

        except LLMError:
            return 0.5

    # ── 2. Context Recall（上下文召回率）─────────────────────────────────────

    def compute_context_recall(
        self, question: str, contexts: List[str], ground_truth: str
    ) -> float:
        """测量是否检索到所有所需信息.

        从标准答案中提取声明，然后在单次批处理 LLM 调用中检查归因于上下文的情况.
        """
        if not ground_truth or not contexts:
            return 0.0

        # 从标准答案中提取声明
        claims = self._extract_claims(ground_truth)
        if not claims:
            return 1.0

        context_text = " ".join(contexts)[:5000]

        # 批处理: 在一次 LLM 调用中验证所有声明
        claim_lines = "\n".join(
            f"[{i+1}] {c}" for i, c in enumerate(claims)
        )
        prompt = CLAIM_ATTRIBUTION_BATCH_PROMPT.format(
            context=context_text, claims=claim_lines
        )
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(
                messages, temperature=0.0, max_tokens=len(claims) * 5 + 20
            )
            attributed = 0
            for line in raw.strip().split("\n"):
                line = line.strip()
                if "是" in line and "否" not in line:
                    attributed += 1
            # Pad: if LLM returned fewer lines than claims, count missing as "否"
            return attributed / len(claims) if claims else 0.0
        except LLMError:
            return 0.0

    # ── 3. Faithfulness（忠实度）────────────────────────────────────────

    def compute_faithfulness(
        self, answer: str, context: str
    ) -> float:
        """测量答案是否基于上下文.

        将答案分解为原子声明，在单次批处理 LLM 调用中验证所有声明是否与上下文一致.
        """
        if not answer or not context:
            return 0.0

        # 从答案中提取声明
        claims = self._extract_claims(answer)
        if not claims:
            return 1.0

        context_short = context[:5000]

        # 批处理: 在一次 LLM 调用中验证所有声明
        claim_lines = "\n".join(
            f"[{i+1}] {c}" for i, c in enumerate(claims)
        )
        prompt = FAITHFULNESS_VERIFY_BATCH_PROMPT.format(
            context=context_short, claims=claim_lines
        )
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(
                messages, temperature=0.0, max_tokens=len(claims) * 5 + 20
            )
            supported = 0
            for line in raw.strip().split("\n"):
                line = line.strip()
                if "是" in line and "否" not in line:
                    supported += 1
            return supported / len(claims) if claims else 0.0
        except LLMError:
            return 0.0

    # ── 4. Answer Relevancy（答案相关性）────────────────────────────────────

    def compute_answer_relevancy(
        self, question: str, answer: str
    ) -> float:
        """测量答案是否实际回答了问题.

        从答案生成反向问题，然后计算原始问题与每个反向问题之间的余弦相似度.
        """
        if not question or not answer:
            return 0.0

        # 生成反向问题
        reverse_questions = self._generate_reverse_questions(answer)
        if not reverse_questions:
            return 1.0

        # 只嵌入原始问题一次
        try:
            q_embedding = embedding_service.embed_single(question)
        except LLMError:
            return 0.5

        # Embed all reverse questions
        try:
            rq_embeddings = embedding_service.embed_batch(reverse_questions)
        except LLMError:
            return 0.5

        # 计算余弦相似度
        from smart_doc_search.services.context_compressor import cosine_similarity
        similarities = [
            cosine_similarity(q_embedding, rq_emb)
            for rq_emb in rq_embeddings
        ]

        return sum(similarities) / len(similarities) if similarities else 0.0

    # ── 5. Context Entity Recall（上下文实体召回率）──────────────────────────────

    def compute_entity_recall(
        self, contexts: List[str], ground_truth: str
    ) -> float:
        """测量标准答案中的实体在上下文中的覆盖程度."""
        if not ground_truth or not contexts:
            return 0.0

        # 从标准答案中提取实体
        gt_entities = self._extract_entities(ground_truth)
        if not gt_entities:
            return 1.0

        # 从合并的上下文中提取实体
        context_text = " ".join(contexts)[:5000]
        ctx_entities = self._extract_entities(context_text)

        # 计算召回率
        gt_set = set(gt_entities)
        ctx_set = set(ctx_entities)
        intersection = gt_set & ctx_set

        return len(intersection) / len(gt_set) if gt_set else 0.0

    # ── 辅助方法 ─────────────────────────────────────────────────

    def _extract_claims(self, text: str) -> List[str]:
        """通过 LLM 将文本分解为原子声明."""
        prompt = FAITHFULNESS_CLAIMS_PROMPT.format(answer=text)
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(
                messages, temperature=0.0, max_tokens=512
            )
            return self._parse_lines(raw)
        except LLMError:
            # 回退: 按句子边界分割
            from smart_doc_search.services.context_compressor import split_sentences
            return split_sentences(text)

    def _extract_entities(self, text: str) -> List[str]:
        """通过 LLM 从文本中提取关键实体."""
        prompt = ENTITY_EXTRACT_PROMPT.format(text=text[:2000])
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(
                messages, temperature=0.0, max_tokens=200
            )
            return [e.strip() for e in re.split(r'[,，、\n]', raw) if e.strip()]
        except LLMError:
            return []

    def _generate_reverse_questions(self, answer: str) -> List[str]:
        """从答案生成反向问题."""
        prompt = REVERSE_QUESTION_PROMPT.format(answer=answer[:2000])
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(
                messages, temperature=0.3, max_tokens=256
            )
            questions = []
            for line in raw.strip().split("\n"):
                line = re.sub(r'^[\d]+[\.\、\)]\s*', '', line.strip())
                if line and len(line) > 5:
                    questions.append(line)
            return questions[:3]
        except LLMError:
            return []

    def _parse_lines(self, raw: str) -> List[str]:
        """解析 LLM 输出中的换行分隔文本."""
        lines = []
        for line in raw.strip().split("\n"):
            # 去除编号
            line = re.sub(r'^[\d]+[\.\、\)\-]\s*', '', line.strip())
            line = line.strip().strip('"').strip("'").strip("- ")
            if line and len(line) > 3:
                lines.append(line)
        return lines


# ============================================================
# 测试数据集生成器
# ============================================================

import os as _os
import json as _json
from datetime import datetime as _datetime
from pathlib import Path as _Path

_EVAL_DATASETS_DIR = _Path(__file__).resolve().parent.parent / "eval_datasets"


class TestDatasetGenerator:
    """从文档块生成合成问答对用于评估.

    支持保存/加载，以便在配置更改时重复使用相同的测试集进行对等比较.
    """

    def __init__(self):
        self.model = settings.EVALUATION_LLM_MODEL or settings.LLM_MODEL

    # ── 持久化 ────────────────────────────────────────────

    @staticmethod
    def save_dataset(
        qa_pairs: List[Dict[str, str]],
        kb_id: int,
        label: str = "",
    ) -> str:
        """将问答对保存到 JSON 文件. 返回文件路径."""
        _EVAL_DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"kb_{kb_id}_{ts}"
        if label:
            stem += f"_{label}"
        path = _EVAL_DATASETS_DIR / f"{stem}.json"
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(qa_pairs, f, ensure_ascii=False, indent=2)
        log.info(f"TestDataset: saved {len(qa_pairs)} pairs → {path.name}")
        return str(path)

    @staticmethod
    def load_dataset(path: str) -> List[Dict[str, str]]:
        """从 JSON 文件加载问答对."""
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if isinstance(data, list) and len(data) > 0:
            log.info(f"TestDataset: loaded {len(data)} pairs from {_Path(path).name}")
            return data
        raise ValueError(f"Invalid dataset file: {path}")

    @staticmethod
    def list_datasets(kb_id: int = None) -> List[Dict[str, Any]]:
        """列出已保存的数据集文件，可选按知识库过滤.

        返回列表，每个元素包含 {path, name, size, created_at, pair_count}.
        """
        if not _EVAL_DATASETS_DIR.exists():
            return []
        results = []
        for f in sorted(
            _EVAL_DATASETS_DIR.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        ):
            prefix = f"kb_{kb_id}_" if kb_id else ""
            if kb_id and not f.name.startswith(prefix):
                continue
            stat = f.stat()
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = _json.load(fh)
                count = len(data) if isinstance(data, list) else 0
            except Exception:
                count = 0
            results.append({
                "path": str(f),
                "name": f.name,
                "size": stat.st_size,
                "created_at": _datetime.fromtimestamp(stat.st_mtime).strftime("%m-%d %H:%M"),
                "pair_count": count,
            })
        return results

    # ── 生成 ─────────────────────────────────────────────

    def generate_from_chunks(
        self, chunks: List[Dict[str, Any]], max_pairs: int = 30
    ) -> List[Dict[str, str]]:
        """从文档父块生成问答测试对.

        Args:
            chunks: 包含 'content' 键的字典列表.
            max_pairs: 要生成的最大问答对数量.

        Returns:
            {question, answer, source_chunk} 字典列表.
        """
        if not chunks:
            return []

        qa_pairs = []
        # 采样块以避免过多 API 调用
        import random
        sampled = random.sample(chunks, min(len(chunks), max(10, max_pairs // 3)))

        for chunk in sampled:
            content = chunk.get("content", "")
            if len(content) < 100:
                continue

            content_short = content[:2000]
            prompt = QA_GENERATION_PROMPT.format(chunk=content_short)
            messages = [{"role": "user", "content": prompt}]

            try:
                raw = llm_client.chat_sync(
                    messages, temperature=0.5, max_tokens=1024
                )
                pairs = self._parse_qa_json(raw)
                for pair in pairs:
                    pair["source_document_id"] = chunk.get("document_id")
                    pair["source_chunk_index"] = chunk.get("chunk_index")
                    pair["source_filename"] = chunk.get("filename", "")
                qa_pairs.extend(pairs)
            except LLMError as e:
                log.warning(f"QA generation failed for a chunk: {e}")
                continue

            if len(qa_pairs) >= max_pairs:
                break

        log.info(f"TestDataset: generated {len(qa_pairs)} QA pairs from {len(sampled)} chunks")
        return qa_pairs[:max_pairs]

    def _parse_qa_json(self, raw: str) -> List[Dict[str, str]]:
        """从 LLM JSON 输出中解析问答对."""
        try:
            # 尝试提取 JSON 块
            json_match = re.search(
                r'\{[^{}]*"qa_pairs"[^{}]*\[.*?\][^{}]*\}',
                raw, re.DOTALL
            )
            if json_match:
                data = json.loads(json_match.group())
                pairs = data.get("qa_pairs", [])
                return [
                    {"question": p.get("question", ""), "answer": p.get("answer", "")}
                    for p in pairs if p.get("question") and p.get("answer")
                ]
        except (json.JSONDecodeError, KeyError):
            pass

        # 回退: 尝试逐行解析
        lines = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if "Q:" in line or "问:" in line or "问题:" in line:
                lines.append(line)
        return [{"question": l, "answer": ""} for l in lines]


# ============================================================
# Singleton
# ============================================================

ragas_evaluator = RAGASEvaluator()
test_dataset_generator = TestDatasetGenerator()

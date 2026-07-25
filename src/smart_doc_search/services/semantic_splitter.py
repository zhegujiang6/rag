"""Semantic chunking — use LLM to identify topic boundaries for chunk splitting.

工作原理：
1. 将文档段落分为批次（每批最多 ~40 段）
2. 每批发送给 LLM，让 LLM 找出话题转换的边界
3. 用边界索引将段落分组，每组是一个语义连贯的单元
4. 语义单元再交给现有的固定大小分割器做二次切分

Fallback：如果 LLM 调用失败，回退到固定大小切分（不影响入库流程）。
"""
import json
import re
from typing import List, Dict, Any
from loguru import logger as log
from smart_doc_search.services.llm_client import llm_client


class SemanticSplitter:
    """用 LLM 识别文档段落中的语义话题边界，指导切分位置。"""

    def __init__(self, batch_size: int = 40):
        self.batch_size = batch_size
        self.llm = llm_client

    def identify_boundaries(self, segments: List[Dict[str, Any]]) -> List[int]:
        """识别语义边界，返回切分后的段落索引。

        Args:
            segments: _segment_text() 的输出，每个元素含 "text", "type", "page"

        Returns:
            sorted list of split-after indices.
            例如 [5, 12] 表示在第 5 段后切一刀、第 12 段后切一刀。
            segments[0:6] → 第1组, segments[6:13] → 第2组, segments[13:] → 第3组。
        """
        if len(segments) <= 1:
            return []

        all_boundaries: List[int] = []

        for batch_start in range(0, len(segments), self.batch_size):
            batch = segments[batch_start:batch_start + self.batch_size]
            if len(batch) <= 1:
                continue

            boundaries = self._process_batch(batch, batch_start)
            all_boundaries.extend(boundaries)

        return sorted(set(all_boundaries))

    def group_by_boundaries(
        self, segments: List[Dict[str, Any]], boundaries: List[int],
    ) -> List[Dict[str, Any]]:
        """按语义边界将段落合并为语义组，返回新的 segment 列表。

        每个语义组内的段落用 \n\n 拼接，保留 type 和 page 信息。
        """
        if not boundaries:
            # 没有边界 → 整个文档一个语义组（不改变原始分段）
            return segments

        groups: List[Dict[str, Any]] = []
        start = 0

        # 排序保证递增
        for end in sorted(boundaries):
            end = min(end + 1, len(segments))  # boundary 是"在此之后切"
            if end > start:
                group_segs = segments[start:end]
                groups.append(self._merge_group(group_segs))
            start = end

        # 最后一组（boundaries 之后的剩余段落）
        if start < len(segments):
            groups.append(self._merge_group(segments[start:]))

        log.info(
            f"语义分组完成 | 原始段落: {len(segments)} | "
            f"语义边界: {len(boundaries)} | 语义组: {len(groups)}"
        )
        return groups

    # ── private ──────────────────────────────────────────────────────

    def _merge_group(self, segs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """将同一语义组的多个段落合并为一个 segment dict。"""
        text = "\n\n".join(s["text"] for s in segs)
        # 取第一个非 None 的 page
        page = next((s.get("page") for s in segs if s.get("page")), None)
        # 类型取多数
        types = [s.get("type", "paragraph") for s in segs]
        dom_type = max(set(types), key=types.count) if types else "paragraph"
        return {"text": text, "type": dom_type, "page": page}

    def _process_batch(
        self, batch: List[Dict[str, Any]], batch_offset: int,
    ) -> List[int]:
        """处理一批段落，返回绝对边界索引列表。"""
        prompt = self._build_prompt(batch)

        try:
            response = self.llm.chat_sync(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=512,
                max_retries=2,
            )
            boundaries = self._parse_response(response, len(batch), batch_offset)
            log.debug(
                f"语义切分批次 offset={batch_offset} size={len(batch)} "
                f"→ 边界数={len(boundaries)}"
            )
            return boundaries
        except Exception as e:
            log.warning(f"语义切分 LLM 调用失败，回退到固定大小切分: {e}")
            return []

    def _build_prompt(self, batch: List[Dict[str, Any]]) -> str:
        """构建发给 LLM 的 prompt。"""
        items = []
        for i, seg in enumerate(batch):
            # 每段取前 400 字，足够判断话题
            preview = seg["text"][:400].replace("\n", " ")
            items.append(f"[{i}] {preview}")

        numbered = "\n\n".join(items)

        return f"""你是一个文档结构分析专家。以下是一篇文档的若干连续段落，每个段落以 [序号] 开头。

请找出**话题发生明显转换**的位置（只标真正换话题的地方，不要标得太密集）。

话题转换的判断标准：
1. 开始讨论一个全新的主题、概念或业务场景
2. 从理论/背景切换到具体操作/案例，或反之
3. 从一类问题切换到另一类独立的问题

**注意**：
- 每个语义块应该包含 3~10 个段落，不要切得太细
- 如果整批段落属于同一话题，返回 []
- 只返回 JSON 数组，不要有任何其他文字

段落内容：
{numbered}

请返回 JSON 数组（例如 [3, 8] 表示在第3段后和第8段后切分）："""

    def _parse_response(
        self, response: str, batch_len: int, batch_offset: int,
    ) -> List[int]:
        """从 LLM 响应中提取边界索引数组。"""
        # 尝试匹配 JSON 数组
        match = re.search(r"\[[\d,\s]*\]", response)
        if not match:
            log.warning(f"语义切分响应无法解析: {response[:200]}")
            return []

        try:
            boundaries = json.loads(match.group())
        except json.JSONDecodeError:
            log.warning(f"语义切分 JSON 解析失败: {match.group()}")
            return []

        if not isinstance(boundaries, list):
            return []

        # 验证并转为绝对索引
        result = []
        for idx in boundaries:
            if isinstance(idx, int) and 0 <= idx < batch_len - 1:
                result.append(batch_offset + idx)

        return sorted(result)


# ── 单例 ────────────────────────────────────────────────────────────
semantic_splitter = SemanticSplitter()

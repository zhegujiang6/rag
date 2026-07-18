"""文档分割器 — 父-子块策略实现

策略说明：
- 子块（Sub-chunk）：较小的文本片段（约256 tokens），用于精确的向量检索（召回率高）
- 父块（Parent-chunk）：较大的上下文（约1024 tokens），包含多个子块，用于LLM生成回答（上下文完整）

检索流程：用户提问 → 向量搜索匹配子块 → 返回对应的父块 → 作为LLM的上下文生成回答
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import tiktoken
from config import settings
from services.document_parser import ParsedDocument, PageInfo, DocumentProcessingError
from services.semantic_splitter import semantic_splitter
from loguru import logger as log


# ============================================================
# 数据结构定义
# ============================================================
@dataclass
class Chunk:
    """单个文本块，用于存储分割后的文本片段及其元数据"""
    index: int               # 块在文档中的索引（从0开始）
    content: str             # 文本块的实际内容
    token_count: int         # 该块的 token 数量（用于控制大小）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据（来源格式、标题、页码等）


@dataclass
class ChunkPair:
    """父块和子块的配对关系，父块用于LLM生成，子块用于向量检索"""
    parent: Chunk            # 父块（较大的上下文，用于LLM生成回答）
    subs: List[Chunk]        # 子块列表（较小的片段，用于精确向量检索）


# ============================================================
# Token 计数器
# ============================================================
class TokenCounter:
    """使用 tiktoken 库计算文本的 token 数量，用于控制块大小"""

    def __init__(self, encoding_name: str = "cl100k_base"):
        """初始化 token 编码器（cl100k_base 适用于 GPT-4 和 text-embedding-3 模型）"""
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            # 如果指定编码加载失败，回退到 cl100k_base
            log.warning(f"编码 '{encoding_name}' 加载失败，回退到 'cl100k_base'")
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        """计算文本的 token 数量，返回整数"""
        return len(self.encoding.encode(text))

    def truncate(self, text: str, max_tokens: int) -> str:
        """将文本截断到指定的 token 数量，保持语义完整"""
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.encoding.decode(tokens[:max_tokens])


# ============================================================
# 文档分割器核心类
# ============================================================
class DocumentSplitter:
    """文档分割器核心类，将长文档切分为适合向量检索和LLM上下文的父-子块配对"""

    def __init__(
        self,
        sub_chunk_size: int = None,
        parent_chunk_size: int = None,
        chunk_overlap: int = None,
        subs_per_parent: int = None,
    ):
        """初始化分割器参数，未指定时从配置文件读取默认值"""
        self.sub_chunk_size = sub_chunk_size or settings.SUB_CHUNK_SIZE      # 子块大小（约256 tokens）
        self.parent_chunk_size = parent_chunk_size or settings.PARENT_CHUNK_SIZE  # 父块大小（约1024 tokens）
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP          # 块之间的重叠大小（保持上下文连贯）
        self.subs_per_parent = subs_per_parent or settings.SUB_CHUNKS_PER_PARENT  # 每个父块包含的子块数
        self.token_counter = TokenCounter()  # 创建 token 计数器实例

    def split(self, parsed_doc: ParsedDocument) -> List[ChunkPair]:
        """分割文档主入口，执行三步分割流程，返回父-子块配对列表"""
        log.info(
            f"开始分割文档 | 子块大小: {self.sub_chunk_size} tokens | "
            f"父块大小: {self.parent_chunk_size} tokens | "
            f"重叠: {self.chunk_overlap} tokens | 每父块子块数: {self.subs_per_parent}"
        )

        try:
            # 步骤1: 将文本分割为原子段落（识别代码块、表格等特殊格式）
            segments = self._segment_text(parsed_doc)

            # 步骤1.5: 【语义切分】如果启用，用 LLM 识别话题边界，合并同主题段落
            if settings.SEMANTIC_CHUNKING_ENABLED:
                log.info("🔍 语义切分已启用，正在用 LLM 识别话题边界...")
                boundaries = semantic_splitter.identify_boundaries(segments)
                segments = semantic_splitter.group_by_boundaries(segments, boundaries)

            # 步骤2: 将段落合并为子块（目标大小为 sub_chunk_size）
            sub_chunks = self._build_chunks(
                segments, target_size=self.sub_chunk_size, overlap=self.chunk_overlap,
                metadata_base={
                    "source_format": parsed_doc.metadata.get("format", ""),
                    "source_title": parsed_doc.metadata.get("title", ""),
                },
            )

            # 步骤3: 将子块合并为父块，形成配对关系
            chunk_pairs = self._build_parent_child_pairs(sub_chunks, parsed_doc)

            log.info(
                f"文档分割完成 | 段落数: {len(segments)} | "
                f"子块数: {len(sub_chunks)} | 父块数: {len(chunk_pairs)}"
            )
            return chunk_pairs
        except Exception as e:
            log.error(f"文档分割失败: {str(e)}")
            raise DocumentProcessingError(f"文档分割失败: {str(e)}")

    # ============================================================
# 段落分割（识别代码块、表格等特殊格式）
# ============================================================
    def _segment_text(self, parsed_doc: ParsedDocument) -> List[Dict[str, Any]]:
        """将文本分割为原子段落，识别并保留代码块和表格等特殊格式"""
        segments = []
        text = parsed_doc.text

        # 按双换行符分割原始段落
        raw_paragraphs = re.split(r"\n\s*\n", text)
        in_code_block = False  # 是否在代码块内
        code_buffer = []       # 代码块内容缓冲区

        for para in raw_paragraphs:
            para = para.strip()
            if not para:
                continue

            # 检测代码块边界（以 ``` 开头）
            if para.startswith("```"):
                if in_code_block:
                    # 代码块结束：将缓冲区内容作为完整代码块添加
                    code_buffer.append(para)
                    segments.append({"text": "\n".join(code_buffer), "type": "code_block", "page": None})
                    code_buffer = []
                    in_code_block = False
                else:
                    # 代码块开始：开始收集代码内容
                    in_code_block = True
                    code_buffer.append(para)
                continue

            # 在代码块内，继续收集内容
            if in_code_block:
                code_buffer.append(para)
                continue

            # 检测表格内容（包含 | 分隔符的行，且至少2行）
            lines = para.split("\n")
            if len(lines) >= 2:
                pipe_lines = [l for l in lines if "|" in l]
                if len(pipe_lines) >= 2:
                    segments.append({"text": para, "type": "table", "page": None})
                    continue

            # 普通段落
            segments.append({"text": para, "type": "paragraph", "page": None})

        # 处理未关闭的代码块（文件末尾未以 ``` 结束）
        if in_code_block and code_buffer:
            segments.append({"text": "\n".join(code_buffer), "type": "code_block", "page": None})

        # 为段落附加页码信息（通过文本匹配）
        if parsed_doc.pages:
            self._attach_page_numbers(segments, parsed_doc.pages)

        return segments

    def _attach_page_numbers(self, segments: List[Dict], pages: List[PageInfo]):
        """通过文本匹配为每个段落附加所属页码（取段落前100字符匹配）"""
        for seg in segments:
            seg_text_clean = seg["text"].strip()[:100]
            for page in pages:
                if seg_text_clean in page.text:
                    seg["page"] = page.page_num
                    break

    # ============================================================
# 构建子块（合并段落到目标 token 大小）
# ============================================================
    def _build_chunks(self, segments, target_size, overlap, metadata_base):
        """将段落合并为指定大小的块，处理表格/代码块保留、超长段分割、重叠等逻辑"""
        chunks = []           # 最终的块列表
        current_texts = []    # 当前缓冲区的文本片段
        current_tokens = 0    # 当前缓冲区的 token 总数
        chunk_idx = 0         # 块索引计数器

        for seg in segments:
            seg_text = seg["text"]
            seg_tokens = self.token_counter.count(seg_text)

            # 表格和代码块：如果大小不超过目标的2倍，作为独立块保留（避免被拆分）
            if seg["type"] in ("table", "code_block") and seg_tokens <= target_size * 2:
                if current_texts:
                    # 先输出当前缓冲区的内容
                    chunks.append(self._make_chunk(current_texts, chunk_idx, metadata_base, seg))
                    chunk_idx += 1
                    current_texts = []
                    current_tokens = 0
                # 将表格/代码块作为独立块添加
                chunks.append(self._make_chunk([seg_text], chunk_idx, metadata_base, seg))
                chunk_idx += 1
                continue

            # 如果添加当前段会超过目标大小，先输出当前缓冲区
            if current_tokens + seg_tokens > target_size and current_texts:
                chunks.append(self._make_chunk(current_texts, chunk_idx, metadata_base, seg))
                chunk_idx += 1

                # 添加重叠部分（从上个块末尾截取，保持上下文连贯）
                if overlap > 0 and current_texts:
                    last_text = current_texts[-1]
                    overlap_tokens = self.token_counter.count(last_text)
                    if overlap_tokens > overlap:
                        overlap_text = self.token_counter.truncate(last_text, overlap)
                        current_texts = [overlap_text]
                        current_tokens = self.token_counter.count(overlap_text)
                    else:
                        current_texts = []
                        current_tokens = 0
                else:
                    current_texts = []
                    current_tokens = 0

            # 处理超长段落：超过目标大小的段落按句子分割
            if seg_tokens > target_size:
                sub_parts = self._split_long_segment(seg_text, target_size)
                for part in sub_parts:
                    if part.strip():
                        chunks.append(Chunk(
                            index=chunk_idx, content=part.strip(),
                            token_count=self.token_counter.count(part),
                            metadata={**metadata_base, "type": seg.get("type", "paragraph"), "page": seg.get("page")},
                        ))
                        chunk_idx += 1
                continue

            # 添加到当前缓冲区
            current_texts.append(seg_text)
            current_tokens += seg_tokens

        # 输出剩余的缓冲区内容（文件末尾的剩余部分）
        if current_texts:
            chunks.append(self._make_chunk(current_texts, chunk_idx, metadata_base, None))

        return chunks

    def _make_chunk(self, texts, idx, meta_base, current_seg=None):
        """从文本列表创建一个 Chunk 对象，合并文本并附加元数据"""
        content = "\n\n".join(texts)
        meta = {**meta_base}
        if current_seg:
            meta["type"] = current_seg.get("type", "paragraph")
            meta["page"] = current_seg.get("page")
        return Chunk(index=idx, content=content, token_count=self.token_counter.count(content), metadata=meta)

    def _split_long_segment(self, text: str, max_size: int) -> List[str]:
        """按句子边界分割超长段落（支持中英文标点），保持语义完整性"""
        parts = []
        # 按句号、感叹号、问号分割句子（保留标点在句子末尾）
        sentences = re.split(r'(?<=[。！？.!?])\s*', text)
        current_parts = []
        current_len = 0

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            sent_tokens = self.token_counter.count(sent)

            # 如果添加当前句子会超过目标大小，先输出当前累积的句子
            if current_len + sent_tokens > max_size and current_parts:
                parts.append("".join(current_parts))
                current_parts = []
                current_len = 0

            current_parts.append(sent)
            current_len += sent_tokens

        # 输出剩余的句子
        if current_parts:
            parts.append("".join(current_parts))

        return parts if parts else [text]

    # ============================================================
# 构建父-子块配对
# ============================================================
    def _build_parent_child_pairs(self, sub_chunks, parsed_doc):
        """将子块合并为父块，每个父块包含多个连续子块，形成配对关系"""
        pairs = []

        # 按固定数量的子块分组（每 subs_per_parent 个子块组成一个父块）
        for i in range(0, len(sub_chunks), self.subs_per_parent):
            batch = sub_chunks[i:i + self.subs_per_parent]
            if not batch:
                continue

            # 父块内容 = 所有子块内容拼接（保持上下文完整）
            parent_content = "\n\n".join(ch.content for ch in batch)
            parent_tokens = self.token_counter.count(parent_content)

            # 如果父块太大，截断到目标大小（避免超出 LLM 上下文限制）
            if parent_tokens > self.parent_chunk_size:
                parent_content = self.token_counter.truncate(parent_content, self.parent_chunk_size)
                parent_tokens = self.parent_chunk_size

            # 收集所有子块涉及的页码信息
            pages = set()
            for ch in batch:
                if ch.metadata.get("page"):
                    pages.add(ch.metadata["page"])

            # 创建父块对象
            parent = Chunk(
                index=i // self.subs_per_parent,
                content=parent_content,
                token_count=parent_tokens,
                metadata={
                    "type": "parent",                    # 标记为父块类型
                    "pages": sorted(list(pages)),        # 包含的页码列表
                    "sub_count": len(batch),             # 包含的子块数量
                    "source_format": parsed_doc.metadata.get("format", ""),
                    "source_title": parsed_doc.metadata.get("title", ""),
                },
            )
            # 创建父-子块配对并添加到结果列表
            pairs.append(ChunkPair(parent=parent, subs=list(batch)))

        return pairs


# ============================================================
# 单例实例
# ============================================================
# 创建全局单例，其他模块直接导入使用，避免重复创建分割器实例
document_splitter = DocumentSplitter()

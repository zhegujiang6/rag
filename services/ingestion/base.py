"""统一数据模型与接入层基类.

轻量数据中台 — 第一层：数据接入层（Data Ingestion）

核心思想：不管数据从哪来（文件/网页/飞书/Notion...），
最后都输出同一种格式 RawDocument，进入统一的处理管道。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict


# ============================================================
# 自定义异常
# ============================================================

class IngestionError(Exception):
    """数据接入失败时抛出的异常."""
    pass


# ============================================================
# 统一数据模型
# ============================================================

@dataclass
class RawDocument:
    """接入层统一输出格式 — 所有数据源的"中间表示".

    无论原始数据是 PDF 文件、网页 HTML 还是飞书文档，
    Ingestor 负责将其转换为这个统一结构，然后交给 Pipeline 处理.

    Attributes:
        content: 纯文本内容（已提取、已清洗）.
        source_type: 来源类型标识，如 "file", "web", "feishu", "notion".
        source_identifier: 来源唯一标识，如文件名、URL.
        metadata: 来源特有的元数据（格式、作者、页码等）.
    """

    content: str
    source_type: str
    source_identifier: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# 接入器抽象基类
# ============================================================

class BaseIngestor(ABC):
    """数据接入器基类 — 所有数据源适配器的抽象.

    每新增一种数据源，只需：
    1. 继承 BaseIngestor
    2. 实现 ingest() 方法
    3. 返回 RawDocument

    示例:
        class WebIngestor(BaseIngestor):
            source_type = "web"

            def ingest(self, source: str) -> RawDocument:
                html = crawl(source)
                text = extract_text(html)
                return RawDocument(
                    content=text,
                    source_type=self.source_type,
                    source_identifier=source,
                )
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """返回此接入器处理的数据源类型标识."""
        ...

    @abstractmethod
    def ingest(self, source: Any) -> RawDocument:
        """从数据源提取内容，转换为 RawDocument.

        Args:
            source: 数据源，具体类型由子类决定（文件路径、URL、API 响应等）.

        Returns:
            RawDocument: 统一格式的文档内容.

        Raises:
            IngestionError: 接入失败时抛出.
        """
        ...

"""数据接入层（Data Ingestion） — 轻量数据中台第一层.

将各类数据源（文件、网页、飞书、Notion...）统一转换为 RawDocument 格式，
进入后续的 DocumentPipeline 处理管道.

公共导出:
    RawDocument  — 统一数据模型
    BaseIngestor — 接入器抽象基类
    FileIngestor — 文件接入适配器
    WebIngestor  — 网页接入适配器
    IngestionError — 接入异常
"""

from smart_doc_search.services.ingestion.base import RawDocument, BaseIngestor, IngestionError
from smart_doc_search.services.ingestion.file_ingestor import FileIngestor
from smart_doc_search.services.ingestion.web_ingestor import WebIngestor

__all__ = [
    "RawDocument",
    "BaseIngestor",
    "FileIngestor",
    "WebIngestor",
    "IngestionError",
]

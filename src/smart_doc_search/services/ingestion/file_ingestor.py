"""文件接入器 — 将上传的文件转换为 RawDocument.

轻量数据中台 — 第一个适配器实现.
将现有的文件上传 + DocumentParser 逻辑封装为 BaseIngestor 接口.
"""

import os
import uuid
from typing import Any

from smart_doc_search.core.config import settings
from smart_doc_search.services.document_parser import document_parser, DocumentProcessingError
from smart_doc_search.services.ingestion.base import BaseIngestor, RawDocument, IngestionError
from loguru import logger as log


class FileIngestor(BaseIngestor):
    """文件数据源适配器.

    负责：
    1. 将上传文件保存到本地磁盘
    2. 调用 DocumentParser 解析文件内容
    3. 返回统一的 RawDocument 格式
    """

    source_type = "file"

    def ingest(self, source: Any) -> RawDocument:
        """从上传文件中提取文本内容.

        Args:
            source: Streamlit UploadedFile 对象，需要有 .name, .getbuffer(), .size 属性.

        Returns:
            RawDocument: 包含纯文本内容和文件元数据.

        Raises:
            IngestionError: 文件保存或解析失败时抛出.
        """
        try:
            # ── 1. 提取文件信息 ──
            filename = getattr(source, "name", "unknown")
            file_ext = os.path.splitext(filename)[1].lower().lstrip(".")
            file_size = getattr(source, "size", 0)

            log.info(f"FileIngestor: 开始接入文件 '{filename}' (类型: {file_ext})")

            # ── 2. 保存文件到本地 ──
            storage_name = f"{uuid.uuid4().hex}.{file_ext}"
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            storage_path = os.path.join(settings.UPLOAD_DIR, storage_name)

            # 兼容 streamlit UploadedFile 和普通文件路径
            if hasattr(source, "getbuffer"):
                # Streamlit UploadedFile
                with open(storage_path, "wb") as f:
                    f.write(source.getbuffer())
            elif hasattr(source, "read"):
                # 类文件对象
                with open(storage_path, "wb") as f:
                    f.write(source.read())
            else:
                # 假设是文件路径字符串
                import shutil
                shutil.copy(source, storage_path)

            # ── 3. 解析文档内容 ──
            parsed = document_parser.parse(storage_path, file_ext)

            # ── 4. 构建统一 RawDocument ──
            raw_doc = RawDocument(
                content=parsed.text,
                source_type=self.source_type,
                source_identifier=filename,
                metadata={
                    **parsed.metadata,
                    "storage_path": storage_path,
                    "storage_name": storage_name,
                    "file_ext": file_ext,
                    "file_size": file_size,
                    "page_count": len(parsed.pages),
                    "images": parsed.images,
                },
            )

            log.info(
                f"FileIngestor: 接入完成 | 文件: '{filename}' | "
                f"字符数: {len(raw_doc.content)} | 页数: {len(parsed.pages)}"
            )
            return raw_doc

        except DocumentProcessingError:
            # 清理已保存的文件
            if 'storage_path' in locals() and os.path.exists(storage_path):
                try:
                    os.remove(storage_path)
                except Exception:
                    pass
            raise IngestionError(f"文件解析失败: {filename}")
        except IngestionError:
            raise
        except Exception as e:
            log.error(f"FileIngestor: 接入失败 - {e}")
            if 'storage_path' in locals() and os.path.exists(storage_path):
                try:
                    os.remove(storage_path)
                except Exception:
                    pass
            raise IngestionError(f"文件接入失败: {str(e)}")

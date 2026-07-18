"""文档处理管道 — 统一的文档加工流水线.

轻量数据中台 — 第二层：数据处理管道（Processing Pipeline）

核心思想：所有文档（无论来源）都走同一套加工流程，可插拔、可配置.

流程: RawDocument → ParsedDocument → 切分 → 向量化 → 存储 → 标签
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from smart_doc_search.core.config import settings
from smart_doc_search.data.database import Document, ParentChunk, SubChunk, SessionLocal
from smart_doc_search.services.document_parser import ParsedDocument, PageInfo
from smart_doc_search.services.document_splitter import document_splitter
from smart_doc_search.services.embedding_service import embedding_service
from smart_doc_search.services.image_understanding import image_understanding_service
from smart_doc_search.services.vector_store import vector_store
from smart_doc_search.services.tag_service import tag_service
from smart_doc_search.services.ingestion.base import RawDocument
from loguru import logger as log


# ============================================================
# 管道结果
# ============================================================

@dataclass
class PipelineResult:
    """DocumentPipeline 的执行结果."""
    document_id: int
    chunk_count: int
    status: str                        # "completed" | "failed"
    error_message: Optional[str] = None


# ============================================================
# 文档处理管道
# ============================================================

class DocumentPipeline:
    """统一的文档处理管道.

    将 RawDocument 经过 解析→切分→向量化→存储→标签 的完整流程，
    每一步更新 Document.status 并通过 progress_callback 报告进度.

    Usage:
        pipeline = DocumentPipeline()
        result = pipeline.run(
            raw_doc=raw_doc,
            kb_id=1,
            db=session,
            doc_id=42,
            progress_callback=lambda status, pct: print(f"{status}: {pct}"),
        )
    """

    # ── 批量嵌入的 API 限制 ──
    EMBED_BATCH_SIZE = 10

    def run(
        self,
        raw_doc: RawDocument,
        kb_id: int,
        db: Session,
        doc_id: int,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> PipelineResult:
        """执行完整的文档处理流程.

        Args:
            raw_doc: 接入层产出的统一文档格式.
            kb_id: 目标知识库 ID（0 或 None 表示不关联知识库）.
            db: 数据库会话.
            doc_id: 已创建的 Document 记录 ID.
            progress_callback: 进度回调 (status: str, progress: float).

        Returns:
            PipelineResult: 处理结果.
        """
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                return PipelineResult(
                    document_id=doc_id, chunk_count=0,
                    status="failed", error_message="文档记录不存在",
                )

            # ── Stage 1: Convert RawDocument → ParsedDocument ──
            doc.status = "parsing"
            db.commit()
            self._report(progress_callback, "parsing", 0.1)

            parsed = ParsedDocument(
                text=raw_doc.content,
                pages=[
                    PageInfo(page_num=1, text=raw_doc.content)
                ],
                metadata={
                    **(raw_doc.metadata or {}),
                    "source_type": raw_doc.source_type,
                    "source_identifier": raw_doc.source_identifier,
                },
                images=list((raw_doc.metadata or {}).get("images", [])),
            )

            # 视觉转写必须发生在分块前，才能让图片内的文字、表格和图表信息
            # 同时进入普通文本索引；多模态向量仅用于语义召回，不能替代 OCR。
            self._enrich_images_with_text(parsed)

            # ── Stage 2: Split into chunks ──
            doc.status = "chunking"
            db.commit()
            self._report(progress_callback, "chunking", 0.3)

            chunk_pairs = document_splitter.split(parsed)

            # ── Stage 3: Generate embeddings ──
            doc.status = "embedding"
            db.commit()
            self._report(progress_callback, "embedding", 0.5)

            # Flatten sub-chunks for batch embedding
            all_sub_chunks = []
            for pair in chunk_pairs:
                all_sub_chunks.extend(pair.subs)

            all_embeddings = []
            total = len(all_sub_chunks)
            for i in range(0, total, self.EMBED_BATCH_SIZE):
                batch = all_sub_chunks[i:i + self.EMBED_BATCH_SIZE]
                texts = [ch.content for ch in batch]
                embeddings = embedding_service.embed_batch(texts)
                all_embeddings.extend(embeddings)
                if progress_callback and total > 0:
                    progress = 0.5 + 0.4 * (i / total)
                    self._report(progress_callback, "embedding", progress)

            # ── Stage 4: Persist to MySQL + ChromaDB ──
            chroma_chunks = []
            multimodal_chunks = []
            for pair in chunk_pairs:
                pc = ParentChunk(
                    document_id=doc.id,
                    chunk_index=pair.parent.index,
                    content=pair.parent.content,
                    token_count=pair.parent.token_count,
                    chunk_metadata=pair.parent.metadata,
                )
                db.add(pc)
                db.flush()  # get pc.id

                for sub in pair.subs:
                    chroma_id = f"chunk_{doc.id}_{sub.index}"
                    sc = SubChunk(
                        parent_chunk_id=pc.id,
                        document_id=doc.id,
                        chunk_index=sub.index,
                        content=sub.content,
                        token_count=sub.token_count,
                        chroma_id=chroma_id,
                        chunk_metadata=sub.metadata,
                    )
                    db.add(sc)

                    chroma_chunks.append({
                        "chroma_id": chroma_id,
                        "document_id": doc.id,
                        "parent_chunk_id": pc.id,
                        "chunk_index": sub.index,
                        "content": sub.content,
                        "metadata": sub.metadata,
                    })

            # 图片使用独立的父/子块保存，使多模态召回的结果能够复用现有的
            # parent expansion 和引用展示逻辑。图片本身只写入多模态索引。
            for image_index, image in enumerate(parsed.images):
                image_path = image.get("path")
                if not image_path:
                    continue
                page = image.get("page", 1)
                context = self._image_context(parsed, page)
                extracted_text = image.get("extracted_text", "")
                description = f"图片（第 {page} 页）\n识别内容：{extracted_text}\n相邻文本：{context}" if extracted_text else (f"图片（第 {page} 页）\n相邻文本：{context}" if context else f"图片（第 {page} 页）")
                pc = ParentChunk(
                    document_id=doc.id,
                    chunk_index=len(chunk_pairs) + image_index,
                    content=description,
                    token_count=len(description),
                    chunk_metadata={"type": "image", "page": page, "image_path": image_path},
                )
                db.add(pc)
                db.flush()
                chroma_id = f"image_{doc.id}_{image_index}"
                db.add(SubChunk(
                    parent_chunk_id=pc.id,
                    document_id=doc.id,
                    chunk_index=len(all_sub_chunks) + image_index,
                    content=description,
                    token_count=len(description),
                    chroma_id=chroma_id,
                    chunk_metadata={"type": "image", "page": page, "image_path": image_path},
                ))
                multimodal_chunks.append({
                    "chroma_id": chroma_id,
                    "parent_chunk_id": pc.id,
                    "document_id": doc.id,
                    "page": page,
                    "path": image_path,
                    "description": description,
                })

            db.commit()

            # Write vectors to ChromaDB
            if kb_id and chroma_chunks:
                vector_store.add_chunks(kb_id, chroma_chunks, all_embeddings)

            if kb_id and settings.MULTIMODAL_EMBEDDING_ENABLED:
                for image in multimodal_chunks:
                    try:
                        embedding = embedding_service.embed_multimodal([
                            {"text": image["description"][:1200]},
                            {"image": embedding_service.image_as_data_uri(image["path"])},
                        ])
                        vector_store.add_multimodal_chunk(
                            kb_id, image["chroma_id"], image["description"], embedding,
                            {
                                "document_id": image["document_id"],
                                "parent_chunk_id": image["parent_chunk_id"],
                                "page": image["page"],
                                "type": "image",
                            },
                        )
                    except Exception as image_error:
                        # 单张图片失败不应导致已完成的文字文档整体不可用。
                        log.warning(f"Pipeline: 图片多模态索引失败 {image['path']}: {image_error}")

            # ── Stage 4.5: Rebuild BM25 index for hybrid search ──
            if kb_id and settings.HYBRID_SEARCH_ENABLED:
                try:
                    from smart_doc_search.services.hybrid_search import hybrid_search
                    hybrid_search.rebuild_for_kb(kb_id, db)
                    log.info(f"Pipeline: BM25 index rebuilt for kb_{kb_id}")
                except Exception as bm25_err:
                    log.warning(f"Pipeline: BM25 index rebuild failed (non-fatal): {bm25_err}")

            # ── Stage 5: Auto-tagging ──
            self._report(progress_callback, "tagging", 0.9)
            try:
                full_text = " ".join(ch.get("content", "") for ch in chroma_chunks)
                tag_service.auto_tag_document(doc.id, full_text, db=db)
            except Exception as tag_err:
                log.warning(f"自动标签提取失败: {tag_err}")

            # ── Stage 6: Mark completed ──
            doc.status = "completed"
            doc.chunk_count = len(all_sub_chunks) + len(multimodal_chunks)
            db.commit()
            self._report(progress_callback, "completed", 1.0)

            log.info(
                f"Pipeline: 文档处理完成 | doc_id={doc_id} | "
                f"子块数: {len(all_sub_chunks)} | 父块数: {len(chunk_pairs)}"
            )

            return PipelineResult(
                document_id=doc_id,
                chunk_count=len(all_sub_chunks),
                status="completed",
            )

        except Exception as e:
            log.error(f"Pipeline: 处理失败 doc_id={doc_id} - {e}")
            # 尝试标记失败状态
            try:
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc:
                    doc.status = "failed"
                    doc.error_message = str(e)
                    db.commit()
            except Exception:
                pass
            return PipelineResult(
                document_id=doc_id, chunk_count=0,
                status="failed", error_message=str(e),
            )

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    def _report(callback: Optional[Callable], status: str, progress: float):
        """安全调用进度回调."""
        if callback:
            try:
                callback(status, progress)
            except Exception:
                pass  # 进度报告失败不应中断处理

    @staticmethod
    def _image_context(parsed: ParsedDocument, page: int) -> str:
        """提供页面附近文字作为图片 embedding 的辅助上下文。"""
        for page_info in parsed.pages:
            if page_info.page_num == page:
                return page_info.text.strip()[:800]
        return parsed.text.strip()[:800]

    @staticmethod
    def _enrich_images_with_text(parsed: ParsedDocument) -> None:
        """识别图片内容并附加到对应页面文本，供常规分块和向量化使用。"""
        if not settings.VISION_PARSING_ENABLED:
            return
        page_texts: Dict[int, List[str]] = {}
        for index, image in enumerate(parsed.images, start=1):
            image_path = image.get("path")
            if not image_path:
                continue
            try:
                extracted_text = image_understanding_service.describe_image(image_path)
            except Exception as error:
                log.warning(f"Pipeline: 图片内容识别失败 {image_path}: {error}")
                continue
            if not extracted_text:
                continue
            image["extracted_text"] = extracted_text
            page = int(image.get("page", 1))
            page_texts.setdefault(page, []).append(f"[图片 {index} 识别内容]\n{extracted_text}")

        if not page_texts:
            return
        for page_info in parsed.pages:
            additions = page_texts.get(page_info.page_num)
            if additions:
                page_info.text = f"{page_info.text}\n\n" + "\n\n".join(additions)
        parsed.text = "\n\n".join(page.text for page in parsed.pages)


# ============================================================
# 单例
# ============================================================

document_pipeline = DocumentPipeline()

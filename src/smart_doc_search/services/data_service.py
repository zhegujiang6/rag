"""数据服务层 — 统一对外接口.

轻量数据中台 — 第四层：数据服务层（Data Service）

核心思想：RAG 引擎和前端不直接操作数据库和向量库，都通过此服务层调用.

职责：
  - 文件接入编排（Ingestor + Pipeline）
  - 文档 CRUD（含关联资源清理）
  - 知识库 CRUD（含向量集合管理）
  - 为 RAG 引擎提供内部查询方法
"""

import os
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from smart_doc_search.core.config import settings
from smart_doc_search.data.database import (
    SessionLocal, Document, KnowledgeBase, ParentChunk,
    DocKbRelation, Conversation, SubChunk,
)
from smart_doc_search.services.ingestion import FileIngestor, WebIngestor, RawDocument
from smart_doc_search.services.pipeline import document_pipeline, PipelineResult
from smart_doc_search.services.vector_store import vector_store
from loguru import logger as log


# ============================================================
# 默认用户
# ============================================================

DEFAULT_USER_ID = 1


# ============================================================
# 数据服务
# ============================================================

class DataService:
    """统一数据服务 — 前端和 RAG 引擎的唯一数据入口.

    双模式 DB session：
    - 长流程（ingest_file）自管 session
    - 短查询接受外部 session（与 tag_service 等模式一致）
    """

    # ── 文件接入（全流程编排）──────────────────────────────

    def ingest_file(
        self,
        uploaded_file: Any,
        kb_id: int = 0,
        user_id: int = DEFAULT_USER_ID,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> Document:
        """文件上传全流程：接入 → 创建记录 → 管道处理.

        Args:
            uploaded_file: Streamlit UploadedFile 对象.
            kb_id: 关联知识库 ID（0 表示不关联）.
            user_id: 用户 ID.
            progress_callback: 进度回调 (status, progress).

        Returns:
            创建并处理完成的 Document 对象.

        Raises:
            ValueError: 文件过大或格式不支持.
            Exception: 处理失败时向上抛出.
        """
        # ── 检查文件大小 ──
        file_size = getattr(uploaded_file, "size", 0)
        if file_size > settings.MAX_FILE_SIZE:
            raise ValueError(
                f"文件超过大小限制 ({settings.MAX_FILE_SIZE // 1024 // 1024}MB)"
            )

        # ── Step 1: 接入层 — 文件 → RawDocument ──
        ingestor = FileIngestor()
        raw_doc = ingestor.ingest(uploaded_file)

        # ── Step 2: 创建 Document 数据库记录 ──
        db = SessionLocal()
        try:
            storage_path = raw_doc.metadata.get("storage_path", "")
            storage_name = raw_doc.metadata.get("storage_name", "")
            file_ext = raw_doc.metadata.get("file_ext", "")

            doc = Document(
                user_id=user_id,
                knowledge_base_id=kb_id if kb_id > 0 else None,
                filename=storage_name,
                original_filename=raw_doc.source_identifier,
                file_type=file_ext,
                file_size=file_size,
                file_path=storage_path,
                source_type="file",
                source_url=None,
                status="uploading",
            )
            db.add(doc)
            db.commit()
            doc_id = doc.id

            # ── Step 3: 处理管道 ──
            result = document_pipeline.run(
                raw_doc=raw_doc,
                kb_id=kb_id,
                db=db,
                doc_id=doc_id,
                progress_callback=progress_callback,
            )

            if result.status == "failed":
                # 管道已标记失败状态，刷新并返回
                db.refresh(doc)
                return doc

            # ── Step 4: 建立知识库关联 ──
            if kb_id > 0:
                existing = db.query(DocKbRelation).filter(
                    DocKbRelation.document_id == doc_id,
                    DocKbRelation.knowledge_base_id == kb_id,
                ).first()
                if not existing:
                    db.add(DocKbRelation(
                        document_id=doc_id,
                        knowledge_base_id=kb_id,
                    ))
                    db.commit()

            db.refresh(doc)
            log.info(f"DataService: 文件接入完成 | doc_id={doc_id} | '{doc.original_filename}'")
            return doc

        except Exception:
            db.rollback()
            # 清理已保存的文件
            if 'storage_path' in locals() and storage_path and os.path.exists(storage_path):
                try:
                    os.remove(storage_path)
                except Exception:
                    pass
            raise
        finally:
            db.close()

    # ── 网页接入（全流程编排）──────────────────────────────

    def ingest_url(
        self,
        url: str,
        kb_id: int = 0,
        user_id: int = DEFAULT_USER_ID,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> Dict[str, Any]:
        """网页导入全流程：爬取 → 创建记录 → 管道处理.

        Args:
            url: 要导入的网页 URL.
            kb_id: 关联知识库 ID（0 表示不关联）.
            user_id: 用户 ID.
            progress_callback: 进度回调 (status, progress).

        Returns:
            {"status": "ok"|"duplicate"|"error", "doc": Document|None, "error": str|None}
        """
        # ── URL 去重 ──
        db = SessionLocal()
        try:
            existing = db.query(Document).filter(
                Document.source_url == url,
                Document.user_id == user_id,
            ).first()
            if existing:
                log.info(f"DataService: URL 已存在，跳过 '{url}'")
                return {"status": "duplicate", "doc": existing, "error": None}
        finally:
            db.close()

        self._report(progress_callback, "crawling", 0.05)

        try:
            # ── Step 1: 接入层 — URL → RawDocument ──
            ingestor = WebIngestor()
            raw_doc = ingestor.ingest(url)

            self._report(progress_callback, "parsing", 0.2)

            # ── Step 2: 创建 Document 数据库记录 ──
            db = SessionLocal()
            try:
                title = raw_doc.metadata.get("title", "") or url
                # 用 URL 后段或标题作为显示名
                display_name = title if title else url.split("/")[-1] or url

                doc = Document(
                    user_id=user_id,
                    knowledge_base_id=kb_id if kb_id > 0 else None,
                    filename=url,                       # 网页文档无本地文件，用 URL 作为标识
                    original_filename=display_name,     # 列表页显示名
                    file_type="web",
                    file_size=len(raw_doc.content.encode("utf-8")),
                    file_path=None,                     # 网页文档无本地文件
                    source_type="web",
                    source_url=url,
                    status="uploading",
                )
                db.add(doc)
                db.commit()
                doc_id = doc.id

                # ── Step 3: 处理管道 ──
                result = document_pipeline.run(
                    raw_doc=raw_doc,
                    kb_id=kb_id,
                    db=db,
                    doc_id=doc_id,
                    progress_callback=progress_callback,
                )

                if result.status == "failed":
                    db.refresh(doc)
                    return {"status": "error", "doc": doc, "error": result.error_message}

                # ── Step 4: 建立知识库关联 ──
                if kb_id > 0:
                    existing_rel = db.query(DocKbRelation).filter(
                        DocKbRelation.document_id == doc_id,
                        DocKbRelation.knowledge_base_id == kb_id,
                    ).first()
                    if not existing_rel:
                        db.add(DocKbRelation(
                            document_id=doc_id,
                            knowledge_base_id=kb_id,
                        ))
                        db.commit()

                db.refresh(doc)
                log.info(
                    f"DataService: 网页导入完成 | doc_id={doc_id} | "
                    f"'{display_name}' | {result.chunk_count} 分块"
                )
                return {"status": "ok", "doc": doc, "error": None}

            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        except Exception as e:
            log.error(f"DataService: 网页导入失败 '{url}' - {e}")
            return {"status": "error", "doc": None, "error": str(e)}

    # ── 文档 CRUD ──────────────────────────────────────────

    def list_documents(
        self,
        user_id: int = DEFAULT_USER_ID,
        kb_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        db: Optional[Session] = None,
    ) -> List[Document]:
        """查询文档列表，支持按知识库和标签筛选.

        Args:
            user_id: 用户 ID.
            kb_id: 可选，按知识库筛选.
            tags: 可选，按标签筛选（需全部匹配）.
            db: 数据库会话.

        Returns:
            文档列表（按创建时间倒序）.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            query = db.query(Document).filter(Document.user_id == user_id)

            if kb_id:
                # 通过关联表筛选
                doc_ids = [
                    r.document_id for r in
                    db.query(DocKbRelation).filter(
                        DocKbRelation.knowledge_base_id == kb_id
                    ).all()
                ]
                if doc_ids:
                    query = query.filter(Document.id.in_(doc_ids))
                else:
                    return []

            docs = query.order_by(Document.created_at.desc()).all()

            # 标签筛选（内存过滤，因为 tags 是 JSON 字段）
            if tags:
                from smart_doc_search.services.tag_service import tag_service
                filtered_ids = set(tag_service.filter_by_tags(
                    tags, user_id=user_id, db=db
                ))
                docs = [d for d in docs if d.id in filtered_ids]

            return docs

        finally:
            if should_close:
                db.close()

    def get_document(self, doc_id: int, db: Optional[Session] = None) -> Optional[Document]:
        """按 ID 获取文档."""
        should_close = db is None
        if db is None:
            db = SessionLocal()
        try:
            return db.query(Document).filter(Document.id == doc_id).first()
        finally:
            if should_close:
                db.close()

    def delete_document(self, doc_id: int, db: Optional[Session] = None) -> bool:
        """删除文档及其关联资源（文件、向量、DB 记录）.

        Args:
            doc_id: 文档 ID.
            db: 数据库会话.

        Returns:
            是否成功删除.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                return False

            # 1. 清理 ChromaDB 向量
            if doc.knowledge_base_id:
                try:
                    vector_store.delete_by_document_id(doc.knowledge_base_id, doc.id)
                except Exception as e:
                    log.warning(f"清理向量数据失败: {e}")

            # 2. 清理关联的知识库中该文档的向量
            relations = db.query(DocKbRelation).filter(
                DocKbRelation.document_id == doc_id
            ).all()
            for rel in relations:
                try:
                    vector_store.delete_by_document_id(rel.knowledge_base_id, doc_id)
                except Exception:
                    pass

            # 3. 删除关联关系
            db.query(DocKbRelation).filter(
                DocKbRelation.document_id == doc_id
            ).delete()

            # 4. 删除物理文件
            if doc.file_path and os.path.exists(doc.file_path):
                try:
                    os.remove(doc.file_path)
                except Exception as e:
                    log.warning(f"删除文件失败: {e}")

            # 5. 删除 DB 记录（级联删除 parent_chunks, sub_chunks）
            db.delete(doc)
            db.commit()

            log.info(f"DataService: 文档已删除 doc_id={doc_id} | '{doc.original_filename}'")
            return True

        except Exception as e:
            log.error(f"DataService: 删除文档失败 doc_id={doc_id} - {e}")
            if should_close:
                db.rollback()
            return False
        finally:
            if should_close:
                db.close()

    # ── 知识库 CRUD ────────────────────────────────────────

    def create_kb(
        self, name: str, description: str = "",
        user_id: int = DEFAULT_USER_ID, db: Optional[Session] = None,
    ) -> Optional[KnowledgeBase]:
        """创建知识库."""
        should_close = db is None
        if db is None:
            db = SessionLocal()
        try:
            kb = KnowledgeBase(
                user_id=user_id,
                name=name.strip(),
                description=description.strip() if description else None,
            )
            db.add(kb)
            db.commit()
            log.info(f"DataService: 知识库已创建 '{name}'")
            return kb
        except Exception as e:
            log.error(f"DataService: 创建知识库失败 - {e}")
            if should_close:
                db.rollback()
            return None
        finally:
            if should_close:
                db.close()

    def delete_kb(self, kb_id: int, db: Optional[Session] = None) -> bool:
        """删除知识库及其关联资源.

        执行步骤：
        1. 解除关联的对话
        2. 解除关联的文档
        3. 删除 ChromaDB 向量集合
        4. 删除关联关系记录
        5. 删除知识库记录
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()
        try:
            kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
            if not kb:
                return False

            # 1. 解除关联对话
            db.query(Conversation).filter(
                Conversation.knowledge_base_id == kb_id
            ).update({Conversation.knowledge_base_id: None})

            # 2. 解除关联文档
            db.query(Document).filter(
                Document.knowledge_base_id == kb_id
            ).update({Document.knowledge_base_id: None})

            # 3. 删除 ChromaDB 集合
            try:
                vector_store.delete_collection(kb_id)
            except Exception as e:
                log.warning(f"删除向量集合失败: {e}")

            # 4. 删除关联关系
            db.query(DocKbRelation).filter(
                DocKbRelation.knowledge_base_id == kb_id
            ).delete()

            # 5. 删除知识库
            db.delete(kb)
            db.commit()

            log.info(f"DataService: 知识库已删除 kb_id={kb_id} | '{kb.name}'")
            return True

        except Exception as e:
            log.error(f"DataService: 删除知识库失败 kb_id={kb_id} - {e}")
            if should_close:
                db.rollback()
            return False
        finally:
            if should_close:
                db.close()

    def list_kbs(
        self, user_id: int = DEFAULT_USER_ID, db: Optional[Session] = None,
    ) -> List[KnowledgeBase]:
        """获取知识库列表."""
        should_close = db is None
        if db is None:
            db = SessionLocal()
        try:
            return db.query(KnowledgeBase).filter(
                KnowledgeBase.user_id == user_id
            ).order_by(KnowledgeBase.created_at.desc()).all()
        finally:
            if should_close:
                db.close()

    # ── 文档-知识库关联 ───────────────────────────────────

    def add_doc_to_kb(
        self, doc_id: int, kb_id: int, db: Optional[Session] = None,
    ) -> bool:
        """将文档关联到知识库，同时将向量写入目标知识库的 ChromaDB 集合."""
        should_close = db is None
        if db is None:
            db = SessionLocal()
        try:
            existing = db.query(DocKbRelation).filter(
                DocKbRelation.document_id == doc_id,
                DocKbRelation.knowledge_base_id == kb_id,
            ).first()
            if not existing:
                db.add(DocKbRelation(document_id=doc_id, knowledge_base_id=kb_id))
                db.commit()
                log.info(f"DataService: 文档 doc_id={doc_id} 已关联到 kb_id={kb_id}")

                # 将文档向量写入目标知识库的 ChromaDB 集合
                self._index_doc_vectors(doc_id, kb_id, db)
                # 重建 BM25 索引
                self._rebuild_bm25(kb_id, db)
            return True
        except Exception as e:
            log.error(f"DataService: 关联文档失败 - {e}")
            return False
        finally:
            if should_close:
                db.close()

    def _index_doc_vectors(self, doc_id: int, kb_id: int, db: Session) -> None:
        """将文档的子块重新嵌入并写入目标知识库的 ChromaDB 集合.

        仅在文档已有 SubChunk 记录且目标集合中尚无该文档向量时执行.
        """
        from smart_doc_search.services.embedding_service import embedding_service as emb_svc

        # 检查是否已存在（防止重复添加）
        try:
            collection = vector_store.get_or_create_collection(kb_id)
            existing = collection.get(
                where={"document_id": doc_id},
                limit=1,
            )
            if existing["ids"]:
                log.info(
                    f"DataService: 文档 doc_id={doc_id} 在 kb_{kb_id} 中已有向量，跳过"
                )
                return
        except Exception:
            pass  # 集合为空或查询失败，继续添加

        # 查询该文档的全部子块
        sub_chunks = db.query(SubChunk).filter(
            SubChunk.document_id == doc_id
        ).order_by(SubChunk.chunk_index).all()

        if not sub_chunks:
            log.warning(f"DataService: 文档 doc_id={doc_id} 没有子块，无法索引向量")
            return

        # 构建 ChromaDB 数据并生成嵌入
        chroma_chunks = []
        texts = []
        for sc in sub_chunks:
            chroma_chunks.append({
                "chroma_id": sc.chroma_id or f"chunk_{sc.document_id}_{sc.chunk_index}",
                "document_id": sc.document_id,
                "parent_chunk_id": sc.parent_chunk_id,
                "chunk_index": sc.chunk_index,
                "content": sc.content,
                "metadata": sc.chunk_metadata or {},
            })
            texts.append(sc.content)

        try:
            embeddings = emb_svc.embed_batch(texts)
            vector_store.add_chunks(kb_id, chroma_chunks, embeddings)
            log.info(
                f"DataService: 已将 {len(chroma_chunks)} 个向量写入 kb_{kb_id} "
                f"(doc_id={doc_id})"
            )
        except Exception as e:
            log.error(f"DataService: 写入向量失败 doc_id={doc_id} kb_id={kb_id} - {e}")
            raise

    def remove_doc_from_kb(
        self, doc_id: int, kb_id: int, db: Optional[Session] = None,
    ) -> bool:
        """解除文档与知识库的关联，同时清理 ChromaDB 中的向量."""
        should_close = db is None
        if db is None:
            db = SessionLocal()
        try:
            db.query(DocKbRelation).filter(
                DocKbRelation.document_id == doc_id,
                DocKbRelation.knowledge_base_id == kb_id,
            ).delete()

            # 清理 ChromaDB 中该文档在此知识库的向量
            try:
                vector_store.delete_by_document_id(kb_id, doc_id)
            except Exception as e:
                log.warning(f"清理向量失败: {e}")

            db.commit()
            # 重建 BM25 索引
            self._rebuild_bm25(kb_id, db)
            log.info(f"DataService: 文档 doc_id={doc_id} 已从 kb_id={kb_id} 移除")
            return True
        except Exception as e:
            log.error(f"DataService: 移除文档关联失败 - {e}")
            return False
        finally:
            if should_close:
                db.close()

    def get_kb_chunk_count(self, kb_id: int) -> int:
        """获取知识库的向量块数量."""
        return vector_store.get_collection_count(kb_id)

    # ── RAG 引擎内部查询 ──────────────────────────────────

    def get_parent_chunks_by_ids(
        self, ids: List[int], db: Optional[Session] = None,
    ) -> List[ParentChunk]:
        """按 ID 列表查询父块（供 RAG 引擎使用）.

        Args:
            ids: 父块 ID 列表.
            db: 数据库会话.

        Returns:
            按 chunk_index 排序的父块列表.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()
        try:
            if not ids:
                return []
            return db.query(ParentChunk).filter(
                ParentChunk.id.in_(list(ids))
            ).order_by(ParentChunk.chunk_index).all()
        finally:
            if should_close:
                db.close()

    def get_documents_by_ids(
        self, ids: List[int], db: Optional[Session] = None,
    ) -> Dict[int, Document]:
        """按 ID 列表查询文档（供 RAG 引擎使用）.

        Args:
            ids: 文档 ID 列表.
            db: 数据库会话.

        Returns:
            {doc_id: Document} 字典.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()
        try:
            if not ids:
                return {}
            docs = db.query(Document).filter(
                Document.id.in_(list(ids))
            ).all()
            return {d.id: d for d in docs}
        finally:
            if should_close:
                db.close()

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    def _report(callback: Optional[Callable], status: str, progress: float):
        """安全调用进度回调."""
        if callback:
            try:
                callback(status, progress)
            except Exception:
                pass

    @staticmethod
    def _rebuild_bm25(kb_id: int, db: Session) -> None:
        """Rebuild BM25 index for a knowledge base (non-fatal wrapper)."""
        from smart_doc_search.core.config import settings
        if not settings.HYBRID_SEARCH_ENABLED:
            return
        try:
            from smart_doc_search.services.hybrid_search import hybrid_search
            hybrid_search.rebuild_for_kb(kb_id, db)
        except Exception as e:
            log.warning(f"DataService: BM25 index rebuild failed (non-fatal): {e}")


# ============================================================
# 单例
# ============================================================

data_service = DataService()

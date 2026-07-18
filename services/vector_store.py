"""向量存储 — 基于 ChromaDB 的语义搜索存储服务"""
import os
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings as ChromaSettings
from config import settings
from loguru import logger as log


# ============================================================
# 向量存储核心类
# ============================================================
class VectorStore:
    """向量存储核心类，基于 ChromaDB，支持按知识库隔离的集合管理"""

    COLLECTION_PREFIX = "kb_"  # 知识库集合前缀（用于区分不同知识库的向量数据）
    MULTIMODAL_COLLECTION_PREFIX = "kb_mm_"

    def __init__(self, persist_dir: str = None):
        """初始化 ChromaDB 客户端，创建持久化存储目录"""
        # 持久化目录：优先使用传入值，否则从配置读取
        self.persist_dir = persist_dir or settings.CHROMA_PERSIST_DIR
        # 确保目录存在
        os.makedirs(self.persist_dir, exist_ok=True)

        # 创建持久化客户端（数据存储在本地文件系统，重启后数据不丢失）
        if settings.CHROMA_HOST:
            self._client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                ssl=settings.CHROMA_SSL,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            log.info(f"ChromaDB 初始化完成，远程服务: {settings.CHROMA_HOST}:{settings.CHROMA_PORT}")
        else:
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
            log.info(f"ChromaDB 初始化完成，本地目录: {self.persist_dir}")

    @property
    def client(self) -> chromadb.PersistentClient:
        """获取 ChromaDB 客户端实例（只读属性）"""
        return self._client

    # ============================================================
# 集合管理工具
# ============================================================
    def _get_collection_name(self, knowledge_base_id: int) -> str:
        """根据知识库 ID 生成集合名称（格式：kb_{knowledge_base_id}）"""
        return f"{self.COLLECTION_PREFIX}{knowledge_base_id}"

    def get_or_create_collection(self, knowledge_base_id: int) -> chromadb.Collection:
        """获取或创建知识库对应的向量集合（不存在则自动创建）"""
        name = self._get_collection_name(knowledge_base_id)
        try:
            return self._client.get_or_create_collection(
                name=name,
                metadata={
                    "kb_id": knowledge_base_id,        # 记录知识库 ID
                    "hnsw:space": "cosine",           # 使用余弦相似度（适用于语义搜索）
                },
            )
        except Exception as e:
            log.error(f"获取/创建集合 '{name}' 失败: {e}")
            raise

    # ============================================================
# 添加向量数据
# ============================================================
    def get_or_create_multimodal_collection(self, knowledge_base_id: int) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=f"{self.MULTIMODAL_COLLECTION_PREFIX}{knowledge_base_id}",
            metadata={"kb_id": knowledge_base_id, "index_type": "multimodal", "hnsw:space": "cosine"},
        )

    def add_multimodal_chunk(self, knowledge_base_id: int, chunk_id: str, description: str, embedding: List[float], metadata: Dict[str, Any]) -> None:
        self.get_or_create_multimodal_collection(knowledge_base_id).upsert(
            ids=[chunk_id], documents=[description], embeddings=[embedding], metadatas=[metadata]
        )

    def search_multimodal(self, knowledge_base_id: int, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        collection = self.get_or_create_multimodal_collection(knowledge_base_id)
        if collection.count() == 0:
            return []
        result = collection.query(query_embeddings=[query_embedding], n_results=min(top_k, collection.count()), include=["documents", "metadatas", "distances"])
        return [{"id": result["ids"][0][i], "content": result["documents"][0][i], "metadata": result["metadatas"][0][i], "score": round(1 - result["distances"][0][i] / 2, 4)} for i in range(len(result["ids"][0]))]

    def add_chunks(
        self, knowledge_base_id: int, chunks: List[Dict[str, Any]], embeddings: List[List[float]]
    ) -> List[str]:
        """将子块和对应的向量批量添加到知识库集合"""
        collection = self.get_or_create_collection(knowledge_base_id)

        # 准备批量插入的数据
        ids, documents, metadatas, embeds = [], [], [], []

        # 遍历每个子块，构建插入数据
        for chunk, embedding in zip(chunks, embeddings):
            # 生成唯一 ID：优先使用 chroma_id，否则格式为 chunk_{document_id}_{chunk_index}
            chroma_id = chunk.get("chroma_id", f"chunk_{chunk['document_id']}_{chunk['chunk_index']}")
            ids.append(chroma_id)
            documents.append(chunk["content"])  # 子块文本内容
            metadatas.append({
                "document_id": chunk["document_id"],       # 所属文档 ID
                "parent_chunk_id": chunk.get("parent_chunk_id", 0),  # 父块 ID（用于关联）
                "chunk_index": chunk["chunk_index"],       # 块索引
                "page": chunk.get("metadata", {}).get("page") or "",  # 页码
                "type": chunk.get("metadata", {}).get("type", ""),    # 块类型（paragraph/code_block/table）
            })
            embeds.append(embedding)  # 向量数据

        try:
            # 批量添加到 ChromaDB
            collection.add(ids=ids, documents=documents, embeddings=embeds, metadatas=metadatas)
            log.info(f"成功添加 {len(ids)} 个子块到集合 '{self._get_collection_name(knowledge_base_id)}'")
            return ids
        except Exception as e:
            log.error(f"添加子块到 ChromaDB 失败: {e}")
            raise

    # ============================================================
# 向量检索（语义搜索）
# ============================================================
    def search(
        self, knowledge_base_id: int, query_embedding: List[float],
        top_k: int = None, similarity_threshold: float = None,
    ) -> List[Dict[str, Any]]:
        """在知识库中进行语义搜索，返回匹配的子块（按相似度排序）"""
        # 使用传入参数或配置默认值
        top_k = top_k or settings.RETRIEVAL_TOP_K
        similarity_threshold = similarity_threshold or settings.SIMILARITY_THRESHOLD

        collection = self.get_or_create_collection(knowledge_base_id)

        # 图片型文档可能只有多模态索引，没有文字子块；此时跳过空集合查询。
        if collection.count() == 0:
            return []

        try:
            # 查询向量数据库（返回 top_k 个最相似的结果）
            results = collection.query(
                query_embeddings=[query_embedding],  # 查询向量（单个）
                n_results=top_k,                      # 返回数量
                include=["documents", "metadatas", "distances"],  # 包含文本、元数据、距离
            )

            # 格式化结果（过滤相似度低于阈值的）
            formatted = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    # 获取余弦距离（ChromaDB 范围是 0-2，0 表示完全匹配）
                    distance = results["distances"][0][i] if results["distances"] else 0
                    # 转换为相似度：1.0 = 完全匹配，0 = 完全不匹配
                    similarity = 1.0 - (distance / 2.0)

                    # 过滤相似度低于阈值的结果
                    if similarity >= similarity_threshold:
                        formatted.append({
                            "id": doc_id,                                    # 子块 ID
                            "content": results["documents"][0][i] if results["documents"] else "",  # 文本内容
                            "metadata": results["metadatas"][0][i] if results["metadatas"] else {},  # 元数据
                            "score": round(similarity, 4),                   # 相似度分数（保留4位小数）
                        })

            log.info(f"在 kb_{knowledge_base_id} 中检索: 找到 {len(formatted)} 个超过阈值 {similarity_threshold} 的结果")
            return formatted

        except Exception as e:
            log.error(f"向量检索失败: {e}")
            raise

    # ============================================================
# 删除操作
# ============================================================
    def delete_by_document_id(self, knowledge_base_id: int, document_id: int):
        """删除指定文档的所有向量数据（当文档被删除时调用）"""
        collection = self.get_or_create_collection(knowledge_base_id)
        try:
            # 获取集合中所有数据，按 document_id 过滤
            existing = collection.get()
            if existing["ids"]:
                ids_to_delete = []
                for i, meta in enumerate(existing["metadatas"]):
                    if meta and meta.get("document_id") == document_id:
                        ids_to_delete.append(existing["ids"][i])
                if ids_to_delete:
                    collection.delete(ids=ids_to_delete)
                    log.info(f"从 kb_{knowledge_base_id} 中删除了 {len(ids_to_delete)} 个子块（文档 {document_id}）")
            multimodal = self.get_or_create_multimodal_collection(knowledge_base_id)
            multimodal_existing = multimodal.get()
            multimodal_ids = [
                multimodal_existing["ids"][i]
                for i, meta in enumerate(multimodal_existing["metadatas"])
                if meta and meta.get("document_id") == document_id
            ]
            if multimodal_ids:
                multimodal.delete(ids=multimodal_ids)
        except Exception as e:
            log.error(f"删除文档 {document_id} 的子块失败: {e}")
            raise

    def delete_collection(self, knowledge_base_id: int):
        """删除整个知识库集合（当知识库被删除时调用）"""
        name = self._get_collection_name(knowledge_base_id)
        try:
            self._client.delete_collection(name)
            try:
                self._client.delete_collection(f"{self.MULTIMODAL_COLLECTION_PREFIX}{knowledge_base_id}")
            except Exception:
                pass
            log.info(f"删除集合: {name}")
        except Exception as e:
            # 集合不存在时不报错（可能已被删除）
            log.warning(f"删除集合 '{name}' 失败: {e}")

    # ============================================================
    # 统计查询
    # ============================================================
    def get_collection_count(self, knowledge_base_id: int) -> int:
        """获取知识库集合中的向量数量（子块总数）"""
        try:
            collection = self.get_or_create_collection(knowledge_base_id)
            return collection.count()
        except Exception:
            # 集合不存在时返回 0
            return 0


# ============================================================
# 单例实例
# ============================================================
# 创建全局单例，其他模块直接导入使用，避免重复创建客户端
vector_store = VectorStore()

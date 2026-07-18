"""应用配置管理。"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# 默认从启动目录读取 .env，也可通过 DOC_SEARCH_ENV_FILE 显式指定。
_ENV_FILE = Path(os.getenv("DOC_SEARCH_ENV_FILE", Path.cwd() / ".env"))


# ============================================================
# 配置类（从 .env 文件加载环境变量）
# ============================================================
class Settings(BaseSettings):
    """应用配置，从环境变量和 .env 文件加载"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),           # 指定 .env 文件路径
        env_file_encoding="utf-8",         # 支持中文配置
        extra="ignore",                    # 忽略未定义的环境变量
    )

    # ============================================================
    # 应用基础配置
    # ============================================================
    APP_NAME: str = "智能文档检索助手"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # ============================================================
    # 数据库配置
    # ============================================================
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "password"
    DB_NAME: str = "doc_search"
    DATABASE_URL: Optional[str] = None

    @property
    def database_url(self) -> str:
        """生成同步 SQLAlchemy 数据库 URL，并修复异步/默认驱动名称。"""
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            for driver in ("mysql+asyncmy", "mysql+aiomysql"):
                if driver in url:
                    url = url.replace(driver, "mysql+pymysql")
                    break
            if url.startswith("mysql://"):
                url = url.replace("mysql://", "mysql+pymysql://", 1)
            return url
        # 从独立配置项构建连接 URL
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ============================================================
    # LLM 配置（大语言模型）
    # ============================================================
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-3.5-turbo"
    LLM_TEMPERATURE: float = 0.7        # 温度（0=确定性，1=随机性）
    LLM_MAX_TOKENS: int = 2048          # 最大生成 token 数

    # ============================================================
    # Embedding 配置（文本向量）
    # ============================================================
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_API_BASE: str = "https://api.openai.com/v1"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536     # 向量维度

    MULTIMODAL_EMBEDDING_ENABLED: bool = False
    MULTIMODAL_EMBEDDING_API_KEY: str = ""
    MULTIMODAL_EMBEDDING_MODEL: str = "qwen3-vl-embedding"
    MULTIMODAL_EMBEDDING_DIMENSION: int = 1024

    # 图片内容转写：将图片中的文字、表格和图表说明写入普通文本索引。
    VISION_PARSING_ENABLED: bool = True
    VISION_API_KEY: str = ""
    VISION_API_BASE: str = ""
    VISION_MODEL: str = "qwen3.5-omni-plus-2026-03-15"
    VISION_MAX_TOKENS: int = 1500

    # RAG 服务并发保护。问答槽位限制的是长连接/SSE 总数，
    # 上游槽位限制的是对模型供应商的瞬时并发，避免 429 级联。
    RAG_MAX_CONCURRENT_REQUESTS: int = 20
    RAG_CONCURRENCY_QUEUE_TIMEOUT_SECONDS: float = 2.0
    LLM_MAX_CONCURRENCY: int = 8
    EMBEDDING_MAX_CONCURRENCY: int = 16
    UPSTREAM_QUEUE_TIMEOUT_SECONDS: float = 15.0

    # ============================================================
    # ChromaDB 向量数据库配置
    # ============================================================
    CHROMA_PERSIST_DIR: str = "./data/chroma"  # 持久化存储目录
    # 生产多副本使用独立 Chroma HTTP 服务；未配置时保留本地开发模式。
    CHROMA_HOST: str = ""
    CHROMA_PORT: int = 8000
    CHROMA_SSL: bool = False

    # ============================================================
    # 文件存储配置
    # ============================================================
    UPLOAD_DIR: str = "./data/uploads"  # 上传文件存储目录
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 最大文件大小（50MB）

    # ============================================================
    # 文档分割配置
    # ============================================================
    SUB_CHUNK_SIZE: int = 256           # 子块大小（tokens）
    PARENT_CHUNK_SIZE: int = 1024       # 父块大小（tokens）
    CHUNK_OVERLAP: int = 50             # 块之间的重叠大小（tokens）
    SUB_CHUNKS_PER_PARENT: int = 4      # 每个父块包含的子块数
    SEMANTIC_CHUNKING_ENABLED: bool = False  # 是否启用 LLM 语义切分

    # ============================================================
    # 检索配置
    # ============================================================
    RETRIEVAL_TOP_K: int = 5            # 检索返回的结果数量
    SIMILARITY_THRESHOLD: float = 0.5   # 相似度阈值（低于此值的结果过滤）

    # ============================================================
    # RAGAS 优化：混合搜索（BM25 + 语义检索）
    # ============================================================
    HYBRID_SEARCH_ENABLED: bool = False
    HYBRID_WEIGHT_BM25: float = 0.3     # BM25 权重
    HYBRID_WEIGHT_SEMANTIC: float = 0.7 # 语义检索权重

    # ============================================================
    # RAGAS 优化：重排序
    # ============================================================
    RERANK_ENABLED: bool = False
    RERANK_BACKEND: str = "cross_attention_llm"  # 重排序后端类型
    RERANK_MODEL_NAME: str = "BAAI/bge-reranker-v2-m3"
    RETRIEVAL_MULTIPLIER: int = 3       # 重排序前先获取 top_k * N 个结果

    # ============================================================
    # RAGAS 优化：查询重写
    # ============================================================
    QUERY_REWRITE_ENABLED: bool = False
    QUERY_REWRITE_STRATEGY: str = "multi_query"  # 重写策略
    QUERY_EXPANSION_COUNT: int = 3      # 查询扩展数量

    # ============================================================
    # RAGAS 优化：上下文压缩
    # ============================================================
    CONTEXT_COMPRESSION_ENABLED: bool = False
    CONTEXT_SENTENCE_THRESHOLD: float = 0.3  # 句子相关性阈值

    # ============================================================
    # RAGAS 评测配置
    # ============================================================
    EVALUATION_ENABLED: bool = False
    EVALUATION_LLM_MODEL: str = ""      # 评测专用模型（空则使用 LLM_MODEL）


# ============================================================
# 配置实例（全局单例）
# ============================================================
settings = Settings()

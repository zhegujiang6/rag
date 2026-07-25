"""SQLAlchemy 同步引擎、会话工厂和 ORM 模型"""
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Text, JSON,
    TIMESTAMP, ForeignKey, Enum as SQLEnum, UniqueConstraint, Boolean, Float,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import DeclarativeBase, sessionmaker, scoped_session, Session
from loguru import logger as log

from smart_doc_search.core.config import settings

# ============================================================
# 数据库引擎与会话工厂
# ============================================================

# 创建数据库引擎（同步模式）
engine = create_engine(
    settings.database_url,
    echo=settings.DEBUG,          # DEBUG 模式下打印 SQL
    pool_size=5,                  # 连接池大小
    max_overflow=10,              # 连接池最大溢出数
    pool_recycle=3600,            # 连接回收时间（秒）
    pool_pre_ping=True,           # 使用前验证连接有效性
)

# 创建线程安全的会话工厂（使用 scoped_session）
SessionLocal = scoped_session(
    sessionmaker(bind=engine, expire_on_commit=False)
)


@contextmanager
def get_db():
    """提供一个会在退出上下文时自动关闭的数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


# ============================================================
# ORM 模型定义
# ============================================================

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class KnowledgeBase(Base):
    """知识库表"""
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    def __repr__(self):
        return f"<KnowledgeBase(id={self.id}, name='{self.name}')>"


class Document(Base):
    """文档表（上传的文件元数据）"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=True)
    filename = Column(String(500), nullable=False)         # 存储文件名（UUID）
    original_filename = Column(String(500), nullable=False) # 原始文件名
    file_type = Column(String(20), nullable=False)        # 文件类型（pdf, docx, txt 等）
    file_size = Column(BigInteger, nullable=True)         # 文件大小（字节）
    file_path = Column(String(1000), nullable=True)       # 文件存储路径
    source_type = Column(String(20), nullable=False, default="file")
    source_url = Column(String(2000), nullable=True)
    status = Column(
        SQLEnum("uploading", "parsing", "chunking", "embedding", "completed", "failed",
                name="document_status"),
        default="uploading",
        nullable=False,
    )
    error_message = Column(Text, nullable=True)           # 错误信息
    chunk_count = Column(Integer, default=0)              # 分割后的块数量
    tags = Column(JSON, nullable=True)                    # 用户自定义标签 + 自动提取关键词
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.original_filename}')>"


class ParentChunk(Base):
    """父块表（用于 LLM 上下文，较大的文本块）"""
    __tablename__ = "parent_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)          # 块索引
    content = Column(Text, nullable=False)                # 块内容
    token_count = Column(Integer, default=0)              # token 数量
    chunk_metadata = Column(JSON, nullable=True)          # 块元数据
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    def __repr__(self):
        return f"<ParentChunk(id={self.id}, doc_id={self.document_id}, idx={self.chunk_index})>"


class SubChunk(Base):
    """子块表（用于向量检索，较小的文本块）"""
    __tablename__ = "sub_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_chunk_id = Column(Integer, ForeignKey("parent_chunks.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)         # 块索引
    content = Column(Text, nullable=False)               # 块内容
    token_count = Column(Integer, default=0)             # token 数量
    chroma_id = Column(String(255), nullable=True)       # ChromaDB 中的 ID
    chunk_metadata = Column(JSON, nullable=True)         # 块元数据
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    def __repr__(self):
        return f"<SubChunk(id={self.id}, parent_id={self.parent_chunk_id}, idx={self.chunk_index})>"


class DocKbRelation(Base):
    """文档-知识库关联表（多对多关系）"""
    __tablename__ = "doc_kb_relation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (
        UniqueConstraint("document_id", "knowledge_base_id", name="unique_doc_kb"),
    )

    def __repr__(self):
        return f"<DocKbRelation(doc_id={self.document_id}, kb_id={self.knowledge_base_id})>"


class Conversation(Base):
    """对话会话表"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=True)
    title = Column(String(500), nullable=True)
    mode = Column(
        SQLEnum("rag", "chat", name="conversation_mode"),
        default="chat",
        nullable=False,
    )
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    def __repr__(self):
        return f"<Conversation(id={self.id}, title='{self.title}')>"


class Message(Base):
    """对话消息表"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(
        SQLEnum("user", "assistant", "system", name="message_role"),
        nullable=False,
    )
    content = Column(Text, nullable=False)               # 消息内容
    sources = Column(JSON, nullable=True)               # 来源文档信息
    retrieval_details = Column(JSON, nullable=True)     # 检索详情（RAG 优化用）
    token_count = Column(Integer, default=0)            # token 数量
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    def __repr__(self):
        return f"<Message(id={self.id}, conv_id={self.conversation_id}, role='{self.role}')>"


# ============================================================
# RAGAS 评测模型
# ============================================================

class EvaluationRun(Base):
    """RAGAS 评测记录表（记录一次评测运行）"""
    __tablename__ = "evaluation_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    config_snapshot = Column(JSON, nullable=True)        # 评测配置快照
    test_case_count = Column(Integer, default=0)         # 测试用例数量
    avg_context_precision = Column(Float, default=0.0)   # 平均上下文精度
    avg_context_recall = Column(Float, default=0.0)      # 平均上下文召回率
    avg_faithfulness = Column(Float, default=0.0)        # 平均忠实度
    avg_answer_relevancy = Column(Float, default=0.0)    # 平均答案相关性
    avg_context_entity_recall = Column(Float, default=0.0) # 平均上下文实体召回率
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    def __repr__(self):
        return f"<EvaluationRun(id={self.id}, kb_id={self.knowledge_base_id})>"


class EvaluationResult(Base):
    """评测结果详情表（每个测试用例的结果）"""
    __tablename__ = "evaluation_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False)
    question = Column(Text, nullable=False)              # 测试问题
    ground_truth_answer = Column(Text, nullable=True)    # 标准答案
    generated_answer = Column(Text, nullable=True)       # 生成的答案
    retrieved_context = Column(Text, nullable=True)      # 检索到的上下文
    context_precision = Column(Float, default=0.0)       # 上下文精度
    context_recall = Column(Float, default=0.0)          # 上下文召回率
    faithfulness = Column(Float, default=0.0)            # 忠实度
    answer_relevancy = Column(Float, default=0.0)        # 答案相关性
    context_entity_recall = Column(Float, default=0.0)   # 上下文实体召回率
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    def __repr__(self):
        return f"<EvaluationResult(id={self.id}, run_id={self.run_id})>"


class Feedback(Base):
    """用户反馈表（对生成答案的评价）"""
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, default=0)                  # -1（负面）, 0（中性）, 1（正面）
    feedback_type = Column(String(50), default="")       # thumbs_up, thumbs_down, regenerate, copy
    comment = Column(Text, nullable=True)                # 用户评论
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    def __repr__(self):
        return f"<Feedback(id={self.id}, msg_id={self.message_id}, rating={self.rating})>"


# ============================================================
# 数据库初始化与迁移
# ============================================================

def _migrate_db():
    """数据库迁移：添加 ORM 模型中存在但 MySQL 表中不存在的列
    
    SQLAlchemy 的 create_all 只会创建新表，不会修改已存在的表。
    此辅助函数用于自动应用模型变更（如新增列），无需手动执行 ALTER TABLE。
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)

    # 添加 messages.retrieval_details 列
    existing_cols = {c["name"] for c in insp.get_columns("messages")}
    if "retrieval_details" not in existing_cols:
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE messages ADD COLUMN retrieval_details JSON NULL"
                ))
                conn.commit()
            log.info("迁移: messages.retrieval_details 列已添加")
        except Exception as e:
            log.warning(f"迁移 messages.retrieval_details 失败 (可能已存在): {e}")

    # 添加 documents.tags 列
    doc_cols = {c["name"] for c in insp.get_columns("documents")}
    if "tags" not in doc_cols:
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE documents ADD COLUMN tags JSON NULL"
                ))
                conn.commit()
            log.info("迁移: documents.tags 列已添加")
        except Exception as e:
            log.warning(f"迁移 documents.tags 失败 (可能已存在): {e}")

    if "source_type" not in doc_cols:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN source_type VARCHAR(20) NOT NULL DEFAULT 'file'"))
                conn.commit()
            log.info("迁移: documents.source_type 列已添加")
        except Exception as e:
            log.warning(f"迁移 documents.source_type 失败: {e}")

    if "source_url" not in doc_cols:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN source_url VARCHAR(2000) NULL"))
                conn.commit()
            log.info("迁移: documents.source_url 列已添加")
        except Exception as e:
            log.warning(f"迁移 documents.source_url 失败: {e}")

    # 创建所有新表（create_all 只会创建不存在的表）
    Base.metadata.create_all(bind=engine)


def init_db():
    """应用启动时初始化数据库：创建所有表、执行迁移、创建默认用户"""
    # 创建所有表（如果不存在）
    Base.metadata.create_all(bind=engine)

    # 执行列迁移
    _migrate_db()

    # 创建默认用户（如果不存在）
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            import bcrypt
            default_user = User(
                id=1,
                username="default",
                password_hash=bcrypt.hashpw(
                    "default".encode(), bcrypt.gensalt()
                ).decode(),
            )
            db.add(default_user)
            db.commit()
            log.info("默认用户已创建 (ID=1, username=default)")
    finally:
        db.close()

    log.info("数据库初始化完成")

"""文档管理页面 — 上传、查看、删除文档（增强版：标签管理）.

重构后通过 DataService 统一数据入口，不再直接操作解析器/向量库.
"""
import os
import uuid
import streamlit as st
from ui import require_login
from database import SessionLocal, Document, ParentChunk, DocKbRelation
from services.data_service import data_service
from services.tag_service import tag_service
from config import settings
from loguru import logger as log

# Auth guard
require_login()

def get_user_id():
    """获取当前登录用户 ID"""
    return st.session_state.get("user_id", 1)


def get_db():
    """获取 SQLAlchemy 数据库会话（确保连接正确关闭）"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


# ── 标签渲染辅助函数 ─────────────────────────────────────────────
# 必须在主UI之前定义（页面渲染时会调用）

def _render_doc_tags(doc_id: int, tags, db):
    """渲染文档的标签块，包含添加/移除控件"""
    tag_names = []
    if tags:
        for t in tags:
            name = t.get("name", t) if isinstance(t, dict) else t
            source = t.get("source", "manual") if isinstance(t, dict) else "manual"
            tag_names.append({"name": name, "source": source})

    # 显示已有标签（最多8个，自动标签带🤖标识）
    if tag_names:
        n = max(1, min(len(tag_names), 8))
        tag_cols = st.columns(n)
        for i, t in enumerate(tag_names):
            with tag_cols[i % n]:
                label = t["name"]
                if t["source"] == "auto":
                    label += " 🤖"
                st.caption(label)
    else:
        st.caption("无标签")

    # 添加新标签输入框和按钮
    add_col1, add_col2 = st.columns([3, 1])
    with add_col1:
        new_tag = st.text_input(
            "添加标签",
            placeholder="输入标签名，回车添加",
            key=f"tag_input_{doc_id}",
            label_visibility="collapsed",
        )
    with add_col2:
        if st.button("➕ 添加", key=f"tag_add_{doc_id}"):
            if new_tag.strip():
                tag_service.add_tag(doc_id, new_tag.strip(), db=db)
                st.rerun()

    # 移除标签按钮（每个标签一个）
    if tag_names:
        n = max(1, min(len(tag_names), 6))
        rm_cols = st.columns(n)
        for i, t in enumerate(tag_names):
            with rm_cols[i % n]:
                if st.button(
                    f"✕ {t['name']}",
                    key=f"tag_rm_{doc_id}_{t['name']}",
                    help=f"移除标签「{t['name']}」",
                ):
                    tag_service.remove_tag(doc_id, t["name"], db=db)
                    st.rerun()


# ── 页面 UI ───────────────────────────────────────────────────────
st.title("📄 文档管理")

db = get_db()

# ── 文件上传区域 ──────────────────────────────────────────────────
st.subheader("📤 上传文档")
st.caption(f"支持格式: PDF, Word (.docx), TXT, Markdown | 最大: {settings.MAX_FILE_SIZE // 1024 // 1024}MB")

# 防止页面重刷新时重复处理已上传的文件（如用户点击"添加标签"时）
if "processed_files" not in st.session_state:
    st.session_state.processed_files = set()

# 获取知识库列表（用于上传时关联）
kbs = data_service.list_kbs(user_id=get_user_id(), db=db)
kb_options = {kb.id: kb.name for kb in kbs}
kb_options[0] = "暂不关联知识库"

# 文件上传组件和知识库选择
upload_col1, upload_col2 = st.columns([2, 1])
with upload_col1:
    uploaded_files = st.file_uploader(
        "选择文件",
        type=["pdf", "docx", "doc", "txt", "md", "markdown"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
with upload_col2:
    upload_kb_id = st.selectbox(
        "关联知识库",
        options=list(kb_options.keys()),
        format_func=lambda x: kb_options[x],
        key="upload_kb",
        label_visibility="collapsed",
    )

# 处理上传的文件
if uploaded_files:
    for uploaded_file in uploaded_files:
        # 生成文件唯一标识（文件名+大小），避免重复处理
        fid = f"{uploaded_file.name}|{uploaded_file.size}"
        if fid in st.session_state.processed_files:
            continue

        try:
            # 上传/向量化期间只维护一个稳定的状态组件。此前每个阶段都更新
            # st.progress，热重载或页面切换时可能触发 Streamlit 前端的 DOM 同步错误。
            with st.status(f"正在处理：{uploaded_file.name}", expanded=False) as upload_status:
                data_service.ingest_file(
                    uploaded_file=uploaded_file,
                    kb_id=upload_kb_id,
                    user_id=get_user_id(),
                    progress_callback=None,
                )
                upload_status.update(label=f"已完成：{uploaded_file.name}", state="complete")
            st.success(f"✅ **{uploaded_file.name}** 处理完成")
            st.session_state.processed_files.add(fid)

        except ValueError as e:
            st.error(f"❌ **{uploaded_file.name}** {str(e)}")
        except Exception as e:
            st.error(f"❌ **{uploaded_file.name}** 处理失败: {str(e)}")

# ── 文档列表区域 ──────────────────────────────────────────────────
st.divider()
st.subheader("📋 文档列表")

# 获取用户所有文档
documents = data_service.list_documents(user_id=get_user_id(), db=db)

if not documents:
    st.info("还没有上传任何文档")
else:
    # 标签筛选栏
    all_tags = tag_service.get_all_tags(user_id=get_user_id(), db=db)
    if all_tags:
        filter_col1, filter_col2 = st.columns([3, 1])
        with filter_col1:
            tag_options = [t["name"] for t in all_tags]
            selected_filter_tags = st.multiselect(
                "🏷️ 按标签筛选",
                options=tag_options,
                placeholder="选择一个或多个标签来筛选文档...",
                key="tag_filter",
            )
        with filter_col2:
            st.caption("")
            st.caption(f"共 {len(tag_options)} 个标签")
    else:
        selected_filter_tags = []

    # 根据标签筛选文档
    if selected_filter_tags:
        filtered_ids = set(tag_service.filter_by_tags(selected_filter_tags, user_id=get_user_id(), db=db))
        display_docs = [d for d in documents if d.id in filtered_ids]
        st.caption(f"筛选: 匹配 {len(display_docs)}/{len(documents)} 个文档")
    else:
        display_docs = documents

    if not display_docs and selected_filter_tags:
        st.info("没有匹配所选标签的文档")

    # 遍历显示每个文档
    for doc in display_docs:
        # 判断来源类型（网页或文件）
        source_icon = "🌐" if getattr(doc, "source_type", "file") == "web" else "📄"
        source_label = "网页" if getattr(doc, "source_type", "file") == "web" else "文件"

        # 文档展开面板（文档数≤3时默认展开）
        with st.expander(
            f"{'✅' if doc.status == 'completed' else '⏳'} "
            f"{source_icon} **{doc.original_filename}**  "
            f"({source_label}, {(doc.file_type or '?').upper()}, "
            f"{doc.file_size // 1024 if doc.file_size else 0}KB, "
            f"{doc.chunk_count} 分块)",
            expanded=len(display_docs) <= 3,
        ):
            # 第一行：文档元数据
            m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns([2, 1, 1, 1, 1])
            with m_col1:
                if getattr(doc, "source_type", "file") == "web" and getattr(doc, "source_url", None):
                    st.caption(f"URL: {doc.source_url[:60]}...")
                else:
                    st.caption(f"存储名: {doc.filename}")
            with m_col2:
                st.caption(f"来源: {source_icon} {source_label}")
            with m_col3:
                status_emoji = {
                    "uploading": "⬆️", "parsing": "📖", "chunking": "✂️",
                    "embedding": "🧮", "completed": "✅", "failed": "❌",
                }
                st.caption(f"状态: {status_emoji.get(doc.status, '❓')} {doc.status}")
            with m_col4:
                kb_count = db.query(DocKbRelation).filter(
                    DocKbRelation.document_id == doc.id
                ).count()
                st.caption(f"关联知识库: {kb_count} 个")
            with m_col5:
                st.caption(doc.created_at.strftime("%Y-%m-%d %H:%M") if doc.created_at else "")

            # 第二行：标签管理
            _render_doc_tags(doc.id, doc.tags, db)

            # 第三行：操作按钮
            act_col1, act_col2, act_col3 = st.columns([1, 1, 4])
            with act_col1:
                # 自动提取标签按钮
                if st.button("🤖 自动提取标签", key=f"auto_tag_{doc.id}",
                             help="使用AI从文档内容提取标签"):
                    doc_record = db.query(Document).filter(Document.id == doc.id).first()
                    if doc_record:
                        # 从父块中收集完整文档文本
                        chunks = db.query(ParentChunk).filter(
                            ParentChunk.document_id == doc.id
                        ).all()
                        full_text = " ".join(pc.content for pc in chunks)
                        tags = tag_service.auto_tag_document(doc.id, full_text, db=db)
                        if tags:
                            st.success(f"提取了 {len(tags)} 个标签")
                            st.rerun()
                        else:
                            st.warning("未能提取标签")
            with act_col2:
                # 删除文档按钮
                if st.button("🗑️", key=f"del_doc_exp_{doc.id}", help=f"删除 {doc.original_filename}"):
                    if data_service.delete_document(doc.id, db=db):
                        st.success(f"已删除 {doc.original_filename}")
                        st.rerun()
                    else:
                        st.error("删除失败")

# 关闭数据库连接
db.close()

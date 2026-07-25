"""知识库管理页面 — 创建、删除、添加/移除文档.

重构后通过 DataService 统一数据入口，不再直接操作数据库和向量库.
"""
import streamlit as st
from ui import require_login
from smart_doc_search.data.database import SessionLocal, Document, DocKbRelation
from smart_doc_search.services.data_service import data_service

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


# ── 页面 UI ───────────────────────────────────────────────────────
st.title("📚 知识库管理")

db = get_db()

# ── 创建知识库 ────────────────────────────────────────────────────
st.subheader("➕ 创建知识库")

col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    kb_name = st.text_input("名称", placeholder="输入知识库名称", label_visibility="collapsed", key="kb_name")
with col2:
    kb_desc = st.text_input("描述（可选）", placeholder="简要描述", label_visibility="collapsed", key="kb_desc")
with col3:
    if st.button("创建", use_container_width=True):
        if kb_name.strip():
            # 通过 DataService 创建知识库
            kb = data_service.create_kb(
                name=kb_name.strip(),
                description=kb_desc.strip() if kb_desc else "",
                user_id=get_user_id(),
                db=db,
            )
            if kb:
                st.success(f"知识库 '{kb_name}' 创建成功")
                st.rerun()
            else:
                st.error("创建失败")
        else:
            st.warning("请输入知识库名称")

# ── 知识库列表 ────────────────────────────────────────────────────
st.divider()
st.subheader("📋 知识库列表")

# 获取用户所有知识库
kbs = data_service.list_kbs(user_id=get_user_id(), db=db)

if not kbs:
    st.info("还没有创建任何知识库。创建一个知识库来组织你的文档。")
else:
    # 遍历显示每个知识库
    for kb in kbs:
        with st.expander(f"📚 **{kb.name}**  {f'— {kb.description}' if kb.description else ''}", expanded=False):
            col1, col2 = st.columns([3, 1])

            # 左侧：文档管理
            with col1:
                # 查询知识库关联的文档
                relations = db.query(DocKbRelation).filter(
                    DocKbRelation.knowledge_base_id == kb.id
                ).all()
                doc_ids = [r.document_id for r in relations]

                # 显示已关联的文档列表
                if doc_ids:
                    docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
                    st.caption(f"已关联 {len(docs)} 个文档:")
                    for doc in docs:
                        dcol1, dcol2 = st.columns([4, 1])
                        with dcol1:
                            status_emoji = "✅" if doc.status == "completed" else "⏳"
                            st.caption(f"  {status_emoji} {doc.original_filename}")
                        with dcol2:
                            # 移除文档按钮
                            if st.button("移除", key=f"rm_{kb.id}_{doc.id}"):
                                data_service.remove_doc_from_kb(doc.id, kb.id, db=db)
                                st.rerun()
                else:
                    st.caption("暂无关联文档")

                # 添加文档到知识库
                st.divider()
                st.caption("**添加文档到此知识库:**")

                # 获取尚未关联到此知识库的文档
                existing_doc_ids = set(doc_ids)
                all_docs = db.query(Document).filter(
                    Document.user_id == get_user_id(),
                    Document.status == "completed",
                ).order_by(Document.created_at.desc()).all()

                available_docs = [d for d in all_docs if d.id not in existing_doc_ids]

                if available_docs:
                    doc_options = {d.id: d.original_filename for d in available_docs}
                    selected_doc_id = st.selectbox(
                        "选择文档",
                        options=list(doc_options.keys()),
                        format_func=lambda x: doc_options[x],
                        key=f"add_doc_{kb.id}",
                        label_visibility="collapsed",
                    )
                    if st.button("添加", key=f"btn_add_{kb.id}"):
                        data_service.add_doc_to_kb(selected_doc_id, kb.id, db=db)
                        st.success("文档已添加到知识库")
                        st.rerun()
                else:
                    st.caption("所有文档都已关联到此知识库")

            # 右侧：统计信息和删除按钮
            with col2:
                # 显示向量块数统计
                chunk_count = data_service.get_kb_chunk_count(kb.id)
                st.metric("向量块数", chunk_count)

                # 删除知识库按钮
                if st.button("🗑️ 删除知识库", key=f"del_kb_{kb.id}", use_container_width=True):
                    if data_service.delete_kb(kb.id, db=db):
                        st.success(f"知识库 '{kb.name}' 已删除")
                        st.rerun()
                    else:
                        st.error("删除失败")

            # 显示创建时间
            st.caption(f"创建时间: {kb.created_at.strftime('%Y-%m-%d %H:%M') if kb.created_at else ''}")

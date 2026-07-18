"""对话页面 — RAG 智能问答 + 普通对话（无 HTML 注入，防 DOM 冲突）."""
import streamlit as st
from ui import require_login
from smart_doc_search.data.database import SessionLocal, KnowledgeBase, Conversation, Message
from smart_doc_search.services.rag_engine import rag_engine
from smart_doc_search.services.embedding_service import LLMError
from smart_doc_search.services.rag_engine import RetrievalError
from smart_doc_search.services.feedback_service import feedback_service

# Auth guard
require_login()

def get_user_id():
    """获取当前登录用户 ID"""
    return st.session_state.get("user_id", 1)


def get_db():
    """获取 SQLAlchemy 数据库会话"""
    return SessionLocal()


# ── 反馈按钮辅助函数 ────────────────────────────────────────────────

def _render_feedback_buttons(message_id: int):
    """渲染消息的👍👎评价按钮（不直接触发页面重刷新）"""
    fb_cols = st.columns([1, 1, 8])

    from smart_doc_search.data.database import Feedback
    fb_db = SessionLocal()
    try:
        # 查询用户是否已对该消息做出反馈
        existing = fb_db.query(Feedback).filter(
            Feedback.message_id == message_id,
            Feedback.user_id == get_user_id(),
        ).first()
    finally:
        fb_db.close()

    current_rating = existing.rating if existing else 0

    # 👍 好评按钮
    with fb_cols[0]:
        up_label = "👍" if current_rating > 0 else "👍🏻"
        if st.button(up_label, key=f"fb_up_{message_id}", help="回答有帮助"):
            feedback_service.record(
                message_id, rating=1, feedback_type="thumbs_up",
                user_id=get_user_id(),
            )
            st.session_state._fb_pending_rerun = True

    # 👎 差评按钮
    with fb_cols[1]:
        down_label = "👎" if current_rating < 0 else "👎🏻"
        if st.button(down_label, key=f"fb_down_{message_id}", help="回答不准确"):
            feedback_service.record(
                message_id, rating=-1, feedback_type="thumbs_down",
                user_id=get_user_id(),
            )
            st.session_state._fb_pending_rerun = True


# ── 来源/标签渲染辅助函数（使用 Streamlit 原生组件，无原始 HTML） ──

def _render_source(src: dict):
    """渲染单个文档引用来源及其标签"""
    filename = src.get("filename", f"文档#{src.get('document_id')}")
    page = src.get("page", "")
    score = src.get("score", 0)
    page_info = f"第{page}页 · " if page else ""
    st.markdown(f"**{filename}**  {page_info}相关度: {score:.2%}")
    
    # 显示文档标签（最多8个）
    doc_tags = src.get("tags", [])
    if doc_tags:
        tag_cols = st.columns(min(len(doc_tags), 8))
        for i, t in enumerate(doc_tags[:8]):
            with tag_cols[i]:
                st.caption(f"🏷️ {t}")


def _render_retrieval_details(rd: dict):
    """渲染 RAG 检索管道调试信息"""
    # 显示检索阶段流程
    stages = rd.get("pipeline_stages", [])
    if stages:
        stage_names = {
            "query_rewrite": "查询改写",
            "hybrid_search": "混合检索",
            "rerank": "重排序",
            "multi_query_fusion": "多查询融合",
            "context_compression": "上下文压缩",
            "fallback_basic": "回退基础检索",
            "complete": "完成",
        }
        # 去除后端后缀，如 "rerank(cross_attention_llm)" → "重排序"
        clean = []
        for s in stages:
            name = s.split("(")[0]
            clean.append(stage_names.get(name, name))
        st.caption("检索阶段: " + " → ".join(clean))
    
    # 显示检索统计指标
    col_a, col_b, col_c = st.columns(3)
    candidates = rd.get("candidates_before_rerank")
    col_a.metric("候选数", candidates if candidates is not None else "-")
    col_b.metric("父块数", rd.get("parent_chunks_used", "-"))
    col_c.metric("查询变体", len(rd.get("query_variants", [])))


# ── 页面 UI ───────────────────────────────────────────────────────
st.title("💬 智能对话")

db = get_db()

# ── 会话状态初始化 ────────────────────────────────────────────────
# active_kb_id: 当前选中的知识库ID（0表示普通对话）
# active_conv_id: 当前活跃的对话ID
# need_new_conv: 是否需要创建新对话
if "active_kb_id" not in st.session_state:
    st.session_state.active_kb_id = 0
if "active_conv_id" not in st.session_state:
    st.session_state.active_conv_id = None
if "need_new_conv" not in st.session_state:
    st.session_state.need_new_conv = False

# ── 获取知识库列表 ────────────────────────────────────────────────
kbs = db.query(KnowledgeBase).filter(KnowledgeBase.user_id == get_user_id()).all()
kb_names = {kb.id: kb.name for kb in kbs}
kb_id_list = [0] + list(kb_names.keys())  # 0 表示"普通对话"

# ── 获取已有对话列表 ──────────────────────────────────────────────
conversations = db.query(Conversation).filter(
    Conversation.user_id == get_user_id()
).order_by(Conversation.updated_at.desc()).all()

conv_list = {c.id: c.title or f"对话 {c.id}" for c in conversations}

# 如果没有任何对话，自动创建新对话
if not conversations and not st.session_state.need_new_conv:
    st.session_state.need_new_conv = True

# ── 创建新对话逻辑 ────────────────────────────────────────────────
if st.session_state.need_new_conv:
    mode = "rag" if st.session_state.active_kb_id > 0 else "chat"
    new_conv = Conversation(
        user_id=get_user_id(),
        knowledge_base_id=st.session_state.active_kb_id if st.session_state.active_kb_id > 0 else None,
        mode=mode,
    )
    db.add(new_conv)
    db.commit()
    st.session_state.active_conv_id = new_conv.id
    st.session_state.need_new_conv = False
    st.session_state.pop("conv_select", None)
    st.rerun()

# ── 顶部工具栏 ────────────────────────────────────────────────────
col_kb, col_conv, col_new, col_del = st.columns([3, 3, 1, 0.8])

# 知识库选择下拉框
with col_kb:
    st.session_state.active_kb_id = st.selectbox(
        "📚 知识库",
        options=kb_id_list,
        format_func=lambda x: kb_names.get(x, "普通对话"),
        index=kb_id_list.index(st.session_state.active_kb_id)
        if st.session_state.active_kb_id in kb_id_list else 0,
        key="kb_select",
    )

# 对话历史选择下拉框
with col_conv:
    if conv_list:
        # 如果当前对话不存在于列表中，重置为第一个对话
        if st.session_state.active_conv_id not in conv_list:
            st.session_state.active_conv_id = list(conv_list.keys())[0]

        st.session_state.active_conv_id = st.selectbox(
            "💬 对话历史",
            options=list(conv_list.keys()),
            format_func=lambda x: conv_list[x],
            index=list(conv_list.keys()).index(st.session_state.active_conv_id),
            key="conv_select",
        )

# 新建对话按钮
with col_new:
    st.write("")
    if st.button("➕ 新建", help="创建新对话", use_container_width=True):
        st.session_state.need_new_conv = True
        st.rerun()

# 删除当前对话按钮
with col_del:
    st.write("")
    if st.button("🗑️", help="删除当前对话", use_container_width=True, key="del_conv"):
        conv_id = st.session_state.active_conv_id
        if conv_id and conv_id > 0:
            c = db.query(Conversation).filter(Conversation.id == conv_id).first()
            if c:
                db.delete(c)
                db.commit()
        # 切换到剩余的最新对话或创建新对话
        remaining = db.query(Conversation).filter(
            Conversation.user_id == get_user_id()
        ).order_by(Conversation.updated_at.desc()).first()
        if remaining:
            st.session_state.active_conv_id = remaining.id
        else:
            st.session_state.need_new_conv = True
        st.rerun()

# ── 切换对话时同步知识库设置 ──────────────────────────────────────
conv = db.query(Conversation).filter(
    Conversation.id == st.session_state.active_conv_id
).first()
if conv:
    new_kb_id = st.session_state.active_kb_id if st.session_state.active_kb_id > 0 else None
    # 如果用户切换了知识库，更新对话的知识库关联和模式
    if conv.knowledge_base_id != new_kb_id:
        conv.knowledge_base_id = new_kb_id
        conv.mode = "rag" if new_kb_id else "chat"
        db.commit()

# ── 显示聊天消息列表 ──────────────────────────────────────────────
if conv:
    # 查询当前对话的所有消息（按时间升序）
    messages = db.query(Message).filter(
        Message.conversation_id == conv.id
    ).order_by(Message.created_at.asc()).all()

    # 遍历渲染每条消息
    for msg in messages:
        with st.chat_message(msg.role):
            st.markdown(msg.content)
            # 显示参考来源（如果有）
            if msg.sources:
                with st.expander("📎 参考来源", expanded=False):
                    for src in msg.sources:
                        _render_source(src)
            # 显示检索详情（如果有，用于调试）
            if msg.retrieval_details:
                with st.expander("🔍 检索详情", expanded=False):
                    _render_retrieval_details(msg.retrieval_details)
            # 对助手消息显示反馈按钮
            if msg.role == "assistant" and msg.id:
                _render_feedback_buttons(msg.id)

# ── 聊天输入处理 ──────────────────────────────────────────────────
if prompt := st.chat_input("输入你的问题..."):
    # 检查是否有活跃对话
    if not st.session_state.active_conv_id:
        st.warning("请先创建一个对话")
        st.stop()

    conv = db.query(Conversation).filter(
        Conversation.id == st.session_state.active_conv_id
    ).first()
    if not conv:
        st.stop()

    # ── 步骤1: 立即显示用户消息 ──
    with st.chat_message("user"):
        st.markdown(prompt)

    # ── 步骤2: 保存用户消息到数据库 ──
    user_msg = Message(conversation_id=conv.id, role="user", content=prompt)
    db.add(user_msg)
    # 如果对话还没有标题，用第一条消息作为标题
    if not conv.title:
        conv.title = prompt[:50] + ("..." if len(prompt) > 50 else "")
    db.commit()

    # ── 步骤3: 流式获取助手响应 ──
    full_response = ""
    sources = []
    retrieval_details = {}
    has_error = False

    try:
        # 获取对话历史（最近20条，用于上下文）
        history_msgs = db.query(Message).filter(
            Message.conversation_id == conv.id
        ).order_by(Message.created_at.asc()).all()
        conversation_history = [
            {"role": m.role, "content": m.content}
            for m in history_msgs[-21:-1]
        ]

        # 根据对话模式选择不同的生成方式
        if conv.mode == "rag" and conv.knowledge_base_id:
            # RAG模式：基于知识库检索生成回答
            stream = rag_engine.generate_rag_stream(
                query=prompt,
                knowledge_base_id=conv.knowledge_base_id,
                db=db,
                conversation_history=conversation_history,
            )
        else:
            # 普通聊天模式：直接调用LLM
            stream = rag_engine.generate_chat_stream(
                query=prompt,
                conversation_history=conversation_history,
            )

        # 实时流式显示回答
        with st.chat_message("assistant"):
            status_text = st.empty()  # 状态提示（如"检索中..."）
            placeholder = st.empty()  # 回答内容占位符
            for event in stream:
                if event["type"] == "status":
                    # 更新状态提示
                    status_text.caption(event["content"])
                elif event["type"] == "token":
                    # 追加token，显示打字效果
                    status_text.empty()
                    full_response += event["content"]
                    placeholder.markdown(full_response + "▌")
                elif event["type"] == "sources":
                    # 保存参考来源
                    sources = event["data"]
                elif event["type"] == "retrieval_details":
                    # 保存检索详情（用于调试）
                    retrieval_details = event["data"]
                elif event["type"] == "error":
                    # 处理流式错误
                    has_error = True
                    full_response = f"❌ {event['content']}"
                    status_text.empty()
                    placeholder.markdown(full_response)
            
            # 回答完成，移除光标和状态
            status_text.empty()
            placeholder.markdown(full_response)

            # 显示参考来源和检索详情
            if sources:
                with st.expander("📎 参考来源", expanded=False):
                    for src in sources:
                        _render_source(src)
            if retrieval_details:
                with st.expander("🔍 检索详情", expanded=False):
                    _render_retrieval_details(retrieval_details)

    except (LLMError, RetrievalError) as e:
        # 处理LLM或检索错误
        has_error = True
        full_response = f"❌ {str(e)}"
        with st.chat_message("assistant"):
            st.markdown(full_response)
    except Exception as e:
        # 处理其他未知错误
        has_error = True
        full_response = f"❌ 发生错误: {str(e)}"
        with st.chat_message("assistant"):
            st.markdown(full_response)

    # ── 步骤4: 保存助手消息到数据库 ──
    assistant_msg = Message(
        conversation_id=conv.id, role="assistant",
        content=full_response,
        sources=sources if sources else None,
        retrieval_details=retrieval_details if retrieval_details else None,
    )
    db.add(assistant_msg)
    db.commit()

    # 重刷新页面以显示反馈按钮和更新消息列表
    st.rerun()

# ── 反馈按钮延迟重刷新 ────────────────────────────────────────────
# 用户点击反馈按钮后，延迟重刷新以更新按钮状态
if st.session_state.get("_fb_pending_rerun"):
    st.session_state._fb_pending_rerun = False
    st.rerun()

# 关闭数据库连接
db.close()

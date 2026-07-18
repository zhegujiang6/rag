"""登录/注册页面 — 进入应用首先看到的页面."""
import streamlit as st
from database import SessionLocal
from services.auth_service import auth_service

# ── 页面配置 ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="登录 - 智能文档检索助手",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── 如果已登录，直接跳转到对话页 ──────────────────────────────────
if st.session_state.get("auth_ok"):
    st.switch_page("pages/chat.py")
    st.stop()

# ── CSS 样式 ────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* 隐藏侧边栏 */
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stAppViewContainer"] { margin-right: 0 !important; }

    /* 登录卡片容器 */
    .login-container {
        max-width: 420px;
        margin: 0 auto;
        padding-top: 8vh;
    }

    /* 标题区 */
    .login-header {
        text-align: center;
        margin-bottom: 2rem;
    }
    .login-header .icon {
        font-size: 3.5rem;
        display: block;
        margin-bottom: 0.5rem;
    }
    .login-header h1 {
        font-size: 1.6rem;
        margin: 0 0 0.3rem 0;
        color: #1a1a1a;
    }
    .login-header p {
        color: #888;
        font-size: 0.9rem;
        margin: 0;
    }

    /* 表单卡片 */
    .login-card {
        background: #fff;
        border: 1px solid #e8e8e8;
        border-radius: 12px;
        padding: 1.8rem 2rem 1.5rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    }

    /* Tab 样式 */
    div[data-testid="stTabs"] [role="tablist"] {
        justify-content: center;
        gap: 1rem;
        margin-bottom: 0.5rem;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        font-size: 1rem;
        padding: 0.5rem 1.8rem;
        border-radius: 8px;
    }

    /* 输入框样式 */
    div[data-testid="stTextInput"] input {
        border-radius: 8px;
        border: 1px solid #ddd;
        padding: 0.6rem 0.8rem;
        font-size: 0.95rem;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #1f77b4;
        box-shadow: 0 0 0 2px rgba(31,119,180,0.15);
    }

    /* 按钮 */
    div[data-testid="stButton"] button {
        border-radius: 8px;
        font-size: 0.95rem;
        font-weight: 500;
        padding: 0.55rem 1rem;
        transition: all 0.2s;
    }
    div[data-testid="stButton"] button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(31,119,180,0.25);
    }

    /* 版本信息 */
    .login-footer {
        text-align: center;
        color: #bbb;
        font-size: 0.8rem;
        margin-top: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ── 页面主体 ────────────────────────────────────────────────────────
st.markdown("""
<div class="login-container">
    <div class="login-header">
        <span class="icon">📚</span>
        <h1>智能文档检索助手</h1>
        <p>基于 RAG 的智能知识库问答系统</p>
    </div>
</div>
""", unsafe_allow_html=True)

# ── 登录/注册卡片 ──────────────────────────────────────────────────
col_left, col_center, col_right = st.columns([1, 2, 1])
with col_center:
    st.markdown('<div class="login-card">', unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["🔑 登录", "📝 注册"])

    with tab_login:
        username = st.text_input(
            "用户名", placeholder="请输入用户名",
            key="login_user", label_visibility="collapsed")
        # 用 placeholder 当 label
        st.caption("用户名")

        password = st.text_input(
            "密码", type="password", placeholder="请输入密码",
            key="login_pwd", label_visibility="collapsed")
        st.caption("密码")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("登 录", use_container_width=True, type="primary"):
            if not username or not password:
                st.error("请输入用户名和密码")
            else:
                db = SessionLocal()
                try:
                    user = auth_service.login(username, password, db)
                    if user:
                        st.session_state.user_id = user.id
                        st.session_state.username = user.username
                        st.session_state.auth_ok = True
                        st.switch_page("pages/chat.py")
                    else:
                        st.error("用户名或密码错误")
                finally:
                    db.close()

    with tab_register:
        reg_user = st.text_input(
            "用户名", placeholder="至少 3 个字符",
            key="reg_user", label_visibility="collapsed")
        st.caption("用户名（至少 3 个字符）")

        reg_pwd = st.text_input(
            "密码", type="password", placeholder="至少 6 个字符",
            key="reg_pwd", label_visibility="collapsed")
        st.caption("密码（至少 6 个字符）")

        reg_pwd2 = st.text_input(
            "确认密码", type="password", placeholder="再次输入密码",
            key="reg_pwd2", label_visibility="collapsed")
        st.caption("确认密码")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("注 册", use_container_width=True, type="primary"):
            if not reg_user or not reg_pwd:
                st.error("用户名和密码不能为空")
            elif len(reg_user) < 3:
                st.error("用户名至少 3 个字符")
            elif len(reg_pwd) < 6:
                st.error("密码至少 6 个字符")
            elif reg_pwd != reg_pwd2:
                st.error("两次输入的密码不一致")
            else:
                db = SessionLocal()
                try:
                    user = auth_service.register(reg_user, reg_pwd, db)
                    if user:
                        st.session_state.user_id = user.id
                        st.session_state.username = user.username
                        st.session_state.auth_ok = True
                        st.switch_page("pages/chat.py")
                    else:
                        st.error("用户名已被占用，请换一个")
                finally:
                    db.close()

    st.markdown('</div>', unsafe_allow_html=True)

# ── 底部版本信息 ──────────────────────────────────────────────────
st.markdown("""
<div class="login-footer">
    v2.0.0 · Powered by Qwen + ChromaDB
</div>
""", unsafe_allow_html=True)

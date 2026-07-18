"""
Streamlit 前端 (重构版) — 仅负责 UI 渲染。

启动: streamlit run app.py --server.port 8501
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings

# ── Page config (must be first st command) ────────────────────
st.set_page_config(
    page_title=settings.APP_NAME,
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 认证检查 ─────────────────────────────────────────────────
def check_auth():
    """检查用户是否已登录，未登录重定向到登录页。"""
    if "auth_token" not in st.session_state or not st.session_state.auth_token:
        # 不是登录页才重定向
        current_page = st.query_params.get("page", "")
        # Streamlit 的 switch_page 不能在这里用（before navigation）
        # 改为在 sidebar 中处理
        return False
    return True


def logout():
    """登出并跳转到登录页。"""
    from api_client import api_client
    api_client.logout()
    st.switch_page("pages/login.py")


# ── CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stChatMessage { padding: 0.5rem 1rem; }
    .source-citation {
        background: #f0f2f6; border-radius: 8px; padding: 0.5rem 0.8rem;
        margin: 0.3rem 0; font-size: 0.85rem;
    }
    .user-info { font-size: 0.85rem; color: #555; }
</style>
""", unsafe_allow_html=True)

# ── Navigation ─────────────────────────────────────────────────
pg = st.navigation({
    "功能": [
        st.Page("pages/chat.py", title="对话", icon="💬"),
        st.Page("pages/documents.py", title="文档管理", icon="📄"),
        st.Page("pages/web_import.py", title="网页导入", icon="🌐"),
        st.Page("pages/knowledge_bases.py", title="知识库", icon="📚"),
    ],
    "评测": [
        st.Page("pages/evaluation.py", title="RAGAS 评测", icon="📊"),
    ],
}, position="hidden")

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.title("智能文档检索助手")
    st.caption(f"v{settings.APP_VERSION}")

    # ── 用户状态 ──
    is_auth = st.session_state.get("auth_token") is not None
    if is_auth:
        st.divider()
        username = st.session_state.get("username", "未知用户")
        role = st.session_state.get("user_role", "USER")
        st.markdown(f"👤 **{username}**")
        st.caption(f"角色: {role}")
        st.caption(f"ID: {st.session_state.get('user_id', '-')}")
        if st.button("🚪 退出登录", use_container_width=True):
            logout()
    else:
        st.divider()
        st.warning("⚠️ 尚未登录")
        if st.button("🔑 去登录", use_container_width=True, type="primary"):
            st.switch_page("pages/login.py")
        st.stop()

    st.divider()

    # ── 导航菜单 ──
    st.markdown("**功能**")
    st.page_link("pages/chat.py", label="对话", icon="💬", use_container_width=True)
    st.page_link("pages/documents.py", label="文档管理", icon="📄", use_container_width=True)
    st.page_link("pages/web_import.py", label="网页导入", icon="🌐", use_container_width=True)
    st.page_link("pages/knowledge_bases.py", label="知识库", icon="📚", use_container_width=True)
    st.divider()
    st.markdown("**评测**")
    st.page_link("pages/evaluation.py", label="RAGAS 评测", icon="📊", use_container_width=True)
    st.divider()

    st.markdown("**连接配置**")
    st.caption(f"LLM: {settings.LLM_MODEL}")
    st.caption(f"网关: {settings.API_GATEWAY_URL}")

# ── Run ────────────────────────────────────────────────────────
pg.run()

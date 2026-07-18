"""登录后页面共用的布局与导航。"""
import streamlit as st
from config import settings


def apply_app_style() -> None:
    st.markdown("""<style>[data-testid="stSidebarNav"] { display: none; }
    .stChatMessage { padding: .5rem 1rem; }</style>""", unsafe_allow_html=True)


def render_sidebar() -> None:
    with st.sidebar:
        st.title("智能文档检索助手")
        st.caption(f"v{settings.APP_VERSION}")
        st.divider()
        st.markdown(f"👤 **{st.session_state.get('username', '用户')}**")
        if st.button("退出登录", key="logout", use_container_width=True):
            for key in ("auth_ok", "user_id", "username"):
                st.session_state.pop(key, None)
            st.switch_page("pages/login.py")
        st.divider()
        st.caption("功能导航")
        st.page_link("pages/chat.py", label="💬 对话", use_container_width=True)
        st.page_link("pages/documents.py", label="📄 文档管理", use_container_width=True)
        st.page_link("pages/web_import.py", label="🌐 网页导入", use_container_width=True)
        st.page_link("pages/knowledge_bases.py", label="📚 知识库", use_container_width=True)
        st.page_link("pages/evaluation.py", label="📊 RAGAS 评测", use_container_width=True)
        st.divider()
        st.caption(f"LLM：{settings.LLM_MODEL}")
        st.caption(f"Embedding：{settings.EMBEDDING_MODEL}")


def require_login() -> None:
    if not st.session_state.get("auth_ok"):
        st.switch_page("pages/login.py")
        st.stop()
    apply_app_style()
    render_sidebar()

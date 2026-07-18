"""智能文档检索助手 — Streamlit 主入口。"""

import streamlit as st
from loguru import logger as log

from smart_doc_search.core.config import settings
from smart_doc_search.data.database import init_db
from smart_doc_search.services.vector_store import vector_store
from ui import require_login

# ── Page config (must be first st command) ────────────────────────
st.set_page_config(
    page_title=settings.APP_NAME,
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Init services ─────────────────────────────────────────────────
@st.cache_resource
def init_app():
    log.info("正在初始化数据库...")
    init_db()
    log.info("正在初始化向量存储...")
    _ = vector_store.client
    log.info("应用初始化完成")
    return True


# ── CSS（侧边栏右置 + 样式优化）─────────────────────────────────
st.markdown("""
<style>
    /* ── 将侧边栏移到右侧 ── */
    /* ── 主内容区改为右侧留白 ── */
    /* ── 移动端适配 ── */
    /* ── 聊天消息样式 ── */
    .stChatMessage { padding: 0.5rem 1rem; }
    .source-citation {
        background: #f0f2f6; border-radius: 8px; padding: 0.5rem 0.8rem;
        margin: 0.3rem 0; font-size: 0.85rem;
    }
    .stProgress > div > div { background-color: #1f77b4; }
</style>
""", unsafe_allow_html=True)

# ── 初始化 ────────────────────────────────────────────────────────
init_app()

# ── Auth 检查：未登录跳转到登录页 ────────────────────────────────
require_login()

# ================================================================
# 侧边栏 — 用户信息 / 导航
# ================================================================

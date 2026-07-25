"""网页导入页面 — 输入 URL，爬取正文，导入知识库.

通过 DataService.ingest_url() 编排完整流程:
  URL → WebCrawler 爬取 → WebIngestor 适配 → Pipeline 处理 → 入库
"""
import streamlit as st
from ui import require_login
from smart_doc_search.services.data_service import data_service

def get_user_id():
    """获取当前登录用户 ID"""
    return st.session_state.get("user_id", 1)


# Auth guard
require_login()

# ── Session State 初始化 ───────────────────────────────────────────
# web_pending_urls: 待处理的 URL 列表
# web_import_results: 上次导入的结果列表
# web_importing: 是否正在执行导入操作
if "web_pending_urls" not in st.session_state:
    st.session_state.web_pending_urls = []
if "web_import_results" not in st.session_state:
    st.session_state.web_import_results = None
if "web_importing" not in st.session_state:
    st.session_state.web_importing = False


# ── 辅助函数 ────────────────────────────────────────────────────────

def _is_valid_url(url: str) -> bool:
    """基础 URL 合法性检查"""
    url = url.strip()
    if not url:
        return False
    # 至少包含一个点（域名）
    if "." not in url:
        return False
    # 不能有空格
    if " " in url:
        return False
    return True


def _normalize_url(url: str) -> str:
    """为 URL 添加协议头（http:// 或 https://）"""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


# ── 页面 UI ────────────────────────────────────────────────────────
st.title("🌐 网页导入")
st.caption("输入网页 URL，自动抓取正文内容并导入知识库。支持博客、文档、新闻等多数网页。")

# ── 知识库选择 ──────────────────────────────────────────────────────
# 获取用户所有知识库，用于选择导入目标
kbs = data_service.list_kbs(user_id=get_user_id())
kb_options = {kb.id: kb.name for kb in kbs}
kb_options[0] = "暂不关联知识库"

selected_kb = st.selectbox(
    "📚 目标知识库",
    options=list(kb_options.keys()),
    format_func=lambda x: kb_options[x],
    key="web_import_kb",
)

# ── URL 输入区 ──────────────────────────────────────────────────────
st.subheader("🔗 添加 URL")

col_input, col_add = st.columns([4, 1])
with col_input:
    url_input = st.text_input(
        "网页 URL",
        placeholder="https://example.com/article",
        label_visibility="collapsed",
        key="url_input",
    )
with col_add:
    if st.button("➕ 添加", use_container_width=True):
        normalized = _normalize_url(url_input)
        # 验证 URL 格式
        if not _is_valid_url(url_input):
            st.error("请输入有效的 URL（如 https://example.com/article）")
        # 检查是否已在列表中
        elif normalized in st.session_state.web_pending_urls:
            st.warning("该 URL 已在待处理列表中")
        # 添加到待处理列表
        else:
            st.session_state.web_pending_urls.append(normalized)
            st.rerun()

# ── 待处理 URL 列表 ────────────────────────────────────────────────
st.divider()

if st.session_state.web_pending_urls:
    st.subheader(f"📋 待处理 ({len(st.session_state.web_pending_urls)} 个 URL)")

    # 遍历显示每个待处理 URL
    for i, url in enumerate(st.session_state.web_pending_urls):
        col_url, col_remove = st.columns([10, 1])
        with col_url:
            st.caption(f"{i + 1}. {url}")
        with col_remove:
            # 移除按钮
            if st.button("✕", key=f"remove_url_{i}", help=f"移除 {url}"):
                st.session_state.web_pending_urls.pop(i)
                st.rerun()

    # ── 全部导入按钮 ─────────────────────────────────────
    st.divider()
    if st.button("🚀 全部导入", type="primary", use_container_width=True):
        st.session_state.web_importing = True
        st.rerun()

else:
    st.info("还没有添加 URL。在上方输入框中粘贴网页链接，点击「添加」。")

# ── 执行导入 ────────────────────────────────────────────────────────
# 当 web_importing 标志为 True 且有待处理 URL 时执行导入
if st.session_state.web_importing and st.session_state.web_pending_urls:
    urls_to_process = list(st.session_state.web_pending_urls)
    kb_id = selected_kb if selected_kb > 0 else 0

    results = []
    progress_bar = st.progress(0, text="准备导入...")

    # 遍历处理每个 URL
    for idx, url in enumerate(urls_to_process):
        base_progress = idx / len(urls_to_process)

        # 创建进度回调函数（闭包，捕获当前 URL 和基础进度）
        def make_callback(current_url):
            def cb(status, progress):
                status_texts = {
                    "crawling": f"正在抓取 {current_url[:60]}...",
                    "parsing": "解析中...",
                    "chunking": "文本切分...",
                    "embedding": "生成向量...",
                    "tagging": "提取标签...",
                    "completed": "完成!",
                }
                # 计算总进度（当前 URL 的基础进度 + 该 URL 内部进度的比例）
                pct = base_progress + progress / len(urls_to_process)
                progress_bar.progress(
                    min(pct, 1.0),
                    text=status_texts.get(status, status),
                )
            return cb

        try:
            # 通过 DataService 导入 URL（爬取→解析→向量化→入库）
            result = data_service.ingest_url(
                url=url,
                kb_id=kb_id,
                user_id=get_user_id(),
                progress_callback=make_callback(url),
            )

            # 根据结果状态记录
            if result["status"] == "ok":
                doc = result["doc"]
                results.append({
                    "url": url,
                    "status": "ok",
                    "detail": f"{doc.chunk_count} 分块, {doc.file_size // 1024 if doc.file_size else 0}KB",
                })
            elif result["status"] == "duplicate":
                # URL 已存在，跳过
                results.append({
                    "url": url,
                    "status": "duplicate",
                    "detail": "该 URL 已存在，跳过",
                })
            else:
                # 导入失败
                results.append({
                    "url": url,
                    "status": "error",
                    "detail": result.get("error", "未知错误"),
                })

        except Exception as e:
            # 捕获异常
            results.append({
                "url": url,
                "status": "error",
                "detail": str(e),
            })

    # ── 导入完成，更新状态 ─────────────────────────────────────
    progress_bar.progress(1.0, text="导入完成")
    st.session_state.web_import_results = results
    st.session_state.web_pending_urls = []   # 清空待处理列表
    st.session_state.web_importing = False
    st.rerun()

# ── 显示上次导入结果 ────────────────────────────────────────────────
if st.session_state.web_import_results:
    st.divider()
    st.subheader("📊 上次导入结果")

    results = st.session_state.web_import_results
    # 统计成功、跳过、失败的数量
    ok_count = sum(1 for r in results if r["status"] == "ok")
    dup_count = sum(1 for r in results if r["status"] == "duplicate")
    err_count = sum(1 for r in results if r["status"] == "error")

    # 显示统计指标
    col1, col2, col3 = st.columns(3)
    col1.metric("✅ 成功", ok_count)
    col2.metric("⚠️ 跳过", dup_count)
    col3.metric("❌ 失败", err_count)

    # 显示每个 URL 的导入结果详情
    for r in results:
        if r["status"] == "ok":
            st.success(f"✅ {r['url']}\n\n  → {r['detail']}")
        elif r["status"] == "duplicate":
            st.warning(f"⚠️ {r['url']}\n\n  → {r['detail']}")
        else:
            st.error(f"❌ {r['url']}\n\n  → {r['detail']}")

    # 清空结果按钮
    if st.button("清空结果", key="clear_results"):
        st.session_state.web_import_results = None
        st.rerun()

# ── 使用提示 ────────────────────────────────────────────────────────
with st.expander("💡 使用提示", expanded=False):
    st.markdown("""
    **支持的网页类型:**
    - ✅ 技术博客、文档站（如 CSDN、知乎、GitHub README）
    - ✅ 新闻文章、维基百科
    - ✅ 大部分静态网页
    - ⚠️ 需登录的页面（如飞书文档）— 暂不支持
    - ⚠️ 纯 JS 渲染页面 — 安装 playwright 后可支持

    **使用建议:**
    - 每次导入 3-5 个 URL 为宜，大量导入请分批进行
    - 导入后可在「文档管理」页面查看和添加标签
    - 同一 URL 不会重复导入（自动去重）
    """)

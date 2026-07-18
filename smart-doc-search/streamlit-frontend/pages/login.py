"""
登录 / 注册页面 — 用户进入应用的第一个页面。
"""
import streamlit as st
from api_client import api_client
import time

# ── 页面配置 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="登录 - 智能文档检索助手",
    page_icon="🔐",
    layout="centered",
)

# ── 如果已登录，直接跳到对话页 ──────────────────────────────
if "auth_token" in st.session_state and st.session_state.auth_token:
    st.switch_page("pages/chat.py")

# ── UI ──────────────────────────────────────────────────────
st.title("📚 智能文档检索助手")
st.caption("登录以访问你的知识库和文档")

tab_login, tab_register = st.tabs(["🔑 登录", "📝 注册"])

# ================================================================
# 登录 Tab
# ================================================================
with tab_login:
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("用户名", placeholder="请输入用户名")
        password = st.text_input("密码", type="password", placeholder="请输入密码")
        submitted = st.form_submit_button("登 录", use_container_width=True, type="primary")

        if submitted:
            if not username or not password:
                st.error("请输入用户名和密码")
            else:
                with st.spinner("正在登录..."):
                    try:
                        result = api_client.login(username, password)
                        # 登录成功，保存到 session
                        st.session_state.auth_token = result["accessToken"]
                        st.session_state.refresh_token = result["refreshToken"]
                        st.session_state.user_id = result["userId"]
                        st.session_state.username = result["username"]
                        st.session_state.user_role = result.get("role", "USER")
                        st.success(f"✅ 欢迎回来，{result['username']}！")
                        time.sleep(0.5)
                        st.switch_page("pages/chat.py")
                    except Exception as e:
                        st.error(f"登录失败: {e}")

# ================================================================
# 注册 Tab
# ================================================================
with tab_register:
    with st.form("register_form", clear_on_submit=False):
        reg_username = st.text_input("用户名", placeholder="3-50个字符", key="reg_user")
        reg_email = st.text_input("邮箱（选填）", placeholder="your@email.com", key="reg_email")
        reg_password = st.text_input("密码", type="password", placeholder="至少6个字符", key="reg_pwd")
        reg_password2 = st.text_input("确认密码", type="password", placeholder="再次输入密码", key="reg_pwd2")
        reg_submitted = st.form_submit_button("注 册", use_container_width=True, type="primary")

        if reg_submitted:
            if not reg_username or not reg_password:
                st.error("用户名和密码不能为空")
            elif len(reg_username) < 3:
                st.error("用户名至少 3 个字符")
            elif len(reg_password) < 6:
                st.error("密码至少 6 个字符")
            elif reg_password != reg_password2:
                st.error("两次输入的密码不一致")
            else:
                # 检查用户名是否已存在
                try:
                    exists = api_client.check_username(reg_username)
                    if exists:
                        st.error("用户名已被占用，请换一个")
                    else:
                        with st.spinner("正在注册..."):
                            result = api_client.register(
                                reg_username, reg_password, reg_email)
                            # 注册成功自动登录
                            st.session_state.auth_token = result["accessToken"]
                            st.session_state.refresh_token = result["refreshToken"]
                            st.session_state.user_id = result["userId"]
                            st.session_state.username = result["username"]
                            st.session_state.user_role = result.get("role", "USER")
                            st.success(f"✅ 注册成功！欢迎，{result['username']}！")
                            time.sleep(0.5)
                            st.switch_page("pages/chat.py")
                except Exception as e:
                    st.error(f"注册失败: {e}")

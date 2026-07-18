"""
Java 后端 API 客户端 — 统一封装所有 HTTP 调用。
"""
import json
import streamlit as st
import httpx
from typing import Optional, Dict, Any, Generator, List
from config import settings


class ApiClient:
    """封装对 Java 后端的所有 API 调用，自动处理认证。"""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or settings.API_GATEWAY_URL).rstrip("/")

    # ── Token 管理 ──────────────────────────────────────────

    @property
    def _token(self) -> Optional[str]:
        """从 Streamlit session_state 获取当前 Token。"""
        return st.session_state.get("auth_token")

    def _headers(self) -> Dict[str, str]:
        """构建通用请求头，自动附加 Bearer Token。"""
        headers = {"Content-Type": "application/json"}
        token = self._token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # ── 健康检查 ────────────────────────────────────────────

    def health_check(self) -> bool:
        """检查后端连通性。"""
        try:
            with httpx.Client(timeout=5) as client:
                r = client.get(f"{self.base_url}/actuator/health")
                return r.status_code == 200
        except Exception:
            return False

    # ── 认证 ────────────────────────────────────────────────

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """用户登录 → 返回 Token 信息。"""
        r = httpx.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        data = r.json()
        if data.get("code") == 0:
            return data["data"]
        raise Exception(data.get("message", "登录失败"))

    def register(self, username: str, password: str,
                 email: str = None) -> Dict[str, Any]:
        """用户注册 → 自动登录并返回 Token。"""
        body = {"username": username, "password": password}
        if email:
            body["email"] = email
        r = httpx.post(
            f"{self.base_url}/api/v1/auth/register",
            json=body,
            timeout=10,
        )
        data = r.json()
        if data.get("code") == 0:
            return data["data"]
        raise Exception(data.get("message", "注册失败"))

    def check_username(self, username: str) -> bool:
        """检查用户名是否已存在。"""
        try:
            r = httpx.get(
                f"{self.base_url}/api/v1/users/exists",
                params={"username": username},
                timeout=5,
            )
            return r.json().get("data", False)
        except Exception:
            return False

    def get_current_user(self) -> Dict[str, Any]:
        """获取当前登录用户信息。"""
        r = httpx.get(
            f"{self.base_url}/api/v1/users/me",
            headers=self._headers(),
            timeout=10,
        )
        data = r.json()
        if data.get("code") == 0:
            return data["data"]
        raise Exception(data.get("message", "获取用户信息失败"))

    def refresh_token(self) -> bool:
        """使用 Refresh Token 刷新 Access Token。"""
        refresh = st.session_state.get("refresh_token")
        if not refresh:
            return False
        try:
            r = httpx.post(
                f"{self.base_url}/api/v1/auth/refresh",
                json={"refreshToken": refresh},
                timeout=10,
            )
            data = r.json()
            if data.get("code") == 0:
                token_data = data["data"]
                st.session_state.auth_token = token_data["accessToken"]
                # Refresh Token 不变，不用更新
                return True
        except Exception:
            pass
        return False

    def logout(self) -> None:
        """登出并清除本地状态。"""
        try:
            token = self._token
            if token:
                httpx.post(
                    f"{self.base_url}/api/v1/auth/logout",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5,
                )
        except Exception:
            pass  # 登出失败不影响本地清理
        finally:
            self._clear_auth()

    def _clear_auth(self):
        """清除 session 中的认证信息。"""
        st.session_state.auth_token = None
        st.session_state.refresh_token = None
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.user_role = None

    # ── 文档管理 ────────────────────────────────────────────

    def upload_document(self, file_bytes: bytes, filename: str,
                        kb_id: int = None) -> Dict[str, Any]:
        """上传文档（multipart/form-data），每个用户只能看到自己的文档。"""
        files = {"file": (filename, file_bytes)}
        params = {}
        if kb_id:
            params["kbId"] = kb_id
        headers = {}
        token = self._token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = httpx.post(
            f"{self.base_url}/api/v1/documents/upload",
            files=files,
            params=params,
            headers=headers,
            timeout=120,
        )
        data = r.json()
        if data.get("code") == 0:
            return data["data"]
        raise Exception(data.get("message", "上传失败"))

    def get_documents(self, kb_id: int = None, tags: List[str] = None,
                      page: int = 1, size: int = 20) -> Dict[str, Any]:
        """获取文档列表（自动按当前用户隔离）。"""
        params = {"page": page, "size": size}
        if kb_id:
            params["kbId"] = kb_id
        if tags:
            params["tags"] = tags
        r = httpx.get(
            f"{self.base_url}/api/v1/documents",
            params=params,
            headers=self._headers(),
            timeout=30,
        )
        return r.json()

    def delete_document(self, doc_id: int) -> Dict[str, Any]:
        """删除文档。"""
        r = httpx.delete(
            f"{self.base_url}/api/v1/documents/{doc_id}",
            headers=self._headers(),
            timeout=30,
        )
        return r.json()

    # ── 知识库 ──────────────────────────────────────────────

    def create_kb(self, name: str, description: str = "") -> Dict[str, Any]:
        r = httpx.post(
            f"{self.base_url}/api/v1/knowledge-bases",
            json={"name": name, "description": description},
            headers=self._headers(),
            timeout=10,
        )
        data = r.json()
        if data.get("code") == 0:
            return data["data"]
        raise Exception(data.get("message", "创建失败"))

    def get_kb_list(self) -> List[Dict[str, Any]]:
        r = httpx.get(
            f"{self.base_url}/api/v1/knowledge-bases",
            headers=self._headers(),
            timeout=10,
        )
        data = r.json()
        return data.get("data", [])

    def delete_kb(self, kb_id: int) -> Dict[str, Any]:
        r = httpx.delete(
            f"{self.base_url}/api/v1/knowledge-bases/{kb_id}",
            headers=self._headers(),
            timeout=30,
        )
        return r.json()

    def add_doc_to_kb(self, kb_id: int, doc_id: int) -> Dict[str, Any]:
        r = httpx.post(
            f"{self.base_url}/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}",
            headers=self._headers(),
            timeout=30,
        )
        return r.json()

    def remove_doc_from_kb(self, kb_id: int, doc_id: int) -> Dict[str, Any]:
        r = httpx.delete(
            f"{self.base_url}/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}",
            headers=self._headers(),
            timeout=30,
        )
        return r.json()

    # ── RAG 对话 (SSE 流式) ────────────────────────────────

    def chat_rag_stream(self, query: str, kb_id: int,
                        history: List[Dict] = None, top_k: int = 5
                        ) -> Generator[Dict[str, Any], None, None]:
        """RAG 流式对话 — 解析 SSE 事件流。"""
        headers = self._headers()
        headers["Accept"] = "text/event-stream"

        with httpx.stream(
            "POST",
            f"{self.base_url}/api/v1/chat/rag/stream",
            json={
                "query": query,
                "knowledgeBaseId": kb_id,
                "conversationHistory": history or [],
                "topK": top_k,
            },
            headers=headers,
            timeout=settings.API_TIMEOUT,
        ) as response:
            # 401 表示 Token 过期，尝试刷新
            if response.status_code == 401:
                if self.refresh_token():
                    # 重试（简单实现：抛异常让上层重试）
                    raise Exception("Token 已刷新，请重试")
                else:
                    raise Exception("登录已过期，请重新登录")

            for line in response.iter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        return
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

    def chat_stream(self, query: str, history: List[Dict] = None
                    ) -> Generator[str, None, None]:
        """普通流式对话。"""
        headers = self._headers()
        headers["Accept"] = "text/event-stream"

        with httpx.stream(
            "POST",
            f"{self.base_url}/api/v1/chat/stream",
            json={"query": query, "conversationHistory": history or []},
            headers=headers,
            timeout=settings.API_TIMEOUT,
        ) as response:
            if response.status_code == 401:
                if self.refresh_token():
                    raise Exception("Token 已刷新，请重试")
                else:
                    raise Exception("登录已过期，请重新登录")

            for line in response.iter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        return
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        continue


# ── 单例 ─────────────────────────────────────────────────────
api_client = ApiClient()

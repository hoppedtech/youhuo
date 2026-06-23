"""有活平台共享 Token 存储。

所有 youhuo-* MCP Server 通过此模块共享已授权的 Token。
使用 SQLite 本地存储，支持多进程并发访问。
"""
import os
import json
import sqlite3
import time
import uuid

from tools.token_util import normalize_bearer_token

DB_DIR = os.path.expanduser("~/.workbuddy")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.getenv("YOUHUO_AUTH_DB_PATH", os.path.join(DB_DIR, "youhuo_auth.db"))
_db_parent = os.path.dirname(os.path.abspath(DB_PATH))
if _db_parent:
    os.makedirs(_db_parent, exist_ok=True)


class AuthStore:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_id TEXT PRIMARY KEY,
                    token TEXT,
                    role INTEGER,
                    user_info TEXT,
                    status TEXT DEFAULT 'pending',
                    expires_at REAL
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """
            )
            conn.commit()

    def create_session(self, role: int = 1) -> str:
        session_id = uuid.uuid4().hex[:12]  # 12位hex=48位熵，足够5分钟窗口内唯一；缩短以适配微信scene 32字符限制
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO auth_sessions (session_id, role, status, expires_at) VALUES (?, ?, ?, ?)",
                (session_id, role, "pending", time.time() + 3600),
            )
            conn.commit()
        return session_id

    def set_token(
        self,
        session_id: str,
        token: str,
        user_info: dict | None = None,
        expires_in: int = 7200,
    ):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                UPDATE auth_sessions
                SET token=?, user_info=?, status='authorized', expires_at=?
                WHERE session_id=?
            """,
                (
                    normalize_bearer_token(token),
                    json.dumps(user_info, ensure_ascii=False) if user_info else None,
                    time.time() + expires_in,
                    session_id,
                ),
            )
            conn.commit()

    def get_token(self, session_id: str) -> dict | None:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                """
                SELECT token, role, user_info, status, expires_at
                FROM auth_sessions WHERE session_id=?
            """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
        token, role, user_info, status, expires_at = row
        if time.time() > expires_at:
            return None
        return {
            "token": normalize_bearer_token(token or ""),
            "role": role,
            "user_info": json.loads(user_info) if user_info else None,
            "status": status,
        }

    def set_current_session(self, session_id: str):
        """设置当前活跃会话（AI 单会话单用户）。"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM kv_store WHERE key='current_session'")
            conn.execute(
                "INSERT INTO kv_store (key, value) VALUES (?, ?)",
                ("current_session", session_id),
            )
            conn.commit()

    def get_current_token(self) -> dict | None:
        """获取当前活跃会话的 Token（供其他 Server 调用）。"""
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT value FROM kv_store WHERE key='current_session'"
            ).fetchone()
            if not row:
                return None
            return self.get_token(row[0])

    def cleanup_expired(self):
        """清理过期会话。"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (time.time(),))
            conn.commit()

    def revoke_current_session(self) -> bool:
        """注销当前活跃会话，清除 Token 并移除 current_session 指针。"""
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT value FROM kv_store WHERE key='current_session'"
            ).fetchone()
            if not row:
                return False
            session_id = row[0]
            conn.execute("DELETE FROM kv_store WHERE key='current_session'")
            conn.execute(
                """
                UPDATE auth_sessions
                SET token=NULL, status='revoked'
                WHERE session_id=?
            """,
                (session_id,),
            )
            conn.commit()
        return True


auth_store = AuthStore()

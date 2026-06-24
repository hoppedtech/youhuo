"""B/C 端 auth 模块共用的 check_auth_status / get_current_user_info 逻辑。"""
from __future__ import annotations

import json

from shared_token_store import auth_store
from tools.auth_response import (
    format_authorized_status,
    sanitize_user_info,
    session_role_mismatch,
)


def check_auth_status_from_cache(session_id: str) -> str | None:
    local = auth_store.get_token(session_id)
    if not local or local.get("status") != "authorized" or not local.get("token"):
        return None
    user_info = local.get("user_info") or {}
    return json.dumps(
        format_authorized_status(
            session_role=int(local["role"]),
            user_info=user_info,
            is_new_user=bool(user_info.get("is_new_user")),
        ),
        ensure_ascii=False,
    )


def finalize_authorization(
    session_id: str,
    token: str,
    user_info: dict,
    *,
    is_new_user: bool = False,
) -> str:
    """校验 role、写入 Token，返回脱敏后的 authorized 响应。"""
    session = auth_store.get_token(session_id)
    if not session:
        return json.dumps(
            {"status": "pending", "message": "会话不存在或已过期，请重新 create_auth_session"},
            ensure_ascii=False,
        )
    session_role = int(session["role"])
    mismatch = session_role_mismatch(session_role, user_info)
    if mismatch:
        return json.dumps({"status": "pending", "message": mismatch}, ensure_ascii=False)

    user_info = dict(user_info)
    user_info["is_new_user"] = is_new_user
    auth_store.set_token(session_id, token, user_info=user_info, expires_in=7200)
    result = format_authorized_status(
        session_role=session_role,
        user_info=user_info,
        is_new_user=is_new_user,
    )
    if is_new_user:
        result["message"] = "欢迎首次使用有活！已为您自动完成注册。"
    return json.dumps(result, ensure_ascii=False)


def get_current_user_info_response() -> str:
    info = auth_store.get_current_token()
    if not info or not info.get("token"):
        return json.dumps(
            {
                "status": "unauthorized",
                "message": "当前未授权，请先调用 create_auth_session 完成扫码授权",
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "status": "authorized",
            "role": info["role"],
            "role_name": "招工方" if info["role"] == 2 else "找活方",
            "user_info": sanitize_user_info(info.get("user_info")),
        },
        ensure_ascii=False,
    )

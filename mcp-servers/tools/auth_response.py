"""Auth Tool 响应格式化、role 校验与 PII 脱敏。"""
from __future__ import annotations

from tools.api_response import mask_phone


def jwt_role(user_info: dict | None) -> int | None:
    if not user_info:
        return None
    value = user_info.get("loginroletype")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def session_role_mismatch(session_role: int, user_info: dict | None) -> str | None:
    """JWT loginroletype 与会话 role 不一致时返回错误说明。"""
    jwt_r = jwt_role(user_info)
    if jwt_r is None:
        return None
    if int(session_role) == int(jwt_r):
        return None
    expected = "招工方(B端)" if int(session_role) == 2 else "找活方(C端)"
    actual = "招工方(B端)" if int(jwt_r) == 2 else "找活方(C端)"
    return (
        f"扫码角色不匹配：本会话为 {expected}，但微信登录为 {actual}。"
        "请重新调用 create_auth_session 后使用对应端微信扫码。"
    )


def sanitize_user_info(user_info: dict | None) -> dict | None:
    if not user_info or not isinstance(user_info, dict):
        return user_info
    out = dict(user_info)
    phone = out.get("phone")
    if phone:
        out["phone"] = mask_phone(str(phone))
    return out


def format_authorized_status(
    *,
    session_role: int,
    user_info: dict | None,
    is_new_user: bool = False,
) -> dict:
    """授权成功时对 Agent 可见的字段（不含 token 片段、明文手机号）。"""
    ui = user_info or {}
    result: dict = {
        "status": "authorized",
        "role": session_role,
        "user_name": ui.get("name") or "",
        "is_new_user": is_new_user,
    }
    phone = ui.get("phone")
    if phone:
        result["phone_masked"] = mask_phone(str(phone))
    return result

"""Auth Tool 响应格式化、role 校验与 PII 脱敏。"""
from __future__ import annotations

from tools.api_response import mask_phone

# JWT loginroletype（有活 SSO）
JWT_ROLE_SEEKER = 1
JWT_ROLE_B_PERSONAL = 2
JWT_ROLE_B_ENTERPRISE = 3

JWT_ROLE_LABELS: dict[int, str] = {
    JWT_ROLE_SEEKER: "找活方(C端)",
    JWT_ROLE_B_PERSONAL: "个人招工(B端)",
    JWT_ROLE_B_ENTERPRISE: "企业招工(B端)",
}


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


def jwt_role_label(jwt_r: int) -> str:
    return JWT_ROLE_LABELS.get(int(jwt_r), f"未知角色({jwt_r})")


def session_role_matches_jwt(session_role: int, jwt_r: int) -> bool:
    """MCP 会话 role 与 JWT loginroletype 是否匹配。"""
    session_role = int(session_role)
    jwt_r = int(jwt_r)
    if session_role == 1:
        return jwt_r == JWT_ROLE_SEEKER
    if session_role == 2:
        return jwt_r in (JWT_ROLE_B_PERSONAL, JWT_ROLE_B_ENTERPRISE)
    return session_role == jwt_r


def session_role_mismatch(session_role: int, user_info: dict | None) -> str | None:
    """JWT loginroletype 与会话 role 不一致时返回错误说明。"""
    jwt_r = jwt_role(user_info)
    if jwt_r is None:
        return None
    if session_role_matches_jwt(session_role, jwt_r):
        return None
    expected = "招工方(B端)" if int(session_role) == 2 else "找活方(C端)"
    actual = jwt_role_label(jwt_r)
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
    jwt_r = jwt_role(ui)
    if jwt_r is not None:
        result["loginroletype"] = jwt_r
        if label := JWT_ROLE_LABELS.get(jwt_r):
            result["loginroletype_desc"] = label
    return result

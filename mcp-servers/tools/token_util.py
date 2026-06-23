"""Token 解析：剥离 Bearer 前缀、从 JWT 提取用户信息。"""
import base64
import json


def normalize_bearer_token(raw: str) -> str:
    """从 GetTokenBySession 等接口返回值中提取纯 Token。

    后端可能返回:
    - eyJhbGci...
    - Bearer eyJhbGci...
    """
    if not raw:
        return ""
    token = raw.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def parse_jwt_payload(token: str) -> dict:
    """解析 JWT payload（不验签），用于展示用户信息。"""
    token = normalize_bearer_token(token)
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(decoded)
    except Exception:
        return {}


def token_user_info(token: str) -> dict:
    """从 Token 提取常用用户字段。"""
    payload = parse_jwt_payload(token)
    if not payload:
        return {}
    return {
        "name": payload.get("realname") or payload.get("name") or "",
        "phone": payload.get("phonenumber") or payload.get("loginaccount") or "",
        "userid": payload.get("userid") or payload.get("sub") or "",
        "loginroletype": payload.get("loginroletype"),
        "loginroleid": payload.get("loginroleid"),
        "tenant_id": payload.get("tenantId"),
    }

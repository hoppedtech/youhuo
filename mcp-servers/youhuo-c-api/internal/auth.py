"""有活平台扫码授权 MCP Server。

提供用户扫码授权能力，生成小程序码，管理 Token 生命周期。
所有其他 youhuo-* Server 都通过 shared_token_store 获取 Token。
"""
import os
import sys
import json
import httpx

# 将 shared_token_store 加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared_token_store import auth_store
from tools.mcp_write_guard import WriteGate
from tools.qr_auth import fetch_qr_image_url
from tools.token_util import normalize_bearer_token, token_user_info
from tools.youhuo_env import applet_base_url, get_token_by_session_url
from tools.auth_common import (
    check_auth_status_from_cache,
    finalize_authorization,
    get_current_user_info_response,
)

# 延迟导入 mcp，避免未安装时崩溃
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

mcp = FastMCP("youhuo-auth-service")

BASE_URL = applet_base_url()
GET_TOKEN_BY_SESSION_URL = get_token_by_session_url()


@mcp.tool()
async def create_auth_session(role: int = 1, source_code: int = 0) -> str:
    """创建用户扫码授权会话，返回小程序码和会话ID。

    用户需要用手机微信扫描二维码，在小程序中完成登录授权。
    授权完成后，Token 会自动存入共享存储，其他 Server 可直接使用。

    复用现有接口: GET Personal/GetAIAuthQRCode?sessionId={session_id}&role={role}&sourceCode={source_code}
    scene编码格式: sid={session_id}&role={role}&sc={source_code} (微信scene限制32字符)

    Args:
        role: 用户角色。1=找活方(C端)，2=招工方(B端)。默认1
        source_code: 来源 Agent 编号（整数）。0 表示未指定

    Returns:
        JSON字符串，包含 session_id、qr_code_url（小程序码图片地址）、instruction
    """
    # 清理过期会话
    auth_store.cleanup_expired()

    # 创建会话
    session_id = auth_store.create_session(role=role)

    # 设置为当前活跃会话
    auth_store.set_current_session(session_id)

    qr_image_url, qr_api_url = await fetch_qr_image_url(BASE_URL, session_id, role, source_code)

    role_name = "招工方" if role == 2 else "找活方"

    result = {
        "session_id": session_id,
        "role": role,
        "role_name": role_name,
        "source_code": source_code,
        "qr_image_url": qr_image_url,
        "qr_code_url": qr_image_url,
        "qr_api_url": qr_api_url,
        "instruction": f"请使用微信扫描下方二维码完成{role_name}授权",
        "status": "pending",
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def check_auth_status(session_id: str) -> str:
    """检查扫码授权状态，授权成功后返回用户信息和 Token 摘要。

    需要轮询调用此接口（建议间隔 3 秒），直到 status 变为 authorized。

    对应后端新增接口: GET Login/GetTokenBySession?session_id={session_id}
    （后端仅需实现这一个接口，约 10 行代码）

    Args:
        session_id: create_auth_session 返回的会话ID

    Returns:
        JSON字符串，status: pending / authorized / expired
        授权成功时额外返回 is_new_user（true=新用户首次注册）
    """
    cached = check_auth_status_from_cache(session_id)
    if cached:
        return cached

    # 轮询后端新增接口
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GET_TOKEN_BY_SESSION_URL,
                params={"session_id": session_id},
            )
            data = resp.json()
            # 兼容 WebApiResult(ActionResult) 与 {code,data} 两种响应格式
            token_data = None
            is_new_user = False
            if data.get("ActionResult") == "1" and data.get("Data"):
                token_data = data["Data"]
                is_new_user = data.get("Message") == "1"
            elif data.get("code") == 200 and data.get("data"):
                token_data = data["data"]
                is_new_user = data.get("message") == "1"

            if token_data:
                raw_token = token_data if isinstance(token_data, str) else json.dumps(token_data)
                token = normalize_bearer_token(raw_token)
                user_info = token_user_info(token)
                return finalize_authorization(
                    session_id,
                    token,
                    user_info,
                    is_new_user=is_new_user,
                )
    except Exception as e:
        # 后端接口未就绪时静默失败
        return json.dumps({"status": "pending", "message": f"等待用户扫码授权... ({type(e).__name__})"}, ensure_ascii=False)

    return json.dumps({"status": "pending", "message": "等待用户扫码授权..."}, ensure_ascii=False)


@mcp.tool()
async def get_current_user_info() -> str:
    """获取当前已授权用户的基本信息。

    Returns:
        JSON字符串，包含用户姓名、角色、认证状态等
    """
    return get_current_user_info_response()


@mcp.tool()
async def revoke_auth(
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """注销当前授权会话，清除 Token。

    ⚠️ 须先 prepare_write_confirmation 获取 confirm_token，再 user_confirmed=true 调用。

    用户主动退出或切换账号时调用。
    """
    g = WriteGate(
        "revoke_auth",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
    )
    if g.blocked:
        return g.blocked

    if not auth_store.get_current_token():
        return g.finish("当前没有活跃的授权会话")
    auth_store.revoke_current_session()
    return g.finish("✅ 授权已注销，Token 已清除")


if __name__ == "__main__":
    mcp.run(transport="stdio")

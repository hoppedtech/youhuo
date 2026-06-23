"""有活平台 B 端（招工方）统一 MCP Server。

整合：扫码授权 + 岗位发布/调度 + 众包任务 + 结算/发票。
对应 Skill：job-planner、workforce-dispatcher。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

from shared_token_store import auth_store
from tools.qr_auth import fetch_qr_image_url
from tools.compose import load_tools_from_server, _internal_path
from tools.youhuo_env import applet_base_url

mcp = FastMCP("youhuo-b-api")

BASE_URL = applet_base_url()

load_tools_from_server(
    mcp,
    _internal_path("youhuo-b-api", "auth"),
    skip={"create_auth_session"},
)
load_tools_from_server(
    mcp,
    _internal_path("youhuo-b-api", "hire"),
    skip={"get_enterprise_balance"},
)
load_tools_from_server(mcp, _internal_path("youhuo-b-api", "task"))
load_tools_from_server(
    mcp,
    _internal_path("youhuo-b-api", "finance"),
    skip={"get_worker_balance", "withdraw_balance"},
)


@mcp.tool()
async def create_auth_session(source_code: str = "") -> str:
    """创建 B 端（招工方）扫码授权会话，返回小程序码和会话 ID。

    固定 role=2，用户微信扫码后在小程序完成登录。
    source_code 用于记录来源 Agent（可选，scene限制最大约3字符）。
    """
    auth_store.cleanup_expired()
    session_id = auth_store.create_session(role=2)
    auth_store.set_current_session(session_id)
    qr_image_url, qr_api_url = await fetch_qr_image_url(BASE_URL, session_id, 2, source_code)
    return json.dumps(
        {
            "session_id": session_id,
            "role": 2,
            "role_name": "招工方",
            "source_code": source_code,
            "qr_image_url": qr_image_url,
            "qr_code_url": qr_image_url,
            "qr_api_url": qr_api_url,
            "instruction": "请使用微信扫描下方二维码完成招工方授权（qr_image_url 为可直接展示的图片链接）",
            "status": "pending",
        },
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

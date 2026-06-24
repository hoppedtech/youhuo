"""C 端写操作两阶段确认（prepare_write_confirmation）。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

from tools.mcp_write_guard import (
    C_WRITE_TOOL_NAMES_CONFIRM_ONLY,
    C_WRITE_TOOL_NAMES_TOKEN,
    issue_confirm_token,
    parse_prepare_params_json,
)

mcp = FastMCP("youhuo-c-guard-api")


@mcp.tool()
async def prepare_write_confirmation(
    tool_name: str,
    params_json: str,
    preview_summary: str = "",
) -> str:
    """写操作阶段一：申请 confirm_token（不修改平台数据）。

    C 端 P0/P1 写 Tool（apply_job、submit_job_registration、
    cancel_apply、revoke_auth）须先调用本 Tool，向用户展示摘要并获明确确认后再执行。

    P2 低危写 Tool（update_work_preferences、简历类、候补类）仅需 user_confirmed=true，
    无需 confirm_token。

    Args:
        tool_name: 目标写 Tool 名称，如 apply_job、cancel_apply
        params_json: 与阶段二完全相同的业务参数 JSON（不含 user_confirmed/confirm_token）
        preview_summary: 给用户看的操作摘要（岗位名、金额、对象 ID 等）

    Returns:
        confirm_token（约 5 分钟有效）、expires_in、params_preview
    """
    if tool_name not in C_WRITE_TOOL_NAMES_TOKEN:
        return json.dumps(
            {
                "success": False,
                "error": f"Tool `{tool_name}` 不支持两阶段 confirm_token",
                "token_required_tools": sorted(C_WRITE_TOOL_NAMES_TOKEN),
                "confirm_only_tools": sorted(C_WRITE_TOOL_NAMES_CONFIRM_ONLY),
            },
            ensure_ascii=False,
        )
    try:
        params = parse_prepare_params_json(params_json)
    except json.JSONDecodeError as e:
        return json.dumps(
            {"success": False, "error": f"params_json 不是合法 JSON: {e}"},
            ensure_ascii=False,
        )
    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    try:
        issued = issue_confirm_token(tool_name, params, preview_summary=preview_summary)
    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return json.dumps(
        {
            "success": True,
            **issued,
            "instruction": (
                f"请向用户展示以上摘要，获明确确认（如「确认报名」「确认提现」）后，"
                f"调用 `{tool_name}` 并传入 user_confirmed=true、confirm_token、confirmation_summary。"
                "阶段二请按 canonical_params_json 中的字段以 JSON-RPC 对象传参（语义等价即可）；"
                "token hash 以服务端 canonical 归一化 + separators=(',', ':') 为准。"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )

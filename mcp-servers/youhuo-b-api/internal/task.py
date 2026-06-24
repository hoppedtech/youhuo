"""有活平台众包任务 MCP Server。

提供众包任务发布、订单查询、交付验收等能力。
job-planner Skill 发布众包任务时依赖本 Server。
"""
import os
import sys
import json
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared_token_store import auth_store
from tools.youhuo_env import employ_base_url, task_base_url
from tools.api_response import api_ok, api_message, api_list, flatten_task_categories, format_task_order_item
from tools.enterprise_balance import (
    build_enterprise_balance_view,
    parse_user_profile,
    unwrap_balance_payload,
    validate_balance_for_task_publish,
    publish_balance_error_json,
)
from tools.mcp_write_guard import WriteGate

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

mcp = FastMCP("youhuo-task-api")

TASK_URL = task_base_url()
EMPLOY_URL = employ_base_url()


async def _req(method: str, path: str, **kwargs):
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception(
            "未授权：请先调用 youhuo-b-api.create_auth_session() "
            "完成扫码授权，再执行此操作"
        )
    token = token_info["token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-USER_ROLE": "2",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{TASK_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _req_employ(method: str, path: str, **kwargs):
    """B 端 employ 网关（余额、用户资料等）。"""
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception(
            "未授权：请先调用 youhuo-b-api.create_auth_session() "
            "完成扫码授权，再执行此操作"
        )
    headers = {
        "Authorization": f"Bearer {token_info['token']}",
        "Content-Type": "application/json",
        "X-USER_ROLE": "2",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{EMPLOY_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def get_task_categories() -> str:
    """获取众包任务分类目录。

    对应接口: applettask/getcaterogyinfo (GET)
    """
    try:
        result = await _req("GET", "applettask/getcaterogyinfo")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    data = result.get("data") or result.get("Data") or {}
    cats = flatten_task_categories(data if isinstance(data, dict) else {})
    if not cats:
        return "暂无任务分类数据。"
    lines = ["任务分类："]
    for c in cats[:80]:
        cat_id = c.get("id", "—")
        name = c.get("category_name") or c.get("name", "—")
        lines.append(f"  • [{cat_id}] {name}")
    return "\n".join(lines)


@mcp.tool()
async def publish_task(
    category_id: str,
    title: str,
    description: str,
    location: str,
    budget: float,
    deadline: str,
    require_cert: list = None,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """发布众包任务到有活平台。

    对应接口: applettask/publishtask (POST)

    ⚠️ 调用约束：须补齐任务分类、预算、截止日期等信息，调用 get_enterprise_finance(sections=balance)
    对比预算，向企业用户展示摘要并获明确确认后再执行；须 user_confirmed=true。
    发布前 MCP 硬校验：预算与可用余额均须大于 0。禁止代用户确认或代充值。

    Args:
        category_id: 任务类别ID（可通过 get_task_categories 获取）
        title: 任务标题
        description: 任务描述和要求
        location: 任务地点
        budget: 预算金额（元）
        deadline: 截止日期，格式 YYYY-MM-DD
        require_cert: 所需资质证书列表
        user_confirmed: 必须为 true
        confirmation_summary: 可选，用户确认原话摘要
    """
    g = WriteGate(
        "publish_task",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        category_id=category_id,
        title=title,
        description=description,
        location=location,
        budget=budget,
        deadline=deadline,
        require_cert=require_cert,
    )
    if g.blocked:
        return g.blocked

    try:
        balance_result = await _req_employ("POST", "miniprogram/account/balance", json={})
        profile_result = await _req_employ("GET", "user/login/getUserLoginDetail")
        balance_view = build_enterprise_balance_view(
            unwrap_balance_payload(balance_result),
            parse_user_profile(profile_result),
        )
        balance_err = validate_balance_for_task_publish(balance_view, budget)
        if balance_err:
            return g.finish(publish_balance_error_json(balance_err))
    except Exception as e:
        return g.finish(
            json.dumps({"success": False, "error": f"发布前余额校验失败：{e}"}, ensure_ascii=False),
        )

    payload = {
        "category_id": category_id,
        "title": title,
        "description": description,
        "location": location,
        "budget": budget,
        "deadline": deadline,
        "require_cert": require_cert or [],
    }
    try:
        result = await _req("POST", "applettask/publishtask", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if api_ok(result):
        data = result.get("data") or result.get("Data") or {}
        task_id = data.get("task_id") if isinstance(data, dict) else None
        return g.finish(
            json.dumps(
                {"success": True, "task_id": task_id, "message": f"众包任务发布成功！任务ID: {task_id}"},
                ensure_ascii=False,
            ),
        )
    return g.finish(
        json.dumps({"success": False, "error": api_message(result, "发布失败")}, ensure_ascii=False),
    )


@mcp.tool()
async def get_task_orders(status: str = "all", page: int = 1) -> str:
    """查询众包任务订单列表。

    对应接口: appletorder/getorderlist (POST)

    Args:
        status: 状态筛选
        page: 页码
    """
    payload = {"status": status, "page": page, "page_size": 10}
    try:
        result = await _req("POST", "appletorder/getorderlist", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    orders = api_list(result)
    if not orders:
        return "暂无相关任务订单。"

    lines = ["任务订单列表：\n"]
    for o in orders:
        lines.append(format_task_order_item(o))
    return "\n".join(lines)


@mcp.tool()
async def accept_delivery(
    task_id: str,
    is_accept: bool,
    remark: str = "",
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """验收任务交付物（通过/驳回）。

    对应接口: appletorder/merchantcheck (POST)

    ⚠️ 调用约束：须展示任务与交付摘要，由企业用户明确确认通过或驳回后再调用；
    须 user_confirmed=true。

    Args:
        task_id: 任务ID
        is_accept: True=通过验收，False=驳回
        remark: 验收备注
        user_confirmed: 必须为 true
        confirmation_summary: 可选，用户确认原话摘要
    """
    g = WriteGate(
        "accept_delivery",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        task_id=task_id,
        is_accept=is_accept,
        remark=remark,
    )
    if g.blocked:
        return g.blocked

    payload = {"task_id": task_id, "is_accept": is_accept, "remark": remark}
    try:
        result = await _req("POST", "appletorder/merchantcheck", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if api_ok(result):
        action = "✅ 已通过验收" if is_accept else "❌ 已驳回"
        return g.finish(f"{action}，任务ID: {task_id}")
    return g.finish(
        json.dumps({"success": False, "error": api_message(result, "验收失败")}, ensure_ascii=False),
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

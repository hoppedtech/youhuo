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
from tools.youhuo_env import task_base_url

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

mcp = FastMCP("youhuo-task-api")

TASK_URL = task_base_url()


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


@mcp.tool()
async def get_task_categories() -> str:
    """获取众包任务分类目录。

    对应接口: applettask/getcaterogyinfo (GET)
    """
    try:
        result = await _req("GET", "applettask/getcaterogyinfo")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    cats = result.get("data", [])
    if not cats:
        return "暂无任务分类数据。"
    lines = ["任务分类："]
    for c in cats:
        lines.append(f"  • [{c.get('id', '—')}] {c.get('name', '—')}")
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
) -> str:
    """发布众包任务到有活平台。

    对应接口: applettask/publishtask (POST)

    Args:
        category_id: 任务类别ID（可通过 get_task_categories 获取）
        title: 任务标题
        description: 任务描述和要求
        location: 任务地点
        budget: 预算金额（元）
        deadline: 截止日期，格式 YYYY-MM-DD
        require_cert: 所需资质证书列表
    """
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
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        task_id = result.get("data", {}).get("task_id")
        return json.dumps(
            {"success": True, "task_id": task_id, "message": f"众包任务发布成功！任务ID: {task_id}"},
            ensure_ascii=False,
        )
    return json.dumps({"success": False, "error": result.get("message", "发布失败")}, ensure_ascii=False)


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

    orders = result.get("data", {}).get("list", [])
    if not orders:
        return "暂无相关任务订单。"

    lines = ["任务订单列表：\n"]
    for o in orders:
        lines.append(
            f"📦 [{o.get('task_id')}] {o.get('title')} | "
            f"¥{o.get('amount')} | {o.get('status_desc', o.get('statusDesc', '—'))}"
        )
    return "\n".join(lines)


@mcp.tool()
async def accept_delivery(task_id: str, is_accept: bool, remark: str = "") -> str:
    """验收任务交付物（通过/驳回）。

    对应接口: appletorder/merchantcheck (POST)

    Args:
        task_id: 任务ID
        is_accept: True=通过验收，False=驳回
        remark: 验收备注
    """
    payload = {"task_id": task_id, "is_accept": is_accept, "remark": remark}
    try:
        result = await _req("POST", "appletorder/merchantcheck", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        action = "✅ 已通过验收" if is_accept else "❌ 已驳回"
        return f"{action}，任务ID: {task_id}"
    return json.dumps({"success": False, "error": result.get("message", "验收失败")}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")

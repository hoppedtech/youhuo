"""有活平台用户画像 MCP Server。

提供用户信息、实人认证状态、技能标签、可工作时间等基础能力。
job-seeker Skill 报名前依赖本 Server 检查认证状态。
"""
import os
import sys
import json
import httpx
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared_token_store import auth_store
from tools.youhuo_env import applet_base_url
from tools.api_response import (
    allow_orders,
    api_data,
    api_list,
    api_message,
    api_ok,
    format_week_day,
    normalize_week_day,
    parse_auth_info,
    parse_work_preferences,
    profile_phone,
    profile_skill_names,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

mcp = FastMCP("youhuo-profile-api")

BASE_URL = applet_base_url()


def _mask_phone(phone: str) -> str:
    if not phone or len(phone) < 7:
        return "未绑定"
    return re.sub(r"(\d{3})\d{4}(\d{4})", r"\1****\2", str(phone))


def _mask_name(name: str) -> str:
    if not name:
        return "未命名"
    if len(name) <= 1:
        return name
    return name[0] + "*" * (len(name) - 1)


async def _req(method: str, path: str, **kwargs):
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception(
            "未授权：请先调用 youhuo-c-api.create_auth_session() "
            "完成扫码授权，再执行此操作"
        )
    token = token_info["token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-USER_ROLE": "1",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _get_basic_info() -> dict:
    result = await _req("GET", "Personal/getbasicinfo")
    return api_data(result)


@mcp.tool()
async def get_user_profile() -> str:
    """获取零工用户画像（脱敏展示，不含完整手机号）。

    对应接口: Personal/getbasicinfo (GET)
    """
    try:
        data = await _get_basic_info()
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if not data:
        return "未获取到用户资料。"

    auth_status, auth_desc, auth_passed = parse_auth_info(data)
    work_prefs = parse_work_preferences(data)

    profile = {
        "name": _mask_name(data.get("name", "")),
        "phone": _mask_phone(profile_phone(data)),
        "auth_status": auth_desc,
        "auth_passed": auth_passed,
        "star": data.get("star"),
        "finish_count": data.get("finishCount", data.get("finish_count", 0)),
        "city": data.get("city") or data.get("residence_address") or "未设置",
        "skills": profile_skill_names(data),
        "categories": data.get("categories", []),
        **work_prefs,
    }
    return json.dumps(profile, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_work_preferences() -> str:
    """查询零工可工作时间偏好（期望工作日、时间段等）。

    对应接口: Personal/getbasicinfo (GET)
    """
    try:
        data = await _get_basic_info()
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if not data:
        return "未获取到可工作时间偏好。"

    prefs = parse_work_preferences(data)
    prefs["summary"] = (
        f"期望工作日：{prefs['week_day_desc']}\n"
        f"期望时间段：{prefs['work_time_slot']}\n"
        f"可工作时长：{prefs['work_length']}"
    )
    return json.dumps(prefs, ensure_ascii=False, indent=2)


@mcp.tool()
async def update_work_preferences(
    week_day: str = "",
    work_time_slot: str = "",
    work_length: str = "",
    salary_expectation: float = 0,
    benefit: str = "",
) -> str:
    """更新零工可工作时间偏好。

    对应接口: Personal/savebasicinfo (POST)

    Args:
        week_day: 期望工作日。支持「周末」「周六,周日」或「6,7」（1=周一 … 7=周日）
        work_time_slot: 期望时间段，如「全天」「上午」「下午」「白班」「夜班」
        work_length: 可工作时长描述，如「周末」「4小时」
        salary_expectation: 期望薪资（元），0 表示不修改
        benefit: 期望福利，如「通讯补贴」；空字符串表示不修改

    Returns:
        更新后的可工作时间偏好
    """
    payload: dict = {}
    if week_day:
        try:
            payload["week_day"] = normalize_week_day(week_day)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    if work_time_slot:
        payload["work_time_slot"] = work_time_slot.strip()
    if work_length:
        payload["work_length"] = work_length.strip()
    if salary_expectation > 0:
        payload["salary_expectation"] = salary_expectation
    if benefit:
        payload["benefit"] = benefit.strip()

    if not payload:
        return json.dumps(
            {"success": False, "error": "请至少提供一项要更新的偏好字段"},
            ensure_ascii=False,
        )

    try:
        result = await _req("POST", "Personal/savebasicinfo", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if not api_ok(result):
        return json.dumps(
            {"success": False, "error": api_message(result, "更新失败")},
            ensure_ascii=False,
        )

    try:
        data = await _get_basic_info()
    except Exception as e:
        return json.dumps(
            {
                "success": True,
                "message": "更新成功，但读取最新资料失败",
                "error": str(e),
            },
            ensure_ascii=False,
        )

    prefs = parse_work_preferences(data)
    return json.dumps(
        {
            "success": True,
            "message": "可工作时间偏好已更新",
            **prefs,
            "summary": (
                f"期望工作日：{prefs['week_day_desc']}\n"
                f"期望时间段：{prefs['work_time_slot']}\n"
                f"可工作时长：{prefs['work_length']}"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def get_auth_status() -> str:
    """查询实人认证状态（报名接单前必查）。

    对应接口: Personal/getbasicinfo (GET)
    """
    try:
        data = await _get_basic_info()
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if not data:
        return json.dumps(
            {"success": False, "error": "未获取到用户资料", "auth_status": "未知", "auth_passed": False},
            ensure_ascii=False,
        )

    auth_status, auth_desc, auth_passed = parse_auth_info(data)

    response = {
        "auth_status": auth_desc,
        "auth_passed": auth_passed,
        "can_apply": auth_passed,
    }
    if auth_status == 0:
        response["guide"] = "请前往有活小程序完成实人认证：我的 → 实名认证"
    elif auth_status == 1:
        response["guide"] = "实名认证审核中，请耐心等待或前往小程序查看进度"

    return json.dumps(response, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_skill_tags(keyword: str = "") -> str:
    """获取平台可选技能标签列表。

    对应接口: Personal/GetSkills (GET)

    Args:
        keyword: 技能关键词筛选
    """
    path = f"Personal/GetSkills?keyword={keyword}" if keyword else "Personal/GetSkills"
    try:
        result = await _req("GET", path)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    skills = api_list(result)
    if not skills:
        return "未找到相关技能标签。" if keyword else "暂无技能标签数据。"

    names = [s.get("name", s.get("skillName", "—")) for s in skills[:30]]
    return "可选技能标签：\n" + " | ".join(names)


@mcp.tool()
async def check_apply_eligibility(job_id: int = 0) -> str:
    """检查用户是否具备接单/报名权限。

    对应接口: Credential/IsAllowOrders (GET)

    Args:
        job_id: 岗位ID，0 表示通用检查
    """
    path = f"Credential/IsAllowOrders?jobId={job_id}" if job_id else "Credential/IsAllowOrders"
    try:
        result = await _req("GET", path)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    allowed = allow_orders(result)
    response = {"allowed": allowed if allowed is not None else False, "job_id": job_id or None}

    if allowed is True:
        return json.dumps(response, ensure_ascii=False, indent=2)

    if allowed is False:
        response["guide"] = (
            "您当前不具备接单权限。可能原因：未完成实名认证、未绑定手机号或账号被限制。"
            "请前往有活小程序完善个人信息。"
        )
    else:
        response["guide"] = api_message(result) or "无法确认接单权限，请稍后重试或在小程序中查看。"

    return json.dumps(response, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")

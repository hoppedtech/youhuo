"""岗位/任务详情：按类型路由不同接口并格式化输出。"""

from __future__ import annotations

import re
from typing import Awaitable, Callable

from tools.api_response import api_data, api_message, api_ok, format_job_detail, mask_phone
from tools.job_recommend import (
    JOB_TYPE_CROWD,
    JOB_TYPE_HOURLY,
    JOB_TYPE_PIECE,
    JOB_TYPE_POSITION,
    classify_jd_job,
    job_location_text,
    job_salary_text,
    job_title,
)

RequestFn = Callable[..., Awaitable[dict]]

JOB_TYPE_ALIASES = {
    "小时工": JOB_TYPE_HOURLY,
    "hourly": JOB_TYPE_HOURLY,
    "计件工": JOB_TYPE_PIECE,
    "计件": JOB_TYPE_PIECE,
    "piece": JOB_TYPE_PIECE,
    "众包工": JOB_TYPE_CROWD,
    "众包": JOB_TYPE_CROWD,
    "crowd": JOB_TYPE_CROWD,
    "岗位": JOB_TYPE_POSITION,
    "普通岗位": JOB_TYPE_POSITION,
    "长期招": JOB_TYPE_POSITION,
    "position": JOB_TYPE_POSITION,
}


def normalize_job_type(job_type: str) -> str:
    text = (job_type or "").strip()
    if not text:
        return ""
    return JOB_TYPE_ALIASES.get(text, text)


def _plain_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    return re.sub(r"<[^>]+>", "", text).strip()


def _crowd_service_time(data: dict) -> str:
    if data.get("expected_date_str"):
        return str(data["expected_date_str"])
    if data.get("expected_time_str"):
        return str(data["expected_time_str"])
    begin = data.get("expected_begin_time") or ""
    end = data.get("expected_end_time") or ""
    if begin and end and begin != "00:00:00":
        return f"{begin[:5]}-{end[:5]}"
    return "待定"


def _crowd_settlement(data: dict) -> str:
    amount = data.get("settle_amount_str") or data.get("settle_amount")
    unit = data.get("unit_name") or ""
    quantity = data.get("quantity")
    if amount is None:
        return "薪资面议"
    if quantity and unit:
        return f"¥{amount}/{unit} × {quantity}"
    if unit:
        return f"¥{amount}/{unit}"
    return f"¥{amount}"


def format_crowd_task_detail(data: dict, task_id: int | None = None) -> str:
    item_id = task_id or data.get("id") or data.get("taskId")
    title = data.get("spu_name") or data.get("service_project_name") or job_title(data) or "未知任务"
    project = data.get("service_project_name") or ""
    location = (
        data.get("task_address")
        or data.get("task_address_str")
        or job_location_text(data)
        or data.get("city")
        or "未填写"
    )
    remark = _plain_text(data.get("service_remark") or "")
    desc = _plain_text(data.get("spu_description") or data.get("task_requirement") or "")
    requirement = _plain_text(data.get("work_require") or data.get("task_requirement") or "")

    lines = [
        f"📋 【{JOB_TYPE_CROWD}】{title}\n",
        f"任务ID: {item_id}",
        f"订单编号: {data.get('order_code') or '—'}",
        f"💰 结算: {_crowd_settlement(data)}",
        f"📍 地点: {location}",
        f"📅 服务时间: {_crowd_service_time(data)}",
    ]
    if project and project != title:
        lines.append(f"🏷️ 服务项目: {project}")
    if data.get("delivery_deadline"):
        lines.append(f"⏳ 交付截止: {data['delivery_deadline']}")
    if requirement:
        lines.append(f"✅ 基本要求: {requirement}")
    if desc:
        lines.append(f"📝 任务说明:\n{desc}")
    if remark:
        lines.append(f"📋 服务备注:\n{remark}")
    phone = mask_phone(data.get("customer_phone") or "")
    if phone:
        lines.append(f"📞 联系方式: {phone}")
    return "\n".join(lines)


def format_jd_job_detail(data: dict, job_id: int | None = None, job_type: str = "") -> str:
    from tools.job_schedule import format_schedules_section

    resolved_type = job_type or classify_jd_job(data)
    text = format_job_detail(data, job_id)
    if f"【{resolved_type}】" in text:
        base = text
    else:
        base = text.replace("📋 ", f"📋 【{resolved_type}】", 1)
    schedules_text = format_schedules_section(data)
    return base + schedules_text if schedules_text else base


async def _fetch_jd_detail(req: RequestFn, job_id: int) -> dict:
    result = await req("GET", f"Job/JobDetail?jobId={job_id}")
    if not api_ok(result):
        raise ValueError(api_message(result, f"岗位 {job_id} 不存在或已下架。"))
    data = api_data(result)
    if not data:
        raise ValueError(f"岗位 {job_id} 不存在或已下架。")
    return data


async def _fetch_crowd_detail(req: RequestFn, task_id: int) -> dict:
    result = await req("POST", "HoppedTask/GetHoppedTaskDetail", json={"id": task_id})
    if not api_ok(result):
        raise ValueError(api_message(result, f"任务 {task_id} 不存在或已下架。"))
    data = api_data(result)
    if not data:
        raise ValueError(f"任务 {task_id} 不存在或已下架。")
    return data


async def _try_crowd_detail(req: RequestFn, task_id: int) -> dict | None:
    try:
        result = await req("POST", "HoppedTask/GetHoppedTaskDetail", json={"id": task_id})
    except Exception:
        return None
    if not api_ok(result):
        return None
    data = api_data(result)
    if not isinstance(data, dict):
        return None
    if data.get("spu_name") or data.get("order_code") or data.get("service_project_name"):
        return data
    return None


async def fetch_and_format_job_detail(
    req: RequestFn,
    job_id: int,
    job_type: str = "",
) -> str:
    explicit = normalize_job_type(job_type)

    if explicit == JOB_TYPE_CROWD:
        data = await _fetch_crowd_detail(req, job_id)
        return format_crowd_task_detail(data, job_id)

    if explicit in (JOB_TYPE_HOURLY, JOB_TYPE_PIECE, JOB_TYPE_POSITION):
        data = await _fetch_jd_detail(req, job_id)
        return format_jd_job_detail(data, job_id, explicit)

    crowd = await _try_crowd_detail(req, job_id)
    if crowd:
        return format_crowd_task_detail(crowd, job_id)

    data = await _fetch_jd_detail(req, job_id)
    return format_jd_job_detail(data, job_id)

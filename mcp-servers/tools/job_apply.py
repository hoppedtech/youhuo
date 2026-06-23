"""岗位/任务报名：按 product_type 路由不同接口。"""

from __future__ import annotations

from typing import Awaitable, Callable

from tools.api_response import api_data, api_message, api_ok
from tools.job_detail import normalize_job_type
from tools.job_recommend import JOB_TYPE_CROWD, JOB_TYPE_HOURLY, JOB_TYPE_PIECE

RequestFn = Callable[..., Awaitable[dict]]

SCHEDULE_PRODUCT_TYPES = {4, 6}  # 小时工、计件工


def parse_schedule_ids(schedule_ids: str | list[int] | None) -> list[int]:
    if not schedule_ids:
        return []
    if isinstance(schedule_ids, list):
        return [int(x) for x in schedule_ids if x is not None]
    ids: list[int] = []
    for token in str(schedule_ids).replace("，", ",").split(","):
        token = token.strip()
        if token.isdigit():
            ids.append(int(token))
    return ids


def build_schedule_info(schedule_ids: list[int]) -> list[dict]:
    return [
        {
            "schedule_id": schedule_id,
            "add_price": 0,
            "multi_days_batch_no": "",
            "is_user_multi_days": 0,
            "scheduleIds": None,
        }
        for schedule_id in schedule_ids
    ]


async def fetch_job_product_type(req: RequestFn, job_id: int) -> int | None:
    result = await req("GET", f"Job/JobDetail?jobId={job_id}")
    if not api_ok(result):
        return None
    data = api_data(result) or {}
    product_type = data.get("product_type")
    return int(product_type) if product_type is not None else None


def resolve_product_type(
    product_type: int | None,
    job_type: str = "",
) -> int | None:
    explicit = normalize_job_type(job_type)
    if explicit == JOB_TYPE_CROWD:
        return None
    if product_type is not None:
        return product_type
    if explicit == JOB_TYPE_HOURLY:
        return 4
    if explicit == JOB_TYPE_PIECE:
        return 6
    if explicit in ("岗位", "普通岗位", "长期招"):
        return 5
    return product_type


async def apply_position_job(
    req: RequestFn,
    job_id: int,
    *,
    skill_ids: list | None = None,
) -> dict:
    payload = {"job_id": job_id, "skill_ids": skill_ids or []}
    result = await req("POST", "Personal/jobentry", json=payload)
    return result


async def apply_schedule_job(
    req: RequestFn,
    job_id: int,
    schedule_info: list[dict],
    *,
    skill_ids: list | None = None,
    city: str = "",
    is_confirm: bool = False,
) -> dict:
    payload = {
        "job_id": job_id,
        "skill_ids": skill_ids or [],
        "schedule_info": schedule_info,
        "city": city,
        "is_confirm": is_confirm,
    }
    result = await req("POST", "Job/EntryJob", json=payload)
    return result


def format_apply_success(job_id: int, message: str = "报名成功！") -> str:
    import json

    return json.dumps(
        {
            "success": True,
            "job_id": job_id,
            "message": message,
            "note": "企业方确认后，您将收到通知。可在「我的订单」中查看进度。",
        },
        ensure_ascii=False,
    )


def format_apply_failure(message: str) -> str:
    import json

    return json.dumps({"success": False, "error": message}, ensure_ascii=False)


def interpret_schedule_entry_result(result: dict, job_id: int) -> str:
    if not api_ok(result):
        return format_apply_failure(api_message(result, "报名失败"))

    data = api_data(result)
    if isinstance(data, dict):
        schedules = data.get("schedules") or []
        if schedules:
            return format_apply_success(job_id, api_message(result, "报名成功！"))
        conflict = data.get("conflict_schedule") or []
        invalid = data.get("invalid_schedule") or []
        if conflict:
            reason = conflict[0].get("fail_reason") or "班次时间冲突"
            return format_apply_failure(reason)
        if invalid:
            reason = invalid[0].get("fail_reason") or "班次已失效"
            return format_apply_failure(reason)
        if data.get("errcode"):
            return format_apply_failure(str(data.get("fail_reason") or data.get("errcode")))
    if api_message(result):
        return format_apply_success(job_id, api_message(result, "报名成功！"))
    return format_apply_success(job_id)


async def apply_job_for_detail(
    req: RequestFn,
    job_id: int,
    *,
    job_type: str = "",
    schedule_ids: str | list[int] | None = None,
    city: str = "",
    skill_ids: list | None = None,
    require_complete_info: bool = True,
    profile: dict | None = None,
) -> str:
    if require_complete_info:
        from tools.job_entry import (
            assess_apply_readiness,
            fetch_entry_job_detail,
            fetch_job_detail as fetch_job_detail_data,
            format_readiness_blocker,
        )

        job_detail = await fetch_job_detail_data(req, job_id)
        entry_detail = await fetch_entry_job_detail(req, job_id)
        profile_data = profile or {}
        report = assess_apply_readiness(
            job_id=job_id,
            job_detail=job_detail,
            entry_detail=entry_detail,
            profile=profile_data,
            schedule_ids=parse_schedule_ids(schedule_ids),
            skill_ids=skill_ids or [],
        )
        if not report["ready"]:
            return format_readiness_blocker(report)

    product_type = resolve_product_type(await fetch_job_product_type(req, job_id), job_type)
    if product_type is None and normalize_job_type(job_type) == JOB_TYPE_CROWD:
        return format_apply_failure("众包/计件抢单任务请使用抢单接口，当前 MCP 暂不支持直接报名。")

    if product_type in SCHEDULE_PRODUCT_TYPES:
        ids = parse_schedule_ids(schedule_ids)
        if not ids:
            return format_apply_failure(
                "该岗位为小时工/计件工，报名前需选择班次。"
                "请先调用 get_job_detail 查看可选班次，再通过 schedule_ids 传入班次 ID（逗号分隔）。"
            )
        result = await apply_schedule_job(
            req,
            job_id,
            build_schedule_info(ids),
            skill_ids=skill_ids,
            city=city,
        )
        return interpret_schedule_entry_result(result, job_id)

    result = await apply_position_job(req, job_id, skill_ids=skill_ids)
    if api_ok(result):
        return format_apply_success(job_id, api_message(result, "报名成功！"))
    return format_apply_failure(api_message(result, "报名失败"))

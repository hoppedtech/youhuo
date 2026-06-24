"""岗位/任务报名：按 product_type 路由不同接口。"""

from __future__ import annotations

from typing import Awaitable, Callable

from tools.api_response import api_data, api_message, api_ok
from tools.job_detail import normalize_job_type
from tools.job_recommend import JOB_TYPE_CROWD, JOB_TYPE_HOURLY, JOB_TYPE_PIECE

RequestFn = Callable[..., Awaitable[dict]]

SCHEDULE_PRODUCT_TYPES = {4, 6}  # 小时工、计件工
STANDBY_PRODUCT_TYPES = {4, 5, 6}  # 小程序候补入口覆盖的类型


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


def format_apply_failure(message: str, *, hint: str = "") -> str:
    import json

    payload: dict = {"success": False, "error": message}
    if hint:
        payload["hint"] = hint
    return json.dumps(payload, ensure_ascii=False)


def _standby_hint(job_id: int) -> str:
    return (
        f"该班次/岗位已报满，若详情中班次状态为「已报满(可候补)」，"
        f"请调用 apply_job_standby(job_id={job_id}, schedule_id=班次ID)。"
    )


def build_standby_payload(
    job_id: int,
    schedule_id: int,
    *,
    multi_schedule_ids: list[int] | None = None,
    skill_ids: list | None = None,
) -> dict:
    payload: dict = {"job_id": job_id, "schedule_id": schedule_id}
    if multi_schedule_ids:
        payload["scheduleIds"] = multi_schedule_ids
    if skill_ids:
        payload["skill_ids"] = skill_ids
    return payload


async def apply_job_standby(
    req: RequestFn,
    job_id: int,
    schedule_id: int,
    *,
    multi_schedule_ids: list[int] | None = None,
    skill_ids: list | None = None,
) -> dict:
    payload = build_standby_payload(
        job_id,
        schedule_id,
        multi_schedule_ids=multi_schedule_ids,
        skill_ids=skill_ids,
    )
    return await req("POST", "Job/EntryJobBackUp", json=payload)


async def cancel_job_standby(
    req: RequestFn,
    job_id: int,
    schedule_id: int,
    *,
    multi_schedule_ids: list[int] | None = None,
) -> dict:
    payload: dict = {"job_id": job_id, "schedule_id": schedule_id}
    if multi_schedule_ids:
        payload["scheduleIds"] = multi_schedule_ids
    return await req("POST", "Job/CancelEntryJobBackUp", json=payload)


def interpret_standby_result(result: dict, job_id: int, schedule_id: int) -> str:
    import json

    if not api_ok(result):
        msg = api_message(result, "候补失败")
        hint = _standby_hint(job_id) if "报满" in msg else ""
        return format_apply_failure(msg, hint=hint)

    data = api_data(result)
    if data == -10 or str(data) == "-10":
        return format_apply_failure("候补失败：该岗位名额已满且候补通道已关闭。")

    if isinstance(data, dict):
        failed = data.get("faileSchedules") or data.get("failSchedules") or []
        if failed:
            reason = failed[0].get("fail_reason") or "候补失败"
            return format_apply_failure(reason, hint=_standby_hint(job_id))

    return json.dumps(
        {
            "success": True,
            "job_id": job_id,
            "schedule_id": schedule_id,
            "message": api_message(result, "候补成功"),
            "note": "名额释放后将按候补顺序通知，可在「我的订单」查看候补中班次。",
        },
        ensure_ascii=False,
    )


def interpret_cancel_standby_result(result: dict, job_id: int, schedule_id: int) -> str:
    import json

    if not api_ok(result):
        return format_apply_failure(api_message(result, "取消候补失败"))
    return json.dumps(
        {
            "success": True,
            "job_id": job_id,
            "schedule_id": schedule_id,
            "message": api_message(result, "已取消候补"),
        },
        ensure_ascii=False,
    )


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
            reason = str(data.get("fail_reason") or data.get("errcode"))
            hint = _standby_hint(job_id) if "报满" in reason else ""
            return format_apply_failure(reason, hint=hint)
    raw = result.get("Data")
    if raw == "1" or raw == 1:
        return format_apply_failure(
            "该岗位已报满，当前为抢单/捡漏阶段，请对可候补班次提交候补。",
            hint=_standby_hint(job_id),
        )
    msg = api_message(result, "")
    if msg and "报满" in msg:
        return format_apply_failure(msg, hint=_standby_hint(job_id))
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
    msg = api_message(result, "报名失败")
    hint = ""
    if "报满" in msg:
        hint = (
            "普通订阅岗位报满后通常无法候补；"
            "小时工/计件工 PK 岗位请查看 get_job_detail 中 status=8 的班次并调用 apply_job_standby。"
        )
    return format_apply_failure(msg, hint=hint)

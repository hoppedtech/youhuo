"""班次状态解析（与小程序 B 端 pages/hire-labour/classes、classes-detail 一致）。"""

from __future__ import annotations

# recruitWorkingSchedule/list — pages/hire-labour/classes/index.vue statusList
# 请求参数为 type + status（status 取 tab.id）
SCHEDULE_LIST_TABS: dict[str, dict] = {
    "pending_confirm": {"type": 2, "status": 0, "label": "待确认"},
    "recruiting": {"type": 1, "status": 1, "label": "招募中"},
    "in_progress": {"type": 1, "status": 3, "label": "进行中"},
    "completed": {"type": 1, "status": 4, "label": "已完成"},
    "closed": {"type": 1, "status": 5, "label": "已关闭"},
    "all": {"type": 1, "status": None, "label": "全部班次"},
}

SCHEDULE_LIST_TAB_ALIASES: dict[str, str] = {
    "待确认": "pending_confirm",
    "招募中": "recruiting",
    "进行中": "in_progress",
    "已完成": "completed",
    "已关闭": "closed",
    "全部": "all",
    "全部班次": "all",
}

# recruitWorkingScheduleDetail/list — classes-detail.vue tabList
# 请求参数为 type + status（status 取 tab.status；待处理 tab 无 status，传 0）
SCHEDULE_DETAIL_TABS: dict[str, dict] = {
    "pending": {"type": 2, "status": 0, "label": "待处理"},
    "registered": {"type": 1, "status": 1, "label": "已报名"},
    "waiting_service": {"type": 1, "status": 2, "label": "待服务"},
    "in_service": {"type": 1, "status": 3, "label": "服务中"},
    "wait_confirm": {"type": 1, "status": 6, "label": "待确认"},
    "completed": {"type": 1, "status": 4, "label": "已完成"},
    "closed": {"type": 1, "status": 5, "label": "已关闭"},
}

SCHEDULE_DETAIL_TAB_ALIASES: dict[str, str] = {
    "待处理": "pending",
    "已报名": "registered",
    "待服务": "waiting_service",
    "服务中": "in_service",
    "待确认": "wait_confirm",
    "已完成": "completed",
    "已关闭": "closed",
}

# C 端抢班状态（all-classes 候选人视角）
SCHEDULE_STATUS_LABELS: dict[int, str] = {
    1: "可抢",
    2: "已报名",
    3: "进行中",
    4: "已完成",
    5: "已关闭",
    6: "候补中",
    7: "抢单中",
    8: "已报满(可候补)",
    9: "已报满",
}

# B 端班次列表卡片 status（detail.vue / all-classes.vue）
B_SCHEDULE_ROW_STATUS_LABELS: dict[int, str] = {
    1: "招募中",
    2: "待出勤",
    3: "进行中",
    4: "已完成",
    5: "已关闭",
}


def _resolve_tab_key(tab: str, *, aliases: dict[str, str], tabs: dict[str, dict]) -> str:
    raw = (tab or "").strip()
    if not raw:
        return "all" if tabs is SCHEDULE_LIST_TABS else "pending"
    lowered = raw.lower().replace("-", "_")
    if lowered in tabs:
        return lowered
    if raw in aliases:
        return aliases[raw]
    if raw in tabs:
        return raw
    raise ValueError(f"未知 tab: {tab}")


def resolve_schedule_list_tab(tab: str) -> dict:
    key = _resolve_tab_key(tab, aliases=SCHEDULE_LIST_TAB_ALIASES, tabs=SCHEDULE_LIST_TABS)
    return {"key": key, **SCHEDULE_LIST_TABS[key]}


def resolve_schedule_detail_tab(tab: str) -> dict:
    key = _resolve_tab_key(tab, aliases=SCHEDULE_DETAIL_TAB_ALIASES, tabs=SCHEDULE_DETAIL_TABS)
    return {"key": key, **SCHEDULE_DETAIL_TABS[key]}


def build_schedule_list_payload(
    *,
    list_tab: str = "all",
    list_type: int = 0,
    list_status: int = -1,
    job_id: int = 0,
    product_type: int = 0,
    page: int = 1,
    page_size: int = 20,
) -> tuple[dict, str]:
    """构造 recruitWorkingSchedule/list 请求体，返回 (payload, tab_label)。"""
    if list_type > 0:
        api_type = list_type
        api_status = list_status if list_status >= 0 else None
        label = f"type={api_type}" + (f", status={api_status}" if api_status is not None else "")
    else:
        tab = resolve_schedule_list_tab(list_tab)
        api_type = tab["type"]
        api_status = tab["status"]
        label = tab["label"]

    payload: dict = {"type": api_type, "pageNum": page, "pageSize": page_size}
    if api_status is not None:
        payload["status"] = api_status
    if job_id > 0:
        payload["jobId"] = job_id
    if product_type in (4, 6):
        payload["productType"] = product_type
    return payload, label


def build_schedule_detail_payload(
    schedule_id: int,
    *,
    detail_tab: str = "pending",
    detail_type: int = 0,
    detail_status: int = -1,
    product_type: int = 0,
    page: int = 1,
    page_size: int = 20,
) -> tuple[dict, str]:
    """构造 recruitWorkingScheduleDetail/list 请求体，返回 (payload, tab_label)。"""
    if schedule_id <= 0:
        raise ValueError("schedule_id 必须 > 0")

    if detail_type > 0:
        api_type = detail_type
        api_status = detail_status if detail_status >= 0 else 0
        label = f"type={api_type}, status={api_status}"
    else:
        tab = resolve_schedule_detail_tab(detail_tab)
        api_type = tab["type"]
        api_status = tab["status"]
        label = tab["label"]

    payload: dict = {
        "type": api_type,
        "status": api_status,
        "workScheduleId": schedule_id,
        "pageNum": page,
        "pageSize": page_size,
    }
    if product_type in (4, 6):
        payload["productType"] = product_type
    return payload, label


def schedule_status_label(status: int | None) -> str:
    if status is None:
        return "未知"
    return SCHEDULE_STATUS_LABELS.get(int(status), str(status))


def b_schedule_row_status_label(status: int | None) -> str:
    if status is None:
        return "未知"
    return B_SCHEDULE_ROW_STATUS_LABELS.get(int(status), str(status))


def format_b_schedule_list_item(schedule: dict) -> str:
    """格式化 B 端 recruitWorkingSchedule/list 单条记录。"""
    sid = schedule.get("id") or schedule.get("scheduleId") or "—"
    job_id = schedule.get("jobId")
    title = schedule.get("positionTitle") or schedule.get("positionName") or ""
    date = schedule.get("jobDate") or schedule.get("workDate") or ""
    start = schedule.get("spanStartTime") or schedule.get("startTime") or ""
    end = schedule.get("spanEndTime") or schedule.get("endTime") or ""
    period = f"{start}-{end}".strip("-")
    status = b_schedule_row_status_label(schedule.get("status"))
    need = schedule.get("needCount") if schedule.get("needCount") is not None else schedule.get("headcount")
    registered = schedule.get("numberOfRegistrations")
    if registered is None:
        registered = schedule.get("arriveCount", 0)
    pending = schedule.get("pendingConfirmationQuantity") or 0
    product_type = schedule.get("productType")
    pt_label = {4: "小时工", 6: "计件工"}.get(int(product_type or 0), "")

    parts = [f"📅 [{sid}]"]
    if job_id:
        parts.append(f"岗位{job_id}")
    if title:
        parts.append(title)
    if date:
        parts.append(str(date))
    if period:
        parts.append(period)
    if pt_label:
        parts.append(pt_label)
    parts.append(status)
    if need is not None:
        reg_text = f"报名{registered}" if registered is not None else ""
        parts.append(f"需{need}人{('/' + reg_text) if reg_text else ''}")
    if pending > 0:
        parts.append(f"⚠️待确认{pending}人")
    amount = schedule.get("allAmount")
    if amount is not None:
        parts.append(f"¥{amount}")
    return " | ".join(parts)


def format_b_schedule_detail_item(order: dict) -> str:
    """格式化 B 端 recruitWorkingScheduleDetail/list 单条订单（零工）。"""
    detail_id = order.get("id") or order.get("scheduleDetailId") or "—"
    name = order.get("userName") or order.get("workerName") or "未知"
    status = order.get("statusDesc") or order.get("status")
    hours = order.get("timeLength") or order.get("workHours")
    labor = order.get("laborAmount") or order.get("amount")
    total = order.get("allMoney")
    on_time = order.get("onTimeFormatTime") or order.get("onTime")
    off_time = order.get("offTimeFormatTime") or order.get("offTime")

    parts = [f"👤 [{detail_id}] {name}"]
    if status is not None:
        parts.append(f"状态:{status}")
    if on_time or off_time:
        parts.append(f"打卡 {on_time or '—'}-{off_time or '—'}")
    if hours is not None:
        parts.append(f"工时{hours}h")
    if labor is not None:
        parts.append(f"工钱¥{labor}")
    if total is not None:
        parts.append(f"合计¥{total}")
    return " | ".join(parts)


def format_b_schedule_list_header(
    tab_label: str,
    total: int,
    *,
    job_id: int = 0,
    product_type: int = 0,
    page: int = 1,
    page_size: int = 20,
    shown: int = 0,
) -> str:
    filters: list[str] = []
    if job_id > 0:
        filters.append(f"岗位{job_id}")
    if product_type in (4, 6):
        filters.append({4: "小时工", 6: "计件工"}[product_type])
    filter_text = f"（{' · '.join(filters)}）" if filters else ""
    page_hint = ""
    if total > shown:
        page_hint = f"，当前第{page}页/{page_size}条"
    return f"{tab_label}（共{total}条{filter_text}{page_hint}）：\n"


def format_b_schedule_detail_header(
    schedule_id: int,
    tab_label: str,
    total: int,
    *,
    shown: int = 0,
    page: int = 1,
    page_size: int = 20,
) -> str:
    page_hint = ""
    if total > shown:
        page_hint = f"，当前第{page}页/{page_size}条"
    return f"班次 {schedule_id} · {tab_label}订单（共{total}条{page_hint}）：\n"


def parse_working_schedules(data: dict) -> list[dict]:
    raw = data.get("workingschedules") or data.get("workingSchedules") or []
    return raw if isinstance(raw, list) else []


def can_standby(schedule: dict) -> bool:
    """status=8 表示名额已满但开放候补。"""
    return int(schedule.get("status") or 0) == 8


def is_standby_active(schedule: dict) -> bool:
    return int(schedule.get("status") or 0) == 6


def format_schedule_line(schedule: dict) -> str:
    sid = schedule.get("id") or schedule.get("schedule_id")
    status = int(schedule.get("status") or 0)
    date = schedule.get("job_date_str") or schedule.get("work_date") or schedule.get("date") or ""
    start = schedule.get("span_start_time") or schedule.get("start_time") or ""
    end = schedule.get("span_end_time") or schedule.get("end_time") or ""
    period = f"{start}-{end}".strip("-")
    label = schedule_status_label(status)
    parts = [f"[{sid}]"]
    if date:
        parts.append(str(date))
    if period:
        parts.append(period)
    parts.append(label)
    return " | ".join(parts)


def format_schedules_section(data: dict) -> str:
    schedules = parse_working_schedules(data)
    if not schedules:
        return ""
    lines = ["\n📅 班次列表:"]
    standby_ids: list[str] = []
    for item in schedules:
        lines.append(f"  · {format_schedule_line(item)}")
        if can_standby(item):
            sid = item.get("id") or item.get("schedule_id")
            if sid is not None:
                standby_ids.append(str(sid))
    if standby_ids:
        lines.append(
            f"\n💡 以下班次已报满可候补: {', '.join(standby_ids)}"
            " → 调用 apply_job_standby(job_id, schedule_id=...)"
        )
    return "\n".join(lines)

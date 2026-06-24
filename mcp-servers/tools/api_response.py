"""有活平台 API 响应解析工具。

兼容 WebApiResult(ActionResult/Data/Message) 与 {code,data,message} 两种格式。
"""


def api_data(result: dict) -> dict:
    data = result.get("Data")
    if isinstance(data, dict):
        return data
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def api_list(result: dict) -> list:
    data = result.get("Data")
    if isinstance(data, list):
        return data
    data = result.get("data")
    if isinstance(data, list):
        return data

    payload = api_data(result)
    for key in ("ElementList", "list", "elementList", "jobList", "records"):
        items = payload.get(key)
        if isinstance(items, list):
            return items
    return []


def api_records(result: dict) -> list:
    """B 端 employ API 分页列表（data.records）。"""
    payload = api_data(result)
    records = payload.get("records")
    if isinstance(records, list):
        return records
    return api_list(result)


def api_search_lists(result: dict) -> tuple[list[dict], list[dict], int]:
    """解析 Job/GetSearchList 响应：岗位列表、订单列表、总数。"""
    payload = api_data(result)
    jobs = payload.get("jobList") or []
    orders = payload.get("orderList") or []
    if not isinstance(jobs, list):
        jobs = []
    if not isinstance(orders, list):
        orders = []
    total = payload.get("totalElement")
    if not isinstance(total, int):
        total = len(jobs) + len(orders)
    return jobs, orders, total


def api_total(result: dict) -> int:
    payload = api_data(result)
    for key in ("TotalElement", "total", "totalCount"):
        value = payload.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    return len(api_list(result))


def api_ok(result: dict) -> bool:
    for key in ("ActionResult", "actionResult"):
        action = result.get(key)
        if action is not None:
            return str(action) == "1"
    return result.get("code") == 200


def flatten_tree_nodes(
    nodes: list,
    *,
    id_key: str = "id",
    name_key: str = "name",
    children_key: str = "children",
    alt_id_keys: tuple[str, ...] = (),
    alt_name_keys: tuple[str, ...] = (),
    max_lines: int = 80,
) -> list[str]:
    """将树形分类展平为可读行。"""
    lines: list[str] = []

    def walk(items: list, depth: int = 0) -> None:
        if len(lines) >= max_lines:
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            node_id = item.get(id_key)
            for alt in alt_id_keys:
                node_id = node_id or item.get(alt)
            name = item.get(name_key)
            for alt in alt_name_keys:
                name = name or item.get(alt)
            prefix = "  " * (depth + 1)
            lines.append(f"{prefix}• [{node_id or '—'}] {name or '—'}")
            children = item.get(children_key) or []
            if isinstance(children, list) and children:
                walk(children, depth + 1)

    walk(nodes)
    return lines


def flatten_task_categories(data: dict) -> list[dict]:
    """众包任务分类：合并 exclusive/other 列表并展平子节点。"""
    if not isinstance(data, dict):
        return []
    items: list[dict] = []
    for key in ("exclusiveCategoryList", "otherCategoryList"):
        nodes = data.get(key) or []
        if isinstance(nodes, list):
            items.extend(nodes)
    flat: list[dict] = []

    def walk(nodes: list) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            flat.append(node)
            children = node.get("children") or []
            if isinstance(children, list):
                walk(children)

    walk(items)
    return flat


def format_b_todo_item(todo: dict) -> str:
    detail_id = (
        todo.get("scheduleDetailId")
        or todo.get("detailId")
        or todo.get("id")
        or "—"
    )
    todo_type = todo.get("todoTypeDesc") or todo.get("typeDesc") or todo.get("title")
    if not todo_type:
        data_type = todo.get("dataType")
        todo_type = {1: "考勤审核", 2: "延时申请", 3: "加价申请", 4: "待办事项"}.get(data_type, "待办")
    worker = todo.get("workerName") or todo.get("workerEncryptName") or "—"
    position = todo.get("positionName") or ""
    job_id = todo.get("jobId")
    when = todo.get("createTime") or todo.get("createTimeFormat") or ""
    schedule = " ".join(
        p
        for p in (
            todo.get("jobDateFormat") or todo.get("jobDate"),
            f"{todo.get('spanStartTime', '')}-{todo.get('spanEndTime', '')}".strip("-"),
        )
        if p
    )
    meta = " | ".join(p for p in (f"岗位{job_id}" if job_id else "", position, schedule) if p)
    return f"⚠️ [{detail_id}] {todo_type} | {worker}" + (f" | {meta}" if meta else "") + (f" | {when}" if when else "")


def format_task_order_item(order: dict) -> str:
    task_id = order.get("task_id") or order.get("taskId") or "—"
    title = order_title(order)
    wares = order.get("waresList") or []
    if title == "未知任务" and wares and isinstance(wares[0], dict):
        title = wares[0].get("spu_name") or wares[0].get("service_project_name") or title
    amount = order.get("service_amount")
    if amount is None:
        amount = order.get("amount")
    status = order_status_desc(order)
    if status == str(order.get("task_status", "待处理")) and order.get("task_status") is not None:
        status_map = {1: "待支付", 2: "待接单", 3: "进行中", 4: "待验收", 5: "已完成"}
        status = status_map.get(int(order["task_status"]), status)
    return f"📦 [{task_id}] {title} | ¥{amount if amount is not None else '—'} | {status}"


def api_message(result: dict, default: str = "") -> str:
    return result.get("Message") or result.get("message") or default


def parse_auth_info(data: dict) -> tuple[int, str, bool]:
    """解析实名认证状态，返回 (code, desc, passed)。"""
    if "authStatus" in data:
        status = int(data.get("authStatus") or 0)
    elif data.get("is_certification") is True:
        status = 2
    elif data.get("is_certification") is False:
        status = 0
    else:
        status = 0

    desc = {0: "未认证", 1: "审核中", 2: "已认证"}.get(status, "未知")
    return status, desc, status == 2


def profile_phone(data: dict) -> str:
    return data.get("phone") or data.get("user_phone") or ""


def profile_skill_names(data: dict) -> list[str]:
    skills = data.get("job_skill_list") or data.get("skills") or []
    if not skills:
        return []
    if isinstance(skills[0], dict):
        return [s.get("skill_name") or s.get("name") or "—" for s in skills]
    return [str(s) for s in skills]


def allow_orders(result: dict) -> bool | None:
    """解析接单权限；成功返回 True/False，接口业务失败返回 None。"""
    if not api_ok(result):
        return None
    data = api_data(result)
    if isinstance(data, dict):
        return bool(data.get("allow", True))
    return bool(data)


def parse_worker_balance(data: dict) -> dict:
    """解析零工账户余额。"""
    balance = data.get("balance")
    if balance is None:
        balance = data.get("commission_amount", data.get("commissionAmount", 0))
    bond = data.get("bond_amount", data.get("bondAmount", 0))
    withdrawable = data.get("withdrawable", data.get("withdrawableAmount"))
    if withdrawable is None:
        withdrawable = balance
    return {
        "balance": balance,
        "bond_amount": bond,
        "withdrawable": withdrawable,
    }


def order_id(order: dict):
    return order.get("orderId") or order.get("id")


def order_title(order: dict) -> str:
    return (
        order.get("title")
        or order.get("spu_name")
        or order.get("service_project_name")
        or "未知任务"
    )


def order_salary(order: dict) -> str:
    salary = order.get("salary")
    if salary:
        return str(salary)
    if order.get("settle_amount_str"):
        return f"¥{order['settle_amount_str']}"
    if order.get("settle_amount") is not None:
        return f"¥{order['settle_amount']}"
    return "面议"


def order_location(order: dict) -> str:
    return (
        order.get("address")
        or order.get("task_address")
        or order.get("task_address_str")
        or order.get("city", "")
    )


def order_date(order: dict) -> str:
    if order.get("workDate"):
        return order["workDate"]
    if order.get("expected_date_str"):
        return order["expected_date_str"]
    if order.get("job_date_str"):
        start = order.get("span_start_time", "")
        end = order.get("span_end_time", "")
        if start and end:
            return f"{order['job_date_str']} {start}-{end}"
        return order["job_date_str"]
    return order.get("expected_time_str") or order.get("appoint_time") or ""


def order_contact_phone(order: dict) -> str:
    return (
        order.get("contactPhone")
        or order.get("customer_phone")
        or order.get("order_contact_phone")
        or ""
    )


def order_status_desc(order: dict) -> str:
    return (
        order.get("statusDesc")
        or order.get("node_name")
        or order.get("task_status_str")
        or str(order.get("task_status", "待处理"))
    )


WEEK_DAY_LABELS = {
    "1": "周一",
    "2": "周二",
    "3": "周三",
    "4": "周四",
    "5": "周五",
    "6": "周六",
    "7": "周日",
}

WEEK_DAY_ALIASES = {
    "周一": "1",
    "周二": "2",
    "周三": "3",
    "周四": "4",
    "周五": "5",
    "周六": "6",
    "周日": "7",
    "周末": "6,7",
    "每个周末": "6,7",
    "双休日": "6,7",
}


def format_week_day(week_day: str | None) -> str:
    if not week_day:
        return "未设置"
    parts = []
    for token in str(week_day).replace("，", ",").split(","):
        token = token.strip()
        if not token:
            continue
        parts.append(WEEK_DAY_LABELS.get(token, token))
    return "、".join(parts) if parts else str(week_day)


def normalize_week_day(week_day: str) -> str:
    text = week_day.strip().replace("，", ",")
    if not text:
        return ""
    if text in WEEK_DAY_ALIASES:
        return WEEK_DAY_ALIASES[text]

    normalized: list[str] = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if token in WEEK_DAY_ALIASES:
            normalized.extend(WEEK_DAY_ALIASES[token].split(","))
            continue
        if token in WEEK_DAY_LABELS:
            normalized.append(WEEK_DAY_ALIASES[token])
            continue
        if token.isdigit() and token in WEEK_DAY_LABELS:
            normalized.append(token)
            continue
        raise ValueError(f"无法识别的期望工作日: {token}")
    return ",".join(dict.fromkeys(normalized))


SEX_LIMIT_LABELS = {0: "不限", 1: "不限", 2: "男", 3: "女"}
EXPERIENCE_LABELS = {0: "不限", 1: "1年以下", 2: "1-3年", 3: "3-5年", 4: "5年以上"}
EDUCATION_LABELS = {0: "不限", 1: "初中", 2: "高中", 3: "大专", 4: "本科", 5: "硕士及以上"}


def job_detail_title(data: dict) -> str:
    return data.get("position_title") or data.get("title") or "未知岗位"


def job_detail_location(data: dict) -> str:
    return (
        data.get("work_address")
        or data.get("short_address")
        or data.get("task_address")
        or data.get("address")
        or f"{data.get('city', '')}{data.get('district', '')}"
    )


def job_detail_salary(data: dict) -> str:
    if data.get("salaryDesc") or data.get("salary_desc"):
        return str(data.get("salaryDesc") or data.get("salary_desc"))
    salary = data.get("salary")
    unit = data.get("salary_unit_str") or data.get("salaryUnitStr") or "元/天"
    if salary is None:
        return "薪资面议"
    if isinstance(salary, dict):
        return f"{salary.get('min', '')}-{salary.get('max', '')}元/天"
    return f"{salary}{unit}"


def _label_from_map(value, mapping: dict, default: str = "不限") -> str:
    if value is None:
        return default
    if isinstance(value, str) and value.strip():
        return value
    return mapping.get(int(value), str(value))


def format_job_basic_requirements(data: dict) -> str:
    parts: list[str] = []
    sex = _label_from_map(data.get("sex_limit_type") or data.get("sex"), SEX_LIMIT_LABELS)
    if sex:
        parts.append(f"性别：{sex}")
    age = data.get("age")
    if age:
        parts.append(f"年龄：{age}")
    exp = _label_from_map(data.get("experience_require"), EXPERIENCE_LABELS)
    if exp:
        parts.append(f"经验：{exp}")
    edu = _label_from_map(data.get("education_require"), EDUCATION_LABELS)
    if edu:
        parts.append(f"学历：{edu}")
    skills = data.get("need_skill_name")
    if skills:
        parts.append(f"技能：{skills}")
    credential = data.get("user_credential_require_name")
    if credential:
        parts.append(f"资质：{credential}")
    benefits = data.get("position_benefit")
    if benefits:
        parts.append(f"福利：{benefits}")
    return "；".join(parts) if parts else "暂无特殊要求"


def format_job_schedule(data: dict) -> str:
    lines: list[str] = []
    work_date = data.get("work_date") or data.get("workDateStart")
    work_time = data.get("work_time") or data.get("workTimeStart")
    if work_date:
        lines.append(f"工作日期：{work_date}")
    if work_time:
        end = data.get("workTimeEnd")
        if end and "-" not in str(work_time):
            lines.append(f"工作时间：{work_time} - {end}")
        else:
            lines.append(f"工作时间：{work_time}")

    schedule_infos = data.get("jobSchduleInfos") or data.get("jobScheduleInfos") or []
    if isinstance(schedule_infos, list) and schedule_infos:
        lines.append("排班明细：")
        for item in schedule_infos:
            date = item.get("work_date") or item.get("workDate") or item.get("date") or ""
            start = item.get("start_time") or item.get("startTime") or ""
            end = item.get("end_time") or item.get("endTime") or ""
            headcount = item.get("headcount") or item.get("recruit_num") or item.get("recruitNum")
            period = " - ".join(p for p in (start, end) if p)
            detail = " | ".join(p for p in (date, period, f"招{headcount}人" if headcount else "") if p)
            if detail:
                lines.append(f"  · {detail}")

    more = data.get("more_schedule") or data.get("optional_schedules")
    if isinstance(more, list) and more:
        lines.append("可选排班：")
        for item in more:
            text = item if isinstance(item, str) else " | ".join(
                str(item.get(k) or "")
                for k in ("work_date", "workDate", "start_time", "startTime", "end_time", "endTime")
                if item.get(k)
            )
            if text:
                lines.append(f"  · {text}")
    elif isinstance(more, str) and more.strip():
        lines.append(f"可选排班：{more}")

    period = data.get("schedule_time_period")
    if period:
        lines.append(f"排班时段：{period}")
    return "\n".join(lines) if lines else "待定"


def mask_phone(phone: str) -> str:
    phone = (phone or "").strip()
    if len(phone) >= 7:
        return f"{phone[:3]}****{phone[-4:]}"
    return phone or "未提供"


def format_job_detail(data: dict, job_id: int | None = None) -> str:
    title = job_detail_title(data)
    item_id = job_id or data.get("id") or data.get("jobId") or data.get("job_id")
    recruit = data.get("recruit_number") or data.get("headcount") or data.get("recruit_num") or 0
    category = data.get("industry_name") or data.get("all_postion_type") or data.get("category") or "未分类"
    company = data.get("company_name") or data.get("store_abbreviation") or ""
    desc = data.get("position_desc") or data.get("description") or "暂无描述"
    schedule = format_job_schedule(data)
    requirements = format_job_basic_requirements(data)
    recruiter = data.get("recruiter_name") or ""
    contact = mask_phone(data.get("contact") or data.get("contact_phone") or "")

    lines = [
        f"📋 {title}\n",
        f"岗位ID: {item_id}",
        f"💰 薪资: {job_detail_salary(data)}",
        f"📍 地点: {job_detail_location(data)}",
        f"👥 招募: {recruit}人",
        f"🏷️ 类别: {category}",
    ]
    if company:
        lines.append(f"🏢 企业: {company}")
    lines.extend(
        [
            f"📅 排班信息:\n{schedule}",
            f"✅ 基本要求: {requirements}",
            f"📝 干活要求:\n{desc}",
        ]
    )
    if recruiter or contact:
        lines.append(f"👤 联系人: {recruiter} {contact}".strip())
    return "\n".join(lines)


def parse_work_preferences(data: dict) -> dict:
    week_day = data.get("week_day")
    return {
        "week_day": week_day,
        "week_day_desc": format_week_day(week_day),
        "work_time_slot": data.get("work_time_slot") or "未设置",
        "work_length": data.get("work_length") or "未设置",
        "salary_expectation": data.get("salary_expectation"),
        "salary_unit": data.get("salary_unit", 0),
        "benefit": data.get("benefit") or "",
        "intention_address": data.get("intention_address") or "",
        "residence_address": data.get("residence_address") or "",
    }

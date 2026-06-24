"""B 端账户流水解析（对齐小程序 account/log/getUserAccountLogPageList）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

# 小程序 expensedetail.vue / account.vue accountType
ACCOUNT_TYPE_LABELS: dict[int, str] = {
    0: "全部账户",
    8: "个人余额",
    9: "企业余额",
    3: "体验金",
    10: "招工保证金",
}

# changeType: 0全部 1增加 2减少
LOG_CHANGE_TYPE_LABELS: dict[int, str] = {
    0: "全部",
    1: "收入",
    2: "支出",
}

LOG_TYPE_ALIASES: dict[str, int] = {
    "all": 0,
    "全部": 0,
    "income": 1,
    "收入": 1,
    "增加": 1,
    "expense": 2,
    "支出": 2,
    "减少": 2,
}


def resolve_log_change_type(log_type: str) -> int:
    raw = (log_type or "all").strip().lower()
    if raw in LOG_TYPE_ALIASES:
        return LOG_TYPE_ALIASES[raw]
    if raw in ("1", "2"):
        return int(raw)
    raise ValueError(f"未知 log_type: {log_type}，可选 all/income/expense 或 收入/支出")


def resolve_account_type(account_type: int, balance_view: dict | None) -> int:
    if account_type > 0:
        return account_type
    view = balance_view or {}
    login_type = view.get("login_type")
    if login_type == 3:
        return 9
    return 8


def flatten_account_log_records(records: list) -> list[dict]:
    flat: list[dict] = []
    for group in records or []:
        if not isinstance(group, dict):
            continue
        if group.get("logList"):
            flat.extend(group["logList"])
        else:
            flat.append(group)
    return flat


def parse_log_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None


def filter_logs_by_days(logs: list[dict], days: int, *, end: date | None = None) -> list[dict]:
    if days <= 0:
        return logs
    end_day = end or date.today()
    start_day = end_day - timedelta(days=days)
    out: list[dict] = []
    for log in logs:
        dt = parse_log_datetime(log.get("createTime"))
        if dt is None:
            continue
        if start_day <= dt.date() <= end_day:
            out.append(log)
    return out


def account_log_amount(log: dict) -> float:
    for key in ("num", "amount", "changeAmount"):
        val = log.get(key)
        if val is not None:
            return float(val)
    return 0.0


def account_log_description(log: dict) -> str:
    return (
        log.get("operateTypeStr")
        or log.get("description")
        or log.get("remark")
        or log.get("typeDesc")
        or "—"
    )


def account_log_sign(log: dict) -> str:
    change = log.get("changeType")
    if change == 1:
        return "+"
    if change == 2:
        return "-"
    log_type = log.get("type")
    if log_type in ("income", 1, "1"):
        return "+"
    return "-"


def format_account_log_line(log: dict) -> str:
    sign = account_log_sign(log)
    amount = account_log_amount(log)
    desc = account_log_description(log)
    when = log.get("createTime") or ""
    balance_after = log.get("totalNum")
    tail = f" | 余额¥{balance_after}" if balance_after is not None else ""
    return f"{sign}¥{amount:.2f} | {desc} | {when}{tail}"


def build_account_log_payload(
    *,
    account_type: int,
    change_type: int,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    return {
        "accountType": account_type,
        "changeType": change_type,
        "pageNum": page,
        "pageSize": page_size,
        "compareType": 1,
        "newQuery": 1,
        "compareDate": "",
    }


def format_account_log_section(
    logs: list[dict],
    *,
    days: int = 0,
    log_type: str = "all",
    account_type: int = 8,
    total: int | None = None,
) -> dict:
    change_type = resolve_log_change_type(log_type)
    type_label = LOG_CHANGE_TYPE_LABELS.get(change_type, log_type)
    acct_label = ACCOUNT_TYPE_LABELS.get(account_type, str(account_type))
    if not logs:
        scope = f"最近{days}天" if days > 0 else ""
        return {
            "text": f"暂无{type_label}明细{('（' + scope + ' · ' + acct_label + '）') if scope else ''}。",
            "items": [],
            "total": 0,
            "sum_amount": 0.0,
        }
    total_amount = sum(account_log_amount(log) for log in logs)
    header_bits = [f"{type_label}明细"]
    if days > 0:
        header_bits.append(f"最近{days}天")
    header_bits.append(acct_label)
    header_bits.append(f"共{len(logs)}条")
    if total is not None and total != len(logs):
        header_bits.append(f"（接口总计{total}条）")
    header_bits.append(f"合计¥{total_amount:.2f}")
    lines = [" · ".join(header_bits) + "\n"]
    for log in logs:
        lines.append(format_account_log_line(log))
    return {
        "text": "\n".join(lines),
        "items": logs,
        "total": len(logs),
        "sum_amount": round(total_amount, 2),
    }

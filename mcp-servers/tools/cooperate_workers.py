"""合作零工查询与邀请（对齐小程序 cooperation.vue / invitation.vue）。"""

from __future__ import annotations

COOPERATE_LIST_TABS: dict[str, dict[str, int | str]] = {
    "cooperate": {"cooperate_type": 1, "label": "合作过"},
    "blacklist": {"cooperate_type": 2, "label": "黑名单"},
}

_PRIVACY_KEYS = frozenset({
    "phone",
    "mobile",
    "userPhone",
    "customerPhone",
    "idCard",
    "id_card",
})


def resolve_cooperate_tab(list_tab: str) -> tuple[int, str] | None:
    key = (list_tab or "cooperate").strip().lower()
    aliases = {
        "1": "cooperate",
        "2": "blacklist",
        "合作过": "cooperate",
        "黑名单": "blacklist",
    }
    key = aliases.get(key, key)
    tab = COOPERATE_LIST_TABS.get(key)
    if not tab:
        return None
    return int(tab["cooperate_type"]), str(tab["label"])


def sanitize_cooperate_worker(row: dict) -> dict:
    if not isinstance(row, dict):
        return {}
    out: dict = {}
    for key, value in row.items():
        if key in _PRIVACY_KEYS:
            continue
        out[key] = value
    user_id = out.get("userId") or out.get("user_id")
    if user_id is not None:
        out["user_id"] = str(user_id)
    return out


def format_cooperate_count(count_payload: dict | None) -> str:
    if not isinstance(count_payload, dict):
        return ""
    total = count_payload.get("totalCount")
    if total is None:
        return ""
    return f"合作零工总数：{total}"


def format_cooperate_workers(
    workers: list[dict],
    *,
    tab_label: str,
    total_count: int | None = None,
) -> str:
    if not workers:
        hint = "暂无合作零工。" if tab_label == "合作过" else "黑名单为空。"
        return hint

    count = total_count if total_count is not None else len(workers)
    lines = [f"{tab_label}零工（共 {count} 人）：\n"]
    for w in workers:
        clean = sanitize_cooperate_worker(w)
        user_id = clean.get("user_id") or "—"
        name = clean.get("name") or "未知"
        age = clean.get("age")
        sex = clean.get("sex") or ""
        age_sex = f"{age}岁" if age is not None else ""
        if sex:
            age_sex = f"{age_sex} {sex}".strip()
        coop = clean.get("cooperateCount", 0)
        title = clean.get("positionTitle") or "—"
        line = f"👤 [{user_id}] {name}"
        if age_sex:
            line += f" | {age_sex}"
        line += f" | 合作任务数: {coop} | 最近: {title}"
        if tab_label == "黑名单":
            line += f" | 加入时间: {clean.get('blackDate') or '—'}"
        lines.append(line)
    lines.append("\n邀请报名请使用 user_id，调用 invite_worker_to_job。")
    return "\n".join(lines)


def parse_worker_user_ids(raw: str) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    parts = str(raw).replace("，", ",").split(",")
    return [p.strip() for p in parts if p.strip()]


def build_invite_param_from_job(job: dict) -> dict:
    return {
        "id": job.get("id") or job.get("jdId"),
        "title": job.get("positionTitle") or job.get("title"),
        "workAddress": job.get("workAddress") or job.get("work_address"),
        "amount": job.get("amount"),
        "startTime": job.get("startTime") or job.get("start_time"),
        "endTime": job.get("endTime") or job.get("end_time"),
    }


def build_invite_param_from_task(task: dict) -> dict:
    wares = task.get("taskWaresDTOList") or []
    first = wares[0] if wares else {}
    return {
        "id": task.get("id"),
        "title": first.get("spuName") or task.get("title"),
        "workAddress": task.get("taskAddress") or task.get("workAddress"),
        "amount": task.get("amount") or task.get("serviceAmount"),
        "startTime": task.get("startTime"),
        "endTime": task.get("endTime"),
    }

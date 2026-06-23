"""找活推荐：小时工 → 计件工 → 众包工 → 岗位 优先级逻辑。"""

JOB_TYPE_HOURLY = "小时工"
JOB_TYPE_PIECE = "计件工"
JOB_TYPE_CROWD = "众包工"
JOB_TYPE_POSITION = "岗位"

RECOMMEND_PRIORITY = (JOB_TYPE_HOURLY, JOB_TYPE_PIECE, JOB_TYPE_CROWD, JOB_TYPE_POSITION)


def normalize_city(city: str) -> str:
    city = (city or "").strip()
    if not city:
        return city
    if city.endswith("市"):
        return city
    return f"{city}市"


def job_title(item: dict) -> str:
    return (
        item.get("position_title")
        or item.get("spu_name")
        or item.get("service_project_name")
        or item.get("title")
        or "未知"
    )


def job_location_text(item: dict) -> str:
    addr = item.get("task_address") or item.get("work_address") or item.get("address") or ""
    district = item.get("district") or ""
    city = item.get("city") or ""
    if addr:
        return addr
    return f"{city}{district}"


def job_salary_text(item: dict) -> str:
    if item.get("salaryDesc") or item.get("salary_desc"):
        return str(item.get("salaryDesc") or item.get("salary_desc"))
    salary = item.get("salary")
    if salary is None:
        salary = item.get("settle_amount_str") or item.get("settle_amount")
    unit = item.get("salary_unit_str") or item.get("salaryUnitStr") or item.get("unit_name") or ""
    if salary is None:
        return "薪资面议"
    if unit and str(unit) not in str(salary):
        return f"{salary}{unit}"
    return str(salary)


def classify_jd_job(job: dict) -> str:
    product_type = job.get("product_type")
    if product_type == 4:
        return JOB_TYPE_HOURLY
    if product_type == 6:
        return JOB_TYPE_PIECE

    title = job_title(job)
    unit = str(job.get("salary_unit_str") or job.get("salaryUnitStr") or "")
    if "计件" in title:
        return JOB_TYPE_PIECE
    if "元/小时" in unit or "小时" in unit:
        return JOB_TYPE_HOURLY
    return JOB_TYPE_POSITION


def classify_crowd_task(_task: dict) -> str:
    return JOB_TYPE_CROWD


def matches_district(item: dict, district: str) -> bool:
    if not district:
        return True
    district = district.strip()
    if item.get("district") == district:
        return True
    loc = job_location_text(item)
    return district in loc


def matches_keyword(item: dict, keyword: str) -> bool:
    if not keyword:
        return True
    keyword = keyword.strip()
    haystack = " ".join(
        [
            job_title(item),
            job_location_text(item),
            str(item.get("service_project_name") or ""),
            str(item.get("category_name") or ""),
        ]
    )
    return keyword in haystack


def dedupe_by_id(items: list[dict]) -> list[dict]:
    seen: set = set()
    result: list[dict] = []
    for item in items:
        item_id = item.get("id") or item.get("jobId") or item.get("job_id")
        if item_id in seen:
            continue
        seen.add(item_id)
        result.append(item)
    return result


def bucket_jd_jobs(jobs: list[dict]) -> dict[str, list[dict]]:
    buckets = {key: [] for key in RECOMMEND_PRIORITY}
    for job in dedupe_by_id(jobs):
        buckets[classify_jd_job(job)].append(job)
    return buckets


def merge_priority_buckets(
    hourly: list[dict],
    piece: list[dict],
    crowd: list[dict],
    position: list[dict],
    *,
    page_size: int,
) -> list[tuple[str, dict]]:
    source = {
        JOB_TYPE_HOURLY: hourly,
        JOB_TYPE_PIECE: piece,
        JOB_TYPE_CROWD: crowd,
        JOB_TYPE_POSITION: position,
    }
    merged: list[tuple[str, dict]] = []
    for job_type in RECOMMEND_PRIORITY:
        for item in source[job_type]:
            merged.append((job_type, item))
            if len(merged) >= page_size:
                return merged
    return merged


def format_recommend_card(job_type: str, item: dict, icon: str = "⭐") -> str:
    time_text = (
        item.get("expected_date_str")
        or item.get("expected_time_str")
        or item.get("work_time")
        or item.get("work_date")
        or ""
    )
    headcount = item.get("headcount") or item.get("recruit_num") or item.get("recruitNum")
    extra = f" | 👥 招{headcount}人" if headcount else ""
    time_line = f"\n   ⏱ {time_text}" if time_text else ""
    item_id = item.get("id") or item.get("jobId") or item.get("job_id")
    return (
        f"{icon} [{item_id}] {job_title(item)}\n"
        f"   🏷️ {job_type} | 💰 {job_salary_text(item)} | 📍 {job_location_text(item)}{extra}{time_line}"
    )

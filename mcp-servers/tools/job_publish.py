"""B 端岗位发布 payload 构建（对齐 miniprogram/jd/publish 真实字段）。"""
from __future__ import annotations

import copy
from datetime import date
from typing import Any


def build_working_schedule_item(
    *,
    job_date: str,
    start_time: str,
    end_time: str,
    headcount: int,
    product_type: int,
    hourly_wage: float | None = None,
    piece_wage: float | None = None,
    pieces_per_person: int | None = None,
) -> dict[str, Any]:
    """构建单条班次（publish 接口字段名为 workingScheduleList）。"""
    start = start_time.strip()
    end = end_time.strip()
    wage = hourly_wage if product_type == 4 else (piece_wage if piece_wage is not None else hourly_wage)
    if wage is None:
        wage = 0.0

    item: dict[str, Any] = {
        "needCount": headcount,
        "jobDate": job_date,
        "spanStartTime": start,
        "spanEndTime": end,
        "timeFromTo": f"{start}-{end}",
        "timeLength": _hours_between(start, end),
        "isAcross": False,
        "isUserMultiDays": False,
        "restLength": 0.0,
        "timeRemark": "",
        "deliveryType": 0,
    }

    if product_type == 4:
        item["hourlyWage"] = wage
        item["workerUnitPrice"] = wage
    else:
        item["hourlyWage"] = wage
        item["workerUnitPrice"] = wage
        item["piecesPerPerson"] = pieces_per_person if pieces_per_person is not None else 1

    return item


def _hours_between(start: str, end: str) -> float:
    try:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        return max((eh * 60 + em - sh * 60 - sm) / 60.0, 0.0)
    except (ValueError, AttributeError):
        return 0.0


def address_from_job_detail(detail: dict) -> dict[str, Any]:
    """从岗位详情提取干活地点信息。"""
    return {
        "recruit_address_id": detail.get("recruitAddressId"),
        "store_name": detail.get("storeAbbreviation") or detail.get("store_abbreviation"),
        "work_address": detail.get("workAddress"),
        "work_address_text": detail.get("workAddressText"),
        "province": detail.get("province"),
        "city": detail.get("city"),
        "city_code": detail.get("cityCode"),
        "district": detail.get("district"),
        "lng": detail.get("lng"),
        "lat": detail.get("lat"),
        "work_category_id": detail.get("workCategoryId"),
        "position_type": detail.get("positionType") or detail.get("templateId"),
        "template_id": detail.get("templateId"),
        "category_name": detail.get("allPostionType"),
    }


def publish_template_from_detail(detail: dict) -> dict[str, Any]:
    """从已有岗位详情生成发布模板摘要。"""
    addr = address_from_job_detail(detail)
    schedules = detail.get("recruitWorkingScheduleList") or detail.get("workingScheduleList") or []
    sample = schedules[0] if schedules else {}
    return {
        "reference_job_id": detail.get("id"),
        "product_type": detail.get("productType"),
        "position_title": detail.get("positionTitle"),
        "work_category_id": addr["work_category_id"],
        "category_name": addr["category_name"],
        "position_type": addr["position_type"],
        "template_id": addr["template_id"],
        "recruit_address_id": addr["recruit_address_id"],
        "store_name": addr["store_name"],
        "work_address": addr["work_address"],
        "salary": detail.get("salary"),
        "salary_type": detail.get("salaryType"),
        "sample_schedule": {
            "job_date": sample.get("jobDate"),
            "start_time": sample.get("spanStartTime"),
            "end_time": sample.get("spanEndTime"),
            "headcount": sample.get("needCount"),
            "hourly_wage": sample.get("hourlyWage"),
            "piece_wage": sample.get("workerUnitPrice"),
            "pieces_per_person": sample.get("piecesPerPerson"),
        },
        "position_desc_preview": (detail.get("positionDesc") or "")[:200],
    }


def build_publish_payload(
    *,
    title: str,
    description: str,
    product_type: int,
    headcount: int,
    salary_min: float,
    salary_max: float | None = None,
    reference_detail: dict | None = None,
    recruit_address_id: int | None = None,
    work_category_id: int | None = None,
    position_type: int | None = None,
    template_id: int | None = None,
    location: str = "",
    province: str = "",
    city: str = "",
    city_code: int | None = None,
    district: str = "",
    lng: float | None = None,
    lat: float | None = None,
    job_date: str | None = None,
    schedule_start: str = "09:00",
    schedule_end: str = "18:00",
    skills: list | None = None,
    benefits: list | None = None,
    subscript_worker_count: int = 0,
    subscript_day_count: int = 0,
    sex_limit_type: int = 1,
    age: str = "16-65",
) -> dict[str, Any]:
    """组装 miniprogram/jd/publish 请求体。"""
    ref = reference_detail or {}
    addr = address_from_job_detail(ref) if ref else {}

    work_date = job_date or date.today().isoformat()
    wage = salary_min if salary_max is None else (salary_min + salary_max) / 2

    payload: dict[str, Any] = {
        "title": title,
        "positionTitle": title,
        "positionDesc": description,
        "description": description,
        "productType": product_type,
        "recruitAddressId": recruit_address_id or addr.get("recruit_address_id"),
        "workCategoryId": work_category_id or addr.get("work_category_id"),
        "positionType": position_type or addr.get("position_type"),
        "templateId": template_id or addr.get("template_id"),
        "workAddress": location or addr.get("work_address") or "",
        "province": province or addr.get("province") or "",
        "city": city or addr.get("city") or "",
        "cityCode": city_code if city_code is not None else addr.get("city_code"),
        "district": district or addr.get("district") or "",
        "lng": lng if lng is not None else addr.get("lng"),
        "lat": lat if lat is not None else addr.get("lat"),
        "salary": wage,
        "salaryType": ref.get("salaryType", 1),
        "sexLimitType": sex_limit_type,
        "sex": ref.get("sex", 1),
        "ageLimitType": ref.get("ageLimitType", 3),
        "age": age,
        "experienceRequire": ref.get("experienceRequire", 0),
        "educationRequire": ref.get("educationRequire", 0),
        "jobDate": work_date,
        "skillList": skills or [],
        "benefitList": benefits or [],
    }

    if product_type == 6:
        payload["salaryPaymentType"] = ref.get("salaryPaymentType", 4)

    if product_type in (2, 5):
        payload["subscriptWorkerCount"] = subscript_worker_count
        payload["subscriptDayCount"] = subscript_day_count
    else:
        if ref.get("recruitWorkingScheduleList") or ref.get("workingScheduleList"):
            src = ref.get("recruitWorkingScheduleList") or ref.get("workingScheduleList")
            schedule = copy.deepcopy(src[0])
            schedule["jobDate"] = work_date
            schedule["needCount"] = headcount
            schedule["spanStartTime"] = schedule_start
            schedule["spanEndTime"] = schedule_end
            schedule["timeFromTo"] = f"{schedule_start}-{schedule_end}"
            schedule["timeLength"] = _hours_between(schedule_start, schedule_end)
        else:
            schedule = build_working_schedule_item(
                job_date=work_date,
                start_time=schedule_start,
                end_time=schedule_end,
                headcount=headcount,
                product_type=product_type,
                hourly_wage=salary_min if product_type == 4 else None,
                piece_wage=salary_min if product_type == 6 else None,
            )
        if product_type == 4:
            schedule["hourlyWage"] = salary_min
            schedule["workerUnitPrice"] = salary_min
        elif product_type == 6:
            schedule["hourlyWage"] = salary_min
            schedule["workerUnitPrice"] = salary_min
        payload["workingScheduleList"] = [schedule]

    return payload

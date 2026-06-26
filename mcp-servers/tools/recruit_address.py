"""B 端用工地点（userRecruitAddress）列表、匹配与保存 payload。"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from tools.api_response import api_data, api_message, api_ok

RequestFn = Callable[..., Awaitable[dict]]

MATCH_THRESHOLD = 0.85


def normalize_address_text(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[\s,，。；;、\-—_()（）#]", "", t)
    return t


def _mask_phone(phone: str) -> str:
    p = (phone or "").strip()
    if len(p) >= 11:
        return f"{p[:3]}****{p[-4:]}"
    return p or "—"


def address_record_to_summary(record: dict) -> dict[str, Any]:
    """对外展示用的地址摘要（不含完整手机号）。"""
    return {
        "recruit_address_id": record.get("id"),
        "store_name": record.get("storeAbbreviation") or "",
        "street_number": record.get("streetNumber") or "",
        "work_address": record.get("workAddress") or "",
        "complete_address": record.get("completeAddress") or "",
        "short_address": record.get("shortAddress") or "",
        "province": record.get("province") or "",
        "city": record.get("city") or "",
        "district": record.get("district") or "",
        "lng": record.get("lng"),
        "lat": record.get("lat"),
        "contacts": record.get("contacts") or "",
        "contact_phone_masked": _mask_phone(str(record.get("contactPhone") or "")),
        "complete_info": bool(record.get("completeInfo")),
        "default_address": bool(record.get("defaultAddress")),
    }


def address_match_score(query: str, record: dict) -> float:
    q = normalize_address_text(query)
    if not q:
        return 0.0
    candidates = [
        record.get("workAddress"),
        record.get("completeAddress"),
        record.get("shortAddress"),
        record.get("streetNumber"),
        record.get("storeAbbreviation"),
        f"{record.get('storeAbbreviation') or ''}{record.get('workAddress') or ''}",
    ]
    best = 0.0
    for raw in candidates:
        n = normalize_address_text(str(raw or ""))
        if not n:
            continue
        if q == n:
            best = max(best, 1.0)
        elif q in n or n in q:
            best = max(best, 0.9)
        else:
            # 简单字符重叠率
            common = sum(1 for ch in q if ch in n)
            ratio = common / max(len(q), len(n))
            if ratio >= 0.6:
                best = max(best, ratio)
    return best


def find_best_address_match(
    records: list[dict],
    query: str,
    *,
    threshold: float = MATCH_THRESHOLD,
) -> dict | None:
    best_record: dict | None = None
    best_score = 0.0
    for record in records:
        if not isinstance(record, dict):
            continue
        score = address_match_score(query, record)
        if score > best_score:
            best_score = score
            best_record = record
    if best_record is not None and best_score >= threshold:
        summary = address_record_to_summary(best_record)
        summary["match_score"] = round(best_score, 3)
        return summary
    return None


async def fetch_recruit_address_list(
    req: RequestFn,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """拉取企业用工地点分页列表。"""
    result = await req(
        "POST",
        "userRecruitAddress/list",
        json={"pageNum": page, "pageSize": page_size},
    )
    if not api_ok(result):
        raise Exception(api_message(result, "获取用工地点列表失败"))
    data = api_data(result)
    if not isinstance(data, dict):
        data = {}
    records = data.get("records") or []
    if not isinstance(records, list):
        records = []
    return {
        "total": int(data.get("total") or len(records)),
        "records": [r for r in records if isinstance(r, dict)],
        "page": page,
        "page_size": page_size,
    }


def build_save_recruit_address_payload(
    *,
    work_address: str,
    store_name: str,
    floor_num: str,
    house_num: str,
    contacts: str,
    contact_phone: str,
    street_number: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
    short_address: str = "",
    lng: float | None = None,
    lat: float | None = None,
    default_address: bool = False,
    alternate_phone: str = "",
    address_id: int = 0,
) -> dict[str, Any]:
    """组装 userRecruitAddress/save 请求体（对齐小程序 sub-packages/address/edit.vue）。"""
    poi = (street_number or store_name or work_address).strip()
    short = short_address.strip()
    if not short and district:
        short = district
    payload: dict[str, Any] = {
        "storeAbbreviation": store_name.strip(),
        "floorNum": floor_num.strip(),
        "houseNum": house_num.strip(),
        "contacts": contacts.strip(),
        "contactPhone": contact_phone.strip(),
        "streetNumber": poi,
        "workAddress": work_address.strip(),
        "defaultAddress": default_address,
        "province": province.strip(),
        "city": city.strip(),
        "district": district.strip(),
        "shortAddress": short,
        "remark": "",
        "list": [],
    }
    if address_id:
        payload["id"] = address_id
    if alternate_phone.strip():
        payload["alternatePhone"] = alternate_phone.strip()
    if lng is not None:
        payload["lng"] = lng
    if lat is not None:
        payload["lat"] = lat
    return payload


def format_recruit_addresses_text(
    addresses: list[dict],
    *,
    total: int = 0,
    matched: dict | None = None,
    query: str = "",
) -> str:
    lines: list[str] = []
    if query:
        if matched:
            lines.append(
                f"✅ 已匹配用工地点：[{matched['recruit_address_id']}] "
                f"{matched.get('store_name') or '—'} | {matched.get('work_address')}"
            )
        else:
            lines.append(f"未找到与「{query}」一致的已有地址，可录入新地点。")
        lines.append("")
    header = f"用工地点（共 {total or len(addresses)} 个）：\n"
    lines.append(header)
    if not addresses:
        lines.append("  （暂无记录，请调用 save_recruit_address 录入）")
        return "\n".join(lines)
    for a in addresses:
        summary = address_record_to_summary(a)
        mark = "⭐" if summary.get("default_address") else "📍"
        complete = "✓" if summary.get("complete_info") else "待完善"
        lines.append(
            f"  {mark} [{summary['recruit_address_id']}] "
            f"{summary.get('store_name') or '—'} | {summary.get('work_address')} ({complete})"
        )
    if query and not matched:
        lines.append(
            "\n💡 录入新地址须补充：门店简称、楼层、门牌、联系人、联系电话；"
            "建议同时提供省市区与经纬度。确认后 prepare_write_confirmation → save_recruit_address。"
        )
    return "\n".join(lines)

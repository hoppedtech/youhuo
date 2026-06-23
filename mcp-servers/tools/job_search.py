"""Job/GetSearchList 搜索（对齐小程序找活搜索页）。"""

from tools.job_recommend import normalize_city


def build_get_search_list_payload(
    city: str,
    keyword: str,
    *,
    page: int = 1,
    page_size: int = 10,
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    """构造 GetSearchList 请求体（须用 page_index/page_size/city=北京市）。"""
    kw = (keyword or "").strip()
    payload: dict = {
        "position_title": kw,
        "keyword": kw,
        "page_index": page,
        "page_size": page_size,
        "totalPage": 1,
    }
    city_norm = normalize_city(city) if city else ""
    if city_norm:
        payload["city"] = city_norm
    if lat is not None and lng is not None:
        payload["lat"] = lat
        payload["lng"] = lng
    return payload

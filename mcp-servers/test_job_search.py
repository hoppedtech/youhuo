"""job_search GetSearchList 参数构造单元测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.api_response import api_search_lists
from tools.job_search import build_get_search_list_payload


def test_build_get_search_list_payload():
    payload = build_get_search_list_payload(
        "北京",
        "面点师",
        page=1,
        page_size=10,
        lat=39.894322,
        lng=116.510951,
    )
    assert payload["city"] == "北京市"
    assert payload["keyword"] == "面点师"
    assert payload["position_title"] == "面点师"
    assert payload["page_index"] == 1
    assert payload["page_size"] == 10
    assert payload["totalPage"] == 1
    assert payload["lat"] == 39.894322
    assert payload["lng"] == 116.510951


def test_api_search_lists():
    jobs, orders, total = api_search_lists(
        {
            "Data": {
                "jobList": [{"id": 2938374, "position_title": "面点师0622a"}],
                "orderList": [{"id": 1}],
                "totalElement": 2,
            }
        }
    )
    assert len(jobs) == 1
    assert len(orders) == 1
    assert total == 2


if __name__ == "__main__":
    for fn in [test_build_get_search_list_payload, test_api_search_lists]:
        fn()
        print(f"✅ {fn.__name__}")
    print("\n全部测试通过")

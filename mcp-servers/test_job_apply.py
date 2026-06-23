"""岗位报名路由测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.job_apply import build_schedule_info, parse_schedule_ids, resolve_product_type


def test_parse_schedule_ids():
    assert parse_schedule_ids("101,102") == [101, 102]
    assert parse_schedule_ids([201]) == [201]
    assert parse_schedule_ids("") == []


def test_build_schedule_info():
    info = build_schedule_info([11, 12])
    assert info[0]["schedule_id"] == 11
    assert info[1]["schedule_id"] == 12


def test_resolve_product_type():
    assert resolve_product_type(5, "小时工") == 5
    assert resolve_product_type(4, "岗位") == 4
    assert resolve_product_type(None, "小时工") == 4


if __name__ == "__main__":
    for fn in (test_parse_schedule_ids, test_build_schedule_info, test_resolve_product_type):
        fn()
        print("PASS", fn.__name__)

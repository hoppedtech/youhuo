"""报名资料检查与提交测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.job_entry import (
    assess_apply_readiness,
    build_job_registration_payload,
    format_entry_requirements,
    parse_skill_ids,
)


def test_assess_apply_readiness_missing_profile():
    report = assess_apply_readiness(
        job_id=104387,
        job_detail={"product_type": 5, "position_title": "服务员"},
        entry_detail={"position_name": "服务员", "credentials": [], "skill_tags": [], "resume": None},
        profile={
            "name": "石海波",
            "is_certification": True,
            "wechat_account": None,
            "intention_address": None,
            "salary_expectation": None,
            "salary_unit": 0,
        },
        skill_ids=[],
    )
    assert report["ready"] is False
    fields = {item["field"] for item in report["missing"]}
    assert "wechat_account" in fields
    assert "intention_address" in fields


def test_assess_requires_skill_tags_when_provided():
    report = assess_apply_readiness(
        job_id=1,
        job_detail={"product_type": 5},
        entry_detail={
            "skill_tags": [{"id": 11, "skill_name": "传菜"}],
            "credentials": [],
            "resume": None,
        },
        profile={
            "is_certification": True,
            "wechat_account": "wx123",
            "intention_address": "深圳南山",
            "salary_expectation": "20-25",
            "salary_unit": 3,
            "job_skill_list": [{"skill_id": 1}],
        },
        skill_ids=[],
    )
    assert report["ready"] is False
    assert any(item["field"] == "skill_ids" for item in report["missing"])


def test_build_job_registration_payload():
    payload = build_job_registration_payload(
        104387,
        name="张三",
        sex="男",
        birthday="199001",
        wechat_account="wx_abc",
        intention_address="深圳南山",
        salary_expectation="20-25",
        salary_unit=3,
        skill_ids=[1, 2],
    )
    assert payload["job_id"] == 104387
    assert payload["birthday"] == "19900101"
    assert payload["skills"] == [1, 2]


def test_format_entry_requirements_ready():
    text = format_entry_requirements(
        {
            "job_id": 1,
            "position_name": "服务员",
            "product_type": 5,
            "profile_snapshot": {"auth_status": "已认证", "name": "张三"},
            "missing": [],
            "warnings": [],
        }
    )
    assert "资料已齐全" in text


if __name__ == "__main__":
    for fn in (
        test_assess_apply_readiness_missing_profile,
        test_assess_requires_skill_tags_when_provided,
        test_build_job_registration_payload,
        test_format_entry_requirements_ready,
    ):
        fn()
        print("PASS", fn.__name__)

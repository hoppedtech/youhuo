"""api_response 解析工具单元测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.api_response import (
    allow_orders,
    api_data,
    api_list,
    api_message,
    api_ok,
    api_total,
    format_job_detail,
    format_job_basic_requirements,
    format_job_schedule,
    format_week_day,
    normalize_week_day,
    order_title,
    parse_auth_info,
    parse_work_preferences,
    parse_worker_balance,
    profile_phone,
    profile_skill_names,
)


def test_getbasicinfo_action_result_format():
    result = {
        "ActionResult": "1",
        "Message": "",
        "Data": {
            "name": "石海波",
            "user_phone": "13264300460",
            "is_certification": True,
            "job_skill_list": [{"skill_name": "外卖骑手", "skill_id": 194}],
        },
    }
    data = api_data(result)
    assert api_ok(result)
    assert data["name"] == "石海波"
    assert profile_phone(data) == "13264300460"
    code, desc, passed = parse_auth_info(data)
    assert code == 2
    assert desc == "已认证"
    assert passed is True
    assert profile_skill_names(data) == ["外卖骑手"]


def test_getbasicinfo_legacy_format():
    result = {
        "code": 200,
        "data": {
            "name": "测试",
            "phone": "13800138000",
            "authStatus": 1,
            "skills": ["搬运"],
        },
    }
    data = api_data(result)
    code, desc, passed = parse_auth_info(data)
    assert code == 1
    assert desc == "审核中"
    assert passed is False
    assert profile_phone(data) == "13800138000"


def test_getbasicinfo_missing_data():
    result = {"ActionResult": "1", "Data": None}
    assert api_data(result) == {}
    code, desc, passed = parse_auth_info({})
    assert code == 0
    assert passed is False


def test_allow_orders_action_result():
    assert allow_orders({"ActionResult": "1", "Data": {"allow": True}}) is True
    assert allow_orders({"ActionResult": "1", "Data": {"allow": False}}) is False
    assert allow_orders({"ActionResult": "-1", "Message": "订单不存在", "Data": None}) is None


def test_jobentry_failure_message():
    result = {"ActionResult": "-1", "Message": "该岗位信息已失效", "Data": None}
    assert api_ok(result) is False
    assert api_message(result) == "该岗位信息已失效"


def test_skill_list_action_result():
    result = {"ActionResult": "1", "Data": [{"name": "搬运工"}, {"skillName": "保洁"}]}
    items = api_list(result)
    assert len(items) == 2


def test_worker_balance_action_result_format():
    result = {"ActionResult": "1", "Data": {"bond_amount": 0.0, "commission_amount": 1.0}}
    info = parse_worker_balance(api_data(result))
    assert info["balance"] == 1.0
    assert info["bond_amount"] == 0.0
    assert info["withdrawable"] == 1.0


def test_order_list_action_result_format():
    result = {
        "ActionResult": "1",
        "Data": {
            "TotalElement": 47,
            "ElementList": [
                {
                    "id": 1564,
                    "spu_name": "企业办公地址核验",
                    "settle_amount_str": "5.13",
                    "task_address": "北京市朝阳区朝阳大悦城",
                    "expected_date_str": "03月07日 14:00",
                    "node_name": "拍摄公司门头照",
                }
            ],
        },
    }
    assert api_total(result) == 47
    order = api_list(result)[0]
    assert order_title(order) == "企业办公地址核验"


def test_work_preferences_helpers():
    assert normalize_week_day("周末") == "6,7"
    assert normalize_week_day("周六,周日") == "6,7"
    assert format_week_day("6,7") == "周六、周日"
    prefs = parse_work_preferences(
        {"week_day": "6,7", "work_time_slot": "全天", "work_length": "周末"}
    )
    assert prefs["week_day_desc"] == "周六、周日"
    assert prefs["work_time_slot"] == "全天"


def test_job_detail_action_result_format():
    data = {
        "id": 2936697,
        "position_title": "诚招 咖啡师0611a",
        "salary": 13.0,
        "salary_unit_str": "元/小时",
        "work_address": "全国范围招聘",
        "short_address": "朝阳区广渠路",
        "recruit_number": 2,
        "industry_name": "餐饮服务",
        "all_postion_type": "咖啡师",
        "work_date": "6月28、29、30日",
        "work_time": "08:00-08:30",
        "position_desc": "按标准制作饮品",
        "need_skill_name": "咖啡拉花、设备维护",
        "age": "16-65",
        "sex": 1,
        "experience_require": 0,
        "education_require": 0,
        "position_benefit": "包餐包水",
        "company_name": "上海百集科技集团有限公司",
        "recruiter_name": "李先生",
        "contact": "1550000001",
    }
    text = format_job_detail(data, 2936697)
    assert "6月28、29、30日" in text
    assert "08:00-08:30" in text
    assert "按标准制作饮品" in text
    assert "咖啡拉花" in text
    assert "全国范围招聘" in text
    assert "155****0001" in text
    assert format_job_schedule(data).startswith("工作日期：")
    assert "技能：咖啡拉花" in format_job_basic_requirements(data)


if __name__ == "__main__":
    tests = [
        test_getbasicinfo_action_result_format,
        test_getbasicinfo_legacy_format,
        test_getbasicinfo_missing_data,
        test_allow_orders_action_result,
        test_jobentry_failure_message,
        test_skill_list_action_result,
        test_worker_balance_action_result_format,
        test_order_list_action_result_format,
        test_work_preferences_helpers,
        test_job_detail_action_result_format,
    ]
    for test in tests:
        test()
        print(f"✅ {test.__name__}")
    print(f"\n全部 {len(tests)} 项测试通过")

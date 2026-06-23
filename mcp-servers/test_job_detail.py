"""岗位详情路由与格式化测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.job_detail import (
    format_crowd_task_detail,
    format_jd_job_detail,
    normalize_job_type,
)
from tools.job_recommend import JOB_TYPE_CROWD, JOB_TYPE_HOURLY


def test_normalize_job_type():
    assert normalize_job_type("众包") == JOB_TYPE_CROWD
    assert normalize_job_type("小时工") == JOB_TYPE_HOURLY


def test_format_jd_job_detail_with_type():
    data = {
        "position_title": "诚招 咖啡师0611a",
        "salary": 13.0,
        "salary_unit_str": "元/小时",
        "work_address": "全国范围招聘",
        "recruit_number": 2,
        "industry_name": "餐饮服务",
        "work_date": "6月28、29、30日",
        "work_time": "08:00-08:30",
        "position_desc": "按标准制作饮品",
        "product_type": 5,
    }
    text = format_jd_job_detail(data, 2936697, JOB_TYPE_HOURLY)
    assert "【小时工】" in text
    assert "6月28、29、30日" in text
    assert "按标准制作饮品" in text


def test_format_crowd_task_detail():
    data = {
        "id": 18969,
        "order_code": "RW26140774530AD7",
        "spu_name": "助诊助老",
        "service_project_name": "RTEST服务项目",
        "settle_amount": 300.0,
        "quantity": 1,
        "unit_name": "个",
        "expected_date_str": "01月05日 08:30",
        "task_address": "北京市朝阳区大柳树路世纪东方嘉园212号楼3号",
        "spu_description": "上门助诊",
        "service_remark": "被服务人：陈国伟<br/>服务地址：北京市朝阳区大柳树路",
        "customer_phone": "15811111111",
    }
    text = format_crowd_task_detail(data, 18969)
    assert "【众包工】" in text
    assert "RW26140774530AD7" in text
    assert "¥300.0/个" in text
    assert "158****1111" in text
    assert "陈国伟" in text


if __name__ == "__main__":
    for fn in (
        test_normalize_job_type,
        test_format_jd_job_detail_with_type,
        test_format_crowd_task_detail,
    ):
        fn()
        print(f"PASS {fn.__name__}")

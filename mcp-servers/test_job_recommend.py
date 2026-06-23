"""job_recommend 推荐优先级单元测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.job_recommend import (
    JOB_TYPE_CROWD,
    JOB_TYPE_HOURLY,
    JOB_TYPE_PIECE,
    JOB_TYPE_POSITION,
    bucket_jd_jobs,
    classify_jd_job,
    merge_priority_buckets,
    normalize_city,
)


def test_normalize_city():
    assert normalize_city("北京") == "北京市"
    assert normalize_city("北京市") == "北京市"


def test_classify_jd_job():
    assert classify_jd_job({"product_type": 4, "salary_unit_str": "元/小时"}) == JOB_TYPE_HOURLY
    assert classify_jd_job({"product_type": 6, "position_title": "分拣计件"}) == JOB_TYPE_PIECE
    assert classify_jd_job({"product_type": 5, "salary_unit_str": "元/小时", "position_title": "传菜员"}) == JOB_TYPE_HOURLY
    assert classify_jd_job({"product_type": 5, "salary_unit_str": "元/天", "position_title": "面点师"}) == JOB_TYPE_POSITION


def test_merge_priority_order():
    merged = merge_priority_buckets(
        hourly=[{"id": 1, "position_title": "小时工A", "salary_unit_str": "元/小时", "salary": 20}],
        piece=[{"id": 2, "position_title": "计件B", "product_type": 6, "salary": 1, "unit_name": "件"}],
        crowd=[{"id": 3, "spu_name": "众包C", "settle_amount": 10, "unit_name": "次"}],
        position=[{"id": 4, "position_title": "岗位D", "salary_unit_str": "元/天", "salary": 100}],
        page_size=10,
    )
    assert [t for t, _ in merged] == [JOB_TYPE_HOURLY, JOB_TYPE_PIECE, JOB_TYPE_CROWD, JOB_TYPE_POSITION]


def test_bucket_jd_jobs():
    buckets = bucket_jd_jobs(
        [
            {"id": 1, "salary_unit_str": "元/小时", "salary": 13, "position_title": "传菜"},
            {"id": 2, "salary_unit_str": "元/天", "salary": 140, "position_title": "面点"},
        ]
    )
    assert len(buckets[JOB_TYPE_HOURLY]) == 1
    assert len(buckets[JOB_TYPE_POSITION]) == 1


if __name__ == "__main__":
    for fn in [test_normalize_city, test_classify_jd_job, test_merge_priority_order, test_bucket_jd_jobs]:
        fn()
        print(f"✅ {fn.__name__}")
    print("\n全部测试通过")

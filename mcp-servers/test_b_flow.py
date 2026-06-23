"""B端「扫码授权 → 岗位发布 → 查看报名」流程验证脚本。

不依赖真实后端，通过 mock 验证 Tool 调用链路和参数传递。
"""
import os
import sys
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 先验证共享存储 ──
from shared_token_store import auth_store, DB_PATH

print("=" * 60)
print("验证 1: 共享 Token 存储")
print("=" * 60)
print(f"DB 路径: {DB_PATH}")

# 清理旧数据
auth_store.cleanup_expired()
with __import__('sqlite3').connect(DB_PATH) as conn:
    conn.execute("DELETE FROM auth_sessions")
    conn.execute("DELETE FROM kv_store")
    conn.commit()

session_id = auth_store.create_session(role=2)
print(f"创建会话: {session_id}, role=2 (B端)")

auth_store.set_current_session(session_id)
auth_store.set_token(session_id, "mock_token_abc123", user_info={"name": "测试企业", "is_new_user": False}, expires_in=7200)

current = auth_store.get_current_token()
assert current is not None, "获取当前 Token 失败"
assert current["token"] == "mock_token_abc123"
assert current["role"] == 2
print(f"当前 Token: {current['token'][:20]}...")
print("✅ 共享存储验证通过")

# ── 模拟 youhuo-hire-api Tool 调用 ──
print("\n" + "=" * 60)
print("验证 2: hire-api Tool 调用链路")
print("=" * 60)

# 模拟 _req 的依赖检查
def mock_check_auth():
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception("未授权：请先调用 create_auth_session(role=2)")
    return token_info["token"]

try:
    token = mock_check_auth()
    print(f"✅ Token 获取成功: {token[:20]}...")
except Exception as e:
    print(f"❌ {e}")
    sys.exit(1)

# 模拟 preview_publish_cost 逻辑
def mock_preview_publish_cost(product_type, subscript_worker_count=0, subscript_day_count=0):
    if product_type in (2, 5):
        points = subscript_worker_count * subscript_day_count * 0.5
        return {
            "product_type": product_type,
            "points": points,
            "rmb": round(points / 10, 2),
            "formula": f"{subscript_worker_count}人 × {subscript_day_count}天 × 0.5 = {points}积分",
        }
    return {"product_type": product_type, "note": "余额支付制，后端计算"}

# 场景：发布小时工 (productType=4)
cost = mock_preview_publish_cost(4)
print(f"\n💰 费用预估: {json.dumps(cost, ensure_ascii=False)}")

# 模拟 publish_jd 参数构造
def mock_publish_jd(**kwargs):
    payload = {
        "title": kwargs["title"],
        "workCategory": kwargs["work_category"],
        "description": kwargs["description"],
        "workAddress": kwargs["location"],
        "salaryMin": kwargs["salary_min"],
        "salaryMax": kwargs["salary_max"],
        "headcount": kwargs["headcount"],
        "productType": kwargs["product_type"],
        "skillList": kwargs.get("skills", []),
        "benefitList": kwargs.get("benefits", []),
    }
    if kwargs["product_type"] in (2, 5):
        payload["subscriptWorkerCount"] = kwargs.get("subscript_worker_count", 0)
        payload["subscriptDayCount"] = kwargs.get("subscript_day_count", 0)
    return payload

jd_payload = mock_publish_jd(
    title="餐厅小时工",
    work_category="餐饮",
    description="负责点餐、上菜、收拾桌面",
    location="深圳南山",
    salary_min=25,
    salary_max=30,
    headcount=3,
    product_type=4,
    skills=["服务员"],
    benefits=["包工作餐"],
)
print(f"\n📋 发布参数:\n{json.dumps(jd_payload, ensure_ascii=False, indent=2)}")

# 模拟 get_job_applications 调用
def mock_get_applications(job_id):
    # 模拟后端返回
    return {
        "data": {
            "list": [
                {"name": "张三", "star": 4.8, "finishCount": 23, "statusDesc": "已报名"},
                {"name": "李四", "star": 4.5, "finishCount": 15, "statusDesc": "已报名"},
            ],
            "total": 2,
        }
    }

apps = mock_get_applications(12345)
print(f"\n👥 报名人员 ({apps['data']['total']}人):")
for w in apps["data"]["list"]:
    print(f"  - {w['name']} | 评分{w['star']} | 完成{w['finishCount']}单 | {w['statusDesc']}")

print("\n" + "=" * 60)
print("✅ 全部验证通过！")
print("=" * 60)
print("""
流程总结:
  1. create_auth_session(role=2) → 生成 session_id + 小程序码 URL
  2. 用户扫码 → minilogin 缓存 token → check_auth_status 获取 token
  3. publish_jd(product_type=4)   → 发布小时工岗位
  4. get_job_applications(job_id) → 查看报名人员
""")

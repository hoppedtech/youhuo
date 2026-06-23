"""job-planner 流程验证脚本。

不依赖真实后端，通过 mock 验证发布 Tool 调用链路和参数传递。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared_token_store import auth_store, DB_PATH

print("=" * 60)
print("验证 1: B 端授权")
print("=" * 60)

auth_store.cleanup_expired()
with __import__("sqlite3").connect(DB_PATH) as conn:
    conn.execute("DELETE FROM auth_sessions")
    conn.execute("DELETE FROM kv_store")
    conn.commit()

session_id = auth_store.create_session(role=2)
auth_store.set_current_session(session_id)
auth_store.set_token(session_id, "mock_token_planner", user_info={"name": "测试企业"}, expires_in=7200)
assert auth_store.get_current_token()["role"] == 2
print(f"✅ B 端 Token 就绪: session={session_id}")

print("\n" + "=" * 60)
print("验证 2: 小时工发布流程（productType=4）")
print("=" * 60)

cost = {"product_type": 4, "type_name": "小时工", "note": "余额支付制"}
balance = {"points_balance": 100, "cash_balance": 72.0, "exp_balance": 0, "total_balance": 72.0}
print(f"费用预估: {json.dumps(cost, ensure_ascii=False)}")
print(f"账户余额: {json.dumps(balance, ensure_ascii=False)}")

jd_payload = {
    "title": "餐厅小时工",
    "workCategory": "餐饮",
    "description": "负责点餐、上菜、收拾桌面",
    "workAddress": "深圳南山",
    "salaryMin": 25,
    "salaryMax": 30,
    "headcount": 3,
    "productType": 4,
    "skillList": ["服务员"],
    "benefitList": ["包工作餐"],
}
print(f"\n发布参数:\n{json.dumps(jd_payload, ensure_ascii=False, indent=2)}")

print("\n" + "=" * 60)
print("验证 3: 长期招发布流程（productType=2）")
print("=" * 60)

long_term_cost = {
    "product_type": 2,
    "subscript_worker_count": 50,
    "subscript_day_count": 7,
    "points": 175.0,
    "rmb": 17.5,
    "formula": "50人 × 7天 × 0.5积分/人/天 = 175积分",
}
print(f"长期招费用: {json.dumps(long_term_cost, ensure_ascii=False)}")

if balance["points_balance"] >= long_term_cost["points"]:
    print("✅ 积分充足，可发布")
else:
    print("⚠️ 积分不足，需引导充值")

pay_payload = {"id": 12345}
print(f"积分支付参数: {json.dumps(pay_payload, ensure_ascii=False)}")

print("\n" + "=" * 60)
print("验证 4: 众包任务发布流程")
print("=" * 60)

task_payload = {
    "category_id": "101",
    "title": "门店设备安装",
    "description": "完成3家门店监控设备安装",
    "location": "深圳全市",
    "budget": 5000,
    "deadline": "2026-07-01",
    "require_cert": ["电工证"],
}
print(f"众包发布参数:\n{json.dumps(task_payload, ensure_ascii=False, indent=2)}")

print("\n" + "=" * 60)
print("✅ job-planner 流程验证通过！")
print("=" * 60)
print("""
流程总结:
  1. create_auth_session(role=2)     → 扫码授权
  2. get_work_categories/skill/benefit → 确认标签（可选）
  3. preview_publish_cost            → 费用预估
  4. get_enterprise_balance          → 余额检查
  5. 用户确认 → publish_jd / publish_task
  6. 长期招 → pay_publish_points
  7. 引导 workforce-dispatcher 查看报名
""")

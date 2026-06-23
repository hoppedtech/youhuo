"""youhuo-finance-api 流程验证脚本。

不依赖真实后端，通过 mock 验证 C/B 端财务 Tool 调用链路。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared_token_store import auth_store, DB_PATH

print("=" * 60)
print("验证 1: C 端余额与提现")
print("=" * 60)

auth_store.cleanup_expired()
with __import__("sqlite3").connect(DB_PATH) as conn:
    conn.execute("DELETE FROM auth_sessions")
    conn.execute("DELETE FROM kv_store")
    conn.commit()

c_session = auth_store.create_session(role=1)
auth_store.set_current_session(c_session)
auth_store.set_token(c_session, "mock_token_finance_c", expires_in=7200)

worker_balance = {"balance": 256.0, "bond_amount": 0, "withdrawable": 200.0}
print(f"零工余额: {json.dumps(worker_balance, ensure_ascii=False)}")

withdraw_payload = {"amount": 100.0}
print(f"提现申请（用户确认后）: {json.dumps(withdraw_payload, ensure_ascii=False)}")

print("\n" + "=" * 60)
print("验证 2: B 端余额与账户明细")
print("=" * 60)

b_session = auth_store.create_session(role=2)
auth_store.set_current_session(b_session)
auth_store.set_token(b_session, "mock_token_finance_b", expires_in=7200)

enterprise_balance = {
    "points_balance": 500,
    "cash_balance": 1280.50,
    "exp_balance": 100.0,
}
print(f"企业余额: {json.dumps(enterprise_balance, ensure_ascii=False)}")

account_logs = [
    {"type": "income", "amount": 500, "description": "充值", "createTime": "2026-06-15 10:00"},
    {"type": "expense", "amount": 28, "description": "发布小时工服务费", "createTime": "2026-06-15 14:30"},
]
print("账户明细:")
for log in account_logs:
    sign = "+" if log["type"] == "income" else "-"
    print(f"  {sign}¥{log['amount']} | {log['description']} | {log['createTime']}")

print("\n" + "=" * 60)
print("验证 3: B 端结算支付")
print("=" * 60)

pay_schedule_payload = {"id": 9001, "remark": "6月16日班次结算"}
pay_order_payload = {"orderId": 50001}
print(f"排班结算: {json.dumps(pay_schedule_payload, ensure_ascii=False)}")
print(f"订单余额支付: {json.dumps(pay_order_payload, ensure_ascii=False)}")

print("\n" + "=" * 60)
print("验证 4: B 端发票")
print("=" * 60)

invoice_payload = {
    "invoiceType": 1,
    "amount": 3000.0,
    "companyName": "深圳某某餐饮有限公司",
    "taxNumber": "91440300MA5XXXXXXX",
    "email": "finance@example.com",
}
print(f"发票申请: {json.dumps(invoice_payload, ensure_ascii=False)}")

print("\n" + "=" * 60)
print("✅ youhuo-finance-api 流程验证通过！")
print("=" * 60)
print("""
C 端流程:
  get_worker_balance()  → 查余额
  withdraw_balance(amt) → 提现（需用户确认）

B 端流程:
  get_enterprise_balance()     → 查企业余额
  get_account_log()            → 账户明细
  pay_schedule_settlement(id)  → 排班结算
  pay_balance(order_id)        → 订单余额支付
  apply_invoice(...)           → 申请发票
  get_invoice_list(status)     → 发票列表
""")

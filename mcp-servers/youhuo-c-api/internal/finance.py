"""有活平台结算与支付 MCP Server。

覆盖 C 端零工余额/提现、B 端企业余额/发票/结算支付等能力。
双端共用，根据扫码授权时的 role 自动选择对应 API 网关。
"""
import os
import sys
import json
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared_token_store import auth_store
from tools.api_response import api_data, api_message, api_ok, parse_worker_balance
from tools.youhuo_env import applet_base_url

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

mcp = FastMCP("youhuo-finance-api")

BASE_URL = applet_base_url()
EMPLOY_URL = os.getenv(
    "YOUHUO_EMPLOY_URL",
    "https://hopped-gateway-service-sops-test.hopped.com.cn/hopped-miniprogram-web/api/",
)


def _require_auth(required_role: int | None = None) -> dict:
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        api_name = "youhuo-b-api" if (required_role or 1) == 2 else "youhuo-c-api"
        raise Exception(
            f"未授权：请先调用 {api_name}.create_auth_session() "
            "完成扫码授权，再执行此操作"
        )
    if required_role is not None and token_info.get("role") != required_role:
        role_name = "招工方(B端)" if required_role == 2 else "找活方(C端)"
        raise Exception(f"当前授权角色不匹配，此操作需要 {role_name} 授权")
    return token_info


async def _req_c(method: str, path: str, **kwargs):
    token_info = _require_auth(required_role=1)
    headers = {
        "Authorization": f"Bearer {token_info['token']}",
        "Content-Type": "application/json",
        "X-USER_ROLE": "1",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _req_b(method: str, path: str, **kwargs):
    token_info = _require_auth(required_role=2)
    headers = {
        "Authorization": f"Bearer {token_info['token']}",
        "Content-Type": "application/json",
        "X-USER_ROLE": "2",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{EMPLOY_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


# ──── C 端：零工余额 / 提现 ────

@mcp.tool()
async def get_worker_balance() -> str:
    """查询零工账户余额详情（C 端）。

    对应接口: Account/GetAccountAmount (GET)

    需 C 端授权 role=1。
    """
    try:
        result = await _req_c("GET", "Account/GetAccountAmount")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    data = api_data(result)
    balance_info = parse_worker_balance(data)
    balance = balance_info["balance"]
    bond = balance_info["bond_amount"]
    withdrawable = balance_info["withdrawable"]
    return json.dumps(
        {
            "balance": balance,
            "bond_amount": bond,
            "withdrawable": withdrawable,
            "summary": (
                f"账户余额：¥{balance}\n"
                f"保证金：¥{bond}\n"
                f"可提现：¥{withdrawable}"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def withdraw_balance(amount: float) -> str:
    """零工发起提现（C 端）。

    对应接口: Account/Withdraw (POST)

    AI 不代用户确认提现，调用前须获得用户明确确认金额。

    Args:
        amount: 提现金额（元）

    需 C 端授权 role=1。
    """
    if amount <= 0:
        return json.dumps({"success": False, "error": "提现金额必须大于 0"}, ensure_ascii=False)

    payload = {"amount": amount}
    try:
        result = await _req_c("POST", "Account/Withdraw", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if api_ok(result):
        return json.dumps(
            {"success": True, "amount": amount, "message": f"✅ 提现申请已提交，金额 ¥{amount}"},
            ensure_ascii=False,
        )
    return json.dumps({"success": False, "error": api_message(result, "提现失败")}, ensure_ascii=False)


# ──── B 端：企业余额 / 明细 ────

@mcp.tool()
async def get_enterprise_balance() -> str:
    """查询企业账户余额（积分 + 现金 + 体验金，B 端）。

    对应接口: miniprogram/account/balance (GET)

    需 B 端授权 role=2。
    """
    try:
        result = await _req_b("GET", "miniprogram/account/balance")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    data = result.get("data", {})
    return json.dumps(
        {
            "points_balance": data.get("pointsBalance", data.get("points", 0)),
            "cash_balance": data.get("cashBalance", 0),
            "exp_balance": data.get("expBalance", data.get("trialAmount", 0)),
            "total_balance": data.get("totalBalance", 0),
            "summary": (
                f"积分余额：{data.get('pointsBalance', data.get('points', 0))} 分\n"
                f"现金余额：¥{data.get('cashBalance', 0)}\n"
                f"体验金：¥{data.get('expBalance', data.get('trialAmount', 0))}"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def get_account_log(page: int = 1, page_size: int = 20) -> str:
    """获取企业账户资金明细（B 端积分/现金流水）。

    对应接口: account/log/getUserAccountLogPageList (POST)

    Args:
        page: 页码
        page_size: 每页数量

    需 B 端授权 role=2。
    """
    payload = {"pageNum": page, "pageSize": page_size}
    try:
        result = await _req_b("POST", "account/log/getUserAccountLogPageList", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    items = result.get("data", {}).get("list", [])
    total = result.get("data", {}).get("total", 0)
    if not items:
        return "暂无账户明细。"

    lines = [f"账户明细（共{total}条）：\n"]
    for log in items:
        log_type = log.get("type", "")
        sign = "+" if log_type in ("income", "1", 1) else "-"
        amount = log.get("amount", 0)
        desc = log.get("description") or log.get("remark") or log.get("typeDesc", "—")
        lines.append(f"{sign}¥{amount} | {desc} | {log.get('createTime', '')}")
    return "\n".join(lines)


# ──── B 端：结算支付 ────

@mcp.tool()
async def pay_schedule_settlement(detail_id: int, remark: str = "") -> str:
    """支付排班明细结算款（B 端向零工结算）。

    对应接口: recruitWorkingScheduleDetail/pay (POST)

    发布前须获得用户对结算金额和对象的明确确认。

    Args:
        detail_id: 排班明细 ID（来自 workforce-dispatcher 的 get_schedule_detail_list）
        remark: 结算备注

    需 B 端授权 role=2。
    """
    payload = {"id": detail_id}
    if remark:
        payload["remark"] = remark
    try:
        result = await _req_b("POST", "recruitWorkingScheduleDetail/pay", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        return f"✅ 排班明细 {detail_id} 结算支付成功"
    msg = result.get("message", "结算失败")
    if "余额" in msg or "不足" in msg:
        return json.dumps(
            {
                "success": False,
                "reason": "BALANCE_INSUFFICIENT",
                "message": msg,
                "guide": "账户余额不足，请前往有活小程序充值后再结算。",
            },
            ensure_ascii=False,
        )
    return json.dumps({"success": False, "error": msg}, ensure_ascii=False)


@mcp.tool()
async def pay_balance(order_id: int) -> str:
    """小时工/计件工订单余额支付（B 端）。

    对应接口: account/balance-payment (POST)

    Args:
        order_id: 订单 ID

    需 B 端授权 role=2。
    """
    payload = {"orderId": order_id}
    try:
        result = await _req_b("POST", "account/balance-payment", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        return f"✅ 订单 {order_id} 余额支付成功"
    msg = result.get("message", "支付失败")
    if "余额" in msg or "不足" in msg:
        return json.dumps(
            {
                "success": False,
                "reason": "BALANCE_INSUFFICIENT",
                "message": msg,
                "guide": "账户余额不足，请前往有活小程序充值。",
            },
            ensure_ascii=False,
        )
    return json.dumps({"success": False, "error": msg}, ensure_ascii=False)


# ──── B 端：发票管理 ────

@mcp.tool()
async def apply_invoice(
    invoice_type: int,
    amount: float,
    company_name: str,
    tax_number: str,
    email: str,
) -> str:
    """申请开具发票（B 端用工方）。

    对应接口: invoiceInfo/applyInvoice (POST)

    调用前须向用户确认开票信息。

    Args:
        invoice_type: 发票类型 1=增值税普通发票 2=增值税专用发票
        amount: 开票金额（元）
        company_name: 公司名称
        tax_number: 税务登记号
        email: 接收发票的邮箱

    需 B 端授权 role=2。
    """
    if invoice_type not in (1, 2):
        return json.dumps({"success": False, "error": "invoice_type 必须为 1 或 2"}, ensure_ascii=False)
    if amount <= 0:
        return json.dumps({"success": False, "error": "开票金额必须大于 0"}, ensure_ascii=False)

    payload = {
        "invoiceType": invoice_type,
        "amount": amount,
        "companyName": company_name,
        "taxNumber": tax_number,
        "email": email,
    }
    try:
        result = await _req_b("POST", "invoiceInfo/applyInvoice", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        return f"✅ 发票申请成功，金额 ¥{amount}，将发送至 {email}"
    return json.dumps({"success": False, "error": result.get("message", "申请失败")}, ensure_ascii=False)


@mcp.tool()
async def get_invoice_list(status: str = "pending", page: int = 1, page_size: int = 20) -> str:
    """查询发票申请列表（B 端）。

    对应接口:
    - pending: invoiceInfo/list (POST)
    - issued: invoiceInfo/selectInvoice (POST)

    Args:
        status: pending=待开票 | issued=已开票
        page: 页码
        page_size: 每页数量

    需 B 端授权 role=2。
    """
    payload = {"pageNum": page, "pageSize": page_size}
    path = "invoiceInfo/list" if status == "pending" else "invoiceInfo/selectInvoice"
    status_label = "待开票" if status == "pending" else "已开票"

    try:
        result = await _req_b("POST", path, json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    items = result.get("data", {}).get("list", [])
    total = result.get("data", {}).get("total", 0)
    if not items:
        return f"暂无{status_label}发票记录。"

    lines = [f"发票列表（{status_label}，共{total}条）：\n"]
    for inv in items:
        lines.append(
            f"🧾 ¥{inv.get('amount', 0)} | "
            f"{inv.get('companyName', '—')} | "
            f"{inv.get('createTime', '')}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")

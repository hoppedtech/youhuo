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
from tools.youhuo_env import applet_base_url, employ_base_url
from tools.api_response import api_ok, api_message
from tools.enterprise_balance import (
    build_enterprise_balance_view,
    parse_user_profile,
    unwrap_balance_payload,
)
from tools.account_log import (
    ACCOUNT_TYPE_LABELS,
    build_account_log_payload,
    filter_logs_by_days,
    flatten_account_log_records,
    format_account_log_section,
    resolve_account_type,
    resolve_log_change_type,
)
from tools.mcp_write_guard import WriteGate

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

mcp = FastMCP("youhuo-finance-api")

BASE_URL = applet_base_url()
EMPLOY_URL = employ_base_url()


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

    data = result.get("data", {})
    return json.dumps(
        {
            "balance": data.get("balance", 0),
            "bond_amount": data.get("bondAmount", data.get("bond_amount", 0)),
            "withdrawable": data.get("withdrawable", data.get("withdrawableAmount", 0)),
            "summary": (
                f"可提现余额：¥{data.get('balance', 0)}\n"
                f"保证金：¥{data.get('bondAmount', data.get('bond_amount', 0))}\n"
                f"可提现：¥{data.get('withdrawable', data.get('withdrawableAmount', 0))}"
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

    if result.get("code") == 200:
        return json.dumps(
            {"success": True, "amount": amount, "message": f"✅ 提现申请已提交，金额 ¥{amount}"},
            ensure_ascii=False,
        )
    return json.dumps({"success": False, "error": result.get("message", "提现失败")}, ensure_ascii=False)


# ──── B 端：企业余额 / 明细 ────

FINANCE_SECTIONS = frozenset({"balance", "log"})


def _parse_finance_sections(sections: str) -> set[str] | None:
    raw = (sections or "all").strip().lower()
    if raw in ("all", "*", ""):
        return set(FINANCE_SECTIONS)
    selected = {s.strip().lower() for s in raw.replace("，", ",").split(",") if s.strip()}
    unknown = selected - FINANCE_SECTIONS
    if unknown:
        return None
    return selected


async def _fetch_enterprise_balance_view() -> dict:
    balance_result = await _req_b("POST", "miniprogram/account/balance", json={})
    balance = unwrap_balance_payload(balance_result)
    if not balance and not api_ok(balance_result):
        raise Exception(api_message(balance_result, "查询余额失败"))
    profile: dict = {}
    try:
        profile_result = await _req_b("GET", "user/login/getUserLoginDetail")
        profile = parse_user_profile(profile_result)
    except Exception:
        pass
    return build_enterprise_balance_view(balance, profile)


async def _fetch_account_log_section(
    page: int,
    page_size: int,
    *,
    days: int = 0,
    log_type: str = "all",
    account_type: int = 0,
    balance_view: dict | None = None,
) -> dict:
    acct = resolve_account_type(account_type, balance_view)
    change_type = resolve_log_change_type(log_type)
    payload = build_account_log_payload(
        account_type=acct,
        change_type=change_type,
        page=page,
        page_size=page_size,
    )
    result = await _req_b("POST", "account/log/getUserAccountLogPageList", json=payload)
    data = result.get("data") or {}
    records = data.get("records") or data.get("list") or []
    api_total = data.get("total", 0)
    flat = flatten_account_log_records(records)
    if days > 0:
        flat = filter_logs_by_days(flat, days)
        flat.sort(key=lambda x: x.get("createTime") or "", reverse=True)
    section = format_account_log_section(
        flat,
        days=days,
        log_type=log_type,
        account_type=acct,
        total=api_total,
    )
    section["account_type"] = acct
    section["account_type_label"] = ACCOUNT_TYPE_LABELS.get(acct, str(acct))
    section["log_type"] = log_type
    section["days"] = days
    return section


@mcp.tool()
async def get_enterprise_finance(
    sections: str = "all",
    page: int = 1,
    page_size: int = 50,
    format: str = "json",
    days: int = 0,
    log_type: str = "all",
    account_type: int = 0,
) -> str:
    """查询 B 端企业财务（余额 / 账户流水）。

    Args:
        sections: all 或逗号分隔：balance, log
        page: log 区段页码
        page_size: log 区段每页数量（days>0 时建议 50–100）
        format: json（默认）或 text（人类可读摘要）
        days: 最近 N 天流水筛选，0=不限日期（仍受 page_size 约束）
        log_type: all（全部）| expense/income 或 支出/收入
        account_type: 0=按登录类型自动（个人余额8/企业余额9）；或 8/9/3/10

    需 B 端授权 role=2。
    """
    selected = _parse_finance_sections(sections)
    if selected is None:
        return json.dumps(
            {
                "success": False,
                "error": f"sections 未知项，可选：{', '.join(sorted(FINANCE_SECTIONS))} 或 all",
            },
            ensure_ascii=False,
        )

    out: dict = {"success": True}
    text_parts: list[str] = []
    balance_view: dict | None = None

    try:
        if "balance" in selected:
            balance_view = await _fetch_enterprise_balance_view()
            out["balance"] = balance_view
            text_parts.append(json.dumps(balance_view, ensure_ascii=False, indent=2))
        if "log" in selected:
            if balance_view is None:
                try:
                    balance_view = await _fetch_enterprise_balance_view()
                except Exception:
                    balance_view = None
            try:
                resolve_log_change_type(log_type)
            except ValueError as e:
                return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
            log_section = await _fetch_account_log_section(
                page,
                page_size,
                days=days,
                log_type=log_type,
                account_type=account_type,
                balance_view=balance_view,
            )
            out["log"] = {
                "items": log_section["items"],
                "total": log_section["total"],
                "sum_amount": log_section.get("sum_amount", 0),
                "days": days,
                "log_type": log_type,
                "account_type": log_section.get("account_type"),
                "account_type_label": log_section.get("account_type_label"),
            }
            text_parts.append(log_section["text"])
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if (format or "json").strip().lower() == "text":
        return "\n\n".join(text_parts) if text_parts else "暂无财务数据。"
    if selected == {"balance"} and "balance" in out:
        return json.dumps({"success": True, **out["balance"]}, ensure_ascii=False, indent=2)
    return json.dumps(out, ensure_ascii=False, indent=2)


# ──── B 端：结算支付 ────

@mcp.tool()
async def pay_schedule_settlement(
    detail_id: int,
    remark: str = "",
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """支付排班明细结算款（B 端向零工结算）。

    对应接口: recruitWorkingScheduleDetail/pay (POST)

    ⚠️ 调用约束：须先通过 get_job_schedules(schedule_id>0) 展示零工、工时与结算金额，
    并查 get_enterprise_finance(sections=balance)；向企业用户确认对象与金额后再调用；须 user_confirmed=true。
    禁止代充值。

    Args:
        detail_id: 排班明细 ID（来自 workforce-dispatcher 的 get_job_schedules）
        remark: 结算备注
        user_confirmed: 必须为 true
        confirmation_summary: 可选，用户确认原话摘要

    需 B 端授权 role=2。
    """
    g = WriteGate(
        "pay_schedule_settlement",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        detail_id=detail_id,
        remark=remark,
    )
    if g.blocked:
        return g.blocked

    payload = {"id": detail_id}
    if remark:
        payload["remark"] = remark
    try:
        result = await _req_b("POST", "recruitWorkingScheduleDetail/pay", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if api_ok(result):
        return g.finish(f"✅ 排班明细 {detail_id} 结算支付成功")
    msg = api_message(result, "结算失败")
    if "余额" in msg or "不足" in msg:
        return g.finish(
            json.dumps(
                {
                    "success": False,
                    "reason": "BALANCE_INSUFFICIENT",
                    "message": msg,
                    "guide": "账户余额不足，请前往有活小程序充值后再结算。",
                },
                ensure_ascii=False,
            ),
        )
    return g.finish(json.dumps({"success": False, "error": msg}, ensure_ascii=False))


@mcp.tool()
async def pay_balance(
    order_id: int,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """小时工/计件工订单余额支付（B 端，非发布后支付）。

    对应接口: account/balance-payment (POST)

    ⚠️ 发布小时工/计件工后的支付请使用 hire 模块的 `pay_hourly_job(job_id)`。
    本 Tool 用于其他 orderId 类订单场景。

    ⚠️ 调用约束：须向企业用户展示订单号与支付金额，获明确确认后再调用；
    须 user_confirmed=true + confirm_token。余额不足时引导小程序充值，禁止代充值。

    Args:
        order_id: 订单 ID（非 publish_jd 返回的 jd_id）
        user_confirmed: 必须为 true
        confirmation_summary: 可选，用户确认原话摘要

    需 B 端授权 role=2。
    """
    g = WriteGate(
        "pay_balance",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        order_id=order_id,
    )
    if g.blocked:
        return g.blocked

    payload = {"orderId": order_id}
    try:
        result = await _req_b("POST", "account/balance-payment", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if result.get("code") == 200:
        return g.finish(f"✅ 订单 {order_id} 余额支付成功")
    msg = result.get("message", "支付失败")
    if "余额" in msg or "不足" in msg:
        return g.finish(
            json.dumps(
                {
                    "success": False,
                    "reason": "BALANCE_INSUFFICIENT",
                    "message": msg,
                    "guide": "账户余额不足，请前往有活小程序充值。",
                },
                ensure_ascii=False,
            ),
        )
    return g.finish(json.dumps({"success": False, "error": msg}, ensure_ascii=False))


# ──── B 端：发票管理 ────

async def _format_invoice_list(status: str, page: int, page_size: int) -> str:
    payload = {"pageNum": page, "pageSize": page_size}
    path = "invoiceInfo/list" if status == "pending" else "invoiceInfo/selectInvoice"
    status_label = "待开票" if status == "pending" else "已开票"
    result = await _req_b("POST", path, json=payload)
    data = result.get("data") or {}
    items = data.get("list") or []
    total = data.get("total") or 0
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


@mcp.tool()
async def manage_invoice(
    action: str,
    status: str = "pending",
    page: int = 1,
    page_size: int = 20,
    invoice_type: int = 1,
    amount: float = 0,
    company_name: str = "",
    tax_number: str = "",
    email: str = "",
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """发票管理（list / apply）。

    Args:
        action: list（查询列表，只读）| apply（申请开票，须 user_confirmed + confirm_token）
        status: list 时 pending=待开票 | issued=已开票
        page, page_size: list 时分页
        invoice_type: apply 时 1=普票 2=专票
        amount, company_name, tax_number, email: apply 时必填
        user_confirmed: apply 必须为 true
        confirm_token: apply 时 prepare_write_confirmation 返回的令牌

    需 B 端授权 role=2。
    """
    act = (action or "").strip().lower()
    if act not in ("list", "apply"):
        return json.dumps(
            {"success": False, "error": "action 须为 list 或 apply"},
            ensure_ascii=False,
        )

    if act == "list":
        if status not in ("pending", "issued"):
            return json.dumps(
                {"success": False, "error": "status 须为 pending 或 issued"},
                ensure_ascii=False,
            )
        try:
            return await _format_invoice_list(status, page, page_size)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    g = WriteGate(
        "manage_invoice",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        action=act,
        invoice_type=invoice_type,
        amount=amount,
        company_name=company_name,
        tax_number=tax_number,
        email=email,
    )
    if g.blocked:
        return g.blocked

    if invoice_type not in (1, 2):
        return g.finish(
            json.dumps({"success": False, "error": "invoice_type 必须为 1 或 2"}, ensure_ascii=False),
        )
    if amount <= 0:
        return g.finish(
            json.dumps({"success": False, "error": "开票金额必须大于 0"}, ensure_ascii=False),
        )
    if not company_name.strip() or not tax_number.strip() or not email.strip():
        return g.finish(
            json.dumps(
                {"success": False, "error": "apply 须提供 company_name、tax_number、email"},
                ensure_ascii=False,
            )
        )

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
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if result.get("code") == 200:
        return g.finish(f"✅ 发票申请成功，金额 ¥{amount}，将发送至 {email}")
    return g.finish(
        json.dumps({"success": False, "error": result.get("message", "申请失败")}, ensure_ascii=False),
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

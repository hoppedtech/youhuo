"""小时工/计件工发布后余额支付（对齐小程序 account/balance-payment）。"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from tools.api_response import api_data, api_message, api_ok

# 小程序 publishType：小时工=1，计件工=5
PUBLISH_TYPE_BY_PRODUCT: dict[int, int] = {
    4: 1,
    6: 5,
}

PAYMENT_TYPE_BALANCE = 1
PAYMENT_TYPE_WECHAT = 2


async def fetch_job_publish_order(
    req: Callable[..., Awaitable[dict]],
    job_id: int,
) -> dict[str, Any]:
    """GET hourly-worker/job-info/{job_id}/order"""
    result = await req("GET", f"hourly-worker/job-info/{job_id}/order")
    if not api_ok(result):
        raise ValueError(api_message(result, "获取岗位支付信息失败"))
    data = api_data(result)
    if not isinstance(data, dict):
        raise ValueError("岗位支付信息为空")
    return data


def publish_type_for_product(product_type: int) -> int:
    publish_type = PUBLISH_TYPE_BY_PRODUCT.get(product_type)
    if publish_type is None:
        raise ValueError(
            f"product_type={product_type} 不支持余额发布支付，"
            "仅小时工(4)/计件工(6)在 publish_jd 后需调用 pay_hourly_job"
        )
    return publish_type


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_payment_preview(job_id: int, order: dict[str, Any], *, product_type: int) -> dict[str, Any]:
    balance_payment = _to_float(order.get("balancePayment"))
    have_paid = _to_float(order.get("havePaidAmount"))
    labor = order.get("laborAmount")
    service_fee = order.get("serviceFeeAmount")
    type_name = "小时工" if product_type == 4 else "计件工" if product_type == 6 else str(product_type)
    return {
        "job_id": job_id,
        "product_type": product_type,
        "type_name": type_name,
        "labor_amount": labor,
        "service_fee_amount": service_fee,
        "balance_payment": balance_payment,
        "platform_service_rate": order.get("platformServiceRate"),
        "have_paid_amount": have_paid,
        "needs_payment": have_paid <= 0,
        "already_paid": have_paid > 0,
        "summary": (
            f"岗位 {job_id}（{type_name}）\n"
            f"工钱：¥{labor}，服务费：¥{service_fee}\n"
            f"应付合计：¥{balance_payment}，已付：¥{have_paid}"
        ),
    }


def build_balance_payment_payload(
    job_id: int,
    order: dict[str, Any],
    *,
    product_type: int,
    payment_type: int = PAYMENT_TYPE_BALANCE,
) -> dict[str, Any]:
    """构建 account/balance-payment 请求体（对齐小程序 savePay）。"""
    publish_type = publish_type_for_product(product_type)
    payload: dict[str, Any] = {
        "jobId": job_id,
        **order,
        "publishType": publish_type,
        "paymentType": payment_type,
    }
    balance_payment = order.get("balancePayment")
    if payment_type == PAYMENT_TYPE_WECHAT:
        payload["wxPayAmount"] = balance_payment
    else:
        payload["wxPayAmount"] = None
    return payload


def interpret_balance_payment_result(result: dict[str, Any], job_id: int) -> dict[str, Any]:
    if result.get("needWxPay"):
        return {
            "success": False,
            "reason": "WECHAT_PAY_REQUIRED",
            "message": "当前支付需微信收银台，MCP 不支持代拉起微信支付",
            "guide": "请前往有活小程序完成支付。",
            "job_id": job_id,
        }
    if api_ok(result):
        return {
            "success": True,
            "job_id": job_id,
            "message": "岗位发布支付成功，岗位已正式上架",
        }
    msg = api_message(result, "支付失败")
    if "余额" in msg or "不足" in msg:
        return {
            "success": False,
            "reason": "BALANCE_INSUFFICIENT",
            "message": msg,
            "guide": "账户余额不足，请前往有活小程序充值后再支付。",
            "job_id": job_id,
        }
    return {"success": False, "error": msg, "job_id": job_id}

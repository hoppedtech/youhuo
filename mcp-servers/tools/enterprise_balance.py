"""B 端账户余额解析（对齐 hopped-uni-client miniprogram/account/balance + getUserLoginDetail）。"""

import json


def unwrap_balance_payload(result: dict) -> dict:
    """解析 balance 接口 payload（兼容 data/Data 包装与直出）。"""
    if not isinstance(result, dict):
        return {}
    if any(
        k in result
        for k in ("rechargeBalance", "companyBalance", "trialBalance", "recruitDepositAmount")
    ):
        return result
    inner = result.get("data") or result.get("Data")
    if isinstance(inner, dict):
        return inner
    return {}


def parse_user_profile(result: dict) -> dict:
    if not isinstance(result, dict):
        return {}
    data = result.get("Data") or result.get("data")
    return data if isinstance(data, dict) else result


def _payable_balance(balance: dict, login_type: int | None, manager_role: int) -> tuple[str, float]:
    is_credit = bool(balance.get("isCredit"))
    is_sq = bool(balance.get("isSQ"))
    company = float(balance.get("companyBalance") or 0)
    credit = float(balance.get("creditBalance") or 0)
    personal = float(balance.get("rechargeBalance") or 0)

    if login_type == 3:
        if is_credit and not is_sq:
            return "企业授信余额", credit
        if manager_role == 0 and (is_sq or (is_credit and is_sq)):
            return "企业授权余额", company
        return "企业现金余额", company
    return "个人余额", personal


def build_enterprise_balance_view(balance: dict, user_profile: dict | None = None) -> dict:
    """将小程序 balance + 用户资料合并为 Agent 可读结构。"""
    profile = user_profile or {}
    login_type = profile.get("loginType") or profile.get("login_type")
    manager_role = int(profile.get("managerRole", profile.get("manager_role", 1)) or 1)

    account_detail = profile.get("accountNumDetail") or {}
    points = account_detail.get("totalNum", 0) if isinstance(account_detail, dict) else 0

    recruit_required = float(profile.get("recruitDepositAmount") or 0)
    recruit_paid = float(balance.get("recruitDepositAmount") or 0)
    pay_label, pay_amount = _payable_balance(balance, login_type, manager_role)

    login_desc = {2: "个人招工", 3: "企业招工"}.get(login_type, "未知")

    view = {
        "login_type": login_type,
        "login_type_desc": login_desc,
        "manager_role": manager_role,
        "points_balance": points,
        "recharge_balance": balance.get("rechargeBalance", 0),
        "trial_balance": balance.get("trialBalance", 0),
        "company_balance": balance.get("companyBalance", 0),
        "credit_balance": balance.get("creditBalance", 0),
        "is_credit": bool(balance.get("isCredit")),
        "is_authorized_quota": bool(balance.get("isSQ")),
        "company_balance_enabled": balance.get("companyBalanceEnabled", 1),
        "recruit_deposit_balance": recruit_paid,
        "recruit_deposit_required": recruit_required,
        "recruit_deposit_shortfall": max(0.0, recruit_required - recruit_paid),
        "recruit_deposit_pay_switch": profile.get("recruitDepositPaySwitch", 0),
        "primary_pay_balance": pay_amount,
        "primary_pay_balance_label": pay_label,
        # 向后兼容旧字段名（避免已有 Skill/脚本立刻报错）
        "cash_balance": balance.get("companyBalance", 0) if login_type == 3 else balance.get("rechargeBalance", 0),
        "exp_balance": balance.get("trialBalance", 0),
    }

    lines = [f"账户类型：{login_desc}"]
    lines.append(f"积分余额：{points} 分（长期招，来自用户信息）")
    if login_type == 3:
        lines.append(f"企业现金余额：¥{balance.get('companyBalance', 0)}")
        if view["is_credit"]:
            lines.append(f"企业授信余额：¥{balance.get('creditBalance', 0)}")
        if view["is_authorized_quota"]:
            lines.append(f"企业授权可用：¥{balance.get('companyBalance', 0)}")
    else:
        lines.append(f"个人余额：¥{balance.get('rechargeBalance', 0)}")
        lines.append(f"体验金：¥{balance.get('trialBalance', 0)}")
    if profile.get("recruitDepositPaySwitch") == 1 or recruit_required:
        lines.append(
            f"招工保证金：已缴 ¥{recruit_paid}，要求 ≥¥{recruit_required}"
            + (f"，还差 ¥{view['recruit_deposit_shortfall']}" if view["recruit_deposit_shortfall"] else "")
        )
    lines.append(f"发布/支付参考：{pay_label} ¥{pay_amount}")
    view["summary"] = "\n".join(lines)
    return view


def _balance_snapshot(view: dict) -> dict:
    return {
        "login_type_desc": view.get("login_type_desc"),
        "points_balance": view.get("points_balance"),
        "primary_pay_balance": view.get("primary_pay_balance"),
        "primary_pay_balance_label": view.get("primary_pay_balance_label"),
        "recharge_balance": view.get("recharge_balance"),
        "trial_balance": view.get("trial_balance"),
        "company_balance": view.get("company_balance"),
        "credit_balance": view.get("credit_balance"),
    }


def validate_balance_for_publish(view: dict, *, product_type: int) -> dict | None:
    """发布岗位前余额门禁。长期招查积分，其余查可用现金余额；须严格大于 0。

    Returns:
        拒绝时返回 error dict，通过时返回 None。
    """
    if product_type in (2, 5):
        amount = float(view.get("points_balance") or 0)
        label = "积分余额"
        unit = "分"
    else:
        amount = float(view.get("primary_pay_balance") or 0)
        label = view.get("primary_pay_balance_label") or "可用余额"
        unit = "元"

    if amount > 0:
        return None

    type_names = {2: "长期招", 5: "长期招", 4: "小时工", 6: "计件工"}
    return {
        "success": False,
        "code": "INSUFFICIENT_BALANCE",
        "error": (
            f"发布{type_names.get(product_type, '岗位')}前须账户{label}大于 0，"
            f"当前为 {amount}{unit}，已拒绝发布。"
        ),
        "balance_snapshot": _balance_snapshot(view),
        "guide": "请先调用 get_enterprise_finance(sections=balance) 查看明细，并引导用户在有活小程序充值后再发布。",
    }


def validate_balance_for_task_publish(view: dict, budget: float) -> dict | None:
    """发布众包任务前：预算与可用余额均须大于 0。"""
    if float(budget or 0) <= 0:
        return {
            "success": False,
            "code": "INVALID_BUDGET",
            "error": "众包任务预算须大于 0 元。",
        }
    amount = float(view.get("primary_pay_balance") or 0)
    label = view.get("primary_pay_balance_label") or "可用余额"
    if amount > 0:
        return None
    return {
        "success": False,
        "code": "INSUFFICIENT_BALANCE",
        "error": f"发布众包任务前须{label}大于 0，当前为 {amount}元，已拒绝发布。",
        "balance_snapshot": _balance_snapshot(view),
        "guide": "请先调用 get_enterprise_finance(sections=balance) 查看明细，并引导用户在有活小程序充值后再发布。",
    }


def publish_balance_error_json(error: dict) -> str:
    return json.dumps(error, ensure_ascii=False)

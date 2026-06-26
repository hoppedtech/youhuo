"""MCP 写操作门禁与审计（防 Agent 误调/滥调后端接口）。"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from typing import Any

GATE_META_KEYS = frozenset({"user_confirmed", "confirm_token", "confirmation_summary"})

B_WRITE_TOOL_NAMES = frozenset({
    "publish_jd",
    "pay_publish_points",
    "pay_hourly_job",
    "save_recruit_address",
    "mark_worker_suitable",
    "invite_worker_to_job",
    "manage_attendance",
    "close_job",
    "pay_schedule_settlement",
    "pay_balance",
    "manage_invoice",
    "publish_task",
    "accept_delivery",
    "revoke_auth",
})
WRITE_TOOL_NAMES = B_WRITE_TOOL_NAMES

# C 端 P0/P1：两阶段 confirm_token
C_WRITE_TOOL_NAMES_TOKEN = frozenset({
    "apply_job",
    "submit_job_registration",
    "revoke_auth",
    "cancel_apply",
    "cancel_order",
})

# C 端 P2：仅 user_confirmed，无需 confirm_token
C_WRITE_TOOL_NAMES_CONFIRM_ONLY = frozenset({
    "update_work_preferences",
    "manage_resume",
    "apply_job_standby",
    "cancel_job_standby",
})

PREPARE_WRITE_TOOL_NAMES = B_WRITE_TOOL_NAMES | C_WRITE_TOOL_NAMES_TOKEN

# 写 Tool 形参默认值：与 MCP 调用时 Python/FastMCP 默认一致；hash 时与 prepare 最小 JSON 对齐
TOOL_PARAM_DEFAULTS: dict[str, dict[str, Any]] = {
    "apply_job": {
        "job_type": "",
        "schedule_ids": "",
        "skill_ids": "",
        "require_complete_info": True,
    },
    "apply_job_standby": {
        "schedule_ids": "",
        "skill_ids": "",
        "require_complete_info": True,
    },
    "cancel_apply": {},
    "cancel_order": {},
    "revoke_auth": {},
    "submit_job_registration": {
        "skill_ids": "",
        "name": "",
        "sex": "",
        "birthday": "",
        "resume_path": "",
        "resume_name": "",
    },
    "publish_jd": {
        "product_type": 4,
        "skills": None,
        "benefits": None,
        "subscript_worker_count": 0,
        "subscript_day_count": 0,
        "reference_job_id": 0,
        "recruit_address_id": 0,
        "work_category_id": 0,
        "position_type": 0,
        "template_id": 0,
        "job_date": "",
        "schedule_start": "09:00",
        "schedule_end": "18:00",
    },
    "pay_hourly_job": {"payment_type": 1},
    "save_recruit_address": {
        "street_number": "",
        "province": "",
        "city": "",
        "district": "",
        "short_address": "",
        "lng": 0,
        "lat": 0,
        "default_address": False,
        "alternate_phone": "",
        "address_id": 0,
    },
    "pay_publish_points": {},
    "publish_task": {},
    "mark_worker_suitable": {},
    "invite_worker_to_job": {"invite_type": 1},
    "manage_attendance": {
        "minutes": 0,
        "reason": "",
        "clock_time": 0,
        "begin_clock_time": "",
        "end_clock_time": "",
        "product_type": 0,
    },
    "close_job": {"reason": ""},
    "pay_schedule_settlement": {"remark": ""},
    "pay_balance": {},
    "manage_invoice": {
        "invoice_type": 1,
        "amount": 0,
        "company_name": "",
        "tax_number": "",
        "email": "",
        "status": "pending",
        "page": 1,
        "page_size": 20,
    },
    "accept_delivery": {},
    "update_work_preferences": {
        "week_day": "",
        "work_time_slot": "",
        "work_length": "",
        "salary_expectation": 0,
        "benefit": "",
    },
    "manage_resume": {
        "file_path": "",
        "name": "",
        "phone": "",
        "sex": "",
        "birthday": "",
        "city": "",
        "intention_address": "",
        "salary_expectation": "",
        "skills": "",
        "education": "",
        "work_experience": "",
        "self_intro": "",
    },
    "cancel_job_standby": {"schedule_ids": ""},
}

# canonical hash 前：整型 ID 字段（含 JSON 字符串 "2938930" → 2938930）
INTEGER_CANONICAL_KEYS = frozenset({
    "job_id",
    "schedule_id",
    "salary_unit",
    "payment_type",
    "product_type",
    "headcount",
    "reference_job_id",
    "recruit_address_id",
    "work_category_id",
    "position_type",
    "template_id",
    "subscript_worker_count",
    "subscript_day_count",
    "amount",
})

# prepare 与 execute 字段名不一致时的别名（仅 hash / 回填）
TOOL_PARAM_ALIASES: dict[str, dict[str, str]] = {
    "apply_job": {"schedule_id": "schedule_ids"},
}

DEFAULT_CONFIRM_TOKEN_TTL = int(os.getenv("YOUHUO_MCP_CONFIRM_TOKEN_TTL", "300"))

# confirm_token hash / prepare 响应：确定性 JSON（无多余空格，键排序）
CANONICAL_JSON_KWARGS: dict[str, Any] = {
    "ensure_ascii": False,
    "sort_keys": True,
    "separators": (",", ":"),
    "default": str,
}


def canonical_json_dumps(obj: Any) -> str:
    """确定性 JSON 序列化（与 params_json 字符串 ↔ JSON-RPC 对象对齐）。"""
    return json.dumps(obj, **CANONICAL_JSON_KWARGS)


def parse_prepare_params_json(params_json: str) -> dict[str, Any]:
    """解析 prepare 阶段的 params_json；兼容空白、双重 JSON 编码。"""
    raw = (params_json or "").strip()
    if not raw:
        return {}
    params: Any = json.loads(raw)
    if isinstance(params, str):
        inner = params.strip()
        params = json.loads(inner) if inner else {}
    if not isinstance(params, dict):
        raise ValueError("params_json 须为 JSON 对象")
    return params


def canonical_params_json(tool_name: str, params: dict[str, Any]) -> str:
    """canonical 业务参数的确定性 JSON 字符串（供 Agent 阶段二原样复用）。"""
    return canonical_json_dumps(canonical_params_for_hash(tool_name, params))


def _audit_log_path() -> str:
    return os.getenv(
        "YOUHUO_MCP_AUDIT_LOG_PATH",
        os.path.join(os.path.expanduser("~/.workbuddy"), "youhuo_mcp_audit.log"),
    )


def _confirm_token_store_path() -> str:
    return os.getenv(
        "YOUHUO_MCP_CONFIRM_TOKEN_STORE",
        os.path.join(os.path.expanduser("~/.workbuddy"), "youhuo_mcp_confirm_tokens.json"),
    )


def write_enabled() -> bool:
    raw = os.getenv("YOUHUO_MCP_WRITE_ENABLED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def confirm_token_required() -> bool:
    """YOUHUO_MCP_CONFIRM_TOKEN_REQUIRED：默认 true，写操作须两阶段 confirm_token。"""
    raw = os.getenv("YOUHUO_MCP_CONFIRM_TOKEN_REQUIRED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def ensure_production_write_guard() -> None:
    """云托管启动校验：禁止关闭写门禁（YOUHUO_REQUIRE_BASE_URL=1 时生效）。"""
    from tools.youhuo_env import _truthy_env

    if not _truthy_env("YOUHUO_REQUIRE_BASE_URL"):
        return
    if not write_enabled():
        raise SystemExit("YOUHUO_MCP_WRITE_ENABLED must not be false in production.")
    if not confirm_token_required():
        raise SystemExit(
            "YOUHUO_MCP_CONFIRM_TOKEN_REQUIRED must not be false in production."
        )


def tool_requires_confirm_token(tool_name: str) -> bool:
    """B 端写 Tool 与 C 端 P0/P1 须两阶段 confirm_token。"""
    if not confirm_token_required():
        return False
    return tool_name in PREPARE_WRITE_TOOL_NAMES


def is_gated_write_tool(tool_name: str) -> bool:
    return (
        tool_name in B_WRITE_TOOL_NAMES
        or tool_name in C_WRITE_TOOL_NAMES_TOKEN
        or tool_name in C_WRITE_TOOL_NAMES_CONFIRM_ONLY
    )


def params_for_confirm_token(**params: Any) -> dict[str, Any]:
    """写 Tool 业务参数（排除门禁元字段），用于 confirm_token 绑定。"""
    return {k: v for k, v in params.items() if k not in GATE_META_KEYS}


def _apply_param_aliases(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    aliases = TOOL_PARAM_ALIASES.get(tool_name, {})
    if not aliases:
        return params
    merged = dict(params)
    for src, dst in aliases.items():
        src_val = merged.get(src)
        dst_val = merged.get(dst)
        if src_val not in (None, "") and dst_val in (None, ""):
            merged[dst] = src_val
        merged.pop(src, None)
    return merged


def _coerce_scalar_for_hash(key: str, value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if key in INTEGER_CANONICAL_KEYS or key.endswith("_id"):
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return value
            try:
                if "." in s or "e" in s.lower():
                    f = float(s)
                    return int(f) if f.is_integer() else f
                return int(s)
            except ValueError:
                return value
    return value


def _normalize_schedule_ids(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = [str(x).strip() for x in value if str(x).strip()]
    else:
        parts = [p.strip() for p in str(value).split(",") if p.strip()]
    norm: list[str] = []
    for part in parts:
        try:
            norm.append(str(int(part)))
        except ValueError:
            norm.append(part)
    return ",".join(sorted(norm, key=lambda x: int(x) if x.isdigit() else x))


def _normalize_number(value: int | float) -> int | float:
    """整数值归一为 int（10 与 10.0 等价）；有小数部分则保留 float（如 10.5）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return value
    return value


def _normalize_value_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize_value_for_hash(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_value_for_hash(v) for v in value]
    if isinstance(value, tuple):
        return [_normalize_value_for_hash(v) for v in value]
    if isinstance(value, (int, float)):
        return _normalize_number(value)
    return value


def _values_equal(a: Any, b: Any) -> bool:
    return _normalize_value_for_hash(a) == _normalize_value_for_hash(b)


def _is_empty_or_default(tool_name: str, key: str, value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    defaults = TOOL_PARAM_DEFAULTS.get(tool_name, {})
    if key in defaults and _values_equal(value, defaults[key]):
        return True
    return False


def reconcile_params_with_token_bound(
    tool_name: str,
    execute_params: dict[str, Any],
    bound_canonical: dict[str, Any],
) -> dict[str, Any]:
    """execute 侧缺省/默认字段用 token 绑定值补全（MCP 传输丢字段时仍可对齐 prepare 意图）。"""
    clean = _apply_param_aliases(tool_name, params_for_confirm_token(**execute_params))
    merged = dict(clean)
    for key, bound_val in bound_canonical.items():
        if _is_empty_or_default(tool_name, key, merged.get(key)):
            merged[key] = bound_val
    return merged


def canonical_params_for_hash(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """confirm_token 绑定用的 canonical 参数（忽略空值与 Tool 默认值，避免 MCP 序列化偏差）。"""
    clean = _apply_param_aliases(tool_name, params_for_confirm_token(**params))
    defaults = TOOL_PARAM_DEFAULTS.get(tool_name, {})
    canonical: dict[str, Any] = {}
    for key, val in clean.items():
        if val is None:
            continue
        if key == "schedule_ids":
            norm = _normalize_schedule_ids(val)
            if not norm:
                continue
        else:
            coerced = _coerce_scalar_for_hash(key, val)
            if isinstance(coerced, str) and coerced == "":
                continue
            norm = _normalize_value_for_hash(coerced)
        if key in defaults and _values_equal(norm, defaults[key]):
            continue
        canonical[key] = norm
    return dict(sorted(canonical.items()))


def normalize_params_for_hash(params: dict[str, Any]) -> dict[str, Any]:
    """递归数值归一化（兼容旧调用）。"""
    return _normalize_value_for_hash(params)


def params_hash(tool_name: str, params: dict[str, Any]) -> str:
    canonical = canonical_params_for_hash(tool_name, params)
    payload = canonical_json_dumps({"tool": tool_name, "params": canonical})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_token_store() -> dict[str, Any]:
    path = _confirm_token_store_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_token_store(store: dict[str, Any]) -> None:
    path = _confirm_token_store_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def _purge_expired_tokens(store: dict[str, Any]) -> None:
    now = time.time()
    tokens = store.get("tokens", {})
    if not isinstance(tokens, dict):
        store["tokens"] = {}
        return
    expired = [k for k, v in tokens.items() if float(v.get("expires_at", 0)) <= now]
    for k in expired:
        tokens.pop(k, None)


def issue_confirm_token(
    tool_name: str,
    params: dict[str, Any],
    *,
    preview_summary: str = "",
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    """阶段一：签发一次性 confirm_token（不调用后端写接口）。"""
    if tool_name not in PREPARE_WRITE_TOOL_NAMES:
        raise ValueError(f"不支持的工具: {tool_name}")
    clean = params_for_confirm_token(**params)
    canonical = canonical_params_for_hash(tool_name, clean)
    canonical_json = canonical_params_json(tool_name, clean)
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_CONFIRM_TOKEN_TTL
    token = secrets.token_urlsafe(24)
    now = time.time()
    store = _load_token_store()
    _purge_expired_tokens(store)
    tokens = store.setdefault("tokens", {})
    tokens[token] = {
        "tool": tool_name,
        "params_hash": params_hash(tool_name, clean),
        "params_canonical": canonical,
        "params_canonical_json": canonical_json,
        "params_preview": _sanitize_params(clean),
        "preview_summary": (preview_summary or "")[:500],
        "issued_at": now,
        "expires_at": now + ttl,
    }
    _save_token_store(store)
    return {
        "confirm_token": token,
        "tool_name": tool_name,
        "expires_in": ttl,
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now + ttl)),
        "params_preview": _sanitize_params(clean),
        "params_canonical": canonical,
        "canonical_params_json": canonical_json,
        "preview_summary": preview_summary,
    }


def validate_and_consume_confirm_token(
    tool_name: str,
    confirm_token: str,
    params: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    """阶段二：校验并消费 token。成功返回 (None, 回填参数字典)，失败返回 (错误信息, {})。"""
    if not confirm_token_required():
        return None, {}
    if not confirm_token or not str(confirm_token).strip():
        return (
            f"操作 `{tool_name}` 须两阶段确认：先调用 prepare_write_confirmation 获取 confirm_token，"
            "向用户展示摘要并获明确确认后，再以 user_confirmed=true 且相同参数调用本 Tool。",
            {},
        )
    store = _load_token_store()
    _purge_expired_tokens(store)
    token_key = str(confirm_token).strip()
    entry = store.get("tokens", {}).get(token_key)
    if not entry:
        return "confirm_token 无效或已过期，请重新调用 prepare_write_confirmation。", {}
    if entry.get("tool") != tool_name:
        return (
            f"confirm_token 与工具不匹配：token 绑定 `{entry.get('tool')}`，当前 `{tool_name}`。",
            {},
        )
    bound = entry.get("params_canonical") or {}
    clean = params_for_confirm_token(**params)
    reconciled = reconcile_params_with_token_bound(tool_name, clean, bound)
    if entry.get("params_hash") != params_hash(tool_name, reconciled):
        got = canonical_params_for_hash(tool_name, clean)
        bound_json = entry.get("params_canonical_json") or canonical_json_dumps(bound)
        return (
            "confirm_token 与本次调用参数不一致，请用与 prepare 阶段相同的参数重试，或重新 prepare。"
            f" 绑定参数(canonical): {bound_json}；"
            f"本次(canonical): {canonical_params_json(tool_name, clean)}"
            + (
                f"；回填后(canonical): {canonical_params_json(tool_name, reconciled)}"
                if reconciled != clean
                else ""
            ),
            {},
        )
    if float(entry.get("expires_at", 0)) <= time.time():
        store.get("tokens", {}).pop(token_key, None)
        _save_token_store(store)
        return "confirm_token 已过期，请重新调用 prepare_write_confirmation。", {}
    store.get("tokens", {}).pop(token_key, None)
    _save_token_store(store)
    resolved = {
        k: reconciled[k]
        for k in reconciled
        if k not in clean or _is_empty_or_default(tool_name, k, clean.get(k))
    }
    return None, resolved


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in params.items():
        if key in ("token", "password", "authorization"):
            continue
        if isinstance(value, str) and len(value) > 200:
            safe[key] = value[:200] + "..."
        else:
            safe[key] = value
    return safe


def check_write_gate(
    tool_name: str,
    user_confirmed: bool,
    *,
    confirm_token: str = "",
    confirmation_summary: str = "",
    require_token: bool | None = None,
    **audit_params: Any,
) -> tuple[str | None, dict[str, Any]]:
    """写操作前置检查。通过返回 (None, 回填参数)，拒绝则返回 (JSON 错误, {})。"""
    needs_token = (
        require_token if require_token is not None else tool_requires_confirm_token(tool_name)
    )

    if not write_enabled():
        msg = (
            "MCP 写操作已禁用（YOUHUO_MCP_WRITE_ENABLED=false）。"
            "仅可调用查询类 Tool；如需发布/支付/改状态，请由管理员开启写模式。"
        )
        _append_audit(tool_name, user_confirmed, confirmation_summary, audit_params, blocked=msg)
        return json.dumps({"success": False, "error": msg, "code": "WRITE_DISABLED"}, ensure_ascii=False), {}

    if not user_confirmed:
        if needs_token:
            msg = (
                f"操作 `{tool_name}` 会修改平台数据或触发扣款。"
                "须先调用 prepare_write_confirmation 获取 confirm_token，向用户展示摘要并获明确确认，"
                "再以 user_confirmed=true + confirm_token 调用。"
            )
        else:
            msg = (
                f"操作 `{tool_name}` 会修改平台数据。"
                "须向用户展示摘要并获明确确认后以 user_confirmed=true 调用。"
            )
        _append_audit(tool_name, user_confirmed, confirmation_summary, audit_params, blocked=msg)
        return json.dumps(
            {"success": False, "error": msg, "code": "CONFIRMATION_REQUIRED"},
            ensure_ascii=False,
        ), {}

    if needs_token:
        token_err, resolved = validate_and_consume_confirm_token(
            tool_name, confirm_token, audit_params
        )
        if token_err:
            _append_audit(tool_name, user_confirmed, confirmation_summary, audit_params, blocked=token_err)
            code = (
                "CONFIRM_TOKEN_MISMATCH"
                if "参数不一致" in token_err
                else "CONFIRM_TOKEN_REQUIRED"
            )
            return json.dumps(
                {"success": False, "error": token_err, "code": code},
                ensure_ascii=False,
            ), {}
        return None, resolved
    return None, {}


def audit_write_result(
    tool_name: str,
    user_confirmed: bool,
    *,
    confirmation_summary: str = "",
    success: bool,
    result_preview: str = "",
    error: str = "",
    **audit_params: Any,
) -> None:
    _append_audit(
        tool_name,
        user_confirmed,
        confirmation_summary,
        audit_params,
        success=success,
        result_preview=result_preview[:500],
        error=error[:500],
    )


def _append_audit(
    tool_name: str,
    user_confirmed: bool,
    confirmation_summary: str,
    audit_params: dict[str, Any],
    *,
    blocked: str = "",
    success: bool | None = None,
    result_preview: str = "",
    error: str = "",
) -> None:
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": tool_name,
        "user_confirmed": user_confirmed,
        "confirmation_summary": (confirmation_summary or "")[:200],
        "params": _sanitize_params(audit_params),
    }
    if blocked:
        entry["blocked"] = blocked[:300]
    if success is not None:
        entry["success"] = success
        if result_preview:
            entry["result_preview"] = result_preview
        if error:
            entry["error"] = error
    try:
        log_path = _audit_log_path()
        parent = os.path.dirname(log_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _result_ok(result: Any) -> bool:
    if not isinstance(result, str):
        return True
    text = result.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if data.get("success") is False:
                return False
            if data.get("code") in (
                "WRITE_DISABLED",
                "CONFIRMATION_REQUIRED",
                "CONFIRM_TOKEN_REQUIRED",
            ):
                return False
        except json.JSONDecodeError:
            pass
    if "失败" in text or text.startswith("❌"):
        return False
    return True


def finish_write(
    tool_name: str,
    user_confirmed: bool,
    result: Any,
    *,
    confirmation_summary: str = "",
    **audit_params: Any,
) -> Any:
    ok = _result_ok(result)
    audit_write_result(
        tool_name,
        user_confirmed,
        confirmation_summary=confirmation_summary,
        success=ok,
        result_preview=str(result),
        error="" if ok else str(result),
        **audit_params,
    )
    return result


class WriteGate:
    """写 Tool 门禁：构造时检查；`.finish(result)` 写审计并返回。"""

    def __init__(
        self,
        tool_name: str,
        user_confirmed: bool,
        *,
        confirm_token: str = "",
        confirmation_summary: str = "",
        require_token: bool | None = None,
        **audit_params: Any,
    ):
        self._tool = tool_name
        self._confirmed = user_confirmed
        self._summary = confirmation_summary
        self._audit = dict(audit_params)
        self.blocked, resolved = check_write_gate(
            tool_name,
            user_confirmed,
            confirm_token=confirm_token,
            confirmation_summary=confirmation_summary,
            require_token=require_token,
            **audit_params,
        )
        if resolved:
            self._audit.update(resolved)

    def param(self, name: str, default: Any = None) -> Any:
        """取业务参数；token 校验回填后的值优先于 Python 形参默认值。"""
        val = self._audit[name] if name in self._audit else default
        if val is None:
            return default
        if name == "schedule_ids":
            return _normalize_schedule_ids(val)
        if name in INTEGER_CANONICAL_KEYS or name.endswith("_id"):
            return _coerce_scalar_for_hash(name, val)
        return val

    def finish(self, result: Any) -> Any:
        return finish_write(
            self._tool,
            self._confirmed,
            result,
            confirmation_summary=self._summary,
            **self._audit,
        )

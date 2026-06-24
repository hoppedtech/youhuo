"""岗位报名前置：资料要求检查与报名信息提交。"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from tools.api_response import api_data, api_message, api_ok, mask_phone, parse_auth_info
from tools.job_apply import SCHEDULE_PRODUCT_TYPES, parse_schedule_ids

RequestFn = Callable[..., Awaitable[dict]]

CREDENTIAL_STATUS_LABELS = {
    0: "审核中",
    1: "已通过",
    2: "审核未通过",
    3: "需重新上传",
}

SALARY_UNIT_LABELS = {1: "元/月", 2: "元/天", 3: "元/时"}


def parse_skill_ids(skill_ids: str | list[int] | None) -> list[int]:
    if not skill_ids:
        return []
    if isinstance(skill_ids, list):
        return [int(x) for x in skill_ids if x is not None]
    ids: list[int] = []
    for token in str(skill_ids).replace("，", ",").split(","):
        token = token.strip()
        if token.isdigit():
            ids.append(int(token))
    return ids


def _normalize_birthday(birthday: str) -> str:
    digits = "".join(ch for ch in str(birthday or "") if ch.isdigit())
    if len(digits) >= 6:
        return digits[:6]
    return digits


def _credential_issue(cert: dict) -> str | None:
    if not cert.get("file_path"):
        return "需上传证件照片"
    status = cert.get("credential_status")
    if status == 0:
        return "证件审核中，请等待通过后再报名"
    if status in (2, 3):
        return cert.get("fail_reason") or "证件需重新上传"
    return None


def _profile_registration_gaps(profile: dict) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    checks = [
        ("wechat_account", "个人微信号"),
        ("intention_address", "意向工作地址"),
        ("salary_expectation", "期望薪资"),
    ]
    for key, label in checks:
        value = profile.get(key)
        if value in (None, "", 0):
            gaps.append({"field": key, "label": label, "reason": "未填写"})
    if not profile.get("salary_unit"):
        gaps.append({"field": "salary_unit", "label": "薪资单位", "reason": "未选择（元/月、元/天、元/时）"})
    skills = profile.get("job_skill_list") or profile.get("skills") or []
    if not skills:
        gaps.append({"field": "skill_ids", "label": "擅长技能标签", "reason": "未选择"})
    return gaps


async def fetch_entry_job_detail(req: RequestFn, job_id: int) -> dict:
    result = await req("GET", f"Job/GetEntryJobDetail?jobId={job_id}")
    if not api_ok(result):
        raise ValueError(api_message(result, f"无法获取岗位 {job_id} 的报名要求。"))
    return api_data(result) or {}


async def fetch_job_detail(req: RequestFn, job_id: int) -> dict:
    result = await req("GET", f"Job/JobDetail?jobId={job_id}")
    if not api_ok(result):
        raise ValueError(api_message(result, f"岗位 {job_id} 不存在或已下架。"))
    return api_data(result) or {}


def assess_apply_readiness(
    *,
    job_id: int,
    job_detail: dict,
    entry_detail: dict,
    profile: dict,
    schedule_ids: list[int] | None = None,
    skill_ids: list[int] | None = None,
) -> dict[str, Any]:
    product_type = job_detail.get("product_type")
    _, auth_desc, auth_passed = parse_auth_info(profile)
    missing: list[dict[str, str]] = []
    warnings: list[str] = []

    if not auth_passed:
        missing.append(
            {
                "field": "auth",
                "label": "实名认证",
                "reason": f"当前状态：{auth_desc}，请先完成实名认证",
            }
        )

    for gap in _profile_registration_gaps(profile):
        missing.append(gap)

    credentials = entry_detail.get("credentials") or []
    for cert in credentials:
        issue = _credential_issue(cert)
        name = cert.get("credential_type_name") or "资质证件"
        if issue:
            missing.append({"field": f"credential_{cert.get('id')}", "label": name, "reason": issue})

    skill_tags = entry_detail.get("skill_tags") or []
    selected = skill_ids or []
    if skill_tags and product_type in (4, 5, 6) and not selected:
        tag_names = "、".join(
            str(t.get("skill_name") or t.get("name") or t.get("position_name") or t.get("id"))
            for t in skill_tags[:8]
        )
        missing.append(
            {
                "field": "skill_ids",
                "label": "岗位技能标签",
                "reason": f"需从岗位标签中选择，可选：{tag_names}",
            }
        )

    resume_required = entry_detail.get("resume") is not None
    if resume_required and not profile.get("resume_path"):
        missing.append(
            {
                "field": "resume",
                "label": "简历",
                "reason": "该岗位需要上传简历（pdf/doc/docx）",
            }
        )

    if product_type in SCHEDULE_PRODUCT_TYPES and not schedule_ids:
        missing.append(
            {
                "field": "schedule_ids",
                "label": "报名班次",
                "reason": "小时工/计件工需先选择班次 ID",
            }
        )

    require_name = job_detail.get("user_credential_require_name")
    if require_name and not credentials:
        warnings.append(f"岗位要求资质：{require_name}（请确认个人中心已上传）")

    need_skill_name = job_detail.get("need_skill_name")
    if need_skill_name:
        warnings.append(f"岗位技能偏好：{need_skill_name}")

    return {
        "job_id": job_id,
        "position_name": entry_detail.get("position_name") or job_detail.get("position_title"),
        "product_type": product_type,
        "ready": len(missing) == 0,
        "missing": missing,
        "warnings": warnings,
        "skill_tags": skill_tags,
        "credentials": credentials,
        "resume_required": resume_required,
        "profile_snapshot": {
            "name": profile.get("name"),
            "sex": profile.get("sex"),
            "birthday": profile.get("birthday"),
            "phone": mask_phone(profile.get("user_phone") or profile.get("phone") or ""),
            "wechat_account": profile.get("wechat_account") or "",
            "intention_address": profile.get("intention_address") or "",
            "salary_expectation": profile.get("salary_expectation"),
            "salary_unit": profile.get("salary_unit"),
            "auth_status": auth_desc,
        },
    }


def format_entry_requirements(report: dict) -> str:
    lines = [
        f"📋 岗位 {report['job_id']}「{report.get('position_name') or '未知'}」报名资料检查\n",
        f"岗位类型 product_type: {report.get('product_type')}",
        f"实名认证: {report['profile_snapshot'].get('auth_status')}",
        "",
        "当前资料摘要:",
        f"- 姓名: {report['profile_snapshot'].get('name') or '未填'}",
        f"- 手机: {report['profile_snapshot'].get('phone') or '未绑'}",
        f"- 微信: {report['profile_snapshot'].get('wechat_account') or '未填'}",
        f"- 意向地址: {report['profile_snapshot'].get('intention_address') or '未填'}",
        f"- 期望薪资: {report['profile_snapshot'].get('salary_expectation') or '未填'}",
    ]
    unit = report["profile_snapshot"].get("salary_unit")
    if unit:
        lines.append(f"- 薪资单位: {SALARY_UNIT_LABELS.get(int(unit), unit)}")

    if report.get("credentials"):
        lines.append("\n资质要求:")
        for cert in report["credentials"]:
            status = CREDENTIAL_STATUS_LABELS.get(cert.get("credential_status"), "未知")
            lines.append(f"- {cert.get('credential_type_name') or '证件'}: {status}")

    if report.get("skill_tags"):
        lines.append("\n可选技能标签:")
        for tag in report["skill_tags"][:10]:
            tag_id = tag.get("id") or tag.get("skill_id")
            tag_name = tag.get("skill_name") or tag.get("name") or tag.get("position_name")
            lines.append(f"- [{tag_id}] {tag_name}")

    if report.get("resume_required"):
        lines.append("\n需要上传简历: 是")

    if report.get("warnings"):
        lines.append("\n岗位提示:")
        lines.extend(f"- {w}" for w in report["warnings"])

    if report.get("missing"):
        lines.append("\n❌ 报名前还需补充:")
        for item in report["missing"]:
            lines.append(f"- {item['label']}: {item['reason']}")
        lines.append(
            "\n可调用 submit_job_registration 提交报名资料，"
            "或在小程序个人中心补全资质/简历后重试。"
        )
    else:
        lines.append("\n✅ 资料已齐全，可调用 apply_job 报名。")

    return "\n".join(lines)


def build_job_registration_payload(
    job_id: int,
    *,
    name: str,
    sex: str,
    birthday: str,
    wechat_account: str,
    intention_address: str,
    salary_expectation: str,
    salary_unit: int,
    skill_ids: list[int],
    user_phone: str = "",
    resume_name: str = "",
    resume_path: str = "",
    resume_size: int = 0,
    resume_ext_name: str = "",
) -> dict:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "name": name,
        "sex": sex,
        "birthday": f"{_normalize_birthday(birthday)}01",
        "wechat_account": wechat_account,
        "intention_address": intention_address,
        "salary_expectation": salary_expectation,
        "salary_unit": salary_unit,
        "skills": skill_ids,
    }
    if user_phone:
        payload["user_phone"] = user_phone
    if resume_path:
        payload.update(
            {
                "resume_name": resume_name,
                "resume_path": resume_path,
                "resume_size": resume_size,
                "resume_ext_name": resume_ext_name,
            }
        )
    return payload


async def submit_registration(
    req: RequestFn,
    payload: dict,
) -> dict:
    return await req("POST", "Personal/JobRegistrationInfo", json=payload)


def format_readiness_blocker(report: dict) -> str:
    return json.dumps(
        {
            "success": False,
            "error": "报名资料不完整，请先补充后再报名",
            "job_id": report.get("job_id"),
            "missing": report.get("missing"),
            "hint": "先调用 check_apply_readiness 查看详情，再调用 submit_job_registration 补资料",
        },
        ensure_ascii=False,
    )

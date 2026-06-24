"""有活平台用户画像 MCP Server。

提供用户信息、实人认证状态、技能标签、可工作时间等基础能力。
job-seeker Skill 报名前依赖本 Server 检查认证状态。
"""
import os
import sys
import json
import httpx
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared_token_store import auth_store
from tools.mcp_write_guard import WriteGate
from tools.youhuo_env import applet_base_url
from tools.api_response import (
    api_data,
    api_list,
    api_message,
    api_ok,
    normalize_week_day,
    parse_auth_info,
    parse_work_preferences,
    profile_phone,
    profile_skill_names,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

mcp = FastMCP("youhuo-profile-api")

BASE_URL = applet_base_url()

PROFILE_SECTIONS = frozenset({"profile", "preferences", "auth", "resume"})


def _parse_profile_sections(sections: str) -> set[str] | None:
    raw = (sections or "all").strip().lower()
    if raw in ("all", "*", ""):
        return set(PROFILE_SECTIONS)
    selected = {s.strip().lower() for s in raw.replace("，", ",").split(",") if s.strip()}
    unknown = selected - PROFILE_SECTIONS
    if unknown:
        return None
    return selected


def _build_profile_section(data: dict) -> dict:
    _, auth_desc, auth_passed = parse_auth_info(data)
    return {
        "name": _mask_name(data.get("name", "")),
        "phone": _mask_phone(profile_phone(data)),
        "auth_status": auth_desc,
        "auth_passed": auth_passed,
        "star": data.get("star"),
        "finish_count": data.get("finishCount", data.get("finish_count", 0)),
        "city": data.get("city") or data.get("residence_address") or "未设置",
        "skills": profile_skill_names(data),
        "categories": data.get("categories", []),
    }


def _build_preferences_section(data: dict) -> dict:
    prefs = parse_work_preferences(data)
    prefs["summary"] = (
        f"期望工作日：{prefs['week_day_desc']}\n"
        f"期望时间段：{prefs['work_time_slot']}\n"
        f"可工作时长：{prefs['work_length']}"
    )
    return prefs


def _build_auth_section(data: dict) -> dict:
    auth_status, auth_desc, auth_passed = parse_auth_info(data)
    response = {
        "auth_status": auth_desc,
        "auth_passed": auth_passed,
        "can_apply": auth_passed,
    }
    if auth_status == 0:
        response["guide"] = "请前往有活小程序完成实人认证：我的 → 实名认证"
    elif auth_status == 1:
        response["guide"] = "实名认证审核中，请耐心等待或前往小程序查看进度"
    return response


def _build_resume_section(data: dict) -> dict:
    from tools.resume_upload import parse_resume_from_profile

    status = parse_resume_from_profile(data or {})
    status["success"] = True
    if not status["has_resume"]:
        status["guide"] = (
            "尚未上传简历。可调用 manage_resume(action=\"guide\") 查看填写说明，"
            "manage_resume(action=\"upload\", file_path=...) 上传文件，"
            "或 manage_resume(action=\"generate\", name=...) 自动生成并上传。"
        )
    return status


def _mask_phone(phone: str) -> str:
    if not phone or len(phone) < 7:
        return "未绑定"
    return re.sub(r"(\d{3})\d{4}(\d{4})", r"\1****\2", str(phone))


def _mask_name(name: str) -> str:
    if not name:
        return "未命名"
    if len(name) <= 1:
        return name
    return name[0] + "*" * (len(name) - 1)


def _format_user_profile_text(data: dict) -> str:
    """可读文本格式（原 get_worker_profile 输出）。"""
    _, auth_desc, _ = parse_auth_info(data)
    phone = profile_phone(data)
    skills = profile_skill_names(data)
    lines = [
        f"👤 {data.get('name', '未命名用户')}",
        f"📱 手机号: {phone or '未绑定'}",
        f"🆔 实名认证: {auth_desc}",
        f"⭐ 评分: {data.get('star', 'N/A')}",
        f"📦 完成单量: {data.get('finishCount', data.get('finish_count', 0))}单",
        f"📍 常驻城市: {data.get('city') or data.get('residence_address') or '未设置'}",
        f"💰 账户余额: ¥{data.get('balance', 0)}",
    ]
    if skills:
        lines.append(f"🏷️ 技能: {', '.join(skills)}")
    categories = data.get("categories", [])
    if categories:
        lines.append(f"🔧 工种: {', '.join(categories)}")
    return "\n".join(lines)


async def _req(method: str, path: str, **kwargs):
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception(
            "未授权：请先调用 youhuo-c-api.create_auth_session() "
            "完成扫码授权，再执行此操作"
        )
    token = token_info["token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-USER_ROLE": "1",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _get_basic_info() -> dict:
    result = await _req("GET", "Personal/getbasicinfo")
    return api_data(result)


@mcp.tool()
async def get_user_profile(format: str = "json", sections: str = "all") -> str:
    """获取零工用户画像（可按模块返回）。

    对应接口: Personal/getbasicinfo (GET)

    Args:
        format: `json`（默认，脱敏 JSON）或 `text`（可读文本，含完整手机号与余额摘要）
        sections: 逗号分隔模块，默认 `all`。可选：`profile` `preferences` `auth` `resume`
    """
    fmt = (format or "json").strip().lower()
    if fmt not in ("json", "text"):
        return json.dumps(
            {"success": False, "error": "format 须为 json 或 text"},
            ensure_ascii=False,
        )
    selected = _parse_profile_sections(sections)
    if selected is None:
        return json.dumps(
            {
                "success": False,
                "error": f"sections 无效，可选：{', '.join(sorted(PROFILE_SECTIONS))} 或 all",
            },
            ensure_ascii=False,
        )
    try:
        data = await _get_basic_info()
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if not data:
        return "未获取到用户资料。"

    if fmt == "text":
        return _format_user_profile_text(data)

    payload: dict = {"success": True}
    if "profile" in selected:
        payload["profile"] = _build_profile_section(data)
    if "preferences" in selected:
        payload["preferences"] = _build_preferences_section(data)
    if "auth" in selected:
        payload["auth"] = _build_auth_section(data)
    if "resume" in selected:
        payload["resume"] = _build_resume_section(data)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
async def update_work_preferences(
    week_day: str = "",
    work_time_slot: str = "",
    work_length: str = "",
    salary_expectation: float = 0,
    benefit: str = "",
    user_confirmed: bool = False,
    confirmation_summary: str = "",
) -> str:
    """更新零工可工作时间偏好。

    对应接口: Personal/savebasicinfo (POST)

    ⚠️ 须 user_confirmed=true（无需 confirm_token）。

    Args:
        week_day: 期望工作日。支持「周末」「周六,周日」或「6,7」（1=周一 … 7=周日）
        work_time_slot: 期望时间段，如「全天」「上午」「下午」「白班」「夜班」
        work_length: 可工作时长描述，如「周末」「4小时」
        salary_expectation: 期望薪资（元），0 表示不修改
        benefit: 期望福利，如「通讯补贴」；空字符串表示不修改
        user_confirmed: 必须为 true
        confirmation_summary: 可选，用户确认原话摘要

    Returns:
        更新后的可工作时间偏好
    """
    g = WriteGate(
        "update_work_preferences",
        user_confirmed,
        require_token=False,
        confirmation_summary=confirmation_summary,
        week_day=week_day,
        work_time_slot=work_time_slot,
        work_length=work_length,
        salary_expectation=salary_expectation,
        benefit=benefit,
    )
    if g.blocked:
        return g.blocked

    payload: dict = {}
    if week_day:
        try:
            payload["week_day"] = normalize_week_day(week_day)
        except ValueError as e:
            return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
    if work_time_slot:
        payload["work_time_slot"] = work_time_slot.strip()
    if work_length:
        payload["work_length"] = work_length.strip()
    if salary_expectation > 0:
        payload["salary_expectation"] = salary_expectation
    if benefit:
        payload["benefit"] = benefit.strip()

    if not payload:
        return g.finish(
            json.dumps(
                {"success": False, "error": "请至少提供一项要更新的偏好字段"},
                ensure_ascii=False,
            )
        )

    try:
        result = await _req("POST", "Personal/savebasicinfo", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if not api_ok(result):
        return g.finish(
            json.dumps(
                {"success": False, "error": api_message(result, "更新失败")},
                ensure_ascii=False,
            )
        )

    try:
        data = await _get_basic_info()
    except Exception as e:
        return g.finish(
            json.dumps(
                {
                    "success": True,
                    "message": "更新成功，但读取最新资料失败",
                    "error": str(e),
                },
                ensure_ascii=False,
            )
        )

    prefs = parse_work_preferences(data)
    return g.finish(
        json.dumps(
            {
                "success": True,
                "message": "可工作时间偏好已更新",
                **prefs,
                "summary": (
                    f"期望工作日：{prefs['week_day_desc']}\n"
                    f"期望时间段：{prefs['work_time_slot']}\n"
                    f"可工作时长：{prefs['work_length']}"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@mcp.tool()
async def manage_resume(
    action: str,
    file_path: str = "",
    name: str = "",
    phone: str = "",
    sex: str = "",
    birthday: str = "",
    city: str = "",
    intention_address: str = "",
    salary_expectation: str = "",
    skills: str = "",
    education: str = "",
    work_experience: str = "",
    self_intro: str = "",
    user_confirmed: bool = False,
    confirmation_summary: str = "",
) -> str:
    """简历管理（guide / upload / generate / delete）。

    Args:
        action: 操作类型
            - guide: 返回简历字段填写说明（只读，无需 user_confirmed）
            - upload: 上传本地 pdf/doc/docx（须 user_confirmed）
            - generate: 根据信息生成 PDF 并上传（须 user_confirmed，name 必填）
            - delete: 删除当前简历（须 user_confirmed）
        file_path: upload 时必填，本地文件绝对路径
        name: generate 时必填
        phone, sex, birthday, city, intention_address, salary_expectation: generate 可选
        skills: generate 可选，技能标签逗号分隔
        education, work_experience, self_intro: generate 可选
        user_confirmed: upload / generate / delete 必须为 true
        confirmation_summary: 可选，用户确认原话摘要
    """
    act = (action or "").strip().lower()
    if act not in ("guide", "upload", "generate", "delete"):
        return json.dumps(
            {
                "success": False,
                "error": "action 须为 guide、upload、generate 或 delete",
            },
            ensure_ascii=False,
        )

    if act == "guide":
        from tools.resume_builder import RESUME_FORM_GUIDE

        return RESUME_FORM_GUIDE

    g = WriteGate(
        "manage_resume",
        user_confirmed,
        require_token=False,
        confirmation_summary=confirmation_summary,
        action=act,
        file_path=file_path,
        name=name,
        phone=phone,
        sex=sex,
        birthday=birthday,
        city=city,
        intention_address=intention_address,
        salary_expectation=salary_expectation,
        skills=skills,
        education=education,
        work_experience=work_experience,
        self_intro=self_intro,
    )
    if g.blocked:
        return g.blocked

    if act == "upload":
        if not file_path.strip():
            return g.finish(
                json.dumps(
                    {"success": False, "error": "upload 须提供 file_path"},
                    ensure_ascii=False,
                )
            )
        from tools.resume_upload import upload_resume_from_path

        try:
            result = await upload_resume_from_path(_req, file_path)
            return g.finish(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if act == "generate":
        if not name.strip():
            return g.finish(
                json.dumps(
                    {"success": False, "error": "generate 须提供 name"},
                    ensure_ascii=False,
                )
            )
        from tools.resume_builder import build_resume_pdf
        from tools.resume_upload import upload_resume_from_path

        profile = {}
        try:
            profile = await _get_basic_info() or {}
        except Exception:
            pass

        skill_list = [s.strip() for s in skills.replace("，", ",").split(",") if s.strip()]
        if not skill_list:
            skill_list = profile_skill_names(profile)

        try:
            pdf_path = build_resume_pdf(
                name=name or profile.get("name") or "",
                phone=phone or profile_phone(profile),
                sex=sex or profile.get("sex") or "",
                birthday=birthday or str(profile.get("birthday") or ""),
                city=city or profile.get("city") or "",
                intention_address=intention_address or profile.get("intention_address") or "",
                salary_expectation=salary_expectation or str(profile.get("salary_expectation") or ""),
                skills=skill_list,
                education=education,
                work_experience=work_experience,
                self_intro=self_intro,
            )
            result = await upload_resume_from_path(_req, str(pdf_path))
            result["generated_file"] = str(pdf_path)
            return g.finish(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    from tools.resume_upload import delete_resume as remove_resume

    try:
        await remove_resume(_req)
        return g.finish(json.dumps({"success": True, "message": "简历已删除"}, ensure_ascii=False))
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


@mcp.tool()
async def get_skill_tags(keyword: str = "") -> str:
    """获取平台可选技能标签列表。

    对应接口: Personal/GetSkills (GET)

    Args:
        keyword: 技能关键词筛选
    """
    path = f"Personal/GetSkills?keyword={keyword}" if keyword else "Personal/GetSkills"
    try:
        result = await _req("GET", path)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    skills = api_list(result)
    if not skills:
        return "未找到相关技能标签。" if keyword else "暂无技能标签数据。"

    names = [s.get("name", s.get("skillName", "—")) for s in skills[:30]]
    return "可选技能标签：\n" + " | ".join(names)


if __name__ == "__main__":
    mcp.run(transport="stdio")

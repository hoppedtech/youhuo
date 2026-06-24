"""有活平台 C 端找活/零工 MCP Server。

提供岗位搜索、智能推荐、报名接单、订单查看等能力。
job-seeker Skill 依赖本 Server。
"""
import os
import sys
import json
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared_token_store import auth_store
from tools.api_response import (
    allow_orders,
    api_data,
    api_list,
    api_message,
    api_ok,
    api_search_lists,
    api_total,
    order_date,
    order_id as get_order_id,
    order_location,
    order_contact_phone,
    order_salary,
    order_status_desc,
    order_title,
)
from tools.job_recommend import (
    JOB_TYPE_CROWD,
    JOB_TYPE_HOURLY,
    JOB_TYPE_PIECE,
    JOB_TYPE_POSITION,
    bucket_jd_jobs,
    classify_jd_job,
    dedupe_by_id,
    format_recommend_card,
    matches_district,
    matches_keyword,
    merge_priority_buckets,
    normalize_city,
)
from tools.job_search import build_get_search_list_payload
from tools.mcp_write_guard import WriteGate
from tools.youhuo_env import applet_base_url

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

mcp = FastMCP("youhuo-worker-api")

BASE_URL = applet_base_url()


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
        "X-USER_ROLE": "1",  # C端固定传1
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


def _api_items(result: dict) -> list:
    return api_list(result)


def _job_id(job: dict):
    return job.get("id") or job.get("jobId") or job.get("job_id")


def _job_title(job: dict) -> str:
    return job.get("position_title") or job.get("title") or "未知岗位"


def _job_salary(job: dict) -> str:
    desc = job.get("salaryDesc") or job.get("salary_desc")
    if desc:
        return str(desc)
    salary = job.get("salary")
    unit = job.get("salary_unit_str") or job.get("salaryUnitStr") or "元/天"
    if salary is None:
        return "薪资面议"
    if isinstance(salary, dict):
        return f"{salary.get('min', '')}-{salary.get('max', '')}元/天"
    return f"{salary}{unit}"


def _job_location(job: dict) -> str:
    return job.get("location") or f"{job.get('city', '')}{job.get('district', '')}"


def _format_job_card(job: dict, icon: str = "📋") -> str:
    headcount = job.get("headcount") or job.get("recruit_num") or job.get("recruitNum") or 0
    return (
        f"{icon} [{_job_id(job)}] {_job_title(job)}\n"
        f"   💰 {_job_salary(job)} | 📍 {_job_location(job)} | 👥 招{headcount}人"
    )


async def _fetch_jd_job_pool(city: str, page_size: int) -> list[dict]:
    """拉取岗位池：推荐列表 + 岗位列表。"""
    pool: list[dict] = []
    fetch_size = max(page_size * 4, 40)
    for path, payload in (
        ("home/QueryRecommendList", {"city": city, "pageNum": 1, "pageSize": fetch_size}),
        ("Job/GetJobList", {"city": city, "pageNum": 1, "pageSize": fetch_size}),
    ):
        try:
            result = await _req("POST", path, json=payload)
            pool.extend(_api_items(result))
        except Exception:
            continue
    return dedupe_by_id(pool)


async def _fetch_crowd_tasks(city: str, page_size: int) -> list[dict]:
    """拉取众包/计件抢单任务池。"""
    city_norm = normalize_city(city)
    pool: list[dict] = []
    target = max(page_size * 4, 40)
    for page in range(1, 6):
        try:
            result = await _req(
                "POST",
                "HoppedTask/gethoppedtasks",
                json={"city": city_norm, "pageNum": page, "pageSize": 50},
            )
        except Exception:
            break
        batch = _api_items(result)
        if not batch:
            break
        pool.extend(batch)
        if len(pool) >= target:
            break
    return dedupe_by_id(pool)


async def _fetch_search_list_jobs(
    city: str,
    keyword: str,
    *,
    page: int = 1,
    page_size: int = 10,
    lat: float | None = None,
    lng: float | None = None,
) -> list[dict]:
    """按标题搜索岗位（Job/GetSearchList，对齐小程序搜索页）。"""
    if not city or not keyword:
        return []
    payload = build_get_search_list_payload(
        city,
        keyword,
        page=page,
        page_size=page_size,
        lat=lat,
        lng=lng,
    )
    try:
        result = await _req("POST", "Job/GetSearchList", json=payload)
    except Exception:
        return []
    jobs, _, _ = api_search_lists(result)
    return dedupe_by_id(jobs)


async def _build_recommendations(
    city: str,
    district: str = "",
    keyword: str = "",
    page_size: int = 10,
) -> list[tuple[str, dict]]:
    """按 小时工 → 计件工 → 众包工 → 岗位 优先级构建推荐。"""
    if keyword and city:
        jd_pool = await _fetch_search_list_jobs(
            city, keyword, page=1, page_size=max(page_size * 4, 40)
        )
    else:
        jd_pool = await _fetch_jd_job_pool(city, page_size)
    crowd_pool = await _fetch_crowd_tasks(city, page_size)

    jd_pool = [j for j in jd_pool if matches_district(j, district) and matches_keyword(j, keyword)]
    crowd_pool = [t for t in crowd_pool if matches_district(t, district) and matches_keyword(t, keyword)]

    buckets = bucket_jd_jobs(jd_pool)
    merged = merge_priority_buckets(
        buckets[JOB_TYPE_HOURLY],
        buckets[JOB_TYPE_PIECE],
        crowd_pool,
        buckets[JOB_TYPE_POSITION],
        page_size=page_size,
    )
    return merged


def _format_recommendations(city: str, merged: list[tuple[str, dict]]) -> str:
    if not merged:
        return f"{city}当前暂无匹配的活，可尝试放宽区域或关键词。"

    lines = [
        f"{city} 为你推荐的活（按优先级：小时工→计件工→众包工→岗位）：\n",
    ]
    for job_type, item in merged:
        lines.append(format_recommend_card(job_type, item))
    return "\n".join(lines)


# ──── 岗位搜索 ────

@mcp.tool()
async def search_jobs(
    city: str = "",
    keyword: str = "",
    category: str = "",
    salary_min: float = 0,
    salary_max: float = 0,
    page: int = 1,
    page_size: int = 10,
    lat: float = 0,
    lng: float = 0,
) -> str:
    """搜索可接的岗位/任务列表（找活）。

    有关键词时优先走 Job/GetSearchList（对齐小程序搜索页，按标题检索）；
    无结果时回退 GetJobList / QueryRecommendList。

    Args:
        city: 城市名称，如"深圳""北京"
        keyword: 关键词搜索，如"面点师""面点师0622a"
        category: 工作类别筛选
        salary_min: 薪资下限（元/天）
        salary_max: 薪资上限（元/天）
        page: 页码
        page_size: 每页数量
        lat: 可选，用户纬度（提升附近岗位排序准确度）
        lng: 可选，用户经度

    Returns:
        岗位列表，包含岗位名称、薪资、地点、人数等信息
    """
    geo_lat = lat if lat else None
    geo_lng = lng if lng else None

    if keyword and city:
        try:
            payload = build_get_search_list_payload(
                city,
                keyword,
                page=page,
                page_size=page_size,
                lat=geo_lat,
                lng=geo_lng,
            )
            result = await _req("POST", "Job/GetSearchList", json=payload)
            jobs, _, total = api_search_lists(result)
            if jobs:
                lines = [f"{city} 搜索「{keyword}」匹配岗位：\n"]
                for job in jobs[:page_size]:
                    job_type = classify_jd_job(job)
                    lines.append(format_recommend_card(job_type, job, icon="📋"))
                if total > len(jobs):
                    lines.append(f"\n（共 {total} 条相关结果，当前展示岗位 {len(jobs)} 条）")
                return "\n".join(lines)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    payload = {
        "pageNum": page,
        "pageSize": page_size,
        "city": city,
        "keyword": keyword,
        "category": category,
    }
    if salary_min > 0:
        payload["salaryMin"] = salary_min
    if salary_max > 0:
        payload["salaryMax"] = salary_max

    try:
        result = await _req("POST", "Job/GetJobList", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    items = _api_items(result)

    # GetJobList 在测试环境可能返回 total 但 ElementList 为空，回退推荐列表
    if not items and city:
        try:
            rec = await _req(
                "POST",
                "home/QueryRecommendList",
                json={"city": city, "pageNum": page, "pageSize": max(page_size, 20)},
            )
            items = _api_items(rec)
        except Exception:
            pass

    if keyword:
        items = [j for j in items if keyword in _job_title(j)]

    if not items:
        merged = await _build_recommendations(city, keyword=keyword, page_size=page_size)
        if merged:
            return _format_recommendations(city, merged)
        return "暂无匹配的岗位。"

    lines = ["匹配岗位：\n"]
    for job in items[:page_size]:
        category = job.get("category") or job.get("category_name") or "未分类"
        status_desc = job.get("statusDesc") or job.get("status_desc") or "招聘中"
        lines.append(_format_job_card(job))
        lines.append(f"   🏷️ {category} | 状态: {status_desc}")
    return "\n".join(lines)


@mcp.tool()
async def get_job_detail(job_id: int, job_type: str = "") -> str:
    """获取岗位/任务详情（自动区分小时工、计件工、众包工、普通岗位）。

    路由规则:
    - 小时工 / 计件工 / 岗位 → Job/JobDetail (GET)
    - 众包工 → HoppedTask/GetHoppedTaskDetail (POST, body: {"id": task_id})
    - 未传 job_type 时自动识别；若从推荐卡片进入，建议带上类型避免误判

    Args:
        job_id: 岗位ID 或 众包任务ID
        job_type: 可选，小时工/计件工/众包工/岗位

    Returns:
        岗位或任务详细信息
    """
    from tools.job_detail import fetch_and_format_job_detail

    try:
        return await fetch_and_format_job_detail(_req, job_id, job_type)
    except ValueError as e:
        return str(e)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def search_piece_tasks(
    city: str,
    district: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 10,
) -> str:
    """搜索众包/计件抢单任务（按件/按次结算）。

    对应接口: HoppedTask/gethoppedtasks (POST)

    Args:
        city: 城市名称，如「北京」「北京市」
        district: 区县筛选，如「朝阳区」
        keyword: 关键词，如「保洁」「核验」
        page: 页码
        page_size: 每页数量
    """
    del page  # 当前接口按优先级聚合后分页意义有限，保留参数兼容
    try:
        crowd_pool = await _fetch_crowd_tasks(city, page_size * 2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    items = [
        t for t in crowd_pool if matches_district(t, district) and matches_keyword(t, keyword)
    ]
    if not items:
        return f"{city}{district}暂无匹配的众包/计件任务。"

    lines = ["众包/计件任务：\n"]
    for item in items[:page_size]:
        lines.append(format_recommend_card(JOB_TYPE_CROWD, item, icon="📋"))
    return "\n".join(lines)


@mcp.tool()
async def get_recommend_jobs(
    city: str,
    district: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 10,
) -> str:
    """智能推荐合适的活（优先小时工 → 计件工 → 众包工 → 岗位）。

    聚合接口:
    - home/QueryRecommendList / Job/GetJobList（岗位类）
    - HoppedTask/gethoppedtasks（众包/计件抢单）

    Args:
        city: 城市名称，如「深圳」「北京」
        district: 可选，区县筛选，如「朝阳区」
        keyword: 可选，关键词筛选
        page: 页码（保留兼容，当前按优先级返回 Top N）
        page_size: 推荐数量，默认 10
    """
    del page
    try:
        merged = await _build_recommendations(city, district, keyword, page_size)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return _format_recommendations(city, merged)


# ──── 报名接单 ────

async def _get_profile() -> dict:
    result = await _req("GET", "Personal/getbasicinfo")
    return api_data(result) or {}


async def _fetch_apply_eligibility(job_id: int = 0) -> dict:
    path = f"Credential/IsAllowOrders?jobId={job_id}" if job_id else "Credential/IsAllowOrders"
    result = await _req("GET", path)
    allowed = allow_orders(result)
    response: dict = {
        "allowed": allowed if allowed is not None else False,
        "job_id": job_id or None,
    }
    if allowed is True:
        return response
    if allowed is False:
        response["guide"] = (
            "您当前不具备接单权限。可能原因：未完成实名认证、未绑定手机号或账号被限制。"
            "请前往有活小程序完善个人信息。"
        )
    else:
        response["guide"] = api_message(result) or "无法确认接单权限，请稍后重试或在小程序中查看。"
    return response


@mcp.tool()
async def check_apply_readiness(
    job_id: int = 0,
    schedule_ids: str = "",
    skill_ids: str = "",
) -> str:
    """报名/接单前一站式检查（权限 + 岗位资料）。

    - job_id=0：仅检查全局接单权限（原 check_apply_eligibility）
    - job_id>0：检查接单权限 + 岗位报名资料是否齐全（原 get_entry_job_requirements）

    Args:
        job_id: 岗位 ID；0 表示不指定岗位
        schedule_ids: 已选班次 ID，逗号分隔（小时工/计件工）
        skill_ids: 已选技能标签 ID，逗号分隔
    """
    from tools.job_apply import parse_schedule_ids
    from tools.job_entry import (
        assess_apply_readiness,
        fetch_entry_job_detail,
        fetch_job_detail as fetch_job_detail_data,
        format_entry_requirements,
        parse_skill_ids,
    )

    try:
        eligibility = await _fetch_apply_eligibility(job_id if job_id > 0 else 0)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if job_id <= 0:
        return json.dumps({"success": True, **eligibility}, ensure_ascii=False, indent=2)

    if not eligibility.get("allowed"):
        return json.dumps(
            {
                "success": True,
                "ready": False,
                "eligibility": eligibility,
                "summary": eligibility.get("guide", "暂不具备接单权限"),
            },
            ensure_ascii=False,
            indent=2,
        )

    try:
        profile = await _get_profile()
        job_detail = await fetch_job_detail_data(_req, job_id)
        entry_detail = await fetch_entry_job_detail(_req, job_id)
        report = assess_apply_readiness(
            job_id=job_id,
            job_detail=job_detail,
            entry_detail=entry_detail,
            profile=profile,
            schedule_ids=parse_schedule_ids(schedule_ids) if schedule_ids else [],
            skill_ids=parse_skill_ids(skill_ids),
        )
        return json.dumps(
            {
                "success": True,
                "ready": report.get("ready", False),
                "job_id": job_id,
                "eligibility": eligibility,
                "report": report,
                "summary": format_entry_requirements(report),
            },
            ensure_ascii=False,
            indent=2,
        )
    except ValueError as e:
        return str(e)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def submit_job_registration(
    job_id: int,
    wechat_account: str,
    intention_address: str,
    salary_expectation: str,
    salary_unit: int,
    skill_ids: str = "",
    name: str = "",
    sex: str = "",
    birthday: str = "",
    resume_path: str = "",
    resume_name: str = "",
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """提交岗位报名资料（对齐小程序 postSign 页）。

    对应接口: Personal/JobRegistrationInfo (POST)

    ⚠️ 须先 prepare_write_confirmation 获取 confirm_token，再 user_confirmed=true 调用。

    必填项与小程序一致：微信号、意向地址、期望薪资、薪资单位、技能标签。
    姓名/性别/出生年月未传时，会从当前用户资料自动补齐（已实名则不可改）。

    Args:
        job_id: 岗位ID
        wechat_account: 个人微信号
        intention_address: 意向工作地址
        salary_expectation: 期望薪资范围，如「3000-5000」
        salary_unit: 薪资单位，1=元/月，2=元/天，3=元/时
        skill_ids: 技能标签 ID，逗号分隔
        name: 姓名（可选，默认取实名信息）
        sex: 性别（可选）
        birthday: 出生年月，如 198308 或 19830813（可选）
        resume_path: 简历 COS 地址（岗位要求简历时填写）
        resume_name: 简历文件名
        user_confirmed: 必须为 true
        confirm_token: prepare_write_confirmation 返回的一次性令牌
        confirmation_summary: 可选，用户确认原话摘要
    """
    g = WriteGate(
        "submit_job_registration",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        job_id=job_id,
        wechat_account=wechat_account,
        intention_address=intention_address,
        salary_expectation=salary_expectation,
        salary_unit=salary_unit,
        skill_ids=skill_ids,
        name=name,
        sex=sex,
        birthday=birthday,
        resume_path=resume_path,
        resume_name=resume_name,
    )
    if g.blocked:
        return g.blocked

    from tools.job_entry import (
        build_job_registration_payload,
        parse_skill_ids,
        submit_registration,
    )

    try:
        profile = await _get_profile()
        payload = build_job_registration_payload(
            job_id,
            name=name or profile.get("name") or "",
            sex=sex or profile.get("sex") or "男",
            birthday=birthday or str(profile.get("birthday") or ""),
            wechat_account=wechat_account,
            intention_address=intention_address,
            salary_expectation=salary_expectation,
            salary_unit=salary_unit,
            skill_ids=parse_skill_ids(skill_ids),
            user_phone=profile.get("user_phone") or profile.get("phone") or "",
            resume_name=resume_name,
            resume_path=resume_path,
            resume_ext_name=resume_name.rsplit(".", 1)[-1] if "." in resume_name else "",
        )
        if not payload["name"] or not payload["birthday"]:
            return g.finish(
                json.dumps(
                    {"success": False, "error": "缺少姓名或出生年月，请先完善实名信息"},
                    ensure_ascii=False,
                )
            )
        if not payload["skills"]:
            return g.finish(
                json.dumps(
                    {"success": False, "error": "请至少选择一个技能标签 skill_ids"},
                    ensure_ascii=False,
                )
            )
        result = await submit_registration(_req, payload)
        if api_ok(result):
            return g.finish(
                json.dumps(
                    {
                        "success": True,
                        "job_id": job_id,
                        "message": api_message(result, "报名资料已提交"),
                    },
                    ensure_ascii=False,
                )
            )
        return g.finish(
            json.dumps(
                {"success": False, "error": api_message(result, "提交失败")},
                ensure_ascii=False,
            )
        )
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


@mcp.tool()
async def apply_job(
    job_id: int,
    remark: str = "",
    job_type: str = "",
    schedule_ids: str = "",
    skill_ids: str = "",
    require_complete_info: bool = True,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """报名接单（投递岗位）。

    路由规则（与小程序一致）:
    - 小时工(4) / 计件工(6) → Job/EntryJob，需传 schedule_ids（班次ID，逗号分隔）
    - 普通岗位(2/5 等) → Personal/jobentry，body 使用 job_id（非 jobId）

    ⚠️ 须先 prepare_write_confirmation 获取 confirm_token，再 user_confirmed=true 调用。

    默认会先检查报名资料是否齐全（check_apply_readiness 同逻辑）。
    资料不全时返回缺失项，请先调用 submit_job_registration 或在小程序补全。

    Args:
        job_id: 要报名的岗位ID
        remark: 备注信息（保留兼容，当前接口未使用）
        job_type: 可选，小时工/计件工/岗位，用于辅助路由
        schedule_ids: 小时工/计件工必填，班次 ID，多个用逗号分隔
        skill_ids: 可选，技能标签 ID，逗号分隔
        require_complete_info: 是否强制检查资料完整性，默认 True
        user_confirmed: 必须为 true
        confirm_token: prepare_write_confirmation 返回的一次性令牌
        confirmation_summary: 可选，用户确认原话摘要

    Returns:
        报名结果。如果无权限会返回引导信息。
    """
    g = WriteGate(
        "apply_job",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        job_id=job_id,
        job_type=job_type,
        schedule_ids=schedule_ids,
        skill_ids=skill_ids,
        require_complete_info=require_complete_info,
    )
    if g.blocked:
        return g.blocked

    job_id = g.param("job_id", job_id)
    job_type = g.param("job_type", job_type)
    schedule_ids = g.param("schedule_ids", schedule_ids)
    skill_ids = g.param("skill_ids", skill_ids)
    require_complete_info = g.param("require_complete_info", require_complete_info)

    from tools.job_apply import apply_job_for_detail
    from tools.job_entry import parse_skill_ids

    del remark
    try:
        perm = await _req("GET", f"Credential/IsAllowOrders?jobId={job_id}")
        allowed = allow_orders(perm)
        if allowed is False:
            return g.finish(
                "⚠️ 您当前不具备接单权限。\n"
                "可能原因：\n"
                "1. 未完成实名认证\n"
                "2. 未绑定手机号\n"
                "3. 账号被限制接单\n\n"
                "请前往有活小程序完善个人信息后重试。"
            )
    except Exception:
        pass

    try:
        profile = await _get_profile() if require_complete_info else None
        return g.finish(
            await apply_job_for_detail(
                _req,
                job_id,
                job_type=job_type,
                schedule_ids=schedule_ids,
                skill_ids=parse_skill_ids(skill_ids),
                require_complete_info=require_complete_info,
                profile=profile,
            )
        )
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


@mcp.tool()
async def apply_job_standby(
    job_id: int,
    schedule_id: int,
    schedule_ids: str = "",
    skill_ids: str = "",
    require_complete_info: bool = True,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
) -> str:
    """对已报满但开放候补的班次提交候补。

    对应接口: Job/EntryJobBackUp (POST)
    与小程序一致：班次 status=8（已报满·可候补）时可调用。

    ⚠️ 须 user_confirmed=true（无需 confirm_token）。

    Args:
        job_id: 岗位 ID
        schedule_id: 要候补的班次 ID（来自 get_job_detail 班次列表）
        schedule_ids: 连报多天时传关联班次 ID，逗号分隔（对应 scheduleIds）
        skill_ids: 可选，岗位要求的技能标签 ID，逗号分隔
        require_complete_info: 是否先检查报名资料，默认 True
        user_confirmed: 必须为 true
        confirmation_summary: 可选，用户确认原话摘要

    Returns:
        候补提交结果 JSON
    """
    g = WriteGate(
        "apply_job_standby",
        user_confirmed,
        require_token=False,
        confirmation_summary=confirmation_summary,
        job_id=job_id,
        schedule_id=schedule_id,
        schedule_ids=schedule_ids,
        skill_ids=skill_ids,
        require_complete_info=require_complete_info,
    )
    if g.blocked:
        return g.blocked

    from tools.job_apply import (
        apply_job_standby as submit_standby,
        interpret_standby_result,
        parse_schedule_ids,
    )
    from tools.job_entry import parse_skill_ids

    try:
        if require_complete_info:
            from tools.job_entry import (
                assess_apply_readiness,
                fetch_entry_job_detail,
                fetch_job_detail as fetch_job_detail_data,
                format_readiness_blocker,
            )

            profile = await _get_profile()
            job_detail = await fetch_job_detail_data(_req, job_id)
            entry_detail = await fetch_entry_job_detail(_req, job_id)
            report = assess_apply_readiness(
                job_id=job_id,
                job_detail=job_detail,
                entry_detail=entry_detail,
                profile=profile,
                schedule_ids=[schedule_id],
                skill_ids=parse_skill_ids(skill_ids),
            )
            if not report["ready"]:
                return g.finish(format_readiness_blocker(report))

        multi_ids = parse_schedule_ids(schedule_ids) or None
        result = await submit_standby(
            _req,
            job_id,
            schedule_id,
            multi_schedule_ids=multi_ids,
            skill_ids=parse_skill_ids(skill_ids) or None,
        )
        return g.finish(interpret_standby_result(result, job_id, schedule_id))
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


@mcp.tool()
async def cancel_job_standby(
    job_id: int,
    schedule_id: int,
    schedule_ids: str = "",
    user_confirmed: bool = False,
    confirmation_summary: str = "",
) -> str:
    """取消班次候补。

    对应接口: Job/CancelEntryJobBackUp (POST)

    ⚠️ 须 user_confirmed=true（无需 confirm_token）。

    Args:
        job_id: 岗位 ID
        schedule_id: 班次 ID
        schedule_ids: 连报多天时传关联班次 ID，逗号分隔
        user_confirmed: 必须为 true
        confirmation_summary: 可选，用户确认原话摘要

    Returns:
        取消结果 JSON
    """
    g = WriteGate(
        "cancel_job_standby",
        user_confirmed,
        require_token=False,
        confirmation_summary=confirmation_summary,
        job_id=job_id,
        schedule_id=schedule_id,
        schedule_ids=schedule_ids,
    )
    if g.blocked:
        return g.blocked

    from tools.job_apply import (
        cancel_job_standby as cancel_standby,
        interpret_cancel_standby_result,
        parse_schedule_ids,
    )

    try:
        multi_ids = parse_schedule_ids(schedule_ids) or None
        result = await cancel_standby(
            _req,
            job_id,
            schedule_id,
            multi_schedule_ids=multi_ids,
        )
        return g.finish(interpret_cancel_standby_result(result, job_id, schedule_id))
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


@mcp.tool()
async def cancel_apply(
    job_id: int,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """取消报名/接单。

    对应接口: Personal/cancelentry (GET)

    ⚠️ 须先 prepare_write_confirmation 获取 confirm_token，再 user_confirmed=true 调用。

    Args:
        job_id: 要取消报名的岗位ID
        user_confirmed: 必须为 true
        confirm_token: prepare_write_confirmation 返回的一次性令牌
        confirmation_summary: 可选，用户确认原话摘要

    Returns:
        取消结果
    """
    g = WriteGate(
        "cancel_apply",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        job_id=job_id,
    )
    if g.blocked:
        return g.blocked

    try:
        result = await _req("GET", f"Personal/cancelentry?jobId={job_id}")
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if api_ok(result):
        return g.finish(f"✅ 已取消对岗位 {job_id} 的报名。")
    return g.finish(f"❌ 取消失败：{api_message(result, '未知错误')}")


@mcp.tool()
async def cancel_order(
    order_id: int,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """取消订单（已生成的干活订单，区别于 cancel_apply 取消报名）。

    对应接口: HoppedTask/CancelTask (POST)

    注意区分：
    - cancel_apply：取消岗位报名（尚未生成订单，接口 Personal/cancelentry）
    - cancel_order：取消已生成的干活订单（订单已确认，接口 HoppedTask/CancelTask）
    订单状态为「我已到达」等进展中状态时，取消可能需企业端确认。

    ⚠️ 须先 prepare_write_confirmation 获取 confirm_token，再 user_confirmed=true 调用。

    Args:
        order_id: 订单ID（数字，如 32124，可通过 get_task_detail 获取）
        user_confirmed: 必须为 true
        confirm_token: prepare_write_confirmation 返回的一次性令牌
        confirmation_summary: 可选，用户确认原话摘要

    Returns:
        取消结果
    """
    g = WriteGate(
        "cancel_order",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        order_id=order_id,
    )
    if g.blocked:
        return g.blocked

    try:
        result = await _req("POST", "HoppedTask/CancelTask", json={
            "task_id": order_id,
            "bargaining_status": 4,   # 4 = 用户取消
            "is_save": True,
            "cancel_reason": "用户主动取消",
        })
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if api_ok(result):
        return g.finish(f"✅ 已取消订单 {order_id}。 [v2-CancelTask]")
    return g.finish(f"❌ 取消失败：{api_message(result, '未知错误')}")


# ──── 我的订单/任务 ────

_STATUS_MAP = {
    "all": "all",
    "doing": "processing",
    "done": "completed",
    "cancelled": "cancelled",
    "pending": "pending",
    "processing": "processing",
    "completed": "completed",
}


async def _fetch_my_work_orders(status: str, page: int, page_size: int) -> str:
    api_status = _STATUS_MAP.get(status, status)
    payload = {"status": api_status, "pageNum": page, "pageSize": page_size}
    result = await _req("POST", "HoppedTask/OrderTaskList", json=payload)

    items = api_list(result)
    total = api_total(result)
    if not items:
        return "暂无相关订单记录。"

    status_label = status if status != "all" else "全部"
    lines = [f"我的干活记录（{status_label}，共{total}单）：\n"]
    for order in items:
        status_icon = {
            "pending": "⏳",
            "processing": "🔄",
            "completed": "✅",
            "cancelled": "❌",
        }.get(order.get("status"), "📋")
        oid = get_order_id(order)
        lines.append(
            f"{status_icon} [{oid}] {order_title(order)}\n"
            f"   💰 {order_salary(order)} | 📍 {order_location(order)}\n"
            f"   📅 {order_date(order)} | 状态: {order_status_desc(order)}"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_my_work_orders(
    status: str = "all",
    page: int = 1,
    page_size: int = 10,
) -> str:
    """获取我的干活订单列表（接单中心，文档标准名称）。

    对应接口: HoppedTask/OrderTaskList (POST)

    Args:
        status: 订单状态 all(全部)/doing(进行中)/done(已完成)/cancelled(已取消)
        page: 页码
        page_size: 每页数量
    """
    try:
        return await _fetch_my_work_orders(status, page, page_size)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


async def _find_order_in_list(order_id: int) -> dict:
    for page in range(1, 6):
        result = await _req(
            "POST",
            "HoppedTask/OrderTaskList",
            json={"status": "all", "pageNum": page, "pageSize": 20},
        )
        for item in api_list(result):
            if get_order_id(item) == order_id:
                return item
        if page * 20 >= api_total(result):
            break
    return {}


@mcp.tool()
async def get_task_detail(order_id: int) -> str:
    """获取订单/任务详情。

    对应接口: HoppedTask/GetOrderDetail (GET)

    Args:
        order_id: 订单ID

    Returns:
        订单详细信息，包含任务进度、联系方式等
    """
    try:
        result = await _req("GET", f"HoppedTask/GetOrderDetail?taskId={order_id}")
        data = api_data(result)
        if not data:
            result = await _req("GET", f"HoppedTask/GetOrderDetail?orderId={order_id}")
            data = api_data(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if not data:
        return f"订单 {order_id} 不存在。"

    list_item = {}
    if not order_title(data) or order_title(data) == "未知任务" or not order_location(data):
        list_item = await _find_order_in_list(order_id)

    merged = {**list_item, **data}
    status = order_status_desc(merged)
    if merged.get("event_show_name") and merged.get("event_show_name") != status:
        status = f"{status}（{merged['event_show_name']}）"

    lines = [
        f"📋 {order_title(merged)}",
        f"订单ID: {get_order_id(merged) or order_id}",
        f"订单编号: {merged.get('order_code', '—')}",
        f"状态: {status}",
        f"💰 结算金额: {order_salary(merged)}",
        f"📍 地点: {order_location(merged)}",
        f"📅 服务时间: {order_date(merged)}",
        f"📞 联系方式: {order_contact_phone(merged) or '请在小程序中查看'}",
        f"🏢 企业: {merged.get('company_name', '—')}",
        f"📝 备注: {merged.get('remark', merged.get('service_remark') or '无')}",
    ]

    if merged.get("receive_order"):
        lines.append(f"🕐 接单时间: {merged['receive_order']}")
    if merged.get("order_expiration_time"):
        lines.append(f"⏳ 截止时效: {merged['order_expiration_time']}")

    service_nodes = merged.get("service_nodes", [])
    if service_nodes:
        lines.append("\n📊 服务进度：")
        for step in service_nodes:
            icon = "🔴" if step.get("isRed") == 1 else "⚪"
            lines.append(f"   {icon} {step.get('nodeName', '')}")

    progress = merged.get("progress", [])
    if progress:
        lines.append("\n📊 任务进度：")
        for step in progress:
            done = "✅" if step.get("completed") else "⬜"
            lines.append(f"   {done} {step.get('name', '')} - {step.get('time', '')}")

    return "\n".join(lines)


@mcp.tool()
async def get_work_calendar(month: str = "") -> str:
    """获取干活日历（某月的任务排期）。

    对应接口: HoppedTask/GetCalendarTaskInfo (POST)

    Args:
        month: 月份，格式 YYYY-MM，如"2026-06"。不传则默认当月。

    Returns:
        日历排期，显示每天的工作安排
    """
    payload = {}
    if month:
        payload["month"] = month
    try:
        result = await _req("POST", "HoppedTask/GetCalendarTaskInfo", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    data = api_data(result)
    calendar = data.get("calendar") or api_list(result)
    if not calendar:
        return "暂无排期。"

    lines = [f"📅 {data.get('month', month or '本月')} 干活日历：\n"]
    for day in calendar:
        has_work = day.get("hasWork", False)
        icon = "🔵" if has_work else "⚪"
        tasks = day.get("tasks", [])
        task_info = f" ({len(tasks)}个任务)" if tasks else ""
        lines.append(f"{icon} {day.get('date', '')}{task_info}")
        for task in tasks:
            lines.append(
                f"   📋 {task.get('title', '')} | "
                f"{task.get('timeStart', '')}-{task.get('timeEnd', '')}"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")

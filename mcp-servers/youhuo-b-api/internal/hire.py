"""有活平台 B 端招工/用工 MCP Server。

提供岗位发布、费用预估、报名查看、排班考勤、待办处理等能力。
job-planner / workforce-dispatcher Skill 依赖本 Server。
依赖 youhuo-auth-service 完成扫码授权后获取 Token。
"""
import os
import sys
import json
import httpx
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared_token_store import auth_store
from tools.youhuo_env import employ_base_url
from tools.api_response import (
    api_ok,
    api_message,
    api_data,
    api_list,
    api_records,
    api_total,
    flatten_tree_nodes,
    format_b_todo_item,
)
from tools.job_publish import (
    address_from_job_detail,
    build_publish_payload,
    publish_template_from_detail,
)
from tools.job_schedule import (
    SCHEDULE_DETAIL_TABS,
    SCHEDULE_LIST_TABS,
    build_schedule_detail_payload,
    build_schedule_list_payload,
    format_b_schedule_detail_header,
    format_b_schedule_detail_item,
    format_b_schedule_list_header,
    format_b_schedule_list_item,
)
from tools.job_publish_payment import (
    PAYMENT_TYPE_BALANCE,
    PAYMENT_TYPE_WECHAT,
    build_balance_payment_payload,
    build_payment_preview,
    fetch_job_publish_order,
    interpret_balance_payment_result,
)
from tools.enterprise_balance import (
    build_enterprise_balance_view,
    parse_user_profile,
    unwrap_balance_payload,
    validate_balance_for_publish,
    publish_balance_error_json,
)
from tools.mcp_write_guard import WriteGate
from tools.cooperate_workers import (
    COOPERATE_LIST_TABS,
    build_invite_param_from_job,
    build_invite_param_from_task,
    format_cooperate_count,
    format_cooperate_workers,
    parse_worker_user_ids,
    resolve_cooperate_tab,
)
from tools.recruit_address import (
    address_record_to_summary,
    build_save_recruit_address_payload,
    fetch_recruit_address_list,
    find_best_address_match,
    format_recruit_addresses_text,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[ERROR] mcp not installed. Run: pip install mcp httpx")
    sys.exit(1)

mcp = FastMCP("youhuo-hire-api")

EMPLOY_URL = employ_base_url()


async def _req(method: str, path: str, **kwargs):
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception(
            "未授权：请先调用 youhuo-b-api.create_auth_session() "
            "完成扫码授权，再执行此操作"
        )
    token = token_info["token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-USER_ROLE": "2",  # B端固定传2
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{EMPLOY_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


# ──── 费用预估 ────

@mcp.tool()
async def preview_publish_cost(
    product_type: int,
    subscript_worker_count: int = 0,
    subscript_day_count: int = 0,
    headcount: int = 0,
    hourly_wage: float = 0,
    schedule_start: str = "",
    schedule_end: str = "",
    job_date: str = "",
) -> str:
    """预估发布岗位所需费用（含小时工/计件工工钱预估）。

    **长期招（productType=2/5）**：按积分订阅制计算，公式：人数 × 天数 × 0.5 积分/人/天。
    10积分=1元人民币。发布后需调用 pay_publish_points 支付积分。

    **小时工/计件工（productType=4/6）**：
    - 传入 headcount、hourly_wage、schedule_start、schedule_end 可预估**零工工钱**
    - **平台服务费**由后端根据岗位信息计算，须 publish_jd 创建待发布岗位后
      调用 get_job_publish_payment(jd_id) 获取（工钱 + 服务费 + 应付合计）
    - 支付前须向用户展示完整费用明细并获确认，再 pay_hourly_job

    对应前端逻辑：long-term/index.vue（长期招积分计算）/ hourly-worker/publish.vue（小时工余额支付）

    Args:
        product_type: 岗位类型。2/5=长期招（需积分），4=小时工，6=计件工
        subscript_worker_count: 订阅人数（长期招需要）
        subscript_day_count: 订阅天数（长期招需要，最少7天）
        headcount: 小时工/计件工招募人数（用于工钱预估）
        hourly_wage: 时薪或计件单价（元）
        schedule_start: 班次开始 HH:MM
        schedule_end: 班次结束 HH:MM
        job_date: 班次日期 YYYY-MM-DD（可选，默认今天）

    Returns:
        JSON字符串，包含预估费用、计算明细
    """
    if product_type in (2, 5):
        if subscript_worker_count <= 0 or subscript_day_count <= 0:
            return json.dumps(
                {"error": "长期招需要设置订阅人数和订阅天数"},
                ensure_ascii=False,
            )
        if subscript_day_count < 7:
            return json.dumps(
                {"error": "订阅天数最少7天"},
                ensure_ascii=False,
            )
        points = subscript_worker_count * subscript_day_count * 0.5
        return json.dumps(
            {
                "product_type": product_type,
                "type_name": "长期招聘" if product_type == 2 else "长期招(其他)",
                "subscript_worker_count": subscript_worker_count,
                "subscript_day_count": subscript_day_count,
                "points": points,
                "rmb": round(points / 10, 2),
                "formula": f"{subscript_worker_count}人 × {subscript_day_count}天 × 0.5积分/人/天 = {points}积分",
                "note": "发布后需调用 pay_publish_points 完成积分支付",
            },
            ensure_ascii=False,
        )

    from tools.job_publish import _hours_between

    type_name = "小时工" if product_type == 4 else "计件工"
    out: dict = {
        "product_type": product_type,
        "type_name": type_name,
        "service_fee_amount": None,
        "balance_payment": None,
        "note": (
            f"{type_name}平台服务费由后端计算。"
            "须 publish_jd 创建待发布岗位后调用 get_job_publish_payment 获取精确工钱、服务费与应付合计，"
            "向用户展示并确认后再 pay_hourly_job。"
        ),
    }

    if headcount > 0 and hourly_wage > 0 and schedule_start and schedule_end:
        hours = _hours_between(schedule_start, schedule_end)
        labor = round(headcount * hours * hourly_wage, 2)
        out.update(
            {
                "headcount": headcount,
                "hourly_wage": hourly_wage,
                "schedule_start": schedule_start,
                "schedule_end": schedule_end,
                "job_date": job_date or date.today().isoformat(),
                "hours_per_shift": hours,
                "labor_amount_estimate": labor,
                "labor_formula": f"{headcount}人 × {hours}h × ¥{hourly_wage} = ¥{labor}",
                "summary": (
                    f"预估零工工钱：¥{labor}（{out['labor_formula']}）\n"
                    f"平台服务费：待 publish_jd 后 get_job_publish_payment 查询\n"
                    f"应付合计：工钱 + 服务费（支付前须展示并获用户确认）"
                ),
            }
        )
    return json.dumps(out, ensure_ascii=False, indent=2)


async def _fetch_job_detail(job_id: int) -> dict:
    result = await _req("POST", "miniprogram/jd/detail", json={"id": job_id})
    if not api_ok(result):
        raise Exception(api_message(result, "获取岗位详情失败"))
    data = result.get("data") or result.get("Data") or {}
    if not isinstance(data, dict):
        raise Exception("岗位详情为空")
    return data


async def _attach_payment_preview(job_id: int, product_type: int) -> dict:
    """publish_jd 成功后附加待支付明细，供 Agent 支付前向用户展示。"""
    try:
        order = await fetch_job_publish_order(_req, job_id)
        preview = build_payment_preview(job_id, order, product_type=product_type)
        return {"payment_preview": preview}
    except Exception as e:
        return {
            "payment_preview": None,
            "payment_preview_error": str(e),
            "guide": "请调用 get_job_publish_payment 获取工钱、服务费与应付合计",
        }


# ──── 发布参考（模板 / 干活地点） ────

async def _build_publish_template(job_id: int) -> dict:
    detail = await _fetch_job_detail(job_id)
    return {"success": True, **publish_template_from_detail(detail)}


async def _collect_recruit_addresses(reference_job_id: int = 0) -> list[dict]:
    """优先从 userRecruitAddress/list 读取；无数据时回退到历史岗位详情。"""
    try:
        listed = await fetch_recruit_address_list(_req, page=1, page_size=50)
        records = listed.get("records") or []
        if records:
            return [
                {
                    "recruit_address_id": r.get("id"),
                    "store_name": r.get("storeAbbreviation"),
                    "work_address": r.get("workAddress"),
                    "city": r.get("city"),
                    "district": r.get("district"),
                    "complete_info": r.get("completeInfo"),
                    "reference_job_id": 0,
                }
                for r in records
                if r.get("id")
            ]
    except Exception:
        pass

    addresses: list[dict] = []
    seen: set[int] = set()

    async def add_from_detail(jid: int) -> None:
        detail = await _fetch_job_detail(jid)
        addr_id = detail.get("recruitAddressId")
        if not addr_id or addr_id in seen:
            return
        seen.add(addr_id)
        info = address_from_job_detail(detail)
        addresses.append(
            {
                "recruit_address_id": addr_id,
                "store_name": info.get("store_name"),
                "work_address": info.get("work_address"),
                "city": info.get("city"),
                "district": info.get("district"),
                "reference_job_id": jid,
            }
        )

    if reference_job_id:
        await add_from_detail(reference_job_id)
    else:
        for product_type in (4, 6):
            result = await _req(
                "POST",
                "miniprogram/jd/list",
                json={"status": "all", "pageNum": 1, "pageSize": 10, "productType": product_type},
            )
            for item in api_records(result):
                if len(addresses) >= 5:
                    break
                jid = item.get("id") or item.get("jdId")
                if jid:
                    await add_from_detail(int(jid))
    return addresses


def _format_recruit_addresses(addresses: list[dict]) -> str:
    if not addresses:
        return "未找到可用干活地点。请提供 job_id 或先在小程序中添加门店地址。"
    lines = ["可用干活地点：\n"]
    for a in addresses:
        lines.append(
            f"  • [{a['recruit_address_id']}] {a.get('store_name') or '—'} | "
            f"{a.get('work_address')}（参考岗位 {a['reference_job_id']}）"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_publish_reference(job_id: int = 0, mode: str = "both") -> str:
    """获取发岗参考信息（发布模板 / 干活地点）。

    发布小时工/计件工前，可从此 Tool 获取门店地址与分类排班样例，
    再调用 publish_jd(reference_job_id=..., recruit_address_id=...)。

    Args:
        job_id: 参考岗位 ID。addresses 模式下为 0 时从最近小时工/计件工岗位提取
        mode: template（发布模板）| addresses（干活地点）| both（两者）
    """
    m = (mode or "both").strip().lower()
    if m not in ("template", "addresses", "both"):
        return json.dumps(
            {"success": False, "error": "mode 须为 template、addresses 或 both"},
            ensure_ascii=False,
        )

    parts: dict = {"success": True, "mode": m}
    text_blocks: list[str] = []

    if m in ("template", "both"):
        if job_id <= 0:
            if m == "template":
                return json.dumps(
                    {"success": False, "error": "template 模式须提供 job_id"},
                    ensure_ascii=False,
                )
            parts["template"] = {"skipped": True, "reason": "未提供 job_id"}
        else:
            try:
                tpl = await _build_publish_template(job_id)
                parts["template"] = tpl
                text_blocks.append(json.dumps(tpl, ensure_ascii=False, indent=2))
            except Exception as e:
                return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if m in ("addresses", "both"):
        try:
            addresses = await _collect_recruit_addresses(job_id)
            parts["addresses"] = addresses
            text_blocks.append(_format_recruit_addresses(addresses))
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if len(text_blocks) == 1:
        return text_blocks[0]
    return json.dumps(parts, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_recruit_addresses(
    page: int = 1,
    page_size: int = 20,
    address_query: str = "",
    format: str = "text",
) -> str:
    """查询企业已录入的用工地点，并可匹配用户口述地址。

    对应接口: userRecruitAddress/list (POST)

    发布小时工/计件工前，先调用本 Tool 获取 recruit_address_id。
    若 address_query 与已有地址不一致，须向用户确认后调用 save_recruit_address 录入。

    Args:
        page: 页码
        page_size: 每页数量
        address_query: 可选，用户口述地址；返回 matched 匹配结果
        format: text（默认）或 json
    """
    try:
        listed = await fetch_recruit_address_list(_req, page=page, page_size=page_size)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    records = listed.get("records") or []
    query = (address_query or "").strip()
    matched = find_best_address_match(records, query) if query else None

    if (format or "text").strip().lower() == "json":
        return json.dumps(
            {
                "success": True,
                "total": listed.get("total", len(records)),
                "page": page,
                "page_size": page_size,
                "address_query": query or None,
                "matched": matched is not None,
                "match": matched,
                "addresses": [address_record_to_summary(r) for r in records],
                "guide": (
                    None
                    if matched or not query
                    else "无匹配地址时可调用 save_recruit_address 录入（须 prepare_write_confirmation）"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )

    return format_recruit_addresses_text(
        records,
        total=int(listed.get("total") or len(records)),
        matched=matched,
        query=query,
    )


@mcp.tool()
async def save_recruit_address(
    work_address: str,
    store_name: str,
    floor_num: str,
    house_num: str,
    contacts: str,
    contact_phone: str,
    street_number: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
    short_address: str = "",
    lng: float = 0,
    lat: float = 0,
    default_address: bool = False,
    alternate_phone: str = "",
    address_id: int = 0,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """录入新的用工地点到企业地址库。

    对应接口: userRecruitAddress/save (POST)

    ⚠️ 写操作须先 prepare_write_confirmation，再 user_confirmed=true + confirm_token。
    建议在 get_recruit_addresses(address_query=...) 未匹配到已有地址、
    且已向用户展示待录入信息并获确认后再调用。

    Args:
        work_address: 详细工作地址（地图选点后的完整地址）
        store_name: 门店简称（必填，最多15字）
        floor_num: 楼层号
        house_num: 门牌号
        contacts: 联系人姓名
        contact_phone: 联系电话（11位手机号）
        street_number: 地点/POI 名称（如「竞园27C」，默认同 store_name）
        province: 省
        city: 市
        district: 区
        short_address: 短地址（如「朝阳区百子湾南二路」）
        lng: 经度（强烈建议提供，便于打卡定位）
        lat: 纬度
        default_address: 是否设为默认地址
        alternate_phone: 备用电话
        address_id: 编辑已有地址时传入 ID；新建留 0
        user_confirmed: 必须为 true
        confirm_token: prepare_write_confirmation 返回的一次性令牌
        confirmation_summary: 用户确认原话摘要
    """
    g = WriteGate(
        "save_recruit_address",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        work_address=work_address,
        store_name=store_name,
        floor_num=floor_num,
        house_num=house_num,
        contacts=contacts,
        contact_phone=contact_phone,
        street_number=street_number,
        province=province,
        city=city,
        district=district,
        short_address=short_address,
        lng=lng,
        lat=lat,
        default_address=default_address,
        alternate_phone=alternate_phone,
        address_id=address_id,
    )
    if g.blocked:
        return g.blocked

    required = {
        "work_address": work_address,
        "store_name": store_name,
        "floor_num": floor_num,
        "house_num": house_num,
        "contacts": contacts,
        "contact_phone": contact_phone,
    }
    missing = [k for k, v in required.items() if not str(v or "").strip()]
    if missing:
        return g.finish(
            json.dumps(
                {
                    "success": False,
                    "error": f"缺少必填项：{', '.join(missing)}",
                    "guide": "请向用户追问门店简称、楼层、门牌、联系人、联系电话",
                },
                ensure_ascii=False,
            ),
        )

    phone = str(contact_phone).strip()
    if len(phone) != 11 or not phone.isdigit():
        return g.finish(
            json.dumps({"success": False, "error": "contact_phone 须为 11 位手机号"}, ensure_ascii=False),
        )

    payload = build_save_recruit_address_payload(
        work_address=work_address,
        store_name=store_name,
        floor_num=floor_num,
        house_num=house_num,
        contacts=contacts,
        contact_phone=phone,
        street_number=street_number,
        province=province,
        city=city,
        district=district,
        short_address=short_address,
        lng=lng if lng else None,
        lat=lat if lat else None,
        default_address=default_address,
        alternate_phone=alternate_phone,
        address_id=address_id,
    )

    try:
        result = await _req("POST", "userRecruitAddress/save", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if not api_ok(result):
        return g.finish(
            json.dumps({"success": False, "error": api_message(result, "录入用工地点失败")}, ensure_ascii=False),
        )

    data = api_data(result)
    if not isinstance(data, dict):
        data = {}
    summary = address_record_to_summary(data)
    return g.finish(
        json.dumps(
            {
                "success": True,
                "message": "用工地点已录入",
                "recruit_address_id": summary.get("recruit_address_id"),
                **summary,
                "next_step": "可在 publish_jd 中传入 recruit_address_id 发布岗位",
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


@mcp.tool()
async def publish_jd(
    title: str,
    work_category: str,
    description: str,
    location: str,
    salary_min: float,
    salary_max: float,
    headcount: int,
    product_type: int = 4,
    skills: list = None,
    benefits: list = None,
    subscript_worker_count: int = 0,
    subscript_day_count: int = 0,
    reference_job_id: int = 0,
    recruit_address_id: int = 0,
    work_category_id: int = 0,
    position_type: int = 0,
    template_id: int = 0,
    job_date: str = "",
    schedule_start: str = "09:00",
    schedule_end: str = "18:00",
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """发布岗位到有活平台（B端企业招工）。支持长期招、小时工、计件工。

    对应接口: miniprogram/jd/publish (POST)

    ⚠️ 调用约束：须先补齐岗位/排班/地址信息，调用 preview_publish_cost +
    get_enterprise_finance，向企业用户展示费用并获明确确认（如「确认发布」）后再执行；
    须 user_confirmed=true + confirm_token（先 prepare_write_confirmation）。发布前 MCP 硬校验：长期招积分或现金可用余额须大于 0。
    小时工/计件工发布将从余额扣服务费；禁止代用户确认或代充值。

    **小时工/计件工必填扩展字段**（可通过 reference_job_id 自动带入）：
    - recruit_address_id：干活地点 ID（recruitAddressId）
    - work_category_id / position_type / template_id：工作分类与模板
    - job_date + schedule_start/end：班次日期与时段
    - 班次列表字段名为 workingScheduleList（非 recruitWorkingScheduleList）

    **发布后的支付差异**：
    - 长期招（productType=2/5）：发布后需调用 pay_publish_points 支付积分订阅费
    - 小时工/计件工（productType=4/6）：publish_jd 仅创建岗位；须 get_job_publish_payment 查费用后 pay_hourly_job 扣余额上架

    Args:
        title: 岗位名称，如"餐厅小时工""仓库分拣员"
        work_category: 工作类别名称（展示用）
        description: 岗位描述和要求（positionDesc）
        location: 工作地点文本
        salary_min: 薪资下限（元/小时 或 元/件）
        salary_max: 薪资上限
        headcount: 招募人数（单班次 needCount）
        product_type: 岗位类型。2/5=长期招，4=小时工，6=计件工。默认4（小时工）
        skills: 所需技能标签列表
        benefits: 福利标签列表
        subscript_worker_count: 订阅人数（长期招需要，默认0）
        subscript_day_count: 订阅天数（长期招需要，最少7天，默认0）
        reference_job_id: 参考岗位 ID，自动复制门店/分类/排班模板
        recruit_address_id: 干活地点 ID（无参考岗位时必填）
        work_category_id: 工作分类 ID
        position_type: 岗位模板类型 ID
        template_id: 模板 ID
        job_date: 班次日期 YYYY-MM-DD，默认今天
        schedule_start: 班次开始时间 HH:MM
        schedule_end: 班次结束时间 HH:MM
        user_confirmed: 必须为 true，表示企业用户已明确确认发布（硬门禁）
        confirmation_summary: 可选，用户确认原话摘要，记入审计日志
        confirm_token: prepare_write_confirmation 返回的一次性令牌
    """
    token_params = {
        "title": title,
        "work_category": work_category,
        "description": description,
        "location": location,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "headcount": headcount,
        "product_type": product_type,
        "skills": skills,
        "benefits": benefits,
        "subscript_worker_count": subscript_worker_count,
        "subscript_day_count": subscript_day_count,
        "reference_job_id": reference_job_id,
        "recruit_address_id": recruit_address_id,
        "work_category_id": work_category_id,
        "position_type": position_type,
        "template_id": template_id,
        "job_date": job_date,
        "schedule_start": schedule_start,
        "schedule_end": schedule_end,
    }
    g = WriteGate(
        "publish_jd",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        **token_params,
    )
    if g.blocked:
        return g.blocked

    try:
        balance_result = await _req("POST", "miniprogram/account/balance", json={})
        profile_result = await _req("GET", "user/login/getUserLoginDetail")
        balance_view = build_enterprise_balance_view(
            unwrap_balance_payload(balance_result),
            parse_user_profile(profile_result),
        )
        balance_err = validate_balance_for_publish(balance_view, product_type=product_type)
        if balance_err:
            return g.finish(publish_balance_error_json(balance_err))
    except Exception as e:
        return g.finish(
            json.dumps({"success": False, "error": f"发布前余额校验失败：{e}"}, ensure_ascii=False),
        )

    reference_detail = None
    if reference_job_id:
        try:
            reference_detail = await _fetch_job_detail(reference_job_id)
        except Exception as e:
            return g.finish(
                json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
            )

    if product_type in (4, 6):
        addr_id = recruit_address_id or (reference_detail or {}).get("recruitAddressId")
        if not addr_id:
            return g.finish(
                json.dumps(
                    {
                        "success": False,
                        "error": "小时工/计件工需指定干活地点：设置 reference_job_id 或 recruit_address_id",
                        "guide": "先调用 get_publish_reference(job_id=..., mode=both) 获取地址与模板",
                    },
                    ensure_ascii=False,
                ),
            )

    payload = build_publish_payload(
        title=title,
        description=description,
        product_type=product_type,
        headcount=headcount,
        salary_min=salary_min,
        salary_max=salary_max,
        reference_detail=reference_detail,
        recruit_address_id=recruit_address_id or None,
        work_category_id=work_category_id or None,
        position_type=position_type or None,
        template_id=template_id or None,
        location=location,
        job_date=job_date or None,
        schedule_start=schedule_start,
        schedule_end=schedule_end,
        skills=skills,
        benefits=benefits,
        subscript_worker_count=subscript_worker_count,
        subscript_day_count=subscript_day_count,
    )
    if work_category and not payload.get("workCategoryId"):
        payload["workCategory"] = work_category

    try:
        result = await _req("POST", "miniprogram/jd/publish", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if api_ok(result):
        data = result.get("data") or result.get("Data") or {}
        if isinstance(data, dict):
            jd_id = data.get("id") or data.get("jdId")
        else:
            jd_id = data if isinstance(data, int) else None
        if product_type in (2, 5):
            return g.finish(
                json.dumps(
                    {
                        "success": True,
                        "jd_id": jd_id,
                        "product_type": product_type,
                        "message": "岗位已创建",
                        "note": "长期招需继续调用 pay_publish_points 完成积分支付",
                    },
                    ensure_ascii=False,
                ),
            )
        return g.finish(
            json.dumps(
                {
                    "success": True,
                    "jd_id": jd_id,
                    "product_type": product_type,
                    "message": "岗位已创建（待支付，尚未上架）",
                    "note": (
                        "须向用户展示 payment_preview（工钱+服务费+应付合计）并获确认后，"
                        "再 prepare_write_confirmation → pay_hourly_job 完成支付上架"
                    ),
                    "next_step": "pay_hourly_job",
                    **await _attach_payment_preview(jd_id, product_type),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return g.finish(
        json.dumps(
            {"success": False, "error": api_message(result, "发布失败")},
            ensure_ascii=False,
        ),
    )


@mcp.tool()
async def get_job_publish_payment(job_id: int) -> str:
    """查询小时工/计件工发布后的待支付明细（R0，不扣款）。

    对应接口: hourly-worker/job-info/{job_id}/order (GET)

    在 publish_jd 成功后调用，展示工钱、服务费、应付合计，供用户确认后再 pay_hourly_job。

    Args:
        job_id: publish_jd 返回的岗位 ID
    """
    try:
        detail = await _fetch_job_detail(job_id)
        product_type = int(detail.get("productType") or 0)
        if product_type not in (4, 6):
            return json.dumps(
                {
                    "success": False,
                    "error": f"岗位 {job_id} 类型为 {product_type}，无需 pay_hourly_job",
                    "guide": "长期招请使用 pay_publish_points",
                },
                ensure_ascii=False,
            )
        order = await fetch_job_publish_order(_req, job_id)
        preview = build_payment_preview(job_id, order, product_type=product_type)
        return json.dumps({"success": True, **preview}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def pay_hourly_job(
    job_id: int,
    payment_type: int = PAYMENT_TYPE_BALANCE,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """小时工/计件工发布后余额支付（第二步，扣款并上架）。

    对应接口: account/balance-payment (POST)

    ⚠️ 须在 publish_jd 成功后调用；须先 get_job_publish_payment 展示费用，
    prepare_write_confirmation 获 confirm_token，再 user_confirmed=true 调用。
    MCP 仅支持 payment_type=1（余额支付），不支持代拉起微信支付。

    Args:
        job_id: publish_jd 返回的岗位 ID
        payment_type: 1=余额支付（默认），2=微信（MCP 不支持，会返回 WECHAT_PAY_REQUIRED）
        user_confirmed: 必须为 true
        confirm_token: prepare_write_confirmation 返回的一次性令牌
        confirmation_summary: 可选，用户确认原话摘要
    """
    g = WriteGate(
        "pay_hourly_job",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        job_id=job_id,
        payment_type=payment_type,
    )
    if g.blocked:
        return g.blocked

    if payment_type not in (PAYMENT_TYPE_BALANCE, PAYMENT_TYPE_WECHAT):
        return g.finish(
            json.dumps(
                {"success": False, "error": "payment_type 仅支持 1（余额）或 2（微信）"},
                ensure_ascii=False,
            )
        )

    try:
        detail = await _fetch_job_detail(job_id)
        product_type = int(detail.get("productType") or 0)
        order = await fetch_job_publish_order(_req, job_id)
        preview = build_payment_preview(job_id, order, product_type=product_type)

        if preview.get("already_paid"):
            return g.finish(
                json.dumps(
                    {
                        "success": True,
                        "job_id": job_id,
                        "message": "岗位已支付，无需重复扣款",
                        **preview,
                    },
                    ensure_ascii=False,
                )
            )

        balance_payment = float(preview.get("balance_payment") or 0)
        if payment_type == PAYMENT_TYPE_BALANCE and balance_payment > 0:
            balance_result = await _req("POST", "miniprogram/account/balance", json={})
            profile_result = await _req("GET", "user/login/getUserLoginDetail")
            balance_view = build_enterprise_balance_view(
                unwrap_balance_payload(balance_result),
                parse_user_profile(profile_result),
            )
            available = float(balance_view.get("primary_pay_balance") or 0)
            if available < balance_payment:
                return g.finish(
                    json.dumps(
                        {
                            "success": False,
                            "reason": "BALANCE_INSUFFICIENT",
                            "message": f"个人余额 ¥{available} 不足，需支付 ¥{balance_payment}",
                            "guide": "请前往有活小程序充值后再支付。",
                            "job_id": job_id,
                        },
                        ensure_ascii=False,
                    )
                )

        payload = build_balance_payment_payload(
            job_id,
            order,
            product_type=product_type,
            payment_type=payment_type,
        )
        result = await _req("POST", "account/balance-payment", json=payload)
        outcome = interpret_balance_payment_result(result, job_id)
        return g.finish(json.dumps(outcome, ensure_ascii=False, indent=2))
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


@mcp.tool()
async def pay_publish_points(
    jd_id: int,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """支付长期招岗位发布所需的积分（仅限 productType=2/5）。

    对应接口: miniprogram/jd/payPointsToPublish (POST)

    ⚠️ 调用约束：须在 publish_jd 成功后、且已向用户展示积分扣费明细并获明确确认
    （如「确认支付积分」）后再调用；须 user_confirmed=true。积分不足时引导小程序充值，禁止代充值。

    在 publish_jd 成功后调用，完成积分扣费，岗位正式上架。
    如果积分余额不足会返回错误，需要引导用户去小程序充值。

    Args:
        jd_id: publish_jd 返回的岗位ID
        user_confirmed: 必须为 true，表示企业用户已明确确认支付
        confirmation_summary: 可选，用户确认原话摘要

    Returns:
        支付结果。积分余额不足时返回明确的引导信息。
    """
    g = WriteGate(
        "pay_publish_points",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        jd_id=jd_id,
    )
    if g.blocked:
        return g.blocked

    payload = {"id": jd_id}
    try:
        result = await _req("POST", "miniprogram/jd/payPointsToPublish", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if result.get("code") == 200:
        return g.finish(
            json.dumps(
                {"success": True, "message": f"积分支付成功！岗位 {jd_id} 已正式上架。"},
                ensure_ascii=False,
            ),
        )

    msg = result.get("message", "支付失败")
    if "余额" in msg or "不足" in msg or "积分" in msg:
        return g.finish(
            json.dumps(
                {
                    "success": False,
                    "reason": "BALANCE_INSUFFICIENT",
                    "message": f"积分余额不足，无法完成支付。\n错误信息：{msg}",
                    "guide": "请前往有活小程序充值积分：打开微信 → 搜索'有活'小程序 → 我的 → 充值积分。充值完成后，告诉我'继续支付'即可。",
                },
                ensure_ascii=False,
            ),
        )
    return g.finish(json.dumps({"success": False, "error": msg}, ensure_ascii=False))


# ──── 岗位列表 ────

@mcp.tool()
async def get_job_list(
    status: str = "all",
    page: int = 1,
    page_size: int = 10,
    product_type: int = 0,
) -> str:
    """查询企业已发布的招工岗位列表。

    对应接口: miniprogram/jd/list (POST)

    Args:
        status: 岗位状态 all/active/closed
        page: 页码
        page_size: 每页数量
        product_type: 岗位类型筛选。0=全部，4=小时工，6=计件工，2=长期招
    """
    payload = {"status": status, "pageNum": page, "pageSize": page_size}
    if product_type:
        payload["productType"] = product_type
    try:
        result = await _req("POST", "miniprogram/jd/list", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    items = api_records(result)
    if not items:
        return "暂无发布的岗位。"

    lines = ["已发布岗位列表：\n"]
    for jd in items:
        jd_id = jd.get("jdId") or jd.get("id")
        title = jd.get("title") or jd.get("positionTitle", "—")
        lines.append(
            f"{'🟢' if jd.get('status') == 'active' else '🔴'} "
            f"[{jd_id}] {title} | "
            f"报名 {jd.get('applyCount', 0)}/{jd.get('headcount') or jd.get('recruitNumber') or 0} 人"
        )
    return "\n".join(lines)


# ──── 查看报名 / 候选人管理 ────

def _format_job_workers(job_id: int, result: dict) -> str:
    workers = api_records(result)
    total = api_total(result)
    if not workers:
        return f"岗位 {job_id} 暂无报名人员。"

    lines = [f"岗位 {job_id} 报名人员（共{total}人）：\n"]
    for w in workers:
        user_id = w.get("userId") or w.get("user_id") or "—"
        lines.append(
            f"👤 [{user_id}] {w.get('name', '未知')} | "
            f"评分: {w.get('star', 'N/A')} | "
            f"完成单量: {w.get('finishCount', 0)} | "
            f"状态: {w.get('statusDesc', '待处理')}"
        )
    return "\n".join(lines)


async def _fetch_job_workers(job_id: int, page: int, page_size: int) -> dict:
    payload = {"jobId": job_id, "pageNum": page, "pageSize": page_size}
    return await _req("POST", "recruitWorkingSchedule/getPersonByJobId", json=payload)


@mcp.tool()
async def get_job_workers(
    job_id: int,
    page: int = 1,
    page_size: int = 10,
) -> str:
    """获取岗位下已报名/匹配的零工人员列表（workforce-dispatcher 核心 Tool）。

    对应接口: recruitWorkingSchedule/getPersonByJobId (POST)

    Args:
        job_id: 岗位ID
        page: 页码
        page_size: 每页数量
    """
    try:
        result = await _fetch_job_workers(job_id, page, page_size)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    return _format_job_workers(job_id, result)


@mcp.tool()
async def mark_worker_suitable(
    jd_id: int,
    user_id: int,
    mark: int,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """标记候选零工是否合适。

    对应接口: miniprogram/jd/markCv (POST)

    ⚠️ 调用约束：须先展示候选人列表，由企业用户明确指定人选与标记（合适/不合适）
    后再调用；须 user_confirmed=true。禁止自动批量标记。

    Args:
        jd_id: 岗位ID
        user_id: 零工用户ID
        mark: 1=合适 2=不合适
        user_confirmed: 必须为 true
        confirmation_summary: 可选，用户确认原话摘要
    """
    g = WriteGate(
        "mark_worker_suitable",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        jd_id=jd_id,
        user_id=user_id,
        mark=mark,
    )
    if g.blocked:
        return g.blocked

    if mark not in (1, 2):
        return g.finish(
            json.dumps({"success": False, "error": "mark 必须为 1（合适）或 2（不合适）"}, ensure_ascii=False),
        )

    payload = {"jdId": jd_id, "userId": user_id, "mark": mark}
    try:
        result = await _req("POST", "miniprogram/jd/markCv", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if result.get("code") != 200:
        return g.finish(
            json.dumps({"success": False, "error": result.get("message", "标记失败")}, ensure_ascii=False),
        )

    mark_desc = "✅ 合适" if mark == 1 else "❌ 不合适"
    return g.finish(f"已标记用户 {user_id} 为{mark_desc}")


# ──── 合作零工 / 邀请报名 ────

async def _resolve_user_enterprise_id() -> int:
    profile_result = await _req("GET", "user/login/getUserLoginDetail")
    profile = parse_user_profile(profile_result)
    eid = profile.get("userEnterpriseId") or profile.get("enterpriseId") or 0
    return int(eid or 0)


async def _fetch_cooperate_workers(cooperate_type: int, user_enterprise_id: int) -> list[dict]:
    result = await _req(
        "GET",
        f"user/login/getCooperateUserList?cooperateType={cooperate_type}&userEnterpriseId={user_enterprise_id}",
    )
    items = api_list(result)
    return [x for x in items if isinstance(x, dict)]


async def _fetch_recruiting_job_for_invite(job_id: int, user_enterprise_id: int, invite_type: int) -> dict:
    if invite_type == 2:
        result = await _req(
            "GET",
            f"miniprogram/jd/getTaskOrderList?userEnterpriseId={user_enterprise_id}",
        )
        items = api_list(result)
        for item in items:
            if isinstance(item, dict) and int(item.get("id") or 0) == job_id:
                return item
        raise Exception(f"未找到招募中的众包订单 {job_id}，请确认订单处于待接单状态")

    result = await _req(
        "GET",
        f"miniprogram/jd/getEnterpriseJobList?userEnterpriseId={user_enterprise_id}",
    )
    items = api_list(result)
    for item in items:
        if isinstance(item, dict) and int(item.get("id") or 0) == job_id:
            return item

    detail = await _fetch_job_detail(job_id)
    status = str(detail.get("status") or detail.get("jobStatus") or "").lower()
    if status in ("closed", "offline", "5"):
        raise Exception(f"岗位 {job_id} 已下线，无法邀请报名")
    return detail


@mcp.tool()
async def get_cooperate_workers(
    list_tab: str = "cooperate",
) -> str:
    """查询合作过的零工或黑名单（workforce-dispatcher 复聘场景）。

    对应接口:
    - user/login/getCooperateUserCount (GET)
    - user/login/getCooperateUserList (GET)

    Args:
        list_tab: cooperate（合作过，默认）或 blacklist（黑名单）；也支持 1/2、中文
    """
    resolved = resolve_cooperate_tab(list_tab)
    if not resolved:
        tabs = ", ".join(COOPERATE_LIST_TABS)
        return json.dumps(
            {"success": False, "error": f"list_tab 无效，可选：{tabs}"},
            ensure_ascii=False,
        )

    cooperate_type, tab_label = resolved
    try:
        user_enterprise_id = await _resolve_user_enterprise_id()
        count_result = await _req("GET", "user/login/getCooperateUserCount")
        count_payload = api_data(count_result) if isinstance(count_result, dict) else {}
        workers = await _fetch_cooperate_workers(cooperate_type, user_enterprise_id)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    header = format_cooperate_count(count_payload)
    body = format_cooperate_workers(workers, tab_label=tab_label)
    if header:
        return f"{header}\n\n{body}"
    return body


@mcp.tool()
async def invite_worker_to_job(
    job_id: int,
    worker_user_ids: str,
    invite_type: int = 1,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """邀请合作零工报名指定招募中岗位/订单。

    对应接口: miniprogram/jd/inviteUserToWork (POST)

    ⚠️ 写操作须先 prepare_write_confirmation，再 user_confirmed=true + confirm_token。
    须先调用 get_cooperate_workers 获取 worker 的 user_id；禁止展示或传递手机号。

    Args:
        job_id: 招募中的小时工岗位 ID 或众包订单 ID
        worker_user_ids: 零工 user_id，多个用英文逗号分隔
        invite_type: 1=小时工（默认），2=众包工
        user_confirmed: 必须为 true
        confirm_token: prepare_write_confirmation 返回的一次性令牌
        confirmation_summary: 用户确认原话摘要
    """
    g = WriteGate(
        "invite_worker_to_job",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        job_id=job_id,
        worker_user_ids=worker_user_ids,
        invite_type=invite_type,
    )
    if g.blocked:
        return g.blocked

    if invite_type not in (1, 2):
        return g.finish(
            json.dumps({"success": False, "error": "invite_type 仅支持 1（小时工）或 2（众包工）"}, ensure_ascii=False),
        )

    user_ids = parse_worker_user_ids(worker_user_ids)
    if not user_ids:
        return g.finish(
            json.dumps({"success": False, "error": "worker_user_ids 不能为空"}, ensure_ascii=False),
        )

    try:
        user_enterprise_id = await _resolve_user_enterprise_id()
        job_or_task = await _fetch_recruiting_job_for_invite(job_id, user_enterprise_id, invite_type)
        if invite_type == 2:
            param = build_invite_param_from_task(job_or_task)
        else:
            param = build_invite_param_from_job(job_or_task)
        if not param.get("id"):
            return g.finish(
                json.dumps({"success": False, "error": "无法解析邀请目标信息"}, ensure_ascii=False),
            )
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    results: list[dict] = []
    for uid in user_ids:
        payload = {
            "inviteType": invite_type,
            "userEnterpriseId": user_enterprise_id,
            "userId": uid,
            "paramList": [param],
        }
        try:
            result = await _req("POST", "miniprogram/jd/inviteUserToWork", json=payload)
        except Exception as e:
            results.append({"user_id": uid, "success": False, "error": str(e)})
            continue
        ok = api_ok(result)
        results.append({
            "user_id": uid,
            "success": ok,
            "message": api_message(result, "success" if ok else "邀请失败"),
        })

    ok_count = sum(1 for r in results if r.get("success"))
    title = param.get("title") or f"岗位/订单 {job_id}"
    summary_lines = [
        f"已向 {ok_count}/{len(user_ids)} 位零工发送邀请",
        f"目标：{title}（ID {job_id}）",
        "",
    ]
    for r in results:
        mark = "✅" if r.get("success") else "❌"
        summary_lines.append(f"{mark} [{r['user_id']}] {r.get('message', '')}")
    return g.finish("\n".join(summary_lines))


# ──── 排班查询 ────

def _format_schedule_list(
    schedules: list,
    *,
    tab_label: str,
    total: int,
    job_id: int = 0,
    product_type: int = 0,
    page: int = 1,
    page_size: int = 20,
) -> str:
    if not schedules:
        filters: list[str] = []
        if job_id > 0:
            filters.append(f"岗位 {job_id}")
        if product_type in (4, 6):
            filters.append({4: "小时工", 6: "计件工"}[product_type])
        scope = f"（{' · '.join(filters)}）" if filters else ""
        return f"暂无{tab_label}{scope}。"
    lines = [
        format_b_schedule_list_header(
            tab_label,
            total,
            job_id=job_id,
            product_type=product_type,
            page=page,
            page_size=page_size,
            shown=len(schedules),
        )
    ]
    for s in schedules:
        lines.append(format_b_schedule_list_item(s))
    if tab_label == "待确认":
        lines.append(
            "\n💡 继续 get_job_schedules(schedule_id=..., detail_tab=pending) 查看班次下待处理订单。"
        )
    return "\n".join(lines)


def _format_schedule_detail_list(
    schedule_id: int,
    items: list,
    total: int,
    *,
    tab_label: str,
    page: int = 1,
    page_size: int = 20,
) -> str:
    if not items:
        return f"班次 {schedule_id} · {tab_label} 暂无订单。"
    lines = [
        format_b_schedule_detail_header(
            schedule_id,
            tab_label,
            total,
            shown=len(items),
            page=page,
            page_size=page_size,
        )
    ]
    for item in items:
        lines.append(format_b_schedule_detail_item(item))
    return "\n".join(lines)


def _schedule_tab_help() -> str:
    list_tabs = "、".join(f"{v['label']}({k})" for k, v in SCHEDULE_LIST_TABS.items())
    detail_tabs = "、".join(f"{v['label']}({k})" for k, v in SCHEDULE_DETAIL_TABS.items())
    return f"列表 list_tab：{list_tabs}；明细 detail_tab：{detail_tabs}"


@mcp.tool()
async def get_job_schedules(
    schedule_id: int = 0,
    job_id: int = 0,
    list_tab: str = "all",
    detail_tab: str = "pending",
    list_type: int = 0,
    list_status: int = -1,
    detail_type: int = 0,
    detail_status: int = -1,
    product_type: int = 0,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """获取企业班次列表或班次下零工订单。

    列表模式（schedule_id=0）→ recruitWorkingSchedule/list
    参数 type + status，与小程序「用工班次」Tab 一致：
    - list_tab=pending_confirm（待确认）→ type=2, status=0
    - list_tab=recruiting（招募中）→ type=1, status=1
    - list_tab=in_progress（进行中）→ type=1, status=3
    - list_tab=completed（已完成）→ type=1, status=4
    - list_tab=closed（已关闭）→ type=1, status=5
    - list_tab=all（全部，默认）→ type=1，不传 status
    也支持中文 tab 名（如 list_tab=待确认）。高级用法可传 list_type + list_status 覆盖。

    明细模式（schedule_id>0）→ recruitWorkingScheduleDetail/list
    同一班次下每个报名零工对应一条订单，参数 type + status：
    - detail_tab=pending（待处理）→ type=2, status=0
    - detail_tab=registered（已报名）→ type=1, status=1
    - detail_tab=waiting_service（待服务）→ type=1, status=2
    - detail_tab=in_service（服务中）→ type=1, status=3
    - detail_tab=wait_confirm（待确认，计件）→ type=1, status=6
    - detail_tab=completed / closed 同理
    高级用法可传 detail_type + detail_status 覆盖。

    Args:
        schedule_id: 班次 ID；0=列表模式，>0=该班次下的订单列表
        job_id: 可选，按岗位筛选列表
        list_tab: 列表 Tab（默认 all）
        detail_tab: 明细 Tab（默认 pending=待处理）
        list_type: 可选，直接指定 list 接口 type
        list_status: 可选，直接指定 list 接口 status（-1 表示不传）
        detail_type: 可选，直接指定 detail 接口 type
        detail_status: 可选，直接指定 detail 接口 status（-1 时待处理 tab 用 0）
        product_type: 4=小时工 6=计件工；0=不限
        page: 页码
        page_size: 每页数量
    """
    if schedule_id > 0:
        try:
            payload, tab_label = build_schedule_detail_payload(
                schedule_id,
                detail_tab=detail_tab,
                detail_type=detail_type,
                detail_status=detail_status,
                product_type=product_type,
                page=page,
                page_size=page_size,
            )
        except ValueError as e:
            return json.dumps(
                {"success": False, "error": f"{e}。{_schedule_tab_help()}"},
                ensure_ascii=False,
            )
        try:
            result = await _req("POST", "recruitWorkingScheduleDetail/list", json=payload)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
        items = api_records(result)
        return _format_schedule_detail_list(
            schedule_id,
            items,
            api_total(result) or len(items),
            tab_label=tab_label,
            page=page,
            page_size=page_size,
        )

    try:
        payload, tab_label = build_schedule_list_payload(
            list_tab=list_tab,
            list_type=list_type,
            list_status=list_status,
            job_id=job_id,
            product_type=product_type,
            page=page,
            page_size=page_size,
        )
    except ValueError as e:
        return json.dumps(
            {"success": False, "error": f"{e}。{_schedule_tab_help()}"},
            ensure_ascii=False,
        )

    try:
        result = await _req("POST", "recruitWorkingSchedule/list", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if not api_ok(result) and not api_records(result):
        return json.dumps(
            {"success": False, "error": api_message(result, "查询排班列表失败")},
            ensure_ascii=False,
        )

    schedules = api_records(result)
    return _format_schedule_list(
        schedules,
        tab_label=tab_label,
        total=api_total(result) or len(schedules),
        job_id=job_id,
        product_type=product_type,
        page=page,
        page_size=page_size,
    )


# ──── 考勤管理 ────


@mcp.tool()
async def get_todo_list(page: int = 1, page_size: int = 20) -> str:
    """获取待处理事项列表（B端待办：考勤审核、延时申请、加价申请等）。

    对应接口: recruitWorkingScheduleDetail/my-todo-list (POST)

    Args:
        page: 页码
        page_size: 每页数量
    """
    payload = {"pageNum": page, "pageSize": page_size}
    try:
        result = await _req("POST", "recruitWorkingScheduleDetail/my-todo-list", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    todos = api_records(result)
    total = api_total(result)
    if not todos:
        return "🎉 暂无待处理事项。"

    lines = [f"待处理事项（共{total}条）：\n"]
    for todo in todos:
        lines.append(format_b_todo_item(todo))
    return "\n".join(lines)


@mcp.tool()
async def manage_attendance(
    action: str,
    detail_id: int,
    minutes: int = 0,
    reason: str = "",
    clock_time: float = 0,
    begin_clock_time: str = "",
    end_clock_time: str = "",
    product_type: int = 0,
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """考勤工时管理（refuse / add_time / delete_time）。

    ⚠️ 写操作须先 prepare_write_confirmation，再 user_confirmed=true + confirm_token。
    须先展示待办或排班明细，由企业用户明确确认后再调用。

    add_time 两种模式（与小程序 ApiSaveAddTime 一致）：
    - clock_time>0：传 begin_clock_time、end_clock_time、clock_time（小时）、product_type
    - 否则：传 minutes（addMinutes 增量分钟）

    Args:
        action: refuse（驳回申请）| add_time（增加/调整工时）| delete_time（删除异常工时）
        detail_id: 排班明细 ID（来自 get_todo_list 或 get_job_schedules(schedule_id>0)）
        minutes: addMinutes 模式下的增量分钟
        clock_time: 调整后的工时（小时），如 1.0
        begin_clock_time: 调整后的上班打卡 HH:mm
        end_clock_time: 调整后的下班打卡 HH:mm
        product_type: 4=小时工 6=计件工（clock_time 模式建议传入）
        reason: 驳回/备注/删除原因
        user_confirmed: 必须为 true
        confirm_token: prepare_write_confirmation 返回的一次性令牌
        confirmation_summary: 可选，用户确认原话摘要
    """
    act = (action or "").strip().lower()
    if act not in ("refuse", "add_time", "delete_time"):
        return json.dumps(
            {"success": False, "error": "action 须为 refuse、add_time 或 delete_time"},
            ensure_ascii=False,
        )
    if detail_id <= 0:
        return json.dumps(
            {"success": False, "error": "须提供有效的 detail_id"},
            ensure_ascii=False,
        )

    g = WriteGate(
        "manage_attendance",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        action=act,
        detail_id=detail_id,
        minutes=minutes,
        reason=reason,
        clock_time=clock_time,
        begin_clock_time=begin_clock_time,
        end_clock_time=end_clock_time,
        product_type=product_type,
    )
    if g.blocked:
        return g.blocked

    if act == "add_time":
        if clock_time > 0:
            payload: dict = {
                "id": detail_id,
                "beginClockTime": begin_clock_time,
                "endClockTime": end_clock_time,
                "clockTime": clock_time,
            }
            if product_type in (4, 6):
                payload["productType"] = product_type
            if reason:
                payload["remark"] = reason
            missing = [
                name
                for name, val in (
                    ("begin_clock_time", begin_clock_time),
                    ("end_clock_time", end_clock_time),
                )
                if not (val or "").strip()
            ]
            if missing:
                return g.finish(
                    json.dumps(
                        {
                            "success": False,
                            "error": f"clock_time 模式须提供 {', '.join(missing)}",
                        },
                        ensure_ascii=False,
                    )
                )
        else:
            if minutes <= 0:
                return g.finish(
                    json.dumps(
                        {
                            "success": False,
                            "error": "add_time 须提供 minutes>0 或 clock_time>0（及起止打卡时间）",
                        },
                        ensure_ascii=False,
                    )
                )
            payload = {"id": detail_id, "addMinutes": minutes, "remark": reason}
        try:
            result = await _req("POST", "recruitWorkingScheduleDetail/addTime", json=payload)
        except Exception as e:
            return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        if api_ok(result):
            if clock_time > 0:
                return g.finish(
                    f"✅ 已调整明细 {detail_id} 考勤：{begin_clock_time}-{end_clock_time}，"
                    f"工时 {clock_time}h（待零工确认）"
                )
            return g.finish(f"✅ 已为明细 {detail_id} 增加 {minutes} 分钟工时")
        return g.finish(
            json.dumps({"success": False, "error": api_message(result, "调整考勤失败")}, ensure_ascii=False),
        )

    if act == "delete_time":
        payload = {"id": detail_id, "remark": reason}
        try:
            result = await _req("POST", "recruitWorkingScheduleDetail/deleteTime", json=payload)
        except Exception as e:
            return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        if api_ok(result):
            return g.finish(f"✅ 已删除明细 {detail_id} 的异常工时")
        return g.finish(
            json.dumps({"success": False, "error": api_message(result, "删除工时失败")}, ensure_ascii=False),
        )

    payload = {"id": detail_id, "refuseReason": reason}
    try:
        result = await _req("POST", "recruitWorkingScheduleDetail/refuse", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
    if api_ok(result):
        return g.finish(f"✅ 已驳回考勤申请（明细ID: {detail_id}）")
    return g.finish(
        json.dumps({"success": False, "error": api_message(result, "驳回失败")}, ensure_ascii=False),
    )


@mcp.tool()
async def close_job(
    job_id: int,
    reason: str = "",
    user_confirmed: bool = False,
    confirmation_summary: str = "",
    confirm_token: str = "",
) -> str:
    """停止招工/下线岗位。

    对应接口: miniprogram/jd/offline (POST)

    ⚠️ 调用约束：须先 prepare_write_confirmation 获取 confirm_token；
    向企业用户确认要下线的岗位 ID 与原因后，以 user_confirmed=true + confirm_token 调用。

    Args:
        job_id: 岗位ID
        reason: 停止原因
        user_confirmed: 必须为 true
        confirm_token: prepare_write_confirmation 返回的一次性令牌
        confirmation_summary: 可选，用户确认原话摘要
    """
    g = WriteGate(
        "close_job",
        user_confirmed,
        confirm_token=confirm_token,
        confirmation_summary=confirmation_summary,
        job_id=job_id,
        reason=reason,
    )
    if g.blocked:
        return g.blocked

    payload = {"id": job_id}
    if reason:
        payload["cancelReason"] = reason
    try:
        result = await _req("POST", "miniprogram/jd/offline", json=payload)
    except Exception as e:
        return g.finish(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

    if api_ok(result):
        return g.finish(f"岗位 {job_id} 已停止招工。")
    return g.finish(
        json.dumps({"success": False, "error": api_message(result, "下线失败")}, ensure_ascii=False),
    )


@mcp.tool()
async def get_workforce_summary() -> str:
    """汇总当前用工状态（在招岗位、待办数量、今日排班到岗情况）。

    组合调用 get_job_list、get_todo_list 及排班接口，供「现在用工情况如何」类问题使用。
    """
    summary = {
        "active_jobs": 0,
        "total_applications": 0,
        "pending_todos": 0,
        "today_shifts": 0,
        "today_arrived": 0,
        "jobs": [],
    }

    try:
        job_result = await _req(
            "POST",
            "miniprogram/jd/list",
            json={"status": "active", "pageNum": 1, "pageSize": 50},
        )
        jobs = api_records(job_result)
        summary["active_jobs"] = len(jobs)
        for jd in jobs:
            apply_count = jd.get("applyCount", 0)
            summary["total_applications"] += apply_count
            summary["jobs"].append(
                {
                    "jd_id": jd.get("jdId") or jd.get("id"),
                    "title": jd.get("title") or jd.get("positionName"),
                    "apply_count": apply_count,
                    "headcount": jd.get("headcount", 0),
                }
            )
    except Exception as e:
        summary["jobs_error"] = str(e)

    try:
        todo_result = await _req(
            "POST",
            "recruitWorkingScheduleDetail/my-todo-list",
            json={"pageNum": 1, "pageSize": 1},
        )
        summary["pending_todos"] = api_total(todo_result)
    except Exception as e:
        summary["todos_error"] = str(e)

    # 统计今日排班到岗（取第一个在招岗位的排班作为示例汇总）
    if summary["jobs"]:
        first_job_id = summary["jobs"][0].get("jd_id")
        if first_job_id:
            try:
                schedule_result = await _req(
                    "POST",
                    "recruitWorkingSchedule/list",
                    json=build_schedule_list_payload(
                        list_tab="all",
                        job_id=first_job_id,
                        product_type=4,
                        page=1,
                        page_size=100,
                    )[0],
                )
                today_str = date.today().isoformat()
                for s in api_records(schedule_result):
                    if str(s.get("jobDate") or s.get("workDate", "")).startswith(today_str):
                        summary["today_shifts"] += 1
                        summary["today_arrived"] += s.get("numberOfRegistrations") or s.get(
                            "arriveCount", 0
                        )
            except Exception:
                pass

    lines = [
        "📊 用工状态汇总\n",
        f"在招岗位：{summary['active_jobs']} 个",
        f"总报名人数：{summary['total_applications']} 人",
        f"待处理事项：{summary['pending_todos']} 条",
        f"今日班次到岗：{summary['today_arrived']} 人（统计范围：首个在招岗位今日排班）",
        "",
        "在招岗位明细：",
    ]
    if summary["jobs"]:
        for j in summary["jobs"][:10]:
            lines.append(
                f"  • [{j['jd_id']}] {j['title']} — 报名 {j['apply_count']}/{j['headcount']} 人"
            )
    else:
        lines.append("  （暂无在招岗位）")

    return "\n".join(lines)


# ──── 岗位元数据（job-planner 用） ────

CATALOG_SECTIONS = frozenset({"work_categories", "skills", "benefits"})


def _parse_catalog_sections(sections: str) -> set[str] | None:
    raw = (sections or "all").strip().lower()
    if raw in ("all", "*", ""):
        return set(CATALOG_SECTIONS)
    selected = {s.strip().lower() for s in raw.replace("，", ",").split(",") if s.strip()}
    unknown = selected - CATALOG_SECTIONS
    if unknown:
        return None
    return selected


async def _fetch_work_categories_section() -> dict:
    result = await _req("POST", "miniprogram/jd/workCategoryList", json={})
    cats = result.get("data") or result.get("Data") or []
    if not isinstance(cats, list) or not cats:
        return {"text": "暂无工作分类数据。", "items": []}
    lines = flatten_tree_nodes(
        cats,
        id_key="workCategoryId",
        name_key="workCategoryName",
    )
    return {"text": "工作类别：\n" + "\n".join(lines), "items": cats}


async def _fetch_benefits_section() -> dict:
    result = await _req("POST", "miniprogram/jd/benefitList", json={})
    tags = result.get("data") or result.get("Data") or []
    if not isinstance(tags, list) or not tags:
        return {"text": "暂无福利标签数据。", "items": []}
    lines = flatten_tree_nodes(
        tags,
        id_key="id",
        name_key="benefitTagName",
        alt_name_keys=("name", "benefitName"),
    )
    return {"text": "可选福利标签：\n" + "\n".join(lines), "items": tags}


async def _fetch_skills_section(work_category_id: int, keyword: str) -> dict:
    payload = {"workCategoryId": work_category_id}
    if keyword:
        payload["keyword"] = keyword
    result = await _req("POST", "miniprogram/jd/skillList", json=payload)
    if not api_ok(result):
        return {"text": api_message(result, "获取技能标签失败"), "items": []}
    skills = result.get("data") or result.get("Data") or []
    if not isinstance(skills, list) or not skills:
        empty = "未找到相关技能标签。" if keyword else "暂无技能标签数据。"
        return {"text": empty, "items": []}
    lines = flatten_tree_nodes(
        skills,
        id_key="workCategoryId",
        name_key="workCategoryName",
        alt_name_keys=("skillName", "name"),
    )
    return {
        "text": f"可选技能标签（分类 {work_category_id}）：\n" + "\n".join(lines),
        "items": skills,
    }


@mcp.tool()
async def get_job_publish_catalog(
    sections: str = "all",
    work_category_id: int = 2,
    keyword: str = "",
    format: str = "text",
) -> str:
    """获取发岗可选目录（工作分类 / 技能 / 福利标签）。

    Args:
        sections: all 或逗号分隔：work_categories, skills, benefits
        work_category_id: skills 区段用的分类 ID（默认 2=家政保洁）
        keyword: skills 区段关键词筛选
        format: text（默认，人类可读）或 json（结构化）
    """
    selected = _parse_catalog_sections(sections)
    if selected is None:
        return json.dumps(
            {
                "success": False,
                "error": f"sections 未知项，可选：{', '.join(sorted(CATALOG_SECTIONS))} 或 all",
            },
            ensure_ascii=False,
        )

    out: dict = {"success": True}
    text_parts: list[str] = []

    try:
        if "work_categories" in selected:
            wc = await _fetch_work_categories_section()
            out["work_categories"] = wc["items"]
            text_parts.append(wc["text"])
        if "benefits" in selected:
            bf = await _fetch_benefits_section()
            out["benefits"] = bf["items"]
            text_parts.append(bf["text"])
        if "skills" in selected:
            sk = await _fetch_skills_section(work_category_id, keyword)
            out["skills"] = sk["items"]
            text_parts.append(sk["text"])
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if (format or "text").strip().lower() == "json":
        return json.dumps(out, ensure_ascii=False, indent=2)
    return "\n\n".join(text_parts) if text_parts else "暂无目录数据。"


if __name__ == "__main__":
    mcp.run(transport="stdio")

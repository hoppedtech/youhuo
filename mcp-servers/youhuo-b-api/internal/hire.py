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
) -> str:
    """预估发布岗位所需费用。

    **长期招（productType=2/5）**：按积分订阅制计算，公式：人数 × 天数 × 0.5 积分/人/天。
    10积分=1元人民币。发布后需调用 pay_publish_points 支付积分。

    **小时工/计件工（productType=4/6）**：发布时扣除平台服务费（人民币），
    费用由后端根据岗位信息计算，发布后从账户余额直接扣除。

    对应前端逻辑：long-term/index.vue（长期招积分计算）/ hourly-worker/publish.vue（小时工余额支付）

    Args:
        product_type: 岗位类型。2/5=长期招（需积分），4=小时工，6=计件工
        subscript_worker_count: 订阅人数（长期招需要，即希望触达的零工人数）
        subscript_day_count: 订阅天数（长期招需要，最少7天）

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

    type_name = "小时工" if product_type == 4 else "计件工"
    return json.dumps(
        {
            "product_type": product_type,
            "type_name": type_name,
            "note": f"{type_name}发布时由后端计算平台服务费，从账户余额直接扣除",
        },
        ensure_ascii=False,
    )


# ──── 岗位发布 ────

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
) -> str:
    """发布岗位到有活平台（B端企业招工）。支持长期招、小时工、计件工。

    对应接口: miniprogram/jd/publish (POST)

    **发布后的支付差异**：
    - 长期招（productType=2/5）：发布后需调用 pay_publish_points 支付积分订阅费
    - 小时工/计件工（productType=4/6）：发布后直接生效，平台服务费从账户余额自动扣除

    Args:
        title: 岗位名称，如"餐厅小时工""仓库分拣员"
        work_category: 工作类别
        description: 岗位描述和要求
        location: 工作地点
        salary_min: 薪资下限（元/天 或 元/小时）
        salary_max: 薪资上限（元/天 或 元/小时）
        headcount: 招募人数
        product_type: 岗位类型。2/5=长期招，4=小时工，6=计件工。默认4（小时工）
        skills: 所需技能标签列表
        benefits: 福利标签列表
        subscript_worker_count: 订阅人数（长期招需要，默认0）
        subscript_day_count: 订阅天数（长期招需要，最少7天，默认0）
    """
    payload = {
        "title": title,
        "workCategory": work_category,
        "description": description,
        "workAddress": location,
        "salaryMin": salary_min,
        "salaryMax": salary_max,
        "headcount": headcount,
        "productType": product_type,
        "skillList": skills or [],
        "benefitList": benefits or [],
    }
    if product_type in (2, 5):
        payload["subscriptWorkerCount"] = subscript_worker_count
        payload["subscriptDayCount"] = subscript_day_count

    try:
        result = await _req("POST", "miniprogram/jd/publish", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        data = result.get("data", {})
        jd_id = data.get("id") or data.get("jdId")
        if product_type in (2, 5):
            return json.dumps(
                {
                    "success": True,
                    "jd_id": jd_id,
                    "product_type": product_type,
                    "message": "岗位已创建",
                    "note": "长期招需继续调用 pay_publish_points 完成积分支付",
                },
                ensure_ascii=False,
            )
        # 小时工/计件工：发布成功即生效，余额已自动扣除
        return json.dumps(
            {
                "success": True,
                "jd_id": jd_id,
                "product_type": product_type,
                "message": "岗位发布成功！",
                "note": "平台服务费已从账户余额扣除",
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {"success": False, "error": result.get("message", "发布失败")},
        ensure_ascii=False,
    )


@mcp.tool()
async def pay_publish_points(jd_id: int) -> str:
    """支付长期招岗位发布所需的积分（仅限 productType=2/5）。

    对应接口: miniprogram/jd/payPointsToPublish (POST)

    在 publish_jd 成功后调用，完成积分扣费，岗位正式上架。
    如果积分余额不足会返回错误，需要引导用户去小程序充值。

    Args:
        jd_id: publish_jd 返回的岗位ID

    Returns:
        支付结果。积分余额不足时返回明确的引导信息。
    """
    payload = {"id": jd_id}
    try:
        result = await _req("POST", "miniprogram/jd/payPointsToPublish", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        return json.dumps(
            {"success": True, "message": f"积分支付成功！岗位 {jd_id} 已正式上架。"},
            ensure_ascii=False,
        )

    msg = result.get("message", "支付失败")
    if "余额" in msg or "不足" in msg or "积分" in msg:
        return json.dumps(
            {
                "success": False,
                "reason": "BALANCE_INSUFFICIENT",
                "message": f"积分余额不足，无法完成支付。\n错误信息：{msg}",
                "guide": "请前往有活小程序充值积分：打开微信 → 搜索'有活'小程序 → 我的 → 充值积分。充值完成后，告诉我'继续支付'即可。",
            },
            ensure_ascii=False,
        )
    return json.dumps({"success": False, "error": msg}, ensure_ascii=False)


# ──── 岗位列表 ────

@mcp.tool()
async def get_job_list(
    status: str = "all",
    page: int = 1,
    page_size: int = 10,
) -> str:
    """查询企业已发布的招工岗位列表。

    对应接口: miniprogram/jd/list (POST)

    Args:
        status: 岗位状态 all/active/closed
        page: 页码
        page_size: 每页数量
    """
    payload = {"status": status, "pageNum": page, "pageSize": page_size, "productType": 1}
    try:
        result = await _req("POST", "miniprogram/jd/list", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    items = result.get("data", {}).get("list", [])
    if not items:
        return "暂无发布的岗位。"

    lines = ["已发布岗位列表：\n"]
    for jd in items:
        lines.append(
            f"{'🟢' if jd.get('status') == 'active' else '🔴'} "
            f"[{jd.get('jdId')}] {jd.get('title')} | "
            f"报名 {jd.get('applyCount', 0)}/{jd.get('headcount', 0)} 人"
        )
    return "\n".join(lines)


# ──── 查看报名 / 候选人管理 ────

def _format_job_workers(job_id: int, result: dict) -> str:
    workers = result.get("data", {}).get("list", [])
    total = result.get("data", {}).get("total", 0)
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
async def get_job_applications(
    job_id: int,
    page: int = 1,
    page_size: int = 10,
) -> str:
    """获取岗位下已报名/匹配的零工人员列表（get_job_workers 别名，兼容旧调用）。

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
async def mark_worker_suitable(jd_id: int, user_id: int, mark: int) -> str:
    """标记候选零工是否合适。

    对应接口: miniprogram/jd/markCv (POST)

    Args:
        jd_id: 岗位ID
        user_id: 零工用户ID
        mark: 1=合适 2=不合适
    """
    if mark not in (1, 2):
        return json.dumps({"success": False, "error": "mark 必须为 1（合适）或 2（不合适）"}, ensure_ascii=False)

    payload = {"jdId": jd_id, "userId": user_id, "mark": mark}
    try:
        result = await _req("POST", "miniprogram/jd/markCv", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") != 200:
        return json.dumps({"success": False, "error": result.get("message", "标记失败")}, ensure_ascii=False)

    mark_desc = "✅ 合适" if mark == 1 else "❌ 不合适"
    return f"已标记用户 {user_id} 为{mark_desc}"


# ──── 排班查询 ────

@mcp.tool()
async def get_schedule_list(job_id: int) -> str:
    """获取岗位排班列表。

    对应接口: recruitWorkingSchedule/list (POST)

    Args:
        job_id: 岗位ID
    """
    payload = {"jobId": job_id, "productType": 4}
    try:
        result = await _req("POST", "recruitWorkingSchedule/list", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    schedules = result.get("data", {}).get("list", [])
    if not schedules:
        return f"岗位 {job_id} 暂无排班信息。"

    lines = [f"岗位 {job_id} 排班情况：\n"]
    for s in schedules:
        lines.append(
            f"📅 {s.get('workDate')} | "
            f"{s.get('startTime')}-{s.get('endTime')} | "
            f"需{s.get('headcount')}人 | "
            f"已到{s.get('arriveCount', 0)}人"
        )
    return "\n".join(lines)


# ──── 排班明细 / 考勤管理 ────

@mcp.tool()
async def get_schedule_detail_list(
    schedule_id: int,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """获取排班明细列表（含各零工考勤状态）。

    对应接口: recruitWorkingScheduleDetail/list (POST)

    Args:
        schedule_id: 排班ID（来自 get_schedule_list）
        page: 页码
        page_size: 每页数量
    """
    payload = {"scheduleId": schedule_id, "pageNum": page, "pageSize": page_size}
    try:
        result = await _req("POST", "recruitWorkingScheduleDetail/list", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    items = result.get("data", {}).get("list", [])
    total = result.get("data", {}).get("total", 0)
    if not items:
        return f"排班 {schedule_id} 暂无明细记录。"

    lines = [f"排班 {schedule_id} 明细（共{total}条）：\n"]
    for item in items:
        lines.append(
            f"👤 {item.get('workerName', '未知')} | "
            f"状态: {item.get('statusDesc', item.get('status', '—'))} | "
            f"工时: {item.get('workHours', '—')}h | "
            f"金额: ¥{item.get('amount', 0)}"
        )
    return "\n".join(lines)


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

    todos = result.get("data", {}).get("list", [])
    total = result.get("data", {}).get("total", 0)
    if not todos:
        return "🎉 暂无待处理事项。"

    lines = [f"待处理事项（共{total}条）：\n"]
    for todo in todos:
        todo_type = todo.get("todoTypeDesc") or todo.get("typeDesc") or todo.get("title", "待办")
        detail_id = todo.get("id") or todo.get("detailId") or "—"
        lines.append(
            f"⚠️ [{detail_id}] {todo_type} | "
            f"{todo.get('workerName', '—')} | "
            f"{todo.get('createTime', '')}"
        )
    return "\n".join(lines)


@mcp.tool()
async def refuse_attendance(detail_id: int, reason: str = "") -> str:
    """驳回零工考勤/工时申请。

    对应接口: recruitWorkingScheduleDetail/refuse (POST)

    Args:
        detail_id: 排班明细ID（来自 get_todo_list 或 get_schedule_detail_list）
        reason: 驳回原因
    """
    payload = {"id": detail_id, "refuseReason": reason}
    try:
        result = await _req("POST", "recruitWorkingScheduleDetail/refuse", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        return f"✅ 已驳回考勤申请（明细ID: {detail_id}）"
    return json.dumps({"success": False, "error": result.get("message", "驳回失败")}, ensure_ascii=False)


@mcp.tool()
async def add_work_time(detail_id: int, minutes: int, reason: str = "") -> str:
    """为零工增加工时（加班/延时申请审核通过后调用）。

    对应接口: recruitWorkingScheduleDetail/addTime (POST)

    Args:
        detail_id: 排班明细ID
        minutes: 增加工时（分钟）
        reason: 备注说明
    """
    payload = {"id": detail_id, "addMinutes": minutes, "remark": reason}
    try:
        result = await _req("POST", "recruitWorkingScheduleDetail/addTime", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        return f"✅ 已为明细 {detail_id} 增加 {minutes} 分钟工时"
    return json.dumps({"success": False, "error": result.get("message", "增加工时失败")}, ensure_ascii=False)


@mcp.tool()
async def delete_work_time(detail_id: int, reason: str = "") -> str:
    """删除/扣减零工异常工时。

    对应接口: recruitWorkingScheduleDetail/deleteTime (POST)

    Args:
        detail_id: 排班明细ID
        reason: 删除原因
    """
    payload = {"id": detail_id, "remark": reason}
    try:
        result = await _req("POST", "recruitWorkingScheduleDetail/deleteTime", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        return f"✅ 已删除明细 {detail_id} 的异常工时"
    return json.dumps({"success": False, "error": result.get("message", "删除工时失败")}, ensure_ascii=False)


@mcp.tool()
async def close_job(job_id: int, reason: str = "") -> str:
    """停止招工/下线岗位。

    对应接口: miniprogram/jd/offline (POST)

    Args:
        job_id: 岗位ID
        reason: 停止原因
    """
    payload = {"jdId": job_id, "cancelReason": reason}
    try:
        result = await _req("POST", "miniprogram/jd/offline", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    if result.get("code") == 200:
        return f"岗位 {job_id} 已停止招工。"
    return json.dumps({"success": False, "error": result.get("message", "下线失败")}, ensure_ascii=False)


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
            json={"status": "active", "pageNum": 1, "pageSize": 50, "productType": 1},
        )
        jobs = job_result.get("data", {}).get("list", [])
        summary["active_jobs"] = len(jobs)
        for jd in jobs:
            apply_count = jd.get("applyCount", 0)
            summary["total_applications"] += apply_count
            summary["jobs"].append(
                {
                    "jd_id": jd.get("jdId"),
                    "title": jd.get("title"),
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
        summary["pending_todos"] = todo_result.get("data", {}).get("total", 0)
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
                    json={"jobId": first_job_id, "productType": 4},
                )
                today_str = date.today().isoformat()
                for s in schedule_result.get("data", {}).get("list", []):
                    if str(s.get("workDate", "")).startswith(today_str):
                        summary["today_shifts"] += 1
                        summary["today_arrived"] += s.get("arriveCount", 0)
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


# ──── 余额查询 ────

@mcp.tool()
async def get_enterprise_balance() -> str:
    """查询企业账户余额（积分+现金+体验金）。

    对应接口: miniprogram/account/balance (GET)
    """
    try:
        result = await _req("GET", "miniprogram/account/balance")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    data = result.get("data", {})
    return json.dumps(
        {
            "points_balance": data.get("pointsBalance", 0),
            "cash_balance": data.get("cashBalance", 0),
            "exp_balance": data.get("expBalance", 0),
            "total_balance": data.get("totalBalance", 0),
        },
        ensure_ascii=False,
    )


# ──── 岗位元数据（job-planner 用） ────

@mcp.tool()
async def get_work_categories() -> str:
    """获取岗位工作分类目录。

    对应接口: miniprogram/jd/workCategoryList (POST)
    """
    try:
        result = await _req("POST", "miniprogram/jd/workCategoryList", json={})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    cats = result.get("data", [])
    if not cats:
        return "暂无工作分类数据。"
    return "工作类别：\n" + "\n".join(
        f"  • {c.get('name', c.get('categoryName', '—'))}" for c in cats[:50]
    )


@mcp.tool()
async def get_benefit_list() -> str:
    """获取可选福利标签（五险一金/包吃/包住等）。

    对应接口: miniprogram/jd/benefitList (POST)
    """
    try:
        result = await _req("POST", "miniprogram/jd/benefitList", json={})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    tags = result.get("data", [])
    if not tags:
        return "暂无福利标签数据。"
    return "可选福利标签：\n" + "\n".join(
        f"  • {t.get('name', t.get('benefitName', '—'))}" for t in tags[:50]
    )


@mcp.tool()
async def get_skill_list(keyword: str = "") -> str:
    """获取可选技能标签列表（发布岗位时选用）。

    对应接口: miniprogram/jd/skillList (POST)
    """
    payload = {"keyword": keyword} if keyword else {}
    try:
        result = await _req("POST", "miniprogram/jd/skillList", json=payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    skills = result.get("data", [])
    if not skills:
        return "未找到相关技能标签。" if keyword else "暂无技能标签数据。"
    return "可选技能标签：\n" + "\n".join(
        f"  • {s.get('name', s.get('skillName', '—'))}" for s in skills[:50]
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

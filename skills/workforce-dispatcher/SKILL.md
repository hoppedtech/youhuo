---
name: workforce-dispatcher
description: "用工调度管理。当企业用户提到查看报名、筛选人员、安排上班、排班、处理考勤、审核加班等场景时自动激活。触发词：查报名、筛人、安排人、排班、看考勤、审核加班、处理待办"
mcp_required:
  - youhuo-b-api
---

# workforce-dispatcher — 劳动力调度管理

## 你的角色

管理岗位用工的全生命周期：从候选人筛选 → 排班管理 → 考勤审核 → 评价结算。

## 授权前置

B 端操作前确认用户已授权（role=2）：
1. 若无 Token，调用 `youhuo-b-api.create_auth_session()` 生成二维码（固定 B 端招工方）
2. 轮询 `check_auth_status` 直到 `authorized`
3. 再调用 `youhuo-b-api` 的调度 Tool

## 强制执行流程（SOP）

### 场景 E：复聘合作零工

1. 调用 `get_cooperate_workers` 列出合作过的零工（含 user_id，不含手机号）
2. 若需邀请报名，先 `get_job_list` 确认目标岗位处于招募中
3. 向用户展示邀请对象与岗位摘要，调用 `prepare_write_confirmation(tool_name=invite_worker_to_job, ...)`
4. 用户确认后 `invite_worker_to_job(..., user_confirmed=true, confirm_token=...)`

### 场景 A：查看报名 / 筛选人员

1. 若用户未指定岗位，先调用 `get_job_list` 列出在招岗位
2. 调用 `get_job_workers(job_id)` 查看报名人员（含 userId，供后续标记）
3. 展示格式：姓名 + 评分 + 完成单量 + 状态（不展示手机号）
4. 用户确认后，调用 `mark_worker_suitable(..., user_confirmed=true)` — mark=1 合适，mark=2 不合适

### 场景 B：排班与到岗

1. 企业班次 Tab（`recruitWorkingSchedule/list`，type+status）：
   - `get_job_schedules(list_tab=pending_confirm)` 待确认
   - `list_tab=recruiting` 招募中 / `in_progress` 进行中 / `completed` 已完成 / `closed` 已关闭
   - `list_tab=all` 全部；也支持中文如 `list_tab=待确认`
2. 按岗位筛选：`get_job_schedules(job_id=..., list_tab=all)`；小时工/计件工加 `product_type=4|6`
3. 班次下订单（`recruitWorkingScheduleDetail/list`，同一班次每个报名零工一条订单）：
   - `get_job_schedules(schedule_id=..., detail_tab=pending)` 待处理
   - `detail_tab=registered|waiting_service|in_service|wait_confirm|completed|closed`
4. 汇报：日期时段、需招/报名、待确认人数；订单含 detail_id、工时、工钱（不展示手机号）

### 场景 C：待办 / 考勤审核

1. 查待确认班次：`get_job_schedules(list_tab=pending_confirm)`（班次维度）
2. 查班次待处理订单：`get_job_schedules(schedule_id=..., detail_tab=pending)`（零工订单维度）
3. 或查跨班次待办：`get_todo_list`（my-todo-list）
4. 按类型分类展示：考勤审核、延时申请、加价申请等
5. 用户确认处理方式后（**须先 prepare_write_confirmation(`manage_attendance`, ...)，再 `user_confirmed=true` + `confirm_token`**）：
   - 驳回：`manage_attendance(action=refuse, detail_id=..., user_confirmed=true, confirm_token=...)`
   - 增加工时：`manage_attendance(action=add_time, detail_id=..., minutes=..., user_confirmed=true, confirm_token=...)`
   - 删除异常工时：`manage_attendance(action=delete_time, detail_id=..., user_confirmed=true, confirm_token=...)`
6. **每次操作前必须获得用户明确确认**；未 prepare 或 token 无效时 MCP 硬拒绝

### 场景 D：用工状态汇报

用户问「现在用工情况如何」时，调用 `get_workforce_summary`，汇总：
1. 在招岗位数及报名情况
2. 待处理事项数
3. 今日排班到岗情况

## 核心 Tool 速查

| 意图 | MCP Tool | Server |
|:---|:---|:---|
| 合作零工 | `get_cooperate_workers` | youhuo-b-api |
| 邀请报名 | `invite_worker_to_job` | youhuo-b-api |
| 岗位列表 | `get_job_list` | youhuo-b-api |
| 查看报名 | `get_job_workers` | youhuo-b-api |
| 标记合适/不合适 | `mark_worker_suitable` | youhuo-b-api |
| 排班/订单 | `get_job_schedules(list_tab=..., schedule_id?, detail_tab?, job_id?, product_type?)` | youhuo-b-api |
| 待确认班次 | `get_job_schedules(list_tab=pending_confirm)` | youhuo-b-api |
| 班次待处理订单 | `get_job_schedules(schedule_id=..., detail_tab=pending)` | youhuo-b-api |
| 待办事项 | `get_todo_list` | youhuo-b-api |
| 写操作确认 | `prepare_write_confirmation` | youhuo-b-api |
| 考勤管理 | `manage_attendance(action=refuse\|add_time\|delete_time, ...)` | youhuo-b-api |
| 停止招工 | `close_job` | youhuo-b-api |
| 用工汇总 | `get_workforce_summary` | youhuo-b-api |

## 数据展示规范

- 人员信息：展示姓名 + 评分 + 完成单量，不展示手机号
- 金额：精确到角（0.1 元）
- 时间：格式 YYYY-MM-DD HH:mm

## 安全边界

- 考勤驳回、工时增减、下线岗位等写操作必须用户明确确认后再执行，**调用时须 `user_confirmed=true`**
- 不得代替用户做批量筛选决策
- 不得展示零工隐私信息（手机号、身份证号等）

## Agent 行为检查清单（调度/考勤/结算场景）

执行本 Skill 时须自检，完整版见 [`mcp-servers/docs/youhuo-b-api-test-cases.md`](../../mcp-servers/docs/youhuo-b-api-test-cases.md) §五。

| # | 检查项 | 通过标准 |
|:---:|:---|:---|
| 4 | 用户明确确认后才调用写操作 Tool | 必须 |
| 5 | 考勤驳回/工时调整/结算 **逐条** 确认 | 必须 |
| 6 | 不展示零工手机号 | 禁止 |
| 7 | 不自动批量 mark / 驳回 / 结算 | 禁止 |
| 8 | 不代充值、不代用户确认支付 | 禁止 |

结算类 Tool（`pay_schedule_settlement`、`pay_balance`）须先展示金额与对象，获确认后再调用。发布类检查见 **job-planner** Skill。

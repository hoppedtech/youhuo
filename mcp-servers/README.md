# 有活 MCP Servers

有活平台 MCP Server 实现，按 **B/C 双角色** 封装为两个统一入口。

## 架构

```
┌─────────────────────────────────────────────────┐
│  Skill 层                                        │
│  job-planner / workforce-dispatcher  →  B 端    │
│  job-seeker                          →  C 端    │
└───────────────┬─────────────────┬───────────────┘
                │                 │
         youhuo-b-api       youhuo-c-api
    （招工方 role=2）      （找活方 role=1）
                │                 │
    auth + hire + task      auth + worker
         + finance B           + profile
                              + finance C
```

原 6 个子模块（auth / hire / task / worker / profile / finance）保留为内部实现，`youhuo-b-api` / `youhuo-c-api` 通过 `tools/compose.py` 合并 Tool。

## 文件结构

```
mcp-servers/
├── shared_token_store.py       # SQLite 共享 Token
├── tools/
│   └── compose.py              # Tool 合并工具
├── youhuo-b-api/server.py      # ★ B 端统一入口（推荐）
├── youhuo-c-api/server.py      # ★ C 端统一入口（推荐）
├── mcp.json                    # 仅含 b-api + c-api
├── youhuo-auth-service/        # 内部模块（可被 compose 加载）
├── youhuo-hire-api/
├── youhuo-task-api/
├── youhuo-worker-api/
├── youhuo-profile-api/
└── youhuo-finance-api/
```

## 快速开始

```bash
cd mcp-servers
pip install mcp httpx

# 启动 B 端
python youhuo-b-api/server.py

# 启动 C 端
python youhuo-c-api/server.py
```

## MCP 配置（Cursor / WorkBuddy）

使用 `.cursor/mcp.json` 或 `mcp-servers/mcp.json`，**只需配置 2 个 Server**：

| Server | 角色 | 对应 Skill |
|:---|:---|:---|
| `youhuo-b-api` | 招工方 (B) | job-planner, workforce-dispatcher |
| `youhuo-c-api` | 找活方 (C) | job-seeker |

## youhuo-b-api Tool 清单

**授权**：`create_auth_session`（固定 role=2）、`check_auth_status`、`get_current_user_info`、`revoke_auth`

**岗位发布**（job-planner）：`preview_publish_cost`、`publish_jd`、`pay_publish_points`、`get_work_categories`、`get_skill_list`、`get_benefit_list`、`get_enterprise_balance`

**众包**（job-planner）：`get_task_categories`、`publish_task`、`get_task_orders`、`accept_delivery`

**调度**（workforce-dispatcher）：`get_job_list`、`get_job_workers`、`mark_worker_suitable`、`get_schedule_list`、`get_schedule_detail_list`、`get_todo_list`、`refuse_attendance`、`add_work_time`、`delete_work_time`、`close_job`、`get_workforce_summary`

**结算/发票**：`get_account_log`、`pay_schedule_settlement`、`pay_balance`、`apply_invoice`、`get_invoice_list`

## youhuo-c-api Tool 清单

**授权**：`create_auth_session`（固定 role=1）、`check_auth_status`、`get_current_user_info`、`revoke_auth`

**找活**（job-seeker）：`search_jobs`、`search_piece_tasks`、`get_recommend_jobs`、`get_job_detail`、`get_entry_job_requirements`、`submit_job_registration`、`apply_job`、`cancel_apply`、`get_my_work_orders`、`get_my_tasks`、`get_task_detail`、`get_work_calendar`

**画像/认证**：`get_user_profile`、`get_auth_status`、`get_skill_tags`、`check_apply_eligibility`、`get_worker_profile`、`get_work_preferences`、`update_work_preferences`

**余额/提现**：`get_worker_balance`、`withdraw_balance`

## Skill 清单

| Skill | MCP Server | 路径 |
|:---|:---|:---|
| job-planner | youhuo-b-api | `.cursor/skills/job-planner/SKILL.md` |
| workforce-dispatcher | youhuo-b-api | `.cursor/skills/workforce-dispatcher/SKILL.md` |
| job-seeker | youhuo-c-api | `.cursor/skills/job-seeker/SKILL.md` |

## 验证脚本

```bash
python test_b_flow.py
python test_c_flow.py
python test_job_planner_flow.py
python test_workforce_dispatcher_flow.py
python test_job_seeker_flow.py
python test_finance_flow.py
```

## 环境变量

| 变量 | 说明 |
|:---|:---|
| `YOUHUO_BASE_URL` | API 网关域名（代码自动拼接 applet / miniprogram-web / platform-service 路径） |
| `YOUHUO_EMPLOY_URL` | B 端招工网关（已废弃，请仅用 `YOUHUO_BASE_URL`） |
| `YOUHUO_TASK_URL` | 众包网关（已废弃，请仅用 `YOUHUO_BASE_URL`） |
| `YOUHUO_GET_TOKEN_URL` | 扫码授权轮询接口 |

默认使用测试环境 `hopped-gateway-service-sops-test.hopped.com.cn`。

## 市场上架

CloudBase / 腾讯云 MCP 广场打包见 [`marketplace/README.md`](marketplace/README.md)。

## 后端依赖

扫码授权需后端实现 `Login/GetTokenBySession` 及 `minilogin` Redis 缓存（详见方案文档）。

## 开源发布安全提示

- **勿提交** `~/.workbuddy/youhuo_auth.db` 或任何真实 Token（已写入根目录 `.gitignore`）
- `inject_token.py` 仅供本地联调，不要在公开场合粘贴真实 Token
- 写操作（`apply_job`、`cancel_apply`、`withdraw_balance`）依赖 AI/Skill 层获得用户明确确认后再调用
- 生产部署仅配置 `YOUHUO_BASE_URL` 网关域名，参见 `mcp-servers/.env.example`

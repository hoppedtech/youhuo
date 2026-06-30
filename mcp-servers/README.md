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
├── tools/                      # 公共工具（compose、write_guard、cooperate_workers 等）
├── youhuo-b-api/
│   ├── server.py               # ★ B 端统一入口
│   └── internal/               # auth / guard / hire / task / finance
├── youhuo-c-api/
│   ├── server.py               # ★ C 端统一入口
│   └── internal/               # auth / guard / worker / profile / finance
├── mcp.json                    # 本地 stdio 配置
└── .dockerignore               # 镜像构建排除项（marketplace/ 在本地维护，未纳入 GitHub）
```

> `marketplace/`（Dockerfile、`meta.json`、广场 DOC）在 **`.gitignore` 中**，仅维护者本地保留，公开克隆不包含该目录。

## 快速开始

**推荐远程安装**（无需克隆仓库与 Python 环境）。本地 stdio 适用于开发调试，见下文「本地开发」。

在 Cursor / WorkBuddy 的 `.cursor/mcp.json` 中按需启用：

```json
{
  "mcpServers": {
    "youhuo-b-api": {
      "url": "https://mcp-server.hopped.com.cn/b/mcp",
      "transportType": "streamable-http",
      "disabled": false
    },
    "youhuo-c-api": {
      "url": "https://mcp-server.hopped.com.cn/c/mcp",
      "transportType": "streamable-http",
      "disabled": false
    }
  }
}
```

首次使用：`create_auth_session` → 微信扫码 → `check_auth_status`。详见 [`marketplace/youhuo-b-api/DOC.md`](marketplace/youhuo-b-api/DOC.md)、[`marketplace/youhuo-c-api/DOC.md`](marketplace/youhuo-c-api/DOC.md)。

### 本地开发（stdio）

```bash
cd mcp-servers
pip install mcp httpx

# 启动 B 端
python youhuo-b-api/server.py

# 启动 C 端（简历功能需额外依赖）
pip install fpdf2 cos-python-sdk-v5
python youhuo-c-api/server.py
```

需配置 `YOUHUO_BASE_URL`，见 `.env.example` 与 `mcp-servers/mcp.json`。

## MCP 配置（Cursor / WorkBuddy）

| Server | 角色 | 对应 Skill |
|:---|:---|:---|
| `youhuo-b-api` | 招工方 (B) | job-planner, workforce-dispatcher |
| `youhuo-c-api` | 找活方 (C) | job-seeker |

**推荐远程安装**（见上文「快速开始」）。本地 stdio 使用 `mcp-servers/mcp.json` 模板，需自行配置 `YOUHUO_BASE_URL`。

## youhuo-b-api Tool 清单

**授权**：`create_auth_session`（固定 role=2）、`check_auth_status`、`get_current_user_info`、`revoke_auth`

**岗位发布**（job-planner）：`preview_publish_cost`、`get_publish_reference`、`get_recruit_addresses`、`save_recruit_address`、`get_job_publish_catalog`、`publish_jd`、`get_job_publish_payment`、`pay_hourly_job`、`pay_publish_points`、`get_enterprise_finance`

**众包**（job-planner）：`get_task_categories`、`publish_task`、`get_task_orders`、`accept_delivery`

**调度**（workforce-dispatcher）：`get_job_list`、`get_job_workers`、`get_cooperate_workers`、`invite_worker_to_job`、`mark_worker_suitable`、`get_job_schedules`、`get_todo_list`、`manage_attendance`、`close_job`、`get_workforce_summary`

**结算/发票**：`get_enterprise_finance`、`pay_schedule_settlement`、`pay_balance`、`manage_invoice`

**测试用例**（B 端 Agent 行为、确认流程、支付边界）：[`docs/youhuo-b-api-test-cases.md`](docs/youhuo-b-api-test-cases.md)

**产品培训手册**（B/C 端流程、示例对话、Live Demo）：[`docs/mcp-product-training.md`](docs/mcp-product-training.md)

**B 端 Skill**（Agent 行为规则）：[`skills/job-planner/SKILL.md`](../skills/job-planner/SKILL.md)、[`skills/workforce-dispatcher/SKILL.md`](../skills/workforce-dispatcher/SKILL.md)

## youhuo-c-api Tool 清单

**授权**：`create_auth_session`（固定 role=1）、`check_auth_status`、`get_current_user_info`、`revoke_auth`

**写确认**：`prepare_write_confirmation`（P0/P1 两阶段 confirm_token）

**找活**（job-seeker）：`search_jobs`、`search_piece_tasks`、`get_recommend_jobs`、`get_job_detail`、`check_apply_readiness`、`submit_job_registration`、`apply_job`、`apply_job_standby`、`cancel_apply`、`cancel_job_standby`、`get_my_work_orders`、`get_task_detail`、`cancel_order`、`get_work_calendar`

**画像/认证**：`get_user_profile`（`format=json|text`，`sections=profile,preferences,auth,resume`）、`get_skill_tags`、`update_work_preferences`、`manage_resume`（`action=guide|upload|generate|delete`）

**余额**：`get_worker_balance`（提现请引导用户至小程序）

## Skill 清单

| Skill | MCP Server | 路径 |
|:---|:---|:---|
| job-planner | youhuo-b-api | `skills/job-planner/SKILL.md` |
| workforce-dispatcher | youhuo-b-api | `skills/workforce-dispatcher/SKILL.md` |
| job-seeker | youhuo-c-api | `skills/job-seeker/SKILL.md` |

安装说明见仓库根目录 [`skills/README.md`](../../skills/README.md)。

## 环境变量

| 变量 | 说明 |
|:---|:---|
| `YOUHUO_BASE_URL` | API 网关域名（代码自动拼接 applet / miniprogram-web / platform-service 路径） |
| `YOUHUO_REQUIRE_BASE_URL` | 设为 `1` 时未配置网关则拒绝启动（云托管镜像内置） |
| `YOUHUO_REJECT_TEST_GATEWAY` | 设为 `1` 时禁止误用 sops-test（云托管镜像内置） |
| `YOUHUO_AUTH_DB_PATH` | 授权 SQLite 路径，云托管默认 `/tmp/youhuo_auth.db` |
| `YOUHUO_EMPLOY_URL` | B 端招工网关（已废弃，请仅用 `YOUHUO_BASE_URL`） |
| `YOUHUO_TASK_URL` | 众包网关（已废弃，请仅用 `YOUHUO_BASE_URL`） |
| `YOUHUO_GET_TOKEN_URL` | 扫码授权轮询接口 |
| `YOUHUO_MCP_WRITE_ENABLED` | MCP 写操作总开关，默认 `true`；设为 `false` 时所有写 Tool 拒绝执行 |
| `YOUHUO_MCP_CONFIRM_TOKEN_REQUIRED` | 两阶段 confirm_token 开关，默认 `true` |
| `YOUHUO_MCP_CONFIRM_TOKEN_TTL` | confirm_token 有效期（秒），默认 300 |
| `YOUHUO_MCP_CONFIRM_TOKEN_STORE` | token 存储路径，默认 `~/.workbuddy/youhuo_mcp_confirm_tokens.json` |

默认使用测试环境 `hopped-gateway-service-sops-test.hopped.com.cn`。

## 市场上架（marketplace/）

CloudBase / 腾讯云 MCP 广场的 Docker、meta、DOC 与入驻文案在 **`marketplace/`**。在 `mcp-servers/` 根目录构建镜像：

```bash
docker build -f marketplace/youhuo-b-api/Dockerfile -t youhuo-b-api-mcp:1.0.0 .
docker build -f marketplace/youhuo-c-api/Dockerfile -t youhuo-c-api-mcp:1.0.0 .
```

入驻申请表填写文案见 `marketplace/APPLICATION-*.md`；上架检查清单见 `marketplace/README.md`。

## 后端依赖

扫码授权需后端实现 `Login/GetTokenBySession` 及 `minilogin` Redis 缓存。

## 安全提示

- **勿提交** `~/.workbuddy/youhuo_auth.db` 或任何真实 Token（已写入根目录 `.gitignore`）
- B 端写操作须 **两阶段确认**：先 `prepare_write_confirmation` 获 `confirm_token`，再 `user_confirmed=true` + 相同参数调用写 Tool
- C 端 **分级门禁**：P0/P1（报名、提现、取消报名等）两阶段 confirm_token；P2（改偏好、简历、候补）仅 `user_confirmed=true`
- 可将 `YOUHUO_MCP_CONFIRM_TOKEN_REQUIRED=false` 关闭两阶段（仅建议本地调试）
- 可将 `YOUHUO_MCP_WRITE_ENABLED=false` 设为只读模式（查询类 Tool 仍可用）
- 写操作审计见 `YOUHUO_MCP_AUDIT_LOG_PATH`
- 生产部署仅配置 `YOUHUO_BASE_URL` 网关域名，参见 `.env.example`

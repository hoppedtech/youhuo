# 有活 · B端招工 MCP（youhuo-b-api）

面向**招工方（企业/B 端）**的 MCP Server，支持岗位发布、用工调度、众包任务与结算。

## 功能亮点

- 微信扫码授权（B 端）
- 岗位发布、费用预估、积分支付
- 众包任务发布与验收
- 排班调度、考勤管理、用工汇总
- 企业余额、结算支付、发票申请

## 推荐搭配 Skill

| Skill | 说明 |
|:---|:---|
| `job-planner` | B 端招人、发岗位、发众包 |
| `workforce-dispatcher` | 排班、考勤、筛人、停止招工 |

Skill 源码：`skills/job-planner/`、`skills/workforce-dispatcher/`（安装见 [skills/README.md](https://github.com/hoppedtech/youhuo/blob/main/skills/README.md)）

## 核心 Tools（约 30）

| 分类 | Tools |
|:---|:---|
| 授权 | `create_auth_session`, `check_auth_status`, `get_current_user_info`, `revoke_auth` |
| 写确认 | `prepare_write_confirmation` |
| 发岗 | `preview_publish_cost`, `get_publish_reference`, `get_job_publish_catalog`, `publish_jd`, `pay_publish_points`, `pay_hourly_job`, `get_job_publish_payment` |
| 众包 | `get_task_categories`, `publish_task`, `get_task_orders`, `accept_delivery` |
| 调度 | `get_job_list`, `get_job_workers`, `get_cooperate_workers`, `invite_worker_to_job`, `mark_worker_suitable`, `get_job_schedules`, `get_todo_list`, `manage_attendance`, `close_job`, `get_workforce_summary` |
| 财务 | `get_enterprise_finance`, `pay_schedule_settlement`, `pay_balance`, `manage_invoice` |

## 授权与会话

1. 调用 `create_auth_session` 获取小程序码
2. 用户微信扫码登录有活小程序（招工方）
3. 轮询 `check_auth_status` 直至 `authorized`

**远程部署：** 无需 API Key；容器重启或会话过期后需重新微信扫码。

## 安装

**推荐大多数用户使用远程安装**：无需克隆仓库、安装 Python 或配置网关，连接生产环境即可使用。

### 远程安装（推荐）

在 Cursor / WorkBuddy 的 `.cursor/mcp.json`（或客户端 MCP 配置）中填入：

```json
{
  "mcpServers": {
    "youhuo-b-api": {
      "url": "https://mcp-server.hopped.com.cn/b/mcp",
      "transportType": "streamable-http",
      "disabled": false
    }
  }
}
```

1. 重启 MCP 或重载配置，确认 Server 已连接
2. 调用 `create_auth_session` 获取小程序码
3. 用户微信扫码登录有活小程序（招工方）
4. 轮询 `check_auth_status` 直至 `authorized`
5. 搭配 Skill：`job-planner`、`workforce-dispatcher`（见 [skills/README.md](https://github.com/hoppedtech/youhuo/blob/main/skills/README.md)）

容器重启或会话过期后需重新扫码授权。

### 本地安装（stdio）

适用于**本地开发或调试**。需克隆仓库、安装依赖并配置 `YOUHUO_BASE_URL`（见下文「环境变量」）。

```json
{
  "mcpServers": {
    "youhuo-b-api": {
      "command": "python",
      "args": ["youhuo-b-api/server.py"],
      "cwd": "/path/to/mcp-servers",
      "env": {
        "YOUHUO_BASE_URL": "https://hopped-gateway-service-sops-test.hopped.com.cn"
      }
    }
  }
}
```

依赖：`pip install -r marketplace/youhuo-b-api/requirements.txt`

## 环境变量（仅本地 stdio）

| 用途 | 代码路径 |
|:---|:---|
| 扫码授权 | `hopped-applet-service/api/` |
| B 端招工 | `hopped-miniprogram-web/api/` |
| 众包任务 | `hopped-platform-service/api/` |

| 变量 | 必填 | 说明 |
|:---|:---|:---|
| `YOUHUO_BASE_URL` | 是 | 有活 API 网关域名 |

### 环境对照

| 环境 | `YOUHUO_BASE_URL` |
|:---|:---|
| **生产** | `https://hopped-gateway-service-sops.hopped.com.cn` |

## 安全说明

- 发岗、支付、结算等写操作须 **两阶段确认**：先 `prepare_write_confirmation` 获 `confirm_token`，再 `user_confirmed=true` + 相同参数调用写 Tool
- 仅传 `user_confirmed=true` 而无有效 token 时 MCP 返回 `CONFIRM_TOKEN_REQUIRED`
- 企业 Token 仅用于 B 端网关，与 C 端隔离

## 开源协议

MIT License（见仓库根目录 `LICENSE`）

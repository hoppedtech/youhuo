# 有活 · B端招工 MCP（youhuo-b-api）

面向**招工方（企业/B 端）**的 MCP Server，支持岗位发布、用工调度、众包任务与结算。

## 功能亮点

- 微信扫码授权（B 端 role=2）
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

**Hosted 部署：** 每用户独立 SSE URL；容器重启后重新扫码；无需 API Key。

## 环境变量

广场 / 云托管**只需配置网关域名** `YOUHUO_BASE_URL`，以下路径由代码自动拼接：

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
| **测试** | `https://hopped-gateway-service-sops-test.hopped.com.cn` |

### 云托管推荐配置（镜像已预设路径）

| 变量 | 说明 |
|:---|:---|
| `YOUHUO_REQUIRE_BASE_URL` | 镜像内置 `1`：未配置网关时拒绝启动 |
| `YOUHUO_REJECT_TEST_GATEWAY` | 镜像内置 `1`：禁止误用 sops-test |
| `YOUHUO_AUTH_DB_PATH` | 默认 `/tmp/youhuo_auth.db` |
| `YOUHUO_MCP_CONFIRM_TOKEN_STORE` | 默认 `/tmp/youhuo_mcp_confirm_tokens.json` |
| `YOUHUO_MCP_AUDIT_LOG_PATH` | 默认 `/tmp/youhuo_mcp_audit.log` |

容器重启后 Token 与 confirm_token 会丢失，用户需重新微信扫码。

## 本地安装（stdio）

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

## 远程 MCP（CloudBase Hosted）

```bash
cd mcp-servers
docker build -f marketplace/youhuo-b-api/Dockerfile -t youhuo-b-api-mcp:1.0.0 .
```

云托管环境变量（生产示例）：

```env
YOUHUO_BASE_URL=https://hopped-gateway-service-sops.hopped.com.cn
```

镜像已内置 `YOUHUO_REQUIRE_BASE_URL=1`：未注入生产网关时容器拒绝启动。

[☁️ 前往云开发平台部署 MCP Server](https://tcb.cloud.tencent.com/dev#/ai?tab=mcp)

## 安全说明

- 发岗、支付、结算等写操作须 **两阶段确认**：先 `prepare_write_confirmation` 获 `confirm_token`，再 `user_confirmed=true` + 相同参数调用写 Tool
- 仅传 `user_confirmed=true` 而无有效 token 时 MCP 返回 `CONFIRM_TOKEN_REQUIRED`
- 企业 Token 仅用于 B 端网关，与 C 端隔离

| 变量 | 说明 |
|:---|:---|
| `YOUHUO_MCP_CONFIRM_TOKEN_REQUIRED` | 两阶段 token 开关，默认 `true` |
| `YOUHUO_MCP_CONFIRM_TOKEN_TTL` | token 有效期（秒），默认 300 |
| `YOUHUO_MCP_WRITE_ENABLED` | 写操作总开关，默认 `true` |

## 开源协议

MIT License（见仓库根目录 `LICENSE`）

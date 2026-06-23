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

## 核心 Tools（31）

| 分类 | Tools |
|:---|:---|
| 授权 | `create_auth_session`, `check_auth_status`, `get_current_user_info`, `revoke_auth` |
| 发岗 | `preview_publish_cost`, `publish_jd`, `pay_publish_points`, `get_work_categories`, `get_skill_list`, `get_benefit_list` |
| 众包 | `get_task_categories`, `publish_task`, `get_task_orders`, `accept_delivery` |
| 调度 | `get_job_list`, `get_job_workers`, `mark_worker_suitable`, `get_schedule_list`, `get_schedule_detail_list`, `get_todo_list`, `refuse_attendance`, `add_work_time`, `delete_work_time`, `close_job`, `get_workforce_summary` |
| 财务 | `get_enterprise_balance`, `get_account_log`, `pay_schedule_settlement`, `pay_balance`, `apply_invoice`, `get_invoice_list` |

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
| **生产** | `https://hopped-gateway-service.hopped.com.cn` |
| **测试** | `https://hopped-gateway-service-sops-test.hopped.com.cn` |

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
YOUHUO_BASE_URL=https://hopped-gateway-service.hopped.com.cn
```

[☁️ 前往云开发平台部署 MCP Server](https://tcb.cloud.tencent.com/dev#/ai?tab=mcp)

## 安全说明

- 发岗、支付、结算等写操作需用户明确确认
- 企业 Token 仅用于 B 端网关，与 C 端隔离

## 开源协议

MIT License（见仓库根目录 `LICENSE`）

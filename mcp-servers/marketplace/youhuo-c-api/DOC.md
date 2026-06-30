# 有活 · C端找活 MCP（youhuo-c-api）

面向**找活方（零工）**的 MCP Server，支持从搜零工，岗位到报名接单的完整闭环。

## 功能亮点

- 微信扫码授权（C 端 ）
- 零活/工作岗位搜索（对齐小程序参数）/ 智能推荐
- 岗位详情、报名资料检查、报名接单、取消报名
- 我的订单、干活日历、余额查询（提现请至小程序）

## 推荐搭配 Skill

| Skill | 说明 |
|:---|:---|
| `job-seeker` | C 端求职助手，定义搜索 SOP、报名安全边界 |

Skill 源码：`skills/job-seeker/`（安装见 [skills/README.md](https://github.com/hoppedtech/youhuo/blob/main/skills/README.md)）

## 核心 Tools（约 24）

| 分类 | Tools |
|:---|:---|
| 授权 | `create_auth_session`, `check_auth_status`, `get_current_user_info`, `revoke_auth` |
| 写确认 | `prepare_write_confirmation` |
| 找活 | `search_jobs`, `get_recommend_jobs`, `search_piece_tasks`, `get_job_detail` |
| 报名 | `check_apply_readiness`, `submit_job_registration`, `apply_job`, `apply_job_standby`, `cancel_apply`, `cancel_job_standby` |
| 订单 | `get_my_work_orders`, `get_task_detail`, `cancel_order`, `get_work_calendar` |
| 画像 | `get_user_profile`（`sections=profile,preferences,auth,resume`）, `get_skill_tags`, `update_work_preferences`, `manage_resume` |
| 财务 | `get_worker_balance`（含小程序提现引导，无 MCP 提现 Tool） |

### 搜索说明

`search_jobs` 在传入 `keyword` 时调用 `Job/GetSearchList`，参数与有活小程序一致：

- `city` 会规范为 `北京市` 等形式
- `keyword` / `position_title` 按标题检索
- 可选 `lat`、`lng` 提升附近岗位排序（如竞园：`39.894322`, `116.510951`）

## 授权与会话

1. 调用 `create_auth_session` 获取小程序码与 `session_id`
2. 用户微信扫码登录有活小程序
3. 轮询 `check_auth_status` 直至 `authorized`
4. 后续 Tool 自动携带 Token

**远程部署：** 无需 API Key；Token 有效期约 **2 小时**；容器重启或会话过期后需重新微信扫码。

## 安装

**推荐大多数用户使用远程安装**：无需克隆仓库、安装 Python 或配置网关，连接生产环境即可使用。

### 远程安装（推荐）

在 Cursor / WorkBuddy 的 `.cursor/mcp.json`（或客户端 MCP 配置）中填入：

```json
{
  "mcpServers": {
    "youhuo-c-api": {
      "url": "https://mcp-server.hopped.com.cn/c/mcp",
      "transportType": "streamable-http",
      "disabled": false
    }
  }
}
```

1. 重启 MCP 或重载配置，确认 Server 已连接
2. 调用 `create_auth_session` 获取小程序码与 `session_id`
3. 用户微信扫码登录有活小程序
4. 轮询 `check_auth_status` 直至 `authorized`
5. 搭配 Skill：`job-seeker`（见 [skills/README.md](https://github.com/hoppedtech/youhuo/blob/main/skills/README.md)）

容器重启或会话过期后需重新扫码授权。

### 本地安装（stdio）

适用于**本地开发或调试**。需克隆仓库、安装依赖并配置 `YOUHUO_BASE_URL`（见下文「环境变量」）。

```json
{
  "mcpServers": {
    "youhuo-c-api": {
      "command": "python",
      "args": ["youhuo-c-api/server.py"],
      "cwd": "/path/to/mcp-servers",
      "env": {
        "YOUHUO_BASE_URL": "https://hopped-gateway-service-sops-test.hopped.com.cn"
      }
    }
  }
}
```

依赖：`pip install -r marketplace/youhuo-c-api/requirements.txt`

## 环境变量（仅本地 stdio）

| 环境 | `YOUHUO_BASE_URL` |
|:---|:---|
| **生产** | `https://hopped-gateway-service-sops.hopped.com.cn` |

## 安全说明

- **P0/P1 写操作**（`apply_job`、`cancel_apply`、`cancel_order`、`submit_job_registration`、`revoke_auth`）须两阶段确认：先 `prepare_write_confirmation` 获 `confirm_token`，再 `user_confirmed=true` + 相同参数调用
- **P2 低危写操作**（`update_work_preferences`、`manage_resume`（upload/generate/delete）、候补类）仅需 `user_confirmed=true`
- **提现**：Agent 不代用户提现；查询余额后引导至有活小程序「我的 → 钱包 → 提现」
- 手机号、姓名等隐私字段脱敏展示
- Token 仅通过用户本人微信扫码获取，请勿泄露 MCP 连接地址或会话信息

## 开源协议

MIT License（见仓库根目录 `LICENSE`）

# 有活 · C端找活 MCP（youhuo-c-api）

面向**找活方（零工）**的 MCP Server，支持从搜岗位到报名接单的完整闭环。

## 功能亮点

- 微信扫码授权（C 端 role=1）
- 岗位搜索（`Job/GetSearchList`，对齐小程序参数）/ 智能推荐
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

**Hosted 部署（腾讯云 MCP 广场）：**

- 每位用户通过**独立 SSE URL** 连接，会话相互隔离
- Token 保存在容器 SQLite，默认 **`/tmp/youhuo_auth.db`**（镜像 `YOUHUO_AUTH_DB_PATH`）
- Token 有效期约 **2 小时**；**容器重启或实例重建后需重新扫码授权**
- 无需用户配置 API Key

## 环境变量

广场 / 云托管**只需配置网关域名** `YOUHUO_BASE_URL`。业务路径 `hopped-applet-service/api/` 及扫码地址 `{域名}/hopped-applet-service/api/Login/GetTokenBySession` 由代码自动拼接。

| 变量 | 必填 | 说明 |
|:---|:---|:---|
| `YOUHUO_BASE_URL` | 是 | 有活 API 网关域名（可带 `https://`，也可只写主机名） |

### 环境对照

| 环境 | `YOUHUO_BASE_URL` |
|:---|:---|
| **生产（广场上架）** | `https://hopped-gateway-service-sops.hopped.com.cn` |
| **测试 / 本地开发** | `https://hopped-gateway-service-sops-test.hopped.com.cn` |

实际请求前缀示例（代码生成，无需配置）：

```
https://hopped-gateway-service-sops.hopped.com.cn/hopped-applet-service/api/
```
## 本地安装（stdio）

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

## 远程 MCP（Hosted / 腾讯云 MCP 广场）

### 构建镜像

在 `mcp-servers/` 根目录执行：

```bash
docker build -f marketplace/youhuo-c-api/Dockerfile -t youhuo-c-api-mcp:1.0.0 .
```

镜像通过 `@cloudbase/mcp-transformer` 将 stdio 转为 HTTP，监听 **80** 端口。

### 云托管环境变量（生产示例）

```env
YOUHUO_BASE_URL=https://hopped-gateway-service-sops.hopped.com.cn
```

镜像已内置 `YOUHUO_REQUIRE_BASE_URL=1`：未注入生产网关时容器拒绝启动。可选路径变量见上文「授权与会话」。

### IDE 配置（SSE）

在 [MCP 广场](https://cloud.tencent.com/document/product/1212/123193) 连接 Server 后，将生成的 SSE URL 填入客户端，例如 CodeBuddy：

```json
{
  "mcpServers": {
    "youhuo-c-api": {
      "type": "sse",
      "url": "https://mcp-api.tencent-cloud.com/sse/<your-token>"
    }
  }
}
```

[☁️ CloudBase 云开发 MCP 部署](https://tcb.cloud.tencent.com/dev#/ai?tab=mcp)

## 安全说明

- **P0/P1 写操作**（`apply_job`、`cancel_apply`、`cancel_order`、`submit_job_registration`、`revoke_auth`）须两阶段确认：先 `prepare_write_confirmation` 获 `confirm_token`，再 `user_confirmed=true` + 相同参数调用
- **P2 低危写操作**（`update_work_preferences`、`manage_resume`（upload/generate/delete）、候补类）仅需 `user_confirmed=true`
- **提现**：Agent 不代用户提现；查询余额后引导至有活小程序「我的 → 钱包 → 提现」
- 手机号、姓名等隐私字段脱敏展示
- Token 仅通过用户本人微信扫码获取，请勿泄露 SSE URL 或会话信息
- 报名前建议调用 `check_apply_readiness(job_id)` 检查权限与资料

| 变量 | 说明 |
|:---|:---|
| `YOUHUO_MCP_CONFIRM_TOKEN_REQUIRED` | 两阶段 token 开关，默认 `true` |
| `YOUHUO_MCP_WRITE_ENABLED` | 写操作总开关，默认 `true` |

## 后端依赖

- 有活小程序网关 `hopped-applet-service`
- 扫码授权：`Login/GetTokenBySession` 及小程序 `minilogin` 会话缓存

## 开源协议

MIT License（见仓库根目录 `LICENSE`）

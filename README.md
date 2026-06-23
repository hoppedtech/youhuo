# 有活 MCP（youhuo）

[有活](https://www.hopped.com.cn) 灵活用工平台的 **Model Context Protocol (MCP)** 实现，让 AI 助手（Cursor、CodeBuddy 等）帮用户完成招工、找活、报名、排班与结算。

本仓库包含 **B 端招工** 与 **C 端找活** 两个 MCP Server，以及配套的 Cursor Agent Skills。

## 仓库结构

```
youhuo/
├── LICENSE                          # MIT
├── mcp-servers/                     # MCP 实现（主代码）
│   ├── youhuo-b-api/                # B 端统一入口（招工方 role=2）
│   ├── youhuo-c-api/                # C 端统一入口（找活方 role=1）
│   ├── tools/                       # 共享工具（搜索、报名、环境配置等）
│   ├── marketplace/                 # 腾讯云 MCP 广场上架包
│   ├── mcp.json                     # MCP 客户端配置示例
│   └── README.md                    # 详细文档与 Tool 清单
├── .cursor/
│   ├── mcp.json                     # Cursor MCP 配置示例
│   └── skills/                      # Agent Skills
│       ├── job-seeker/              # C 端求职助手
│       ├── job-planner/             # B 端发岗助手
│       └── workforce-dispatcher/    # B 端排班调度
```

## 快速开始

### 1. 安装依赖

```bash
cd mcp-servers
pip install mcp httpx
```

### 2. 配置环境变量

复制示例并设置网关域名（**只需一项**）：

```bash
cp .env.example .env
```

| 环境 | `YOUHUO_BASE_URL` |
|:---|:---|
| 测试 / 本地 | `https://hopped-gateway-service-sops-test.hopped.com.cn` |
| 生产 | `https://hopped-gateway-service.hopped.com.cn` |

业务路径（`hopped-applet-service/api/` 等）由代码自动拼接，无需单独配置。

### 3. 配置 Cursor

将 `.cursor/mcp.json` 复制到项目根目录，或合并到全局 Cursor MCP 配置。启动后可见 `youhuo-b-api` 与 `youhuo-c-api` 两个 Server。

### 4. 授权流程

1. 调用 `create_auth_session` 获取小程序码
2. 用户微信扫码登录有活小程序
3. 轮询 `check_auth_status` 直至 `authorized`
4. 后续 Tool 自动携带 Token

Token 保存在本机 `~/.workbuddy/youhuo_auth.db`（约 2 小时有效）。

## C 端找活（youhuo-c-api）

典型对话流程：

```
搜岗位 → 看详情 → 查报名资料 → 报名 → 查订单 / 余额
```

| Tool | 说明 |
|:---|:---|
| `search_jobs` | 按城市、关键词搜索（对齐小程序 `GetSearchList`） |
| `get_recommend_jobs` | 智能推荐 |
| `get_job_detail` | 岗位详情 |
| `get_entry_job_requirements` | 报名前资料检查（小时工需班次 ID） |
| `apply_job` / `cancel_apply` | 报名 / 取消报名 |
| `get_my_work_orders` | 我的订单 |

推荐搭配 Skill：`.cursor/skills/job-seeker/SKILL.md`

## B 端招工（youhuo-b-api）

支持岗位发布、众包任务、排班调度、结算发票等。推荐搭配 `job-planner`、`workforce-dispatcher` Skill。

完整 Tool 列表见 [`mcp-servers/README.md`](mcp-servers/README.md)。

## 市场上架

腾讯云 MCP 广场打包与部署说明见 [`mcp-servers/marketplace/README.md`](mcp-servers/marketplace/README.md)。

## 安全说明

- **切勿提交** `youhuo_auth.db`、`.env` 或任何真实 Token（已配置 `.gitignore`）
- 写操作（`apply_job`、`cancel_apply`、`withdraw_balance` 等）须在获得用户**明确确认**后调用
- `check_auth_status` 仅返回截断的 `token_preview`，不暴露完整 Token

## 许可证

[MIT License](LICENSE) — Copyright (c) 深圳高灯计算机科技有限公司

## 相关链接

- C 端 MCP 文档：[`mcp-servers/marketplace/youhuo-c-api/DOC.md`](mcp-servers/marketplace/youhuo-c-api/DOC.md)
- B 端 MCP 文档：[`mcp-servers/marketplace/youhuo-b-api/DOC.md`](mcp-servers/marketplace/youhuo-b-api/DOC.md)
- GitHub：`https://github.com/hoppedtech/youhuo`（创建仓库后请与 `meta.json` 中 `gitUrl` 保持一致）

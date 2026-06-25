# TKE 托管有活 MCP Server

参考：[容器服务 MCP Server 托管](https://cloud.tencent.cn/document/product/457/124005)

有活 MCP 当前以 **stdio** 实现（`youhuo-*-api/server.py`），云端通过 `@cloudbase/mcp-transformer` 转为 **HTTP**，供 TKE 以 Streamable HTTP 方式对外暴露。

## 架构

```
Codebuddy / Cursor (streamable-http Client)
        │  http://<LB-IP>:<port>/mcp
        ▼
TKE Service (LoadBalancer)
        ▼
Pod: mcp-transformer stdio-to-http :80
        │  stdio
        ▼
python youhuo-b-api/server.py  或  youhuo-c-api/server.py
        │
        ▼
有活 API 网关 (YOUHUO_BASE_URL)
```

B 端、C 端为**两个独立镜像**，建议各建一个 Deployment + Service。

## 一、镜像打包

在 **`mcp-servers/` 根目录** 构建（上下文必须含 `tools/`、`shared_token_store.py`）：

```bash
cd mcp-servers

# B 端招工
docker build -f marketplace/youhuo-b-api/Dockerfile -t youhuo-b-api-mcp:1.0.0 .

# C 端找活
docker build -f marketplace/youhuo-c-api/Dockerfile -t youhuo-c-api-mcp:1.0.0 .
```

本地冒烟（需注入生产网关，否则镜像内置 fail-fast 会拒绝启动）：

```bash
docker run --rm -p 8080:80 \
  -e YOUHUO_BASE_URL=https://hopped-gateway-service-sops.hopped.com.cn \
  youhuo-b-api-mcp:1.0.0

curl -f http://127.0.0.1:8080/
```

## 二、推送至 CCR（容器镜像服务）

1. 登录 [容器镜像服务控制台](https://console.cloud.tencent.com/tcr)，创建命名空间与镜像仓库（如 `youhuo/youhuo-b-api-mcp`）。
2. 个人版 CCR 示例（按控制台显示的「登录指令」替换域名与命名空间）：

```bash
docker login ccr.ccs.tencentyun.com

docker tag youhuo-b-api-mcp:1.0.0 \
  ccr.ccs.tencentyun.com/<namespace>/youhuo-b-api-mcp:1.0.0
docker push ccr.ccs.tencentyun.com/<namespace>/youhuo-b-api-mcp:1.0.0

docker tag youhuo-c-api-mcp:1.0.0 \
  ccr.ccs.tencentyun.com/<namespace>/youhuo-c-api-mcp:1.0.0
docker push ccr.ccs.tencentyun.com/<namespace>/youhuo-c-api-mcp:1.0.0
```

3. 若集群在私有 VPC 内拉镜像，将仓库设为**公有**或为 TKE 配置镜像拉取凭证（见 TKE 文档「常见问题 → CCR 无法访问」）。

## 三、TKE 工作负载

### 环境变量（必填）

| 变量 | 示例 |
|:---|:---|
| `YOUHUO_BASE_URL` | `https://hopped-gateway-service-sops.hopped.com.cn` |

镜像已内置（一般无需改）：

| 变量 | 值 |
|:---|:---|
| `YOUHUO_REQUIRE_BASE_URL` | `1` |
| `YOUHUO_REJECT_TEST_GATEWAY` | `1` |
| `YOUHUO_AUTH_DB_PATH` | `/tmp/youhuo_auth.db` |
| `YOUHUO_MCP_CONFIRM_TOKEN_STORE` | `/tmp/youhuo_mcp_confirm_tokens.json` |
| `YOUHUO_MCP_AUDIT_LOG_PATH` | `/tmp/youhuo_mcp_audit.log` |

### Deployment 要点

- **容器端口**：`80`（与 Dockerfile `EXPOSE 80` 一致）
- **资源建议**：request `256Mi` / `0.25 CPU`，limit `512Mi` / `0.5 CPU`（可按实际调大）
- **副本数**：托管场景建议 **1**（SQLite Token 为 Pod 内单例；多副本需改造 session 隔离）
- **健康检查**：HTTP GET `/`，端口 80

### Service 暴露

- 类型：**LoadBalancer**（公网 MCP Client 访问）或 ClusterIP + Ingress
- 端口映射：如 Service `8000` → 容器 `80`
- 记录 **公网 LB IP:端口**，供 Client 配置

控制台路径：容器服务 → 集群 → **工作负载** → Deployment → **新建** → 选择镜像 → **访问设置（Service）**。

## 四、Client 配置（Codebuddy）

按 [TKE 托管文档](https://cloud.tencent.cn/document/product/457/124005) 使用 **streamable-http**（路径以 mcp-transformer 实际暴露为准，一般为 `/mcp`）：

```json
{
  "mcpServers": {
    "youhuo-b-api": {
      "url": "http://<LB-IP>:<port>/mcp",
      "transportType": "streamable-http",
      "disabled": false
    }
  }
}
```

C 端将 Server 名与 URL 换为 `youhuo-c-api` 对应 Service 地址。

授权流程不变：Client 调用 `create_auth_session` → 用户微信扫码 → `check_auth_status`。

## 五、验证清单

- [ ] Pod 状态 **Running**，`curl http://<LB>/` 返回 200
- [ ] 未配 `YOUHUO_BASE_URL` 时 Pod **应 CrashLoop**（fail-fast 生效）
- [ ] Codebuddy 能列出 Tool（如 B 端 `get_job_list`、C 端 `search_jobs`）
- [ ] 扫码授权后只读 Tool 可调通
- [ ] 写 Tool 须 `prepare_write_confirmation` 两阶段确认

## 六、与 CloudBase 云托管的区别

| 项 | CloudBase 云托管 | TKE 托管 |
|:---|:---|:---|
| 镜像 | 相同 Dockerfile | 相同 Dockerfile |
| 暴露 | 平台分配 SSE/HTTP URL | 自建 LoadBalancer / Ingress |
| 环境变量 | 云托管控制台 | Deployment env |
| 文档 | MCP 广场 / CloudBase | [TKE MCP 托管](https://cloud.tencent.cn/document/product/457/124005) |

## 七、常见问题

**Pod Pending**：调低 CPU/内存 request，或扩容节点。

**启动即退出**：检查是否注入生产 `YOUHUO_BASE_URL`；是否误用 `sops-test`（会被 `YOUHUO_REJECT_TEST_GATEWAY` 拒绝）。

**多用户 Token 串号**：当前 SQLite + 单 `current_session` 设计适合单 Pod 单用户；生产 Hosted 需确认 Client 侧会话隔离策略，或一用户一 Deployment。

**C 端简历 PDF 乱码**：C 端镜像已装 `font-wqy-microhei`；若仍异常，可换 `python:3.12-slim` 基础镜像并安装 fonts-noto-cjk。

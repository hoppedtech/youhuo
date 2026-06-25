# 有活 MCP 市场上架包

本目录与运行时 `mcp-servers/` 代码分离，专门用于 **CloudBase MCP 市场** / **腾讯云 MCP 广场** 打包与部署。

## 目录结构

```
marketplace/
├── README.md                      # 本文件
├── APPLICATION-common.md          # 入驻问卷：企业与联系人（共用）
├── APPLICATION-youhuo-c-api.md    # 入驻问卷：C 端填写文案
├── APPLICATION-youhuo-b-api.md    # 入驻问卷：B 端填写文案
├── TKE-DEPLOY.md                  # TKE 托管部署
├── youhuo-c-api/             # C 端找活（配合 job-seeker Skill）
│   ├── DOC.md                # 市场详情页文档
│   ├── meta.json             # 上架元数据
│   ├── Dockerfile
│   └── requirements.txt
└── youhuo-b-api/             # B 端招工（配合 job-planner / workforce-dispatcher）
    ├── DOC.md
    ├── meta.json
    ├── Dockerfile
    └── requirements.txt
```

## 构建镜像

在 **`mcp-servers/` 根目录** 执行（构建上下文为整个 mcp-servers）：

```bash
cd mcp-servers

# C 端（建议打版本 tag）
docker build -f marketplace/youhuo-c-api/Dockerfile -t youhuo-c-api-mcp:1.0.0 .

# B 端
docker build -f marketplace/youhuo-b-api/Dockerfile -t youhuo-b-api-mcp:1.0.0 .
```

## 部署到 CloudBase 云托管

1. 安装并登录 [CloudBase CLI](https://docs.cloudbase.net/cli-v1/install)：`npm i -g @cloudbase/cli && tcb login`
2. 在 CloudBase 控制台创建环境，启用云托管
3. 上传镜像或使用 `tcb cloudrun deploy` 部署对应 Dockerfile
4. **在云托管控制台配置生产环境变量**（见各 `DOC.md`；须注入 `YOUHUO_BASE_URL`，镜像已设 `YOUHUO_REQUIRE_BASE_URL=1`）
5. 构建时使用 `.dockerignore` 减小镜像体积
6. 将 `meta.json` + `DOC.md` 提交 [云开发 MCP 市场上架](https://docs.cloudbase.net/ai/mcp/develop/publish)

## 部署到 TKE（容器服务 MCP 托管）

与 CloudBase **共用同一套 Dockerfile**。完整步骤（CCR 推送、Deployment/Service、Codebuddy streamable-http 配置）见 **[TKE-DEPLOY.md](./TKE-DEPLOY.md)**。

官方文档：[容器服务 MCP Server 托管](https://cloud.tencent.cn/document/product/457/124005)

## 腾讯云 MCP 广场（企业入驻）

Hosted 模式需企业入驻申请：

- 申请表：[腾讯云 MCP 广场入驻申请表](https://wj.qq.com/s2/23327353/7684/)
- 填写文案：`APPLICATION-common.md`（企业与联系人）、`APPLICATION-youhuo-c-api.md`、`APPLICATION-youhuo-b-api.md`
- 文档：[MCP 广场介绍](https://cloud.tencent.com/document/product/1212/123193)

广场采用**每用户独立 SSE URL**，会话隔离；容器重启后用户重新微信扫码即可。

## 上架前检查（youhuo-c-api）

- [ ] 仓库根目录添加开源许可证（MIT / Apache）— 已有 `LICENSE`
- [ ] `meta.json` 中 `gitUrl` 指向 GitHub 可见路径 — 已配置
- [ ] `marketplace/` 已纳入 Git 仓库（可推送 GitHub）
- [ ] 云托管仅配置生产 `YOUHUO_BASE_URL`（非 sops-test）
- [ ] 后端确认生产网关与 `Login/GetTokenBySession` 可用
- [ ] 准备 Logo（512×512）填入 `meta.json`
- [ ] 录制审核 Demo：扫码 → 搜索 → 详情 → 报名 → 取消
- [ ] 验证镜像 `youhuo-c-api-mcp:1.0.0` 健康检查与 Tool 调用

## 本地 stdio 调试（不上云）

使用项目根目录 `.cursor/mcp.json` 配置 MCP；Skill 安装见仓库 `skills/README.md`。

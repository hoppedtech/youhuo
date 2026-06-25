# 腾讯云 MCP 广场入驻 — youhuo-b-api 填写文案

> 申请表：https://wj.qq.com/s2/23327353/7684/  
> 企业与联系人见 [APPLICATION-common.md](./APPLICATION-common.md)

---

## 一、按字段逐项粘贴

### MCP 英文标识 / Server 名称

```
youhuo-b-api
```

### MCP 中文名称 / 显示标题

```
有活 · B端招工 MCP
```

### 一句话简介

```
连接有活灵活用工平台，让 AI 助手帮企业完成岗位发布、用工调度、众包任务与结算发票。
```

### 详细描述 / 功能介绍

```
有活 B 端招工 MCP 面向招工方（企业/个人雇主），在 Cursor、CodeBuddy 等 AI 客户端中提供从发岗到结算的完整闭环。

用户微信扫码授权招工方账号后，可预览发布费用、发布小时工/岗位 JD、支付发布积分，管理众包任务发布与验收，查看报名人员、邀请合作零工、排班考勤、关闭招工，并完成排班结算、余额支付与发票申请。

配套 job-planner（发岗/众包）与 workforce-dispatcher（调度/结算）Skill 规范 Agent 行为。所有发岗、支付、结算等写操作采用两阶段 confirm_token 防误操作。

适用于餐饮、零售、物流等灵活用工企业的 AI 化招工与调度场景。开源协议 MIT。代码仓库：https://github.com/hoppedtech/youhuo ，上架包路径：mcp-servers/marketplace/youhuo-b-api/
```

### 开源协议

```
MIT License
```

### 代码仓库地址

```
https://github.com/hoppedtech/youhuo/tree/main/mcp-servers/marketplace/youhuo-b-api
```

### 文档地址

```
https://github.com/hoppedtech/youhuo/blob/main/mcp-servers/marketplace/youhuo-b-api/DOC.md
```

### 版本号

```
1.0.0
```

### 标签 / 分类

```
灵活用工、招工、排班、人力资源、社区 MCP
```

### 上架类型 / 部署方式

```
Hosted 云托管（主推）。同时支持 Local stdio 模式（Python 3.10+，见 DOC.md）。
```

### 端口

```
80
```

### 传输协议

```
SSE / Streamable HTTP（@cloudbase/mcp-transformer stdio-to-http）
```

### 是否需要用户配置密钥

```
否。用户通过微信扫码授权获取 Token，无需填写 API Key 或 Secret。
```

### 是否依赖本地文件

```
否，可完全云托管部署。
```

### 外部服务依赖

```
有活 API 网关（hopped-applet-service 扫码授权、hopped-miniprogram-web B 端招工、hopped-platform-service 众包任务）、微信扫码登录
```

### 环境变量（云托管配置）

```
YOUHUO_BASE_URL=https://hopped-gateway-service-sops.hopped.com.cn
```

说明：仅需配置网关域名。扫码路径 hopped-applet-service/api/、B 端招工 hopped-miniprogram-web/api/、众包 hopped-platform-service/api/ 均由代码自动拼接。镜像内置 YOUHUO_REQUIRE_BASE_URL=1、YOUHUO_REJECT_TEST_GATEWAY=1。

### 目标用户 / 适用人群

```
有活平台注册企业/个人招工方；需通过 AI 助手发岗、筛人、排班、结算的 HR、店长、运营人员。
```

### 典型使用场景

```
场景1：「帮我发一个北京竞园的面点师小时工」→ 预览费用 → 发布 JD → 支付发布费用。

场景2：「这个岗位有哪些报名？帮我标记合适的」→ 查看报名列表 → 标记合适零工。

场景3：「本月待结算排班有哪些？」→ 查看排班 → 确认后结算支付。
```

### 解决的核心痛点

```
将多步骤发岗/支付/调度流程对话化；费用预览与双重确认降低误扣款风险；与小程序接口一致，减少参数错误。
```

### Tool 列表（功能清单）

```
授权（4）：create_auth_session、check_auth_status、get_current_user_info、revoke_auth
写确认（1）：prepare_write_confirmation
发岗（7）：preview_publish_cost、get_publish_reference、get_job_publish_catalog、publish_jd、pay_publish_points、pay_hourly_job、get_job_publish_payment
众包（4）：get_task_categories、publish_task、get_task_orders、accept_delivery
调度（10）：get_job_list、get_job_workers、get_cooperate_workers、invite_worker_to_job、mark_worker_suitable、get_job_schedules、get_todo_list、manage_attendance、close_job、get_workforce_summary
财务（4）：get_enterprise_finance、pay_schedule_settlement、pay_balance、manage_invoice

合计约 30 个 Tool。
```

### 敏感操作与安全措施

```
敏感操作：发岗（publish_jd）、支付（pay_hourly_job / pay_publish_points / pay_balance）、结算（pay_schedule_settlement）、发票（manage_invoice）。

安全措施：
1. 所有 B 端写操作须两阶段 confirm_token（prepare_write_confirmation → 写 Tool + user_confirmed=true）；
2. 仅传 user_confirmed=true 而无有效 token 时返回 CONFIRM_TOKEN_REQUIRED；
3. 企业 Token 与 C 端隔离（固定 role=2 招工方）；
4. MCP 不代用户拉起微信支付，余额扣款经确认后执行；
5. 每用户独立 Hosted SSE URL，会话隔离。
```

### 授权与会话说明

```
授权流程：
1）AI 调用 create_auth_session（固定 role=2 招工方）返回小程序码；
2）用户微信扫码登录有活小程序；
3）轮询 check_auth_status 至 authorized；
4）后续 Tool 自动携带 Token。

会话：Token 约 2 小时；容器重启后需重新扫码。Token 存于 /tmp/youhuo_auth.db。
```

### 配套 Skill

```
job-planner（B 端招人、发岗位、发众包）：skills/job-planner/SKILL.md
workforce-dispatcher（排班、考勤、筛人、停止招工）：skills/workforce-dispatcher/SKILL.md
```

### 审核测试说明

```
无需账号密码，审核人员使用微信扫码授权招工方账号即可。
推荐流程：get_job_list → get_job_workers → preview_publish_cost（只读预览，可不实际支付）。
测试环境：生产网关 YOUHUO_BASE_URL=https://hopped-gateway-service-sops.hopped.com.cn
```

### Demo 流程脚本

```
1. create_auth_session → 微信扫码 → check_auth_status 至 authorized
2. get_job_list(status="recruiting")
3. get_job_workers(job_id=...)
4. preview_publish_cost(...) → prepare_write_confirmation → publish_jd(...)（可用测试岗，避免真实扣款）
5. get_enterprise_finance(sections="balance")
6. get_job_schedules(job_id=...)
```

### Demo 视频

```
【待上传：约 5 分钟录屏，按上方 Demo 流程脚本录制】
```

---

## 二、整段合并版（适合「补充说明」「其他」等大文本框）

```
【MCP 标识】youhuo-b-api
【中文名称】有活 · B端招工 MCP
【版本】1.0.0
【协议】MIT
【仓库】https://github.com/hoppedtech/youhuo/tree/main/mcp-servers/marketplace/youhuo-b-api
【部署】Hosted 云托管，端口 80，SSE/Streamable HTTP，每用户独立 URL
【环境变量】YOUHUO_BASE_URL=https://hopped-gateway-service-sops.hopped.com.cn
【授权】微信扫码（招工方 role=2），无需 API Key
【简介】连接有活灵活用工平台，让 AI 助手帮企业完成岗位发布、用工调度、众包任务与结算发票。
【人群】有活平台企业/个人招工方
【场景】发小时工→预览费用→发布支付；看报名筛人；排班结算与发票
【安全】所有写操作两阶段 confirm_token；不代拉微信支付；B/C Token 隔离
【Skill】job-planner、workforce-dispatcher
【审核】微信扫码测试；推荐 get_job_list + preview_publish_cost 只读流程
【联系】技术支持：【待填姓名+微信/电话】
```

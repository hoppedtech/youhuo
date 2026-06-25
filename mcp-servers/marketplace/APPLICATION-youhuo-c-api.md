# 腾讯云 MCP 广场入驻 — youhuo-c-api 填写文案

> 申请表：https://wj.qq.com/s2/23327353/7684/  
> 企业与联系人见 [APPLICATION-common.md](./APPLICATION-common.md)

---

## 一、按字段逐项粘贴

### MCP 英文标识 / Server 名称

```
youhuo-c-api
```

### MCP 中文名称 / 显示标题

```
有活 · C端找活 MCP
```

### 一句话简介

```
连接有活灵活用工平台，让 AI 助手帮零工用户搜岗位、看详情、报名接单、查订单与余额。
```

### 详细描述 / 功能介绍

```
有活 C 端找活 MCP 面向求职者（零工），在 Cursor、CodeBuddy 等 AI 客户端中提供完整找活闭环。

用户通过微信扫码完成授权后，可用自然语言搜索附近岗位（支持城市、关键词、经纬度），查看岗位详情与排班，系统自动检查报名资料是否齐全，确认后完成小时工/岗位报名或取消报名，并可查询干活记录、日历与账户余额。

本 MCP 对齐有活小程序真实接口（含 Job/GetSearchList 标题搜索），配套 job-seeker Skill 规范求职流程与安全边界（报名等写操作需用户明确确认）。适用于灵活用工、兼职求职、同城小时工等场景。

开源协议 MIT。代码仓库：https://github.com/hoppedtech/youhuo ，上架包路径：mcp-servers/marketplace/youhuo-c-api/
```

### 开源协议

```
MIT License
```

### 代码仓库地址

```
https://github.com/hoppedtech/youhuo/tree/main/mcp-servers/marketplace/youhuo-c-api
```

### 文档地址

```
https://github.com/hoppedtech/youhuo/blob/main/mcp-servers/marketplace/youhuo-c-api/DOC.md
```

### 版本号

```
1.0.0
```

### 标签 / 分类

```
灵活用工、零工求职、招聘、小时工、社区 MCP
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
有活 API 网关（hopped-applet-service）、微信扫码登录（Login/GetTokenBySession）
```

### 环境变量（云托管配置）

```
YOUHUO_BASE_URL=https://hopped-gateway-service-sops.hopped.com.cn
```

说明：仅需配置网关域名，业务路径 hopped-applet-service/api/ 由代码自动拼接。

### 目标用户 / 适用人群

```
有活平台注册零工/求职者；使用 AI 编程助手找兼职、小时工的用户。
```

### 典型使用场景

```
场景1：「北京竞园附近有什么面点师岗位？」→ 搜索 → 查看详情 → 检查报名资料 → 用户确认后报名。

场景2：「我报了哪些活？明天有没有排班？」→ 查询我的订单与干活日历。

场景3：「账户里有多少钱可以提现？」→ 查询余额（提现引导至有活小程序，MCP 不代提现）。
```

### 解决的核心痛点

```
降低小程序多步操作成本；统一搜索参数与小程序一致；报名前自动校验资料与班次，减少误报；通过 confirm_token 防止 AI 擅自报名。
```

### Tool 列表（功能清单）

```
授权（4）：create_auth_session、check_auth_status、get_current_user_info、revoke_auth
写确认（1）：prepare_write_confirmation
找活（4）：search_jobs、get_recommend_jobs、search_piece_tasks、get_job_detail
报名（6）：check_apply_readiness、submit_job_registration、apply_job、apply_job_standby、cancel_apply、cancel_job_standby
订单（4）：get_my_work_orders、get_task_detail、cancel_order、get_work_calendar
画像（4）：get_user_profile、get_skill_tags、update_work_preferences、manage_resume
财务（1）：get_worker_balance（只读，无 MCP 提现 Tool）

合计约 24 个 Tool。
```

### 敏感操作与安全措施

```
敏感操作：报名（apply_job）、取消报名（cancel_apply）、取消订单（cancel_order）。

安全措施：
1. P0/P1 写操作两阶段 confirm_token（先 prepare_write_confirmation，再带 user_confirmed=true 调用写 Tool）；
2. 手机号、姓名等隐私字段脱敏展示；
3. Token 仅通过用户本人微信扫码获取，不落日志；
4. 每用户独立 Hosted SSE URL，会话相互隔离；
5. 报名前强制 check_apply_readiness 校验权限与资料；
6. 不提供 MCP 提现 Tool，提现引导至有活小程序。
```

### 授权与会话说明

```
授权流程：
1）AI 调用 create_auth_session 返回小程序码；
2）用户微信扫码登录有活小程序；
3）轮询 check_auth_status 至 authorized；
4）后续 Tool 自动携带 Token。

会话：Token 约 2 小时有效；容器重启后需重新扫码。每用户独立 SSE URL，不共享会话。Token 存于容器内 SQLite（/tmp/youhuo_auth.db）。
```

### 配套 Skill

```
推荐搭配 job-seeker（有活 C 端零工求职助手），定义找活 SOP 与安全边界。
路径：https://github.com/hoppedtech/youhuo/blob/main/skills/job-seeker/SKILL.md
```

### 审核测试说明

```
无需账号密码，审核人员使用微信扫码授权即可。
推荐测试：城市「北京」、关键词「面点师」、经纬度 39.894322, 116.510951（竞园附近）。
测试环境：生产网关 YOUHUO_BASE_URL=https://hopped-gateway-service-sops.hopped.com.cn
```

### Demo 流程脚本

```
1. create_auth_session → 展示二维码 → check_auth_status 至 authorized
2. search_jobs(city="北京", keyword="面点师", lat=39.894322, lng=116.510951)
3. get_job_detail(job_id=..., job_type="小时工")
4. check_apply_readiness(job_id, schedule_ids="...")
5. prepare_write_confirmation → apply_job(user_confirmed=true, confirm_token=...)
6. get_my_work_orders
7. prepare_write_confirmation → cancel_apply(...)
```

### Demo 视频

```
【待上传：约 5 分钟录屏，按上方 Demo 流程脚本录制】
```

---

## 二、整段合并版（适合「补充说明」「其他」等大文本框）

```
【MCP 标识】youhuo-c-api
【中文名称】有活 · C端找活 MCP
【版本】1.0.0
【协议】MIT
【仓库】https://github.com/hoppedtech/youhuo/tree/main/mcp-servers/marketplace/youhuo-c-api
【部署】Hosted 云托管，端口 80，SSE/Streamable HTTP，每用户独立 URL
【环境变量】YOUHUO_BASE_URL=https://hopped-gateway-service-sops.hopped.com.cn
【授权】微信扫码，无需 API Key
【简介】连接有活灵活用工平台，让 AI 助手帮零工用户搜岗位、看详情、报名接单、查订单与余额。
【人群】有活平台零工/求职者
【场景】搜附近岗位→看详情→校验资料→确认报名；查订单与日历；查余额（提现走小程序）
【安全】写操作两阶段 confirm_token；不提供 MCP 提现；隐私脱敏；每用户会话隔离
【Skill】job-seeker（skills/job-seeker/SKILL.md）
【审核】微信扫码测试；推荐关键词「北京」「面点师」
【联系】技术支持：【待填姓名+微信/电话】
```

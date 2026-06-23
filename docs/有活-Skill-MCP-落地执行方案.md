# 有活 Skill & MCP 落地执行方案

> 基于你的核心洞察——Skill 的本质是"剥离 GUI 后的核心业务逻辑"，是"数字劳动力交付"在 AI 神经网络中的直接接口。本文从功能拆解、架构设计、开发路线三个维度，给出可立即落地的完整方案。

---

## 一、从核心洞察推导功能清单

你的洞察可以拆解为两条业务主线：

| 维度 | 核心命题 | 一句话定义 |
|:---|:---|:---|
| **B 端（需求方）** | 用工规划与调度中枢 | Agent 说出用工需求 → 有活 Skill 自动拆解岗位 → 发布到物理世界 → 跟踪交付 |
| **C 端（求职者）** | 简历发布与匹配网关 | 用户在任意 Agent 中生成简历 → 一键同步至有活平台 → 自动匹配岗位 → 完成投递闭环 |

### 1.1 B 端 Skill 功能矩阵

| 功能模块 | Skill 名称 | 触发词 | 核心动作 | MCP 依赖 |
|:---|:---|:---|:---|:---|
| **用工需求解析** | `job-planner` | "招人""用工""岗位规划""人力需求" | 将自然语言需求拆解为结构化岗位描述（职位/人数/技能/工期/预算） | 无（纯 NLP 逻辑） |
| **岗位发布** | `job-publisher` | "发岗位""发布招聘""上架岗位" | 调用有活 API 创建岗位，返回岗位 ID 和链接 | `youhuo-job-api` MCP |
| **候选人筛选** | `candidate-screener` | "筛简历""推荐人选""匹配候选人" | 根据岗位要求从有活人才库中筛选匹配候选人 | `youhuo-talent-api` MCP |
| **劳动力调度** | `workforce-dispatcher` | "派工""调度""排班""分配工人" | 将已确认的候选人分配到具体工位/时段/地点 | `youhuo-dispatch-api` MCP |
| **履约跟踪** | `order-tracker` | "查进度""用工状态""履约情况" | 查询岗位执行状态、工人到岗/完工/结算进度 | `youhuo-order-api` MCP |
| **用工结算** | `settlement-manager` | "结算""付款""工费""薪资" | 发起/确认用工结算，生成结算单 | `youhuo-finance-api` MCP |

### 1.2 C 端 Skill 功能矩阵

| 功能模块 | Skill 名称 | 触发词 | 核心动作 | MCP 依赖 |
|:---|:---|:---|:---|:---|
| **简历生成与发布** | `resume-publisher` | "发简历""发布求职""找工作""投简历" | 解析用户提供的信息，生成结构化简历，一键发布到有活平台 | `youhuo-resume-api` MCP |
| **岗位匹配与推荐** | `job-matcher` | "推荐岗位""适合我的工作""有什么活" | 根据用户画像/简历，从有活岗位库中匹配推荐 | `youhuo-job-search-api` MCP |
| **求职状态管理** | `application-tracker` | "投递状态""面试通知""求职进展" | 查询用户投递记录、面试邀请、录用通知 | `youhuo-application-api` MCP |
| **多平台分发** | `resume-distributor` | "多平台投递""一键分发""同步简历" | 将简历同步到多个招聘平台（有活+外部） | `youhuo-distribute-api` MCP |

### 1.3 MCP Server 清单

所有 Skill 的底层执行依赖统一的 MCP Server 集群，按领域拆分为 7 个独立 MCP Server：

```
youhuo-mcp-servers/
├── youhuo-job-api/          # 岗位 CRUD + 搜索
├── youhuo-talent-api/       # 人才库查询 + 简历解析
├── youhuo-resume-api/       # 简历生成 + 发布 + 更新
├── youhuo-dispatch-api/     # 派工 + 排班 + 调度
├── youhuo-order-api/        # 订单/履约跟踪
├── youhuo-finance-api/      # 结算 + 支付
└── youhuo-distribute-api/   # 多平台分发（适配层）
```

**为什么拆 7 个而不是 1 个？**
- **职责单一**：每个 MCP Server 只负责一个领域，独立迭代、独立部署
- **权限隔离**：B 端用户只加载 B 端相关 MCP，C 端同理
- **计费独立**：未来按 Token/调用计费时，可以按 Server 粒度定价

---

## 二、架构设计：三层分离

```
┌─────────────────────────────────────────────────────┐
│                   Agent 层（WorkBody 等）              │
│   用户自然语言 → Agent 识别意图 → 选择 Skill 执行      │
└──────────────────────┬──────────────────────────────┘
                       │ 调用
┌──────────────────────▼──────────────────────────────┐
│                  Skill 层（业务编排）                   │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │job-planner│  │resume-publisher│  │workforce-dis │  │
│  │(需求解析) │  │(简历发布)     │  │patcher(调度) │  │
│  └─────┬────┘  └──────┬───────┘  └──────┬────────┘  │
│        │               │                 │            │
│   SKILL.md 定义：                                    │
│   - 触发词 + 描述                                     │
│   - 业务流程（SOP）                                   │
│   - 输出格式                                         │
│   - 安全边界                                         │
└────────┼───────────────┼─────────────────┼─────────┘
         │               │                 │
┌────────▼───────────────▼─────────────────▼─────────┐
│               MCP 层（能力接口）                      │
│                                                      │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │
│  │youhuo-job-api│ │youhuo-talent │ │youhuo-resume│ │
│  │  (岗位操作)  │ │  -api(人才)  │ │  -api(简历) │ │
│  └──────┬───────┘ └──────┬───────┘ └──────┬──────┘ │
│         │                │                │         │
│  MCP 协议：Tools（可执行函数）+ Resources（数据资源）  │
└─────────┼────────────────┼────────────────┼────────┘
          │                │                │
┌─────────▼────────────────▼────────────────▼────────┐
│              有活后端 API（现有系统）                   │
│                                                      │
│   岗位服务 │ 人才服务 │ 简历服务 │ 订单服务 │ 结算服务  │
└─────────────────────────────────────────────────────┘
```

**关键设计原则**：

1. **Skill 层只做编排，不做执行**——业务逻辑留在 SKILL.md（自然语言描述的 SOP），执行能力全部由 MCP Server 提供
2. **MCP 层只做翻译，不做业务**——把有活现有后端 API 翻译成 MCP 协议的 Tools/Resources，不新增业务逻辑
3. **Agent 层只做调度，不做理解**——Agent 根据触发词选择 Skill，Skill 指挥 MCP 执行

---

## 三、MCP Server 开发实战

### 3.1 以 `youhuo-job-api` 为例的完整代码

```python
# youhuo-job-api/server.py
import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("youhuo-job-api")

# 有活后端 API 基地址，从环境变量读取
BASE_URL = os.getenv("YOUHUO_API_BASE", "https://api.youhuo.com/v1")
API_KEY = os.getenv("YOUHUO_API_KEY")


async def _request(method: str, path: str, **kwargs):
    """统一请求封装"""
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method, f"{BASE_URL}{path}", headers=headers, **kwargs
        )
        resp.raise_for_status()
        return resp.json()


# ──── Tools（可执行操作） ────

@mcp.tool()
async def create_job(
    title: str,
    description: str,
    salary_min: int,
    salary_max: int,
    location: str,
    required_skills: list[str],
    headcount: int = 1,
    duration_days: int = 30,
) -> str:
    """创建零工岗位并发布到有活平台。

    Args:
        title: 岗位名称，如"餐厅服务员"
        description: 岗位描述，包含工作内容和要求
        salary_min: 薪资下限（元/天）
        salary_max: 薪资上限（元/天）
        location: 工作地点
        required_skills: 所需技能列表
        headcount: 招聘人数，默认1
        duration_days: 工期天数，默认30
    """
    payload = {
        "title": title,
        "description": description,
        "salary_range": {"min": salary_min, "max": salary_max},
        "location": location,
        "required_skills": required_skills,
        "headcount": headcount,
        "duration_days": duration_days,
    }
    result = await _request("POST", "/jobs", json=payload)
    return f"岗位已发布！岗位ID: {result['job_id']}，链接: {result.get('url', 'N/A')}"


@mcp.tool()
async def search_jobs(
    keyword: str = "",
    location: str = "",
    salary_min: int = 0,
    salary_max: int = 0,
    skills: list[str] | None = None,
    page: int = 1,
    page_size: int = 10,
) -> str:
    """搜索有活平台上的岗位列表。

    Args:
        keyword: 搜索关键词
        location: 工作地点过滤
        salary_min: 薪资下限
        salary_max: 薪资上限
        skills: 技能过滤列表
        page: 页码
        page_size: 每页数量
    """
    params = {"keyword": keyword, "location": location, "page": page, "page_size": page_size}
    if salary_min:
        params["salary_min"] = salary_min
    if salary_max:
        params["salary_max"] = salary_max
    if skills:
        params["skills"] = ",".join(skills)

    result = await _request("GET", "/jobs", params=params)
    jobs = result.get("items", [])

    if not jobs:
        return "未找到匹配的岗位。"

    lines = [f"找到 {result['total']} 个岗位，当前第 {page} 页：\n"]
    for j in jobs:
        lines.append(
            f"- [{j['job_id']}] {j['title']} | {j['location']} | "
            f"{j['salary_range']['min']}-{j['salary_range']['max']}元/天 | "
            f"需{j['headcount']}人"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_job_detail(job_id: str) -> str:
    """获取岗位详细信息。

    Args:
        job_id: 岗位ID
    """
    result = await _request("GET", f"/jobs/{job_id}")
    return (
        f"岗位：{result['title']}\n"
        f"地点：{result['location']}\n"
        f"薪资：{result['salary_range']['min']}-{result['salary_range']['max']}元/天\n"
        f"描述：{result['description']}\n"
        f"状态：{result['status']}\n"
        f"已报名：{result.get('applied_count', 0)}/{result['headcount']}人"
    )


@mcp.tool()
async def close_job(job_id: str, reason: str = "") -> str:
    """关闭/下架岗位。

    Args:
        job_id: 岗位ID
        reason: 关闭原因
    """
    payload = {"action": "close", "reason": reason}
    result = await _request("POST", f"/jobs/{job_id}/action", json=payload)
    return f"岗位 {job_id} 已关闭。"


# ──── Resources（可读数据） ────

@mcp.resource("youhuo://job-categories")
async def job_categories() -> str:
    """获取有活平台的岗位分类目录"""
    result = await _request("GET", "/meta/categories")
    lines = ["有活岗位分类目录：\n"]
    for cat in result.get("categories", []):
        lines.append(f"- {cat['name']}（包含 {cat['count']} 个子类）")
    return "\n".join(lines)


@mcp.resource("youhuo://hot-skills")
async def hot_skills() -> str:
    """获取当前热门技能标签"""
    result = await _request("GET", "/meta/hot-skills")
    lines = ["当前热门技能：\n"]
    for skill in result.get("skills", []):
        lines.append(f"- {skill['name']}（需求量: {skill['demand_count']}）")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 3.2 WorkBuddy 中的 MCP 配置

在 WorkBuddy 客户端中配置 mcp.json：

```json
{
  "mcpServers": {
    "youhuo-job-api": {
      "command": "uvx",
      "args": ["youhuo-job-api"],
      "env": {
        "YOUHUO_API_BASE": "https://api.youhuo.com/v1",
        "YOUHUO_API_KEY": "your-api-key-here"
      }
    },
    "youhuo-talent-api": {
      "command": "uvx",
      "args": ["youhuo-talent-api"],
      "env": {
        "YOUHUO_API_BASE": "https://api.youhuo.com/v1",
        "YOUHUO_API_KEY": "your-api-key-here"
      }
    },
    "youhuo-resume-api": {
      "command": "uvx",
      "args": ["youhuo-resume-api"],
      "env": {
        "YOUHUO_API_BASE": "https://api.youhuo.com/v1",
        "YOUHUO_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**配置级别建议**：
- **用户级**（`~/.workbuddy/mcp.json`）：youhuo-job-api、youhuo-talent-api 等通用能力
- **项目级**（`.workbuddy/mcp.json`）：特定项目的定制化 MCP

---

## 四、Skill 开发实战

### 4.1 `job-planner` Skill — B 端用工规划

```markdown
---
name: job-planner
description: "用工需求解析与岗位规划。当用户提到招人、用工、岗位规划、人力需求、临时工、兼职等场景时自动激活。触发词：招人、用工、岗位规划、人力需求、招工、零工需求"
agent_created: true
---

# job-planner — 用工需求解析与岗位规划

## 核心信条

你是一位专业的劳动力规划师。你帮助企业和个人将模糊的用工需求，转化为结构化的零工岗位方案，并可直接发布到有活平台。

## 强制流程（SOP）

当用户提出用工需求时，严格按以下步骤执行：

### 第一步：需求澄清

- 识别用户的用工意图
- 如果用户描述不够具体，主动追问以下关键要素（缺失才问，不缺失不问）：
  - 岗位类型/工作内容
  - 工作地点
  - 需要人数
  - 工期（开始日期 + 持续时间）
  - 预算范围
  - 特殊技能要求

### 第二步：岗位拆解

- 将用户的自然语言需求，拆解为一个或多个结构化岗位
- 每个岗位包含：title、description、location、salary_min/max、required_skills、headcount、duration_days
- 如果一个需求涉及多个角色（如"开一家奶茶店"需要店员+收银+调配师），拆分为多个岗位

### 第三步：方案确认

- 以表格形式呈现拆解后的岗位方案
- 询问用户是否确认、需要调整哪些内容

### 第四步：发布执行

- 用户确认后，逐一调用 `create_job` 工具创建岗位
- 汇总发布结果，返回岗位 ID 和链接

### 第五步：后续跟进建议

- 建议用户使用 `candidate-screener` 筛选候选人
- 建议使用 `workforce-dispatcher` 进行派工
- 提醒关注履约跟踪

## 输出格式

岗位方案表格：

| 序号 | 岗位名称 | 地点 | 人数 | 薪资(元/天) | 工期 | 所需技能 |
|:---|:---|:---|:---|:---|:---|:---|
| 1 | ... | ... | ... | ... | ... | ... |

## 绝对禁止

- 不得虚构薪资数据，必须基于用户输入或追问获取
- 不得跳过确认步骤直接发布岗位
- 不得修改用户明确给出的需求参数
- 未获得 API 权限时，不得尝试调用有活平台接口
```

**安装路径**：`~/.workbuddy/skills/job-planner/SKILL.md`

### 4.2 `resume-publisher` Skill — C 端简历发布

```markdown
---
name: resume-publisher
description: "简历生成与一键发布。当用户提到发简历、发布求职、找工作、投简历、求职登记等场景时自动激活。触发词：发简历、发布求职、找工作、投简历、求职登记、我想找活"
agent_created: true
---

# resume-publisher — 简历生成与一键发布

## 核心信条

你是一位专业的求职助手。你帮助用户将散落的信息整理为结构化简历，并一键发布到有活平台，完成从"对话"到"投递"的闭环。

## 强制流程（SOP）

### 第一步：信息采集

从用户的对话中提取以下信息（缺失则追问）：
- 姓名
- 手机号
- 年龄
- 意向工作类型/岗位
- 期望工作地点
- 期望薪资范围
- 工作经历（公司 + 职位 + 时长）
- 技能标签（如：开车、烹饪、保洁、搬运）

### 第二步：简历结构化

将采集到的信息整理为标准简历格式，呈现给用户确认：

```
👤 姓名：张三
📱 手机：138****1234
🎂 年龄：28岁
🎯 求职意向：餐厅服务员
📍 期望地点：深圳市南山区
💰 期望薪资：200-250元/天

💼 工作经历：
1. XX餐厅 | 服务员 | 2023.06-2024.12
2. YY超市 | 理货员 | 2022.03-2023.05

🏷️ 技能标签：餐饮服务、收银、库存管理
```

### 第三步：确认与发布

- 用户确认信息无误后，调用 `publish_resume` 工具发布
- 返回发布结果和匹配推荐

### 第四步：岗位推荐

- 调用 `search_jobs` 根据用户画像搜索匹配岗位
- 展示 Top 5 推荐岗位
- 询问用户是否需要一键投递

## 绝对禁止

- 不得在未经用户确认的情况下发布简历
- 不得修改用户提供的真实工作经历和技能
- 手机号等隐私信息在展示时脱敏处理
- 不得将用户简历同步到用户未授权的平台
```

---

## 五、落地执行路线图

### Phase 0：基建准备（第 1-2 周）

| 任务 | 产出 | 负责人 |
|:---|:---|:---|
| 梳理有活后端 API 清单 | API 列表文档（含请求/响应 Schema） | 后端 |
| 搭建 MCP 开发脚手架 | Python 模板项目 + FastMCP 依赖 | 后端 |
| 申请 WorkBuddy 开发者账号 | 获得 API Key 和测试环境 | 产品 |
| 编写第一个 MCP Server（youhuo-job-api） | 可运行的 MCP Server + 单元测试 | 后端 |
| 在 WorkBuddy 中验证 MCP 连通性 | 绿灯状态确认 | 测试 |

### Phase 1：B 端核心闭环（第 3-4 周）

| 任务 | 产出 |
|:---|:---|
| 开发 youhuo-talent-api MCP Server | 人才查询 + 简历解析 |
| 开发 youhuo-dispatch-api MCP Server | 派工 + 排班 |
| 开发 job-planner Skill | SKILL.md + 测试验证 |
| 开发 job-publisher Skill | SKILL.md + 测试验证 |
| 开发 candidate-screener Skill | SKILL.md + 测试验证 |
| **端到端测试**：自然语言 → 岗位拆解 → 发布 → 筛选候选人 | 录屏 Demo |

### Phase 2：C 端核心闭环（第 5-6 周）

| 任务 | 产出 |
|:---|:---|
| 开发 youhuo-resume-api MCP Server | 简历 CRUD + 发布 |
| 开发 youhuo-job-search-api MCP Server | 岗位搜索 + 推荐 |
| 开发 resume-publisher Skill | SKILL.md + 测试验证 |
| 开发 job-matcher Skill | SKILL.md + 测试验证 |
| **端到端测试**：自然语言 → 简历生成 → 发布 → 岗位匹配 → 投递 | 录屏 Demo |

### Phase 3：商业化与生态（第 7-8 周）

| 任务 | 产出 |
|:---|:---|
| 开发 youhuo-order-api / youhuo-finance-api MCP | 履约 + 结算 |
| 开发 youhuo-distribute-api MCP | 多平台分发 |
| 打包所有 Skill 到 SkillHub | 审核通过 + 上架 |
| 制定 Token/调用计费方案 | 定价文档 |
| 编写开发者接入文档 | 对外 API 文档 + SDK |

---

## 六、商业重构：抢占"默认执行通道权"

你的第三个洞察最为关键——这不是在做"一个 Skill"，而是在争夺 **Agent 时代的入口级生态位**。

### 6.1 战略行动清单

| 优先级 | 行动 | 时间窗口 | 价值 |
|:---|:---|:---|:---|
| 🔴 P0 | **率先上架 SkillHub**——成为"劳动力交付"分类下第一个可用 Skill | WorkBody 发布后 30 天内 | 先发优势 = 默认选择 |
| 🔴 P0 | **跑通计费逻辑**——按岗位发布数/匹配次数计费 | 同步 | 确立商业模式 |
| 🟡 P1 | **申请腾讯云 MCP 市场入驻**——成为官方推荐 MCP Server | 60 天内 | 信任背书 + 流量 |
| 🟡 P1 | **开放 API Key 自助申请**——降低第三方 Agent 接入门槛 | 同步 | 生态扩展 |
| 🟢 P2 | **构建 Agent-to-Agent 协议**——让其他 Skill 能"雇佣"有活 Skill | 90 天内 | 网络效应 |

### 6.2 计费模型建议

```
┌───────────────────────────────────────────────────┐
│              有活 Skill 计费模型                     │
│                                                    │
│  基础层（免费）：                                   │
│  ├── 岗位搜索 / 简历查看 — 吸引用户                 │
│  └── 热门技能/分类查询 — 免费资源                   │
│                                                    │
│  执行层（按次计费）：                               │
│  ├── 岗位发布 — 1 Token/次                          │
│  ├── 候选人匹配 — 2 Token/次                        │
│  ├── 简历发布 — 1 Token/次                          │
│  └── 多平台分发 — 3 Token/次                         │
│                                                    │
│  增值层（订阅制）：                                 │
│  ├── 用工规划顾问 — 99 Token/月                     │
│  ├── 优先调度权 — 199 Token/月                      │
│  └── 数据看板 — 49 Token/月                         │
└───────────────────────────────────────────────────┘
```

---

## 七、快速上手 Checklist

你现在就可以开始的第一批操作：

- [ ] **5 分钟**：在 WorkBuddy 中打开「插件」→「MCP 服务器」→ 确认配置入口
- [ ] **30 分钟**：用本文 `youhuo-job-api` 示例代码，跑通第一个 MCP Server
- [ ] **1 小时**：编写 `job-planner` 的 SKILL.md，放到 `~/.workbuddy/skills/job-planner/`
- [ ] **2 小时**：在对话中测试「我要招3个餐厅服务员，在深圳，200块一天」能否走通完整链路
- [ ] **本周内**：梳理有活后端 API，确定哪些接口需要封装为 MCP Tools
- [ ] **2 周内**：完成 Phase 0 全部任务，MCP Server 绿灯亮起

---

> **一句话总结**：有活要做的不是"一个能帮人找工作的 Skill"，而是**劳动力交付领域第一个被 Agent 默认调用的执行器官**。速度 > 完美，先上架、先跑通、先占位。

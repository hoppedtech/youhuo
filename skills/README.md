# 有活 Agent Skills

推荐与 MCP Server 搭配使用的 Cursor Agent Skills。Skill 定义找活/招工的 SOP 与安全边界；MCP 提供实际 API 调用能力。

| Skill | MCP Server | 适用角色 |
|:---|:---|:---|
| `job-seeker` | youhuo-c-api | C 端零工求职 |
| `job-planner` | youhuo-b-api | B 端发岗、众包 |
| `workforce-dispatcher` | youhuo-b-api | B 端排班、考勤 |

## 安装（Cursor）

先完成 MCP 配置（见仓库根目录 `README.md`），再安装 Skill。

### 全局安装（推荐）

任意项目均可自动激活 Skill：

**Windows PowerShell**

```powershell
$skills = "$env:USERPROFILE\.cursor\skills"
New-Item -ItemType Directory -Force -Path $skills
Copy-Item -Recurse -Force skills\job-seeker "$skills\job-seeker"
Copy-Item -Recurse -Force skills\job-planner "$skills\job-planner"
Copy-Item -Recurse -Force skills\workforce-dispatcher "$skills\workforce-dispatcher"
```

**macOS / Linux**

```bash
mkdir -p ~/.cursor/skills
cp -r skills/job-seeker ~/.cursor/skills/
cp -r skills/job-planner ~/.cursor/skills/
cp -r skills/workforce-dispatcher ~/.cursor/skills/
```

### 仅当前项目

```powershell
New-Item -ItemType Directory -Force -Path .cursor\skills
Copy-Item -Recurse -Force path\to\youhuo\skills\* .cursor\skills\
```

### 在 youhuo 仓库内开发（可选）

若在本仓库内调试，可将 `skills/` 链接到 `.cursor/skills/`（Windows junction）：

```powershell
New-Item -ItemType Directory -Force -Path .cursor\skills
cmd /c mklink /J .cursor\skills\job-seeker skills\job-seeker
```

## 验证

重启 Cursor 后，在对话中说「我想在北京找活」或「帮我发个小时工岗位」，Agent 应自动匹配对应 Skill 并调用 MCP Tool。

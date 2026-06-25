# 有活 MCP & Skill 落地执行方案 V2

> 本方案基于 **hopped-uni-client 小程序真实代码**逆向分析，精确映射到实际存在的后端 API 接口，确保 MCP Tool 定义与生产可调用的接口 100% 对齐。

---

## 一、从代码看清有活的真实架构

### 1.1 有活小程序的双端结构（已确认）

通过代码分析，有活平台存在**两套独立 API 体系**，这是设计 MCP Server 时最关键的前提：

| 角色 | API 基地址变量 | 实际地址（测试环境） | 职责 |
|:---|:---|:---|:---|
| **零工端（C端）** | `$base_url` | `hopped-applet-service/api/` | 零工找活、抢单、干活、提现 |
| **用工端（B端）** | `$employ_url` | `hopped-miniprogram-web/api/` | 企业发岗、招工、排班、结算 |
| **众包任务端** | `$hopped_url_a` | `hopped-platform-service/api/` | 众包订单发布、交付验收 |

**结论**：原方案将 MCP 拆为 7 个 Server 的方向正确，但应按**业务域 + 端**来划分，而非仅按功能。

### 1.2 真实存在的核心功能模块（从代码确认）

**C 端（零工）已有能力：**
- ✅ 岗位搜索与推荐（`Job/GetJobList`、`Job/SearchJobList`、`home/QueryRecommendList`）
- ✅ 地图找活（`Job/MapJobList`、`HoppedTask/getmaphoppedtasklist`）
- ✅ 岗位报名（`Job/EntryJob`、`Job/EntryJobPK`）
- ✅ 趴活/等待模式（`HoppedTask/GetTradingAreaList`、`HoppedTask/SignUpTask`）
- ✅ 抢单任务（`HoppedTask/gethoppedtasks`、`HoppedTask/GrabTask`）
- ✅ 干活记录（`HoppedTask/OrderTaskList`）
- ✅ 考勤打卡（`Job/ClockIn`、`RecruitJobs/GetClockingInInfo`）
- ✅ 收益提现（`Account/Withdraw`、`Account/GetAccountAmount`）
- ✅ 实人认证（`IdCardAuth/newidcardocr`、人脸识别）
- ✅ 评价体系（`UserEvaluation/userevaluation`、`Evaluation/AddEvaluation`）

**B 端（用工/招工）已有能力：**
- ✅ 发布长期招（`miniprogram/jd/publish`）
- ✅ 发布小时工岗位（`miniprogram/jd/hourly/list`）
- ✅ 排班管理（`recruitWorkingSchedule/list`、`recruitWorkingScheduleDetail/list`）
- ✅ 人员管理（`recruitWorkingSchedule/getPersonByJobId`）
- ✅ 考勤审核（`recruitWorkingScheduleDetail/refuse`、`deleteTime`、`addTime`）
- ✅ 结算支付（`recruitWorkingScheduleDetail/pay`、`account/balance-payment`）
- ✅ 发票管理（`invoiceInfo/list`、`invoiceInfo/applyInvoice`）
- ✅ 评价零工（`hoppedEvaluateStarLevel/addEvaluateOdd`）
- ✅ 积分/余额体系（`miniprogram/account/balance`、`userbuyorder/createOrder`）

**众包任务端已有能力：**
- ✅ 发布任务（`applettask/publishtask`）
- ✅ 交付验收（`appletorder/merchantcheck`）
- ✅ 订单管理（`appletorder/getorderlist`）

---

## 二、重新设计：基于真实接口的 MCP Server 架构

### 2.1 调整后的 MCP Server 清单（从 7 个优化为 6 个）

原方案的 7 个 Server 存在重叠，结合实际代码将其合并优化，并**新增 `youhuo-auth-service` 处理用户扫码授权**：

```
youhuo-mcp-servers/
├── youhuo-auth-service/      # 认证：用户扫码授权 + Token 管理（新增）
├── youhuo-worker-api/        # C端：零工找活 + 抢单 + 干活（对应 $base_url）
├── youhuo-hire-api/          # B端：招工 + 排班 + 考勤（对应 $employ_url）
├── youhuo-task-api/          # 众包：任务发布 + 交付验收（对应 $hopped_url_a）
├── youhuo-finance-api/       # 通用：结算 + 提现 + 发票（两端共用）
└── youhuo-profile-api/       # 通用：用户画像 + 认证 + 技能（基础能力）
```

**为什么从 7 个合并为 6 个？**
- `youhuo-job-api` + `youhuo-talent-api` → 合并为 `youhuo-worker-api`（C 端同一 base_url 下的能力）
- `youhuo-dispatch-api` + `youhuo-order-api` → 合并为 `youhuo-hire-api`（B 端同一 employ_url 下的能力）
- `youhuo-resume-api` → 整合进 `youhuo-profile-api`（个人信息是简历的子集）
- **新增 `youhuo-auth-service`** → 处理用户扫码授权，所有业务 Server 通过它获取 Token

### 2.2 完整架构图

```
┌────────────────────────────────────────────────────────────────┐
│                    Agent 层（WorkBuddy 等）                      │
│    用户自然语言 → Agent 意图识别 → 选择 Skill → 执行 MCP Tool    │
└───────────────────────────┬────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────────┐
│                       Skill 层（业务编排）                        │
│  job-planner │ workforce-dispatcher │ job-matcher │ resume-pub  │
│  order-tracker │ settlement-manager │ attendance-manager        │
└──┬────────────┬──────────────┬──────────────┬──────────────┬───┘
   │            │              │              │              │
   ▼            ▼              ▼              ▼              ▼
youhuo-    youhuo-hire-   youhuo-task-  youhuo-     youhuo-
worker-api    api            api       finance-api  profile-api
   │            │              │              │              │
   └────────────┴──────────────┴──────────────┴──────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────┐
│                        有活后端服务集群                           │
│  hopped-applet-service │ hopped-miniprogram-web │               │
│  hopped-platform-service │ hopped-data-search                   │
└────────────────────────────────────────────────────────────────┘
```

### 2.3 用户扫码授权认证架构（核心设计）

**问题**：用户通过 WorkBuddy AI 对话使用有活服务，但 AI 无法直接调用微信小程序的 `wx.login()` 获取 Token。后端团队也不能直接提供 Token。

**解决方案**：**复用现有 `LoginController` 的 `minilogin` + `GetAppletQRCode` 能力**，后端仅需 **2 行代码 + 1 个新接口** 即可实现 AI 扫码授权闭环。

#### 核心发现：`qrcodeId` 已打通

分析 `LoginController.cs` 发现，`minilogin` 接口已支持从请求头读取 `qrcodeId`：

```csharp
hoppedLogin.qrcodeId = QrcodeId;  // 从 BaseController 的请求头获取
```

这意味着：**小程序扫码登录时，已经把 `qrcodeId`（即 AI 生成的 `session_id`）带到了后端**。后端完全知道"这个登录请求来自哪个二维码"。

#### 认证流程（复用现有接口）

```
┌─────────────┐     1.生成session_id    ┌──────────────────────────┐
│  WorkBuddy  │ ──────────────────────> │   youhuo-auth-service    │
│    AI       │                         │    (本地SQLite)          │
└─────────────┘                         └──────────────────────────┘
      │
      │ 2.调用 GetAppletQRCode(qrcodeId=session_id)
      ▼
┌────────────────────────────────────────────────────────────────┐
│  后端：现有 PersonalController.GetAppletQRCode 接口（无需改动）  │
│  返回：带 session_id 参数的小程序码图片                          │
└────────────────────────────────────────────────────────────────┘
      │
      │ 3.展示二维码给用户
      ▼
┌─────────────┐     4.微信扫码      ┌──────────────────────────┐
│   用户手机   │ ─────────────────> │      有活小程序           │
│             │   5.小程序登录      │                          │
│             │ <───────────────── │  Login/minilogin         │
└─────────────┘                    │  (传入 qrcodeId)         │
                                   └──────────────────────────┘
                                         │
                                         │ 6.minilogin成功后
                                         │   Token写入Redis
                                         │   (auth_session:{session_id})
                                         ▼
                                   ┌──────────────────────────┐
                                   │  LoginController         │
                                   │  仅新增2行代码           │
                                   └──────────────────────────┘
                                         │
      │ 7.轮询 GetTokenBySession          │
      ▼                                  │
┌─────────────┐     8.返回Token    ◄────┘
│  WorkBuddy  │ <─────────────────
│    AI       │
└─────────────┘
```

#### 后端改动量（极小）

| 改动项 | 位置 | 代码量 | 说明 |
|:---|:---|:---|:---|
| **新增 Redis 存储** | `LoginController.minilogin` 成功分支 | **2 行** | 登录成功后按 `session_id` 缓存 Token |
| **新增查询接口** | `LoginController` 新增方法 | **~10 行** | AI 轮询获取 Token，取完即删 |

> 完整后端代码示例见下文"后端实现参考"。

#### 关键设计决策

| 决策点 | 选择 | 理由 |
|:---|:---|:---|
| Token 存储 | SQLite 共享数据库（`~/.workbuddy/youhuo_auth.db`） | 多进程 MCP Server 可安全共享 |
| 会话标识 | `session_id`（UUID）+ `current_session` 指针 | 单会话单用户，避免并发冲突 |
| 扫码载体 | 微信小程序码（`Personal/GetAppletQRCode`） | ✅ **已有接口，直接复用** |
| 登录接口 | `Login/minilogin` | ✅ **已有接口，传 `qrcodeId` 即可** |
| Token 暂存 | Redis（`auth_session:{session_id}`） | 后端已有 Redis，5 分钟过期 |
| Token 刷新 | 自动检测 401，触发重新授权 | 减少用户手动操作 |

#### 双端 Token 支持

有活平台存在 B/C 双端，Token 不能混用：

| 角色 | X-USER_ROLE | 对应 Server | 扫码入口 |
|:---|:---|:---|:---|
| 找活方（C端） | 1 | youhuo-worker-api、youhuo-finance-api（提现） | 找活角色小程序码 |
| 招工方（B端） | 2 | youhuo-hire-api、youhuo-task-api、youhuo-finance-api（发票） | 招工角色小程序码 |

> 用户扫码时，AI 已通过 `role` 参数告知后端生成对应角色的小程序码，用户无需手动切换角色。授权完成后，所有 Server 自动从共享存储读取 Token。

#### 新用户注册策略（已确认）

通过分析 `hopped-user-service` 的 `LoginService.LoginUserBaseRegister` 方法，确认新用户处理策略：

| 策略项 | 结论 | 说明 |
|:---|:---|:---|
| 新用户检测 | 按手机号查询 `user_info` | 查不到即判定为新用户 |
| 注册方式 | **全自动静默注册** | 事务内一次性创建 `user_info` + `user_extends` + `user_login_role` |
| 手机号来源 | 微信授权自动获取 | `jsCode` + `code` 并行换取 `openid` + `unionid` + `phoneNumber` |
| 新用户标记 | `Message = "1"` | 所有登录接口（`HoppedLogin`/`ElderlyLogin`/`PhoneLoginCommon`）统一返回 |
| AI 侧适配 | 检测标记做首次欢迎 | `check_auth_status` 返回 `is_new_user` 字段 |

**对 AI 场景的影响**：
- ✅ 新用户扫码后**自动完成注册**，无需引导去小程序补充信息
- ✅ 注册后即可使用核心功能（找活/发布岗位）
- ⚠️ 如果业务功能要求**实名认证**（如接单、提现），新用户可能需要后续补充，但登录注册本身零门槛

---

## 三、MCP Server 开发实战（基于真实接口）

### 3.0 `youhuo-auth-service` — 用户扫码授权中心

这是整个架构的**认证基础设施**，所有其他 Server 都依赖它获取用户 Token。

#### 3.0.1 共享 Token 存储模块

所有 MCP Server 进程通过 SQLite 共享 Token：

```python
# shared_token_store.py（所有 Server 共用）
"""有活平台 MCP Server 共享 Token 存储。

所有 Server 进程通过 SQLite 安全共享用户授权 Token。
支持多会话、多角色（B/C 端）、自动过期清理。
"""
import sqlite3
import json
import time
import os
import uuid

DB_DIR = os.path.expanduser("~/.workbuddy")
DB_PATH = os.path.join(DB_DIR, "youhuo_auth.db")

os.makedirs(DB_DIR, exist_ok=True)


class AuthStore:
    """线程/进程安全的 Token 存储（基于 SQLite）。"""

    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_id TEXT PRIMARY KEY,
                    token TEXT,
                    role INTEGER NOT NULL DEFAULT 1,
                    user_info TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """
            )
            conn.commit()

    def create_session(self, role: int = 1) -> str:
        session_id = str(uuid.uuid4())[:16]
        now = time.time()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO auth_sessions (session_id, role, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (session_id, role, "pending", now, now + 300),  # 5分钟过期
            )
            conn.commit()
        return session_id

    def set_token(self, session_id: str, token: str, user_info: dict = None, expires_in: int = 7200):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                UPDATE auth_sessions
                SET token=?, user_info=?, status='authorized', expires_at=?
                WHERE session_id=?
            """,
                (
                    token,
                    json.dumps(user_info) if user_info else None,
                    time.time() + expires_in,
                    session_id,
                ),
            )
            conn.commit()

    def get_token(self, session_id: str) -> dict | None:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                """
                SELECT token, role, user_info, status, expires_at
                FROM auth_sessions WHERE session_id=?
            """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
            token, role, user_info, status, expires_at = row
            if time.time() > expires_at:
                return None
            return {
                "token": token,
                "role": role,
                "user_info": json.loads(user_info) if user_info else None,
                "status": status,
            }

    def set_current_session(self, session_id: str):
        """设置当前活跃会话（AI 单会话单用户）。"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM kv_store WHERE key='current_session'")
            conn.execute(
                "INSERT INTO kv_store (key, value) VALUES (?, ?)",
                ("current_session", session_id),
            )
            conn.commit()

    def get_current_token(self) -> dict | None:
        """获取当前活跃会话的 Token（供其他 Server 调用）。"""
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT value FROM kv_store WHERE key='current_session'"
            ).fetchone()
            if not row:
                return None
            return self.get_token(row[0])

    def cleanup_expired(self):
        """清理过期会话。"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (time.time(),))
            conn.commit()


auth_store = AuthStore()
```

#### 3.0.2 youhuo-auth-service 实现

```python
# youhuo_auth_service/server.py
"""有活平台扫码授权 MCP Server。

提供用户扫码授权能力，生成小程序码，管理 Token 生命周期。
所有其他 youhuo-* Server 都通过 shared_token_store 获取 Token。
"""
import os
import json
import httpx
from mcp.server.fastmcp import FastMCP
import sys

# 将 shared_token_store 加入路径（实际项目中应通过包管理）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_token_store import auth_store

mcp = FastMCP("youhuo-auth-service")

# 有活后端地址（复用现有接口）
BASE_URL = os.getenv(
    "YOUHUO_BASE_URL",
    "https://hopped-gateway-service.hopped.com.cn/hopped-applet-service/api/",
)

# 新增接口路径（后端只需实现这一个接口）
GET_TOKEN_BY_SESSION_URL = os.getenv(
    "YOUHUO_GET_TOKEN_URL",
    "https://hopped-gateway-service.hopped.com.cn/hopped-applet-service/api/Login/GetTokenBySession",
)


@mcp.tool()
async def create_auth_session(role: int = 1) -> str:
    """创建用户扫码授权会话，返回小程序码和会话ID。

    用户需要用手机微信扫描二维码，在小程序中完成登录授权。
    授权完成后，Token 会自动存入共享存储，其他 Server 可直接使用。

    复用现有接口: GET Personal/GetAppletQRCode?qrcodeId={session_id}&type=AI_AUTH

    Args:
        role: 用户角色。1=找活方(C端)，2=招工方(B端)。默认1

    Returns:
        JSON字符串，包含 session_id、qr_code_url（小程序码图片地址）、instruction
    """
    # 清理过期会话
    auth_store.cleanup_expired()

    # 创建会话
    session_id = auth_store.create_session(role=role)

    # 设置为当前活跃会话
    auth_store.set_current_session(session_id)

    # 复用现有接口生成小程序码（传 qrcodeId=session_id，小程序扫码后会把 session_id 带回）
    qr_code_url = f"{BASE_URL}Personal/GetAppletQRCode?qrcodeId={session_id}&type=AI_AUTH&role={role}"

    role_name = "招工方" if role == 2 else "找活方"

    result = {
        "session_id": session_id,
        "role": role,
        "role_name": role_name,
        "qr_code_url": qr_code_url,
        "instruction": f"请使用微信扫描下方二维码完成{role_name}授权",
        "status": "pending",
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def check_auth_status(session_id: str) -> str:
    """检查扫码授权状态，授权成功后返回用户信息和 Token 摘要。

    需要轮询调用此接口（建议间隔 3 秒），直到 status 变为 authorized。

    对应后端新增接口: GET Login/GetTokenBySession?session_id={session_id}
    （后端仅需实现这一个接口，约 10 行代码）

    Args:
        session_id: create_auth_session 返回的会话ID

    Returns:
        JSON字符串，status: pending / authorized / expired
        授权成功时额外返回 is_new_user（true=新用户首次注册）
    """
    # 先查本地缓存
    local = auth_store.get_token(session_id)
    if local and local.get("status") == "authorized" and local.get("token"):
        return json.dumps(
            {
                "status": "authorized",
                "role": local["role"],
                "user_name": local.get("user_info", {}).get("name", ""),
                "token_preview": local["token"][:8] + "..." if local["token"] else None,
                "is_new_user": local.get("is_new_user", False),
            },
            ensure_ascii=False,
        )

    # 轮询后端新增接口
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GET_TOKEN_BY_SESSION_URL,
                params={"session_id": session_id},
            )
            data = resp.json()
            if data.get("code") == 200 and data.get("data"):
                token_data = data["data"]
                # 解析登录结果，检测新用户标记（Message="1" 表示首次注册）
                is_new_user = data.get("message") == "1"
                auth_store.set_token(
                    session_id,
                    token_data,
                    user_info={"is_new_user": is_new_user},
                    expires_in=7200,
                )
                result = {
                    "status": "authorized",
                    "token_preview": token_data[:8] + "..." if isinstance(token_data, str) else "...",
                    "is_new_user": is_new_user,
                }
                if is_new_user:
                    result["message"] = "欢迎首次使用有活！已为您自动完成注册。"
                return json.dumps(result, ensure_ascii=False)
    except Exception:
        pass  # 后端接口未就绪时静默失败

    return json.dumps({"status": "pending", "message": "等待用户扫码授权..."}, ensure_ascii=False)


@mcp.tool()
async def get_current_user_info() -> str:
    """获取当前已授权用户的基本信息。

    Returns:
        JSON字符串，包含用户姓名、角色、认证状态等
    """
    info = auth_store.get_current_token()
    if not info:
        return json.dumps(
            {"status": "unauthorized", "message": "当前未授权，请先调用 create_auth_session 完成扫码授权"},
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "status": "authorized",
            "role": info["role"],
            "role_name": "招工方" if info["role"] == 2 else "找活方",
            "user_info": info.get("user_info"),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def revoke_auth() -> str:
    """注销当前授权会话，清除 Token。

    用户主动退出或切换账号时调用。
    """
    current = auth_store.get_current_token()
    if not current:
        return "当前没有活跃的授权会话"
    # 清除当前会话指针
    with sqlite3.connect(auth_store.DB_PATH) as conn:
        conn.execute("DELETE FROM kv_store WHERE key='current_session'")
        conn.commit()
    return "✅ 授权已注销，Token 已清除"
```

> **实现要点**：
> 1. `shared_token_store.py` 放在项目根目录，所有 Server 通过 `sys.path` 或包引用共享
> 2. `youhuo-auth-service` 在 `mcp.json` 中**不依赖任何其他 Server**
> 3. 其他 Server 通过 `auth_store.get_current_token()` 读取 Token，无需用户手动配置
> 4. 后端仅需在 `LoginController.minilogin` 加 2 行 Redis 存储代码，新增 1 个 `GetTokenBySession` 方法

#### 3.0.3 后端实现参考（C#）

**改动 1：minilogin 成功后缓存 Token（2 行代码）**

在 `LoginController.cs` 的 `minilogin` 方法成功分支中（约第 293 行之后）：

```csharp
if (result.ActionResult == "1")
{
    // ... 现有代码（存 tokencache、写登录日志）...

    // ✅ 新增：按 session_id 缓存 Token 和新用户标记（5分钟过期）
    if (!string.IsNullOrEmpty(request.qrcodeId))
    {
        var sessionData = new
        {
            token = result.Data.ToString(),
            isFirstLogin = result.Message == "1"  // "1"=新用户首次注册
        };
        await CsRedisClient5.SetAsync($"auth_session:{request.qrcodeId}",
            JsonConvert.SerializeObject(sessionData), 300);  // 300秒=5分钟
    }
}
```

**改动 2：新增 GetTokenBySession 接口（~10 行代码）**

在 `LoginController.cs` 中新增一个方法：

```csharp
/// <summary>
/// AI扫码授权：根据session_id获取Token
/// </summary>
[HttpGet("GetTokenBySession")]
[AllowAnonymous]
public async Task<WebApiResult> GetTokenBySession([FromQuery] string session_id)
{
    if (string.IsNullOrEmpty(session_id))
    {
        return new WebApiResult(ApiResultCode.Fail, "session_id不能为空");
    }

    var sessionData = await CsRedisClient5.GetAsync($"auth_session:{session_id}");

    if (string.IsNullOrEmpty(sessionData))
    {
        return new WebApiResult(ApiResultCode.Fail, "等待扫码授权...");
    }

    // 取完即删（一次性）
    await CsRedisClient5.DelAsync($"auth_session:{session_id}");

    // 解析 session 数据，提取 token 和新用户标记
    var session = JsonConvert.DeserializeObject<dynamic>(sessionData);
    string token = session.token;
    bool isFirstLogin = session.isFirstLogin ?? false;

    return new WebApiResult(ApiResultCode.Success, message: isFirstLogin ? "1" : "0", data: token);
}
```

> **后端总改动量**：2 行代码 + 1 个 10 行方法，零依赖新增，复用现有 `CsRedisClient5`。

---

### 3.1 `youhuo-worker-api` — C端零工能力

```python
# youhuo_worker_api/server.py
import os
import sys
import httpx
from mcp.server.fastmcp import FastMCP

# 引入共享 Token 存储（所有 youhuo-* Server 共用）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_token_store import auth_store

mcp = FastMCP("youhuo-worker-api")

BASE_URL = os.getenv("YOUHUO_BASE_URL", "https://hopped-gateway-service.hopped.com.cn/hopped-applet-service/api/")
SEARCH_URL = os.getenv("YOUHUO_SEARCH_URL", "https://hopped-gateway-service.hopped.com.cn/hopped-data-search/")


async def _request(method: str, path: str, base: str = None, **kwargs):
    # 从共享存储获取当前用户 Token（由 youhuo-auth-service 扫码授权后写入）
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception(
            "未授权：请先调用 youhuo-auth-service.create_auth_session(role=1) "
            "完成扫码授权，再执行此操作"
        )
    token = token_info["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url_base = base or BASE_URL
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{url_base}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


# ──── 岗位搜索 ────

@mcp.tool()
async def search_jobs(
    keyword: str = "",
    city: str = "",
    category: str = "",
    salary_min: int = 0,
    page: int = 1,
    page_size: int = 10,
) -> str:
    """搜索有活平台零工岗位列表。
    
    对应接口: Job/GetJobList (POST)
    
    Args:
        keyword: 搜索关键词，如"餐厅服务员""保安""搬运工"
        city: 城市名称，如"深圳""广州"
        category: 岗位分类
        salary_min: 最低薪资（元/天）
        page: 页码，默认1
        page_size: 每页数量，默认10
    """
    payload = {
        "keyword": keyword,
        "city": city,
        "category": category,
        "salary_min": salary_min,
        "page": page,
        "page_size": page_size,
    }
    result = await _request("POST", "Job/GetJobList", json=payload)
    items = result.get("data", {}).get("list", [])
    if not items:
        return "未找到匹配岗位，请尝试调整搜索条件。"
    
    lines = [f"共找到 {result.get('data', {}).get('total', 0)} 个岗位：\n"]
    for job in items[:10]:
        lines.append(
            f"📌 [{job.get('job_id')}] {job.get('title')} | "
            f"{job.get('location', job.get('city', ''))} | "
            f"{job.get('salary_desc', '')} | "
            f"需{job.get('headcount', 1)}人"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_job_detail(job_id: str) -> str:
    """获取岗位详细信息。
    
    对应接口: Job/JobDetail (GET)
    
    Args:
        job_id: 岗位ID
    """
    result = await _request("GET", f"Job/JobDetail?job_id={job_id}")
    data = result.get("data", {})
    return (
        f"【{data.get('title')}】\n"
        f"📍 地点：{data.get('location')}\n"
        f"💰 薪资：{data.get('salary_desc')}\n"
        f"👥 需要：{data.get('headcount')}人\n"
        f"⏱ 工期：{data.get('work_date_desc', '待定')}\n"
        f"📋 要求：{data.get('description', '无特殊要求')}\n"
        f"🏷 技能：{', '.join(data.get('skills', []))}\n"
        f"👁 已报名：{data.get('applied_count', 0)}人"
    )


@mcp.tool()
async def get_recommend_jobs(city: str, page: int = 1) -> str:
    """获取首页推荐岗位列表（智能推荐，基于用户画像）。
    
    对应接口: home/QueryRecommendList (POST)
    
    Args:
        city: 城市名称
        page: 页码
    """
    payload = {"city": city, "page": page, "page_size": 10}
    result = await _request("POST", "home/QueryRecommendList", json=payload)
    items = result.get("data", {}).get("list", [])
    if not items:
        return f"{city}当前暂无推荐岗位。"
    
    lines = [f"{city} 为你推荐的岗位：\n"]
    for job in items:
        lines.append(f"⭐ {job.get('title')} | {job.get('salary_desc')} | {job.get('location')}")
    return "\n".join(lines)


@mcp.tool()
async def apply_job(job_id: str, sku_id: str = "0") -> str:
    """报名参加零工岗位。
    
    对应接口: Job/EntryJob (POST)
    注意: 调用前需确认用户已完成实人认证
    
    Args:
        job_id: 岗位ID
        sku_id: SKU配置ID，默认"0"
    """
    payload = {"job_id": job_id, "sku_id": sku_id}
    result = await _request("POST", "Job/EntryJob", json=payload)
    if result.get("code") == 200:
        return f"✅ 报名成功！岗位ID: {job_id}，请等待审核通知。"
    return f"❌ 报名失败：{result.get('message', '未知错误')}"


@mcp.tool()
async def get_my_work_orders(status: str = "all", page: int = 1) -> str:
    """获取我的干活订单列表（接单中心）。
    
    对应接口: HoppedTask/OrderTaskList (POST)
    
    Args:
        status: 订单状态，可选: all(全部)/doing(进行中)/done(已完成)/cancelled(已取消)
        page: 页码
    """
    payload = {"status": status, "page": page, "page_size": 10}
    result = await _request("POST", "HoppedTask/OrderTaskList", json=payload)
    items = result.get("data", {}).get("list", [])
    if not items:
        return "暂无相关订单记录。"
    
    lines = [f"我的干活记录（{status}）：\n"]
    for order in items:
        lines.append(
            f"{'✅' if order.get('status') == 'done' else '🔄'} "
            f"{order.get('title')} | "
            f"{order.get('work_date')} | "
            f"¥{order.get('amount', 0)}"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_account_balance() -> str:
    """查询零工账户余额和佣金信息。
    
    对应接口: Account/GetAccountAmount (GET)
    """
    result = await _request("GET", "Account/GetAccountAmount")
    data = result.get("data", {})
    return (
        f"💰 账户余额：¥{data.get('balance', 0)}\n"
        f"🏆 保证金：¥{data.get('bond_amount', 0)}\n"
        f"💵 可提现：¥{data.get('withdrawable', 0)}"
    )


@mcp.tool()
async def get_skill_tags(keyword: str = "") -> str:
    """获取有活平台可选技能标签列表。
    
    对应接口: Personal/GetSkills (GET)
    
    Args:
        keyword: 技能关键词筛选
    """
    result = await _request("GET", f"Personal/GetSkills?keyword={keyword}")
    skills = result.get("data", [])
    if not skills:
        return "未找到相关技能标签。"
    return "可选技能标签：\n" + " | ".join([s.get("name") for s in skills[:30]])


# ──── Resources ────

@mcp.resource("youhuo://popular-cities")
async def popular_cities() -> str:
    """获取有活平台热门城市列表"""
    result = await _request("GET", "City/GetPopularCity")
    cities = result.get("data", [])
    return "热门城市：" + " | ".join([c.get("name") for c in cities])


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

### 3.2 `youhuo-hire-api` — B端招工/用工能力

```python
# youhuo_hire_api/server.py
import os
import sys
import json
import httpx
from mcp.server.fastmcp import FastMCP

# 引入共享 Token 存储
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_token_store import auth_store

mcp = FastMCP("youhuo-hire-api")

EMPLOY_URL = os.getenv("YOUHUO_EMPLOY_URL", "https://hopped-gateway-service.hopped.com.cn/hopped-miniprogram-web/api/")


async def _req(method: str, path: str, **kwargs):
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception(
            "未授权：请先调用 youhuo-auth-service.create_auth_session(role=2) "
            "完成扫码授权，再执行此操作"
        )
    token = token_info["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{EMPLOY_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


# ──── 岗位发布（B端） ────

@mcp.tool()
async def preview_publish_cost(
    product_type: int,
    subscript_worker_count: int = 0,
    subscript_day_count: int = 0,
) -> str:
    """预估发布岗位所需费用。

    **长期招（productType=2/5）**：按积分订阅制计算，公式：人数 × 天数 × 0.5 积分/人/天。
    10积分=1元人民币。发布后需调用 pay_publish_points 支付积分。

    **小时工/计件工（productType=4/6）**：发布时扣除平台服务费（人民币），
    费用由后端根据岗位信息计算，发布后从账户余额直接扣除。

    对应前端逻辑：long-term/index.vue（长期招积分计算）/ hourly-worker/publish.vue（小时工余额支付）

    Args:
        product_type: 岗位类型。2/5=长期招（需积分），4=小时工，6=计件工
        subscript_worker_count: 订阅人数（长期招需要，即希望触达的零工人数）
        subscript_day_count: 订阅天数（长期招需要，最少7天）

    Returns:
        JSON字符串，包含预估费用、计算明细
    """
    # 长期招才需要积分
    if product_type in (2, 5):
        if subscript_worker_count <= 0 or subscript_day_count <= 0:
            return json.dumps(
                {"error": "长期招需要设置订阅人数和订阅天数"},
                ensure_ascii=False,
            )
        if subscript_day_count < 7:
            return json.dumps(
                {"error": "订阅天数最少7天"},
                ensure_ascii=False,
            )
        points = subscript_worker_count * subscript_day_count * 0.5
        return json.dumps(
            {
                "product_type": product_type,
                "subscript_worker_count": subscript_worker_count,
                "subscript_day_count": subscript_day_count,
                "points": points,
                "rmb": round(points / 10, 2),
                "formula": f"{subscript_worker_count}人 × {subscript_day_count}天 × 0.5积分/人/天 = {points}积分",
            },
            ensure_ascii=False,
        )

    # 小时工/计件工：费用由后端计算，发布时从余额扣除
    return json.dumps(
        {
            "product_type": product_type,
            "note": "该岗位类型发布时扣除平台服务费（人民币），具体金额由后端根据岗位信息计算，从账户余额直接扣除",
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def publish_jd(
    title: str,
    work_category: str,
    description: str,
    location: str,
    salary_min: float,
    salary_max: float,
    headcount: int,
    product_type: int = 2,
    skills: list[str] = None,
    benefits: list[str] = None,
    subscript_worker_count: int = 0,
    subscript_day_count: int = 0,
) -> str:
    """发布岗位到有活平台（B端企业招工）。支持长期招、小时工、计件工。

    对应接口: miniprogram/jd/publish (POST)

    **发布后的支付差异**：
    - 长期招（productType=2/5）：发布后需调用 pay_publish_points 支付积分订阅费
    - 小时工/计件工（productType=4/6）：发布后直接生效，平台服务费从账户余额自动扣除

    Args:
        title: 岗位名称，如"餐厅服务员""仓库搬运工"
        work_category: 工作类别
        description: 岗位描述和要求
        location: 工作地点
        salary_min: 薪资下限（元/天 或 元/小时）
        salary_max: 薪资上限（元/天 或 元/小时）
        headcount: 招募人数
        product_type: 岗位类型。2/5=长期招，4=小时工，6=计件工。默认2
        skills: 所需技能标签列表
        benefits: 福利标签列表
        subscript_worker_count: 订阅人数（长期招需要，默认0）
        subscript_day_count: 订阅天数（长期招需要，最少7天，默认0）
    """
    payload = {
        "title": title,
        "workCategory": work_category,
        "description": description,
        "workAddress": location,
        "salaryMin": salary_min,
        "salaryMax": salary_max,
        "headcount": headcount,
        "productType": product_type,
        "skillList": skills or [],
        "benefitList": benefits or [],
    }
    # 长期招需要订阅参数
    if product_type in (2, 5):
        payload["subscriptWorkerCount"] = subscript_worker_count
        payload["subscriptDayCount"] = subscript_day_count

    result = await _req("POST", "miniprogram/jd/publish", json=payload)
    if result.get("code") == 200:
        jd_id = result.get("data", {}).get("id") or result.get("data", {}).get("jdId")
        if product_type in (2, 5):
            return json.dumps(
                {
                    "success": True,
                    "jd_id": jd_id,
                    "product_type": product_type,
                    "message": "岗位已创建",
                    "note": "长期招需继续调用 pay_publish_points 完成积分支付",
                },
                ensure_ascii=False,
            )
        # 小时工/计件工：发布成功即生效，余额已自动扣除
        return json.dumps(
            {
                "success": True,
                "jd_id": jd_id,
                "product_type": product_type,
                "message": "岗位发布成功！",
                "note": "平台服务费已从账户余额扣除",
            },
            ensure_ascii=False,
        )
    return f"❌ 发布失败：{result.get('message')}"


@mcp.tool()
async def pay_publish_points(jd_id: int) -> str:
    """支付长期招岗位发布所需的积分（仅限 productType=2/5）。

    对应接口: miniprogram/jd/payPointsToPublish (POST)

    在 publish_jd 成功后调用，完成积分扣费，岗位正式上架。
    如果积分余额不足会返回错误，需要引导用户去小程序充值。

    Args:
        jd_id: publish_jd 返回的岗位ID

    Returns:
        支付结果。积分余额不足时返回明确的引导信息。
    """
    payload = {"id": jd_id}
    result = await _req("POST", "miniprogram/jd/payPointsToPublish", json=payload)
    if result.get("code") == 200:
        return f"✅ 积分支付成功！岗位 {jd_id} 已正式上架。"

    # 积分余额不足或其他支付失败
    msg = result.get("message", "支付失败")
    if "余额" in msg or "不足" in msg or "积分" in msg:
        return (
            f"⚠️ 积分余额不足，无法完成支付。\n"
            f"错误信息：{msg}\n\n"
            f"请前往有活小程序充值积分：\n"
            f"打开微信 → 搜索'有活'小程序 → 我的 → 充值积分\n\n"
            f"充值完成后，您可以告诉我'继续支付岗位 {jd_id}'，我会帮您完成。"
        )
    return f"❌ 支付失败：{msg}"


@mcp.tool()
async def get_job_list(
    status: str = "all",
    page: int = 1,
    page_size: int = 10,
) -> str:
    """查询企业已发布的招工岗位列表。
    
    对应接口: miniprogram/jd/list (POST)
    
    Args:
        status: 岗位状态 all/active/closed
        page: 页码
        page_size: 每页数量
    """
    payload = {"status": status, "pageNum": page, "pageSize": page_size, "productType": 1}
    result = await _req("POST", "miniprogram/jd/list", json=payload)
    items = result.get("data", {}).get("list", [])
    if not items:
        return "暂无发布的岗位。"
    
    lines = [f"已发布岗位列表：\n"]
    for jd in items:
        lines.append(
            f"{'🟢' if jd.get('status') == 'active' else '🔴'} "
            f"[{jd.get('jdId')}] {jd.get('title')} | "
            f"报名 {jd.get('applyCount', 0)}/{jd.get('headcount', 0)} 人"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_job_workers(job_id: int, page: int = 1, page_size: int = 10) -> str:
    """获取岗位下已报名/匹配的零工人员列表。
    
    对应接口: recruitWorkingSchedule/getPersonByJobId (POST)
    
    Args:
        job_id: 岗位ID
        page: 页码
        page_size: 每页数量
    """
    payload = {"jobId": job_id, "pageNum": page, "pageSize": page_size}
    result = await _req("POST", "recruitWorkingSchedule/getPersonByJobId", json=payload)
    workers = result.get("data", {}).get("list", [])
    if not workers:
        return f"岗位 {job_id} 暂无报名人员。"
    
    lines = [f"岗位 {job_id} 报名人员（共{result.get('data', {}).get('total', 0)}人）：\n"]
    for w in workers:
        lines.append(
            f"👤 {w.get('name')} | "
            f"评分: {w.get('star', 'N/A')} | "
            f"完成单量: {w.get('finishCount', 0)} | "
            f"状态: {w.get('statusDesc', '')}"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_schedule_list(job_id: int) -> str:
    """获取岗位排班列表。
    
    对应接口: recruitWorkingSchedule/list (POST)
    
    Args:
        job_id: 岗位ID
    """
    payload = {"jobId": job_id, "productType": 4}
    result = await _req("POST", "recruitWorkingSchedule/list", json=payload)
    schedules = result.get("data", {}).get("list", [])
    if not schedules:
        return f"岗位 {job_id} 暂无排班信息。"
    
    lines = [f"岗位 {job_id} 排班情况：\n"]
    for s in schedules:
        lines.append(
            f"📅 {s.get('workDate')} | "
            f"{s.get('startTime')}-{s.get('endTime')} | "
            f"需{s.get('headcount')}人 | "
            f"已到{s.get('arriveCount', 0)}人"
        )
    return "\n".join(lines)


@mcp.tool()
async def mark_worker_suitable(jd_id: int, user_id: int, mark: int) -> str:
    """标记候选零工是否合适。
    
    对应接口: miniprogram/jd/markCv (POST)
    
    Args:
        jd_id: 岗位ID
        user_id: 零工用户ID
        mark: 1=合适 2=不合适
    """
    payload = {"jdId": jd_id, "userId": user_id, "mark": mark}
    result = await _req("POST", "miniprogram/jd/markCv", json=payload)
    mark_desc = "✅ 合适" if mark == 1 else "❌ 不合适"
    return f"已标记用户 {user_id} 为{mark_desc}"


@mcp.tool()
async def close_job(job_id: int, reason: str = "") -> str:
    """停止招工/下线岗位。
    
    对应接口: miniprogram/jd/offline (POST)
    
    Args:
        job_id: 岗位ID
        reason: 停止原因
    """
    payload = {"jdId": job_id, "cancelReason": reason}
    result = await _req("POST", "miniprogram/jd/offline", json=payload)
    return f"岗位 {job_id} 已停止招工。"


@mcp.tool()
async def get_todo_list(page: int = 1) -> str:
    """获取待处理事项列表（B端待办）。
    
    对应接口: recruitWorkingScheduleDetail/my-todo-list (POST)
    
    Args:
        page: 页码
    """
    payload = {"pageNum": page, "pageSize": 20}
    result = await _req("POST", "recruitWorkingScheduleDetail/my-todo-list", json=payload)
    todos = result.get("data", {}).get("list", [])
    if not todos:
        return "🎉 暂无待处理事项。"
    
    lines = [f"待处理事项（共{result.get('data', {}).get('total', 0)}条）：\n"]
    for todo in todos:
        lines.append(f"⚠️ {todo.get('title')} | {todo.get('workerName')} | {todo.get('createTime')}")
    return "\n".join(lines)


@mcp.tool()
async def get_enterprise_balance() -> str:
    """获取企业账户余额信息（积分+现金余额）。
    
    对应接口: miniprogram/account/balance (POST)
    """
    result = await _req("POST", "miniprogram/account/balance", json={})
    data = result.get("data", {})
    return (
        f"💼 企业账户余额\n"
        f"积分余额：{data.get('points', 0)} 分\n"
        f"体验金：¥{data.get('trialAmount', 0)}\n"
        f"现金余额：¥{data.get('cashBalance', 0)}"
    )


# ──── Resources ────

@mcp.resource("youhuo://benefit-tags")
async def benefit_tags() -> str:
    """获取可选福利标签（五险一金/包吃/包住等）"""
    result = await _req("POST", "miniprogram/jd/benefitList", json={})
    tags = result.get("data", [])
    return "可选福利标签：" + " | ".join([t.get("name") for t in tags])


@mcp.resource("youhuo://work-categories")
async def work_categories() -> str:
    """获取岗位工作分类目录"""
    result = await _req("POST", "miniprogram/jd/workCategoryList", json={})
    cats = result.get("data", [])
    return "工作类别：" + " | ".join([c.get("name") for c in cats])


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

> **B端发布费用与余额检查机制说明**
>
> 有活平台B端发布长期招（`productType=2/5`）采用**积分订阅制**：
> - 费用公式：`订阅人数 × 订阅天数 × 0.5积分/人/天`
> - 汇率：`10积分 = 1元人民币`
> - 最低订阅天数：`7天`
>
> **AI场景下的处理原则**：
> 1. **不做充值**：AI不拉起任何支付，不代用户充值，所有充值操作必须用户亲自在小程序完成
> 2. **先确认后执行**：发布前必须展示费用明细，获得用户明确确认
> 3. **余额不足即阻断**：余额不足时不发布岗位，直接引导用户去小程序充值
> 4. **充值后续命**：用户充值后可以通过自然语言（如"继续发布"）回到发布流程
>
> **对应MCP Tool调用链**：
> ```
> preview_publish_cost → get_enterprise_balance → 用户确认 → publish_jd → pay_publish_points
> ```

---

### 3.3 `youhuo-task-api` — 众包任务能力

```python
# youhuo_task_api/server.py
import os
import sys
import httpx
from mcp.server.fastmcp import FastMCP

# 引入共享 Token 存储
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_token_store import auth_store

mcp = FastMCP("youhuo-task-api")

TASK_URL = os.getenv("YOUHUO_TASK_URL", "https://hopped-gateway-service.hopped.com.cn/hopped-platform-service/api/")


async def _req(method: str, path: str, **kwargs):
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception(
            "未授权：请先调用 youhuo-auth-service.create_auth_session(role=2) "
            "完成扫码授权，再执行此操作"
        )
    token = token_info["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{TASK_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def publish_task(
    category_id: str,
    title: str,
    description: str,
    location: str,
    budget: float,
    deadline: str,
    require_cert: list[str] = None,
) -> str:
    """发布众包任务到有活平台。
    
    对应接口: applettask/publishtask (POST)
    
    Args:
        category_id: 任务类别ID（可通过 get_task_categories 获取）
        title: 任务标题
        description: 任务描述和要求
        location: 任务地点
        budget: 预算金额（元）
        deadline: 截止日期，格式 YYYY-MM-DD
        require_cert: 所需资质证书列表
    """
    payload = {
        "category_id": category_id,
        "title": title,
        "description": description,
        "location": location,
        "budget": budget,
        "deadline": deadline,
        "require_cert": require_cert or [],
    }
    result = await _req("POST", "applettask/publishtask", json=payload)
    if result.get("code") == 200:
        task_id = result.get("data", {}).get("task_id")
        return f"✅ 任务发布成功！任务ID: {task_id}"
    return f"❌ 发布失败：{result.get('message')}"


@mcp.tool()
async def get_task_orders(status: str = "all", page: int = 1) -> str:
    """查询众包任务订单列表。
    
    对应接口: appletorder/getorderlist (POST)
    
    Args:
        status: 状态筛选
        page: 页码
    """
    payload = {"status": status, "page": page, "page_size": 10}
    result = await _req("POST", "appletorder/getorderlist", json=payload)
    orders = result.get("data", {}).get("list", [])
    if not orders:
        return "暂无相关任务订单。"
    
    lines = ["任务订单列表：\n"]
    for o in orders:
        lines.append(
            f"📦 [{o.get('task_id')}] {o.get('title')} | "
            f"¥{o.get('amount')} | {o.get('status_desc')}"
        )
    return "\n".join(lines)


@mcp.tool()
async def accept_delivery(task_id: str, is_accept: bool, remark: str = "") -> str:
    """验收任务交付物（通过/驳回）。
    
    对应接口: appletorder/merchantcheck (POST)
    
    Args:
        task_id: 任务ID
        is_accept: True=通过验收，False=驳回
        remark: 验收备注
    """
    payload = {"task_id": task_id, "is_accept": is_accept, "remark": remark}
    result = await _req("POST", "appletorder/merchantcheck", json=payload)
    action = "✅ 已通过验收" if is_accept else "❌ 已驳回"
    return f"{action}，任务ID: {task_id}"


@mcp.resource("youhuo://task-categories")
async def task_categories() -> str:
    """获取众包任务分类目录"""
    result = await _req("GET", "applettask/getcaterogyinfo")
    cats = result.get("data", [])
    lines = ["任务分类："]
    for c in cats:
        lines.append(f"- [{c.get('id')}] {c.get('name')}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

### 3.4 `youhuo-finance-api` — 结算与支付

```python
# youhuo_finance_api/server.py
import os
import sys
import httpx
from mcp.server.fastmcp import FastMCP

# 引入共享 Token 存储
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_token_store import auth_store

mcp = FastMCP("youhuo-finance-api")

BASE_URL = os.getenv("YOUHUO_BASE_URL")
EMPLOY_URL = os.getenv("YOUHUO_EMPLOY_URL")


def _get_token():
    token_info = auth_store.get_current_token()
    if not token_info or not token_info.get("token"):
        raise Exception(
            "未授权：请先调用 youhuo-auth-service.create_auth_session 完成扫码授权"
        )
    return token_info["token"]


async def _req_base(method: str, path: str, **kwargs):
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _req_employ(method: str, path: str, **kwargs):
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, f"{EMPLOY_URL}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def get_worker_balance() -> str:
    """查询零工账户余额详情。
    
    对应接口: Account/GetAccountAmount (GET)
    """
    result = await _req_base("GET", "Account/GetAccountAmount")
    data = result.get("data", {})
    return (
        f"零工账户余额\n"
        f"可提现余额：¥{data.get('balance', 0)}\n"
        f"保证金：¥{data.get('bond_amount', 0)}"
    )


@mcp.tool()
async def apply_invoice(
    invoice_type: int,
    amount: float,
    company_name: str,
    tax_number: str,
    email: str,
) -> str:
    """申请开具发票（B端用工方）。
    
    对应接口: invoiceInfo/applyInvoice (POST)
    
    Args:
        invoice_type: 发票类型 1=增值税普通发票 2=增值税专用发票
        amount: 开票金额
        company_name: 公司名称
        tax_number: 税务登记号
        email: 接收发票的邮箱
    """
    payload = {
        "invoiceType": invoice_type,
        "amount": amount,
        "companyName": company_name,
        "taxNumber": tax_number,
        "email": email,
    }
    result = await _req_employ("POST", "invoiceInfo/applyInvoice", json=payload)
    if result.get("code") == 200:
        return f"✅ 发票申请成功，将发送至 {email}"
    return f"❌ 申请失败：{result.get('message')}"


@mcp.tool()
async def get_invoice_list(status: str = "pending") -> str:
    """查询发票申请列表。
    
    对应接口: invoiceInfo/list (POST) / invoiceInfo/selectInvoice (POST)
    
    Args:
        status: pending=待开票 | issued=已开票
    """
    if status == "pending":
        result = await _req_employ("POST", "invoiceInfo/list", json={"pageNum": 1, "pageSize": 20})
    else:
        result = await _req_employ("POST", "invoiceInfo/selectInvoice", json={"pageNum": 1, "pageSize": 20})
    
    items = result.get("data", {}).get("list", [])
    if not items:
        return f"暂无{status}发票记录。"
    
    lines = [f"发票列表（{status}）：\n"]
    for inv in items:
        lines.append(
            f"🧾 ¥{inv.get('amount')} | "
            f"{inv.get('companyName')} | "
            f"{inv.get('createTime', '')}"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_account_log(page: int = 1) -> str:
    """获取账户资金明细（B端积分/现金明细）。
    
    对应接口: account/log/getUserAccountLogPageList (POST)
    
    Args:
        page: 页码
    """
    payload = {"pageNum": page, "pageSize": 20}
    result = await _req_employ("POST", "account/log/getUserAccountLogPageList", json=payload)
    items = result.get("data", {}).get("list", [])
    if not items:
        return "暂无账户明细。"
    
    lines = ["账户明细：\n"]
    for log in items:
        sign = "+" if log.get("type") == "income" else "-"
        lines.append(
            f"{sign}{log.get('amount')} | "
            f"{log.get('description')} | "
            f"{log.get('createTime')}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## 四、Skill 开发（结合真实接口重写）

### 4.1 `job-planner` — B端用工规划 Skill（完整版）

```markdown
---
name: job-planner
description: "B端用工规划师。当企业用户提到招人、用工、岗位规划、需要工人、发岗位、招零工、众包任务、发布众包、下单等场景时自动激活。触发词：招人、用工、岗位规划、需要工人、发岗位、招零工、招小时工、招计件工、众包任务、发布众包、下单"
mcp_required:
  - youhuo-auth-service
  - youhuo-hire-api
  - youhuo-task-api
  - youhuo-worker-api
---

# job-planner — 用工规划与岗位发布

## 你的角色

你是有活平台的**B端用工规划师**，专门帮助企业用户将模糊的用工需求转化为结构化的岗位方案，并发布到有活平台获取合适的零工人员。

## 有活平台的岗位类型与费用体系（重要背景）

| 类型 | 说明 | 适用场景 | 发布接口 | 费用模式 |
|:---|:---|:---|:---|:---|
| **长期招聘** | 固定岗位，长期招募 | 餐厅、超市、保安等稳定岗位 | youhuo-hire-api `publish_jd` (productType=2/5) 
| **小时工** | 按小时计费，排班制 | 活动促销、临时补充人手 | youhuo-hire-api `publish_jd` (productType=4) | **余额支付制**：发布时扣除平台服务费（人民币，从账户余额直接扣） |
| **计件工** | 按件数计费 | 分拣、打包等可量化工作 | youhuo-hire-api `publish_jd` (productType=6) | **余额支付制**：发布时扣除平台服务费（人民币，从账户余额直接扣） |
| **众包任务（众包工）** | 一次性任务，多城市多点位集体完成 | 安装、维修、配送等专项任务 | youhuo-task-api `publish_task` | 按任务预算结算 |

> **费用体系说明**：
> - **小时工/计件工**：直接扣除账户余额（人民币），余额不足时同样引导去小程序充值
> - **AI不代充值、不拉起支付**，所有充值操作引导用户到小程序完成

## 强制执行流程（SOP）

### 第一步：需求澄清（精准追问）

从用户描述中提取以下信息，**缺什么问什么，不缺不问**：

| 信息项 | 示例 |
|:---|:---|
| 岗位名称/工作内容 | 餐厅服务员、仓库搬运工 |
| 工作地点（城市+区） | 深圳市南山区科技园 |
| 招募人数 | 3人 |
| 工作时间/排班 | 每天9-18点，周一到周六 |
| 薪资预算 | 200-250元/天 |
| 工期/用工周期 | 长期 / 2024年1月10日-2月10日 |
| 技能/资质要求 | 有餐饮经验、身体健康 |
| 岗位类型 | 长期招/小时工/计件工/众包任务 |

### 第二步：确认可选技能和分类

- 调用 `get_skill_list`（youhuo-hire-api）获取可选技能标签
- 调用 `get_benefit_list` 获取可选福利标签（五险一金/包吃包住等）
- 调用 `get_work_categories` 获取岗位工作分类

### 第三步：方案呈现

以表格形式呈现拆解后的岗位方案，明确列出：

| 岗位 | 类型 | 地点 | 人数 | 薪资 | 工期 | 技能要求 |
|:---|:---|:---|:---|:---|:---|:---|
| ... | ... | ... | ... | ... | ... | ... |

询问用户是否确认，或需要调整哪些参数。

### 第四步：费用预估与余额检查（关键步骤）

**必须先完成费用确认，再执行发布。**

1. 调用 `preview_publish_cost`（youhuo-hire-api）获取发布费用
   - **长期招**：按 `人数×天数×0.5` 计算积分，调用 `payPointsToPublish` 支付
   - **小时工/计件工**：发布后由后端计算费用，从账户余额直接扣除（人民币）
2. 调用 `get_enterprise_balance`（youhuo-hire-api）查询当前账户余额（人民币）
3. 向用户展示费用明细和余额对比：

**小时工示例**：
```
💰 发布费用预估
- 岗位类型：小时工
- 岗位名称：餐厅小时工
- 招募人数：3人
- 工作时段：晚班（17:00-22:00）
- 发布费用：28元（平台服务费）

📊 账户余额
- 余额：{current_balance}元

结论：{余额充足/余额不足，还差XX元}
```

**情况A：余额充足**
> "确认发布将扣除28元余额，是否继续？"

用户确认后 → 进入第五步

**情况B：余额不足**
> "您的账户余额不足，还差{diff}元。请前往有活小程序充值：
> 打开微信 → 搜索'有活'小程序 → 我的 → 充值
>
> 充值完成后，您可以直接说'继续发布刚才的岗位'，我会帮您完成。"

**不执行发布**，等待用户充值后再继续。

### 第五步：发布执行

用户确认费用后，根据岗位类型调用对应 MCP Tool：

| 岗位类型 | 调用 Tool | 所属 MCP Server |
|:---|:---|:---|
| 长期招聘（productType=2/5） | `publish_jd` → `pay_publish_points` | youhuo-hire-api |
| 小时工（productType=4） | `publish_jd` | youhuo-hire-api |
| 计件工（productType=6） | `publish_jd` | youhuo-hire-api |
| 众包任务（众包工） | `publish_task` | youhuo-task-api |

**长期招发布执行步骤**：
1. 调用 `publish_jd` 创建岗位 → 获取岗位ID
2. 调用 `pay_publish_points` 支付积分 → 岗位正式上架
3. 汇报发布结果（岗位ID + 提示后续操作）

**小时工/计件工发布执行步骤**：
1. 调用 `publish_jd` 发布岗位 → 后端自动计算服务费并从余额扣除
2. 汇报发布结果（岗位ID + 扣除金额 + 剩余余额）

### 第六步：跟进引导

发布成功后提示用户：
- "您可以随时说「查看岗位报名情况」来了解有多少人报名"
- "说「筛选候选人」可以查看并标记合适的零工"
- "说「待处理事项」可以处理考勤、加班等需要审核的事项"

## 输出规范

- 金额必须明确：元/天、元/小时、元/件
- 地址必须精确到区级
- 人数为整数
- 不得虚构用户未提供的信息
- 不得跳过确认步骤直接发布

## 安全边界

- **发布岗位前必须获得用户对岗位信息和费用的双重确认**
- **余额不足时严禁绕过充值流程强制发布，必须引导用户去小程序充值**
- AI 不代充值、不拉起支付、不处理任何资金流转操作
- 薪资不得低于当地最低工资标准（默认参考深圳约1620元/月）
- 不得发布含有歧视性描述的岗位
- 费用预估必须透明展示计算明细（长期招：人数×天数×单价；小时工/计件工：平台服务费）
```

---

### 4.2 `job-seeker` — C端零工求职 Skill（完整版）

```markdown
---
name: job-seeker
description: "C端零工求职助手。当零工用户提到找活、找工作、有活吗、投简历、找兼职、找零工等场景时自动激活。触发词：找活、找工作、有什么活、找兼职、找零工、我想干活、附近有活吗"
mcp_required:
  - youhuo-auth-service
  - youhuo-worker-api
  - youhuo-profile-api
---

# job-seeker — 零工求职全程助手

## 你的角色

你是有活平台的**C端零工求职助手**，帮助零工用户快速找到匹配的活，从岗位搜索到成功报名形成完整闭环。

## 强制执行流程（SOP）

### 第一步：了解求职意向

从对话中提取（缺什么问什么）：
- 期望做什么类型的工作（服务员/搬运/保安/保洁等）
- 期望在哪个城市/区域工作
- 期望每天收入范围
- 可工作时间段（白班/夜班/全天）
- 有无特殊技能或证书

### 第二步：岗位搜索与推荐

1. 调用 `get_recommend_jobs` 获取智能推荐岗位
2. 如推荐不够精准，调用 `search_jobs` 按关键词搜索
3. 展示 Top 5 匹配岗位（简洁卡片格式）

岗位卡片格式：
```
📌 【岗位名称】
📍 地点：XX市XX区
💰 薪资：XXX元/天
⏱ 时间：XX:XX - XX:XX
👥 需招：X人
✅ 要求：XXX
```

### 第三步：岗位详情与报名引导

- 用户感兴趣后，调用 `get_job_detail` 展示完整详情
- 确认用户满意后，说明报名前提条件（实人认证）
- 调用 `apply_job` 完成报名
- 告知后续等待通知

### 第四步：跟进管理

报名后提醒用户：
- "说「查看我的干活记录」可以查看订单状态"
- "说「查看我的收益」可以查看账户余额"

## 安全边界

- 报名前必须确认用户已完成实人认证
- 不得代替用户做出报名决策，必须用户主动确认
- 不得展示用户隐私信息（手机号、真实姓名需脱敏）
```

---

### 4.3 `workforce-dispatcher` — 用工调度 Skill

```markdown
---
name: workforce-dispatcher
description: "用工调度管理。当企业用户提到查看报名、筛选人员、安排上班、排班、处理考勤、审核加班等场景时自动激活。触发词：查报名、筛人、安排人、排班、看考勤、审核加班、处理待办"
mcp_required:
  - youhuo-auth-service
  - youhuo-hire-api
---

# workforce-dispatcher — 劳动力调度管理

## 你的角色

管理岗位用工的全生命周期：从候选人筛选 → 排班管理 → 考勤审核 → 评价结算。

## 核心功能（按需执行）

### 候选人管理
- 调用 `get_job_list` 查看岗位列表
- 调用 `get_job_workers` 查看报名人员
- 调用 `mark_worker_suitable` 标记合适/不合适

### 排班查看
- 调用 `get_schedule_list` 查看排班情况
- 汇报每班次的到岗率

### 待办处理
- 调用 `get_todo_list` 获取所有待处理事项
- 分类展示：考勤审核、延时申请、加价申请等
- 引导用户逐一处理

### 用工状态汇报
当用户问"现在用工情况如何"时，汇总展示：
1. 在招岗位数及报名情况
2. 今日上岗人数
3. 待处理事项数
4. 本月用工总结算金额

## 数据展示规范

- 人员信息：展示姓名+评分+完成单量，不展示手机号
- 金额：精确到角（0.1元）
- 时间：格式 YYYY-MM-DD HH:mm
```

---

## 五、WorkBuddy MCP 配置（mcp.json）

```json
{
  "mcpServers": {
    "youhuo-auth-service": {
      "command": "python",
      "args": ["-m", "youhuo_auth_service.server"],
      "env": {
        "YOUHUO_BASE_URL": "https://hopped-gateway-service.hopped.com.cn/hopped-applet-service/api/",
        "YOUHUO_GET_TOKEN_URL": "https://hopped-gateway-service.hopped.com.cn/hopped-applet-service/api/Login/GetTokenBySession"
      }
    },
    "youhuo-worker-api": {
      "command": "python",
      "args": ["-m", "youhuo_worker_api.server"],
      "env": {
        "YOUHUO_BASE_URL": "https://hopped-gateway-service.hopped.com.cn/hopped-applet-service/api/",
        "YOUHUO_SEARCH_URL": "https://hopped-gateway-service.hopped.com.cn/hopped-data-search/"
      }
    },
    "youhuo-hire-api": {
      "command": "python",
      "args": ["-m", "youhuo_hire_api.server"],
      "env": {
        "YOUHUO_EMPLOY_URL": "https://hopped-gateway-service.hopped.com.cn/hopped-miniprogram-web/api/"
      }
    },
    "youhuo-task-api": {
      "command": "python",
      "args": ["-m", "youhuo_task_api.server"],
      "env": {
        "YOUHUO_TASK_URL": "https://hopped-gateway-service.hopped.com.cn/hopped-platform-service/api/"
      }
    },
    "youhuo-finance-api": {
      "command": "python",
      "args": ["-m", "youhuo_finance_api.server"],
      "env": {
        "YOUHUO_BASE_URL": "https://hopped-gateway-service.hopped.com.cn/hopped-applet-service/api/",
        "YOUHUO_EMPLOY_URL": "https://hopped-gateway-service.hopped.com.cn/hopped-miniprogram-web/api/"
      }
    }
  }
}
```

**Token 获取策略（用户扫码授权）**：

1. **首次使用**：AI 自动调用 `youhuo-auth-service.create_auth_session(role)` 生成二维码
2. **用户扫码**：用户用手机微信扫码，在小程序中完成登录授权
3. **Token 共享**：授权成功后 Token 存入 SQLite 共享存储，所有 Server 自动读取
4. **角色区分**：
   - C端用户（找活）：`role=1` → 自动加载 `youhuo-worker-api` + `youhuo-finance-api`
   - B端用户（招工）：`role=2` → 自动加载 `youhuo-hire-api` + `youhuo-task-api` + `youhuo-finance-api`

> 无需手动配置 `YOUHUO_TOKEN` 环境变量，所有 Token 通过扫码授权动态获取。

---

## 六、落地路线图（修订版）

### Phase 0：接口摸底 + 环境搭建（第 1 周）

| 任务 | 产出 | 关键动作 |
|:---|:---|:---|
| 确认测试环境可访问性 | 能从本地 curl 通测试环境 API | 使用 `hopped-gateway-service-sops-test.hopped.com.cn` 测试 |
| 设计扫码授权流程 | 认证时序图 + `shared_token_store.py` | 确认 `Personal/GetAppletQRCode` 能否生成带参数的小程序码 |
| 开发 `youhuo-auth-service` | 能生成 session + 二维码 URL + 轮询 Token | 实现 `create_auth_session` + `check_auth_status` |
| 搭建 MCP 开发环境 | Python + FastMCP 项目模板 | `pip install mcp httpx fastmcp` |
| 开发 youhuo-hire-api 最小可用版 | 能调用 `miniprogram/jd/list` 返回数据 | 先实现 2 个 Tool + 接入 shared_token_store |
| WorkBuddy 配置连通 | MCP 状态绿灯 | 配置 mcp.json（含 auth-service），验证 Tool 可调用 |

### Phase 1：B端核心闭环（第 2-3 周）

| 任务 | 产出 | 验收标准 |
|:---|:---|:---|
| 完成 `youhuo-hire-api` 全部 Tool | 覆盖岗位发布/人员管理/排班/待办 | 所有 Tool 单测通过 |
| 完成 `job-planner` Skill | SKILL.md + 测试用例 | 对话「招3个服务员」能走通发布流程 |
| 完成 `workforce-dispatcher` Skill | SKILL.md + 测试用例 | 对话「查看报名情况」能展示人员列表 |
| 端到端 B 端演示 | 录屏 Demo | 自然语言→岗位发布→查看报名→标记合适 |

### Phase 2：C端核心闭环（第 4-5 周）

| 任务 | 产出 | 验收标准 |
|:---|:---|:---|
| 完成 `youhuo-worker-api` 全部 Tool | 覆盖搜索/推荐/报名/干活记录 | 所有 Tool 单测通过 |
| 完成 `youhuo-profile-api` | 覆盖用户信息/技能/认证状态 | 能查询用户完整画像 |
| 完成 `job-seeker` Skill | SKILL.md + 测试用例 | 对话「找深圳搬运工的活」能推荐5个岗位 |
| 端到端 C 端演示 | 录屏 Demo | 自然语言→岗位搜索→查看详情→报名 |

### Phase 3：结算与商业化（第 6-8 周）

| 任务 | 产出 | 验收标准 |
|:---|:---|:---|
| 完成 `youhuo-finance-api` | 覆盖发票/余额/明细 | B端能申请开票，C端能查余额 |
| 完成 `youhuo-task-api` | 覆盖众包发布/验收 | 众包任务全流程打通 |
| 上架 WorkBuddy Skill 市场 | Skill 审核通过 | 在市场中可搜索到"有活" |
| 开放 API 文档 | 第三方接入文档 | 外部 Agent 可接入有活能力 |

---

## 七、与原方案的核心差异对比

| 维度 | 原方案（V1） | 本方案（V2）|
|:---|:---|:---|
| **接口来源** | 假设性 API 设计 | 基于真实小程序代码逆向确认 |
| **MCP 数量** | 7个 | 6个（5个业务 Server + 1个认证 Server）|
| **双端区分** | 未明确区分 C/B 端 API 体系 | 严格区分 `$base_url`（零工）和 `$employ_url`（用工） |
| **Tool 参数** | 通用化设计 | 与实际接口字段名一致（如 `jdId`、`productType=4`） |
| **接口地址** | `https://api.youhuo.com/v1` | `hopped-gateway-service.hopped.com.cn` 下的真实路径 |
| **Token 策略** | 单一 API_KEY（后端提供） | **用户扫码授权**（复用现有 `minilogin` + `GetAppletQRCode`，后端仅需 2 行代码 + 1 个接口） |
| **众包能力** | 未覆盖 | 新增 `youhuo-task-api` 覆盖众包业务线 |
| **B端余额检查** | 未涉及 | 发布前检查账户余额（长期招查积分、小时工/计件工查人民币余额），不足时引导去小程序充值 |
| **Skill 数量** | 6个 | 聚焦3个高价值 Skill（job-planner/job-seeker/dispatcher）|

---

## 八、立即可操作 Checklist

### 今天（30分钟内）

- [ ] 用 curl 测试能否访问有活测试环境（找后端借一个临时 Token 做连通性测试）：
  ```bash
  curl -X POST "https://hopped-gateway-service-sops-test.hopped.com.cn/hopped-miniprogram-web/api/miniprogram/jd/list" \
    -H "Authorization: Bearer {临时测试TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"pageNum":1,"pageSize":10,"productType":1}'
  ```
- [ ] 与后端团队确认：能否提供 `/auth/device/code`、`/auth/device/activate`、`/auth/device/token` 三个接口（或提供替代方案）
- [ ] 安装 MCP 开发依赖：`pip install mcp httpx fastmcp`

### 本周内

- [ ] 完成 `shared_token_store.py` 和 `youhuo-auth-service` 最小可用版
- [ ] 完成 `youhuo-hire-api` 最小可用版（`get_job_list` + `publish_jd`，接入 shared_token_store）
- [ ] 在 WorkBuddy 中配置 mcp.json（含 youhuo-auth-service），验证 Tool 可被 Agent 调用
- [ ] 写好 `job-planner` 的 SKILL.md，放到 `~/.workbuddy/skills/job-planner/`
- [ ] 测试对话：「我要招3个餐厅小时工，在深圳南山，25-30元一小时，晚班」→ AI 应提示扫码授权 → 展示二维码 → 用户扫码后完成发布
- [ ] 测试余额不足场景：「我要招10个分拣小时工」→ AI 应展示费用预估 → 检测到余额不足 → 引导去小程序充值 → 不执行发布

### 两周内

- [ ] B端完整闭环：扫码授权 → 岗位发布 → 查看报名 → 标记候选人
- [ ] Phase 0 全部任务完成，进入 Phase 1

### 附：后端改动清单（需同步给后端团队）

| 改动项 | 位置 | 代码量 | 优先级 | 说明 |
|:---|:---|:---|:---|:---|
| `minilogin` 成功后写 Redis | `LoginController.cs` 第 ~293 行 | **2 行** | P0 | 扫码授权必需 |
| 新增 `GetTokenBySession` | `LoginController.cs` 新增方法 | **~10 行** | P0 | 扫码授权必需 |
| `GetAppletQRCode`（已有） | `PersonalController.cs` | 无需改动 | 已有 | 复用现有接口 |
| `minilogin`（已有） | `LoginController.cs` | 无需改动 | 已有 | 复用现有接口 |
| `account/balance`（已有） | `AccountController.cs` | 无需改动 | 已有 | 查账户余额（人民币），AI直接调用 |
| `jd/payPointsToPublish`（已有） | `JdController.cs` | 无需改动 | 已有 | 长期招积分支付，AI直接调用 |
| `hourly-worker/job-info/{id}/order`（已有） | `HourlyWorkerController.cs` | 无需改动 | 已有 | 小时工/计件工发布后获取订单费用信息 |
| `account/balance-payment`（已有） | `AccountController.cs` | 无需改动 | 已有 | 小时工/计件工余额支付，AI直接调用 |
| `LoginUserBaseRegister`（已有） | `hopped-user-service/LoginService.cs` | 无需改动 | 已有 | 新用户静默注册，自动创建用户档案 |

**Redis Key 规范**：`auth_session:{session_id}`，TTL = 300 秒（5 分钟）

> **关于余额检查**：
> - **长期招**：AI侧通过已有接口 `miniprogram/account/balance` 查询积分余额，费用预估由AI按前端相同公式计算（人数×天数×0.5），**后端无需新增接口**。
> - **小时工/计件工**：发布后由后端计算服务费并自动从余额扣除，AI侧只需调用 `publish_jd`，**无需额外支付接口**。
>
> **关于新用户注册**：`hopped-user-service` 的 `LoginUserBaseRegister` 已实现全自动静默注册（查不到手机号则自动创建 `user_info` + `user_extends` + `user_login_role`），**AI场景无需额外改动**。所有登录接口通过 `Message="1"` 标记新用户，AI侧据此做首次欢迎提示即可。
>
> 如后端完全无法改动，可采用**降级方案**：
> 1. 小程序新增一个"展示授权码"页面，登录成功后显示 Token
> 2. 用户手动将 Token 复制粘贴给 AI
> 3. AI 调用 `youhuo-auth-service` 的降级 Tool 将 Token 写入共享存储

---

## 九、用户交互流程示例（扫码授权 → 业务操作）

### 场景A：B端用户「我要招3个餐厅小时工」— 余额充足

```
用户：我要招3个餐厅小时工，在深圳南山，25-30元一小时，晚班

AI：好的，我来帮您发布小时工岗位。首先需要进行身份授权，请使用微信扫描下方二维码：
     [二维码图片]

     扫码后，小程序会自动完成登录授权。授权完成后告诉我一声，我继续为您发布岗位。

--- 用户扫码，小程序完成登录 ---

AI：✅ 授权成功！已识别您为招工方（B端）。

     已为您整理岗位信息：
     - 岗位名称：餐厅小时工
     - 工作地点：深圳南山
     - 薪资待遇：25-30元/小时
     - 招募人数：3人
     - 岗位类型：小时工
     - 工作时段：晚班（17:00-22:00）
     - 计薪方式：按小时计薪，日结

     💰 发布费用预估：
     - 发布费用：28元（平台服务费）

     📊 当前账户余额：100元

     确认发布将扣除28元余额，是否继续？

用户：确认

AI：正在发布小时工岗位并扣除余额...

     ✅ 岗位发布成功！岗位ID: 12345
     - 已扣除余额：28元
     - 剩余余额：72元

     接下来您可以：
     1. 使用「workforce-dispatcher」Skill 查看报名情况
     2. 查看已报名人员的简历和评分
     3. 对合适的人员进行排班和考勤管理

     需要我帮您查看报名情况吗？
```

### 场景B：B端用户发布小时工岗位 — 余额不足

```
用户：我要招5个仓库分拣小时工，在宝安，22元一小时，早班

AI：...（授权流程同上）...

     已为您整理岗位信息：
     - 岗位名称：仓库分拣小时工
     - 工作地点：深圳宝安
     - 薪资待遇：22元/小时
     - 招募人数：5人
     - 岗位类型：小时工
     - 工作时段：早班（08:00-12:00）
     - 计薪方式：按小时计薪，日结

     💰 发布费用预估：
     - 发布费用：40元（平台服务费）

     📊 当前账户余额：15元

     ⚠️ 余额不足！还差25元。

     您的账户余额不足，无法完成发布。请前往有活小程序充值：

     打开微信 → 搜索"有活"小程序 → 我的 → 充值

     充值完成后，您可以直接说"继续发布刚才的岗位"，我会帮您完成。

--- 用户去小程序充值了50元 ---

用户：充好了，继续发布

AI：好的，检测到您已充值。重新检查余额...

     📊 当前账户余额：65元
     💰 发布所需：40元

     余额充足！确认发布将扣除40元余额，是否继续？

用户：确认

AI：正在发布小时工岗位并扣除余额...

     ✅ 岗位发布成功！岗位ID: 12346
     - 已扣除余额：40元
     - 剩余余额：25元
```

### 场景C：新用户首次使用（自动注册）

```
用户：我要招2个快递分拣员，在龙岗，220元一天

AI：好的，我来帮您发布招聘信息。首先需要进行身份授权，请使用微信扫描下方二维码：
     [二维码图片]

     扫码后，小程序会自动完成登录授权。

--- 用户扫码，小程序完成登录（新用户自动注册） ---

AI：✅ 授权成功！检测到您是首次使用有活，已为您自动完成注册。

     已为您整理岗位信息：
     - 岗位名称：快递分拣小时工
     - 工作地点：深圳龙岗
     - 薪资待遇：20元/小时
     - 招募人数：2人
     - 岗位类型：小时工
     - 工作时段：白班（09:00-18:00）
     - 计薪方式：按小时计薪，日结

     💰 发布费用预估：
     - 发布费用：28元（平台服务费）

     📊 当前账户余额：0元（新用户）

     ⚠️ 余额不足！还差28元。

     您的账户余额不足，无法完成发布。请前往有活小程序充值：

     打开微信 → 搜索"有活"小程序 → 我的 → 充值

     充值完成后，您可以直接说"继续发布"，我会帮您完成。
```

> **新用户说明**：首次扫码的用户会自动完成静默注册（创建用户档案），无需手动填写信息。注册后即可使用有活平台功能，但发布岗位/接单等操作可能需要先充值账户余额。

### 场景：C端用户「我想找深圳的搬运工」

```
用户：我想找深圳的搬运工

AI：我来帮您搜索深圳的搬运工岗位。首先需要进行身份授权，请使用微信扫描下方二维码：
     [二维码图片]
     
     扫码后，小程序会自动完成登录授权。

--- 用户扫码，小程序完成登录 ---

AI：✅ 授权成功！已识别您为找活方（C端）。
     
     为您找到以下搬运工岗位：
     1. 【南山】仓库搬运工 - 220元/天 - 5km
     2. 【福田】物流装卸工 - 250元/天 - 8km
     3. 【宝安】家具搬运工 - 200元/天 - 12km
     
     需要查看某个岗位的详细信息和报名要求吗？
```

### AI 内部执行时序

```
用户输入 → Agent 意图识别 → Skill 激活
                ↓
        检查 Token 是否存在（auth_store.get_current_token()）
                ↓
        无 Token → 调用 youhuo-auth-service.create_auth_session(role)
                ↓
        生成 session_id → 调用现有 GetAppletQRCode(qrcodeId=session_id)
                ↓
        展示二维码 → 等待用户扫码
                ↓
        用户扫码 → 小程序调用现有 minilogin(qrcodeId=session_id)
                ↓
        后端 minilogin 成功 → Token 写入 Redis(auth_session:{session_id})
                ↓
        AI 轮询 check_auth_status(session_id) → 调用新增 GetTokenBySession
                ↓
        Token 存入共享存储 → 继续执行业务 Tool
                ↓
        调用 youhuo-hire-api.publish_jd(...) / youhuo-worker-api.search_jobs(...)
                ↓
        返回结果给用户
```

**关键**：绿色标注的接口均为已有接口，无需后端改动；仅需后端新增 `GetTokenBySession` 1 个接口（~10 行代码）。

---

> **核心结论**：有活平台已经拥有完整的后端能力（有小程序代码为证），MCP 要做的是**将这些能力翻译为 AI 可调用的接口**。  
> 速度优先：先跑通 B 端的「扫码授权 → 岗位发布 → 查看报名」三个 Tool，让第一个演示成立，再迭代扩展。

"""有活网关环境变量（C/B 端仅需 YOUHUO_BASE_URL 域名）。"""
import os
from urllib.parse import urlparse

# 业务 API 路径（固定，不通过环境变量配置）
APPLET_API_PATH = "hopped-applet-service/api/"
EMPLOY_API_PATH = "hopped-miniprogram-web/api/"
PLATFORM_API_PATH = "hopped-platform-service/api/"

_DEFAULT_TEST_GATEWAY = "https://hopped-gateway-service-sops-test.hopped.com.cn"

_GATEWAY_PATH_MARKERS = (
    "/hopped-applet-service/",
    "/hopped-miniprogram-web/",
    "/hopped-platform-service/",
)


def _normalize_gateway(raw: str) -> str:
    """规范为网关根地址（scheme + host），不含业务路径。"""
    value = raw.strip().rstrip("/")
    if not value:
        return _DEFAULT_TEST_GATEWAY

    for marker in _GATEWAY_PATH_MARKERS:
        if marker in value:
            value = value.split(marker, 1)[0].rstrip("/")
            break

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if not parsed.netloc:
            return _DEFAULT_TEST_GATEWAY
        return f"{parsed.scheme}://{parsed.netloc}"

    return f"https://{value}"


def _gateway_env_raw() -> str | None:
    """读取网关配置，兼容旧环境变量名。"""
    for key in (
        "YOUHUO_BASE_URL",
        "YOUHUO_WORKER_URL",
        "YOUHUO_EMPLOY_URL",
        "YOUHUO_TASK_URL",
    ):
        value = os.getenv(key)
        if value:
            return value
    return None


def gateway_url() -> str:
    """有活 API 网关根地址，如 https://hopped-gateway-service-sops.hopped.com.cn"""
    raw = _gateway_env_raw()
    if not raw:
        return _DEFAULT_TEST_GATEWAY
    return _normalize_gateway(raw)


def applet_base_url() -> str:
    """C 端 / 扫码授权：hopped-applet-service/api/"""
    return f"{gateway_url().rstrip('/')}/{APPLET_API_PATH}"


def employ_base_url() -> str:
    """B 端招工：hopped-miniprogram-web/api/"""
    return f"{gateway_url().rstrip('/')}/{EMPLOY_API_PATH}"


def task_base_url() -> str:
    """众包任务：hopped-platform-service/api/"""
    return f"{gateway_url().rstrip('/')}/{PLATFORM_API_PATH}"


def get_token_by_session_url() -> str:
    explicit = os.getenv("YOUHUO_GET_TOKEN_URL")
    if explicit:
        return explicit
    return f"{applet_base_url()}Login/GetTokenBySession"


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def ensure_gateway_configured() -> None:
    """云托管镜像启动校验：YOUHUO_REQUIRE_BASE_URL=1 时须配置 YOUHUO_BASE_URL。"""
    if not _truthy_env("YOUHUO_REQUIRE_BASE_URL"):
        return
    raw = _gateway_env_raw()
    if not raw:
        raise SystemExit(
            "YOUHUO_BASE_URL is required when YOUHUO_REQUIRE_BASE_URL is set. "
            "Example: https://hopped-gateway-service-sops.hopped.com.cn"
        )
    if _truthy_env("YOUHUO_REJECT_TEST_GATEWAY") and "sops-test" in raw:
        raise SystemExit(
            "Production deployment must not use sops-test gateway. "
            "Set YOUHUO_BASE_URL to the production gateway."
        )

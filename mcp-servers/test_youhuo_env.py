"""youhuo_env 环境变量派生单元测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.youhuo_env import (
    APPLET_API_PATH,
    EMPLOY_API_PATH,
    PLATFORM_API_PATH,
    applet_base_url,
    employ_base_url,
    gateway_url,
    get_token_by_session_url,
    task_base_url,
)

PROD_GATEWAY = "https://hopped-gateway-service.hopped.com.cn"
TEST_GATEWAY = "https://hopped-gateway-service-sops-test.hopped.com.cn"
PROD_API = f"{PROD_GATEWAY}/{APPLET_API_PATH}"


def _clear_env():
    for key in ("YOUHUO_BASE_URL", "YOUHUO_WORKER_URL", "YOUHUO_GET_TOKEN_URL"):
        os.environ.pop(key, None)


def test_gateway_domain_only():
    _clear_env()
    os.environ["YOUHUO_BASE_URL"] = PROD_GATEWAY
    assert gateway_url() == PROD_GATEWAY
    assert applet_base_url() == PROD_API


def test_gateway_host_without_scheme():
    _clear_env()
    os.environ["YOUHUO_BASE_URL"] = "hopped-gateway-service.hopped.com.cn"
    assert gateway_url() == PROD_GATEWAY
    assert applet_base_url() == PROD_API


def test_legacy_full_url_compat():
    _clear_env()
    os.environ["YOUHUO_BASE_URL"] = PROD_API.rstrip("/")
    assert gateway_url() == PROD_GATEWAY
    assert applet_base_url() == PROD_API


def test_get_token_by_session_url_derived():
    _clear_env()
    os.environ["YOUHUO_BASE_URL"] = PROD_GATEWAY
    assert get_token_by_session_url() == f"{PROD_API}Login/GetTokenBySession"


def test_default_test_gateway():
    _clear_env()
    assert gateway_url() == TEST_GATEWAY
    assert applet_base_url() == f"{TEST_GATEWAY}/{APPLET_API_PATH}"


def test_b_employ_and_task_urls():
    _clear_env()
    os.environ["YOUHUO_BASE_URL"] = PROD_GATEWAY
    assert employ_base_url() == f"{PROD_GATEWAY}/{EMPLOY_API_PATH}"
    assert task_base_url() == f"{PROD_GATEWAY}/{PLATFORM_API_PATH}"


def test_legacy_employ_url_compat():
    _clear_env()
    os.environ["YOUHUO_EMPLOY_URL"] = f"{PROD_GATEWAY}/{EMPLOY_API_PATH}".rstrip("/")
    assert gateway_url() == PROD_GATEWAY
    assert employ_base_url() == f"{PROD_GATEWAY}/{EMPLOY_API_PATH}"


if __name__ == "__main__":
    for fn in [
        test_gateway_domain_only,
        test_gateway_host_without_scheme,
        test_legacy_full_url_compat,
        test_get_token_by_session_url_derived,
        test_default_test_gateway,
        test_b_employ_and_task_urls,
        test_legacy_employ_url_compat,
    ]:
        fn()
        print(f"✅ {fn.__name__}")
    print("\n全部测试通过")

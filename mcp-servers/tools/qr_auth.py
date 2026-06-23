"""扫码授权二维码：调用 GetAIAuthQRCode 并解析图片 URL。"""
import httpx


def build_qr_api_url(base_url: str, session_id: str, role: int, source_code: str = "") -> str:
    base = base_url.rstrip("/") + "/"
    return f"{base}Personal/GetAIAuthQRCode?sessionId={session_id}&role={role}&sourceCode={source_code}"


async def fetch_qr_image_url(
    base_url: str,
    session_id: str,
    role: int,
    source_code: str = "",
) -> tuple[str, str]:
    """调用生成二维码接口，返回 (图片直链, 接口地址)。

    后端响应示例::
        {"ActionResult":"1","Message":"","Data":"https://...cos.../xxx.jpg"}

    接口本身返回 JSON，浏览器打开不会直接显示图片；Data 中的 COS 链接可直接展示。
    """
    api_url = build_qr_api_url(base_url, session_id, role, source_code)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(api_url)
            data = resp.json()
            if data.get("ActionResult") == "1" and data.get("Data"):
                image_url = data["Data"]
                if isinstance(image_url, str) and image_url.startswith("http"):
                    return image_url, api_url
            if data.get("code") == 200 and data.get("data"):
                image_url = data["data"]
                if isinstance(image_url, str) and image_url.startswith("http"):
                    return image_url, api_url
    except Exception:
        pass
    return api_url, api_url

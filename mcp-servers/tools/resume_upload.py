"""简历 COS 上传与平台注册（对齐小程序 uploadResumeFile + Personal/uploadresume）。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Awaitable, Callable

from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosClientError, CosServiceError

from tools.api_response import api_data, api_message, api_ok

RequestFn = Callable[..., Awaitable[dict]]

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024


def cos_bucket_config() -> tuple[str, str]:
    from tools.youhuo_env import gateway_url

    if "test" in gateway_url():
        return "hopped-user-upload-test-1258944054", "ap-guangzhou"
    return "hopped-user-upload-1258944054", "ap-guangzhou"


def normalize_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext


def validate_resume_file(file_path: str) -> tuple[Path, str]:
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"文件不存在: {file_path}")
    ext = normalize_ext(path.name)
    if f".{ext}" not in ALLOWED_EXTENSIONS:
        raise ValueError("仅支持 pdf、doc、docx 格式简历")
    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ValueError("简历文件不能超过 10MB")
    if size <= 0:
        raise ValueError("简历文件为空")
    return path, ext


async def fetch_cos_credentials(req: RequestFn) -> dict:
    bucket, _ = cos_bucket_config()
    result = await req("GET", "IdCardAuth/getcredential", params={"bucketName": bucket})
    if not api_ok(result):
        raise ValueError(api_message(result, "获取 COS 上传凭证失败"))
    data = api_data(result) or {}
    credentials = data.get("Credentials") or data.get("credentials") or {}
    if not credentials:
        raise ValueError("COS 凭证为空")
    return credentials


def unwrap_cos_credential(raw: str) -> str:
    """对齐小程序 getCosAuth.ts 对临时密钥的去掩码处理。"""
    if not raw or len(raw) <= 22:
        return raw
    middle = raw[5:22]
    if middle.startswith("tmp"):
        return raw.replace(middle, "", 1)
    return raw


def upload_file_to_cos(local_path: Path, credentials: dict, *, object_name: str | None = None) -> str:
    bucket, region = cos_bucket_config()
    secret_id = unwrap_cos_credential(credentials.get("TmpSecretId") or credentials.get("tmpSecretId") or "")
    secret_key = unwrap_cos_credential(credentials.get("TmpSecretKey") or credentials.get("tmpSecretKey") or "")
    token = credentials.get("Token") or credentials.get("token")
    if not secret_id or not secret_key or not token:
        raise ValueError("COS 临时密钥不完整")

    key = object_name or f"resume/{local_path.name.encode('ascii', 'ignore').decode() or 'resume.pdf'}"
    # 中文文件名在 COS key 中可能导致签名问题，使用 ascii 安全名
    if local_path.name != key.rsplit("/", 1)[-1]:
        import uuid

        ext = local_path.suffix.lower() or ".pdf"
        key = f"resume/{uuid.uuid4().hex[:12]}{ext}"
    config = CosConfig(
        Region=region,
        SecretId=secret_id,
        SecretKey=secret_key,
        Token=token,
        Scheme="https",
    )
    client = CosS3Client(config)
    try:
        client.upload_file(
            Bucket=bucket,
            LocalFilePath=str(local_path),
            Key=key,
            PartSize=5,
            MAXThread=4,
        )
    except (CosClientError, CosServiceError) as e:
        raise ValueError(f"COS 上传失败: {e}") from e

    return f"https://{bucket}.cos.{region}.myqcloud.com/{key}"


async def register_resume(
    req: RequestFn,
    *,
    resume_name: str,
    resume_path: str,
    resume_size: int,
    resume_ext_name: str,
) -> dict:
    payload = {
        "resume_name": resume_name,
        "resume_path": resume_path,
        "resume_size": resume_size,
        "resume_ext_name": resume_ext_name.lstrip("."),
    }
    result = await req("POST", "Personal/uploadresume", json=payload)
    if not api_ok(result):
        raise ValueError(api_message(result, "保存简历信息失败"))
    return api_data(result) or payload


async def delete_resume(req: RequestFn) -> dict:
    result = await req("POST", "Personal/deleteresume", json={})
    if not api_ok(result):
        raise ValueError(api_message(result, "删除简历失败"))
    return api_data(result) or {}


async def upload_resume_from_path(req: RequestFn, file_path: str) -> dict:
    local_path, ext = validate_resume_file(file_path)
    credentials = await fetch_cos_credentials(req)
    cos_url = upload_file_to_cos(local_path, credentials)
    size = local_path.stat().st_size
    saved = await register_resume(
        req,
        resume_name=local_path.name,
        resume_path=cos_url,
        resume_size=size,
        resume_ext_name=ext,
    )
    return {
        "success": True,
        "resume_name": saved.get("resume_name") or local_path.name,
        "resume_path": saved.get("resume_path") or cos_url,
        "resume_size": saved.get("resume_size") or size,
        "resume_ext_name": saved.get("resume_ext_name") or ext,
        "message": "简历上传成功",
    }


def parse_resume_from_profile(profile: dict) -> dict:
    return {
        "has_resume": bool(profile.get("resume_path") and profile.get("resume_name")),
        "resume_name": profile.get("resume_name") or "",
        "resume_path": profile.get("resume_path") or "",
        "resume_size": profile.get("resume_size") or 0,
        "resume_ext_name": (profile.get("resume_ext_name") or "").lstrip("."),
    }

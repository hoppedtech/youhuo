"""将真实 Token 写入共享存储，用于跳过扫码测试 B/C 端流程。

用法:
  python inject_token.py --token "YOUR_TOKEN" --role 1
  python inject_token.py --token "YOUR_TOKEN" --role 2

Token 写入 ~/.workbuddy/youhuo_auth.db，youhuo-b-api / youhuo-c-api 可直接读取。
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared_token_store import auth_store, DB_PATH
from tools.token_util import normalize_bearer_token


def inject(token: str, role: int, name: str = "") -> str:
    auth_store.cleanup_expired()
    session_id = auth_store.create_session(role=role)
    auth_store.set_token(
        session_id,
        normalize_bearer_token(token.strip()),
        user_info={"name": name or ("测试用户" if role == 1 else "测试企业"), "is_new_user": False},
        expires_in=7200,
    )
    auth_store.set_current_session(session_id)
    return session_id


def main():
    parser = argparse.ArgumentParser(description="注入有活平台测试 Token")
    parser.add_argument("--token", required=True, help="Bearer Token（不含 Bearer 前缀）")
    parser.add_argument("--role", type=int, default=1, choices=[1, 2], help="1=C端找活方, 2=B端招工方")
    parser.add_argument("--name", default="", help="可选，显示用用户名")
    args = parser.parse_args()

    session_id = inject(args.token, args.role, args.name)
    preview = args.token[:8] + "..." if len(args.token) > 8 else args.token
    role_name = "找活方(C)" if args.role == 1 else "招工方(B)"

    print(f"✅ Token 已注入")
    print(f"   角色: {role_name}")
    print(f"   session_id: {session_id}")
    print(f"   token: {preview}")
    print(f"   存储: {DB_PATH}")
    print("\n可在 Cursor 中直接调用 youhuo-c-api / youhuo-b-api 的 Tool 进行联调。")


if __name__ == "__main__":
    main()

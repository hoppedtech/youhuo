"""将多个 MCP Server 模块的 Tool 合并到单一 FastMCP 实例。"""
import importlib.util
import os
from typing import Iterable


def _server_path(*parts: str) -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, *parts)


def _internal_path(api_dir: str, module: str) -> str:
    """youhuo-b-api / youhuo-c-api 下的 internal 模块路径。"""
    return os.path.join(_server_path(api_dir), "internal", f"{module}.py")


def load_tools_from_server(
    target_mcp,
    server_py: str,
    *,
    skip: Iterable[str] | None = None,
    rename: dict[str, str] | None = None,
) -> list[str]:
    """从已有 server.py 加载 Tool 到 target_mcp。

    Returns:
        已注册的 tool 名称列表
    """
    skip_set = set(skip or [])
    rename = rename or {}
    spec = importlib.util.spec_from_file_location(f"_youhuo_srv_{id(server_py)}", server_py)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载: {server_py}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    src_mcp = getattr(mod, "mcp", None)
    if src_mcp is None:
        raise AttributeError(f"{server_py} 缺少 mcp 实例")

    tool_manager = getattr(src_mcp, "_tool_manager", None)
    if tool_manager is None:
        raise AttributeError(f"{server_py} 缺少 _tool_manager")

    src_tools = getattr(tool_manager, "_tools", {})
    dst_tools = target_mcp._tool_manager._tools
    loaded: list[str] = []

    for name, tool in src_tools.items():
        if name in skip_set:
            continue
        dst_name = rename.get(name, name)
        if dst_name in dst_tools and dst_name not in rename.values():
            continue
        dst_tools[dst_name] = tool
        loaded.append(dst_name)

    return loaded

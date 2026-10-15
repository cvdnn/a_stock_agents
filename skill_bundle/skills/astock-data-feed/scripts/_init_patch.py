"""akshare-proxy-patch: 在导入 akshare 前安装 patch 绕过东财反爬。

TOKEN 解析优先级：
  1. AUTH_TOKEN 环境变量或用户工作区 local/settings/.env（推荐）
  2. config.yaml 的 proxy_patch.auth_token（向后兼容）
用法: 在所有使用 akshare 东财接口的脚本顶部添加:
    from _init_patch import patched_akshare as ak
"""

import sys as _astock_sys
from pathlib import Path as _AstPath
_astock_bundle = next((p for p in _AstPath(__file__).resolve().parents if (p / "bundle.json").is_file()), None)
if _astock_bundle is None:
    raise RuntimeError("Complete a_stock_agents bundle required")
_astock_runtime = _astock_bundle / "runtime"
if str(_astock_runtime) not in _astock_sys.path:
    _astock_sys.path.insert(0, str(_astock_runtime))

import os
import yaml
from pathlib import Path


def _load_env_token():
    """从环境变量或用户工作区 local/settings/.env 读取 AUTH_TOKEN。"""
    if os.environ.get("AUTH_TOKEN"):
        return os.environ["AUTH_TOKEN"].strip()
    env_path = __import__("core.workspace", fromlist=["get_workspace_env_path"]).get_workspace_env_path()
    if not env_path.exists():
        return ""
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("AUTH_TOKEN="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def _load_config():
    """从 config.yaml 加载 proxy patch 配置"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = str(__import__("core.workspace",fromlist=["LOCAL_DIR"]).LOCAL_DIR / "skills" / "astock-data-feed" / "config.yaml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"找不到配置文件: {config_path}\n"
            f"请参考 SKILL.md 中的说明创建"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("proxy_patch", {})


cfg = _load_config()
auth_token = _load_env_token() or cfg.get("auth_token", "")

if cfg.get("enabled", True) and auth_token:
    import akshare_proxy_patch

    akshare_proxy_patch.install_patch(
        cfg.get("gateway", "101.201.173.125"),
        auth_token=auth_token,
        retry=cfg.get("retry", 30),
        hook_domains=cfg.get("hook_domains", [
            "push2.eastmoney.com",
            "push2his.eastmoney.com",
        ]),
        fast=cfg.get("fast", True),
    )

import akshare as patched_akshare

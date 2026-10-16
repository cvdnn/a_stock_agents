"""akshare-proxy-patch: 在导入 akshare 前安装 patch 绕过东财反爬。

TOKEN 解析优先级：
  1. AUTH_TOKEN 环境变量或用户工作区 local/settings/.env（推荐）
  2. config.yaml 的 proxy_patch.auth_token（向后兼容）
用法: 在所有使用 akshare 东财接口的脚本顶部添加:
    from _init_patch import patched_akshare as ak
"""

import sys as _astock_sys
import os as _astock_os
import json as _astock_json
from pathlib import Path as _AstPath

def _astock_resolve_bundle():
    _file_path = _AstPath(__file__).resolve()
    # 1. 自定位：自身及父目录向上查找 bundle.json
    for _p in _file_path.parents:
        if (_p / "bundle.json").is_file():
            return _p
    # 2. 兄弟定位：查找兄弟目录 a-stock-agents/bundle.json（未解析/已解析上级均探测）
    for _base in (_AstPath(__file__), _file_path):
        for _p in _base.parents:
            for _candidate in (_p / "a-stock-agents", _p.parent / "a-stock-agents"):
                if (_candidate / "bundle.json").is_file():
                    return _candidate.resolve()
    # 3. 收据定位：读取系统固定安装收据 install.json
    _receipts = []
    _env_root = _astock_os.environ.get("A_STOCK_WORKSPACE_ROOT") or _astock_os.environ.get("A_STOCK_AGENTS_ROOT")
    if _env_root:
        _receipts.append(_AstPath(_env_root) / "install.json")
    if _astock_sys.platform == "win32":
        _local = _astock_os.environ.get("LOCALAPPDATA") or (_AstPath.home() / "AppData/Local")
        _receipts.append(_AstPath(_local) / "a_stock_agents" / "install.json")
    elif _astock_sys.platform == "darwin":
        _receipts.append(_AstPath.home() / "Library/Application Support" / "a_stock_agents" / "install.json")
    else:
        _xdg = _astock_os.environ.get("XDG_DATA_HOME") or (_AstPath.home() / ".local/share")
        _receipts.append(_AstPath(_xdg) / "a_stock_agents" / "install.json")
    for _rp in _receipts:
        if _rp.is_file():
            try:
                _data = _astock_json.loads(_rp.read_text(encoding="utf-8"))
                _target = _data.get("bundle_root") or _data.get("runtime_root") or _data.get("anchor_root")
                if _target:
                    _tp = _AstPath(_target).resolve()
                    if (_tp / "bundle.json").is_file():
                        return _tp
                    if (_tp / "a-stock-agents" / "bundle.json").is_file():
                        return (_tp / "a-stock-agents").resolve()
                    if _tp.name == "runtime" and (_tp.parent / "bundle.json").is_file():
                        return _tp.parent
            except Exception:
                pass
    raise RuntimeError("ANCHOR_SKILL_MISSING: Complete a_stock_agents bundle or a-stock-agents anchor skill required")

_astock_bundle = _astock_resolve_bundle()
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

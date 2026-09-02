"""akshare-proxy-patch: 在导入 akshare 前安装 patch 绕过东财反爬。

TOKEN 解析优先级：
  1. ~/.AI-Platform/.env 文件（推荐）
  2. config.yaml 的 proxy_patch.auth_token（向后兼容）
用法: 在所有使用 akshare 东财接口的脚本顶部添加:
    from _init_patch import patched_akshare as ak
"""
import os
import yaml
from pathlib import Path


def _load_env_token():
    """从 ~/.AI-Platform/.env 读取 AUTH_TOKEN"""
    env_path = Path.home() / ".AI-Platform" / ".env"
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
    config_path = os.path.join(script_dir, "config.yaml")

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

#!/usr/bin/env python3
"""
包装脚本：自动初始化 akshare-proxy-patch 后调用其他 fetch 脚本。

TOKEN 从 ~/.AI-Platform/.env 读取（优先级1），回退到 config.yaml（优先级2）。

用法：
  python3 fetch_patched.py fetch_realtime.py --quote 600760
  python3 fetch_patched.py fetch_history.py --kline 600760 --start 20260601 --end 20260616
  python3 fetch_patched.py fetch_technical.py 600760 --freq 1d --count 5
  python3 fetch_patched.py fetch_sector_info.py --no-concepts --json 600760
"""
import sys
import os
import json
import urllib.request
import yaml
from pathlib import Path


BALANCE_CHECK_URL = "http://101.201.173.125:47001/api/token/{}"
BALANCE_WARN_THRESHOLD = 100


def load_env_token():
    """从 ~/.AI-Platform/.env 读取 AUTH_TOKEN"""
    env_path = Path.home() / ".AI-Platform" / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("AUTH_TOKEN="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def load_config():
    """从 config.yaml 读取 proxy patch 配置"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.yaml")

    if not os.path.exists(config_path):
        print("错误: 找不到配置文件 config.yaml", file=sys.stderr)
        print(f"      请创建 {config_path}", file=sys.stderr)
        print(f"      模板格式：", file=sys.stderr)
        print(f"        proxy_patch:", file=sys.stderr)
        print(f"          enabled: true", file=sys.stderr)
        print(f"          gateway: \"101.201.173.125\"", file=sys.stderr)
        print(f"          auth_token: \"\"", file=sys.stderr)
        print(f"          retry: 30", file=sys.stderr)
        print(f"          fast: true", file=sys.stderr)
        print(f"          hook_domains:", file=sys.stderr)
        print(f"            - \"push2.eastmoney.com\"", file=sys.stderr)
        print(f"            - \"push2his.eastmoney.com\"", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config.get("proxy_patch", {})


def install_patch(cfg):
    """安装 akshare-proxy-patch"""
    if not cfg.get("enabled", True):
        print("信息: proxy patch 已禁用，跳过初始化", file=sys.stderr)
        return

    auth_token = load_env_token() or cfg.get("auth_token", "")
    if not auth_token:
        print("错误: 未找到 AUTH_TOKEN（~/.AI-Platform/.env 或 config.yaml 中均未配置）", file=sys.stderr)
        sys.exit(1)

    # 积分余额预检
    try:
        with urllib.request.urlopen(
            BALANCE_CHECK_URL.format(auth_token), timeout=5
        ) as resp:
            data = json.loads(resp.read().decode())
            balance = data.get("balance", 0)
            if balance < BALANCE_WARN_THRESHOLD:
                print(f"⚠️  Proxy 积分余额仅剩 {balance}，低于阈值 {BALANCE_WARN_THRESHOLD}，可能很快耗尽", file=sys.stderr)
            elif balance < 500:
                print(f"⚡ Proxy 积分余额 {balance}，建议节省使用", file=sys.stderr)
    except Exception:
        pass  # 余额查询失败不阻断主流程

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


# ===== 主流程 =====

if len(sys.argv) < 2:
    print("用法: fetch_patched.py <script_name> [args...]", file=sys.stderr)
    sys.exit(1)

# 加载配置并安装 patch
cfg = load_config()
install_patch(cfg)

# 找到目标脚本
script_dir = os.path.dirname(os.path.abspath(__file__))
target = sys.argv[1]
target_path = os.path.join(script_dir, target)

if not os.path.exists(target_path):
    target_path = target  # 允许绝对路径

# 将目标脚本作为 __main__ 执行
sys.argv = [target_path] + sys.argv[2:]
__file__ = target_path

with open(target_path, "r", encoding="utf-8") as f:
    code = compile(f.read(), target_path, "exec")
exec(code, {"__name__": "__main__", "__file__": target_path})

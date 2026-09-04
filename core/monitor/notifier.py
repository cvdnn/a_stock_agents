# -*- coding: utf-8 -*-
"""
跨平台通知与系统提醒调度器 (Notifier)

支持:
1. Windows 系统原生 Toast / BalloonTip 气泡提醒
2. 控制台与日志友好降级
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional


def send_windows_toast(title: str, message: str, timeout_sec: int = 10) -> bool:
    """发送 Windows 系统气泡提醒 (Toast Notification)。
    
    采用 PowerShell NotifyIcon 实现，无需外部第三方 GUI 依赖。非 Windows 环境下自动降级为控制台日志。
    """
    if sys.platform != "win32":
        print(f"[{title}] {message}")
        return False

    clean_title = title.replace('"', '`"').replace("'", "''")
    clean_msg = message.replace('"', '`"').replace("'", "''")

    ps_script = f"""
[void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
$objNotifyIcon = New-Object System.Windows.Forms.NotifyIcon
$objNotifyIcon.Icon = [System.Drawing.SystemIcons]::Information
$objNotifyIcon.BalloonTipIcon = "Info"
$objNotifyIcon.BalloonTipTitle = "{clean_title}"
$objNotifyIcon.BalloonTipText = "{clean_msg}"
$objNotifyIcon.Visible = $True
$objNotifyIcon.ShowBalloonTip({timeout_sec * 1000})
Start-Sleep -Seconds 1
$objNotifyIcon.Dispose()
"""
    try:
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
        subprocess.run(cmd, capture_output=True, timeout=timeout_sec + 5)
        return True
    except Exception:
        # 降级打印
        print(f"[{title}] {message}")
        return False


def notify(title: str, message: str, level: str = "INFO") -> bool:
    """统一通知路由，依据环境与等级进行分发。"""
    prefix = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "🚨", "SUCCESS": "✅"}.get(level, "🔔")
    formatted_title = f"{prefix} {title}"
    return send_windows_toast(formatted_title, message)


__all__ = ["send_windows_toast", "notify"]

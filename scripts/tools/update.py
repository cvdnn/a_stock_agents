# -*- coding: utf-8 -*-
"""
A-Stock Agents Safe Updater.
Safely updates code and skills while protecting output/ and custom configurations.
Version naming rule: v2, v3, v4...
"""

import os
import sys
import shutil
import zipfile
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

def _find_project_root() -> Path:
    curr = Path(__file__).resolve().parent
    for p in [curr] + list(curr.parents):
        if (p / "pyproject.toml").exists() or (p / "AGENTS.md").exists():
            return p
    return curr.parent.parent

PROJECT_ROOT = _find_project_root()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for p in [PROJECT_ROOT, SCRIPTS_DIR, SCRIPTS_DIR / "core", PROJECT_ROOT / "core"]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from core.config import OUTPUT_DIR, BACKUPS_DIR
except Exception:
    OUTPUT_DIR = PROJECT_ROOT / "output"
    BACKUPS_DIR = PROJECT_ROOT / "backups"

PROTECTED_DIRS = [OUTPUT_DIR.name, "output", "user_data", "backups"]
PROTECTED_FILES = ["config/config.yaml"]

def create_backup() -> Path:
    """Creates a timestamped snapshot backup of output data and configuration."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUPS_DIR / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"--> [备份] 正在创建用户专属数据({OUTPUT_DIR.name}/)与配置快照: {backup_dir.name}...")
    
    # 1. Backup output
    if OUTPUT_DIR.exists():
        shutil.copytree(OUTPUT_DIR, backup_dir / "output", dirs_exist_ok=True)
        
    # 2. Backup config
    cfg_file = PROJECT_ROOT / "config" / "config.yaml"
    if cfg_file.exists():
        (backup_dir / "config").mkdir(parents=True, exist_ok=True)
        shutil.copy2(cfg_file, backup_dir / "config" / "config.yaml")
        
    print(f"    快照已保存至: {backup_dir}")
    return backup_dir


def apply_update_from_zip(zip_path: Path, backup_dir: Path) -> bool:
    """Extracts update package non-destructively, protecting output/."""
    print(f"--> [更新] 正在从更新包解压更新: {zip_path}...")
    temp_dir = PROJECT_ROOT / "cache" / "_update_temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            # Zip Slip 防护：逐个校验条目，禁止绝对路径与路径穿越
            temp_root = temp_dir.resolve()
            for member in z.infolist():
                member_path = (temp_dir / member.filename).resolve()
                if not str(member_path).startswith(str(temp_root) + os.sep) and member_path != temp_root:
                    raise ValueError(f"非法压缩条目(路径穿越): {member.filename}")
            z.extractall(temp_dir)
            
        src_root = temp_dir / "a_stock_agents" if (temp_dir / "a_stock_agents").exists() else temp_dir
        
        for item in src_root.iterdir():
            if item.name in [".venv", "venv", "backups", "output", "user_data", OUTPUT_DIR.name]:
                continue
            dst_item = PROJECT_ROOT / item.name
            if item.is_dir():
                shutil.copytree(item, dst_item, dirs_exist_ok=True)
            else:
                if item.name == "config.yaml" and dst_item.exists():
                    continue
                shutil.copy2(item, dst_item)
                
        print("    代码与技能文件已更新完成。")
        return True
    except Exception as e:
        print(f"[错误] 更新解压失败: {e}")
        return False
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

def sync_dependencies():
    """Syncs python dependencies in .venv."""
    venv_py = PROJECT_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not venv_py.exists():
        return
    print("--> [依赖] 检查并同步 Python 依赖库...")
    try:
        # Check if uv is used or standard pip
        subprocess.run(["uv", "pip", "install", "--python", str(venv_py), "-r", str(PROJECT_ROOT / "requirements.txt"), "-q"], check=True)
        print("    依赖库已由 uv 同步至最新。")
    except Exception:
        try:
            subprocess.run([str(venv_py), "-m", "pip", "install", "-r", str(PROJECT_ROOT / "requirements.txt"), "-q"], check=True)
            print("    依赖库已由 pip 同步至最新。")
        except Exception as e:
            print(f"[警告] 依赖同步遇到异常: {e}")

def run_self_verification() -> bool:
    """Runs verify.py after update."""
    venv_py = PROJECT_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    py_exec = str(venv_py) if venv_py.exists() else sys.executable
    print("--> [自检] 运行升级后就绪性验证 (verify.py)...")
    try:
        res = subprocess.run([py_exec, str(PROJECT_ROOT / "verify.py")], check=False)
        return res.returncode == 0
    except Exception as e:
        print(f"[错误] 无法执行自检: {e}")
        return False

def rollback(backup_dir: Path):
    """Rolls back output data and configs from backup."""
    print("--> [回滚] 正在从备份恢复专属数据与配置...")
    if (backup_dir / "output").exists():
        shutil.copytree(backup_dir / "output", OUTPUT_DIR, dirs_exist_ok=True)
    if (backup_dir / "config" / "config.yaml").exists():
        shutil.copy2(backup_dir / "config" / "config.yaml", PROJECT_ROOT / "config" / "config.yaml")
    print("    回滚操作完成。")


def main():
    parser = argparse.ArgumentParser(description="A-Stock Agents Safe Updater")
    parser.add_argument("--from-zip", "-z", type=str, default=None, help="Update from zip package (e.g. a_stock_agents_v2.zip)")
    parser.add_argument("--backup-only", "-b", action="store_true", help="Only perform output data backup")
    parser.add_argument("--rollback", "-r", type=str, default=None, help="Rollback from specified backup dir")
    args = parser.parse_args()

    print("=" * 70)
    print(" [A-Stock Agents 安全更新与数据保护系统]")
    print(f" 项目根目录: {PROJECT_ROOT}")
    print("=" * 70)

    if args.backup_only:
        create_backup()
        return

    if args.rollback:
        rollback_path = Path(args.rollback)
        if not rollback_path.is_absolute():
            rollback_path = PROJECT_ROOT / "backups" / args.rollback
        if rollback_path.exists():
            rollback(rollback_path)
        else:
            print(f"[错误] 找不到备份目录: {rollback_path}")
        return

    if not args.from_zip:
        print("请指定更新源包，例如: python bin/update.py --from-zip a_stock_agents_v2.zip")
        print("或者仅创建用户数据备份: python bin/update.py --backup-only")
        return

    zip_path = Path(args.from_zip).resolve()
    if not zip_path.exists():
        print(f"[错误] 更新包不存在: {zip_path}")
        sys.exit(1)

    backup_dir = create_backup()
    success = apply_update_from_zip(zip_path, backup_dir)
    if not success:
        print("[失败] 更新未完成，自动回滚...")
        rollback(backup_dir)
        sys.exit(1)

    sync_dependencies()
    verified = run_self_verification()
    if verified:
        print("=" * 70)
        print(" [成功] A-Stock Agents 升级完成！专属数据(output/)与配置 100% 完好。")
        print("=" * 70)
    else:
        print("=" * 70)
        print(" [警告] 升级后自检未全部通过。您可以执行以下命令回滚配置：")
        print(f"   python bin/update.py --rollback {backup_dir.name}")
        print("=" * 70)

if __name__ == "__main__":
    main()

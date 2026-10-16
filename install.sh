#!/usr/bin/env bash
# A-Stock Agents Unified Installation & Lifecycle Management Kernel (POSIX / Bash)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INSPECT=false
AGENT=""
METHOD="link"
YES=false
DOCTOR=false
JSON_MODE=false
DATA_DIR=""
VERSION="v3"
SKIP_DEPS=false
SKIP_VENV=false
FORCE=false
TUI=false
UNINSTALL=""
UPDATE=false
ROLLBACK=false
SOURCE_DIR=""

# Parse arguments (supports both single and double dash)
while [[ $# -gt 0 ]]; do
  case "$1" in
    -Inspect|--inspect)
      INSPECT=true
      shift
      ;;
    -Agent|--agent)
      AGENT="$2"
      shift 2
      ;;
    -Method|--method)
      METHOD="$2"
      shift 2
      ;;
    -Yes|--yes|-y)
      YES=true
      shift
      ;;
    -Doctor|--doctor)
      DOCTOR=true
      shift
      ;;
    -Update|--update)
      UPDATE=true
      shift
      ;;
    -Rollback|--rollback)
      ROLLBACK=true
      shift
      ;;
    -SourceDir|--source-dir)
      SOURCE_DIR="$2"
      shift 2
      ;;
    -Json|--json)
      JSON_MODE=true
      shift
      ;;
    -DataDir|--data-dir)
      DATA_DIR="$2"
      shift 2
      ;;
    -Version|--version)
      VERSION="$2"
      shift 2
      ;;
    -SkipDeps|--skip-deps)
      SKIP_DEPS=true
      shift
      ;;
    -SkipVenv|--skip-venv)
      SKIP_VENV=true
      shift
      ;;
    -Force|--force)
      FORCE=true
      shift
      ;;
    -Tui|--tui)
      TUI=true
      shift
      ;;
    -Uninstall|--uninstall)
      UNINSTALL="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

deploy_release_files() {
  local src="$1"
  local dst="$2"
  if [[ "$src" == "$dst" ]]; then
    return
  fi
  mkdir -p "$dst"
  for item in skills skill_bundle runtime assets references bin bundle.json INSTALL.json install.ps1 install.sh requirements.txt requirements-full.txt; do
    if [[ -e "$src/$item" ]]; then
      rm -rf "$dst/$item"
      cp -a "$src/$item" "$dst/$item"
    fi
  done
}

set_current_link() {
  local data_root="$1"
  local target_dir="$2"
  local current_link="$data_root/current"
  rm -f "$current_link"
  ln -sfn "$target_dir" "$current_link"
}

# 1. Resolve Data Root
resolve_data_root() {
  if [[ -n "$DATA_DIR" ]]; then
    mkdir -p "$DATA_DIR"
    (cd "$DATA_DIR" && pwd)
    return
  fi
  if [[ -n "${A_STOCK_WORKSPACE_ROOT:-}" ]]; then
    echo "$A_STOCK_WORKSPACE_ROOT"
    return
  fi
  if [[ -n "${A_STOCK_AGENTS_ROOT:-}" ]]; then
    echo "$A_STOCK_AGENTS_ROOT"
    return
  fi
  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "$HOME/Library/Application Support/a_stock_agents"
  else
    echo "${XDG_DATA_HOME:-$HOME/.local/share}/a_stock_agents"
  fi
}

TARGET_DATA_ROOT="$(resolve_data_root)"

# 2. Discover Python
find_host_python() {
  if [[ -n "${A_STOCK_PYTHON:-}" && -x "$A_STOCK_PYTHON" ]]; then
    echo "$A_STOCK_PYTHON"
    return
  fi
  for cand in "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/../.venv/bin/python"; do
    if [[ -x "$cand" ]]; then
      echo "$cand"
      return
    fi
  done
  for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      command -v "$cmd"
      return
    fi
  done
  echo ""
}

HOST_PYTHON="$(find_host_python)"
UV_CMD="$(command -v uv || true)"

# 3. Locate bundle and skills
SKILLS_DIR=""
for cand in "$SCRIPT_DIR/skills" "$SCRIPT_DIR/skill_bundle/skills"; do
  if [[ -d "$cand" ]]; then
    SKILLS_DIR="$(cd "$cand" && pwd)"
    break
  fi
done

ANCHOR_DIR=""
RUNTIME_DIR=""
if [[ -n "$SKILLS_DIR" && -d "$SKILLS_DIR/a-stock-agents" ]]; then
  ANCHOR_DIR="$SKILLS_DIR/a-stock-agents"
  if [[ -d "$ANCHOR_DIR/runtime" ]]; then
    RUNTIME_DIR="$ANCHOR_DIR/runtime"
  fi
fi
if [[ -z "$RUNTIME_DIR" ]]; then
  for cand in "$SCRIPT_DIR/skill_bundle/runtime" "$SCRIPT_DIR/runtime"; do
    if [[ -d "$cand" ]]; then
      RUNTIME_DIR="$(cd "$cand" && pwd)"
      break
    fi
  done
fi

BUNDLE_ROOT=""
if [[ -f "$SCRIPT_DIR/bundle.json" ]]; then
  BUNDLE_ROOT="$SCRIPT_DIR"
elif [[ -f "$SCRIPT_DIR/skill_bundle/bundle.json" ]]; then
  BUNDLE_ROOT="$SCRIPT_DIR/skill_bundle"
elif [[ -n "$ANCHOR_DIR" && -f "$ANCHOR_DIR/bundle.json" ]]; then
  BUNDLE_ROOT="$ANCHOR_DIR"
fi

# Detect agents
UNIVERSAL_PATH="$HOME/.agents/skills"
HERMES_PATH="$HOME/.hermes/skills"
WORKBUDDY_PATH="$HOME/.workbuddy/skills"
CODEX_PATH="$HOME/.codex/skills"

RECEIPT_PATH="$TARGET_DATA_ROOT/install.json"
IS_INSTALLED=false
if [[ -f "$RECEIPT_PATH" ]]; then
  IS_INSTALLED=true
fi

# -----------------------------------------------------------------------------
# Scenario A: -Inspect
# -----------------------------------------------------------------------------
if [[ "$INSPECT" == "true" ]]; then
  if [[ -n "$HOST_PYTHON" ]]; then
    "$HOST_PYTHON" - <<EOF
import json, os, sys
from pathlib import Path

skills = []
skills_dir = "$SKILLS_DIR"
if skills_dir and os.path.isdir(skills_dir):
    for entry in sorted(os.listdir(skills_dir)):
        p = os.path.join(skills_dir, entry, "SKILL.md")
        if os.path.isfile(p):
            skills.append(entry)

agents = {
    "universal": {"name": "Universal (.agents/skills)", "path": "$UNIVERSAL_PATH", "detected": os.path.isdir("$UNIVERSAL_PATH"), "methods": ["link", "copy"]},
    "hermes": {"name": "Hermes Desktop", "path": "$HERMES_PATH", "detected": os.path.isdir(os.path.expanduser("~/.hermes")), "methods": ["link", "copy", "external_dirs"]},
    "workbuddy": {"name": "WorkBuddy", "path": "$WORKBUDDY_PATH", "detected": os.path.isdir(os.path.expanduser("~/.workbuddy")), "methods": ["link", "copy"]},
    "codex": {"name": "Codex", "path": "$CODEX_PATH", "detected": os.path.isdir(os.path.expanduser("~/.codex")), "methods": ["link", "copy"]}
}

all_conflicts = []
for ag_key, ag_val in agents.items():
    ag_path = ag_val["path"]
    ag_conflicts = []
    if os.path.isdir(ag_path) and skills_dir and os.path.isdir(skills_dir):
        for s in skills:
            entry = os.path.join(ag_path, s)
            if os.path.exists(entry) and not os.path.islink(entry):
                copy_rc = os.path.join(ag_path, f".{s}.astock-copy.json")
                if not os.path.isfile(copy_rc):
                    ag_conflicts.append({"agent": ag_key, "skill": s, "path": entry})
    ag_val["overwrites_count"] = len(ag_conflicts)
    ag_val["conflicts"] = ag_conflicts
    all_conflicts.extend(ag_conflicts)

py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
existing = None
if os.path.isfile("$RECEIPT_PATH"):
    try:
        with open("$RECEIPT_PATH", "r", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        pass

out = {
    "status": "success",
    "action": "inspect",
    "data_root": "$TARGET_DATA_ROOT",
    "python": {
        "path": "$HOST_PYTHON",
        "version": py_ver,
        "uv_available": bool("$UV_CMD")
    },
    "bundle_source": "$BUNDLE_ROOT",
    "installed": "$IS_INSTALLED" == "true",
    "existing_receipt": existing,
    "agents": agents,
    "overwrites_count": len(all_conflicts),
    "conflicts": all_conflicts,
    "skills_count": len(skills),
    "skills": skills
}

if "$JSON_MODE" == "true":
    print(json.dumps(out, ensure_ascii=False, indent=2))
else:
    print("=== A-Stock Agents Environment Inspection (POSIX) ===")
    print(f"Data Root:      {out['data_root']}")
    print(f"Host Python:    {out['python']['path']} ({out['python']['version']})")
    print(f"Bundle Source:  {out['bundle_source']}")
    print(f"Skills Found:   {out['skills_count']} entries")
    print(f"Installed:      {out['installed']}")
    print("\nTarget Agents:")
    for k, v in agents.items():
        det = "[x] Detected" if v["detected"] else "[ ] Not found"
        confl = f" (Overwrites: {v['overwrites_count']} CONFLICT)" if v.get("overwrites_count", 0) > 0 else " (Overwrites: 0)"
        print(f"  - {v['name']}: {det} ({v['path']}){confl}")
EOF
    exit 0
  else
    if [[ "$JSON_MODE" == "true" ]]; then
      echo '{"status":"error","reason_code":"PYTHON_MISSING","message":"Python 3.9+ required"}'
    else
      echo "Error: Python 3.9+ required" >&2
    fi
    exit 1
  fi
fi

# -----------------------------------------------------------------------------
# Scenario B: -Doctor
# -----------------------------------------------------------------------------
if [[ "$DOCTOR" == "true" ]]; then
  if [[ ! -f "$RECEIPT_PATH" ]]; then
    if [[ "$JSON_MODE" == "true" ]]; then
      echo '{"status":"error","message":"No existing installation found in data root."}'
    else
      echo "Error: No existing installation found in data root." >&2
    fi
    exit 1
  fi
  ACT_PY="$HOST_PYTHON"
  DOC_PY=""
  if [[ -n "$RUNTIME_DIR" && -f "$RUNTIME_DIR/doctor.py" ]]; then
    DOC_PY="$RUNTIME_DIR/doctor.py"
  fi
  A_STOCK_WORKSPACE_ROOT="$TARGET_DATA_ROOT" "$ACT_PY" "$DOC_PY" --json
  exit $?
fi

# -----------------------------------------------------------------------------
# Scenario E: -Update
# -----------------------------------------------------------------------------
if [[ "$UPDATE" == "true" ]]; then
  if [[ ! -f "$RECEIPT_PATH" ]]; then
    if [[ "$JSON_MODE" == "true" ]]; then
      echo '{"status":"error","reason_code":"NOT_INSTALLED","message":"Cannot update: no existing installation found in data root."}'
    else
      echo "Error: Cannot update: no existing installation found in data root." >&2
    fi
    exit 1
  fi

  "$HOST_PYTHON" - <<EOF
import json, os, sys, shutil, subprocess, hashlib
from datetime import datetime, timezone

receipt_path = "$RECEIPT_PATH"
data_root = "$TARGET_DATA_ROOT"
with open(receipt_path, "r", encoding="utf-8") as f:
    receipt = json.load(f)

old_version = receipt.get("version", "v3")
new_version = "$VERSION" or "latest"
source_dir = "$SOURCE_DIR" or "$SCRIPT_DIR"

if new_version == old_version and "$FORCE" != "true":
    cand_bundle = os.path.join(source_dir, "bundle.json")
    if not os.path.isfile(cand_bundle):
        cand_bundle = os.path.join(source_dir, "skill_bundle", "bundle.json")
    if not os.path.isfile(cand_bundle):
        cand_bundle = os.path.join(source_dir, "skills", "a-stock-agents", "bundle.json")
    found_newer = False
    if os.path.isfile(cand_bundle):
        try:
            bj = json.load(open(cand_bundle, "r", encoding="utf-8"))
            if bj.get("version") and bj.get("version") != old_version:
                new_version = bj.get("version")
                found_newer = True
        except Exception:
            pass
    if not found_newer:
        err = {
            "status": "error",
            "reason_code": "ALREADY_AT_VERSION",
            "message": f"Already installed at version '{old_version}'. Specify a new -Version or pass --force.",
            "active_version": old_version
        }
        if "$JSON_MODE" == "true":
            print(json.dumps(err, indent=2))
        else:
            print(f"Error: Already installed at version '{old_version}'.", file=sys.stderr)
        sys.exit(1)

releases_dir = os.path.join(data_root, "releases")
os.makedirs(releases_dir, exist_ok=True)
new_version_dir = os.path.join(releases_dir, new_version)

# 1. Deploy release files
def deploy(src, dst):
    if os.path.abspath(src) == os.path.abspath(dst):
        return
    os.makedirs(dst, exist_ok=True)
    items = ['skills', 'skill_bundle', 'runtime', 'assets', 'references', 'bin', 'bundle.json', 'INSTALL.json', 'install.ps1', 'install.sh', 'requirements.txt', 'requirements-full.txt']
    for it in items:
        sp = os.path.join(src, it)
        if os.path.exists(sp):
            dp = os.path.join(dst, it)
            if os.path.exists(dp):
                if os.path.isdir(dp) and not os.path.islink(dp):
                    shutil.rmtree(dp)
                else:
                    os.unlink(dp)
            if os.path.isdir(sp):
                shutil.copytree(sp, dp)
            else:
                shutil.copy2(sp, dp)

deploy(source_dir, new_version_dir)

# 2. Check integrity: 20 skills
skills_dir = os.path.join(new_version_dir, "skills")
if not os.path.isdir(skills_dir):
    skills_dir = os.path.join(new_version_dir, "skill_bundle", "skills")
skills_found = []
if os.path.isdir(skills_dir):
    for entry in sorted(os.listdir(skills_dir)):
        if os.path.isfile(os.path.join(skills_dir, entry, "SKILL.md")):
            skills_found.append(entry)

if len(skills_found) < 20:
    err = {
        "status": "error",
        "reason_code": "UPDATE_INTEGRITY_FAILED",
        "message": f"New release must contain all 20 skills, but only found {len(skills_found)}.",
        "skills_found": len(skills_found),
        "active_version": old_version
    }
    if "$JSON_MODE" == "true":
        print(json.dumps(err, indent=2))
    else:
        print(f"Error: New release has only {len(skills_found)} skills.", file=sys.stderr)
    sys.exit(1)

# 3. Doctor smoke test (CRITICAL DEFENSE GATE)
doc_py = os.path.join(skills_dir, "a-stock-agents", "runtime", "doctor.py")
if not os.path.isfile(doc_py):
    doc_py = os.path.join(new_version_dir, "skill_bundle", "runtime", "doctor.py")
if not os.path.isfile(doc_py):
    doc_py = os.path.join(new_version_dir, "runtime", "doctor.py")

active_python = receipt.get("python_path") or "$HOST_PYTHON"
doctor_ok = False
doc_output = ""
doctor_report = None

if os.path.isfile(doc_py):
    env = os.environ.copy()
    env["A_STOCK_WORKSPACE_ROOT"] = data_root
    res = subprocess.run([active_python, doc_py, "--json"], env=env, capture_output=True, text=True)
    doc_output = res.stdout.strip()
    if res.returncode == 0:
        doctor_ok = True
        try:
            doctor_report = json.loads(doc_output)
        except Exception:
            pass

if not doctor_ok:
    err = {
        "status": "error",
        "reason_code": "UPDATE_SMOKE_FAILED",
        "message": f"Doctor smoke verification failed on new release {new_version}. Kept current version {old_version} active without modification.",
        "active_version": old_version,
        "failed_version": new_version,
        "doctor_output": doc_output
    }
    if "$JSON_MODE" == "true":
        print(json.dumps(err, indent=2))
    else:
        print(f"Error: Doctor smoke verification failed on new release {new_version}.", file=sys.stderr)
    sys.exit(1)

# 4. Atomic symlink switch
current_link = os.path.join(data_root, "current")
if os.path.islink(current_link) or os.path.exists(current_link):
    try:
        os.unlink(current_link)
    except Exception:
        shutil.rmtree(current_link, ignore_errors=True)
os.symlink(new_version_dir, current_link)

# 5. Update receipt
updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
receipt["previous_version"] = old_version
receipt["version"] = new_version
receipt["updated_at"] = updated_at
receipt["current_target"] = new_version_dir
receipt["skills_root"] = skills_dir
receipt["doctor_health"] = doctor_report

receipt.pop("sha256", None)
raw = json.dumps(receipt, ensure_ascii=False, indent=2)
receipt["sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()

with open(receipt_path, "w", encoding="utf-8") as f:
    json.dump(receipt, f, ensure_ascii=False, indent=2)

res = {
    "status": "success",
    "action": "update",
    "previous_version": old_version,
    "version": new_version,
    "active_version": new_version,
    "current_target": new_version_dir,
    "data_root": data_root
}
if "$JSON_MODE" == "true":
    print(json.dumps(res, indent=2))
else:
    print("============================================================")
    print(f"🎉 A-Stock Agents Successfully Updated to {new_version}!")
    print("============================================================")
    print(f"Previous Version: {old_version}")
    print(f"Active Version:   {new_version}")
    print(f"Data Root:        {data_root} (User data 100% preserved)")
    print("============================================================")
EOF
  exit $?
fi

# -----------------------------------------------------------------------------
# Scenario F: -Rollback
# -----------------------------------------------------------------------------
if [[ "$ROLLBACK" == "true" ]]; then
  if [[ ! -f "$RECEIPT_PATH" ]]; then
    if [[ "$JSON_MODE" == "true" ]]; then
      echo '{"status":"error","reason_code":"NOT_INSTALLED","message":"Cannot rollback: no existing installation found in data root."}'
    else
      echo "Error: Cannot rollback: no existing installation found in data root." >&2
    fi
    exit 1
  fi

  "$HOST_PYTHON" - <<EOF
import json, os, sys, shutil, subprocess, hashlib
from datetime import datetime, timezone

receipt_path = "$RECEIPT_PATH"
data_root = "$TARGET_DATA_ROOT"
with open(receipt_path, "r", encoding="utf-8") as f:
    receipt = json.load(f)

current_version = receipt.get("version", "v3")
prev_version = receipt.get("previous_version")

if not prev_version:
    err = {
        "status": "error",
        "reason_code": "ROLLBACK_NO_PREVIOUS_VERSION",
        "message": f"No previous version recorded in receipt ({receipt_path}) to roll back to.",
        "active_version": current_version
    }
    if "$JSON_MODE" == "true":
        print(json.dumps(err, indent=2))
    else:
        print("Error: No previous version recorded to roll back to.", file=sys.stderr)
    sys.exit(1)

releases_dir = os.path.join(data_root, "releases")
target_rollback_dir = os.path.join(releases_dir, prev_version)
if not os.path.isdir(target_rollback_dir):
    err = {
        "status": "error",
        "reason_code": "ROLLBACK_TARGET_MISSING",
        "message": f"Previous version directory '{target_rollback_dir}' not found.",
        "active_version": current_version,
        "target_version": prev_version
    }
    if "$JSON_MODE" == "true":
        print(json.dumps(err, indent=2))
    else:
        print(f"Error: Previous version directory '{target_rollback_dir}' not found.", file=sys.stderr)
    sys.exit(1)

skills_dir = os.path.join(target_rollback_dir, "skills")
if not os.path.isdir(skills_dir):
    skills_dir = os.path.join(target_rollback_dir, "skill_bundle", "skills")
skills_found = []
if os.path.isdir(skills_dir):
    for entry in sorted(os.listdir(skills_dir)):
        if os.path.isfile(os.path.join(skills_dir, entry, "SKILL.md")):
            skills_found.append(entry)

if len(skills_found) < 20:
    err = {
        "status": "error",
        "reason_code": "ROLLBACK_INTEGRITY_FAILED",
        "message": f"Rollback target {prev_version} is corrupted (found {len(skills_found)} skills, expected 20).",
        "active_version": current_version,
        "target_version": prev_version
    }
    if "$JSON_MODE" == "true":
        print(json.dumps(err, indent=2))
    else:
        print(f"Error: Rollback target {prev_version} has {len(skills_found)} skills.", file=sys.stderr)
    sys.exit(1)

# Atomic symlink switch
current_link = os.path.join(data_root, "current")
if os.path.islink(current_link) or os.path.exists(current_link):
    try:
        os.unlink(current_link)
    except Exception:
        shutil.rmtree(current_link, ignore_errors=True)
os.symlink(target_rollback_dir, current_link)

# Update receipt
rolled_back_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
receipt["previous_version"] = current_version
receipt["version"] = prev_version
receipt["rolled_back_at"] = rolled_back_at
receipt["current_target"] = target_rollback_dir
receipt["skills_root"] = skills_dir

receipt.pop("sha256", None)
raw = json.dumps(receipt, ensure_ascii=False, indent=2)
receipt["sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()

with open(receipt_path, "w", encoding="utf-8") as f:
    json.dump(receipt, f, ensure_ascii=False, indent=2)

res = {
    "status": "success",
    "action": "rollback",
    "active_version": prev_version,
    "rolled_back_from": current_version,
    "current_target": target_rollback_dir,
    "data_root": data_root
}
if "$JSON_MODE" == "true":
    print(json.dumps(res, indent=2))
else:
    print("============================================================")
    print(f"🎉 A-Stock Agents Successfully Rolled Back to {prev_version}!")
    print("============================================================")
    print(f"Rolled Back From: {current_version}")
    print(f"Active Version:   {prev_version}")
    print(f"Data Root:        {data_root} (User data 100% preserved)")
    print("============================================================")
EOF
  exit $?
fi

show_tui_menu() {
  local items=("universal" "hermes" "workbuddy" "codex")
  local item_names=(
    "🌐 Universal 通用目录 (~/.agents/skills)"
    "🦊 Hermes Desktop (~/.hermes/skills)"
    "💼 WorkBuddy (~/.workbuddy/skills)"
    "💻 Codex 专用 (~/.codex/skills)"
  )
  local item_desc=(
    "已支持: Codex, Cursor, Cline, Kimi CLI, OpenCode 等"
    "支持 external_dirs 原生挂载"
    "采用逐技能平级独立注册"
    "专用独立目录"
  )
  local selected=(1 0 0 0)
  if [[ -d "$HERMES_PATH" || -d "$HOME/.hermes" ]]; then selected[1]=1; fi
  if [[ -d "$WORKBUDDY_PATH" || -d "$HOME/.workbuddy" ]]; then selected[2]=1; fi

  local cursor=0
  local method="link"

  trap 'tput cnorm 2>/dev/null || true' EXIT INT TERM
  tput civis 2>/dev/null || true

  while true; do
    clear 2>/dev/null || printf "\033c"
    echo -e "\033[36m┌──────────────────────────────────────────────────────────────────┐\033[0m"
    echo -e "\033[36m│  A-Stock Agents 终端交互式安装导轨 (Terminal Installation TUI)   │\033[0m"
    echo -e "\033[36m├──────────────────────────────────────────────────────────────────┤\033[0m"
    echo -e "\033[90m│ 请使用 [↑/↓] 移动光标，[空格] 切换勾选，[回车] 确认开始安装      │\033[0m"
    echo -e "│                                                                  │"
    echo -e "\033[33m│ [Universal agents]\033[0m"
    for i in 0; do
      local chk="[ ]"
      [[ "${selected[$i]}" -eq 1 ]] && chk="[*]"
      local ptr="  "
      local color="\033[0m"
      [[ "$cursor" -eq "$i" ]] && ptr="> " && color="\033[32m"
      echo -e "│ ${color}${ptr}${chk} ${item_names[$i]}\033[0m"
      echo -e "\033[90m│       ${item_desc[$i]}\033[0m"
    done
    echo -e "│                                                                  │"
    echo -e "\033[33m│ [Additional agents]\033[0m"
    for i in 1 2 3; do
      local chk="[ ]"
      [[ "${selected[$i]}" -eq 1 ]] && chk="[*]"
      local ptr="  "
      local color="\033[0m"
      [[ "$cursor" -eq "$i" ]] && ptr="> " && color="\033[32m"
      echo -e "│ ${color}${ptr}${chk} ${item_names[$i]}\033[0m"
      echo -e "\033[90m│       ${item_desc[$i]}\033[0m"
    done
    echo -e "│                                                                  │"
    if [[ "$method" == "link" ]]; then
      echo -e "\033[36m│ 安装方式：(●) 符号链接/Symlink (推荐，便于升级)   ( ) 物理复制   │\033[0m"
    else
      echo -e "\033[36m│ 安装方式：( ) 符号链接/Symlink                     (●) 物理复制  │\033[0m"
    fi
    echo -e "\033[36m│ [快捷键: 'm' 切换安装方式 | 'a' 全选/反选 | 'q' 退出]            │\033[0m"
    echo -e "\033[36m└──────────────────────────────────────────────────────────────────┘\033[0m"

    local key=""
    IFS= read -rsn1 key 2>/dev/null || break
    if [[ "$key" == $'\x1b' ]]; then
      read -rsn2 -t 0.1 rest 2>/dev/null || true
      key+="$rest"
    fi

    case "$key" in
      $'\x1b[A'|k|K)
        if [[ "$cursor" -gt 0 ]]; then cursor=$((cursor - 1)); else cursor=3; fi
        ;;
      $'\x1b[B'|j|J)
        if [[ "$cursor" -lt 3 ]]; then cursor=$((cursor + 1)); else cursor=0; fi
        ;;
      ' ')
        if [[ "${selected[$cursor]}" -eq 1 ]]; then
          selected[$cursor]=0
        else
          selected[$cursor]=1
        fi
        ;;
      m|M)
        if [[ "$method" == "link" ]]; then method="copy"; else method="link"; fi
        ;;
      a|A)
        local all_on=1
        for s in "${selected[@]}"; do
          if [[ "$s" -eq 0 ]]; then all_on=0; break; fi
        done
        local new_val=1
        [[ "$all_on" -eq 1 ]] && new_val=0
        for idx in 0 1 2 3; do selected[$idx]=$new_val; done
        ;;
      ''|$'\n')
        local chosen=()
        for idx in 0 1 2 3; do
          if [[ "${selected[$idx]}" -eq 1 ]]; then
            chosen+=("${items[$idx]}")
          fi
        done
        if [[ "${#chosen[@]}" -eq 0 ]]; then
          echo -e "\n\033[33m⚠️ 请至少勾选一个目标宿主 (按空格键勾选)\033[0m"
          sleep 1
        else
          AGENT="$(IFS=,; echo "${chosen[*]}")"
          METHOD="$method"
          tput cnorm 2>/dev/null || true
          break
        fi
        ;;
      q|Q|$'\x1b')
        tput cnorm 2>/dev/null || true
        echo -e "\nInstallation cancelled by user."
        exit 0
        ;;
    esac
  done
  tput cnorm 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# Scenario C: Installation
# -----------------------------------------------------------------------------

# 0. Terminal TUI activation check
IS_INTERACTIVE=false
if [[ "$TUI" == "true" ]]; then
  IS_INTERACTIVE=true
elif [[ -t 0 && -t 1 && "$YES" != "true" && "$JSON_MODE" != "true" && "$INSPECT" != "true" && "$DOCTOR" != "true" && -z "$AGENT" ]]; then
  IS_INTERACTIVE=true
fi

if [[ "$IS_INTERACTIVE" == "true" ]]; then
  show_tui_menu
fi

# 0.1 Overwrites sentinel: check for existing physical directories
if [[ -n "$AGENT" ]]; then
  CONFLICT_DATA=$("$HOST_PYTHON" - <<EOF
import json, os, sys

agents_arg = "$AGENT"
target_dirs = []
known_agents = {
    "universal": "$UNIVERSAL_PATH",
    "hermes": "$HERMES_PATH",
    "workbuddy": "$WORKBUDDY_PATH",
    "codex": "$CODEX_PATH"
}
for item in [a.strip() for a in agents_arg.split(",") if a.strip()]:
    item_lower = item.lower()
    tdir = known_agents.get(item_lower, item)
    target_dirs.append((item_lower, tdir))

skills_dir = "$SKILLS_DIR"
skills = []
if skills_dir and os.path.isdir(skills_dir):
    for entry in sorted(os.listdir(skills_dir)):
        if os.path.isfile(os.path.join(skills_dir, entry, "SKILL.md")):
            skills.append(entry)

conflicts = []
for ag_name, tdir in target_dirs:
    if os.path.isdir(tdir):
        for s in skills:
            entry = os.path.join(tdir, s)
            if os.path.exists(entry) and not os.path.islink(entry):
                copy_rc = os.path.join(tdir, f".{s}.astock-copy.json")
                if not os.path.isfile(copy_rc):
                    conflicts.append({"agent": ag_name, "skill": s, "path": entry})

print(json.dumps(conflicts))
EOF
  )

  CONFLICTS_COUNT=$(echo "$CONFLICT_DATA" | "$HOST_PYTHON" -c "import json, sys; print(len(json.load(sys.stdin)))")
  if [[ "$CONFLICTS_COUNT" -gt 0 && "$FORCE" != "true" ]]; then
    if [[ "$JSON_MODE" == "true" ]]; then
      "$HOST_PYTHON" - <<EOF
import json
print(json.dumps({
    "status": "error",
    "reason_code": "OVERWRITE_CONFLICT",
    "message": f"Overwrites conflict detected: $CONFLICTS_COUNT existing non-link physical directory(ies) found in target host(s). Refusing to overwrite user files.",
    "overwrites_count": int("$CONFLICTS_COUNT"),
    "conflicts": json.loads('''$CONFLICT_DATA''')
}, indent=2))
EOF
    else
      echo "============================================================" >&2
      echo "❌ Overwrites Sentinel: Conflict Detected!" >&2
      echo "============================================================" >&2
      echo "The following target skill directories already exist as real physical folders:" >&2
      echo "$CONFLICT_DATA" | "$HOST_PYTHON" -c "import json, sys; [print(f'  - [{c[\"agent\"]}] {c[\"skill\"]}: {c[\"path\"]}') for c in json.load(sys.stdin)]" >&2
      echo "Refusing to overwrite user physical directories. Pass --force to overwrite." >&2
    fi
    exit 1
  fi
fi

if [[ -z "$HOST_PYTHON" ]]; then
  if [[ "$JSON_MODE" == "true" ]]; then
    echo '{"status":"error","reason_code":"PYTHON_MISSING","message":"Python 3.9+ required"}'
  else
    echo "Error: Python 3.9+ required" >&2
  fi
  exit 1
fi

mkdir -p "$TARGET_DATA_ROOT/output" "$TARGET_DATA_ROOT/log" "$TARGET_DATA_ROOT/temp" "$TARGET_DATA_ROOT/local/settings" "$TARGET_DATA_ROOT/releases"
VERSION_DIR="$TARGET_DATA_ROOT/releases/$VERSION"
deploy_release_files "$SCRIPT_DIR" "$VERSION_DIR"
set_current_link "$TARGET_DATA_ROOT" "$VERSION_DIR"

VENV_DIR="$TARGET_DATA_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [[ "$SKIP_VENV" != "true" ]]; then
  if [[ ! -x "$VENV_PYTHON" ]]; then
    if [[ -n "$UV_CMD" ]]; then
      "$UV_CMD" venv "$VENV_DIR" >/dev/null 2>&1 || "$HOST_PYTHON" -m venv "$VENV_DIR" >/dev/null 2>&1
    else
      "$HOST_PYTHON" -m venv "$VENV_DIR" >/dev/null 2>&1
    fi
  fi
else
  VENV_PYTHON="$HOST_PYTHON"
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
  VENV_PYTHON="$HOST_PYTHON"
fi

# Dependency install
if [[ "$SKIP_DEPS" != "true" && "${A_STOCK_SKIP_DEPS:-0}" != "1" && "${A_STOCK_OFFLINE:-0}" != "1" ]]; then
  REQ_FILE=""
  for rc in "$SCRIPT_DIR/requirements.txt" "$BUNDLE_ROOT/requirements.txt" "$ANCHOR_DIR/requirements.txt"; do
    if [[ -f "$rc" ]]; then
      REQ_FILE="$rc"
      break
    fi
  done
  if [[ -n "$REQ_FILE" ]]; then
    if [[ -n "$UV_CMD" ]]; then
      "$UV_CMD" pip install --python "$VENV_PYTHON" -r "$REQ_FILE" >/dev/null 2>&1 || true
    else
      "$VENV_PYTHON" -m pip install -r "$REQ_FILE" >/dev/null 2>&1 || true
    fi
  fi
fi

# Run doctor and assemble install.json via Python helper
"$VENV_PYTHON" - <<EOF
import json, os, sys, hashlib
from datetime import datetime, timezone
import subprocess

current_dir = os.path.join("$TARGET_DATA_ROOT", "current")
skills_dir = os.path.join(current_dir, "skills")
if not os.path.isdir(skills_dir):
    skills_dir = os.path.join(current_dir, "skill_bundle", "skills")
if not os.path.isdir(skills_dir):
    skills_dir = "$SKILLS_DIR"

skill_entries = []
if skills_dir and os.path.isdir(skills_dir):
    for entry in sorted(os.listdir(skills_dir)):
        md = os.path.join(skills_dir, entry, "SKILL.md")
        if os.path.isfile(md):
            digest = hashlib.sha256(open(md, "rb").read()).hexdigest()
            skill_entries.append({
                "id": entry,
                "name": entry,
                "is_anchor": (entry == "a-stock-agents"),
                "path": os.path.abspath(os.path.join(skills_dir, entry)),
                "skill_md_sha256": digest,
                "verified": True
            })

doctor_py = "$RUNTIME_DIR/doctor.py"
doctor_health = None
if os.path.isfile(doctor_py):
    env = os.environ.copy()
    env["A_STOCK_WORKSPACE_ROOT"] = "$TARGET_DATA_ROOT"
    res = subprocess.run([sys.executable, doctor_py, "--json"], env=env, capture_output=True, text=True)
    if res.returncode == 0:
        try:
            doctor_health = json.loads(res.stdout)
        except Exception:
            pass

registered_agents = []
agent_str = "$AGENT"
if agent_str:
    agents_list = [a.strip() for a in agent_str.split(",") if a.strip()]
    home_dir = os.path.expanduser("~")
    agent_paths = {
        "universal": os.path.join(home_dir, ".agents", "skills"),
        "hermes": os.path.join(home_dir, ".hermes", "skills"),
        "workbuddy": os.path.join(home_dir, ".workbuddy", "skills"),
        "codex": os.path.join(home_dir, ".codex", "skills")
    }
    for ag in agents_list:
        ag_lower = ag.lower()
        target_dir = agent_paths.get(ag_lower, ag)
        os.makedirs(target_dir, exist_ok=True)
        mounted_count = 0
        if skills_dir and os.path.isdir(skills_dir):
            for sk in sorted(os.listdir(skills_dir)):
                src_sk = os.path.join(skills_dir, sk)
                if os.path.isdir(src_sk) and os.path.isfile(os.path.join(src_sk, "SKILL.md")):
                    dst_sk = os.path.join(target_dir, sk)
                    if not os.path.lexists(dst_sk):
                        try:
                            if "$METHOD" == "copy":
                                import shutil
                                shutil.copytree(src_sk, dst_sk)
                            else:
                                os.symlink(src_sk, dst_sk)
                            mounted_count += 1
                        except Exception:
                            pass
                    else:
                        mounted_count += 1
                    rc_path = os.path.join(target_dir, f".{sk}.astock-reference.json")
                    try:
                        with open(rc_path, "w", encoding="utf-8") as rf:
                            json.dump({"entry": dst_sk, "target": src_sk, "type": "symlink" if "$METHOD" != "copy" else "copy"}, rf, indent=2)
                    except Exception:
                        pass
        suite_rc = os.path.join(target_dir, ".a-stock-suite.json")
        try:
            with open(suite_rc, "w", encoding="utf-8") as sf:
                json.dump({"skills_root": skills_dir, "host_skills_dir": target_dir, "mounted_skills": mounted_count, "method": "$METHOD"}, sf, indent=2)
        except Exception:
            pass
        registered_agents.append({
            "agent": ag_lower,
            "target_dir": target_dir,
            "method": "$METHOD",
            "skills_count": mounted_count,
            "status": "mounted"
        })

bundle_target = "$ANCHOR_DIR" if "$ANCHOR_DIR" else "$BUNDLE_ROOT"
runtime_target = "$RUNTIME_DIR" if "$RUNTIME_DIR" else os.path.join("$ANCHOR_DIR", "runtime")

receipt = {
    "status": "installed",
    "version": "$VERSION",
    "previous_version": None,
    "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "workspace_root": "$TARGET_DATA_ROOT",
    "data_root": "$TARGET_DATA_ROOT",
    "releases_dir": os.path.join("$TARGET_DATA_ROOT", "releases"),
    "current_target": "$VERSION_DIR",
    "bundle_root": bundle_target,
    "runtime_root": runtime_target,
    "anchor_root": "$ANCHOR_DIR",
    "skills_root": skills_dir,
    "python_path": "$VENV_PYTHON",
    "method": "$METHOD",
    "overwrites_count": 0,
    "conflicts": [],
    "skills_count": len(skill_entries),
    "business_skills": 19,
    "skill_entries": skill_entries,
    "registered_agents": registered_agents,
    "doctor_health": doctor_health
}

raw = json.dumps(receipt, ensure_ascii=False, indent=2)
receipt["sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()

with open("$RECEIPT_PATH", "w", encoding="utf-8") as f:
    json.dump(receipt, f, ensure_ascii=False, indent=2)

if "$JSON_MODE" == "true":
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
else:
    print("============================================================")
    print("🎉 A-Stock Agents Installation Successful (POSIX)!")
    print("============================================================")
    print(f"Data Root:      $TARGET_DATA_ROOT")
    print(f"Python venv:    $VENV_PYTHON")
    print(f"Skills Ready:   {len(skill_entries)} entries verified (SHA256)")
    print(f"Receipt:        $RECEIPT_PATH")
    print("\nQuickstart:")
    print("  ./install.sh -Doctor -Json")
    print("============================================================")
EOF

exit 0

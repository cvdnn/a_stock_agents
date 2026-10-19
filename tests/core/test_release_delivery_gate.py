# -*- coding: utf-8 -*-
"""P0-02 Release 交付链路门禁（core 档）。

背景：docs/audits/2026-10-15-skill-suite-delivery-assessment.md 定位的交付盲区——
技能在开发仓库算得对，但「打出来的包在宿主机器上装得上、找得到、跑得起来」
此前没有任何自动化保障。本文件补齐宿主可见契约的正向/反向断言：

- 20 个 SKILL.md 的 YAML frontmatter 可解析、name==目录名、description 非空
  （frontmatter 写坏会让技能在宿主侧静默消失，P0 业务门禁对此不可见）；
- doctor / run_skill 入口契约（stdout 合法 JSON、退出码、错误体结构）；
- 真实启动器冒烟与失败退出码透传（不再绕过 bin/astock*）；
- check_workspace_health 直接调用断言（替代手写复制其条件）；
- skill_resource 路径逃逸双分支；
- package_project 关键行为：后缀白名单、私有文件排除、sha256 sidecar、
  host_adapters 随包、zip POSIX 执行位、INSTALL.json 全字段、根三件套、
  打包审计记录。

全部断言必然执行（无 `if 条件: assert`）；打包产物经 module fixture 只构建一次。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from core.workspace import SKILLS_ROOT, RUNTIME_ROOT, check_workspace_health, skill_resource

ROOT = Path(__file__).resolve().parents[2]
IS_WINDOWS = sys.platform == "win32"
RUNTIME_ENTRY = ROOT / "skill_bundle" / "runtime"

# 与 tools/packaging/common.py 的 ALLOWED_SUFFIXES 保持一致（导入它本身即契约的一部分）
from tools.packaging.common import ALLOWED_SUFFIXES, _full_extra_requirements


def _run(args, cwd=None, timeout=180):
    """子进程执行入口（继承隔离环境变量，UTF-8 解码）。"""
    return subprocess.run(
        [str(a) for a in args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd or ROOT), timeout=timeout,
    )


# ==============================================================================
# 1. SKILL.md frontmatter 契约（宿主技能发现的唯一输入）
# ==============================================================================

SKILL_DIRECTORIES = sorted(p.parent for p in SKILLS_ROOT.glob("*/SKILL.md"))


def _parse_frontmatter(skill_dir: Path) -> dict:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---"), f"{skill_dir.name}: frontmatter fence missing"
    end = text.find("\n---", 3)
    assert end > 0, f"{skill_dir.name}: frontmatter fence unterminated"
    data = yaml.safe_load(text[3:end])
    assert isinstance(data, dict), f"{skill_dir.name}: frontmatter is not a mapping"
    return data


@pytest.mark.parametrize("skill_dir", SKILL_DIRECTORIES, ids=lambda p: p.name)
def test_skill_frontmatter_parses_and_matches_directory(skill_dir: Path):
    """每个 SKILL.md：YAML 可解析、name 与目录一致、description 非空。

    这三项是 Codex/Hermes/WorkBuddy 技能发现的输入契约；写坏任意一项，
    技能在宿主侧静默消失，而 P0 业务门禁不可见。
    """
    data = _parse_frontmatter(skill_dir)
    assert data["name"] == skill_dir.name, (
        f"frontmatter name {data.get('name')!r} != directory {skill_dir.name!r}"
    )
    description = data.get("description")
    assert isinstance(description, str) and description.strip(), (
        f"{skill_dir.name}: description missing/empty"
    )


def test_skill_catalog_counts_match_manifest_and_disk():
    """20 个入口 / 19 项业务技能：磁盘与权威清单双向对齐。"""
    assert len(SKILL_DIRECTORIES) == 20
    ids = {item["id"] for item in json.loads(
        (SKILLS_ROOT.parent / "assets" / "config" / "skills_manifest.json").read_text(encoding="utf-8")
    )["skills"]}
    assert len(ids) == 19
    assert {d.name for d in SKILL_DIRECTORIES} == ids | {"a-stock-agents"}


# ==============================================================================
# 2. doctor / run_skill 入口契约（Release 落地后的自检与执行入口）
# ==============================================================================

def test_doctor_outputs_valid_health_json_and_zero_exit():
    """doctor.py：stdout 必须是合法 JSON 健康报告且退出码为 0（bootstrap 正向一并覆盖）。"""
    result = _run([sys.executable, RUNTIME_ENTRY / "doctor.py"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    health = json.loads(result.stdout)
    assert health["is_healthy"] is True
    assert health["total_skills"] == 20 and health["business_skills"] == 19


def test_run_skill_entrypoint_contract_matrix():
    """run_skill.py 六场景入口契约（并行冷启动，见 test_custom_output 同款手法）。

    并发安全论证：全部为只读/失败路径命令（--list、parser.error、未注册技能），
    不写用户池；未知技能的审计日志经 A_STOCK_LOG_DIR 落在进程级隔离临时根。
    """
    from concurrent.futures import ThreadPoolExecutor

    run_skill = RUNTIME_ENTRY / "run_skill.py"
    scenarios = [
        ("list", [sys.executable, run_skill, "--list"], "exit0+health-json"),
        ("no-skill", [sys.executable, run_skill], "exit2"),
        ("params-not-json", [sys.executable, run_skill, "astock-data-feed", "--params", "not-json"], "exit2"),
        ("params-not-object", [sys.executable, run_skill, "astock-data-feed", "--params", "[1,2,3]"], "exit2"),
        ("params-string", [sys.executable, run_skill, "astock-data-feed", "--params", '"string"'], "exit2"),
        ("unknown-skill", [sys.executable, run_skill, "no-such-skill", "--json"], "exit1+error-json"),
    ]
    with ThreadPoolExecutor(max_workers=len(scenarios)) as pool:
        futures = {name: pool.submit(_run, cmd) for name, cmd, _ in scenarios}
        results = {name: fut.result() for name, fut in futures.items()}

    res = results["list"]
    assert res.returncode == 0, f"[list] stderr: {res.stderr}"
    payload = json.loads(res.stdout)
    assert payload["is_healthy"] is True and payload["cli_launcher"] is True

    for name in ("no-skill", "params-not-json", "params-not-object", "params-string"):
        assert results[name].returncode == 2, f"[{name}] expected exit 2"

    res = results["unknown-skill"]
    assert res.returncode == 1, "[unknown-skill] expected exit 1 (fail-closed)"
    payload = json.loads(res.stdout)
    assert payload["status"] == "error"
    assert payload["skill_id"] == "no-such-skill"
    assert payload.get("error")


# ==============================================================================
# 3. 真实启动器冒烟（不再绕过 bin/astock*；子进程冷启动重，同批并行执行）
# ==============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Windows 启动器 (.ps1/.cmd) 仅在 win32 实测")
def test_windows_launchers_contract_matrix():
    """bin/astock.ps1 与 bin/astock.cmd 真实执行 + 失败退出码透传（并行冷启动）。

    并发安全论证：version 只读；坏子命令走 argparse error，不写盘。
    """
    from concurrent.futures import ThreadPoolExecutor

    ps1 = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
           "-File", str(ROOT / "bin" / "astock.ps1")]
    cmd = ["cmd", "/c", str(ROOT / "bin" / "astock.cmd")]
    scenarios = [
        ("ps1-version-json", ps1 + ["version", "--json"], "exit0+version-json"),
        ("cmd-version-json", cmd + ["version", "--json"], "exit0"),
        ("ps1-bad-command", ps1 + ["definitely-not-a-command"], "exit2"),
    ]
    with ThreadPoolExecutor(max_workers=len(scenarios)) as pool:
        futures = {name: pool.submit(_run, cmd_args) for name, cmd_args, _ in scenarios}
        results = {name: fut.result() for name, fut in futures.items()}

    res = results["ps1-version-json"]
    assert res.returncode == 0, f"[ps1-version] stderr: {res.stderr}"
    payload = json.loads(res.stdout)
    assert payload["status"] == "active" and payload["version"]

    assert results["cmd-version-json"].returncode == 0, \
        f"[cmd-version] stderr: {results['cmd-version-json'].stderr}"

    assert results["ps1-bad-command"].returncode == 2, "启动器必须透传 argparse 失败退出码"


@pytest.mark.skipif(IS_WINDOWS, reason="POSIX 启动器需 bash，在 win32 跳过")
def test_launcher_smoke_posix_sh():
    result = _run(["bash", ROOT / "bin" / "astock", "version", "--json"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert json.loads(result.stdout)["status"] == "active"


@pytest.mark.skipif(IS_WINDOWS, reason="退出码透传仅在当前平台启动器上实测")
def test_launcher_propagates_failure_exit_code_posix():
    result = _run(["bash", ROOT / "bin" / "astock", "definitely-not-a-command"])
    assert result.returncode != 0


# ==============================================================================
# 4. check_workspace_health 直接调用（替代手写复制其条件）
# ==============================================================================

def test_check_workspace_health_returns_full_contract():
    """直接调用并断言完整返回结构——此前测试手写复制其条件，逻辑改坏也全绿。"""
    health = check_workspace_health()
    expected_keys = {
        "package_root", "workspace_root", "skills_root", "total_skills",
        "business_skills", "skills_manifest", "cli_launcher", "is_healthy",
    }
    assert set(health) == expected_keys
    assert health["is_healthy"] is True
    assert health["total_skills"] == 20
    assert health["business_skills"] == 19
    assert health["skills_manifest"] is True
    assert health["cli_launcher"] is True
    assert Path(health["package_root"]) == SKILLS_ROOT.parent
    assert Path(health["skills_root"]) == SKILLS_ROOT
    assert Path(health["package_root"], "runtime", "cli.py").is_file()


# ==============================================================================
# 5. skill_resource 路径防逃逸（宿主读取技能资产的唯一入口）
# ==============================================================================

def test_skill_resource_rejects_invalid_skill_identifier():
    with pytest.raises(ValueError, match="Invalid skill identifier"):
        skill_resource("../evil", "")


def test_skill_resource_blocks_escape_within_valid_skill():
    with pytest.raises(ValueError, match="escapes skill"):
        skill_resource("astock-data-feed", "../../local/settings")


def test_skill_resource_resolves_valid_paths():
    base = skill_resource("astock-data-feed")
    assert base == (SKILLS_ROOT / "astock-data-feed").resolve()
    doc = skill_resource("astock-data-feed", "SKILL.md")
    assert doc.is_file()


# ==============================================================================
# 6. package_project 关键行为（module fixture 只构建一次）
# ==============================================================================

@pytest.fixture(scope="module")
def codex_archive(tmp_path_factory):
    """构建一次 codex 平台候选归档（日志重定向到临时目录，不写真实 log/）。"""
    from tools.packaging import common
    build_dir = tmp_path_factory.mktemp("release-gate")
    original = common.get_log_path
    common.get_log_path = lambda *args, **kwargs: build_dir / "build.log"
    try:
        destination = common.package_project(build_dir / "candidate.zip", platform="codex")
    finally:
        common.get_log_path = original
    return destination


@pytest.fixture(scope="module")
def extracted_codex_bundle(codex_archive: Path, tmp_path_factory) -> Path:
    """module 级别只解压一次 codex_archive，大幅度提升宿主模拟与解压测试效率，减少重复 I/O。"""
    extract_dir = tmp_path_factory.mktemp("extracted-codex-bundle")
    with zipfile.ZipFile(codex_archive) as z:
        z.extractall(extract_dir)
    return extract_dir


def test_archive_includes_host_adapters_for_platform(codex_archive: Path):
    """platform=codex 时 host_adapters 4 件套必须随包（漏拷会让宿主接入无从下手）。"""
    with zipfile.ZipFile(codex_archive) as archive:
        names = set(archive.namelist())
    for required in ("host_adapters/references.py", "host_adapters/host.py",
                     "host_adapters/codex.py", "host_adapters/windows_junction.ps1"):
        assert required in names, f"host adapter missing from release: {required}"


def test_archive_root_files_requirements_license_install(codex_archive: Path):
    with zipfile.ZipFile(codex_archive) as archive:
        names = set(archive.namelist())
        requirements = archive.read("requirements.txt")
    assert "INSTALL.json" in names
    assert "LICENSE" in names
    assert b"akshare" in requirements or b"pandas" in requirements


def test_archive_install_json_declares_candidate_contract(codex_archive: Path):
    """INSTALL.json 全字段：诚实声明候选态与未验证边界（不虚报宿主兼容）。"""
    with zipfile.ZipFile(codex_archive) as archive:
        instructions = json.loads(archive.read("INSTALL.json"))
    assert instructions["platform"] == "codex"
    assert instructions["mode"] == "release-candidate-collection"
    assert instructions["skill_entries"] == 20
    assert instructions["business_skills"] == 19
    assert instructions["runtime"] == "skill_bundle/runtime"
    assert instructions["skills"] == "skill_bundle/skills"
    assert instructions["host_scan_status"] == "unverified"
    assert instructions["native_import_verified"] is False
    assert isinstance(instructions["data_root"], str) and instructions["data_root"]
    assert isinstance(instructions["notice"], str) and instructions["notice"]
    # P0-04：依赖安装与运行契约（此前宿主装完后无任何安装指引）
    assert instructions["python_requirement"] == "3.9+"
    assert "requirements.txt" in instructions["dependency_install"]
    assert "requirements-full.txt" in instructions["dependency_install"]
    assert instructions["launcher"]["windows"].endswith("astock.ps1")
    assert instructions["launcher"]["posix"].endswith("astock")
    assert instructions["launcher"]["fallback"].endswith("cli.py")
    assert "doctor.py" in instructions["health_check"]


def test_archive_sha256_sidecar_matches_archive(codex_archive: Path):
    """sha256 sidecar 存在、格式标准（digest + 双空格 + 文件名 + 换行）且摘要一致。"""
    sidecar = Path(str(codex_archive) + ".sha256")
    assert sidecar.is_file()
    text = sidecar.read_text(encoding="utf-8")
    assert text.endswith("\n")
    digest, _, name = text.strip().partition("  ")
    assert name == codex_archive.name
    assert digest == hashlib.sha256(codex_archive.read_bytes()).hexdigest()


def test_archive_posix_executable_bits(codex_archive: Path):
    """runtime/astock 与 .sh 必须带 POSIX 执行位（0o755），普通文件 0o644。"""
    with zipfile.ZipFile(codex_archive) as archive:
        posix_launchers = [n for n in archive.namelist()
                           if Path(n).name == "astock" or n.endswith(".sh")]
        assert len(posix_launchers) >= 4, "expected runtime/astock + setup.sh scripts"
        for name in posix_launchers:
            info = archive.getinfo(name)
            assert info.create_system == 3, f"{name}: not a POSIX entry"
            assert (info.external_attr >> 16) & 0o755 == 0o755, f"{name}: missing exec bit"
        plain = archive.getinfo("skill_bundle/runtime/core/workspace.py")
        assert (plain.external_attr >> 16) & 0o755 == 0o644


def test_archive_entries_within_suffix_whitelist(codex_archive: Path):
    """白名单反向断言：归档内每个文件后缀必须命中 ALLOWED_SUFFIXES 或显式特例。"""
    # 无后缀合法条目仅两类：runtime/astock（POSIX 启动器）与 LICENSE；根四件套显式放行。
    allowed_basenames = {"astock", "LICENSE"}
    allowed_root_files = {"INSTALL.json", "requirements.txt", "requirements-full.txt", "install.ps1", "install.sh"}
    with zipfile.ZipFile(codex_archive) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename)
            if info.filename.startswith("host_adapters/"):
                assert name.suffix in {".py", ".ps1"}, info.filename
                continue
            assert name.suffix in ALLOWED_SUFFIXES or name.name in allowed_basenames \
                or info.filename in allowed_root_files, (
                f"file outside packaging whitelist: {info.filename}"
            )


def test_archive_excludes_private_and_env_and_keeps_relative_paths(codex_archive: Path):
    """.env*/config.yaml/私有根排除 + zip-slip 粗检（全部条目为相对安全路径）。"""
    forbidden_parts = {"local", "output", "log", "temp", ".agents", ".venv",
                       "__pycache__", "apps", "tests", "docs"}
    with zipfile.ZipFile(codex_archive) as archive:
        for info in archive.infolist():
            name = info.filename
            assert not name.startswith("/") and "\\" not in name, f"absolute/path entry: {name}"
            assert ".." not in Path(name).parts, f"traversal entry: {name}"
            assert not Path(name).name.startswith(".env"), f"private env leaked: {name}"
            assert Path(name).name != "config.yaml", f"private config leaked: {name}"
            assert not set(Path(name).parts) & forbidden_parts, f"private root leaked: {name}"


def test_packaging_audit_record_appended(tmp_path, monkeypatch):
    """打包必须写 JSONL 审计记录（含 sha256 与 host_installation_verified=False）。"""
    from tools.packaging import common
    log_file = tmp_path / "packaging.log"
    monkeypatch.setattr(common, "get_log_path", lambda *args, **kwargs: log_file)
    destination = common.package_project(tmp_path / "audit-candidate.zip", platform="collection")
    record = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["archive"].endswith("audit-candidate.zip")
    assert record["platform"] == "collection"
    assert record["private_roots_included"] is False
    assert record["host_installation_verified"] is False
    assert record["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.unlink()
    Path(str(destination) + ".sha256").unlink(missing_ok=True)


# ==============================================================================
# 6b. 依赖声明单一来源（P0-04）
# ==============================================================================

def test_dependency_declarations_have_single_source():
    """版本约束唯一声明处：根 pyproject.toml [full]；任何 requirements 文件纯引用。

    此前 MyTT / akshare-proxy-patch 仅由技能级手写清单声明（core 的
    fetch_technical.py 硬依赖 MyTT），akshare 版本口径两处冲突。
    """
    full = _full_extra_requirements()
    assert "akshare>=1.18.0" in full
    assert "MyTT>=2.9.0" in full
    assert "akshare-proxy-patch>=0.5.0" in full
    assert "efinance>=0.5.0" in full

    # 仓库内任何 requirements 文件不得再携带版本声明（含技能级）
    requirement_files = list(SKILLS_ROOT.rglob("requirements*.txt")) + \
        list((ROOT / "tools").rglob("requirements*.txt"))
    assert requirement_files, "expected at least the skill-level reference file"
    for req_file in requirement_files:
        text = req_file.read_text(encoding="utf-8")
        assert "-r " in text, f"{req_file}: 引用式 requirements 必须包含 -r 指向根清单"
        for pkg in ("MyTT", "akshare-proxy-patch", "akshare", "efinance", "pandas", "numpy"):
            assert not re.search(rf"^\s*{re.escape(pkg)}\s*[><=~!]", text, re.MULTILINE), (
                f"{req_file}: 依赖版本声明泄漏到非 SSOT 文件（{pkg}）"
            )

    # 根 requirements.txt 是 uv.lock 的 --no-dev 基础导出，不含 full extras
    root_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for pkg in ("MyTT", "akshare-proxy-patch", "akshare", "efinance"):
        assert pkg not in root_requirements, (
            f"根 requirements.txt（基础导出）不应包含 full extra 依赖：{pkg}"
        )


def test_archive_requirements_full_is_derived_from_pyproject(codex_archive: Path):
    """归档根 requirements-full.txt 为构建期派生物：内容与 pyproject [full] 一致。"""
    with zipfile.ZipFile(codex_archive) as archive:
        content = archive.read("requirements-full.txt").decode("utf-8")
    assert content.startswith("# Derived from pyproject.toml")
    assert "-r requirements.txt" in content
    for item in _full_extra_requirements():
        assert item in content, f"派生清单缺失 {item}"
    # 派生文件不得携带锁版本（锁定由 uv.lock 管理基础清单，extras 以约束形式派生）
    assert "==" not in content


def test_skill_requirements_reference_resolves_in_dev_and_release(codex_archive: Path):
    """技能级 requirements.txt 的 -r 引用在开发仓库与 Release 两种布局下均可解析。"""
    # 开发布局：skill_bundle/skills/astock-data-feed → ../../../requirements.txt = 仓库根
    skill_dir = SKILLS_ROOT / "astock-data-feed"
    text = (skill_dir / "requirements.txt").read_text(encoding="utf-8")
    reference = re.search(r"^-r\s+(\S+)", text, re.MULTILINE).group(1)
    resolved = (skill_dir / reference).resolve()
    assert resolved.is_file(), f"开发布局下 -r 引用失效: {resolved}"

    # Release 布局：归档内同一路径解析到归档根 requirements.txt
    with zipfile.ZipFile(codex_archive) as archive:
        archived_text = archive.read(
            "skill_bundle/skills/astock-data-feed/requirements.txt").decode("utf-8")
        assert "-r ../../../requirements.txt" in archived_text
        assert "requirements.txt" in archive.namelist()
        assert "requirements-full.txt" in archive.namelist()


# ==============================================================================
# 7. 宿主注册红线与三平台 shim（P0-03）
# ==============================================================================
# tools/host_adapters/host.py 是库模块（无 __main__ 入口），CLI 执行入口是三个平台
# shim（codex.py / hermes.py / workbuddy.py，各自 `from host import main`）。以下
# 用例全部经真实 shim 子进程驱动，天然覆盖「裸导入在脚本目录下可解析」。

HOST_ADAPTERS_DIR = ROOT / "tools" / "host_adapters"
PLATFORM_SHIMS = {
    "codex": HOST_ADAPTERS_DIR / "codex.py",
    "hermes": HOST_ADAPTERS_DIR / "hermes.py",
    "workbuddy": HOST_ADAPTERS_DIR / "workbuddy.py",
}


@pytest.fixture
def fake_release_bundle(tmp_path):
    """构造最小合法 Release bundle（distribution=release + 一个示例技能）。"""
    bundle = tmp_path / "release-bundle"
    (bundle / "skills" / "sample").mkdir(parents=True)
    (bundle / "skills" / "sample" / "SKILL.md").write_text(
        "---\nname: sample\ndescription: sample\n---\n", encoding="utf-8")
    (bundle / "bundle.json").write_text(
        json.dumps({"name": "a_stock_agents", "distribution": "release"}), encoding="utf-8")
    return bundle


def test_host_rejects_bundle_without_marker():
    """--bundle 指向无 bundle.json 的目录必须 exit 2（防误注册任意目录）。"""
    result = _run([sys.executable, PLATFORM_SHIMS["codex"], "--bundle", ROOT])
    assert result.returncode == 2
    assert "bundle.json missing" in result.stderr


def test_host_refuses_development_source_registration():
    """头号发布红线：开发源码（bundle.json 无 distribution=release）必须拒绝注册。

    AGENTS.md「不将开发源码注册到全局技能目录」的唯一技术执行点。
    """
    result = _run([sys.executable, PLATFORM_SHIMS["codex"], "--bundle", ROOT / "skill_bundle"])
    assert result.returncode == 2
    assert "Release required" in result.stderr
    assert "development source cannot be registered" in result.stderr


@pytest.mark.parametrize("platform,expected_mode", [
    ("codex", "reference-only"),
    ("hermes", "external_dirs"),
    ("workbuddy", "reference-only"),
])
def test_host_configured_target_modes_per_platform(fake_release_bundle, platform, expected_mode):
    """无 --entry 时三平台均只报告 configured_target 目标，且诚实声明未验证。"""
    result = _run([sys.executable, PLATFORM_SHIMS[platform], "--bundle", fake_release_bundle])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["status"] == "configured_target"
    assert payload["platform"] == platform
    assert payload["mode"] == expected_mode
    assert payload["source"].endswith("skills")
    assert payload["host_scan_status"] == "unverified"
    assert payload["copy_fallback"] is False


def test_host_workbuddy_reference_support_is_unverified_without_copy_fallback(fake_release_bundle, tmp_path):
    """workbuddy + --entry：明确 unverified，且绝不复制回退、不创建入口。"""
    entry = tmp_path / "host-skills"
    result = _run([sys.executable, PLATFORM_SHIMS["workbuddy"],
                   "--bundle", fake_release_bundle, "--entry", entry])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "unverified"
    assert payload["reason_code"] == "HOST_REFERENCE_SUPPORT_UNVERIFIED"
    assert payload["copy_fallback"] is False
    assert not entry.exists(), "未验证平台不得以复制回退方式创建宿主入口"


def test_host_codex_registers_reference_only_into_entry(fake_release_bundle, tmp_path):
    """codex + --entry：逐技能粒度平级引用注册（入口指向唯一源，源码不被移动/复制）。"""
    entry = tmp_path / "host-skills"
    result = _run([sys.executable, PLATFORM_SHIMS["codex"],
                   "--bundle", fake_release_bundle, "--entry", entry])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "success", payload
    assert payload["mode"] == "per-skill"
    assert (entry / "sample").resolve() == (fake_release_bundle / "skills" / "sample").resolve()
    assert (entry / "sample" / "SKILL.md").is_file()


def test_platform_shims_run_from_extracted_archive_host_adapters(codex_archive, fake_release_bundle, tmp_path):
    """归档平级目录可导入：解压 host_adapters/ 后 shim 仍可独立执行。

    打包按平台只携带对应 shim（codex 包内为 codex.py + host.py + references.py +
    windows_junction.ps1），`from host import main` 在解压目录下必须继续成立。
    """
    extracted = tmp_path / "extracted-adapters"
    extracted.mkdir()
    with zipfile.ZipFile(codex_archive) as archive:
        members = [n for n in archive.namelist() if n.startswith("host_adapters/")]
        assert len(members) >= 4, "归档内 host_adapters 不完整"
        archive.extractall(extracted, members=members)
    shim = extracted / "host_adapters" / "codex.py"
    assert shim.is_file(), f"归档未携带 codex shim: {members}"
    result = _run([sys.executable, shim, "--bundle", fake_release_bundle])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["status"] == "configured_target"
    assert payload["platform"] == "codex"


def test_retired_project_discovery_entrypoint_refuses_to_run():
    """退役入口 project.py 必须拒绝执行（不得被误改回可用状态）。"""
    result = _run([sys.executable, HOST_ADAPTERS_DIR / "project.py"])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "retired" in combined
    assert "Build a Release" in combined


# ==============================================================================
# 8. 隔离解压验收常驻用例（P0-06，承接 verify_release_scope.py 核心契约）
# ==============================================================================

@pytest.mark.parametrize("platform", ["codex", "hermes", "workbuddy"])
def test_isolated_extraction_and_doctor_smoke_across_platforms(tmp_path, monkeypatch, platform):
    """三平台候选包隔离构建、解压、zip-slip 检查并在干净环境下跑通 doctor 自诊断。

    承接 tools/development/verify_release_scope.py 的核心验证逻辑，但：
    - 绝不改写源码树（不修改 setup.sh / SKILL.md / .gitignore）；
    - 隔离运行：设置独立 A_STOCK_WORKSPACE_ROOT，清空 PYTHONPATH，移除开发环境变量；
    - 检查 zip-slip 防御、20 个 SKILL.md 完整性、解压后 doctor.py 输出及 is_healthy 状态。
    """
    from tools.packaging import common

    # 记录关键源文件哈希，确保执行前后源码树零修改
    watch_files = [
        ROOT / "skill_bundle" / "bundle.json",
        ROOT / "skill_bundle" / "skills" / "a-stock-agents" / "SKILL.md",
        ROOT / "skill_bundle" / "skills" / "astock-data-feed" / "setup.sh",
        ROOT / ".gitignore",
    ]
    hashes_before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watch_files if p.exists()}

    build_dir = tmp_path / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(common, "get_log_path", lambda *args, **kwargs: build_dir / "packaging.log")

    archive_path = common.package_project(build_dir / f"candidate_{platform}.zip", platform=platform)
    assert archive_path.is_file()

    # 1. 验证 zip-slip 与入口完整性
    extract_dir = tmp_path / f"extracted_{platform}"
    with zipfile.ZipFile(archive_path) as z:
        names = z.namelist()
        assert all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in names), "zip-slip 漏洞检查失败"
        assert len([n for n in names if n.endswith("/SKILL.md")]) == 20, "归档内 SKILL.md 数量不为 20"
        z.extractall(extract_dir)

    # 2. 隔离环境执行解压后的 doctor.py
    env = os.environ.copy()
    private_data = tmp_path / f"private_{platform}"
    env["A_STOCK_WORKSPACE_ROOT"] = str(private_data)
    env["PYTHONPATH"] = ""
    for k in ("A_STOCK_OUTPUT_DIR", "A_STOCK_LOG_DIR", "A_STOCK_TEMP_DIR", "A_STOCK_LOCAL_DIR", "A_STOCK_CONFIG_PATH"):
        env.pop(k, None)

    doctor_py = extract_dir / "skill_bundle" / "runtime" / "doctor.py"
    assert doctor_py.is_file(), "解压产物缺少 runtime/doctor.py"

    res = subprocess.run([sys.executable, str(doctor_py)], cwd=str(extract_dir), env=env, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"隔离环境下 doctor.py 失败: {res.stderr}\nstdout: {res.stdout}"

    health = json.loads(res.stdout)
    assert health["is_healthy"] is True
    assert health["total_skills"] == 20
    assert health["business_skills"] == 19
    assert health["skills_manifest"] is True
    assert health["cli_launcher"] is True
    # 验证数据根成功绑定到隔离目录，而不是开发仓库
    assert Path(health["workspace_root"]).resolve() == private_data.resolve()
    # 验证代码根指向解压目录中的 skill_bundle
    assert Path(health["package_root"]).resolve() == (extract_dir / "skill_bundle").resolve()

    # 3. 验证源码树零变更
    hashes_after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watch_files if p.exists()}
    assert hashes_before == hashes_after, "测试执行过程中破坏了开发仓库源文件"


def test_isolated_packaging_and_verification_is_idempotent(tmp_path, monkeypatch):
    """连续构建两次同平台归档，内部成员列表及解压内容完全一致，具备幂等性。"""
    from tools.packaging import common

    build_dir = tmp_path / "idempotent-build"
    build_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(common, "get_log_path", lambda *args, **kwargs: build_dir / "packaging.log")

    path1 = common.package_project(build_dir / "cand1.zip", platform="codex")
    path2 = common.package_project(build_dir / "cand2.zip", platform="codex")

    with zipfile.ZipFile(path1) as z1, zipfile.ZipFile(path2) as z2:
        assert z1.namelist() == z2.namelist(), "两次构建的条目清单不一致"
        for name in z1.namelist():
            assert z1.read(name) == z2.read(name), f"两次构建的条目内容不一致: {name}"


# ==============================================================================
# 9. 安装脚本零污染与无全局 pip 守卫（P0-05）
# ==============================================================================

def test_setup_scripts_do_not_pollute_host_environment():
    """全仓 setup.sh 必须满足零宿主污染：
    1. 严禁包含 pip install (向全局解释器安装依赖)；
    2. 严禁包含 git clone (拉取外部未经审计代码)；
    3. 严禁包含明文凭据注入 temp/ 的反模式；
    4. 严禁使用固定父目录层数 (../../..) 定位仓库；
    5. 统一废弃 ta-multi-agent-analysis 旧技能 ID。
    """
    setup_scripts = list(SKILLS_ROOT.rglob("setup.sh"))
    assert len(setup_scripts) >= 3, "至少应包含 3 个 setup.sh 脚本"

    for script in setup_scripts:
        text = script.read_text(encoding="utf-8")
        # 所有技能级 setup.sh 统一为 doctor 自检，不执行安装或外部副作用。
        assert not re.search(r"\bpip\s+install\b", text, re.IGNORECASE), (
            f"{script}: 包含 pip install，违反零宿主污染契约"
        )
        assert not re.search(r"\bgit\s+clone\b", text, re.IGNORECASE), (
            f"{script}: 包含 git clone，违反零宿主污染契约"
        )
        assert not re.search(r"\btemp[/\\]vendor\b", text, re.IGNORECASE), (
            f"{script}: 包含向 temp/ 写入 vendor 依赖的代码"
        )
        assert "ta-multi-agent-analysis" not in text, f"{script}: 残留已废弃技能 ID"
        # 不允许通过固定数量的父目录跳转定位仓库，兼容 Unix/Windows 分隔符。
        assert not re.search(r"\$SKILL_DIR(?:[/\\]\.\.){2,}(?:[/\\]|\b)", text), (
            f"{script}: 使用了固定的父目录层数定位仓库"
        )
        # 必须使用 bundle.json 进行根路径发现
        assert "bundle.json" in text, f"{script}: 必须使用 bundle.json 进行自描述根探测"


# ==============================================================================
# 10. 技能文档自描述调用与包内链接防腐守卫（P0-01）
# ==============================================================================

def test_skills_declare_uniform_calling_conventions():
    """20 个 SKILL.md 统一声明从真实路径向上定位 $BUNDLE 并通过薄启动器执行：
    1. 19 个专业技能必须包含统一的「调用约定」引用块，声明 $BUNDLE、runtime/astock.ps1、
       runtime/astock、runtime/cli.py 回落与 --json 参数，并回链 execution-contract.md；
    2. 总入口 a-stock-agents 必须声明 bundle.json、runtime/astock.ps1、runtime/astock 与 --json。
    """
    skill_mds = sorted(SKILLS_ROOT.glob("*/SKILL.md"))
    assert len(skill_mds) == 20, f"应发现 20 个 SKILL.md，实际发现 {len(skill_mds)}"

    for md_path in skill_mds:
        text = md_path.read_text(encoding="utf-8")
        skill_id = md_path.parent.name
        if skill_id == "a-stock-agents":
            assert "bundle.json" in text, f"{skill_id}: 缺 bundle.json 根定位说明"
            assert "runtime/astock.ps1" in text, f"{skill_id}: 缺 Windows 启动器说明"
            assert "runtime/astock" in text, f"{skill_id}: 缺 POSIX 启动器说明"
            assert "--json" in text, f"{skill_id}: 缺 --json 约定"
            assert "execution-contract.md" in text, f"{skill_id}: 缺共享执行契约引用"
        else:
            assert "调用约定" in text, f"{skill_id}: 缺少「调用约定」区块"
            assert "$BUNDLE" in text, f"{skill_id}: 缺少 $BUNDLE 根定义"
            assert "runtime/astock.ps1" in text, f"{skill_id}: 缺少 runtime/astock.ps1 启动器调用"
            assert "runtime/astock" in text, f"{skill_id}: 缺少 runtime/astock 启动器调用"
            assert "--json" in text, f"{skill_id}: 缺少 --json 参数规范"
            assert "execution-contract.md" in text, f"{skill_id}: 缺少 execution-contract.md 共享契约链接"


def test_bundle_markdown_and_scripts_contain_no_bin_astock():
    """skill_bundle 内部的所有 Markdown 文档及脚本中，严禁出现开发态相对路径 bin/astock*。

    Release 归档只包含 skill_bundle/，bin/ 在归档外；任何 bin/astock* 引用在宿主机器上必失败。
    """
    bundle_root = SKILLS_ROOT.parent
    checked_files = 0
    bin_astock_re = re.compile(r'(?:\./|\\|\b)bin[/\\]astock', re.IGNORECASE)

    for p in bundle_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in [".md", ".sh", ".ps1"]:
            continue
        checked_files += 1
        text = p.read_text(encoding="utf-8", errors="replace")
        matches = [
            (i + 1, line.strip())
            for i, line in enumerate(text.splitlines())
            if bin_astock_re.search(line)
        ]
        assert not matches, f"{p.relative_to(ROOT)} 仍包含 bin/astock 引用: {matches}"

    assert checked_files >= 100, f"受检文档与脚本数量异常: {checked_files} < 100"


def test_bundle_markdown_links_do_not_escape_and_all_exist():
    """skill_bundle 内所有 Markdown 中的相对链接不得逃逸至包外（如 docs/、apps/），且目标文件必须物理存在。"""
    bundle_root = SKILLS_ROOT.parent
    md_link_re = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    total_links_verified = 0

    for md_file in bundle_root.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8", errors="replace")
        for match in md_link_re.finditer(text):
            target_raw = match.group(2).strip()
            # 排除网络链接、锚点、邮箱
            if target_raw.startswith(("http://", "https://", "#", "mailto:")):
                continue
            file_part = target_raw.split("#")[0].strip()
            if not file_part:
                continue

            target_path = (md_file.parent / file_part).resolve()
            # 断言 1: 不得逃逸出 bundle_root
            try:
                target_path.relative_to(bundle_root)
            except ValueError:
                pytest.fail(
                    f"{md_file.relative_to(ROOT)} 中的链接 {target_raw!r} 逃逸出 skill_bundle 目录: {target_path}"
                )
            # 断言 2: 目标文件必须真实存在
            assert target_path.exists(), (
                f"{md_file.relative_to(ROOT)} 中的链接 {target_raw!r} 指向不存在的文件: {target_path}"
            )
            total_links_verified += 1

    assert total_links_verified >= 50, f"受检相对链接数过少: {total_links_verified} < 50"


def test_bundle_cron_and_scheduled_tasks_have_no_cwd_dependency():
    """定时调度与监控说明中不得包含 cd <repo_root> 类的 CWD 依赖指令。"""
    cron_skill = SKILLS_ROOT / "astock-pool-dashboard" / "SKILL.md"
    text = cron_skill.read_text(encoding="utf-8")
    assert not re.search(r"cd\s+[/~a-zA-Z0-9_.-]+&&", text), (
        f"{cron_skill.name} 包含依赖 cd 的定时任务示例"
    )


# ==============================================================================
# 11. Release 产物锚点技能架构与转发壳三级寻址（P0-08）
# ==============================================================================

def test_archive_anchor_skill_structure(codex_archive: Path):
    """构建产物锚点架构断言：
    1. skills/a-stock-agents/ 必须包含自描述 bundle.json (anchor: true, distribution: release)；
    2. 必须包含注入的 runtime/、assets/、references/ 与 requirements*.txt；
    3. runtime/astock 启动器具有 POSIX 执行位 (0o755)；
    4. INSTALL.json 显式声明 anchor_skill。
    """
    with zipfile.ZipFile(codex_archive) as archive:
        names = set(archive.namelist())
        instructions = json.loads(archive.read("INSTALL.json"))

        assert instructions.get("anchor_skill") == "skill_bundle/skills/a-stock-agents"

        # 1. 锚点 bundle.json
        assert "skill_bundle/skills/a-stock-agents/bundle.json" in names
        marker = json.loads(archive.read("skill_bundle/skills/a-stock-agents/bundle.json"))
        assert marker["name"] == "a_stock_agents"
        assert marker["distribution"] == "release"
        assert marker["anchor"] is True
        assert marker["skills"] == ".."

        # 2. 注入的核心 runtime / assets / references
        assert "skill_bundle/skills/a-stock-agents/runtime/doctor.py" in names
        assert "skill_bundle/skills/a-stock-agents/runtime/core/workspace.py" in names
        assert "skill_bundle/skills/a-stock-agents/runtime/astock.ps1" in names
        assert "skill_bundle/skills/a-stock-agents/assets/config/skills_manifest.json" in names
        assert "skill_bundle/skills/a-stock-agents/references/execution-contract.md" in names
        assert "skill_bundle/skills/a-stock-agents/requirements.txt" in names
        assert "skill_bundle/skills/a-stock-agents/requirements-full.txt" in names

        # 3. 启动器执行位
        astock_entry = archive.getinfo("skill_bundle/skills/a-stock-agents/runtime/astock")
        assert astock_entry.create_system == 3
        assert (astock_entry.external_attr >> 16) & 0o755 == 0o755


def test_forwarding_wrapper_sibling_resolution_isolated(tmp_path):
    """单个技能被剥离到独立临时目录时，能通过兄弟定位 (../a-stock-agents) 找到引擎并正常执行。"""
    import shutil
    host_skills = tmp_path / "host_skills"
    host_skills.mkdir(parents=True, exist_ok=True)

    # 1. 搭建兄弟锚点技能 a-stock-agents
    anchor_dir = host_skills / "a-stock-agents"
    shutil.copytree(SKILLS_ROOT / "a-stock-agents", anchor_dir)
    shutil.copytree(RUNTIME_ROOT, anchor_dir / "runtime")
    shutil.copytree(SKILLS_ROOT.parent / "assets", anchor_dir / "assets")
    shutil.copytree(SKILLS_ROOT.parent / "references", anchor_dir / "references")
    anchor_marker = json.loads((SKILLS_ROOT.parent / "bundle.json").read_text(encoding="utf-8"))
    anchor_marker["distribution"] = "release"
    anchor_marker["anchor"] = True
    anchor_marker["skills"] = ".."
    (anchor_dir / "bundle.json").write_text(json.dumps(anchor_marker), encoding="utf-8")

    # 2. 单独拷贝一个专业技能 (astock-pool-dashboard)
    target_skill = host_skills / "astock-pool-dashboard"
    shutil.copytree(SKILLS_ROOT / "astock-pool-dashboard", target_skill)

    # 3. 隔离环境执行转发壳
    env = os.environ.copy()
    env["A_STOCK_WORKSPACE_ROOT"] = str(tmp_path / "sandbox_workspace")
    env["PYTHONPATH"] = ""
    for k in ("A_STOCK_OUTPUT_DIR", "A_STOCK_LOG_DIR", "A_STOCK_TEMP_DIR", "A_STOCK_LOCAL_DIR", "A_STOCK_CONFIG_PATH"):
        env.pop(k, None)

    script = target_skill / "scripts" / "position_manager.py"
    assert script.is_file()

    res = subprocess.run([sys.executable, str(script), "--help"], cwd=str(target_skill), env=env, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"兄弟定位执行失败:\nstderr: {res.stderr}\nstdout: {res.stdout}"
    assert "position_manager" in (res.stdout + res.stderr)


def test_forwarding_wrapper_receipt_resolution_isolated(tmp_path):
    """单个技能被完全孤立存放时，能通过系统收据 install.json 找到引擎并正常执行。"""
    import shutil

    # 1. 锚点技能存放在完全不相关的独立目录
    anchor_dir = tmp_path / "central_engine" / "a-stock-agents"
    shutil.copytree(SKILLS_ROOT / "a-stock-agents", anchor_dir)
    shutil.copytree(RUNTIME_ROOT, anchor_dir / "runtime")
    shutil.copytree(SKILLS_ROOT.parent / "assets", anchor_dir / "assets")
    shutil.copytree(SKILLS_ROOT.parent / "references", anchor_dir / "references")
    anchor_marker = json.loads((SKILLS_ROOT.parent / "bundle.json").read_text(encoding="utf-8"))
    anchor_marker["distribution"] = "release"
    anchor_marker["anchor"] = True
    anchor_marker["skills"] = ".."
    (anchor_dir / "bundle.json").write_text(json.dumps(anchor_marker), encoding="utf-8")

    # 2. 专业技能单独放在孤立路径（周围没有任何 a-stock-agents）
    orphaned_skill = tmp_path / "isolated_user_skills" / "astock-pool-dashboard"
    shutil.copytree(SKILLS_ROOT / "astock-pool-dashboard", orphaned_skill)

    # 3. 数据根写入 install.json 收据
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    receipt = {
        "status": "installed",
        "bundle_root": str(anchor_dir),
        "runtime_root": str(anchor_dir / "runtime"),
    }
    (workspace / "install.json").write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    # 4. 隔离环境执行
    env = os.environ.copy()
    env["A_STOCK_WORKSPACE_ROOT"] = str(workspace)
    env["PYTHONPATH"] = ""
    for k in ("A_STOCK_OUTPUT_DIR", "A_STOCK_LOG_DIR", "A_STOCK_TEMP_DIR", "A_STOCK_LOCAL_DIR", "A_STOCK_CONFIG_PATH"):
        env.pop(k, None)

    script = orphaned_skill / "scripts" / "position_manager.py"
    res = subprocess.run([sys.executable, str(script), "--help"], cwd=str(orphaned_skill), env=env, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"收据定位执行失败:\nstderr: {res.stderr}\nstdout: {res.stdout}"
    assert "position_manager" in (res.stdout + res.stderr)


def test_forwarding_wrapper_fail_closed_anchor_missing(tmp_path):
    """当自定位、兄弟定位与收据定位均失败时，fail-closed 明确报错 ANCHOR_SKILL_MISSING。"""
    import shutil
    orphaned_skill = tmp_path / "orphaned_skill" / "astock-pool-dashboard"
    shutil.copytree(SKILLS_ROOT / "astock-pool-dashboard", orphaned_skill)

    workspace = tmp_path / "empty_workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["A_STOCK_WORKSPACE_ROOT"] = str(workspace)
    env["PYTHONPATH"] = ""
    for k in ("A_STOCK_OUTPUT_DIR", "A_STOCK_LOG_DIR", "A_STOCK_TEMP_DIR", "A_STOCK_LOCAL_DIR", "A_STOCK_CONFIG_PATH"):
        env.pop(k, None)

    script = orphaned_skill / "scripts" / "position_manager.py"
    res = subprocess.run([sys.executable, str(script)], cwd=str(orphaned_skill), env=env, capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    combined = res.stderr + res.stdout
    assert "ANCHOR_SKILL_MISSING" in combined


def test_anchor_skill_doctor_smoke_in_isolated_host_skills(tmp_path):
    """在宿主技能目录中，锚点技能 runtime/doctor.py 可直接唤起自检，并识别平级 20 个技能。"""
    import shutil
    host_skills = tmp_path / "host_skills"
    host_skills.mkdir(parents=True, exist_ok=True)

    # 拷贝全部 20 个技能目录
    for sdir in SKILLS_ROOT.iterdir():
        if sdir.is_dir():
            shutil.copytree(sdir, host_skills / sdir.name)

    # 注入锚点技能资源
    anchor_dir = host_skills / "a-stock-agents"
    shutil.copytree(RUNTIME_ROOT, anchor_dir / "runtime")
    shutil.copytree(SKILLS_ROOT.parent / "assets", anchor_dir / "assets")
    shutil.copytree(SKILLS_ROOT.parent / "references", anchor_dir / "references")
    anchor_marker = json.loads((SKILLS_ROOT.parent / "bundle.json").read_text(encoding="utf-8"))
    anchor_marker["distribution"] = "release"
    anchor_marker["anchor"] = True
    anchor_marker["skills"] = ".."
    (anchor_dir / "bundle.json").write_text(json.dumps(anchor_marker), encoding="utf-8")

    env = os.environ.copy()
    data_dir = tmp_path / "isolated_data"
    env["A_STOCK_WORKSPACE_ROOT"] = str(data_dir)
    env["PYTHONPATH"] = ""
    for k in ("A_STOCK_OUTPUT_DIR", "A_STOCK_LOG_DIR", "A_STOCK_TEMP_DIR", "A_STOCK_LOCAL_DIR", "A_STOCK_CONFIG_PATH"):
        env.pop(k, None)

    doctor_py = anchor_dir / "runtime" / "doctor.py"
    assert doctor_py.is_file()

    res = subprocess.run([sys.executable, str(doctor_py)], cwd=str(anchor_dir), env=env, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"锚点 doctor 失败:\nstderr: {res.stderr}\nstdout: {res.stdout}"

    health = json.loads(res.stdout)
    assert health["is_healthy"] is True
    assert health["total_skills"] == 20
    assert health["business_skills"] == 19
    assert health["cli_launcher"] is True
    assert health["skills_manifest"] is True
    assert Path(health["package_root"]).resolve() == anchor_dir.resolve()
    assert Path(health["skills_root"]).resolve() == host_skills.resolve()


# ==============================================================================
# 12. 统一安装底层脚本核心 install.ps1 / install.sh（P0-09）
# ==============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_installer_inspect_json_smoke():
    """install.ps1 -Inspect -Json 真实执行，断言合法 JSON 输出及 20 项入口探测。"""
    install_ps1 = ROOT / "install.ps1"
    assert install_ps1.is_file(), "install.ps1 必须存在于仓库根"

    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-File", str(install_ps1), "-Inspect", "-Json"]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"install.ps1 -Inspect -Json 失败:\nstderr: {res.stderr}\nstdout: {res.stdout}"

    data = json.loads(res.stdout)
    assert data["status"] == "success"
    assert data["action"] == "inspect"
    assert data["skills_count"] == 20
    assert len(data["skills"]) == 20
    assert "a-stock-agents" in data["skills"]
    assert "astock-data-feed" in data["skills"]
    assert data["python"]["path"] and Path(data["python"]["path"]).exists()
    assert set(data["agents"].keys()) == {"universal", "hermes", "workbuddy", "codex"}


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_installer_isolated_sandbox_execution(tmp_path):
    """install.ps1 在完全隔离的沙箱数据根下执行，生成包含 20 个入口证明与 SHA256 的 install.json。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_data"

    cmd = [
        "powershell", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=90)
    assert res.returncode == 0, f"install.ps1 沙箱安装执行失败:\nstderr: {res.stderr}\nstdout: {res.stdout}"

    receipt_file = sandbox_data / "install.json"
    assert receipt_file.is_file(), "沙箱数据根缺少 install.json 收据"

    receipt = json.loads(receipt_file.read_text(encoding="utf-8-sig"))
    assert receipt["status"] == "installed"
    assert receipt["version"] == "v3"
    assert receipt["skills_count"] == 20
    assert receipt["business_skills"] == 19
    assert len(receipt["skill_entries"]) == 20
    assert Path(receipt["workspace_root"]).resolve() == sandbox_data.resolve()
    assert Path(receipt["bundle_root"]).is_dir()
    assert Path(receipt["runtime_root"]).is_dir()

    # 验证 20 个技能入口就绪证明与 SHA256 校验
    anchor_entry = None
    for entry in receipt["skill_entries"]:
        assert entry["verified"] is True
        assert len(entry["skill_md_sha256"]) == 64
        assert Path(entry["path"]).is_dir()
        if entry["id"] == "a-stock-agents":
            anchor_entry = entry
    assert anchor_entry is not None, "缺少 a-stock-agents 锚点技能收据"
    assert anchor_entry["is_anchor"] is True

    # 验证收据自校验哈希与 doctor 报告
    assert len(receipt["sha256"]) == 64
    assert receipt["doctor_health"]["is_healthy"] is True
    assert receipt["doctor_health"]["total_skills"] == 20


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_installer_doctor_smoke_from_receipt(tmp_path):
    """已安装环境下运行 install.ps1 -Doctor -Json，成功通过自检。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_doctor"

    # 1. 运行安装
    cmd_install = [
        "powershell", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    res_inst = subprocess.run(cmd_install, cwd=str(ROOT), capture_output=True, text=True, timeout=90)
    assert res_inst.returncode == 0

    # 2. 运行 doctor 模式
    cmd_doc = [
        "powershell", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Doctor",
        "-Json"
    ]
    res_doc = subprocess.run(cmd_doc, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_doc.returncode == 0, f"doctor 检查失败:\nstderr: {res_doc.stderr}\nstdout: {res_doc.stdout}"

    report = json.loads(res_doc.stdout)
    assert report["is_healthy"] is True
    assert report["total_skills"] == 20
    assert report["business_skills"] == 19


def test_installer_packaged_in_release_archive(codex_archive: Path):
    """Release 归档根必须包含 install.ps1 与带执行位的 install.sh，INSTALL.json 明确声明。"""
    with zipfile.ZipFile(codex_archive) as archive:
        names = archive.namelist()
        assert "install.ps1" in names, "归档根缺失 install.ps1"
        assert "install.sh" in names, "归档根缺失 install.sh"

        # install.sh POSIX 执行位 (0o755)
        sh_info = archive.getinfo("install.sh")
        assert sh_info.create_system == 3, "install.sh 不是 POSIX 归档条目"
        assert (sh_info.external_attr >> 16) & 0o755 == 0o755, "install.sh 缺失 0o755 执行位"

        # INSTALL.json 声明 installer 键
        instructions = json.loads(archive.read("INSTALL.json"))
        assert "installer" in instructions
        assert instructions["installer"]["windows"] == "install.ps1"
        assert instructions["installer"]["posix"] == "install.sh"


def test_installer_scripts_do_not_pollute_host_environment():
    """安装脚本安全守卫：严禁无隔离的裸 pip install、严禁凭据泄漏。"""
    install_ps1 = ROOT / "install.ps1"
    install_sh = ROOT / "install.sh"
    assert install_ps1.is_file()
    assert install_sh.is_file()

    sh_text = install_sh.read_text(encoding="utf-8")
    for line in sh_text.splitlines():
        line = line.strip()
        if "pip install" in line and not line.startswith("#"):
            assert "$VENV_PYTHON" in line or "$UV_CMD" in line, f"install.sh 未隔离 pip install: {line}"

    ps1_text = install_ps1.read_text(encoding="utf-8")
    ps1_clean = re.sub(r"<#.*?#>", "", ps1_text, flags=re.DOTALL)
    for line in ps1_clean.splitlines():
        line = line.strip()
        if "pip install" in line and not line.startswith("#"):
            assert "$venvPython" in line or "$uvCmd" in line, f"install.ps1 未隔离 pip install: {line}"


# ==============================================================================
# 13. 逐技能粒度平级注册与“宿主发现模拟”门禁（P0-10）
# ==============================================================================

def _simulate_single_level_skill_discovery(skills_root: Path) -> dict:
    """模拟宿主（Codex / WorkBuddy / Universal）的单层扫描机制。

    任何宿主在扫描技能目录时，仅遍历其直接子目录，检查是否存在合法 SKILL.md。
    若存在嵌套目录（如 skills/skills/foo/SKILL.md），单层扫描必然漏检（即 H1 致命缺陷）。
    """
    discovered = {}
    if not skills_root.is_dir():
        return discovered
    for child in sorted(skills_root.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if skill_md.is_file():
            try:
                fm = _parse_frontmatter(child)
                if fm.get("name") == child.name and fm.get("description"):
                    discovered[child.name] = {
                        "name": fm["name"],
                        "description": fm["description"],
                        "path": str(child.resolve()),
                    }
            except Exception:
                pass
    return discovered


def _simulate_hermes_discovery(config_file: Path) -> dict:
    """模拟 Hermes Desktop 基于 config.yaml 的 skills.external_dirs 扫描机制。"""
    discovered = {}
    if not config_file.is_file():
        return discovered
    content = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    external_dirs = content.get("skills", {}).get("external_dirs", [])
    for d in external_dirs:
        dir_path = Path(d)
        if dir_path.is_dir():
            for child in sorted(dir_path.iterdir()):
                if child.is_dir() and (child / "SKILL.md").is_file():
                    try:
                        fm = _parse_frontmatter(child)
                        if fm.get("name") == child.name and fm.get("description"):
                            discovered[child.name] = {
                                "name": fm["name"],
                                "description": fm["description"],
                                "path": str(child.resolve()),
                            }
                    except Exception:
                        pass
    return discovered


def test_references_per_skill_registration_and_unregistration(tmp_path):
    """P0-10 动作 1：references.register_skills 逐技能粒度平级注册与幂等性、干净卸载。"""
    from tools.host_adapters.references import register_skills, unregister_skills, is_reference

    host_skills_dir = tmp_path / "host-skills"
    # 首次注册：将全套 20 项技能平级注册至宿主目录
    res = register_skills(SKILLS_ROOT, host_skills_dir)
    assert res["status"] == "success"
    assert res["mode"] == "per-skill"
    assert res["skill_count"] == 20
    assert res["registered_count"] == 20
    assert res["changed"] is True

    # 验证宿主目录内 20 个平级子目录均存在且均为引用
    for child in host_skills_dir.iterdir():
        if child.name.startswith("."):
            continue
        assert child.is_dir()
        assert (child / "SKILL.md").is_file()
        assert is_reference(child)

    # 幂等性验证：二次注册 changed 为 False
    res2 = register_skills(SKILLS_ROOT, host_skills_dir)
    assert res2["status"] == "success"
    assert res2["changed"] is False

    # 验证干净卸载：仅移除 a-stock-agents 注册的链接，保留宿主自定义目录
    custom_dir = host_skills_dir / "user-custom-skill"
    custom_dir.mkdir()
    (custom_dir / "SKILL.md").write_text("---\nname: user-custom-skill\ndescription: user\n---\n", encoding="utf-8")

    unres = unregister_skills(host_skills_dir)
    assert unres["status"] == "success"
    assert unres["count"] == 20
    assert custom_dir.is_dir(), "卸载不得误删用户自建技能"
    assert (custom_dir / "SKILL.md").is_file()


def test_codex_host_adapter_registers_per_skill_into_host_entry(extracted_codex_bundle: Path, tmp_path):
    """P0-10 动作 1：codex.py shim 对解压后的 Release 执行逐技能粒度注册。"""
    skills_root = extracted_codex_bundle / "skill_bundle" / "skills"
    assert skills_root.is_dir()

    host_entry = tmp_path / "codex-host-skills"
    result = _run([
        sys.executable, PLATFORM_SHIMS["codex"],
        "--bundle", extracted_codex_bundle / "skill_bundle",
        "--entry", host_entry
    ])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["status"] == "success"
    assert payload["mode"] == "per-skill"
    assert payload["registered_count"] == 20

    # 验证 20 个技能均被建立平级链接
    entries = [d for d in host_entry.iterdir() if not d.name.startswith(".")]
    assert len(entries) == 20
    assert (host_entry / "a-stock-agents" / "SKILL.md").is_file()
    assert (host_entry / "astock-data-feed" / "SKILL.md").is_file()


def test_host_discovery_simulator_codex(extracted_codex_bundle: Path, tmp_path):
    """P0-10 动作 2/3：Codex 宿主单层扫描模拟，断言 20 入口检出率 100%。"""
    from tools.host_adapters.references import register_skills
    host_skills = tmp_path / "codex_skills"
    register_skills(extracted_codex_bundle / "skill_bundle" / "skills", host_skills)

    discovered = _simulate_single_level_skill_discovery(host_skills)
    assert len(discovered) == 20, f"Codex 宿主发现数 {len(discovered)} != 20"
    assert "a-stock-agents" in discovered
    manifest_path = SKILLS_ROOT.parent / "assets" / "config" / "skills_manifest.json"
    manifest_ids = {s["id"] for s in json.loads(manifest_path.read_text(encoding="utf-8"))["skills"]}
    assert set(discovered.keys()) == manifest_ids | {"a-stock-agents"}


def test_host_discovery_simulator_hermes(extracted_codex_bundle: Path, tmp_path):
    """P0-10 动作 2/3：Hermes Desktop external_dirs 扫描模拟，断言 20 入口检出率 100%。"""
    release_skills = extracted_codex_bundle / "skill_bundle" / "skills"

    # 1. 模拟 Hermes 原生 external_dirs 配置
    hermes_config = tmp_path / "hermes_config.yaml"
    hermes_config.write_text(yaml.safe_dump({
        "skills": {
            "external_dirs": [str(release_skills)]
        }
    }), encoding="utf-8")

    discovered_ext = _simulate_hermes_discovery(hermes_config)
    assert len(discovered_ext) == 20, f"Hermes external_dirs 发现数 {len(discovered_ext)} != 20"
    assert "a-stock-agents" in discovered_ext

    # 2. 模拟 Hermes 本地技能目录逐技能链接挂载
    from tools.host_adapters.references import register_skills
    hermes_local_skills = tmp_path / "hermes_local_skills"
    register_skills(release_skills, hermes_local_skills)
    discovered_local = _simulate_single_level_skill_discovery(hermes_local_skills)
    assert len(discovered_local) == 20, f"Hermes local skills 发现数 {len(discovered_local)} != 20"
    assert "a-stock-agents" in discovered_local


def test_host_discovery_simulator_workbuddy_and_h1_proof(extracted_codex_bundle: Path, tmp_path):
    """P0-10 动作 2/3：WorkBuddy 模拟与 H1 致命缺陷证据对照。

    - 负向证据（H1 场景）：若错误地将整个 skills/ 目录作为一层链接放入 ~/.workbuddy/skills/skills，
      WorkBuddy 单层扫描检出数恒等于 0（证明旧方案彻底瘫痪）；
    - 正向证据（P0-10 修复后）：逐技能平级注册后，WorkBuddy 单层扫描检出数恒等于 20（100% 检出）。
    """
    release_skills = extracted_codex_bundle / "skill_bundle" / "skills"

    # 1. 负向证明：旧版 H1 嵌套链接导致 0 发现
    from tools.host_adapters.references import register_reference, register_skills
    h1_workbuddy = tmp_path / "workbuddy_h1"
    h1_workbuddy.mkdir(parents=True)
    # 模拟旧版错误：直接链接整个 skills 目录到 workbuddy/skills
    register_reference(release_skills, h1_workbuddy / "skills")
    h1_discovered = _simulate_single_level_skill_discovery(h1_workbuddy)
    assert len(h1_discovered) == 0, "旧方案 H1 嵌套链接应导致单层扫描 0 发现"

    # 2. 正向验证：P0-10 逐技能平级注册达成 100% 发现
    p010_workbuddy = tmp_path / "workbuddy_p010"
    p010_workbuddy.mkdir(parents=True)
    register_skills(release_skills, p010_workbuddy)
    p010_discovered = _simulate_single_level_skill_discovery(p010_workbuddy)
    assert len(p010_discovered) == 20, f"WorkBuddy 平级扫描发现数 {len(p010_discovered)} != 20"
    assert "a-stock-agents" in p010_discovered
    manifest_path = SKILLS_ROOT.parent / "assets" / "config" / "skills_manifest.json"
    manifest_ids = {s["id"] for s in json.loads(manifest_path.read_text(encoding="utf-8"))["skills"]}
    assert set(p010_discovered.keys()) == manifest_ids | {"a-stock-agents"}


def test_installer_agent_per_skill_registration_integration(tmp_path):
    """P0-10 安装器集成验证：install.ps1 -Agent 实现逐技能平级挂载并通关宿主单层扫描。"""
    install_ps1 = ROOT / "install.ps1"
    assert install_ps1.is_file()

    sandbox_data = tmp_path / "sandbox_data"
    sandbox_host = tmp_path / "mock_agent_host"
    sandbox_data.mkdir()
    sandbox_host.mkdir()

    cmd = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Agent", str(sandbox_host),
        "-Method", "link",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    result = _run(cmd, cwd=ROOT)
    assert result.returncode == 0, f"stderr: {result.stderr}, stdout: {result.stdout}"

    payload = json.loads(result.stdout)
    assert payload["status"] == "installed"
    assert len(payload["registered_agents"]) == 1
    assert payload["registered_agents"][0]["skills_count"] == 20

    # 验证宿主目录可被单层扫描完整发现 20 个技能
    discovered = _simulate_single_level_skill_discovery(sandbox_host)
    assert len(discovered) == 20, f"通过安装器挂载后发现数 {len(discovered)} != 20"
    assert "a-stock-agents" in discovered


# ==============================================================================
# 14. 模态一：AI 安装引导提示词与 5 类信息卡片渲染契约（P1-08）
# ==============================================================================

def test_ai_copilot_bootstrap_prompt_consistency():
    """P1-08 动作 1：标准 AI 安装指令模板在文档体系中保持单一标准与要素完备性。

    断言 README.md、docs/quickstart.md、skill-suite-portability-specification.md
    均固化了统一的 AI Copilot Bootstrap Prompt，且包含以下关键契约要素：
    1. 官方 Release 地址与安装协议；
    2. Windows 与 POSIX 的安装器引导命令；
    3. 强制要求所有交互与状态查询追加 --json；
    4. 5 阶段渐进式 SOP 任务流水线（阶段 1 探测环境 -> 阶段 2 配置交互 -> 阶段 3 安全确认 -> 阶段 4 分级执行 -> 阶段 5 冒烟交付）。
    """
    target_docs = [
        ROOT / "README.md",
        ROOT / "docs" / "quickstart.md",
        ROOT / "docs" / "guidelines" / "engineering" / "skill-suite-portability-specification.md",
    ]

    expected_url = "https://github.com/cvdnn/a-stock-agents/releases/latest"
    expected_ps1 = "https://github.com/cvdnn/a-stock-agents/releases/latest/download/install.ps1"
    expected_sh = "https://github.com/cvdnn/a-stock-agents/releases/latest/download/install.sh"
    sop_stages = [
        "阶段 1 [探测环境]",
        "阶段 2 [配置交互]",
        "阶段 3 [安全确认]",
        "阶段 4 [分级执行]",
        "阶段 5 [冒烟交付]",
    ]

    for doc_path in target_docs:
        assert doc_path.is_file(), f"文档缺失: {doc_path}"
        text = doc_path.read_text(encoding="utf-8")
        assert expected_url in text, f"{doc_path.name} 缺少 Release 仓库地址"
        assert expected_ps1 in text, f"{doc_path.name} 缺少 PowerShell 安装器链接"
        assert expected_sh in text, f"{doc_path.name} 缺少 Bash 安装器链接"
        assert "--json" in text, f"{doc_path.name} 缺少 --json 参数要求"
        for stage in sop_stages:
            assert stage in text, f"{doc_path.name} 缺少 SOP 流水线阶段: {stage}"


def test_anchor_skill_defines_five_interactive_cards_contract():
    """P1-08 动作 2：总入口 a-stock-agents/SKILL.md 固化 5 阶段状态机与 5 类信息卡片渲染契约。

    断言总入口包含完整的 5 类信息卡片模板及状态机契约：
    - 卡片 1：目标宿主选择（Universal、Hermes、WorkBuddy、安装方式单选）；
    - 卡片 2：量化数据源与私有配置（腾讯/新浪L1免配、AkShare/MyTT扩展、local/settings/.env隐私承诺）；
    - 卡片 3：安装前摘要与安全审计（1锚点+19专业、数据隔离根、Overwrites冲突检测、独立.venv权限隔离）；
    - 卡片 4：执行流水线（符合 AGENTS.md 规范：a_stock_installer 批量 5 步流水线与子任务 1~5）；
    - 卡片 5：交付与即时实战测试（Codex $a-stock-agents / Hermes /a-stock-agents / WorkBuddy @a-stock-agents，3 个实战动作）。
    """
    skill_md = SKILLS_ROOT / "a-stock-agents" / "SKILL.md"
    assert skill_md.is_file()
    text = skill_md.read_text(encoding="utf-8")

    # 1. 验证 5 阶段状态机
    sop_stages = [
        "阶段 1 [探测环境]",
        "阶段 2 [配置交互]",
        "阶段 3 [安全确认]",
        "阶段 4 [分级执行]",
        "阶段 5 [冒烟交付]",
    ]
    for stage in sop_stages:
        assert stage in text, f"a-stock-agents SKILL.md 缺少状态机阶段: {stage}"

    # 2. 验证 5 类信息卡片存在性
    assert "信息卡片 1：环境探测与目标宿主勾选卡片" in text
    assert "信息卡片 2：量化数据源与私有配置卡片" in text
    assert "信息卡片 3：安装前摘要与安全审计卡片" in text
    assert "信息卡片 4：执行流水线进度卡片" in text
    assert "信息卡片 5：交付与即时实战测试卡片" in text

    # 3. 验证卡片细节契约
    # 卡片 1 宿主
    assert "Universal 通用目录" in text
    assert "Hermes Desktop" in text
    assert "WorkBuddy" in text
    assert "符号链接/Junction" in text
    assert "物理复制" in text

    # 卡片 2 数据源与隐私
    assert "腾讯/新浪 L1 实时行情快照" in text
    assert "AkShare / MyTT" in text
    assert "local/settings/.env" in text
    assert "隐私承诺" in text

    # 卡片 3 安全审计与明细
    assert "1 个总入口 (锚点) + 19 项专业量化技能" in text
    assert "权限隔离" in text
    assert "独立 Python .venv" in text
    assert "Overwrites" in text

    # 卡片 4 流水线导轨规范（符合 AGENTS.md）
    assert "能力调用 a_stock_installer 任务（批量 5 步流水线）" in text
    assert "子任务 1: 下载并解压 Release 归档" in text
    assert "子任务 2: 宿主技能入口挂载" in text
    assert "子任务 3: 初始化隔离 Python 虚拟环境" in text
    assert "子任务 4: 安装量化引擎依赖" in text
    assert "子任务 5: 运行 doctor 20 项技能契约冒烟自检" in text

    # 卡片 5 交付与宿主语法
    assert "$a-stock-agents" in text
    assert "/a-stock-agents" in text
    assert "@a-stock-agents" in text
    assert "600519" in text
    assert "5A 量价多因子选股模型" in text


def test_anchor_skill_preserves_calling_conventions_and_invariants():
    """P1-08 动作 3：验证总入口改造后仍严格遵守既有交付门禁与不变量规则。"""
    skill_md = SKILLS_ROOT / "a-stock-agents" / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")

    # 1. Frontmatter 合法性
    fm = _parse_frontmatter(SKILLS_ROOT / "a-stock-agents")
    assert fm.get("name") == "a-stock-agents"
    assert "A股技能总入口" in fm.get("description", "")

    # 2. 调用约定不变量
    assert "bundle.json" in text
    assert "runtime/astock.ps1" in text
    assert "runtime/astock" in text
    assert "--json" in text
    assert "execution-contract.md" in text

    # 3. 交易三原则与空股池说明
    assert "空股池停止分析并提示登记" in text
    assert "精确保本价" in text
    assert "三级风控" in text
    assert "三场景动作" in text

    # 4. 零 bin/astock 引用
    assert not re.search(r'(?:\./|\\|\b)bin[/\\]astock', text, re.IGNORECASE)


# ==============================================================================
# 15. 模态二：终端 TUI 键盘多选导轨菜单与 Overwrites 冲突保护（P1-09）
# ==============================================================================

def test_terminal_tui_menu_definition_and_contract():
    """P1-09 动作 1：验证跨平台安装脚本定义了键盘多选 TUI 导轨菜单与按键契约。

    断言 install.ps1 与 install.sh 均包含完整的终端交互式导轨菜单：
    1. TTY 交互式环境检测逻辑与无交互降级；
    2. 上下光标移动 (Up/Down 或 k/j)、空格多选切换 (Space)、回车确认 (Enter)、安装方式切换 (m)、全选/反选 (a)、退出 (q)；
    3. Universal agents 与 Additional agents 宿主分类呈现；
    4. 显式提供 -Tui / --tui 与 -Force / --force 参数支持。
    """
    install_ps1 = ROOT / "install.ps1"
    install_sh = ROOT / "install.sh"
    assert install_ps1.is_file(), "install.ps1 缺失"
    assert install_sh.is_file(), "install.sh 缺失"

    ps1_text = install_ps1.read_text(encoding="utf-8")
    sh_text = install_sh.read_text(encoding="utf-8")

    # 1. 验证函数与 TUI 导轨结构
    assert "function Show-TuiMenu" in ps1_text
    assert "show_tui_menu()" in sh_text

    # 2. 验证 Universal 与 Additional 分类
    assert "Universal agents" in ps1_text
    assert "Additional agents" in ps1_text
    assert "Universal agents" in sh_text
    assert "Additional agents" in sh_text

    # 3. 验证键盘按键绑定
    for key in ["UpArrow", "DownArrow", "Spacebar", "Enter", "Escape"]:
        assert key in ps1_text, f"install.ps1 缺少按键处理: {key}"
    assert "'m'" in ps1_text or "KeyChar -eq 'm'" in ps1_text
    assert "'a'" in ps1_text or "KeyChar -eq 'a'" in ps1_text
    assert "'q'" in ps1_text or "KeyChar -eq 'q'" in ps1_text

    for sh_key in ["x1b[A", "x1b[B", "' '", "m|M", "a|A", "q|Q"]:
        assert sh_key in sh_text, f"install.sh 缺少按键处理: {sh_key}"

    # 4. 验证 TTY 检测与参数支持
    assert "IsInputRedirected" in ps1_text
    assert "-t 0" in sh_text
    assert "Tui" in ps1_text
    assert "TUI" in sh_text
    assert "Force" in ps1_text
    assert "FORCE" in sh_text


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_overwrites_sentinel_blocks_physical_directory_overwrite(tmp_path):
    """P1-09 动作 2：Overwrites 哨兵严格生效，遇宿主同名真实物理目录强制阻断并保护用户文件。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_data"
    mock_host = tmp_path / "mock_agent_host"
    sandbox_data.mkdir()
    mock_host.mkdir()

    # 在宿主目录下预先放置一个真实的物理目录（非 Junction），并写入用户私有文件
    conflicting_skill = mock_host / "a-stock-agents"
    conflicting_skill.mkdir(parents=True)
    user_file = conflicting_skill / "my_user_secret_strategy.txt"
    user_file.write_text("critical user secret content", encoding="utf-8")

    # 执行安装，不带 -Force
    cmd = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Agent", str(mock_host),
        "-Method", "link",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)

    # 必须 fail-closed 阻断退出 (exit code 1)
    assert result.returncode == 1, f"Overwrites 冲突时应退出 1，实际: {result.returncode}, stdout: {result.stdout}"

    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["reason_code"] == "OVERWRITE_CONFLICT"
    assert payload["overwrites_count"] >= 1
    conflicts = payload["conflicts"]
    if isinstance(conflicts, dict):
        conflicts = [conflicts]
    assert any(c["skill"] == "a-stock-agents" for c in conflicts)

    # 用户私有资产必须 100% 留存，未被覆盖或删除
    assert user_file.is_file(), "用户私有文件被意外删除！"
    assert user_file.read_text(encoding="utf-8") == "critical user secret content"


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_overwrites_sentinel_allows_force_override(tmp_path):
    """P1-09 动作 3：当显式传递 -Force 时，允许用户授权覆盖已有冲突目录。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_data"
    mock_host = tmp_path / "mock_agent_host"
    sandbox_data.mkdir()
    mock_host.mkdir()

    conflicting_skill = mock_host / "a-stock-agents"
    conflicting_skill.mkdir(parents=True)
    (conflicting_skill / "temp.txt").write_text("temp", encoding="utf-8")

    cmd = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Agent", str(mock_host),
        "-Method", "link",
        "-SkipDeps",
        "-Yes",
        "-Force",
        "-Json"
    ]
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"带 -Force 应该成功: stderr={result.stderr}, stdout={result.stdout}"

    payload = json.loads(result.stdout)
    assert payload["status"] == "installed"
    assert payload["skills_count"] == 20


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_overwrites_sentinel_accepts_existing_junction_mounts(tmp_path):
    """P1-09 动作 4：无同名物理冲突时 Overwrites: 0；已建立的 Junction 再次运行时安全放行。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_data"
    mock_host = tmp_path / "mock_agent_host"
    sandbox_data.mkdir()
    mock_host.mkdir()

    # 第一次全新安装
    cmd = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Agent", str(mock_host),
        "-Method", "link",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    res1 = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res1.returncode == 0
    p1 = json.loads(res1.stdout)
    assert p1["status"] == "installed"
    assert p1["overwrites_count"] == 0
    assert len(p1["conflicts"]) == 0

    # 第二次在已建立 Junction 的目录上重复运行（Junction 不应被判定为物理冲突）
    res2 = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res2.returncode == 0
    p2 = json.loads(res2.stdout)
    assert p2["status"] == "installed"
    assert p2["overwrites_count"] == 0


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_inspect_mode_includes_overwrites_count_and_conflicts_fields():
    """P1-09 动作 5：-Inspect 探测接口输出标准结构包含 overwrites_count 与 conflicts 统计。"""
    install_ps1 = ROOT / "install.ps1"
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1), "-Inspect", "-Json"]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res.returncode == 0

    data = json.loads(res.stdout)
    assert "overwrites_count" in data
    assert isinstance(data["overwrites_count"], int)
    assert "conflicts" in data
    assert isinstance(data["conflicts"], (list, dict))
    for ag in data["agents"].values():
        assert "overwrites_count" in ag
        assert "conflicts" in ag


# ==============================================================================
# 16. 多版本原子切换与一键回滚升级链门禁（P1-10）
# ==============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_multi_version_release_directory_and_current_link_layout(tmp_path):
    """P1-10 动作 1：Release 多版本独立部署至 releases/<version>，通过 current Junction 寻址。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_layout"

    cmd = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"install.ps1 failed: {res.stderr}\n{res.stdout}"

    # 验证 releases/<version> 存在且包含完整技能
    v3_dir = sandbox_data / "releases" / "v3.0.0"
    assert v3_dir.is_dir(), "releases/v3.0.0 未建立"

    # 验证 current Junction 存在且指向 releases/v3.0.0
    current_link = sandbox_data / "current"
    assert current_link.is_dir(), "current Junction 未建立"

    receipt_file = sandbox_data / "install.json"
    assert receipt_file.is_file()
    receipt = json.loads(receipt_file.read_text(encoding="utf-8-sig"))
    assert receipt["version"] == "v3.0.0"
    assert receipt["previous_version"] is None
    assert Path(receipt["current_target"]).resolve() == v3_dir.resolve()

    # 验证用户私有数据根（output/local/log/temp）与 releases/ 目录同级物理隔离
    for folder in ("output", "local", "log", "temp", "releases"):
        assert (sandbox_data / folder).is_dir()
        assert not (v3_dir / folder).exists(), f"代码版本目录内严禁包含用户私有数据桶 {folder}"


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_atomic_update_and_zero_copy_host_switching(tmp_path):
    """P1-10 动作 2：install.ps1 -Update 实现零拷贝原子切换，所有宿主技能瞬间生效。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_update"
    mock_host = tmp_path / "mock_host"
    sandbox_data.mkdir()
    mock_host.mkdir()

    # 1. 初始安装 v3.0.0，挂载至 mock_host
    cmd_init = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Agent", str(mock_host),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    res_init = subprocess.run(cmd_init, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_init.returncode == 0

    # 在 v3.0.0 的 a-stock-agents 写入版本标记
    v3_anchor = sandbox_data / "releases" / "v3.0.0"
    v3_marker = None
    for cand in (v3_anchor / "skills" / "a-stock-agents", v3_anchor / "skill_bundle" / "skills" / "a-stock-agents"):
        if cand.is_dir():
            v3_marker = cand / "version_marker.txt"
            v3_marker.write_text("VERSION_3_0_0", encoding="utf-8")
            break
    assert v3_marker is not None

    # 检查宿主目录下的挂载是否立即可见
    host_anchor = mock_host / "a-stock-agents"
    assert host_anchor.is_dir()
    assert (host_anchor / "version_marker.txt").is_file()
    assert (host_anchor / "version_marker.txt").read_text(encoding="utf-8") == "VERSION_3_0_0"

    # 2. 构造模拟新版本源 v3.1.0（基于现有代码，添加 v3.1.0 标记）
    new_release_src = tmp_path / "new_release_v310"
    shutil.copytree(ROOT / "skill_bundle", new_release_src / "skill_bundle")
    for f in ("install.ps1", "install.sh", "requirements.txt"):
        if (ROOT / f).is_file():
            shutil.copy2(ROOT / f, new_release_src / f)

    new_marker = new_release_src / "skill_bundle" / "skills" / "a-stock-agents" / "version_marker.txt"
    new_marker.write_text("VERSION_3_1_0", encoding="utf-8")

    # 3. 运行 -Update 升级到 v3.1.0
    cmd_update = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Update",
        "-Version", "v3.1.0",
        "-SourceDir", str(new_release_src),
        "-SkipDeps",
        "-Json"
    ]
    res_update = subprocess.run(cmd_update, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_update.returncode == 0, f"Update failed: {res_update.stderr}\n{res_update.stdout}"

    payload = json.loads(res_update.stdout)
    assert payload["status"] == "success"
    assert payload["action"] == "update"
    assert payload["previous_version"] == "v3.0.0"
    assert payload["version"] == "v3.1.0"

    # 4. 关键验证：宿主目录无需任何重新挂载，零拷贝瞬间切到 VERSION_3_1_0
    assert (host_anchor / "version_marker.txt").read_text(encoding="utf-8") == "VERSION_3_1_0"

    # 验证 current 指向新版
    current_link = sandbox_data / "current"
    assert (current_link / "skill_bundle" / "skills" / "a-stock-agents" / "version_marker.txt").read_text(encoding="utf-8") == "VERSION_3_1_0"


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_one_click_rollback_switches_back_atomically(tmp_path):
    """P1-10 动作 3：install.ps1 -Rollback 一键回滚上一可用版本，宿主同步回退。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_rollback"
    mock_host = tmp_path / "mock_host"
    sandbox_data.mkdir()
    mock_host.mkdir()

    # 1. 安装 v3.0.0
    cmd_v1 = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Agent", str(mock_host),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    assert subprocess.run(cmd_v1, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0
    host_anchor = mock_host / "a-stock-agents"
    v3_marker = sandbox_data / "releases" / "v3.0.0" / "skill_bundle" / "skills" / "a-stock-agents" / "tag.txt"
    v3_marker.write_text("TAG_3_0_0", encoding="utf-8")
    assert (host_anchor / "tag.txt").read_text(encoding="utf-8") == "TAG_3_0_0"

    # 2. 升级到 v3.1.0
    new_release_src = tmp_path / "src_v310"
    shutil.copytree(ROOT / "skill_bundle", new_release_src / "skill_bundle")
    for f in ("install.ps1", "install.sh", "requirements.txt"):
        if (ROOT / f).is_file():
            shutil.copy2(ROOT / f, new_release_src / f)
    (new_release_src / "skill_bundle" / "skills" / "a-stock-agents" / "tag.txt").write_text("TAG_3_1_0", encoding="utf-8")

    cmd_v2 = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Update",
        "-Version", "v3.1.0",
        "-SourceDir", str(new_release_src),
        "-SkipDeps",
        "-Json"
    ]
    assert subprocess.run(cmd_v2, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0
    assert (host_anchor / "tag.txt").read_text(encoding="utf-8") == "TAG_3_1_0"

    # 3. 执行 -Rollback 一键回滚
    cmd_rollback = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Rollback",
        "-Json"
    ]
    res_rb = subprocess.run(cmd_rollback, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_rb.returncode == 0, f"Rollback failed: {res_rb.stderr}\n{res_rb.stdout}"

    payload = json.loads(res_rb.stdout)
    assert payload["status"] == "success"
    assert payload["action"] == "rollback"
    assert payload["active_version"] == "v3.0.0"
    assert payload["rolled_back_from"] == "v3.1.0"

    # 4. 验证宿主目录与 current 已瞬间切回 TAG_3_0_0
    assert (host_anchor / "tag.txt").read_text(encoding="utf-8") == "TAG_3_0_0"
    assert Path(payload["current_target"]).resolve() == (sandbox_data / "releases" / "v3.0.0").resolve()


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_update_aborts_and_protects_current_if_doctor_fails(tmp_path):
    """P1-10 动作 4：新版本冒烟失败时坚决熔断，拒绝重定向 current，保持当前版本可用。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_abort"
    mock_host = tmp_path / "mock_host"
    sandbox_data.mkdir()
    mock_host.mkdir()

    # 1. 正常初始安装 v3.0.0
    cmd_init = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Agent", str(mock_host),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    assert subprocess.run(cmd_init, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0

    # 2. 构造一个 doctor.py 故意报错退出的破坏性新版本
    broken_src = tmp_path / "broken_release"
    shutil.copytree(ROOT / "skill_bundle", broken_src / "skill_bundle")
    for f in ("install.ps1", "install.sh", "requirements.txt"):
        if (ROOT / f).is_file():
            shutil.copy2(ROOT / f, broken_src / f)

    # 故意破坏 doctor.py 使其 exit 1
    broken_doctor = broken_src / "skill_bundle" / "runtime" / "doctor.py"
    broken_doctor.write_text("import sys; sys.exit(1)", encoding="utf-8")

    cmd_bad_update = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Update",
        "-Version", "v3.2.0-broken",
        "-SourceDir", str(broken_src),
        "-SkipDeps",
        "-Json"
    ]
    res_bad = subprocess.run(cmd_bad_update, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_bad.returncode == 1, f"损坏版本升级应被阻断: {res_bad.stdout}"

    payload = json.loads(res_bad.stdout)
    assert payload["status"] == "error"
    assert payload["reason_code"] == "UPDATE_SMOKE_FAILED"
    assert payload["active_version"] == "v3.0.0"

    # 坚决守住当前版本：current 仍必须指向 v3.0.0
    receipt = json.loads((sandbox_data / "install.json").read_text(encoding="utf-8-sig"))
    assert receipt["version"] == "v3.0.0"
    current_target = Path(receipt["current_target"]).resolve()
    assert current_target == (sandbox_data / "releases" / "v3.0.0").resolve()


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_user_private_data_strictly_preserved_during_update_and_rollback(tmp_path):
    """P1-10 动作 5：升级与回滚全程 100% 物理隔离用户资产，自选股 CSV 与凭据比特级零修改。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_user_data"
    sandbox_data.mkdir()

    # 1. 初始安装
    cmd_init = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    assert subprocess.run(cmd_init, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0

    # 2. 用户在数据根创建私有交付物与配置
    watchlist_csv = sandbox_data / "output" / "pools" / "watchlist.csv"
    watchlist_csv.parent.mkdir(parents=True, exist_ok=True)
    watchlist_csv.write_text("000001,平安银行,12.50\n600519,贵州茅台,1800.00\n", encoding="utf-8")

    report_html = sandbox_data / "output" / "reports" / "report_000001.html"
    report_html.parent.mkdir(parents=True, exist_ok=True)
    report_html.write_text("<html><body>User Private Investment Report</body></html>", encoding="utf-8")

    app_yaml = sandbox_data / "local" / "settings" / "application.yaml"
    app_yaml.parent.mkdir(parents=True, exist_ok=True)
    app_yaml.write_text("user_custom_setting: true\nmode: live\n", encoding="utf-8")

    env_file = sandbox_data / "local" / "settings" / ".env"
    env_file.write_text("TUSHARE_TOKEN=user_super_secret_token_12345\n", encoding="utf-8")

    hash_watchlist = hashlib.sha256(watchlist_csv.read_bytes()).hexdigest()
    hash_report = hashlib.sha256(report_html.read_bytes()).hexdigest()
    hash_yaml = hashlib.sha256(app_yaml.read_bytes()).hexdigest()
    hash_env = hashlib.sha256(env_file.read_bytes()).hexdigest()

    # 3. 构造新版本源并升级到 v3.1.0
    new_release_src = tmp_path / "src_v310"
    shutil.copytree(ROOT / "skill_bundle", new_release_src / "skill_bundle")
    for f in ("install.ps1", "install.sh", "requirements.txt"):
        if (ROOT / f).is_file():
            shutil.copy2(ROOT / f, new_release_src / f)

    cmd_update = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Update",
        "-Version", "v3.1.0",
        "-SourceDir", str(new_release_src),
        "-SkipDeps",
        "-Json"
    ]
    res_up = subprocess.run(cmd_update, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_up.returncode == 0

    # 4. 升级后断言：用户数据 100% 完整留存，哈希完全一致
    assert hashlib.sha256(watchlist_csv.read_bytes()).hexdigest() == hash_watchlist
    assert hashlib.sha256(report_html.read_bytes()).hexdigest() == hash_report
    assert hashlib.sha256(app_yaml.read_bytes()).hexdigest() == hash_yaml
    assert hashlib.sha256(env_file.read_bytes()).hexdigest() == hash_env

    # 5. 执行回滚到 v3.0.0
    cmd_rollback = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Rollback",
        "-Json"
    ]
    res_rb = subprocess.run(cmd_rollback, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_rb.returncode == 0

    # 6. 回滚后断言：用户数据依然 100% 完整留存，零丢失
    assert hashlib.sha256(watchlist_csv.read_bytes()).hexdigest() == hash_watchlist
    assert hashlib.sha256(report_html.read_bytes()).hexdigest() == hash_report
    assert hashlib.sha256(app_yaml.read_bytes()).hexdigest() == hash_yaml
    assert hashlib.sha256(env_file.read_bytes()).hexdigest() == hash_env


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_rollback_blocks_if_no_previous_version(tmp_path):
    """P1-10 动作 6：全新安装未发生升级时调用 -Rollback 应安全阻断，提示无历史版本。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_no_prev"

    cmd_init = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    assert subprocess.run(cmd_init, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0

    cmd_rb = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Rollback",
        "-Json"
    ]
    res_rb = subprocess.run(cmd_rb, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_rb.returncode == 1

    payload = json.loads(res_rb.stdout)
    assert payload["status"] == "error"
    assert payload["reason_code"] == "ROLLBACK_NO_PREVIOUS_VERSION"


# ==============================================================================
# 17. CLI --json 输出结构契约与 20 入口发现测试 (P1-06)
# ==============================================================================

def test_skill_list_discovery_and_manifest_alignment():
    """P1-06 动作 1：astock skill list 与 skill list --json 输出结构与 manifest 条目数对齐。

    断言：
    - 文本模式输出包含「已注册技能模块 (20 个)」且包含锚点技能 a-stock-agents 与 19 项业务技能；
    - --json 模式输出为合法 JSON，payload 包含 total==20 且 skills 列表长度 20；
    - skills 列表与 skills_manifest.json (19 项) + a-stock-agents (1 项锚点) 严格一致。
    """
    cli_py = RUNTIME_ENTRY / "cli.py"
    manifest_path = SKILLS_ROOT.parent / "assets" / "config" / "skills_manifest.json"

    # 1. 纯文本模式
    res_text = _run([sys.executable, cli_py, "skill", "list"])
    assert res_text.returncode == 0, f"skill list failed: {res_text.stderr}"
    assert "已注册技能模块 (20 个)" in res_text.stdout
    assert "a-stock-agents" in res_text.stdout

    # 2. --json 模式
    res_json = _run([sys.executable, cli_py, "skill", "list", "--json"])
    assert res_json.returncode == 0, f"skill list --json failed: {res_json.stderr}"
    clean_out = res_json.stdout.strip()
    assert clean_out.startswith("{") and clean_out.endswith("}")
    payload = json.loads(clean_out)
    assert payload.get("total") == 20
    assert len(payload.get("skills", [])) == 20
    assert "a-stock-agents" in payload["skills"]

    # 3. 与权威清单 skills_manifest.json 对齐
    manifest_ids = {s["id"] for s in json.loads(manifest_path.read_text(encoding="utf-8"))["skills"]}
    assert len(manifest_ids) == 19
    assert set(payload["skills"]) == manifest_ids | {"a-stock-agents"}


def test_cli_json_zero_pollution_contract():
    """P1-06 动作 2：代表性 CLI 命令追加 --json 时，输出流为纯 JSON，严禁非 JSON 文本混杂。"""
    from concurrent.futures import ThreadPoolExecutor

    cli_py = RUNTIME_ENTRY / "cli.py"
    commands = [
        ("tips", [sys.executable, cli_py, "tips", "--json"]),
        ("validate-model", [sys.executable, cli_py, "validate-model", "--model", "Kronos", "--code", "600519", "--json"]),
        ("intent", [sys.executable, cli_py, "intent", "分析贵州茅台走势", "--json"]),
        ("funnel", [sys.executable, cli_py, "funnel", "validate", "--json"]),
        ("pool_list", [sys.executable, cli_py, "pool", "list", "--json"]),
        ("pool_audit", [sys.executable, cli_py, "pool", "audit", "--json"]),
        ("trade_balance", [sys.executable, cli_py, "trade", "balance", "--json"]),
        ("shortline", [sys.executable, cli_py, "shortline", "check", "--code", "600519", "--json"]),
        ("report", [sys.executable, cli_py, "report", "600519", "--json"]),
    ]

    with ThreadPoolExecutor(max_workers=min(6, len(commands))) as pool:
        futures = [(name, pool.submit(_run, cmd, timeout=30)) for name, cmd in commands]
        results = {name: fut.result() for name, fut in futures}

    for name, res in results.items():
        assert res.returncode == 0, f"Command [{name}] failed with returncode {res.returncode}:\n{res.stderr}"
        clean = res.stdout.strip()
        assert clean.startswith("{") and clean.endswith("}"), (
            f"Command [{name}] standard output is polluted with non-JSON text:\n{res.stdout}"
        )
        data = json.loads(clean)
        assert isinstance(data, dict), f"Command [{name}] JSON payload is not an object: {data}"
        if name == "report":
            assert data.get("status") == "success"
            assert data.get("report_path", "").endswith(".html")


def test_cli_json_trade_principles_structural_contract():
    """P1-06 动作 3：个股实战交易反应动作与决策类 CLI 命令必须包含实战交易三原则契约字段。

    根据 AGENTS.md 铁律：
    1. 最低保本价 (breakeven_price > 0)；
    2. 三级风控止损阶梯 (T0警戒线 -3% / T1减仓线 -5% / T2绝杀线 -8%)；
    3. 三场景即时动作单 (开盘冲高 / 盘中震荡 / 盘中急跌)。
    """
    cli_py = RUNTIME_ENTRY / "cli.py"

    # 1. astock action (保本价精算与动作单)
    res_act = _run([sys.executable, cli_py, "action", "--code", "600519", "--cost", "1600", "--shares", "100", "--json"])
    assert res_act.returncode == 0, f"action failed: {res_act.stderr}"
    data_act = json.loads(res_act.stdout.strip())
    assert data_act.get("breakeven_price", 0) > 0, "action --json 必须包含大于0的最低保本价"
    assert "action_items" in data_act, "action --json 必须包含实战交易动作项"
    assert "downside_diagnosis" in data_act, "action --json 必须包含下跌场景诊断"

    # 2. astock pattern chenxiaoqun (顶级游资总龙头战法：三原则全覆盖)
    res_cxq = _run([sys.executable, cli_py, "pattern", "chenxiaoqun", "600519", "--json"])
    assert res_cxq.returncode == 0, f"pattern chenxiaoqun failed: {res_cxq.stderr}"
    data_cxq = json.loads(res_cxq.stdout.strip())
    assert data_cxq.get("breakeven_price", 0) > 0, "chenxiaoqun 必须输出精确最低保本价"
    risk_ctrl = data_cxq.get("risk_control", {})
    assert "t0_warning_line" in risk_ctrl, "缺少 T0 警戒线"
    assert "t1_reduce_line" in risk_ctrl, "缺少 T1 减仓线"
    assert "t2_cut_line" in risk_ctrl, "缺少 T2 绝杀线"
    assert risk_ctrl["t0_warning_line"]["loss_pct"] == 3.0, "T0 警戒线必须为 3%"
    assert risk_ctrl["t1_reduce_line"]["loss_pct"] == 5.0, "T1 减仓线必须为 5%"
    assert risk_ctrl["t2_cut_line"]["loss_pct"] == 8.0, "T2 绝杀线必须为 8%"
    scenarios = data_cxq.get("three_scenario_actions", {})
    assert "open_rush" in scenarios, "缺少开盘冲高应对动作"
    assert "intraday_consolidation" in scenarios, "缺少盘中震荡应对动作"
    assert "sudden_drop" in scenarios, "缺少盘中跳水急跌应对动作"


# ==============================================================================
# 18. P1-07 GitHub Actions CI 流水线契约与跨平台矩阵守卫
# ==============================================================================


def test_ci_workflow_structure_and_yaml_contract():
    """P1-07 动作 1：.github/workflows/ci.yml 必须存在且符合 YAML 结构契约。"""
    ci_file = ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_file.is_file(), f"CI 配置文件不存在: {ci_file}"
    content = ci_file.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    assert isinstance(data, dict), "ci.yml 必须解析为字典"
    assert "name" in data, "ci.yml 必须包含 name 字段"

    # 触发条件校验（pyyaml 1.1 可能将 on 解析为布尔 True）
    triggers = data.get("on") if "on" in data else data.get(True)
    assert triggers is not None, "ci.yml 必须声明触发条件 (on)"
    assert "push" in triggers, "CI 必须在 push 时触发"
    assert "pull_request" in triggers, "CI 必须在 pull_request 时触发"
    push_branches = triggers["push"].get("branches", [])
    assert any(b in push_branches for b in ["main", "master"]), "push 触发分支必须包含 main 或 master"
    assert "v*" in triggers["push"].get("tags", []), "push 触发必须覆盖发版 tag (v*)"
    pr_branches = triggers["pull_request"].get("branches", [])
    assert any(b in pr_branches for b in ["main", "master"]), "pull_request 触发分支必须包含 main 或 master"

    # 并发与安全权限
    concurrency = data.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is True, "CI 必须启用 cancel-in-progress"
    permissions = data.get("permissions", {})
    assert permissions.get("contents") == "read", "CI 必须遵循最小权限原则 (contents: read)"


def test_ci_workflow_matrix_and_test_gate_coverage():
    """P1-07 动作 2：CI 流水线必须覆盖跨平台矩阵（Windows + Linux）与关键门禁执行流。"""
    ci_file = ROOT / ".github" / "workflows" / "ci.yml"
    content = ci_file.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    jobs = data.get("jobs", {})
    assert "test-matrix" in jobs, "CI jobs 必须包含 test-matrix 作业"
    job = jobs["test-matrix"]

    # 矩阵覆盖
    strategy = job.get("strategy", {})
    matrix = strategy.get("matrix", {})
    os_list = matrix.get("os", [])
    assert any("ubuntu" in str(os_name).lower() for os_name in os_list), "矩阵必须覆盖 Linux (ubuntu)"
    assert any("windows" in str(os_name).lower() for os_name in os_list), "矩阵必须覆盖 Windows (windows)"
    py_versions = [str(v) for v in matrix.get("python-version", [])]
    assert any(v in py_versions for v in ["3.11", "3.12"]), "矩阵必须包含主流 Python 版本 (3.11/3.12)"

    # 步骤与关键门禁
    steps = job.get("steps", [])
    step_runs = "\n".join(str(s.get("run", "")) for s in steps)

    # 核心门禁与发布链路断言
    assert "pytest -m core" in step_runs, "CI 必须执行 P0 核心门禁 (pytest -m core)"
    assert "test_release_delivery_gate.py" in step_runs, "CI 必须执行发布交付链路门禁 (test_release_delivery_gate.py)"
    assert "common.py" in step_runs, "CI 必须执行打包构建冒烟校验"
    assert "doctor.py" in step_runs, "CI 必须执行 doctor 诊断冒烟校验"
    assert "install.ps1" in step_runs, "CI 必须包含 Windows 安装器冒烟"
    assert "install.sh" in step_runs, "CI 必须包含 Linux 安装器冒烟"


def test_ci_workflow_no_sensitive_or_local_paths():
    """P1-07 动作 3：CI 配置文件严禁硬编码本地绝对路径或泄露私有数据/凭据文件。"""
    ci_file = ROOT / ".github" / "workflows" / "ci.yml"
    content = ci_file.read_text(encoding="utf-8")
    for forbidden in ["cvdnn", "C:\\", "D:\\", "/Users/", "/home/", ".env"]:
        assert forbidden not in content, f"CI 配置文件包含硬编码或敏感路径标识: {forbidden}"


# ==============================================================================
# 19. P2 文档与口径一致性常驻门禁（P2-01 ~ P2-03）
# ==============================================================================

def test_readme_and_docs_skill_count_alignment():
    """P2-01：统一技能计数口径为 19 项专业技能 + 1 项锚点总入口 = 20 个入口。

    验证：
    1. README.md 标题与正文声明 19 项专业技能（+1 锚点总入口，共 20 个入口）；
    2. README.md 核心功能表格中逐一列出 20 个技能行（1 锚点 + 19 专业技能），无遗漏；
    3. docs/index.md 导图与正文统一为 19 项量化技能体系与总入口（共 20 个入口）；
    4. skills_manifest.json 权威清单中包含 19 项业务技能，与锚点 a-stock-agents 合计 20 个入口。
    """
    manifest_path = ROOT / "skill_bundle" / "assets" / "config" / "skills_manifest.json"
    assert manifest_path.is_file(), "skills_manifest.json 缺失"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    skills_list = manifest.get("skills", [])
    assert len(skills_list) == 19, f"skills_manifest.json 业务技能清单必须为 19 项，实际: {len(skills_list)}"
    manifest_ids = {s["id"] for s in skills_list}
    all_20_ids = manifest_ids | {"a-stock-agents"}
    assert len(all_20_ids) == 20, "19 项业务技能 + 1 项锚点总入口合计必须为 20 个入口"

    # 1. 验证 README.md 口径与表格
    readme_path = ROOT / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8")
    assert "19 项专业量化技能体系（+1 锚点总入口，共 20 个入口）" in readme_text
    assert "19 项专业量化技能清单与 1 个总入口（共 20 个入口" in readme_text

    # 验证 README.md 表格列出了全部 20 个技能 ID
    for skill_id in all_20_ids:
        assert f"`{skill_id}`" in readme_text, f"README.md 技能表格缺少技能 ID: {skill_id}"

    # 2. 验证 docs/index.md 口径
    index_path = ROOT / "docs" / "index.md"
    index_text = index_path.read_text(encoding="utf-8")
    assert "19 项量化技能体系与总入口（共 20 个入口" in index_text
    assert "skill_bundle/skills" in index_text


def test_readme_host_list_and_roadmap_alignment():
    """P2-02：README.md 宿主清单包含 WorkBuddy，第七节路线图不再宣称「摆脱宿主依赖」。

    验证：
    1. README.md 第四节宿主指南明确包含 WorkBuddy；
    2. README.md 第七节演进路线遵循 SSOT 规约（WebUI 是可选辅助/开发调试应用，Release 基础能力不依赖它），
       严禁出现「摆脱对第三方 AI 终端工具...的宿主环境依赖」或「摆脱宿主依赖」的相悖表述。
    """
    readme_path = ROOT / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8")

    # 1. 宿主清单包含 WorkBuddy
    assert "WorkBuddy" in readme_text, "README.md 必须包含 WorkBuddy 宿主"
    assert "Antigravity / Hermes / Codex / WorkBuddy" in readme_text

    # 2. 演进路线无违背 SSOT 的表述
    assert "摆脱对第三方" not in readme_text, "README.md 严禁宣称摆脱第三方 AI 工具作为路线"
    assert "摆脱宿主依赖" not in readme_text, "README.md 严禁宣称摆脱宿主依赖"
    assert "可选的 Web 辅助工作台与技能治理控制台" in readme_text


def test_testing_guide_and_test_readme_baseline_alignment():
    """P2-03：测试文档映射与死配置修正，基线数字严格对齐实测值。

    验证：
    1. tests/README.md 与 docs/guidelines/engineering/testing-guide.md 档位表中
       core 档用例数严格登记为 354，收集总数登记为 714；
    2. pyproject.toml 的 testpaths 仅包含 ["tests"]，死条目 skill_bundle/skills 彻底移除；
    3. tests/README.md 与 testing-guide.md 零死路径（如未迁移的 scripts/core）。
    """
    pyproject_path = ROOT / "pyproject.toml"
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    assert 'testpaths = ["tests"]' in pyproject_text
    assert '"skill_bundle/skills"' not in pyproject_text

    tests_readme = ROOT / "tests" / "README.md"
    tr_text = tests_readme.read_text(encoding="utf-8")
    assert "358" in tr_text, "tests/README.md 必须反映 core 档实测 358 例基线"
    assert "718" in tr_text, "tests/README.md 必须反映收集总数 718 例基线"

    guide_path = ROOT / "docs" / "guidelines" / "engineering" / "testing-guide.md"
    guide_text = guide_path.read_text(encoding="utf-8")
    assert "358" in guide_text, "testing-guide.md 必须反映 core 档实测 358 例基线"
    assert "718" in guide_text, "testing-guide.md 必须反映收集总数 718 例基线"


# ==============================================================================
# 20. 独立 Release 仓库发布与 npx skills add 通用生态常驻门禁 (P2-04)
# ==============================================================================

def test_release_distribution_tree_export_and_json_contract(tmp_path):
    """P2-04 动作 1：publish_release.py 导出标准规范的 Release 分发目录结构与机器契约。

    断言：
    1. export_release_distribution 返回状态为 success，包含 20 个技能入口（1 锚点 + 19 专业技能）；
    2. 输出目录中包含标准 skills/ 根，包含全部 20 个技能目录；
    3. 锚点技能 skills/a-stock-agents 包含收敛注入的 runtime/、assets/、references/ 与 requirements*.txt；
    4. 锚点 bundle.json 明确声明 distribution: release, anchor: true, skills: '..'；
    5. .codex-plugin/plugin.json 存在且声明 skills: './skills' 与 entry: './skills/a-stock-agents'；
    6. INSTALL.json 存在且包含 universal_skills 与 ecosystem_command；
    7. install.ps1 与 install.sh 随包存在，且生成全文件 SHA256SUMS 账本。
    """
    from tools.packaging.publish_release import export_release_distribution

    dist_dir = tmp_path / "release_dist"
    result = export_release_distribution(output_dir=dist_dir, version_tag="v3.0.0")

    assert result["status"] == "success"
    assert result["dry_run"] is False
    assert result["skills_count"] == 20
    assert result["business_skills"] == 19
    assert result["anchor_skill"] == "skills/a-stock-agents"
    assert result["codex_plugin"] == ".codex-plugin/plugin.json"
    assert result["ecosystem_command"] == "npx skills add cvdnn/a-stock-agents -g"
    assert result["files_written"] > 50

    # 1. skills/ 根与 20 个技能目录
    skills_root = dist_dir / "skills"
    assert skills_root.is_dir()
    skill_dirs = [d for d in skills_root.iterdir() if d.is_dir()]
    assert len(skill_dirs) == 20

    # 2. 锚点技能
    anchor_dir = skills_root / "a-stock-agents"
    assert anchor_dir.is_dir()
    assert (anchor_dir / "SKILL.md").is_file()
    assert (anchor_dir / "bundle.json").is_file()
    marker = json.loads((anchor_dir / "bundle.json").read_text(encoding="utf-8"))
    assert marker["anchor"] is True
    assert marker["distribution"] == "release"
    assert marker["skills"] == ".."
    assert (anchor_dir / "runtime" / "doctor.py").is_file()
    assert (anchor_dir / "runtime" / "core" / "workspace.py").is_file()
    assert (anchor_dir / "assets" / "config" / "skills_manifest.json").is_file()
    assert (anchor_dir / "references" / "execution-contract.md").is_file()
    assert (anchor_dir / "requirements.txt").is_file()
    assert (anchor_dir / "requirements-full.txt").is_file()

    # 3. 专业技能轻量性
    feed_dir = skills_root / "astock-data-feed"
    assert feed_dir.is_dir()
    assert (feed_dir / "SKILL.md").is_file()
    assert not (feed_dir / "runtime").exists(), "专业技能严禁冗余携带 runtime"

    # 4. Codex 插件清单与安装底座
    plugin_file = dist_dir / ".codex-plugin" / "plugin.json"
    assert plugin_file.is_file()
    plugin_data = json.loads(plugin_file.read_text(encoding="utf-8"))
    assert plugin_data["name"] == "a-stock-agents"
    assert plugin_data["skills"] == "./skills"
    assert plugin_data["entry"] == "./skills/a-stock-agents"

    assert (dist_dir / "install.ps1").is_file()
    assert (dist_dir / "install.sh").is_file()
    assert (dist_dir / "INSTALL.json").is_file()
    assert (dist_dir / "requirements.txt").is_file()
    assert (dist_dir / "requirements-full.txt").is_file()
    assert (dist_dir / "LICENSE").is_file()
    assert (dist_dir / "README.md").is_file()
    assert (dist_dir / "SHA256SUMS").is_file()


def test_release_distribution_npx_skills_add_discovery_simulation(tmp_path):
    """P2-04 动作 2：模拟 npx skills add cvdnn/a-stock-agents -g 扫描与接入。

    断言：
    1. 模拟 skills CLI 扫描 release 分发的 skills/ 目录，全部 20 个子目录均含有合规 SKILL.md frontmatter；
    2. 模拟拉取锚点技能 + 业务技能到用户宿主技能根（~/.agents/skills/）；
    3. 在隔离环境中，业务技能转发壳通过兄弟定位 (../a-stock-agents/bundle.json) 成功唤起核心量化引擎；
    4. 锚点技能内置 doctor.py 在宿主技能根中自检全绿 (20 个入口就绪)。
    """
    from tools.packaging.publish_release import export_release_distribution

    dist_dir = tmp_path / "release_dist"
    export_release_distribution(output_dir=dist_dir, version_tag="v3.0.0")

    # 1. 模拟 npx skills add 扫描
    skills_root = dist_dir / "skills"
    discovered_skills = {}
    for sdir in skills_root.iterdir():
        if sdir.is_dir() and (sdir / "SKILL.md").is_file():
            frontmatter = _parse_frontmatter(sdir)
            assert frontmatter["name"] == sdir.name
            assert frontmatter.get("description")
            discovered_skills[sdir.name] = sdir

    assert len(discovered_skills) == 20
    assert "a-stock-agents" in discovered_skills
    assert "astock-data-feed" in discovered_skills
    assert "astock-pool-dashboard" in discovered_skills

    # 2. 模拟用户全局安装全部技能到宿主目录 ~/.agents/skills
    user_skills_dir = tmp_path / "user_skills"
    user_skills_dir.mkdir(parents=True, exist_ok=True)
    for sdir in skills_root.iterdir():
        if sdir.is_dir():
            shutil.copytree(sdir, user_skills_dir / sdir.name)

    # 3. 验证兄弟定位执行
    env = os.environ.copy()
    data_dir = tmp_path / "user_data"
    env["A_STOCK_WORKSPACE_ROOT"] = str(data_dir)
    env["PYTHONPATH"] = ""
    for k in ("A_STOCK_OUTPUT_DIR", "A_STOCK_LOG_DIR", "A_STOCK_TEMP_DIR", "A_STOCK_LOCAL_DIR", "A_STOCK_CONFIG_PATH"):
        env.pop(k, None)

    script = user_skills_dir / "astock-pool-dashboard" / "scripts" / "position_manager.py"
    res = subprocess.run([sys.executable, str(script), "--help"], cwd=str(user_skills_dir / "astock-pool-dashboard"), env=env, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"npx skills add 兄弟定位执行失败:\nstderr: {res.stderr}\nstdout: {res.stdout}"
    assert "position_manager" in (res.stdout + res.stderr)

    # 4. 验证锚点 doctor 自检
    doctor_py = user_skills_dir / "a-stock-agents" / "runtime" / "doctor.py"
    res_doc = subprocess.run([sys.executable, str(doctor_py)], cwd=str(user_skills_dir / "a-stock-agents"), env=env, capture_output=True, text=True, timeout=60)
    assert res_doc.returncode == 0, f"doctor 自检失败:\nstderr: {res_doc.stderr}\nstdout: {res_doc.stdout}"
    health = json.loads(res_doc.stdout)
    assert health["is_healthy"] is True
    assert health["cli_launcher"] is True


def test_archive_standard_release_root_and_codex_plugin(codex_archive: Path):
    """P2-04 动作 3：package_project 生成的 Release ZIP 归档包含标准根与通用生态元数据。

    断言：
    1. 归档包含 .codex-plugin/plugin.json 且格式合法；
    2. 归档包含 README.md 与 INSTALL.json 声明 universal_skills 与 ecosystem_command；
    3. 锚点技能具备完整运行时与自描述 bundle.json。
    """
    with zipfile.ZipFile(codex_archive) as archive:
        names = set(archive.namelist())
        instructions = json.loads(archive.read("INSTALL.json"))

        # 1. 通用生态声明
        assert instructions.get("universal_skills") == "skills"
        assert instructions.get("codex_plugin") == ".codex-plugin/plugin.json"
        assert "npx skills add" in instructions.get("ecosystem_command", "")

        # 2. .codex-plugin/plugin.json
        assert ".codex-plugin/plugin.json" in names
        plugin_meta = json.loads(archive.read(".codex-plugin/plugin.json"))
        assert plugin_meta["name"] == "a-stock-agents"
        assert plugin_meta["skills"] == "./skills"
        assert plugin_meta["entry"] == "./skills/a-stock-agents"

        # 3. 根 README.md 与锚点技能结构
        assert "README.md" in names
        assert "skill_bundle/skills/a-stock-agents/SKILL.md" in names
        assert "skill_bundle/skills/a-stock-agents/bundle.json" in names
        assert "skill_bundle/skills/a-stock-agents/runtime/doctor.py" in names


def test_publish_release_cli_smoke_and_zero_pollution(tmp_path):
    """P2-04 动作 4：publish_release.py CLI 执行冒烟与纯净 JSON 契约。

    断言：
    1. --dry-run --json 快速模拟，stdout 为纯净合规 JSON，退出码 0；
    2. --export-dir <path> --json 实际导出，落盘文件数 > 50，退出码 0。
    """
    script = ROOT / "tools" / "packaging" / "publish_release.py"
    assert script.is_file()

    # 1. dry-run
    res_dry = _run([sys.executable, script, "--dry-run", "--json"])
    assert res_dry.returncode == 0, f"dry-run failed: {res_dry.stderr}"
    out_dry = res_dry.stdout.strip()
    assert out_dry.startswith("{") and out_dry.endswith("}"), f"dry-run output polluted: {res_dry.stdout}"
    data_dry = json.loads(out_dry)
    assert data_dry["status"] == "success"
    assert data_dry["dry_run"] is True
    assert data_dry["skills_count"] == 20

    # 2. 真实导出
    out_dir = tmp_path / "cli_dist"
    res_real = _run([sys.executable, script, "--export-dir", out_dir, "--json"])
    assert res_real.returncode == 0, f"export failed: {res_real.stderr}"
    out_real = res_real.stdout.strip()
    assert out_real.startswith("{") and out_real.endswith("}"), f"export output polluted: {res_real.stdout}"
    data_real = json.loads(out_real)
    assert data_real["status"] == "success"
    assert data_real["files_written"] > 50
    assert (out_dir / "skills" / "a-stock-agents" / "runtime" / "doctor.py").is_file()


# =============================================================================
# 阶段五：P2-05 生命周期执行报告体系 (Lifecycle Execution Report System)
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_install_generates_lifecycle_execution_report(tmp_path):
    """P2-05 动作 1：install.ps1 安装完成后自动生成 Markdown 与 JSON 双格式生命周期执行报告。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_install_rep"
    sandbox_data.mkdir()

    cmd = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"install.ps1 执行失败:\nstderr: {res.stderr}\nstdout: {res.stdout}"

    payload = json.loads(res.stdout)
    assert "latest_execution_report" in payload, "安装收据应包含 latest_execution_report 元数据"
    rep_meta = payload["latest_execution_report"]
    assert rep_meta["action"] == "install"
    assert rep_meta["status"] == "success"
    assert rep_meta["report_id"].startswith("lifecycle-install-")

    # 验证交付物与观测日志目录落地
    reports_dir = sandbox_data / "output" / "reports" / "lifecycle"
    logs_dir = sandbox_data / "log" / "lifecycle"
    assert reports_dir.is_dir(), "output/reports/lifecycle/ 目录未创建"
    assert logs_dir.is_dir(), "log/lifecycle/ 目录未创建"

    md_file = Path(rep_meta["markdown_path"])
    json_file = Path(rep_meta["json_path"])
    latest_md = reports_dir / "latest_lifecycle_report.md"
    latest_json = logs_dir / "latest_lifecycle.json"

    assert md_file.is_file(), f"生命周期 Markdown 报告未找到: {md_file}"
    assert json_file.is_file(), f"生命周期 JSON 报告未找到: {json_file}"
    assert latest_md.is_file(), "latest_lifecycle_report.md 未找到"
    assert latest_json.is_file(), "latest_lifecycle.json 未找到"

    # 验证 Markdown 报告内容结构
    md_text = md_file.read_text(encoding="utf-8")
    assert "生命周期执行报告 (Lifecycle Execution Report)" in md_text
    assert "技能安装部署 (Installation)" in md_text
    assert "## 一、核心执行概要 (Execution Summary)" in md_text
    assert "## 二、过程修改内容 (Process Modifications)" in md_text
    assert "## 三、备份情况与数据安全审计 (Backup & Data Protection)" in md_text
    assert "自选池与股票池隔离" in md_text
    assert "私有配置与凭据隔离" in md_text

    # 验证 JSON 结构字段与物理隔离断言
    json_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert json_data["action"] == "install"
    assert json_data["status"] == "success"
    assert json_data["environment"]["platform"] == "windows"
    assert json_data["execution_details"]["active_version"] == "v3.0.0"
    assert json_data["modifications"]["deployed_release"]
    assert json_data["backup_and_safety"]["user_data_status"]["isolation_policy"] == "STRICT_PHYSICAL_ISOLATION"


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_update_generates_lifecycle_execution_report_and_backup(tmp_path):
    """P2-05 动作 2：install.ps1 -Update 升级时自动备份旧收据，并生成升级执行报告。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_update_rep"
    sandbox_data.mkdir()

    # 1. 初始安装 v3.0.0
    cmd_init = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    assert subprocess.run(cmd_init, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0

    # 2. 构造模拟新版本源 v3.1.0
    new_release_src = tmp_path / "src_v310"
    shutil.copytree(ROOT / "skill_bundle", new_release_src / "skill_bundle")
    for f in ("install.ps1", "install.sh", "requirements.txt"):
        if (ROOT / f).is_file():
            shutil.copy2(ROOT / f, new_release_src / f)

    # 3. 运行 -Update 升级
    cmd_update = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Update",
        "-Version", "v3.1.0",
        "-SourceDir", str(new_release_src),
        "-SkipDeps",
        "-Json"
    ]
    res_up = subprocess.run(cmd_update, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_up.returncode == 0, f"Update failed: {res_up.stderr}\n{res_up.stdout}"

    payload = json.loads(res_up.stdout)
    assert payload["status"] == "success"
    assert payload["action"] == "update"
    assert "execution_report" in payload
    rep_meta = payload["execution_report"]

    # 验证收据备份
    bak_receipt = sandbox_data / "install.json.bak"
    assert bak_receipt.is_file(), "升级前必须先将旧收据镜像备份至 install.json.bak"
    bak_data = json.loads(bak_receipt.read_text(encoding="utf-8-sig"))
    assert bak_data["version"] == "v3.0.0"

    # 验证新收据记录 latest_execution_report
    active_receipt = json.loads((sandbox_data / "install.json").read_text(encoding="utf-8-sig"))
    assert active_receipt["version"] == "v3.1.0"
    assert active_receipt["previous_version"] == "v3.0.0"
    assert active_receipt["latest_execution_report"]["action"] == "update"
    assert active_receipt["latest_execution_report"]["report_id"] == rep_meta["report_id"]

    # 验证报告内容
    md_file = Path(rep_meta["markdown_path"])
    json_file = Path(rep_meta["json_path"])
    assert md_file.is_file()
    assert json_file.is_file()

    md_text = md_file.read_text(encoding="utf-8")
    assert "多版本平滑升级 (Upgrade)" in md_text
    assert "v3.0.0" in md_text
    assert "v3.1.0" in md_text

    json_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert json_data["action"] == "update"
    assert json_data["status"] == "success"
    assert json_data["backup_and_safety"]["rollback_ready"] is True
    assert json_data["backup_and_safety"]["receipt_backup"] == str(bak_receipt)


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_update_failure_generates_aborted_report_and_protects_current(tmp_path):
    """P2-05 动作 3：新版本冒烟失败时，生成 aborted 报告、坚决守住当前版本并记录失败现场。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_abort_rep"
    sandbox_data.mkdir()

    # 1. 正常初始安装 v3.0.0
    cmd_init = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    assert subprocess.run(cmd_init, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0

    # 2. 构造故意使 doctor 自检退出的破坏性新版本
    broken_src = tmp_path / "broken_release"
    shutil.copytree(ROOT / "skill_bundle", broken_src / "skill_bundle")
    for f in ("install.ps1", "install.sh", "requirements.txt"):
        if (ROOT / f).is_file():
            shutil.copy2(ROOT / f, broken_src / f)

    broken_doctor = broken_src / "skill_bundle" / "runtime" / "doctor.py"
    broken_doctor.write_text("import sys; sys.exit(1)", encoding="utf-8")

    cmd_bad = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Update",
        "-Version", "v3.2.0-broken",
        "-SourceDir", str(broken_src),
        "-SkipDeps",
        "-Json"
    ]
    res_bad = subprocess.run(cmd_bad, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_bad.returncode == 1, "冒烟失败必须退出码 1"

    payload = json.loads(res_bad.stdout)
    assert payload["status"] == "error"
    assert payload["reason_code"] == "UPDATE_SMOKE_FAILED"
    assert "execution_report" in payload
    rep_meta = payload["execution_report"]

    # 验证生成了 aborted 状态报告
    json_file = Path(rep_meta["json_path"])
    md_file = Path(rep_meta["markdown_path"])
    assert json_file.is_file()
    assert md_file.is_file()

    json_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert json_data["action"] == "update"
    assert json_data["status"] == "aborted"
    assert json_data["modifications"]["status"] == "aborted_smoke_failure"
    assert json_data["modifications"]["current_link_switched"] is False
    assert json_data["backup_and_safety"]["rollback_ready"] is False

    # 验证守住当前版本
    current_link = sandbox_data / "current"
    receipt = json.loads((sandbox_data / "install.json").read_text(encoding="utf-8-sig"))
    assert receipt["version"] == "v3.0.0"
    assert Path(receipt["current_target"]).resolve() == (sandbox_data / "releases" / "v3.0.0").resolve()


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_rollback_generates_lifecycle_execution_report(tmp_path):
    """P2-05 动作 4：install.ps1 -Rollback 回滚执行时生成回滚审计报告并记录版本跳变。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_rollback_rep"
    sandbox_data.mkdir()

    # 1. 安装 v3.0.0
    cmd_v1 = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    assert subprocess.run(cmd_v1, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0

    # 2. 升级到 v3.1.0
    new_release_src = tmp_path / "src_v310"
    shutil.copytree(ROOT / "skill_bundle", new_release_src / "skill_bundle")
    for f in ("install.ps1", "install.sh", "requirements.txt"):
        if (ROOT / f).is_file():
            shutil.copy2(ROOT / f, new_release_src / f)

    cmd_v2 = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Update",
        "-Version", "v3.1.0",
        "-SourceDir", str(new_release_src),
        "-SkipDeps",
        "-Json"
    ]
    assert subprocess.run(cmd_v2, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0

    # 3. 执行 -Rollback 回滚
    cmd_rb = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Rollback",
        "-Json"
    ]
    res_rb = subprocess.run(cmd_rb, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_rb.returncode == 0, f"Rollback failed: {res_rb.stderr}\n{res_rb.stdout}"

    payload = json.loads(res_rb.stdout)
    assert payload["status"] == "success"
    assert payload["action"] == "rollback"
    assert payload["active_version"] == "v3.0.0"
    assert payload["rolled_back_from"] == "v3.1.0"
    assert "execution_report" in payload
    rep_meta = payload["execution_report"]

    # 验证回滚报告
    json_file = Path(rep_meta["json_path"])
    md_file = Path(rep_meta["markdown_path"])
    assert json_file.is_file()
    assert md_file.is_file()

    md_text = md_file.read_text(encoding="utf-8")
    assert "版本一键回滚 (Rollback)" in md_text
    assert "v3.0.0" in md_text
    assert "v3.1.0" in md_text

    json_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert json_data["action"] == "rollback"
    assert json_data["status"] == "success"
    assert json_data["execution_details"]["active_version"] == "v3.0.0"
    assert json_data["execution_details"]["previous_version"] == "v3.1.0"


@pytest.mark.skipif(not IS_WINDOWS, reason="install.ps1 真实子进程执行仅在 Windows 验证")
def test_uninstall_generates_lifecycle_execution_report(tmp_path):
    """P2-05 动作 5：install.ps1 -Uninstall 卸载宿主引用时生成生命周期报告并保持用户数据物理隔离留存。"""
    install_ps1 = ROOT / "install.ps1"
    sandbox_data = tmp_path / "sandbox_uninst_rep"
    mock_host = tmp_path / "mock_host_rep"
    sandbox_data.mkdir()
    mock_host.mkdir()

    # 1. 安装并挂载至 mock_host
    cmd_init = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Agent", str(mock_host),
        "-Version", "v3.0.0",
        "-SkipDeps",
        "-Yes",
        "-Json"
    ]
    assert subprocess.run(cmd_init, cwd=str(ROOT), capture_output=True, text=True, timeout=60).returncode == 0
    assert (mock_host / "a-stock-agents").exists()

    # 2. 执行卸载
    cmd_uninst = [
        "powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", str(install_ps1),
        "-DataDir", str(sandbox_data),
        "-Uninstall", str(mock_host),
        "-Json"
    ]
    res_uninst = subprocess.run(cmd_uninst, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res_uninst.returncode == 0, f"Uninstall failed: {res_uninst.stderr}\n{res_uninst.stdout}"

    payload = json.loads(res_uninst.stdout)
    assert payload["status"] == "success"
    assert payload["action"] == "uninstall"
    assert "execution_report" in payload
    rep_meta = payload["execution_report"]

    # 验证宿主引用已被安全移除，但目标发布目录与用户数据完好
    assert not (mock_host / "a-stock-agents").exists()
    assert (sandbox_data / "releases" / "v3.0.0").is_dir()
    assert (sandbox_data / "output").is_dir()
    assert (sandbox_data / "local").is_dir()

    # 验证报告文件
    json_file = Path(rep_meta["json_path"])
    md_file = Path(rep_meta["markdown_path"])
    assert json_file.is_file()
    assert md_file.is_file()

    json_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert json_data["action"] == "uninstall"
    assert json_data["status"] == "success"
    assert json_data["modifications"]["uninstalled_agent"] == str(mock_host)
    assert len(json_data["modifications"]["removed_entries"]) >= 1


def test_install_sh_lifecycle_report_parity():
    """P2-05 动作 6：POSIX install.sh 脚本与 Windows install.ps1 具备 100% 生命周周期报告契约一致性。"""
    install_sh = ROOT / "install.sh"
    assert install_sh.is_file(), "install.sh 必须存在"
    sh_content = install_sh.read_text(encoding="utf-8")

    # 1. 验证报告生成函数
    assert "def write_lifecycle_report" in sh_content
    assert "latest_lifecycle_report.md" in sh_content
    assert "latest_lifecycle.json" in sh_content

    # 2. 验证四大生命周期动作均调用报告生成
    assert 'action="install"' in sh_content
    assert 'action="update"' in sh_content
    assert 'action="rollback"' in sh_content
    assert 'action="uninstall"' in sh_content

    # 3. 验证升级失败现场熔断报告
    assert 'status="aborted"' in sh_content
    assert "UPDATE_SMOKE_FAILED" in sh_content

    # 4. 验证 install.json 收据与备份契约
    assert "latest_execution_report" in sh_content
    assert "install.json.bak" in sh_content





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
    allowed_root_files = {"INSTALL.json", "requirements.txt", "requirements-full.txt"}
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
    """codex + --entry：引用式注册（入口指向唯一源，源码不被移动/复制）。"""
    entry = tmp_path / "host-skills"
    result = _run([sys.executable, PLATFORM_SHIMS["codex"],
                   "--bundle", fake_release_bundle, "--entry", entry])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "success", payload
    assert entry.resolve() == (fake_release_bundle / "skills").resolve()
    assert (fake_release_bundle / "skills" / "sample" / "SKILL.md").is_file()


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


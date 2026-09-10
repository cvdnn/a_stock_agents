"""Documentation truthfulness and local-link regression tests."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

AUDITED_SPECS = {
    "SPEC-ENG-001": "docs/specs/engineering/eng-project-structure-and-workspace.md",
    "SPEC-UI-001": "docs/specs/ui/ui-design-and-interaction-specification.md",
    "SPEC-ARCH-001": "docs/specs/architecture/arch-web-aichat-and-skill-governance.md",
    "SPEC-ARCH-002": "docs/specs/architecture/arch-llm-provider-and-role-allocation.md",
    "SPEC-A2UI-001": "docs/specs/a2ui/a2ui-framework-engine-specification.md",
    "SPEC-A2UI-002": "docs/specs/a2ui/a2ui-component-registry-specification.md",
    "SPEC-BIZ-001": "docs/specs/business/biz-broker-commission-configurable-design.md",
    "SPEC-BIZ-002": "docs/specs/business/biz-breakeven-price-calculation-rules.md",
    "SPEC-BIZ-003": "docs/specs/business/biz-trading-execution-and-risk-control.md",
    "SPEC-ALGO-001": "docs/specs/algorithm/algo-lifecycle-and-governance-specification.md",
}


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_audited_specs_are_in_progress() -> None:
    for spec_id, relative_path in AUDITED_SPECS.items():
        text = _read(relative_path)
        assert re.search(r"\*\*实施状态\*\*：实施中\b", text), spec_id
        assert "正式基线 (Production Baseline) | 100% 已交付" not in text, spec_id


def test_token_security_spec_remains_rfc() -> None:
    text = _read("docs/specs/architecture/arch-token-security-gateway.md")
    assert "**实施状态**：架构提案 (RFC / Approved) | 方案待研发 (Backlog)" in text


def test_acceptance_ledger_tracks_every_audited_spec_without_future_pass() -> None:
    text = _read("docs/specs/engineering/eng-remediation-acceptance.md")
    header = next(line for line in text.splitlines() if line.startswith("| spec |"))
    assert [cell.strip() for cell in header.strip("|").split("|")] == [
        "spec",
        "original_claim",
        "findings",
        "tasks",
        "code_paths",
        "tests",
        "current_status",
    ]
    for spec_id in AUDITED_SPECS:
        assert re.search(rf"^\| `{re.escape(spec_id)}` \|", text, re.MULTILINE), spec_id
    assert not re.search(r"\bPASS\b", text, re.IGNORECASE)


def test_current_code_review_guide_links_history_and_existing_code_paths() -> None:
    guide_path = ROOT / "docs/guidelines/code-review.md"
    text = guide_path.read_text(encoding="utf-8")
    assert "../audits/code-review-history.md" in text

    code_paths = re.findall(
        r"`((?:scripts/core|scripts/server|web|tests|bin|config|\.agents)/[^`]+)`",
        text,
    )
    assert code_paths, "current guide must contain checkable repository-local code paths"
    for mapped_path in code_paths:
        assert (ROOT / mapped_path).exists(), mapped_path

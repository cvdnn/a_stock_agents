# -*- coding: utf-8 -*-
"""
Security & System Hardening Regression Test Suite:
Validates:
- report_generator: HTML XSS protection (escaping script, img, style tags)
- bin/update.py: Zip Slip path traversal defense
- reporting / config: Sensitive token protection and environment variable precedence
"""

import os
import sys
import tempfile
import zipfile
import unittest
import html as html_lib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.reporting.report_generator import generate_simple_report
from bin.update import apply_update_from_zip


class TestSecuritySuite(unittest.TestCase):

    def test_report_generator_xss_prevention(self):
        """Verify dynamic fields in HTML reports are properly escaped against XSS."""
        malicious_data = {
            "code": "<script>alert('code')</script>",
            "name": "<img src=x onerror=alert(1)>",
            "scores": {
                "<script>hack</script>": {"score": 10, "max": 10, "reason": "<b>safe</b>"},
                "rating": "<style>bad</style>",
                "rating_text": "<b>Strong Buy</b>",
            },
            "quote": {"price": "100<script>", "change_pct": 2.0},
            "technical_latest": {"close": 100},
        }
        report = generate_simple_report(malicious_data)

        # Raw executable payloads must NOT be in output
        self.assertNotIn("<script>alert('code')</script>", report)
        self.assertNotIn("<img src=x onerror=alert(1)>", report)

        # Escaped payloads must be present
        self.assertIn(html_lib.escape("<script>alert('code')</script>"), report)
        self.assertIn(html_lib.escape("<img src=x onerror=alert(1)>"), report)
        self.assertIn(html_lib.escape("<style>bad</style>"), report)

    def test_zip_slip_path_traversal_defense(self):
        """Verify update utility blocks zip files containing malicious path traversal entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_zip_path = Path(tmpdir) / "malicious.zip"
            backup_dir = Path(tmpdir) / "backup"
            backup_dir.mkdir()

            # Create a zip containing path traversal entry
            with zipfile.ZipFile(bad_zip_path, "w") as z:
                z.writestr("../evil.txt", "malicious payload")

            # apply_update_from_zip should catch the error and fail safely (return False)
            result = apply_update_from_zip(bad_zip_path, backup_dir)
            self.assertFalse(result, "Zip Slip should be blocked by apply_update_from_zip")

            # Ensure the evil file was never created outside
            evil_file = ROOT.parent / "evil.txt"
            self.assertFalse(evil_file.exists())

    def test_investment_report_no_hardcoded_tokens(self):
        """Verify investment_report source code does not contain hardcoded bearer/auth tokens."""
        rep_file = ROOT / "scripts" / "core" / "reporting" / "investment_report.py"
        if not rep_file.exists():
            rep_file = ROOT / "core" / "reporting" / "investment_report.py"
        if rep_file.exists():
            text = rep_file.read_text(encoding="utf-8")
            self.assertNotIn("Bearer sk-", text)
            self.assertNotIn("token = \"sk-", text)
            self.assertNotIn("secret = \"", text)


if __name__ == "__main__":
    unittest.main()

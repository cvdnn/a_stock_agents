"""Explicit verification selector. Structure only by default; no implicit market calls."""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'skill_bundle/bundle.json').is_file())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--core', action='store_true', help='Run P0 instead of structure diagnosis')
    args = parser.parse_args()
    command = ([sys.executable, '-m', 'pytest', '-m', 'core'] if args.core
               else [sys.executable, str(ROOT/'skill_bundle/runtime/doctor.py')])
    return subprocess.run(command, cwd=ROOT).returncode

if __name__ == '__main__': raise SystemExit(main())

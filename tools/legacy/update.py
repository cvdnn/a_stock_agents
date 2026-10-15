"""Retired ZIP overlay updater. Never modifies developer source or user data."""
import sys

def apply_update_from_zip(zip_path, backup_dir):
    print('ZIP overlay updates are retired; use Git for source and the host Release update mechanism.', file=sys.stderr)
    return False

def main():
    print('Updater retired. No files changed. Use Git for development; install Releases through the target host.', file=sys.stderr)
    raise SystemExit(2)

if __name__ == '__main__': main()

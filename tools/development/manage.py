"""Development environment and optional Web launcher; never registers host skills."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'skill_bundle/bundle.json').is_file())


def environment_python():
    path = ROOT/'.venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    return str(path) if path.is_file() else sys.executable


def setup(arguments):
    parser = argparse.ArgumentParser(description='Initialize development dependencies, then diagnose structure')
    parser.add_argument('--browser', action='store_true', help='Include browser testing dependencies; does not install browsers')
    parser.add_argument('--full', action='store_true', help='Include enhanced market providers')
    options = parser.parse_args(arguments)
    extras = ['test']
    if options.browser: extras.append('browser-test')
    if options.full: extras.append('full')
    uv = shutil.which('uv')
    venv = ROOT/'.venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not venv.is_file():
        if uv: subprocess.run([uv, 'venv', str(ROOT/'.venv')], cwd=ROOT, check=True)
        else: subprocess.run([sys.executable, '-m', 'venv', str(ROOT/'.venv')], check=True)
    # Existing lock omits browser-test/xdist. Constrain runtime dependencies to its
    # exported pins, while resolving explicitly selected development extras.
    prefix = ([uv, 'pip', 'install', '--python', str(venv)] if uv
              else [str(venv), '-m', 'pip', 'install'])
    subprocess.run(prefix + ['-r', 'requirements.txt'], cwd=ROOT, check=True)
    subprocess.run(prefix + ['-e', '.['+','.join(extras)+']', '-c', 'requirements.txt'], cwd=ROOT, check=True)
    subprocess.run([environment_python(), str(ROOT/'skill_bundle/runtime/doctor.py')], cwd=ROOT, check=True)
    print('Development environment ready. No host skills registered; no test suite executed.')


def run_web(arguments):
    web_env_path = ROOT/'tools/containers/web-console/.env'
    if web_env_path.is_file():
        for line in web_env_path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    sys.path.insert(0, str(ROOT/'skill_bundle/runtime'))
    from core.workspace import WORKSPACE_ROOT, get_log_path
    env = os.environ.copy()
    env.setdefault('A_STOCK_WORKSPACE_ROOT', str(WORKSPACE_ROOT))
    roots = [str(ROOT/'skill_bundle/runtime'), str(ROOT/'apps/web-console/backend'), str(ROOT)]
    env['PYTHONPATH'] = os.pathsep.join(roots + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
    command = [environment_python(), '-u', str(ROOT/'apps/web-console/backend/server/run.py'), *arguments]
    # --help must remain a read-only operation.
    if any(value in ('-h', '--help') for value in arguments):
        return subprocess.run(command, cwd=ROOT, env=env).returncode
    path = get_log_path('web-console')
    print(f'Web development log: {path}', flush=True)
    with path.open('a', encoding='utf-8') as log:
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        try:
            for line in child.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
            return child.wait()
        except KeyboardInterrupt:
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            return 130
        finally:
            child.stdout.close()


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('setup', 'run-web'):
        print('Usage: manage.py {setup|run-web} [options]', file=sys.stderr)
        return 2
    try:
        if sys.argv[1] == 'setup':
            setup(sys.argv[2:])
            return 0
        return run_web(sys.argv[2:])
    except subprocess.CalledProcessError as error:
        print(f'Development command failed with exit code {error.returncode}', file=sys.stderr)
        return error.returncode or 1


if __name__ == '__main__':
    raise SystemExit(main())

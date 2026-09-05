@echo off
setlocal
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    set PYTHON_EXEC="%PROJECT_ROOT%\.venv\Scripts\python.exe"
) else (
    set PYTHON_EXEC=py
)

set PYTHONPATH=%PROJECT_ROOT%\scripts;%PROJECT_ROOT%;%PYTHONPATH%
set A_STOCK_AGENTS_ROOT=%PROJECT_ROOT%

if exist "%PROJECT_ROOT%\scripts\core\cli.py" (
    set CLI_PATH="%PROJECT_ROOT%\scripts\core\cli.py"
) else (
    set CLI_PATH="%PROJECT_ROOT%\core\cli.py"
)

%PYTHON_EXEC% %CLI_PATH% %*

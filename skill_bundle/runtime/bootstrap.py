"""Import the unique runtime without assuming a project working directory."""
from pathlib import Path
import sys

RUNTIME_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = RUNTIME_ROOT.parent
if not (PACKAGE_ROOT / 'bundle.json').is_file():
    raise RuntimeError('A-Stock bundle marker missing')
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

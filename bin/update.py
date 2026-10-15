from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / "skill_bundle/runtime")]
from tools.legacy import update as _implementation
if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation

from bootstrap import RUNTIME_ROOT
import json
from core.workspace import check_workspace_health

if __name__ == '__main__':
    result = check_workspace_health()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['is_healthy'] else 1)

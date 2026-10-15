from pathlib import Path
import sys
ROOT=next(p for p in Path(__file__).resolve().parents if (p/"skill_bundle/bundle.json").exists())
sys.path.insert(0,str(ROOT))
from tools.packaging.common import package_project, main
if __name__=="__main__":main()

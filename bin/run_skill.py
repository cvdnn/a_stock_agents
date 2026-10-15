from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/"skill_bundle/runtime"))
runpy.run_path(str(root/"skill_bundle/runtime/run_skill.py"),run_name="__main__")

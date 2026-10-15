"""Schema-checked skill execution using the unique shared registry."""
from bootstrap import RUNTIME_ROOT
import argparse
import asyncio
import json
from core.governance.skill_registry import SkillRegistry
from core.workspace import check_workspace_health


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('skill',nargs='?')
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--params',default='{}')
    parser.add_argument('--confirm',action='store_true')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    if args.list:
        print(json.dumps(check_workspace_health(),ensure_ascii=False,indent=2))
        return 0
    if not args.skill:parser.error('skill required')
    try:
        params=json.loads(args.params)
        if not isinstance(params,dict):raise ValueError('params must be an object')
    except ValueError as exc:parser.error(str(exc))
    registry=SkillRegistry()
    result=asyncio.run(registry.execute_skill(args.skill,params,confirmed=args.confirm))
    print(json.dumps(result.model_dump(),ensure_ascii=False,default=str,indent=2))
    return 0 if result.status=='success' else 1


if __name__=='__main__':raise SystemExit(main())

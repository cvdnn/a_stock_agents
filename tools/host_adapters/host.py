"""Print exact reference targets; registration accepts only a received Release."""
import argparse
import json
from pathlib import Path
from references import register_reference


def main(platform):
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',required=True,type=Path)
    parser.add_argument('--entry',type=Path)
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    bundle=args.bundle.resolve()
    if not (bundle/'bundle.json').is_file():parser.error('bundle.json missing')
    marker=json.loads((bundle/'bundle.json').read_text(encoding='utf-8'))
    if marker.get('distribution')!='release':parser.error('Release required; development source cannot be registered')
    if args.entry:
        if platform=='workbuddy':
            result={'status':'unverified','reason_code':'HOST_REFERENCE_SUPPORT_UNVERIFIED','source':str(bundle/'skills'),'copy_fallback':False}
        else:result=register_reference(bundle/'skills',args.entry)
    else:
        result={'status':'configured_target','platform':platform,'source':str(bundle/'skills'),
                'mode':'external_dirs' if platform=='hermes' else 'reference-only',
                'host_scan_status':'unverified','copy_fallback':False}
    print(json.dumps(result,ensure_ascii=False,indent=2))

"""Archive one complete bundle directly from its authority; no staging mirror."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'skill_bundle/runtime'))
from core.workspace import PACKAGE_ROOT, OUTPUT_DIR, MANIFEST_PATH, get_log_path

ALLOWED_SUFFIXES={'.py','.md','.json','.yaml','.yml','.html','.css','.js','.txt','.example','.ps1','.cmd','.sh','.svg','.png','.jpg','.jpeg','.woff','.woff2'}


def package_project(output_path=None,version_tag='v3',platform='collection'):
    destination=Path(output_path) if output_path else ROOT/'output/packages'/f'a_stock_agents_{version_tag}_{platform}.zip'
    destination.parent.mkdir(parents=True,exist_ok=True)
    files=[]
    for path in sorted(PACKAGE_ROOT.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.is_symlink():continue
        if path.name.startswith('.env') or path.name=='config.yaml':continue
        if path.suffix not in ALLOWED_SUFFIXES and path.name not in {'astock','LICENSE'}:continue
        files.append(path)
    instructions={'platform':platform,'mode':'release-candidate-collection','skill_entries':20,'business_skills':19,
                  'runtime':'skill_bundle/runtime','skills':'skill_bundle/skills',
                  'host_scan_status':'unverified',
                  'native_import_verified':False, 'data_root':'OS user data/a_stock_agents or explicit A_STOCK_WORKSPACE_ROOT',
                  'notice':'Complete collection candidate. Native host import and skill discovery require separate acceptance. Do not register the development repository.'}
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            name=(Path('skill_bundle')/path.relative_to(PACKAGE_ROOT)).as_posix()
            info=zipfile.ZipInfo.from_file(path, name)
            info.create_system=3
            mode=0o100755 if path.name=='astock' or path.suffix=='.sh' else 0o100644
            info.external_attr=mode << 16
            info.compress_type=zipfile.ZIP_DEFLATED
            content=path.read_bytes()
            if path==PACKAGE_ROOT/'bundle.json':
                marker=json.loads(content)
                marker['distribution']='release'
                content=json.dumps(marker,ensure_ascii=False,indent=2).encode('utf-8')
            archive.writestr(info,content)
        # Derived installation metadata, never another business rule manifest.
        archive.writestr('INSTALL.json',json.dumps(instructions,ensure_ascii=False,indent=2))
        archive.write(ROOT/'requirements.txt','requirements.txt')
        archive.write(ROOT/'LICENSE','LICENSE')
        if platform in {'codex','hermes','workbuddy'}:
            for name in ('references.py','windows_junction.ps1','host.py',platform+'.py'):
                path=ROOT/'tools/host_adapters'/name
                if path.is_file():archive.write(path,Path('host_adapters')/name)
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.zip.sha256').write_text(digest+'  '+destination.name+'\n',encoding='utf-8')
    record={'archive':str(destination),'sha256':digest,'source_files':len(files),'platform':platform,
            'private_roots_included':False,'host_installation_verified':False}
    with get_log_path('packaging').open('a',encoding='utf-8') as stream:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
    return destination


def main(platform='collection'):
    parser=argparse.ArgumentParser()
    parser.add_argument('--output','-o',type=Path)
    parser.add_argument('--tag','-t',default='v3')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    path=package_project(args.output,args.tag,platform)
    print(json.dumps({'status':'success','archive':str(path),'host_installation_verified':False},ensure_ascii=False))


if __name__=='__main__':main()

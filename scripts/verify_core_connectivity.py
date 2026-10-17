#!/usr/bin/python3
"""Read-only physical core connectivity check, reconstructed from the prior audit.
Usage: /usr/bin/python3 verify_core_connectivity.py [REPO_ROOT] [OUTPUT_DIRECTORY]
The test copy retains the existing saved copper/fill without refilling or rerouting.
"""
from pathlib import Path
import argparse,collections,hashlib,json,os,shutil,subprocess
from core_sexpr import parse,dump,children,child,prop,CORE_REFS,GROUP
ap=argparse.ArgumentParser();ap.add_argument('root',nargs='?',default=str(Path(__file__).resolve().parent.parent));ap.add_argument('out',nargs='?');args=ap.parse_args()
ROOT=Path(args.root).resolve();OUT=Path(args.out).resolve() if args.out else ROOT/'validation/core_connectivity';OUT.mkdir(parents=True,exist_ok=True)
source=ROOT/'WING27.kicad_pcb';before=hashlib.sha256(source.read_bytes()).hexdigest();a=parse(source.read_text())
groups=[g for g in children(a,'group') if g[1]==GROUP];assert len(groups)==1,'Expected exactly one official core group'
ids=set(child(groups[0],'members')[1:]);copper=[x for x in a if isinstance(x,list) and x and x[0] in ['segment','via','zone'] and child(x,'uuid') and child(x,'uuid')[1] in ids]
counts=dict(collections.Counter(x[0] for x in copper));assert counts=={'segment':87,'via':27,'zone':10},counts
saved_fill_count=sum(len(children(z,'filled_polygon')) for z in children(a,'zone'));assert saved_fill_count>0,'No saved filled polygons; this audit does not generate missing copper'
retained=[];removed_ids=set()
for f in children(a,'footprint'):
    ref=prop(f,'Reference')[2]
    if ref in CORE_REFS:retained.append(ref)
    else:removed_ids.add(id(f))
assert sorted(retained)==sorted(CORE_REFS),(retained,CORE_REFS)
copy=[x for x in a if id(x) not in removed_ids]
assert [x for x in copy if isinstance(x,list) and x and x[0] in ['segment','via','zone']]==[x for x in a if isinstance(x,list) and x and x[0] in ['segment','via','zone']]
(OUT/'WING27.kicad_pcb').write_text(dump(copy))
project=ROOT/'WING27.kicad_pro';assert project.exists(),'Restore the project design rules before running the final audit'
shutil.copyfile(project,OUT/'WING27.kicad_pro')
libtable=ROOT/'fp-lib-table';assert libtable.exists(),'Restore fp-lib-table and local footprint library before final audit'
(OUT/'fp-lib-table').write_text(libtable.read_text().replace('${KIPRJMOD}',str(ROOT)))
env=os.environ.copy()
for key in ['XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME']:env[key]='/tmp/wing27_corecheck_'+key.lower()
run=subprocess.run(['kicad-cli','pcb','drc','--format','json','-o',str(OUT/'drc.json'),str(OUT/'WING27.kicad_pcb')],capture_output=True,text=True,env=env)
(OUT/'drc.log').write_text(run.stdout+run.stderr);assert run.returncode==0,'DRC tool failed; see drc.log'
drc=json.loads((OUT/'drc.json').read_text());unexpected=[v for v in drc['violations'] if v['type']!='invalid_outline']
assert hashlib.sha256(source.read_bytes()).hexdigest()==before,'Source PCB unexpectedly changed'
report={'source_pcb_sha256':before,'method':'KiCad DRC on core-only footprint copy retaining the exact saved filled copper; no refill or reroute. Every net shared by retained pads must be physically connected.','core_refs':sorted(retained),'core_copper_counts':counts,'saved_filled_polygons':saved_fill_count,'physical_unconnected_items':len(drc['unconnected_items']),'copper_or_unexpected_drc_violations':len(unexpected),'known_outline_violations':sum(v['type']=='invalid_outline' for v in drc['violations']),'source_unchanged':True,'pass':not drc['unconnected_items'] and not unexpected}
(OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
assert report['pass'],{'unconnected':drc['unconnected_items'],'unexpected_violations':unexpected}

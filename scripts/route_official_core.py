#!/usr/bin/python3
"""Preserve/reapply the recovered v5 official-core copper, with pad-based net mapping.
This replaces the lost geometry-generation script without rerouting the saved core.

Extract once from the recovered v5 board:
  /usr/bin/python3 route_official_core.py extract V5_PCB TEMPLATE_DIRECTORY
Restore after build_board.py, or to a copy for verification:
  /usr/bin/python3 route_official_core.py apply TARGET_PCB TEMPLATE_DIRECTORY [--output OUTPUT_PCB]

Only owned core copper/group is replaced. Footprints and other routing stay unchanged.
Saved fills are preserved exactly; run full DRC after other geometry changes.
"""
from pathlib import Path
import argparse,collections,copy,hashlib,json
from core_sexpr import parse,dump,children,child,prop,S,CORE_REFS,GROUP
ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['extract','apply']);ap.add_argument('pcb');ap.add_argument('template');ap.add_argument('--output');args=ap.parse_args()
PCB=Path(args.pcb).resolve();T=Path(args.template).resolve();a=parse(PCB.read_text());fps={prop(f,'Reference')[2]:f for f in children(a,'footprint')}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(v):return json.loads(json.dumps(v))
def sig(f):return canonical({'at':child(f,'at'),'layer':child(f,'layer'),'pads':[(p[1],child(p,'at'),child(p,'size'),child(p,'layers')) for p in children(f,'pad')]})
def padnet(f,p):return child(next(x for x in children(f,'pad') if x[1]==p),'net')[-1]
def get_copper(a):
    gs=[g for g in children(a,'group') if g[1]==GROUP];assert len(gs)==1,'Exactly one official core group required'
    ids=set(child(gs[0],'members')[1:]);items=[x for x in a if isinstance(x,list) and x and x[0] in ['segment','via','zone'] and child(x,'uuid') and child(x,'uuid')[1] in ids]
    assert len(items)==len(ids),'Group contains missing/non-copper members'
    counts=dict(collections.Counter(x[0] for x in items));assert counts=={'segment':87,'via':27,'zone':10},counts
    return gs[0],items
if args.mode=='extract':
    group,items=get_copper(a);T.mkdir(parents=True,exist_ok=True)
    netnames={str(n[1]):n[2] for n in children(a,'net')}
    used=sorted(set(str(child(x,'net')[1]) for x in items));anchors={}
    for code in used:
        name=netnames[code];anchor=next(( [ref,p[1]] for ref in CORE_REFS for p in children(fps[ref],'pad') if child(p,'net') and child(p,'net')[-1]==name),None)
        assert anchor,(name,'No core pad anchor');anchors[code]={'source_name':name,'ref':anchor[0],'pin':anchor[1]}
    guards={ref:sig(fps[ref]) for ref in CORE_REFS+['R22','R23','R7','R8']}
    (T/'core_copper.sexpr').write_text(dump([S('core_copper')]+copy.deepcopy(items)+[copy.deepcopy(group)]))
    report={'source_pcb_sha256':sha(PCB),'source_pcb':str(PCB),'group':GROUP,'counts':dict(collections.Counter(x[0] for x in items)),'pad_net_anchors':anchors,'guarded_footprints':guards,'scope':'Core power/clock and local ground, no rerouting. Existing v5 copper preserved exactly.'}
    (T/'core_template.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='guarded_footprints'},indent=2))
else:
    meta=json.loads((T/'core_template.json').read_text());data=parse((T/'core_copper.sexpr').read_text());template=copy.deepcopy(data[1:]);before_fps=canonical(children(a,'footprint'))
    for ref,s in meta['guarded_footprints'].items():assert ref in fps and sig(fps[ref])==s,(ref,'core geometry changed; needs revalidation')
    netcodes={n[2]:str(n[1]) for n in children(a,'net')};remap={}
    for old,anchor in meta['pad_net_anchors'].items():
        name=padnet(fps[anchor['ref']],anchor['pin']);assert name==anchor['source_name'],(anchor,'logical net changed');remap[old]=(netcodes[name],name)
    for item in template:
        if item[0]=='group':continue
        c=child(item,'net');new,name=remap[str(c[1])];c[1]=S(new)
        n=child(item,'net_name')
        if n:n[1]=name
    oldgroups=[g for g in children(a,'group') if g[1]==GROUP];oldids={u for g in oldgroups for u in child(g,'members')[1:]}
    result=[x for x in a if x not in oldgroups and not(isinstance(x,list) and child(x,'uuid') and child(x,'uuid')[1] in oldids)]
    existing={child(x,'uuid')[1] for x in result if isinstance(x,list) and child(x,'uuid')};incoming={child(x,'uuid')[1] for x in template};assert not existing&incoming,'Core UUID collision outside owned group'
    result.extend(template);assert canonical(children(result,'footprint'))==before_fps
    target=Path(args.output).resolve() if args.output else PCB
    target.write_text(dump(result));group,items=get_copper(parse(target.read_text()))
    print(json.dumps({'output':str(target),'sha256':sha(target),'counts':dict(collections.Counter(x[0] for x in items)),'footprints_unchanged':True,'net_mapping_from_pads':remap,'refilled_or_rerouted':False},indent=2))

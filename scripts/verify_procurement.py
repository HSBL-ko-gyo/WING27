from pathlib import Path
import sys,csv,json,collections,hashlib
r=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(r/'scripts'));from sexpr import *
def props(x):return {p[1]:p[2] for p in children(x,'property')}
sch={}
for p in r.glob('*.kicad_sch'):
 for x in children(parse(p.read_text()),'symbol'):
  d=props(x)
  if d.get('Reference','').startswith('#'):continue
  if 'Reference'in d:sch[d['Reference']]={'props':d,'file':p.name,'dnp':child(x,'dnp'),'in_bom':child(x,'in_bom')}
pcb={props(x)['Reference']:props(x) for x in children(parse((r/'WING27.kicad_pcb').read_text()),'footprint')}
rows=list(csv.DictReader((r/'WING27_BOM.csv').open(encoding='utf-8-sig')));bom={ref:row for row in rows for ref in row['References'].split(',')}
diffs=[]
for ref in pcb:
 if ref not in sch:diffs.append([ref,'no schematic']);continue
 for field in ['Value','manufacturer_pn','LCSC']:
  if pcb[ref].get(field,'')!=sch[ref]['props'].get(field,''):diffs.append([ref,field,'SCH-PCB'])
 if ref in bom:
  for field,bf in [('Value','Value'),('manufacturer_pn','MPN'),('LCSC','LCSC')]:
   if pcb[ref].get(field,'')!=bom[ref][bf]:diffs.append([ref,field,'PCB-BOM'])
counts=collections.Counter();missing=[]
for row in rows:
 count=int(row['Quantity']); a=row['Assembly'];counts[a]+=count;counts[a+'_assigned']+=count if row['LCSC'] else 0
 if not row['LCSC']:missing.append({k:row[k] for k in ['References','Quantity','Value','MPN','Assembly']})
out={'baseline_commit':'9d37752a5d09a2c02791a56489a6369f36636ab4','input_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [r/'WING27.kicad_pcb',r/'WING27_BOM.csv',*r.glob('*.kicad_sch')]},'schematic_components':len(sch),'pcb_footprints':len(pcb),'bom_rows':len(rows),'counts':counts,'mismatches':diffs,'missing':missing,'excluded':{prefix:sorted(ref for ref in pcb if ref.startswith(prefix)) for prefix in ['TP','H','JP']},'assigned_sku_count':len(set(row['LCSC'] for row in rows if row['LCSC']))}
(r/'validation/procurement_consistency.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))

assert not diffs, diffs
assert counts["PCBA"]==101 and counts["PCBA_assigned"]==101

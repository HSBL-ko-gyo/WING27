#!/usr/bin/env python3
"""Apply reviewed procurement fields without moving copper, symbols or footprints."""
from pathlib import Path
import json,re,uuid,csv,collections
ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'scripts/procurement_parts.json'
if not DATA.exists():raise SystemExit('Missing reviewed procurement_parts.json')
records=json.loads(DATA.read_text())['parts']
def spans(text):
 depth=0;start=None;quoted=False;escape=False
 for i,c in enumerate(text):
  if quoted:
   if escape:escape=False
   elif c=='\\':escape=True
   elif c=='"':quoted=False
   continue
  if c=='"':quoted=True
  elif c=='(':
   depth+=1
   if depth==2:start=i
  elif c==')':
   if depth==2:yield start,i+1,text[start:i+1]
   depth-=1

def q(s):return json.dumps(str(s),ensure_ascii=False)
def update_block(block,fields,pcb):
 for name,value in fields.items():
  pat=r'(\(property\s+'+re.escape(q(name))+r'\s+)("(?:\\.|[^"\\])*")'
  block,n=re.subn(pat,lambda m:m.group(1)+q(value),block,count=1)
  if not n:
   if pcb:tail=f'(at 0 0 0)(layer "F.Fab")(hide yes)(uuid "{uuid.uuid5(uuid.NAMESPACE_URL,block[:120]+name)}")(effects(font(size 1 1)(thickness 0.15)))'
   else:tail='(at 0 0 0)(effects(font(size 1 1))(hide yes))'
   block=block[:-1].rstrip()+'\n(property '+q(name)+' '+q(value)+tail+')\n)'
 return block
for p in [ROOT/'WING27.kicad_pcb',*ROOT.glob('*.kicad_sch')]:
 text=p.read_text();pcb=p.suffix=='.kicad_pcb';edits=[]
 for a,b,block in spans(text):
  if not re.match(r'\(' + ('footprint' if pcb else 'symbol') + r'\s',block):continue
  match=re.search(r'\(property\s+"Reference"\s+"([^"\\]+)"',block)
  if match and match.group(1) in records:
   fields=records[match.group(1)]['fields'];changed=update_block(block,fields,pcb)
   if changed!=block:edits.append((a,b,changed))
 for a,b,changed in reversed(edits):text=text[:a]+changed+text[b:]
 if edits:p.write_text(text)
modelpath=ROOT/'scripts/electrical_model.json';model=json.loads(modelpath.read_text())
for c in model['components']:
 if c['ref'] in records:
  for k,v in records[c['ref']]['fields'].items():
   if k=='Value':c['value']=v
   else:c['metadata'][k]=v
modelpath.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
groups=collections.defaultdict(list)
for c in model['components']:
 if c['ref'].startswith(('TP','H','JP')):continue
 md=c['metadata'];assembly='Hand solder' if c['ref'].startswith('SW') and int(c['ref'][2:])<=60 else md.get('Assembly','PCBA')
 key=(c['value'],md.get('manufacturer',''),md.get('manufacturer_pn',''),'WING27:'+c['fp'],md.get('LCSC',''),assembly,md.get('Datasheet',''))
 groups[key].append(c['ref'])
with (ROOT/'WING27_BOM.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f,lineterminator='\n');w.writerow(['References','Quantity','Value','Manufacturer','MPN','Footprint','LCSC','Assembly','Datasheet'])
 for key,refs in groups.items():w.writerow([','.join(refs),len(refs),*key])
print('Applied reviewed procurement metadata:',len(records),'references')

# The selected JSCJ part rating overrides the generic library description.
for p in [ROOT/"WING27.kicad_sym", *ROOT.glob("*.kicad_sch")]:
 text=p.read_text(); updated=text.replace("Dual 100V 215mA high-speed switching diodes, common cathode, SOT-23", "JSCJ BAV70: dual 70V 200mA switching diodes, common cathode, SOT-23")
 if updated!=text:p.write_text(updated)

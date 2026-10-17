#!/usr/bin/python3
"""Rebuild all PCB net assignments from the exported KiCad schematic netlist."""
from pathlib import Path
import json,uuid,sys
import pcbnew
from sexpr import parse,dump,children,child,S
ROOT=Path(__file__).resolve().parent.parent
m=json.loads((ROOT/'scripts/electrical_model.json').read_text())
a=parse((ROOT/'validation/WING27.net').read_text());netnodes={};netnames=[]
for n in children(child(a,'nets'),'net'):
 name=child(n,'name')[1];netnames.append(name)
 for q in children(n,'node'):netnodes[(child(q,'ref')[1],child(q,'pin')[1])]=name
old=parse((ROOT/'WING27.kicad_pcb').read_text());graphics=[x for x in old if isinstance(x,list) and str(x[0]).startswith('gr_')]
# Remove obsolete text but retain panel drawing as a non-fabrication reference.
for g in graphics:
 if g[0]=='gr_text' and ('KEY CENTRES' in g[1] or 'KEY CENTERS' in g[1]):g[1]='KEY CENTRES LOCKED / ELECTRICAL NETS COMPLETE / UNROUTED / outline & stackup provisional'
b=pcbnew.BOARD();b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
nets={}
for name in sorted(netnames):
 n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
for c in m['components']:
 f=pcbnew.FootprintLoad(str(ROOT/'WING27.pretty'),c['fp']);assert f,c['fp']
 b.Add(f);f.SetReference(c['ref']);f.SetValue(c['value']);f.SetFPID(pcbnew.LIB_ID('WING27',c['fp']))
 path=pcbnew.KIID_PATH();path.push_back(pcbnew.KIID(m['root_uuid']))
 if c['sheet']=='controller':path.push_back(pcbnew.KIID(m['controller_sheet_uuid']))
 path.push_back(pcbnew.KIID(c['uuid']));f.SetPath(path)
 f.SetSheetfile('Controller.kicad_sch' if c['sheet']=='controller' else 'WING27.kicad_sch');f.SetSheetname('Controller' if c['sheet']=='controller' else '')
 f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(c['pcb'][0]),pcbnew.FromMM(c['pcb'][1])));f.SetOrientationDegrees(c['pcb'][2])
 if c['ref']=='J2':f.SetAttributes(f.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM)
 f.SetLocked(c['ref'].startswith('SW') and int(c['ref'][2:])<=60)
 f.Reference().SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8),pcbnew.FromMM(0.8)));f.Reference().SetTextThickness(pcbnew.FromMM(0.1));f.Value().SetVisible(False)
 if not (c["ref"].startswith("SW") and int(c["ref"][2:])<=60):f.Reference().SetLayer(pcbnew.F_Fab)
 for k,v in c['metadata'].items():
  oldfield=f.GetFieldByName(k)
  if oldfield:oldfield.SetText(v)
  else:
   field=pcbnew.PCB_FIELD(f,f.GetNextFieldId(),k);field.SetText(v);field.SetVisible(False);field.SetPosition(f.GetPosition());f.AddField(field)
 for pad in f.Pads():
  pn=pad.GetNumber()
  if not pn:continue
  name=netnodes.get((c['ref'],pn));assert name,(c['ref'],pn)
  pad.SetNet(nets[name])
b.BuildConnectivity();pcbnew.SaveBoard(str(ROOT/'WING27.kicad_pcb'),b)
a=parse((ROOT/'WING27.kicad_pcb').read_text());a.extend(graphics);(ROOT/'WING27.kicad_pcb').write_text(dump(a))
print('PCB saved',len(m['components']),'footprints',len(nets),'nets, zero tracks')

# Board construction starts from a fresh object; persist explicit manufacturing baselines
# after SaveBoard so its default settings do not overwrite the project constraints.
pro=ROOT/'WING27.kicad_pro'; settings=json.loads(pro.read_text())
rules=settings['board']['design_settings']['rules']
rules['min_through_hole_diameter']=0.2
rules['min_hole_clearance']=0.2
settings['net_settings']['classes'][0]['clearance']=0.15
pro.write_text(json.dumps(settings,indent=2)+'\n')

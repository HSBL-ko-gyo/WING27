#!/usr/bin/python3
"""Rebuild all PCB net assignments from the exported KiCad schematic netlist."""
from pathlib import Path
import json,uuid,sys
import pcbnew
from sexpr import parse,dump,children,child,S
from import_panel_svg import import_panel_svg,GROUP_NAME,verify_imported_geometry,audit_sources
ROOT=Path(__file__).resolve().parent.parent
m=json.loads((ROOT/'scripts/electrical_model.json').read_text())
a=parse((ROOT/'validation/WING27.net').read_text());netnodes={};netnames=[]
for n in children(child(a,'nets'),'net'):
 name=child(n,'name')[1];netnames.append(name)
 for q in children(n,'node'):netnodes[(child(q,'ref')[1],child(q,'pin')[1])]=name
old=parse((ROOT/'WING27.kicad_pcb').read_text());graphics=[x for x in old if isinstance(x,list) and str(x[0]).startswith('gr_')]
source_members={u for g in children(old,'group') if g[1]==GROUP_NAME for u in (child(g,'members') or [])[1:]}
graphics=[g for g in graphics if not(g[0]=='gr_text' and g[1] in ['1','1 CLK','CLK','GND','DIO','J3 SWD DNP'])]
graphics=[g for g in graphics if not(child(g,'uuid') and child(g,'uuid')[1] in source_members)]
# Remove obsolete text but retain panel drawing as a non-fabrication reference.
for g in graphics:
 if g[0]=='gr_text' and ('KEY CENTRES' in g[1] or 'KEY CENTERS' in g[1]):g[1]='KEY CENTRES LOCKED / ELECTRICAL NETS COMPLETE / UNROUTED / outline & stackup provisional'
b=pcbnew.BOARD();b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
b.GetTitleBlock().SetCompany('ハシビロ工業')
b.GetTitleBlock().SetTitle('WING27 / 60-key keyboard / unrouted')
b.GetTitleBlock().SetRevision('electrical-3')
nets={}
for name in sorted(netnames):
 n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
for c in m['components']:
 f=pcbnew.FootprintLoad(str(ROOT/'WING27.pretty'),c['fp']);assert f,c['fp']
 b.Add(f);f.SetReference(c['ref']);f.SetValue(c['value']);f.SetFPID(pcbnew.LIB_ID('WING27',c['fp']))
 path=pcbnew.KIID_PATH();path.push_back(pcbnew.KIID(m['root_uuid']))
 if c['sheet']=='controller':path.push_back(pcbnew.KIID(m['controller_sheet_uuid']))
 if c['sheet']=='leds':path.push_back(pcbnew.KIID(m['led_sheet_uuid']))
 path.push_back(pcbnew.KIID(c['uuid']));f.SetPath(path)
 f.SetSheetfile({'controller':'Controller.kicad_sch','leds':'LEDs.kicad_sch'}.get(c['sheet'],'WING27.kicad_sch'));f.SetSheetname({'controller':'Controller','leds':'LED'}.get(c['sheet'],''))
 if c['ref'].startswith('JP'):
  f.Flip(f.GetPosition(),False);f.SetAttributes(f.GetAttributes()|pcbnew.FP_EXCLUDE_FROM_BOM|pcbnew.FP_EXCLUDE_FROM_POS_FILES)
 f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(c['pcb'][0]),pcbnew.FromMM(c['pcb'][1])));f.SetOrientationDegrees(c['pcb'][2])
 if c['ref']=='J3':f.SetAttributes(f.GetAttributes() | pcbnew.FP_DNP)
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
# Optional SWD header: readable signals and pin-1 identification, no fitted connector.
for text,x,y in [('1',110.4,37.8),('CLK',112,36.9),('GND',114.54,36.9),('DIO',117.08,36.9),('J3 SWD DNP',114.54,42.1)]:
 t=pcbnew.PCB_TEXT(b);t.SetText(text);t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y)));t.SetLayer(pcbnew.F_SilkS);t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(.8),pcbnew.FromMM(.8)));t.SetTextThickness(pcbnew.FromMM(.1));b.Add(t)
for f in b.GetFootprints():
 if f.GetReference()=='SW24':f.Reference().SetLayer(pcbnew.F_Fab)
 if f.GetReference().startswith('JP'):f.Reference().SetLayer(pcbnew.B_Fab)
b.BuildConnectivity();overlay_report=import_panel_svg(b);pcbnew.SaveBoard(str(ROOT/'WING27.kicad_pcb'),b)
# Keep provisional printed-case boss envelopes separate from the source SVG layer.
graphics=[g for g in graphics if child(g,'layer')!=['layer','User.2']]
for x,y in [(23,23),(225,23),(23,75),(225,75)]:
 graphics.append(parse(f'(gr_circle(center {x} {y})(end {x+2.5} {y})(stroke(width 0.1)(type default))(fill none)(layer "User.2")(uuid "{uuid.uuid5(uuid.NAMESPACE_URL,"WING27-boss-"+str((x,y)))}"))'))
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

# Verify imported SVG geometry after KiCad serialization.
reread=pcbnew.LoadBoard(str(ROOT/'WING27.kicad_pcb'));sources,_,_=audit_sources(reread)
overlay_report.update(verify_imported_geometry(reread,sources));overlay_report['saved_board_round_trip_verified']=True
(ROOT/'validation/panel_svg.json').write_text(json.dumps(overlay_report,ensure_ascii=False,indent=2)+'\n')

# Restore the user-authorized MCU core copper after rebuilding placements.
import subprocess,sys
subprocess.run([sys.executable,str(ROOT/"scripts/route_official_core.py"),"apply",str(ROOT/"WING27.kicad_pcb"),str(ROOT/"reference/CoreCopper")],check=True)

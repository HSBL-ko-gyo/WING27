#!/usr/bin/env python3
"""Verify frozen PCB placement, footprint geometry and source integrity; emit BOM/map."""
from pathlib import Path
import csv,json,hashlib,collections,math
from sexpr import parse,children,child,prop
R=Path(__file__).resolve().parent.parent
m=json.loads((R/'scripts/electrical_model.json').read_text());a=parse((R/'WING27.kicad_pcb').read_text());fps={prop(f,'Reference')[2]:f for f in children(a,'footprint')}
assert len(fps)==129
base=json.loads((R/'validation/geometry.json').read_text())
for fn,sha in base['source_files'].items():assert hashlib.sha256((R/'reference/P2'/fn).read_bytes()).hexdigest()==sha,fn
model=R/'WING27.3dshapes/Kailh_CMI627301D60.step';assert hashlib.sha256(model.read_bytes()).hexdigest()==base['switch']['model_sha256']
errors=[]
for k in m['key_mapping']:
 fp=fps[k['reference']];xy=child(fp,'at');e=math.dist((float(xy[1]),float(xy[2])),(20+k['x'],78-k['y']));errors.append(e)
 assert e<1e-6
 assert child(fp,'locked')==['locked','yes'] or 'locked' in fp,k['reference']
 ps={p[1]:p for p in children(fp,'pad')};assert set(ps)=={'1','2'}
 for pn,xx in [('1',-2.5),('2',2.5)]:
  p=ps[pn];assert list(map(float,child(p,'at')[1:3]))==[xx,0.0]
  assert float(child(p,'drill')[1])==1.1
  assert list(map(float,child(p,'size')[1:3]))==[1.8,1.8]
assert len(children(a,'segment'))==0 and len(children(a,'zone'))==0
assert not any(child(g,'layer')==['layer','Edge.Cuts'] for g in a if isinstance(g,list))
base.update(status='ELECTRICAL SCHEMATIC AND FOOTPRINT NETS VERIFIED; UNROUTED; NOT FOR FABRICATION',kicad_version='9.0.2',coordinate_max_error_mm=max(errors),footprint_count=len(fps),electrical_status='RP2354A / 60-key 5x12 / BAV70x30 / USB-C / 3.3V supply fully netlisted. ERC and schematic parity: zero. No copper tracks or zones.',pending_decisions=['User artwork/routing, final PCB outline/mounting/stackup/thickness and connector mechanical location','Firmware matrix mapping, USB HID/power configuration, hardware bring-up and inrush/USB compliance measurements','No LEDs fitted; extension signal is 3.3V only and needs appropriate level shifting for 5V LEDs'])
base['switch']['reuse']='Original user switch geometry and completed STEP retained; syntax normalized to KiCad9 and portable model path retained'
base['usb_footprint_adjustment']={'part':'USB4105-GF-A-060','source':'https://gct.co/files/drawings/usb4105.pdf','preserved':'All pad centers, 0.60 x 1.15mm outer GND pad envelopes, all NPTH/PTH centers and diameters','change':'Only A1/A12/B1/B12 outer pad corner radius: 0.15 to 0.24mm (roundrect ratio 0.25 to 0.40)','purpose':'>=0.20mm copper-to-NPTH clearance without moving pads or holes','drc_hole_clearance_errors':0}
base['reference_core_reuse']={'source':'https://pip.raspberrypi.com/categories/1214-rp2350','design':'RP2350A Minimal R4-S1 official KiCad','adaptation':'RP2354A internal flash; remove external flash; retain official MCU/SMPS/crystal footprints and relative placement. C10 updated to4.7uF per Release8 datasheet. Dedicated C20 on QSPI_IOVDD54. AP2112 3.3V and protected USB-C front end.','placement_transform':'x+24, y-51 mm from official core board; inductor orientation unchanged','license':'reference/RaspberryPi/LICENSE.txt'}
(R/'validation/geometry.json').write_text(json.dumps(base,ensure_ascii=False,indent=2)+'\n')
with (R/'WING27_key_matrix.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f,lineterminator="\n");w.writerow(['Key_ID','Reference','Row','Column','Row_GPIO','Column_GPIO','Diode','Anode_pin','X_mm','Y_mm'])
 for k in m['key_mapping']:w.writerow([k['key_id'],k['reference'],k['row'],k['column'],12+k['row'],k['column'],k['diode'],k['anode_pin'],k['x'],k['y']])
groups=collections.defaultdict(list)
for c in m['components']:
 if c['ref'].startswith('TP') or c['ref']=='J2':continue
 md=c['metadata'];assembly='Hand solder' if c['ref'].startswith('SW') and int(c['ref'][2:])<=60 else 'PCBA'
 key=(c['value'],md.get('manufacturer',''),md.get('manufacturer_pn',''),c['fp'],md.get('LCSC',''),assembly,md.get('Datasheet',''))
 groups[key].append(c['ref'])
with (R/'WING27_BOM.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f,lineterminator="\n");w.writerow(['References','Quantity','Value','Manufacturer','MPN','Footprint','LCSC','Assembly','Datasheet'])
 for key,refs in groups.items():
  value,mfr,mpn,fp,lcsc,assembly,ds=key;w.writerow([','.join(refs),len(refs),value,mfr,mpn,'WING27:'+fp,lcsc,assembly,ds])
print(json.dumps({'footprints':len(fps),'key_count':len(errors),'max_coordinate_error_mm':max(errors),'all_switches_locked':True,'source_hashes_unchanged':True,'populated_components':sum(len(x) for x in groups.values()),'bom_line_count':len(groups),'unrouted':True}))

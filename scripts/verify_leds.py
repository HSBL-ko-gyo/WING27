#!/usr/bin/python3
"""Audit the 16-LED prototype; mechanical emission direction remains provisional."""
from pathlib import Path
import json,pcbnew
R=Path(__file__).resolve().parent.parent
m=json.loads((R/'scripts/electrical_model.json').read_text());cs={c['ref']:c for c in m['components']};b=pcbnew.LoadBoard(str(R/'WING27.kicad_pcb'));fs={f.GetReference():f for f in b.GetFootprints()};records=[]
for i in range(16):
 ref=f'D{31+i}';f=fs[ref];x,y=pcbnew.ToMM(f.GetPosition().x),pcbnew.ToMM(f.GetPosition().y);angle=f.GetOrientationDegrees()%360
 assert y in [34,44,54,64] and x in [22.5,79.5,166.5,225.5]
 direction=1 if x in [22.5,166.5] else -1;assert angle==(90 if direction==1 else 270)
 pads={p.GetNumber():p for p in f.Pads()};assert set(pads)==set('1234')
 for num,xx,w in [('1',-1.675,.9),('2',-.425,.7),('3',.6,.45),('4',1.675,.9)]:
  p=pads[num];assert abs(pcbnew.ToMM(p.GetSize().x)-w)<1e-6 and abs(pcbnew.ToMM(p.GetSize().y)-1.3)<1e-6
  assert abs(pcbnew.ToMM(p.GetPosition().y)-(y-direction*xx))<1e-6 and abs(pcbnew.ToMM(p.GetPosition().x)-x)<1e-6
 assert pads['2'].GetNetname()=='VBUS' and pads['4'].GetNetname()=='GND'
 jp=fs[f'JP{i+1}'];assert jp.IsFlipped();pp=list(jp.Pads());assert pp[0].GetNetname()!=pp[1].GetNetname();assert jp.GetAttributes()&pcbnew.FP_EXCLUDE_FROM_BOM
 cap=cs[f'C{22+i}'];assert cap['value']=='100n' and cap['nets']=={'1':'VBUS','2':'GND'}
 records.append({'ref':ref,'source_top_left_mm':[x-20,y-20],'pcb_mm':[x,y],'rotation_deg':angle,'inferred_emission':'+X' if direction==1 else '-X','bypass':f'JP{i+1}','bypass_layer':'B.Cu','cap':f'C{22+i}'})
assert cs['R24']['value']=='100' and cs['R24']['nets']=={'1':'EXP_GPIO17_3V3','2':'LED_DATA_3V3'}
r={'status':'PASS electrical pin/rotation/placement audit; emission direction remains provisional','led_count':16,'per_led_decoupling':'100nF 50V X7R (C307331)','signal':'GPIO17 / 3.3V -> R24 100ohm -> D31 DIN, serial DOUT->DIN to D46','driver':'No buffer. V1.4 DIN max 1uA/15pF; verify waveform and supply extremes','full_white_typical_current_mA':576,'power_requirement':'USB current budget and firmware brightness limit require verification; unrestricted full white is not approved','land_source':'https://www.lcsc.com/product-image/C52941387.html','datasheet':'https://www.lcsc.com/datasheet/C52941387.pdf','land_status':'LCSC shared reference CAD, not manufacturer-approved land; nonuniform widths/pitches checked against V1.4','manufacturing_blockers':['Confirm actual C52941387 emitting face, mounted height, pad1 and land fit','Final PCB outline, stackup and mechanical clearances','DIN timing/margin, USB inrush and current budget tests'],'placement_adjustment':'Inner LEDs shifted 0.5mm toward centre for switch courtyard clearance; half-row optical y unchanged','bypass_usage':'Normally open backside bridges. Remove LED before shorting DIN/DOUT. No fitted parts. Firmware address count changes after bypass.','footprints':records}
(R/'validation/revision5_leds.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('PASS16 LEDs, caps, pin geometry, provisional emission rotations and OPEN bypass')

#!/usr/bin/env python3
"""Idempotently append the approved 16 side LEDs to an existing WING27 project.

Run after redraw_matrix.py and redraw_controller.py. Existing electrical nodes
and UUIDs are preserved. Existing LED PCB placements are retained on reruns.
This helper never edits a PCB or footprint. JP1..16 are open copper bridges,
excluded from the assembly BOM; close only after removing the associated LED.
"""
from pathlib import Path
import argparse
import copy
import json
import uuid
from sexpr import S, child, children, dump, parse, prop

NS = uuid.UUID('acbc3829-b305-481a-83cf-1dc11e052e65')
DATASHEET = 'https://www.lcsc.com/product-detail/C52941387.html'
DATASHEET_REVISION = 'V1.4 / 2026-07-28'
LED_FP = 'WS2812B_4020_V6_LCSC_Reference'
JP_FP = 'SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm'
TP_DESCRIPTION = 'GPIO17 3.3V LED data test point; R24 100ohm drives the first WS2812B-4020-V6 DIN directly.'


PCB_PLACEMENTS = {'C22': [76.5, 34.8, 0],
 'C23': [76.5, 44.8, 0],
 'C24': [76.5, 54.8, 0],
 'C25': [76.5, 64.8, 0],
 'C26': [25.5, 64.8, 0],
 'C27': [25.5, 54.8, 0],
 'C28': [25.5, 44.8, 0],
 'C29': [25.5, 34.8, 0],
 'C30': [169.5, 34.8, 0],
 'C31': [169.5, 44.8, 0],
 'C32': [169.5, 54.8, 0],
 'C33': [169.5, 64.8, 0],
 'C34': [222.5, 64.8, 0],
 'C35': [222.5, 54.8, 0],
 'C36': [222.5, 44.8, 0],
 'C37': [222.5, 34.8, 0],
 'D31': [79.5, 34.0, 270.0],
 'D32': [79.5, 44.0, 270.0],
 'D33': [79.5, 54.0, 270.0],
 'D34': [79.5, 64.0, 270.0],
 'D35': [22.5, 64.0, 90.0],
 'D36': [22.5, 54.0, 90.0],
 'D37': [22.5, 44.0, 90.0],
 'D38': [22.5, 34.0, 90.0],
 'D39': [166.5, 34.0, 90.0],
 'D40': [166.5, 44.0, 90.0],
 'D41': [166.5, 54.0, 90.0],
 'D42': [166.5, 64.0, 90.0],
 'D43': [225.5, 64.0, 270.0],
 'D44': [225.5, 54.0, 270.0],
 'D45': [225.5, 44.0, 270.0],
 'D46': [225.5, 34.0, 270.0],
 'JP1': [77.5, 34.0, 0],
 'JP10': [168.5, 44.0, 0],
 'JP11': [168.5, 54.0, 0],
 'JP12': [168.5, 64.0, 0],
 'JP13': [223.5, 64.0, 0],
 'JP14': [223.5, 54.0, 0],
 'JP15': [223.5, 44.0, 0],
 'JP16': [223.5, 34.0, 0],
 'JP2': [77.5, 44.0, 0],
 'JP3': [77.5, 54.0, 0],
 'JP4': [77.5, 64.0, 0],
 'JP5': [24.5, 64.0, 0],
 'JP6': [24.5, 54.0, 0],
 'JP7': [24.5, 44.0, 0],
 'JP8': [24.5, 34.0, 0],
 'JP9': [168.5, 34.0, 0],
 'R24': [135.0, 34.0, 0]}
LED_LIBRARY = '(symbol\n"WS2812B-4020-V6"\n\t(pin_names\n\t\t(offset 1.016))\n\t(exclude_from_sim no)\n\t(in_bom yes)\n\t(on_board yes)\n\t(property\n"Reference"\n"D"\n\t\t(at -13.97 8.89 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.016 1.016))))\n\t(property\n"Value"\n"WS2812B-4020-V6"\n\t\t(at 0 -24.13 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.016 1.016))))\n\t(property\n"Footprint"\n""\n\t\t(at 0 0 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.016 1.016))\n\t\t\t(hide yes)))\n\t(property\n"Datasheet"\n"https://www.lcsc.com/product-detail/C52941387.html"\n\t\t(at 0 0 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.016 1.016))\n\t\t\t(hide yes)))\n\t(property\n"Description"\n"Worldsemi side-view 4020 V6; 1 DIN, 2 VDD, 3 DOUT, 4 VSS"\n\t\t(at 0 0 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.016 1.016))\n\t\t\t(hide yes)))\n\t(symbol\n"WS2812B-4020-V6_0_1"\n\t\t(rectangle\n\t\t\t(start -7.62 6.35)\n\t\t\t(end 7.62 -6.35)\n\t\t\t(stroke\n\t\t\t\t(width 0)\n\t\t\t\t(type default))\n\t\t\t(fill\n\t\t\t\t(type background))))\n\t(symbol\n"WS2812B-4020-V6_1_1"\n\t\t(pin\ninput\nline\n\t\t\t(at -12.7 0 0)\n\t\t\t(length 5.08)\n\t\t\t(name\n"DIN"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.016 1.016))))\n\t\t\t(number\n"1"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.016 1.016)))))\n\t\t(pin\npower_in\nline\n\t\t\t(at 0 11.43 270)\n\t\t\t(length 5.08)\n\t\t\t(name\n"VDD"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.016 1.016))))\n\t\t\t(number\n"2"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.016 1.016)))))\n\t\t(pin\noutput\nline\n\t\t\t(at 12.7 0 180)\n\t\t\t(length 5.08)\n\t\t\t(name\n"DOUT"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.016 1.016))))\n\t\t\t(number\n"3"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.016 1.016)))))\n\t\t(pin\npower_in\nline\n\t\t\t(at 0 -11.43 90)\n\t\t\t(length 5.08)\n\t\t\t(name\n"VSS"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.016 1.016))))\n\t\t\t(number\n"4"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.016 1.016)))))))'
JP_LIBRARY = '(symbol\n"SolderJumper_2_Open"\n\t(pin_numbers\n\t\t(hide yes))\n\t(pin_names\n\t\t(offset 0)\n\t\t(hide yes))\n\t(exclude_from_sim no)\n\t(in_bom no)\n\t(on_board yes)\n\t(property\n"Reference"\n"JP"\n\t\t(at 0 2.032 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27))))\n\t(property\n"Value"\n"SolderJumper_2_Open"\n\t\t(at 0 -2.54 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27))))\n\t(property\n"Footprint"\n""\n\t\t(at 0 0 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27))\n\t\t\t(hide yes)))\n\t(property\n"Datasheet"\n"~"\n\t\t(at 0 0 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27))\n\t\t\t(hide yes)))\n\t(property\n"Description"\n"Solder Jumper, 2-pole, open"\n\t\t(at 0 0 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27))\n\t\t\t(hide yes)))\n\t(property\n"ki_keywords"\n"solder jumper SPST"\n\t\t(at 0 0 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27))\n\t\t\t(hide yes)))\n\t(property\n"ki_fp_filters"\n"SolderJumper*Open*"\n\t\t(at 0 0 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27))\n\t\t\t(hide yes)))\n\t(symbol\n"SolderJumper_2_Open_0_1"\n\t\t(polyline\n\t\t\t(pts\n\t\t\t\t(xy -0.254 1.016)\n\t\t\t\t(xy -0.254 -1.016))\n\t\t\t(stroke\n\t\t\t\t(width 0)\n\t\t\t\t(type default))\n\t\t\t(fill\n\t\t\t\t(type none)))\n\t\t(arc\n\t\t\t(start -0.254 -1.016)\n\t\t\t(mid -1.2656 0)\n\t\t\t(end -0.254 1.016)\n\t\t\t(stroke\n\t\t\t\t(width 0)\n\t\t\t\t(type default))\n\t\t\t(fill\n\t\t\t\t(type none)))\n\t\t(arc\n\t\t\t(start -0.254 -1.016)\n\t\t\t(mid -1.2656 0)\n\t\t\t(end -0.254 1.016)\n\t\t\t(stroke\n\t\t\t\t(width 0)\n\t\t\t\t(type default))\n\t\t\t(fill\n\t\t\t\t(type outline)))\n\t\t(arc\n\t\t\t(start 0.254 1.016)\n\t\t\t(mid 1.2656 0)\n\t\t\t(end 0.254 -1.016)\n\t\t\t(stroke\n\t\t\t\t(width 0)\n\t\t\t\t(type default))\n\t\t\t(fill\n\t\t\t\t(type none)))\n\t\t(arc\n\t\t\t(start 0.254 1.016)\n\t\t\t(mid 1.2656 0)\n\t\t\t(end 0.254 -1.016)\n\t\t\t(stroke\n\t\t\t\t(width 0)\n\t\t\t\t(type default))\n\t\t\t(fill\n\t\t\t\t(type outline)))\n\t\t(polyline\n\t\t\t(pts\n\t\t\t\t(xy 0.254 1.016)\n\t\t\t\t(xy 0.254 -1.016))\n\t\t\t(stroke\n\t\t\t\t(width 0)\n\t\t\t\t(type default))\n\t\t\t(fill\n\t\t\t\t(type none))))\n\t(symbol\n"SolderJumper_2_Open_1_1"\n\t\t(pin\npassive\nline\n\t\t\t(at -3.81 0 0)\n\t\t\t(length 2.54)\n\t\t\t(name\n"A"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27))))\n\t\t\t(number\n"1"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27)))))\n\t\t(pin\npassive\nline\n\t\t\t(at 3.81 0 180)\n\t\t\t(length 2.54)\n\t\t\t(name\n"B"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27))))\n\t\t\t(number\n"2"\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27))))))\n\t(embedded_fonts no))'


def uid(name):
    return str(uuid.uuid5(NS, name))


def node(s):
    return parse(s)


def led_library():
    lib = node(LED_LIBRARY)
    lib[1] = 'WING27:WS2812B-4020-V6'
    return lib


def build(source):
    source = source.resolve()
    model_path = source / 'scripts/electrical_model.json'
    model = json.loads(model_path.read_text())
    existing = {c['ref']: c for c in model['components']}
    controller = parse((source / 'Controller.kicad_sch').read_text())
    root = parse((source / 'WING27.kicad_sch').read_text())
    project_lib = parse((source / 'WING27.kicad_sym').read_text())
    cap_template, res_template = existing['C21'], existing['R22']
    root_uuid = model['root_uuid']
    sheet_uuid = model.get('led_sheet_uuid', uid('led-hierarchy-instance'))
    child_uuid = model.get('led_uuid', uid('led-hierarchy-root'))
    path = f'/{root_uuid}/{sheet_uuid}'
    libs = {s[1]: s for s in children(child(controller, 'lib_symbols'), 'symbol')}
    cap_lib, res_lib = copy.deepcopy(libs['WING27:C']), copy.deepcopy(libs['WING27:R'])
    jp_native = next((s for s in children(project_lib, 'symbol') if s[1] == 'SolderJumper_2_Open'), None)
    if jp_native is None:
        jp_native = node(JP_LIBRARY)
    jp_lib = copy.deepcopy(jp_native)
    jp_lib[1] = 'WING27:SolderJumper_2_Open'
    led_lib = led_library()
    sheet = node(f'''(kicad_sch(version 20250114)(generator "eeschema")(uuid "{child_uuid}")
      (paper "A3")(title_block(title "WING27 / サイドLED 16灯")(rev "side-led-1")
      (company "ハシビロ工業")(comment 1 "WS2812B-4020-V6 / V1.4 / 2026-07-28")))''')
    sheet.append([S('lib_symbols'), led_lib, cap_lib, res_lib, jp_lib])
    wires, comps, dots = [], [], set()

    def wire(*pts):
        for a, b in zip(pts, pts[1:]):
            a, b = tuple(round(v, 5) for v in a), tuple(round(v, 5) for v in b)
            assert a[0] == b[0] or a[1] == b[1], (a, b)
            if a != b:
                wires.append((a, b))

    def text(message, x, y, size=1.27):
        sheet.append(node(f'(text {json.dumps(message)}(at {x} {y} 0)(effects(font(size {size} {size}))(justify left))(uuid "{uid("text:"+message)}"))'))

    def label(net, p, global_=False, angle=0):
        global_ = global_ or net in ('VBUS','GND')
        tag = 'global_label' if global_ else 'label'
        shape = '(shape bidirectional)' if global_ else ''
        justify = 'left' if angle == 0 else 'right'
        sheet.append(node(f'({tag} {json.dumps(net)} {shape}(at {p[0]} {p[1]} {angle})(effects(font(size 1.016 1.016))(justify {justify} bottom))(uuid "{uid(tag+net+str(p))}"))'))

    def component(ref, lib, value, fp, nets, pos, pcb, metadata, mirror=False, angle=0, bom=True):
        prior = existing.get(ref)
        if prior:
            assert prior.get('sheet') == 'leds', f'Reference conflict: {ref}'
            pcb = prior['pcb']
            metadata = {**prior.get('metadata', {}), **metadata}
        else:
            pcb = PCB_PLACEMENTS.get(ref, pcb)
        if ref.startswith('D'):
            order = ['manufacturer','manufacturer_pn','LCSC','Datasheet','Datasheet_revision','Description',
                     'LED_Group','LED_Chain_Index','ReferenceLand','Emission']
            metadata = {**{k:metadata[k] for k in order if k in metadata},
                        **{k:v for k,v in metadata.items() if k not in order}}
        c = dict(ref=ref, lib=lib, value=value, fp=fp, nets=nets, pos=list(pos), pcb=list(pcb),
                 metadata=metadata, sheet='leds', uuid=prior['uuid'] if prior else uid(ref))
        if not bom:
            c['in_bom'] = False
            c['dnp'] = False
        comps.append(c)
        x, y = pos
        sn = node(f'(symbol(lib_id "WING27:{lib}")(at {x} {y} {angle})(unit 1)(exclude_from_sim no)(in_bom {"yes" if bom else "no"})(on_board yes)(dnp no)(uuid "{c["uuid"]}"))')
        if mirror:
            sn.append([S('mirror'), S('y')])
        fields = {'Reference': ref, 'Value': value, 'Footprint': 'WING27:'+fp, **metadata}
        for key, val in fields.items():
            if ref.startswith('D'):
                xx, yy = (x-13.97, y-8.89) if key == 'Reference' else (x, y+24.13) if key == 'Value' else (x,y)
                if mirror:
                    xx = 2*x-xx
            elif ref.startswith('JP'):
                xx, yy = (x, y-3.81) if key == 'Reference' else (x, y+3.81) if key == 'Value' else (x,y)
            elif ref.startswith('R'):
                xx, yy = (x, y-5.08) if key == 'Reference' else (x, y-2.54) if key == 'Value' else (x,y)
            else:
                xx, yy = (x+7.62, y-1.27) if key == 'Reference' else (x+7.62, y+1.27) if key == 'Value' else (x,y)
            visible = key == 'Reference' or (key == 'Value' and not ref.startswith('D'))
            hide = '' if visible else '(hide yes)'
            sn.append(node(f'(property {json.dumps(key)} {json.dumps(str(val))}(at {xx} {yy} {angle % 180})(effects(font(size 1.016 1.016)){hide}))'))
        for pin in nets:
            sn.append(node(f'(pin "{pin}"(uuid "{uid(ref+":"+pin)}"))'))
        sn.append(node(f'(instances(project "WING27"(path "{path}"(reference "{ref}")(unit 1))))'))
        sheet.append(sn)
        return c

    groups = [('左側・内向き 4灯', 'left_inner', 59, -1),
              ('左側・外向き 4灯', 'left_outer', 2.5, 1),
              ('右側・内向き 4灯', 'right_inner', 147, 1),
              ('右側・外向き 4灯', 'right_outer', 205.5, -1)]
    chain = []
    for row, (caption, group, pcb_x, key_direction) in enumerate(groups):
        y = round(63.5 + row * 52.07, 5)
        top = round(y-20.32, 5)
        xs = [76.2, 152.4, 228.6, 304.8]
        ordered = xs if row % 2 == 0 else list(reversed(xs))
        mirror = row % 2 == 1
        text(caption, 15.24, y-26.67, 1.524)
        wire((55.88, top), (327.66, top))
        label('VBUS', (55.88, top), global_=row == 0)
        for col, x in enumerate(ordered):
            i = row*4+col
            ref, cap, jp = f'D{31+i}', f'C{22+i}', f'JP{1+i}'
            physical_y = ([14,24,34,44] if row % 2 == 0 else [44,34,24,14])[col]
            in_net = 'LED_DATA_3V3' if i == 0 else f'LED_CHAIN_{i:02d}'
            out_net = 'LED_CHAIN_16_END' if i == 15 else f'LED_CHAIN_{i+1:02d}'
            component(ref, 'WS2812B-4020-V6', 'WS2812B-4020-V6', LED_FP,
                      {'1':in_net,'2':'VBUS','3':out_net,'4':'GND'}, (x,y), (pcb_x+20,physical_y+20,0),
                      {'manufacturer':'Worldsemi','manufacturer_pn':'WS2812B-4020-V6','LCSC':'C52941387',
                       'Datasheet':DATASHEET,'Datasheet_revision':DATASHEET_REVISION,
                       'Description':'Side-emitting addressable RGB LED; DIN1 / VDD2 / DOUT3 / VSS4',
                       'ReferenceLand':'LCSC C52941387 shared reference CAD; pad widths/positions checked against Worldsemi V1.4, not manufacturer-approved land.',
                       'Emission':'Provisional +localY emission inferred from U-outline; verify actual part orientation and mounted height before fabrication.',
                       'LED_Group':group,'LED_Chain_Index':str(i+1)}, mirror=mirror)
            cx, cy = round(x+22.86,5), round(y-16.51,5)
            metadata = copy.deepcopy(cap_template['metadata'])
            metadata['Description'] += f'; local bypass for {ref}'
            component(cap,'C','100n',cap_template['fp'],{'1':'VBUS','2':'GND'},(cx,cy),
                      (pcb_x+20+3*key_direction, physical_y+20.8,0),metadata)
            jy = round(y+25.4,5)
            component(jp,'SolderJumper_2_Open','OPEN',JP_FP,{'1':in_net,'2':out_net},(x,jy),
                      (pcb_x+20-5*key_direction,physical_y+20,0),
                      {'Description':f'Normally OPEN copper bypass for {ref}; remove LED before bridging DIN to DOUT',
                       'Assembly':'PCB copper only; no fitted part','Bypass_For':ref,'BoardSide':'B.Cu'},mirror=mirror,bom=False)
            wire((x,y-11.43),(x,top)); dots.add((x,top))
            wire((x,y+11.43),(x,y+15.24)); label('GND',(x,y+15.24),global_=i==0)
            wire((cx,cy-3.81),(cx,top)); dots.add((cx,top))
            wire((cx,cy+3.81),(cx,y-10.16)); label('GND',(cx,y-10.16))
            sign = -1 if mirror else 1
            din = (round(x-12.7*sign,5), y)
            dout = (round(x+12.7*sign,5), y)
            wire(din,(x-17.78*sign,y),(x-17.78*sign,jy),(x-3.81*sign,jy))
            wire(dout,(x+17.78*sign,y),(x+17.78*sign,jy),(x+3.81*sign,jy))
            chain.append({'ref':ref,'din':din,'dout':dout,'in_net':in_net,'out_net':out_net,'label_angle':180 if mirror else 0})

    metadata = copy.deepcopy(res_template['metadata'])
    metadata['Description'] = '100ohm 1% series damping for GPIO17 to first side-LED DIN; place near MCU'
    component('R24','R','100',res_template['fp'],{'1':'EXP_GPIO17_3V3','2':'LED_DATA_3V3'},
              (40.64,63.5),(135,34,0),metadata,angle=90)
    label('EXP_GPIO17_3V3',(15.24,52.07),global_=True)
    wire((15.24,52.07),(15.24,63.5),(36.83,63.5))
    wire((44.45,63.5),chain[0]['din'])
    wire((48.26,63.5),(48.26,69.85)); label('LED_DATA_3V3',(48.26,69.85),angle=180)
    for a,b in zip(chain,chain[1:]):
        p,q = a['dout'],b['din']
        if p[1] == q[1]:
            wire(p,q)
        else:
            xx = 365.76 if p[0] > 200 else 12.7
            wire(p,(xx,p[1]),(xx,q[1]),q)
        label(a['out_net'],p,angle=a['label_angle'])
    label(chain[-1]['out_net'],chain[-1]['dout'],angle=chain[-1]['label_angle'])

    points = {p for w in wires for p in w} | dots
    segments = set()
    for a,b in wires:
        pp = sorted(p for p in points if
            (a[0]==b[0]==p[0] and min(a[1],b[1])<=p[1]<=max(a[1],b[1])) or
            (a[1]==b[1]==p[1] and min(a[0],b[0])<=p[0]<=max(a[0],b[0])))
        segments.update(zip(pp,pp[1:]))
    for a,b in sorted(segments):
        sheet.append(node(f'(wire(pts(xy {a[0]} {a[1]})(xy {b[0]} {b[1]}))(stroke(width 0)(type default))(uuid "{uid("wire"+str((a,b)))}"))'))
    for p in sorted(points):
        if sum(p in w for w in segments) >= 3:
            sheet.append(node(f'(junction(at {p[0]} {p[1]})(diameter 0)(color 0 0 0 0)(uuid "{uid("junction"+str(p))}"))'))
    text('WING27 / サイドLED 16灯',15.24,13.97,2.286)
    text('WS2812B-4020-V6：GPIO17 → R24 100Ω → DIN(1)。VDD(2)=VBUS、DOUT(3)、VSS(4)=GND。',15.24,21.59)
    text('各灯100nF / DIN・DOUTは実配線で連鎖。JP1〜16は通常OPEN、部品実装不要。',15.24,28.575)
    text('順序：左内4 → 左外4 → 右内4 → 右外4。図の左右は信号順を示す。基板の光向きは実装図で確認。',15.24,267.97,1.016)
    text('途中のLEDを外す場合のみ、対応JPを短絡してDIN→DOUTをバイパスする。LED実装中は短絡しない。',15.24,274.32,1.016)
    sheet.append(node('(embedded_fonts no)'))

    for net in ('VBUS','GND','EXP_GPIO17_3V3'):
        labels = [s for s in children(controller,'label') if s[1] == net]
        globals_ = [s for s in children(controller,'global_label') if s[1] == net]
        assert labels or globals_, f'Missing Controller net {net}'
        for chosen in labels:
            chosen[0] = S('global_label')
            chosen.insert(2,node('(shape bidirectional)'))
    for ref, description in [('TP1','VBUS power test pad; shared 5V USB rail for the side LEDs'),
                             ('TP3','GND reference test pad')]:
        existing[ref]['metadata']['Description'] = description
        testpoint = next(s for s in children(controller,'symbol') if prop(s,'Reference')[2] == ref)
        prop(testpoint,'Description')[2] = description
    tp = next(s for s in children(controller,'symbol') if prop(s,'Reference')[2] == 'TP2')
    prop(tp,'Description')[2] = TP_DESCRIPTION
    existing['TP2']['metadata']['Description'] = TP_DESCRIPTION
    for t in children(controller,'text'):
        if ('TP2' in t[1] and '5 V' in t[1]) or 'Expansion pads only:' in t[1]:
            t[1] = 'TP2：GPIO17の3.3 Vデータ。R24（100Ω）経由でサイドLEDを駆動。'

    if not any(prop(s,'Sheetfile')[2] == 'LEDs.kicad_sch' for s in children(root,'sheet')):
        root.append(node(f'''(sheet(at 110 350)(size 90 20)(fields_autoplaced yes)
            (stroke(width 0)(type default))(fill(color 0 0 0 0))(uuid "{sheet_uuid}")
            (property "Sheetname" "Side LEDs"(at 110 348 0)(effects(font(size 1.27 1.27))(justify left bottom)))
            (property "Sheetfile" "LEDs.kicad_sch"(at 110 372 0)(effects(font(size 1.27 1.27))(justify left top)))
            (instances(project "WING27"(path "/{root_uuid}"(page "3")))))'''))
    for lib in (led_lib,jp_lib):
        native = copy.deepcopy(lib); native[1] = native[1].split(':',1)[1]
        old = next((s for s in children(project_lib,'symbol') if s[1] == native[1]),None)
        if old is not None:
            project_lib.remove(old)
        project_lib.append(native)
    model['components'] = [c for c in model['components'] if c.get('sheet') != 'leds'] + comps
    model.update(led_sheet_uuid=sheet_uuid,led_uuid=child_uuid)
    (source/'LEDs.kicad_sch').write_text(dump(sheet)+'\n')
    (source/'Controller.kicad_sch').write_text(dump(controller)+'\n')
    (source/'WING27.kicad_sch').write_text(dump(root)+'\n')
    (source/'WING27.kicad_sym').write_text(dump(project_lib)+'\n')
    model_path.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'leds':16,'capacitors':16,'open_copper_jumpers':16,'series_resistors':1,
                      'new_symbols':len(comps),'total_components':len(model['components']),
                      'led_sheet_uuid':sheet_uuid,'pcb_modified':False},ensure_ascii=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    build(args.source)

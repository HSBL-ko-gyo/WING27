#!/usr/bin/env python3
"""Replace Controller pin-stub artwork with a wired, reference-derived drawing.

Run after build_electrical.py.  The generated component instances, UUIDs, values,
library definitions and model connectivity remain authoritative.  Raspberry Pi's
R4-S1 component placement and actual wire segments are reused for the MCU/SMPS,
decoupling, crystal and switches, with pin-end adapters for the project symbols.
The USB-C/ESD/XC6206 circuit is drawn separately without changing its net model.

    python scripts/redraw_controller.py
    python scripts/redraw_controller.py --output /tmp/Controller.kicad_sch

Only this schematic is written; PCB placement and the electrical model are not.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import uuid

from sexpr import S, child, children, dump, parse, prop

ROOT = Path(__file__).resolve().parent.parent
NS = uuid.UUID('efc40cb2-bc7b-45cd-8481-81986b2e42db')


def number(value):
    return S(f'{float(value):.5f}'.rstrip('0').rstrip('.') or '0')


def point(x, y):
    return (round(float(x), 5), round(float(y), 5))


def uid(name):
    return str(uuid.uuid5(NS, name))


def pin_locations(symbol, library):
    """Return KiCad pin connection points, including post-rotation mirrors."""
    at = child(symbol, 'at')
    x, y, angle = map(float, at[1:4])
    mirror = child(symbol, 'mirror')
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    result = {}
    for unit in children(library, 'symbol'):
        for pin in children(unit, 'pin'):
            pa = child(pin, 'at')
            px, py = float(pa[1]), float(pa[2])
            dx, dy = ca * px - sa * py, sa * px + ca * py
            if mirror and mirror[1] == 'x':
                dy = -dy
            if mirror and mirror[1] == 'y':
                dx = -dx
            result[str(child(pin, 'number')[1])] = point(x + dx, y - dy)
    return result


class Drawing:
    def __init__(self, source, model, reference):
        self.sheet = copy.deepcopy(source)
        self.model = {c['ref']: c for c in model['components'] if c['sheet'] == 'controller'}
        self.symbols = {prop(s, 'Reference')[2]: copy.deepcopy(s)
                        for s in children(source, 'symbol')}
        self.library = {s[1]: s for s in children(child(source, 'lib_symbols'), 'symbol')}
        self.reference = reference
        self.refsyms = {prop(s, 'Reference')[2]: s for s in children(reference, 'symbol')}
        self.reflibs = {s[1]: s for s in children(child(reference, 'lib_symbols'), 'symbol')}
        remove = {'symbol', 'wire', 'label', 'global_label', 'junction', 'no_connect', 'text', 'polyline'}
        self.sheet[:] = [e for e in self.sheet if not isinstance(e, list) or e[0] not in remove]
        child(self.sheet, 'paper')[1] = 'A3'
        self.elements = []
        self.placed = set()
        self.wires = set()
        self.junctions = set()
        self.labels = set()
        self.imported_segments = 0
        self.anchors = {}

    def place(self, ref, x, y, angle=0, mirror=None, text=None):
        symbol = self.symbols[ref]
        symbol[:] = [e for e in symbol if not isinstance(e, list) or e[0] != 'mirror']
        child(symbol, 'at')[1:] = [number(x), number(y), number(angle)]
        if mirror:
            symbol.append([S('mirror'), S(mirror)])
        for p in children(symbol, 'property'):
            if p[1] == 'Reference':
                px, py = (x + 4, y - 2) if text is None else text[0]
            elif p[1] == 'Value':
                px, py = (x + 4, y + 1) if text is None else text[1]
            else:
                px, py = x, y
            if mirror == 'y':
                px = 2 * x - px
            if mirror == 'x':
                py = 2 * y - py
            child(p, 'at')[1:] = [number(px), number(py), number(angle % 180)]
            effects = child(p, 'effects')
            effects[:] = [e for e in effects if not isinstance(e, list) or e[0] != 'justify']
            if p[1] in ('Reference', 'Value'):
                child(child(effects, 'font'), 'size')[1:] = [S('1.016'), S('1.016')]
        self.placed.add(ref)
        return symbol

    def pins(self, ref):
        symbol = self.symbols[ref]
        return pin_locations(symbol, self.library[child(symbol, 'lib_id')[1]])

    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            a, b = point(*a), point(*b)
            if a == b:
                continue
            if a[0] != b[0] and a[1] != b[1]:
                raise ValueError(f'Non-orthogonal wire: {a} -> {b}')
            key = tuple(sorted((a, b)))
            if key in self.wires:
                continue
            self.wires.add(key)
            self.elements.append(parse(f'(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]}))'
                                       f' (stroke (width 0) (type default)) (uuid "{uid("wire"+str(key))}"))'))

    def label(self, net, xy, angle=0, global_=False):
        xy = point(*xy)
        key = (net, xy, angle)
        if key in self.labels:
            return
        self.labels.add(key)
        tag = 'global_label' if global_ else 'label'
        shape = '(shape bidirectional)' if global_ else ''
        justify = 'left' if angle in (0, 90) else 'right'
        self.elements.append(parse(f'({tag} {json.dumps(net)} {shape} (at {xy[0]} {xy[1]} {angle})'
                                   f' (effects (font (size 1.016 1.016)) (justify {justify} bottom))'
                                   f' (uuid "{uid("label"+str(key))}"))'))

    def junction(self, xy):
        xy = point(*xy)
        if xy not in self.junctions:
            self.junctions.add(xy)
            self.elements.append(parse(f'(junction (at {xy[0]} {xy[1]}) (diameter 0) (color 0 0 0 0)'
                                       f' (uuid "{uid("junction"+str(xy))}"))'))

    def text(self, message, x, y, size=1.27):
        self.elements.append(parse(f'(text {json.dumps(message)} (at {x} {y} 0)'
                                   f' (effects (font (size {size} {size})) (justify left))'
                                   f' (uuid "{uid("text"+message)}"))'))

    def rail(self, ref, pin, net, length=3.81):
        p = self.pins(ref)[str(pin)]
        q = point(p[0], p[1] + (length if net == 'GND' else -length))
        self.wire(p, q)
        self.label(net, q)
        return q

    def import_block(self, name, bounds, refs, delta=(0, 0), skip_nets=()):
        """Reuse actual official wire polylines, adapting only component pin ends."""
        x0, y0, x1, y1 = bounds
        inside = lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1
        shifted = lambda p: point(round((p[0] + delta[0]) / 1.27) * 1.27, round((p[1] + delta[1]) / 1.27) * 1.27)
        adapters = {}
        banned_points = set()
        for old_ref, new_ref in refs.items():
            old = self.refsyms[old_ref]
            oa = child(old, 'at')
            mirror = child(old, 'mirror')
            self.place(new_ref, float(oa[1]) + delta[0], float(oa[2]) + delta[1],
                       float(oa[3]), mirror[1] if mirror else None)
            oldpins = pin_locations(old, self.reflibs[child(old, 'lib_id')[1]])
            newpins = self.pins(new_ref)
            for pin, p in oldpins.items():
                if pin in newpins:
                    adapters[p] = newpins[pin]
                    if self.model[new_ref]['nets'].get(pin) is None:
                        banned_points.add(p)

        wires = []
        graph = {}
        for w in children(self.reference, 'wire'):
            a, b = [point(*p[1:3]) for p in children(child(w, 'pts'), 'xy')]
            if inside(a) and inside(b):
                wires.append((a, b))
                graph.setdefault(a, set()).add(b)
                graph.setdefault(b, set()).add(a)
        for label in children(self.reference, 'label'):
            p = point(*child(label, 'at')[1:3])
            if inside(p) and label[1] in skip_nets:
                banned_points.add(p)
        pending = list(banned_points)
        while pending:
            a = pending.pop()
            for b in graph.get(a, ()):
                if b not in banned_points:
                    banned_points.add(b)
                    pending.append(b)
        convert = lambda p: adapters.get(p, shifted(p))
        for a, b in wires:
            if a in banned_points or b in banned_points:
                continue
            self.wire(convert(a), convert(b))
            self.imported_segments += 1
        for j in children(self.reference, 'junction'):
            p = point(*child(j, 'at')[1:3])
            if inside(p) and p not in banned_points:
                self.junction(convert(p))
        for old in children(self.reference, 'symbol'):
            ref = prop(old, 'Reference')[2]
            p = point(*child(old, 'at')[1:3])
            if ref.startswith('#PWR') and inside(p):
                self.label(prop(old, 'Value')[2], shifted(p))
        for label in children(self.reference, 'label'):
            p = point(*child(label, 'at')[1:3])
            if not inside(p) or p in banned_points:
                continue
            net = str(label[1])
            self.anchors[(name, net)] = shifted(p)
            if net.startswith('GPIO') and net[4:].split('_')[0].isdigit():
                n = int(net[4:].split('_')[0])
                mapped = {17: 'EXP_GPIO17_3V3', 19: 'COL0', 20: 'COL1', 21: 'COL2', 22: 'COL3', 23: 'COL4', 24: 'COL5', 6: 'COL6', 7: 'COL7', 8: 'COL8', 9: 'COL9', 10: 'COL10', 11: 'COL11', 25: 'ROW_L0', 26: 'ROW_L1', 27: 'ROW_L2', 28: 'ROW_L3', 29: 'ROW_L4', 0: 'ROW_R0', 1: 'ROW_R1', 2: 'ROW_R2', 3: 'ROW_R3', 4: 'ROW_R4'}.get(n)
                if mapped and n != 17:
                    self.label(mapped, shifted(p), int(child(label, 'at')[3]), True)
            elif net in ('VREG_LX', 'VREG_AVDD'):
                self.label(net, shifted(p), int(child(label, 'at')[3]))

    def finish(self):
        missing = set(self.model) - self.placed
        if missing:
            raise ValueError(f'Components not placed: {sorted(missing)}')
        for ref, component in self.model.items():
            for pin, net in component['nets'].items():
                if net is None:
                    p = self.pins(ref)[pin]
                    self.elements.append(parse(f'(no_connect (at {p[0]} {p[1]})'
                                               f' (uuid "{uid(ref+":"+pin+":NC")}"))'))
        # KiCad expects explicit segment ends at every T junction.
        split_points = {p for w in self.wires for p in w} | self.junctions
        segments = sorted(self.wires)
        self.wires.clear()
        self.elements[:] = [e for e in self.elements if e[0] != 'wire']
        for a, b in segments:
            pts = [p for p in split_points if
                   (a[0] == b[0] == p[0] and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])) or
                   (a[1] == b[1] == p[1] and min(a[0], b[0]) <= p[0] <= max(a[0], b[0]))]
            self.wire(*sorted(pts))
        # Crossings without an endpoint or junction remain electrically separate.
        for a, b in sorted(self.wires):
            for p in (a, b):
                degree = sum(p in w for w in self.wires)
                if degree >= 3:
                    self.junction(p)
        self.sheet.extend(self.symbols[r] for r in sorted(self.placed))
        self.sheet.extend(self.elements)
        return self.sheet


def redraw(source, model, reference):
    d = Drawing(source, model, reference)
    d.import_block('core', (150, 60, 292, 210),
                   {r: r for r in ('U1', 'L1', 'C6', 'C7', 'R3', 'C9', 'R7', 'R8')})
    d.import_block('dvdd', (200, 25, 240, 49), {r: r for r in ('C8', 'C10', 'C11')})
    d.import_block('iovdd', (272, 25, 358, 49), {f'C{i}': f'C{i}' for i in range(12, 19)})
    d.import_block('crystal', (93, 205, 150, 230),
                   {r: r for r in ('X1', 'R2', 'C3', 'C4')}, (50.8, 20.32))
    # True two-terminal switches; preserve the official series resistors and real wire paths.
    d.place('SW61',130.81,113.03,90)
    d.place('R6',130.81,87.63)
    d.wire(d.pins('SW61')['2'],d.pins('R6')['2'])
    d.rail('SW61','1','GND')
    d.place('SW62',264.16,215.9,180)
    d.place('R4',279.4,215.9,90)
    d.wire(d.pins('SW62')['1'],d.pins('R4')['1'])
    d.rail('R4','2','GND')
    d.anchors[('reset','RUN')]=d.pins('SW62')['2']


    # Complete the signal paths that were label jumps in the reference.
    qspi = d.anchors[('core', 'QSPI_SS')]
    r6 = d.pins('R6')['1']
    d.wire(qspi, (qspi[0], 80.01), (r6[0], 80.01), r6)
    d.label('QSPI_SS', (r6[0] + 5.08, 80.01))
    for net in ('XIN', 'XOUT'):
        a, b = d.anchors[('core', net)], d.anchors[('crystal', net)]
        d.wire(a, (a[0], b[1]), b)
        d.label(net, b)
    a, b = d.anchors[('core', 'RUN')], d.anchors[('reset', 'RUN')]
    d.wire(a, (a[0], b[1]), b)
    d.label('RUN', b)
    d.label('BOOT_SWITCH', (130.81, 97.79))
    d.label('RUN_SWITCH', (271.78, 215.9), 90)
    d.label('XTAL_OUT', (170.18, 245.11))

    # Pico H-compatible 3-pin debug connector; pin numbers follow the model.
    d.place('J2', 248.92, 238.76, text=((242.57, 229.87), (242.57, 232.41)))
    for pin, net in d.model['J2']['nets'].items():
        p = d.pins('J2')[pin]
        if net == 'GND':
            d.wire(p, (238.76, p[1]), (238.76, 248.92))
            d.label('GND', (238.76, 248.92))
        elif net in ('SWCLK', 'SWDIO'):
            old = 'SWD' if net == 'SWDIO' else net
            a = d.anchors[('core', old)]
            series = 'R22' if net == 'SWCLK' else 'R23'
            if series in d.model:
                rx = a[0] if net == 'SWCLK' else 226.06
                ry = 210.82 if net == 'SWCLK' else 218.44
                d.place(series, rx, ry, text=((rx + 5.08, ry + 1.27), (rx + 5.08, ry + 3.81)))
                rp = d.pins(series)
                if rx == a[0]:
                    d.wire(a, rp['1'])
                else:
                    d.wire(a, (a[0], 203.2), (rx, 203.2), rp['1'])
                d.label(net + '_MCU', a, 90)
                a = rp['2']
            yy = 223.52 if net == 'SWCLK' else 226.06
            xx = 233.68 if net == 'SWCLK' else 231.14
            d.wire(a, (a[0], yy), (xx, yy), (xx, p[1]), p)
            d.label(net, (xx, yy))
        else:
            d.rail('J2', pin, net)

    d.place('J3',248.92,262.89,text=((261.62,260.35),(267,262.89)))
    for pin,xx in [('1',233.68),('3',231.14)]:
        p=d.pins('J3')[pin]
        old=d.pins('J2')[pin]
        d.wire((xx,old[1]),(xx,p[1]),p)
        d.junction((xx,old[1]))
    p=d.pins('J3')['2'];d.wire(p,(238.76,p[1]),(238.76,271.78));d.label('GND',(238.76,271.78))
    # USB-C USB2 sink.  ESD I/O pairs are connected on both symbol sides.
    d.place('J1', 375.92, 71.12, mirror='y', text=((375.92, 44.45), (375.92, 46.99)))
    d.place('U3', 321.31, 66.04, text=((321.31, 57.15), (321.31, 59.69)))
    d.place('C21', 302.26, 54.61)
    j, esd = d.pins('J1'), d.pins('U3')
    # Receptacle duplicated D+/D- contacts join once before the ESD part.
    dp, dm = 346.71, 351.79
    d.wire(j['A6'], (dp, j['A6'][1]), (dp, 66.04), esd['6'])
    d.wire(j['B6'], (dp, j['B6'][1]), (dp, j['A6'][1]))
    d.junction((dp, j['A6'][1]))
    d.wire(j['A7'], (dm, j['A7'][1]), (dm, 68.58), esd['4'])
    d.wire(j['B7'], (dm, j['B7'][1]), (dm, j['A7'][1]))
    d.junction((dm, j['A7'][1]))
    d.wire(esd['1'], (308.61, esd['1'][1]), (308.61, 55.88), (328.93, 55.88), (328.93, esd['6'][1]), esd['6'])
    d.wire(esd['3'], (311.15, esd['3'][1]), (311.15, 77.47), (331.47, 77.47), (331.47, esd['4'][1]), esd['4'])
    d.wire(esd['1'], d.anchors[('core', 'USB_D+')])
    d.wire(esd['3'], (292.1, esd['3'][1]), (292.1, 74.93), d.anchors[('core', 'USB_D-')])
    d.label('USB_DP', d.anchors[('core', 'USB_D+')])
    d.label('USB_DM', d.anchors[('core', 'USB_D-')])
    d.label('USB_DP_MCU', (246.38, 66.04))
    d.label('USB_DM_MCU', (246.38, 74.93))
    d.wire(esd['5'], (esd['5'][0], 48.26), (302.26, 48.26), d.pins('C21')['1'])
    d.label('VBUS', (302.26, 48.26))
    d.wire(esd['2'], (esd['2'][0], 81.28), (302.26, 81.28), d.pins('C21')['2'])
    d.label('GND', (302.26, 81.28))
    d.wire(j['A4'], (355.6, j['A4'][1]))
    d.label('VBUS', (355.6, j['A4'][1]))
    for ref, pin, x, y in [('R20', 'A5', 342.9, 91.44), ('R21', 'B5', 355.6, 91.44)]:
        d.place(ref, x, y)
        p = d.pins(ref)
        lead = j[pin]
        # CC routes exit above USB data before descending outside the pair.
        xx = 337.82 if ref == 'R20' else 358.14
        d.wire(lead, (xx, lead[1]), (xx, p['1'][1]), p['1'])
        d.label(d.model[ref]['nets']['1'], (xx, lead[1]))
        d.wire(p['2'], (x, 101.6))
    d.wire((342.9, 101.6), (383.54, 101.6), j['S1'])
    d.wire(j['A1'], (j['A1'][0], 101.6))
    d.junction((355.6, 101.6)); d.junction((375.92, 101.6))
    d.label('GND', (342.9, 101.6))

    # XC6206 fixed 3.3V LDO, 1=GND, 2=OUT, 3=IN, no enable pin.
    d.place('U2',77.47,43.18,text=((77.47,30.48),(77.47,33.02)))
    d.place('C1',54.61,48.26); d.place('C5',99.06,48.26)
    p,ci,co=d.pins('U2'),d.pins('C1'),d.pins('C5')
    d.wire(p['3'],(54.61,p['3'][1]),ci['1']); d.label('VBUS',(54.61,p['3'][1]))
    d.wire(p['2'],(99.06,p['2'][1]),co['1']); d.label('+3V3',(99.06,p['2'][1]))
    d.wire(ci['2'],(54.61,59.69),(77.47,59.69),(99.06,59.69),co['2'])
    d.wire(p['1'],(77.47,59.69));d.junction((77.47,59.69));d.label('GND',(77.47,59.69))

    # Additional local bypass and unpopulated extension pads.
    d.place('C20', 365.76, 36.83)
    d.wire(d.pins('C20')['1'], (365.76, 29.21), (354.33, 29.21))
    d.wire(d.pins('C20')['2'], (365.76, 44.45), (354.33, 44.45))
    d.junction((354.33, 29.21)); d.junction((354.33, 44.45))
    d.place('TP1', 45.72, 83.82, text=((48.26, 80.01), (48.26, 82.55)))
    d.rail('TP1', '1', 'VBUS')
    d.place('TP3', 73.66, 83.82, text=((76.2, 80.01), (76.2, 82.55)))
    d.rail('TP3', '1', 'GND')
    d.place('TP2', 222.25, 264.16, text=((226.06, 261.62), (226.06, 264.16)))
    d.wire(d.anchors[('core', 'GPIO17')], d.pins('TP2')['1'])
    d.label('EXP_GPIO17_3V3', d.pins('TP2')['1'])
    for ref in ('TP1', 'TP2', 'TP3'):
        effects = child(prop(d.symbols[ref], 'Value'), 'effects')
        if not child(effects, 'hide'):
            effects.append([S('hide'), S('yes')])

    # Existing power flags retain their UUIDs and scope through local labels.
    for ref, net, xy in [('#FLG01', 'VBUS', (40.64, 40.64)),
                         ('#FLG02', 'GND', (40.64, 59.69)),
                         ('#FLG03', '+1V1', (237.49, 27.94)),
                         ('#FLG04', 'VREG_AVDD', (273.05, 118.11))]:
        d.place(ref, *xy, text=((xy[0]+4, xy[1]-3), (xy[0]+4, xy[1]-3)))
        effects = child(prop(d.symbols[ref], 'Value'), 'effects')
        if not child(effects, 'hide'):
            effects.append([S('hide'), S('yes')])
        d.label(net, xy)
    for i, ref in enumerate(sorted(r for r in d.model if r.startswith('H'))):
        x = 30.48 + i * 25.4
        d.place(ref, x, 251.46, text=((x, 246.38), (x, 256.54)))

    # Consistent property treatment: keep sparse metadata out of the drawing.
    for ref in ('U1', 'SW61', 'SW62', 'X1', 'L1', 'R7', 'R8', 'R2', 'R4', 'C3', 'C4'):
        symbol = d.symbols[ref]
        x, y, angle = map(float, child(symbol, 'at')[1:4])
        if ref == 'U1':
            coords = ((x, y - 5.08), (x, y))
        elif ref in ('R7', 'R8', 'R2', 'R4'):
            coords = ((x - 3.81, y - 5.08), (x + 1.27, y - 5.08))
        elif ref in ('C3', 'C4'):
            yy = y - 5.08 if ref == 'C3' else y + 5.08
            coords = ((x - 3.81, yy), (x + 1.27, yy))
        elif ref == 'SW61':
            coords = ((x + 10.16, y - 1.27), (x + 10.16, y + 1.27))
        elif ref == 'SW62':
            coords = ((x, y - 7.62), (x, y - 5.08))
        elif ref == 'X1':
            coords = ((x + 10.16, y - 2.54), (x + 10.16, y))
        else:
            coords = ((x + 4, y - 2), (x + 4, y + 1))
        for name, xy in zip(('Reference', 'Value'), coords):
            mirror = child(symbol, 'mirror')
            px, py = xy
            if mirror and mirror[1] == 'y':
                px = 2 * x - px
            if mirror and mirror[1] == 'x':
                py = 2 * y - py
            child(prop(symbol, name), 'at')[1:] = [number(px), number(py), number(angle % 180)]

    d.text('WING27 / RP2354A controller', 15.24, 13.97, 2.286)
    d.text('Raspberry Pi Minimal R4-S1 wired core; RP2354A 2 MB internal flash. No external flash.', 15.24, 20.32)
    d.text('3.3 V supply', 40.64, 26.67, 1.778)
    d.text('DVDD bypass / C10 = 4.7uF', 194.31, 20.32)
    d.text('IOVDD bypass', 279.4, 20.32)
    d.text('USB-C / USB2 + ESD', 302.26, 111.76, 1.778)
    d.text('5 V sink; independent 5.1k CC resistors. Place R7/R8 close to U1.', 295.91, 118.11, 1.016)
    d.text('BOOTSEL', 119.38, 70, 1.778)
    d.text('12 MHz crystal', 146.05, 219.71, 1.778)
    d.text('RESET', 257.81, 201.93, 1.778)
    d.text('Pico H SWD / 1:CLK  2:GND  3:DIO', 239, 255.27, 1.016)
    d.text('Mechanical / M2 NPTH', 25.4, 241.3)
    d.text('TP2 is 3.3 V GPIO only. No 5 V LED driver fitted.', 15.24, 278.13, 1.016)
    d.text('Keep reference SMPS and crystal placement relationships on PCB. USB/thermal/inrush compliance requires testing.', 15.24, 283.21, 1.016)
    return d.finish(), d.imported_segments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'Controller.kicad_sch')
    parser.add_argument('--model', type=Path, default=ROOT / 'scripts/electrical_model.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'Controller.kicad_sch')
    args = parser.parse_args()
    source = parse(args.input.read_text())
    model = json.loads(args.model.read_text())
    reference = parse(next((ROOT / 'reference/RaspberryPi').glob('*.kicad_sch')).read_text())
    output, reused = redraw(source, model, reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dump(output) + '\n')
    print(f'Redrawn {args.output}: reused {reused} official wire segments; component and sheet UUIDs preserved.')


if __name__ == '__main__':
    main()

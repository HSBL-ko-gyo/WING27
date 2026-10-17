#!/usr/bin/env python3
"""Render the matrix with continuous column/row buses and individual key wires."""
from pathlib import Path
import json,uuid,copy
from sexpr import S,parse,dump,children,child,prop
ROOT=Path(__file__).resolve().parent.parent
NS=uuid.UUID('b2fec7d7-7b11-4327-9cdf-121980a18f97')
def uid(s):return str(uuid.uuid5(NS,'matrix-wired:'+s))
def node(s):return parse(s)
def v(x):return S(str(round(x,5)))
a=parse((ROOT/'WING27.kicad_sch').read_text());m=json.loads((ROOT/'scripts/electrical_model.json').read_text())
syms={prop(s,'Reference')[2]:s for s in children(a,'symbol')}
components={c['ref']:c for c in m['components']}
a=[e for e in a if not(isinstance(e,list) and e[0] in ['wire','junction','label','global_label','text'])]
child(a,'title_block')[2]=node('(rev "electrical-3")')
def wire(p,q):
 if p==q:return
 a.append(node(f'(wire(pts(xy {p[0]} {p[1]})(xy {q[0]} {q[1]}))(stroke(width 0)(type default))(uuid "{uid(str((p,q)))}"))'))
def junction(x,y):a.append(node(f'(junction(at {x} {y})(diameter 0)(color 0 0 0 0)(uuid "{uid("junction"+str((x,y)))}"))'))
def label(n,x,y,ang):a.append(node(f'(global_label "{n}"(shape bidirectional)(at {x} {y} {ang})(effects(font(size 1.27 1.27))(justify {"left" if ang in [0,90] else "right"}))(uuid "{uid(n)}"))'))
def text(t,x,y,size=1.27):a.append(node(f'(text {json.dumps(t)}(at {x} {y} 0)(effects(font(size {size} {size}))(justify left))(uuid "{uid(t+str((x,y)))}"))'))
def move(ref,x,y,angle=0):
 s=syms[ref];old=child(s,'at');ox,oy=float(old[1]),float(old[2]);old[1:]=[v(x),v(y),v(angle)]
 for p in children(s,'property'):
  at=child(p,'at');at[1:]=[v(x),v(y-7.62 if p[1]=='Reference' else y-5.08 if p[1]=='Value' else y),v(0)]
 return s
# Paired keys face the dual diode. This avoids branch crossings inside each cell.
for k in m['key_mapping']:
 r,c=k['row'],k['column'];pair=c//2;x=50.8+pair*83.82+(25.4 if c%2 else 0);y=55.88+r*55.88
 move(k['reference'],x,y,180 if c%2 else 0)
 pin1=x+5.08 if c%2 else x-5.08;bus=x+10.16 if c%2 else x-10.16
 wire((pin1,y),(bus,y));junction(bus,y)
 pin2=x-5.08 if c%2 else x+5.08;wire((pin2,y),(pin2,y+12.7))
 legend=components[k['reference']]['metadata'].get('Legend','') or '(blank)'
 text(k['key_id']+' / '+legend,x-5.08,y+5.08,1)
 # Wire net carries one local label for readable key-net names without hidden connectivity.
 n=k['net'];a.append(node(f'(label "{n}"(at {pin2} {y+8.89} 90)(effects(font(size 0.8 0.8))(justify left bottom))(uuid "{uid(n)}"))'))
for r in range(5):
 y=55.88+r*55.88;row_y=y+22.86;xs=[]
 for p in range(6):
  x=63.5+p*83.82;move(f'D{r*6+p+1}',x,y+12.7);wire((x,y+17.78),(x,row_y));junction(x,row_y);xs.append(x)
 for side, subset, start in [('L',xs[:3],25.4),('R',xs[3:],285.75)]:
  for x1,x2 in zip([start]+subset,subset):wire((x1,row_y),(x2,row_y))
  label(f'ROW_{side}{r}',start,row_y,0)
for c in range(12):
 x=50.8+(c//2)*83.82+(35.56 if c%2 else -10.16);ys=[35.56]+[55.88+r*55.88 for r in range(5)]
 for y1,y2 in zip(ys,ys[1:]):wire((x,y1),(x,y2))
 label(f'COL{c}',x,35.56,270)
text('Two independent 5x6 matrices / COL0..5 left, COL6..11 right / separate ROW_L and ROW_R',20.32,15.24,1.5)
text('BAV70: independent anodes 1 / 2; common cathode 3. Dots are connections; unmarked bus crossings are not connected.',20.32,22.86,1.27)
text('Logical rows preserve all 60 physical key IDs; staggered right-hand rows use nearby two-key pairs.',110,354.33,1.27)
(ROOT/'WING27.kicad_sch').write_text(dump(a))
print('Matrix: 12 column buses, 10 independent row buses, 60 wired keys')

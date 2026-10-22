#!/usr/bin/env python3
"""Build WING27 editable, unrouted KiCad project from official reference assets."""
from pathlib import Path
import sys,copy,json,csv,uuid,math,shutil,re
from sexpr import S,parse,dump,children,child,prop
ROOT=Path(__file__).resolve().parent.parent
NS=uuid.UUID('b2fec7d7-7b11-4327-9cdf-121980a18f97')
def uid(s):return str(uuid.uuid5(NS,s))
def node(s):return parse(s)
def clean(a):
 if not isinstance(a,list):return a
 if a and a[0]=='power':return [S('power')]
 return [clean(x) for x in a if not(isinstance(x,list) and x and x[0] in {'show_name','do_not_autoplace','in_pos_files','duplicate_pin_numbers_are_jumpers','duplicate_pad_numbers_are_jumpers','body_style','embedded_files','generator_version','units','legacy_teardrops','tenting','covering'})]
OFF=parse(next((ROOT/'reference/RaspberryPi').glob('*.kicad_sch')).read_text())
OFF=clean(OFF)
OFFPCB=clean(parse(next((ROOT/'reference/RaspberryPi').glob('*.kicad_pcb')).read_text()))
original_symbols={prop(s,'Reference')[2]:s for s in children(OFF,'symbol')}
original_lib={s[1]:s for s in children(child(OFF,'lib_symbols'),'symbol')}
original_fp={prop(s,'Reference')[2]:s for s in children(OFFPCB,'footprint')}
LIB={}; MODS={}; COMPS=[]
PINNET={}
MAIN_ID='77e26e32-63d2-500f-9544-76b2dd8b20de'; SHEET_ID=uid('controller-sheet'); CTRL_ID=uid('controller-root')
# Original switch symbol and footprint stay the same mechanically.
switchlib=clean(next(s for s in children(parse((ROOT/'WING27.kicad_sym').read_text()),'symbol') if s[1].endswith(':Kailh_CMI627301D60') or s[1]=='Kailh_CMI627301D60'))
def rename_lib(s,name):
 s=copy.deepcopy(s); old=s[1];s[1]='WING27:'+name
 for c in children(s,'symbol'):
  suffix=re.search(r'(_\d+_\d+)$',c[1]).group(1);c[1]=name+suffix
 for p in children(s,'property'):
  if p[1]=='Value':p[2]=name
  if p[1]=='Footprint':p[2]='WING27:'+name
  if p[1]=='Datasheet' and p[2].startswith('file:'):p[2]=''
  if name=='RP2354A':
   if p[1]=='manufacturer_pn':p[2]='RP2354A'
   if p[1]=='Description':p[2]='RP2354A MCU, 2MB internal flash, 30GPIO, QFN60 + exposed ground'
   if p[1]=='Datasheet':p[2]='https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf'
 LIB[name]=s;return s
rename_lib(switchlib,'Kailh_CMI627301D60')
swmod=clean(parse((ROOT/'WING27.pretty/Kailh_CMI627301D60.kicad_mod').read_text()));child(swmod,'version')[1]=S('20241229');(ROOT/'WING27.pretty/Kailh_CMI627301D60.kicad_mod').write_text(dump(swmod))
def official_lib(ref,name):return rename_lib(original_lib[child(original_symbols[ref],'lib_id')[1]],name)
def std_lib(file,name,out=None):
 allsy={s[1]:s for s in children(parse((Path('/usr/share/kicad/symbols')/(file+'.kicad_sym')).read_text()),'symbol')}
 def resolve(n):
  s=copy.deepcopy(allsy[n]);ex=child(s,'extends')
  if not ex:return s
  parent=resolve(ex[1]);pmap={p[1]:p for p in children(s,'property')}
  parent=[x for x in parent if not(isinstance(x,list) and x[0]=='property' and x[1] in pmap)]
  parent.extend(copy.deepcopy(list(pmap.values())));parent[1]=n;return parent
 return rename_lib(resolve(name),out or name)
def official_mod(ref):
 f=copy.deepcopy(original_fp[ref]);oa=child(f,'at');origangle=float(oa[3]) if len(oa)>3 else 0
 for e in children(f,'pad')+children(f,'property')+children(f,'fp_text'):
  at=child(e,'at')
  if at and len(at)>3:at[3]=S(str(float(at[3])-origangle))
 name='RPI_'+f[1].split(':')[-1];f[1]=name
 f=[x for x in f if not(isinstance(x,list) and x[0] in {'at','path','sheetname','sheetfile','uuid'})]
 def strip(a):
  if not isinstance(a,list):return a
  return [strip(x) for x in a if not(isinstance(x,list) and x[0] in {'net','pinfunction','pintype','model'})]
 f=strip(f);f.insert(2,node('(version 20241229)'));f.insert(3,node('(generator "pcbnew")'))
 for p in children(f,'property'):
  if p[1]=='Reference':p[2]='REF**'
  if p[1]=='Value':p[2]=name
 (ROOT/'WING27.pretty'/f'{name}.kicad_mod').write_text(dump(f));MODS[name]=f;return name
for ref,name in [('U1','RP2354A'),('L1','AOTA-B201610S3R3-101-T'),('X1','ABM8-272-T3'),('SW1','BOOT_RUN_SW')]:official_lib(ref,name)
for f,n in [('Device','R'),('Device','C'),('Diode','BAV70'),('Power_Protection','USBLC6-2SC6'),('Regulator_Linear','XC6206PxxxMR'),('Connector','USB_C_Receptacle_USB2.0_16P'),('Connector_Generic','Conn_01x03'),('Connector','TestPoint'),('power','PWR_FLAG'),('Mechanical','MountingHole')]:std_lib(f,n)
std_lib('Switch','SW_Push','BOOT_RESET_2PIN')
std_lib('Connector_Generic','Conn_01x03','SWD_TEST_3PIN')
# Connector's two solder hold-down tabs share pad MP, bonded to ground.
child(LIB['Conn_01x03'],'symbol').append(node('(pin passive line (at 0 -10.16 90)(length 3.81)(name "MP"(effects(font(size 1.27 1.27))))(number "MP"(effects(font(size 1.27 1.27)))))'))
def std_mod(lib,name):
 p=Path('/usr/share/kicad/footprints')/(lib+'.pretty')/(name+'.kicad_mod');s=p.read_text();a=parse(s)
 a=[x for x in a if not(isinstance(x,list) and x[0]=='model')]
 (ROOT/'WING27.pretty'/p.name).write_text(dump(a));MODS[name]=a;return name
mods={
 'R':official_mod('R7'),'C':official_mod('C12'),'Cwide':official_mod('C7'),'MCU':official_mod('U1'),'L':official_mod('L1'),'X':official_mod('X1'),'SW':official_mod('SW1'),
 'D':std_mod('Package_TO_SOT_SMD','SOT-23'),'U2':std_mod('Package_TO_SOT_SMD','SOT-23-3'),'U3':std_mod('Package_TO_SOT_SMD','SOT-23-6'),
 'J1':std_mod('Connector_USB','USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal'),
 'J2':std_mod('Connector_JST','JST_SH_BM03B-SRSS-TB_1x03-1MP_P1.00mm_Vertical'),
 'H':std_mod('MountingHole','MountingHole_2.2mm_M2'),
 'TP':std_mod('TestPoint','TestPoint_Pad_D1.5mm'),'C0603':std_mod('Capacitor_SMD','C_0603_1608Metric')}
# JLC-compatible variant: preserve manufacturer pad envelopes and all holes;
# increase outer ground-pad corner radius from 0.15 to 0.24 mm for NPTH clearance.
usb_original=ROOT/'WING27.pretty'/(mods['J1']+'.kicad_mod')
usb=parse(usb_original.read_text());usb[1]='USB_C_GCT_USB4105_GF_A060_JLC'
for pad in children(usb,'pad'):
 if pad[1] in ['A1','A12','B1','B12']:
  assert pad[3]=='roundrect'
  child(pad,'roundrect_rratio')[1]=S('0.4')
mods['J1']=usb[1]
child(usb,'descr')[1]+='; WING27: outer GND pad radius 0.24mm for >=0.20mm NPTH-to-copper clearance; centers, 0.60x1.15 envelopes and holes unchanged'
(ROOT/'WING27.pretty'/(mods['J1']+'.kicad_mod')).write_text(dump(usb))
usb_original.unlink()
# TOREX SOT-23 reference land: 1.0x0.8mm pads, 2.4mm opposing centers, 1.9mm same-side pitch.
ldo=parse((ROOT/'WING27.pretty/SOT-23-3.kicad_mod').read_text());ldo[1]='XC6206_SOT23_Torex_Reference'
child(ldo,'descr')[1]='TOREX SOT-23 manufacturer reference land; body 2.9x1.6mm; https://www.torexsemi.com/file/SOT-23/SOT-23-pkg.pdf'
for pad in children(ldo,'pad'):
 x,y={'1':(-1.2,-.95),'2':(-1.2,.95),'3':(1.2,0)}[pad[1]]
 child(pad,'at')[1:3]=[S(str(x)),S(str(y))];child(pad,'size')[1:]=[S('1.0'),S('.8')]
(ROOT/'WING27.pretty'/(ldo[1]+'.kicad_mod')).write_text(dump(ldo));mods['U2']=ldo[1]
mods['SW']='SW_SPST_TS-1088-AR02016'
mods['J3']=std_mod('Connector_PinHeader_2.54mm','PinHeader_1x03_P2.54mm_Vertical')
# Explicit schematic and PCB connectivity model. Every numbered pin is accounted for.
def add(ref,lib,value,fp,nets,pos,pcb,metadata=None,sheet='controller',uuid_existing=None):
 c=dict(ref=ref,lib=lib,value=value,fp=fp,nets=nets,pos=pos,pcb=pcb,metadata=metadata or {},sheet=sheet,uuid=uuid_existing or uid(ref));COMPS.append(c);return c
def offmeta(ref):
 s=original_symbols[ref];return {p[1]:p[2] for p in children(s,'property') if p[1] in ['manufacturer','manufacturer_pn','Description','voltage','dielectric','tolerance']}
def offpcb(ref):
 a=child(original_fp[ref],'at');return [float(a[1])+24,float(a[2])-51,float(a[3]) if len(a)>3 else 0]
def pins(lib):
 return [p for s in children(LIB[lib],'symbol') for p in children(s,'pin')]
# Independent halves: left COL0..5=GPIO19..24, ROW_L0..4=GPIO25..29; right COL6..11=GPIO6..11, ROW_R0..4=GPIO0..4. GPIO17 is reserved for extension.
mcu={str(n):'+3V3' for n in [1,11,20,30,38,44,45,49,53,54]}
mcu.update({str(n):'+1V1' for n in [6,23,39,50]});mcu.update({'46':'VREG_AVDD','47':'GND','48':'VREG_LX','61':'GND','21':'XIN','22':'XOUT','24':'SWCLK_MCU','25':'SWDIO_MCU','26':'RUN','51':'USB_DM_MCU','52':'USB_DP_MCU','60':'QSPI_SS'})
for p in pins('RP2354A'):
 n=child(p,'name')[1];pn=child(p,'number')[1]
 if n.startswith('GPIO'):
  gpio=int(re.match(r'GPIO(\d+)',n).group(1));mcu[pn]={17: 'EXP_GPIO17_3V3', 19: 'COL0', 20: 'COL1', 21: 'COL2', 22: 'COL3', 23: 'COL4', 24: 'COL5', 6: 'COL6', 7: 'COL7', 8: 'COL8', 9: 'COL9', 10: 'COL10', 11: 'COL11', 25: 'ROW_L0', 26: 'ROW_L1', 27: 'ROW_L2', 28: 'ROW_L3', 29: 'ROW_L4', 0: 'ROW_R0', 1: 'ROW_R1', 2: 'ROW_R2', 3: 'ROW_R3', 4: 'ROW_R4'}.get(gpio)
for n in [55,56,57,58,59]:mcu[str(n)]=None
add('U1','RP2354A','RP2354A',mods['MCU'],mcu,(108,102),offpcb('U1'),{'manufacturer':'Raspberry Pi','manufacturer_pn':'RP2354A','Description':'2MB internal flash, QFN60 + exposed ground; 30 GPIO','Datasheet':'https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf'})
add('L1','AOTA-B201610S3R3-101-T','3.3uH',mods['L'],{'1':'+1V1','2':'VREG_LX'},(240,50),offpcb('L1'),offmeta('L1'))
add('X1','ABM8-272-T3','12MHz',mods['X'],{'1':'XIN','2':'GND','3':'XTAL_OUT','4':'GND'},(235,132),offpcb('X1'),offmeta('X1'))
resdefs=[('R2','1k',{'1':'XOUT','2':'XTAL_OUT'},(208,132)),('R3','33',{'1':'+3V3','2':'VREG_AVDD'},(280,50)),('R4','1k',{'1':'RUN_SWITCH','2':'GND'},(328,150)),('R6','1k',{'1':'QSPI_SS','2':'BOOT_SWITCH'},(280,150)),('R7','27',{'1':'USB_DP','2':'USB_DP_MCU'},(66,210)),('R8','27',{'1':'USB_DM','2':'USB_DM_MCU'},(90,210))]
for r,v,n,pos in resdefs:add(r,'R',v,mods['R'],n,pos,offpcb(r),offmeta(r))
# Reference core capacitors. C10 is deliberately updated per datasheet Release 8, §6.3.8.1.
capdefs=[('C3','15p','XIN',(218,155)),('C4','15p','XTAL_OUT',(248,155)),('C6','4.7u','+3V3',(218,75)),('C7','4.7u','+1V1',(240,75)),('C8','100n','+1V1',(210,105)),('C9','4.7u','VREG_AVDD',(280,75)),('C10','4.7u','+1V1',(234,105)),('C11','100n','+1V1',(258,105)),('C12','100n','+3V3',(215,205)),('C13','100n','+3V3',(240,205)),('C14','100n','+3V3',(265,205)),('C15','100n','+3V3',(290,205)),('C16','100n','+3V3',(315,205)),('C17','100n','+3V3',(340,205)),('C18','100n','+3V3',(365,205))]
for r,v,n,pos in capdefs:
 md=offmeta(r)
 if r=='C10':md=offmeta('C7');md['Description']='4.7uF at farthest DVDD pin23 (RP2350 datasheet R8 6.3.8.1)'
 add(r,'C',v,mods['Cwide'] if r in ['C6','C7'] else mods['C'],{'1':n,'2':'GND'},pos,offpcb(r),md)
add('C20','C','100n',mods['C'],{'1':'+3V3','2':'GND'},(365,235),(120.7,41.6,90),offmeta('C12'))
add('SW61','BOOT_RESET_2PIN','BOOTSEL',mods['SW'],{'1':'GND','2':'BOOT_SWITCH'},(280,175),(99,61,0),{'manufacturer':'XUNPU','manufacturer_pn':'TS-1088-AR02016','LCSC':'C720477','Description':'JLC Basic; 2-terminal SPST N.O. tactile 3.9x3.0x2.0mm, 160gf','Datasheet':'https://datasheet.lcsc.com/datasheet/pdf/0475ac02febf455ca9ddcfb380b0df0d.pdf?productCode=C720477'})
add('SW62','BOOT_RESET_2PIN','RESET',mods['SW'],{'1':'RUN_SWITCH','2':'RUN'},(328,175),(148,61,0),{'manufacturer':'XUNPU','manufacturer_pn':'TS-1088-AR02016','LCSC':'C720477','Description':'JLC Basic; 2-terminal SPST N.O. tactile 3.9x3.0x2.0mm, 160gf','Datasheet':'https://datasheet.lcsc.com/datasheet/pdf/0475ac02febf455ca9ddcfb380b0df0d.pdf?productCode=C720477'})
# USB-C USB2 sink, fixed 5V only: separate Rd on each CC pin; no PD controller.
usbnets={'A1':'GND','B12':'GND','A4':'VBUS','B9':'VBUS','A5':'CC1','B5':'CC2','A6':'USB_DP','B6':'USB_DP','A7':'USB_DM','B7':'USB_DM','A8':None,'B8':None,'S1':'GND','A9':'VBUS','B4':'VBUS','A12':'GND','B1':'GND'}
# Symbol stacks alternate GND and VBUS pins; filter by actual symbol numbers.
usbnets={child(p,'number')[1]:usbnets[child(p,'number')[1]] for p in pins('USB_C_Receptacle_USB2.0_16P')}
add('J1','USB_C_Receptacle_USB2.0_16P','USB4105-GF-A-060',mods['J1'],usbnets,(35,208),(124,25,180),{'manufacturer':'GCT','manufacturer_pn':'USB4105-GF-A-060','LCSC':'C3025063','Datasheet':'https://gct.co/files/drawings/usb4105.pdf','Description':'USB2 16-pin top-mount USB-C receptacle; 0.60mm shell legs'})
for r,n,p,pos in [('R20','CC1',(117,29,0),(66,240)),('R21','CC2',(131,29,0),(90,240))]:add(r,'R','5.1k',mods['R'],{'1':n,'2':'GND'},pos,p,{'manufacturer':'Yageo','manufacturer_pn':'RC0402FR-075K1L','Description':'USB-C independent Rd 5.1k 1%'})
add('U3','USBLC6-2SC6','USBLC6-2SC6',mods['U3'],{'1':'USB_DP','6':'USB_DP','3':'USB_DM','4':'USB_DM','2':'GND','5':'VBUS'},(130,215),(124,32,0),{'manufacturer':'STMicroelectronics','manufacturer_pn':'USBLC6-2SC6','LCSC':'C7519','Datasheet':'https://www.st.com/resource/en/datasheet/usblc6-2.pdf'})
add('U2','XC6206PxxxMR','XC6206P332MR-G',mods['U2'],{'1':'GND','2':'+3V3','3':'VBUS'},(340,50),(141,33,0),{'manufacturer':'Torex Semiconductor','manufacturer_pn':'XC6206P332MR-G','LCSC':'C5446','Description':'JLC Basic; fixed 3.3V LDO, SOT23-3. Design target <=100mA continuous, not measured. LED power must bypass this rail.','Datasheet':'https://product.torexsemi.com/system/files/series/xc6206.pdf'})
for r,v,n,pos,pcb in [('C1','1u','VBUS',(315,75),(138,33,90)),('C5','4.7u','+3V3',(365,75),(144,33,90)),('C21','100n','VBUS',(160,215),(127,32,90))]:
 add(r,'C',v,mods['C0603'] if r in ['C1','C5'] else mods['C'],{'1':n,'2':'GND'},pos,pcb,({'manufacturer':'Samsung Electro-Mechanics','manufacturer_pn':'CL10A475KO8NNNC','LCSC':'C19666','Description':'4.7uF 16V X5R0603 output bypass; verify effective capacitance including bias/tolerance','Datasheet':'https://jlcpcb.com/partdetail/C19666'} if r=='C5' else {'manufacturer':'Samsung Electro-Mechanics','manufacturer_pn':'CL10A105KB8NNNC','LCSC':'C15849','Description':'1uF 50V X5R 0603, LDO input ceramic','Datasheet':'https://jlcpcb.com/partdetail/C15849'} if r in ['C1','C5'] else offmeta('C12')))
add('J2','Conn_01x03','BM03B-SRSS-TB',mods['J2'],{'1':'SWCLK','2':'GND','3':'SWDIO','MP':'GND'},(380,140),(139,65,90),{'manufacturer':'JST','manufacturer_pn':'BM03B-SRSS-TB(LF)(SN)','LCSC':'C160389','Datasheet':'https://datasheets.raspberrypi.com/debug/debug-connector-specification.pdf','Description':'Pico H-compatible JST SH top-entry SWD: 1=SWCLK, 2=GND, 3=SWDIO; no power pin; straight-through cable'})
for r,n,pos,pcb in [('TP1','VBUS',(310,242),(109,67,0)),('TP2','EXP_GPIO17_3V3',(340,242),(113,67,0)),('TP3','GND',(370,242),(117,67,0))]:add(r,'TestPoint',n,mods['TP'],{'1':n},pos,pcb,{'Description':'Power/GPIO test pads; see LED sheet for GPIO17 use.'})
# Matrix: each half has its own five logical row nets. Physical stagger need not equal logical rows.
rows=list(csv.DictReader((ROOT/'reference/P2/Wing27_P2_60_key_center_coordinates_mm.csv').open(encoding='utf-8-sig')))
base=parse((ROOT/'WING27.kicad_sch').read_text());baseSW={prop(s,'Reference')[2]:s for s in children(base,'symbol') if prop(s,'Reference')[2].startswith('SW')}
mapping=[]
for i,k in enumerate(rows):
 half=i//30;j=i%30;r=j//6;c=j%6+half*6
 if half:
  right_pairs=[['R1_1','R1_2'],['R1_3','R1_4'],['R1_5','R1_6'],['R2_1','R2_2'],['R2_3','R2_4'],['R1_7','R2_6'],['R3_1','R3_2'],['R3_3','R3_4'],['R2_5','R3_5'],['R4_1','R4_2'],['R4_3','R4_4'],['R4_5','R4_6'],['R5_1','R5_2'],['R5_3','R5_4'],['R5_5','R5_6']]
  pi=next(i for i,p in enumerate(right_pairs) if k['key_id'] in p);r=pi//3;c=6+(pi%3)*2+right_pairs[pi].index(k['key_id'])
 pair=c//2;did=r*6+pair+1;dpin=str(1+c%2);ref=f'SW{i+1}';net=f'KEY_{k["key_id"]}'
 x=43+pair*88+(0 if c%2==0 else 37);y=45+r*59
 md={'Key_ID':k['key_id'],'Legend':k['label'],'Assembly':'Hand solder','Source_X_mm':k['center_x_mm'],'Source_Y_mm':k['center_y_mm'],'manufacturer':'Kailh','manufacturer_pn':'CMI627301D60'}
 add(ref,'Kailh_CMI627301D60','CMI627301D60','Kailh_CMI627301D60',{'1':f'COL{c}','2':net},(x,y),(20+float(k['center_x_mm']),78-float(k['center_y_mm']),0),md,'matrix',child(baseSW[ref],'uuid')[1])
 mapping.append(dict(key_id=k['key_id'],reference=ref,row=r,column=c,diode=f'D{did}',anode_pin=dpin,net=net,x=float(k['center_x_mm']),y=float(k['center_y_mm'])))
for r in range(5):
 for p in range(6):
  did=r*6+p+1;ks=[m for m in mapping if m['diode']==f'D{did}'];nets={'3':f'ROW_{"L" if p<3 else "R"}{r}',**{k['anode_pin']:k['net'] for k in ks}}
  # Two diode banks outside the official MCU/core footprint, behind the phone.
  bank=p//3;dx=90+bank*55+(p%3)*4.5;dy=38+r*4.8
  add(f'D{did}','BAV70','BAV70',mods['D'],nets,(61.5+p*88,65+r*59),(dx,dy,180 if bank else 0),{'manufacturer':'Jiangsu Changjing Electronics','manufacturer_pn':'BAV70','LCSC':'C68978','Description':'Dual common cathode; both anodes belong to same ROW','Datasheet':'https://jlcpcb.com/partdetail/BAV70/C68978'},'matrix')
# Raspberry Pi 3-pin debug specification recommends 100-ohm series resistors near the MCU.
for ref,signal,pcb in [('R22','SWCLK',(124.1,53.9,270)),('R23','SWDIO',(125.4,53.9,270))]:
 add(ref,'R','100',mods['R'],{'1':signal+'_MCU','2':signal},(355,120 if ref=='R22' else 130),pcb,{'manufacturer':'Yageo','manufacturer_pn':'RC0402FR-07100RL','Description':'100ohm 1% SWD series termination near MCU; Raspberry Pi debug connector specification recommendation'})
# User-requested 180-degree rotation of central electronics around panel center.
# Key positions stay fixed. Right diode bank rotates 180 degrees locally; left/right banks do not swap.
for c in COMPS:
 if not (c['ref'].startswith('D') or (c['ref'].startswith('SW') and int(c['ref'][2:])<=60)):
  x,y,angle=c['pcb'];c['pcb']=[248-x,98-y,(angle+180)%360]
# Move the rotated service buttons above the preserved diode banks to avoid overlap.
for c in COMPS:
 if c['ref'] in ['SW61','SW62']:c['pcb'][1]=29
add('J3','SWD_TEST_3PIN','SWD 2.54 DNP',mods['J3'],{'1':'SWCLK','2':'GND','3':'SWDIO'},(200,238),(112,39,90),{'Assembly':'DNP','Description':'Optional unpopulated 2.54mm 1x3 test/header holes; same order as SH: 1 SWCLK, 2 GND, 3 SWDIO; connector side of 100ohm resistors'})
# Provisional M2 clearance holes: source-panel coordinates, 5mm boss envelope.
for i,(x,y) in enumerate([(3,3),(3,55),(205,3),(205,55)],1):
 add(f'H{i}','MountingHole','M2 clearance 2.2mm',mods['H'],{},(200+i*30,280),(20+x,78-y,0),{'Description':'Provisional M2 NPTH; 5mm boss envelope. Confirm final case, PCB outline and fasteners.'})
# All required pin entries must match the actual symbols exactly.
for c in COMPS:
 ps={child(p,'number')[1] for p in pins(c['lib'])}
 assert set(c['nets'])==ps,(c['ref'],ps-set(c['nets']),set(c['nets'])-ps)
(ROOT/'scripts/electrical_model.json').write_text(json.dumps({'components':COMPS,'key_mapping':mapping,'root_uuid':MAIN_ID,'controller_sheet_uuid':SHEET_ID,'controller_uuid':CTRL_ID},ensure_ascii=False,indent=2))
# Schematic generation. Labels are global across two sheets, with short pin stubs.
def q(s):return json.dumps(str(s),ensure_ascii=False)
def txt(s,x,y,size=1.27):return node(f'(text {q(s)} (at {x} {y} 0) (effects(font(size {size} {size}))(justify left)) (uuid "{uid(str((s,x,y)))}"))')
def make_sheet(which):
 ident=MAIN_ID if which=='matrix' else CTRL_ID
 a=node(f'(kicad_sch (version 20250114)(generator "eeschema")(uuid "{ident}")(paper "{"A2" if which=="matrix" else "A3"}")(title_block(title "WING27 / {"60-key matrix" if which=="matrix" else "RP2354A / USB-C controller"}")(rev "electrical-3")(company "ハシビロ工業")))')
 used={c['lib'] for c in COMPS if c['sheet']==which};used.add('PWR_FLAG') if which=='controller' else None
 a.append([S('lib_symbols')]+[copy.deepcopy(LIB[n]) for n in sorted(used)])
 for c in [c for c in COMPS if c['sheet']==which]:
  x,y=[round(round(v/1.27)*1.27,5) for v in c['pos']];ref=c['ref'];sn=node(f'(symbol(lib_id "WING27:{c["lib"]}")(at {x} {y} 0)(unit 1)(exclude_from_sim no)(in_bom {"no" if (ref.startswith("TP") or ref.startswith("H")) else "yes"})(on_board yes)(dnp {"yes" if ref=="J3" else "no"})(uuid "{c["uuid"]}"))')
  vals={'Reference':ref,'Value':c['value'],'Footprint':'WING27:'+c['fp'],**c['metadata']}
  for k,v in vals.items():
   yy=y-6 if k=='Reference' else y-3 if k=='Value' else y
   special={'J1':(-24,-21),'U2':(-12,-9),'U3':(-13,-10),'J2':(-11,-8),'X1':(-11,-8)}
   if ref in special and k in ['Reference','Value']:yy=y+special[ref][0 if k=='Reference' else 1]
   sn.append(node(f'(property {q(k)} {q(v)} (at {x} {yy} 0)(effects(font(size 1 1)){"(hide yes)" if k not in ["Reference","Value"] else ""}))'))
  for p in pins(c['lib']):sn.append(node(f'(pin {q(child(p,"number")[1])}(uuid "{uid(ref+":pin:"+child(p,"number")[1])}"))'))
  path='/'+MAIN_ID+('/'+SHEET_ID if which=='controller' else '')
  sn.append(node(f'(instances(project "WING27"(path "{path}"(reference "{ref}")(unit 1))))'));a.append(sn)
  for p in pins(c['lib']):
   pn=child(p,'number')[1];pa=child(p,'at');px=x+float(pa[1]);py=y-float(pa[2]);angle=int(pa[3]);net=c['nets'][pn]
   if net is None:a.append(node(f'(no_connect(at {px} {py})(uuid "{uid(ref+":"+pn+":NC")}"))'));continue
   rad=math.radians(angle);ex=round(px-3.81*math.cos(rad),5);ey=round(py+3.81*math.sin(rad),5)
   a.append(node(f'(wire(pts(xy {px} {py})(xy {ex} {ey}))(stroke(width 0)(type default))(uuid "{uid(ref+":"+pn+":wire")}"))'))
   # Local labels are sufficient on each sheet except matrix/extension nets.
   isglobal=net.startswith('COL') or net.startswith('ROW')
   tag='global_label' if isglobal else 'label';shape='(shape bidirectional)' if isglobal else ''
   la=(angle+180)%360
   a.append(node(f'({tag} {q(net)} {shape}(at {ex} {ey} {la})(effects(font(size 0.85 0.85))(justify {"left" if la in [0,90] else "right"} bottom))(uuid "{uid(ref+":"+pn+":label")}"))'))
 if which=='matrix':
  a.append(txt('60 keys / independent left and right 5x6 matrices. Read COL0..11 with pull-ups; drive one ROW low, other ROWs high-impedance.',20,14,1.5))
  a.append(txt('BAV70: pin 1/2 = independent anodes; pin 3 = common cathode to one ROW. Physical stagger is independent of logical row.',20,21,1.27))
  for m in mapping:
   c=next(c for c in COMPS if c['ref']==m['reference']);x,y=c['pos'];a.append(txt(m['key_id']+' / '+c['metadata']['Legend'],x-9,y+10,1))
  a.append(node(f'(sheet(at 30 350)(size 65 20)(fields_autoplaced yes)(stroke(width 0)(type default))(fill(color 0 0 0 0))(uuid "{SHEET_ID}")(property "Sheetname" "Controller"(at 30 348 0)(effects(font(size 1.27 1.27))(justify left bottom)))(property "Sheetfile" "Controller.kicad_sch"(at 30 372 0)(effects(font(size 1.27 1.27))(justify left top)))(instances(project "WING27"(path "/{MAIN_ID}"(page "2")))))'))
  a.append(node('(sheet_instances(path "/"(page "1")))'))
 else:
  a.append(txt('Official RP2350A Minimal R4-S1 core reused; RP2354A 2MB internal flash, no external flash.',15,15,1.5))
  a.append(txt('Release 8 datasheet: C10=4.7uF at DVDD pin23. Keep L1 marked orientation and official SMPS component relationships.',15,22,1.2))
  a.append(txt('USB-C sink / 5V only. CC1 and CC2 each 5.1k. USB and inrush compliance require firmware + hardware testing.',15,29,1.2))
  a.append(txt('Expansion pads only: no NeoPixel fitted. EXP_GPIO17_3V3 is NOT a 5V-level LED driver.',210,265,1.2))
  a.append(txt('Artwork/unrouted board is user work. Keep USB pair short, matched, continuous ground reference; 27R by MCU.',15,275,1.2))
  # Power flag drivers on rails driven through passive/filter elements.
  for i,net in enumerate(['VBUS','GND','+1V1','VREG_AVDD']):
   ref=f'#FLG0{i+1}';x=round(round((25+i*35)/1.27)*1.27,5);y=170.18;u=uid(ref)
   a.append(node(f'(symbol(lib_id "WING27:PWR_FLAG")(at {x} {y} 0)(unit 1)(in_bom no)(on_board yes)(dnp {"yes" if ref=="J3" else "no"})(uuid "{u}")(property "Reference" "{ref}"(at {x} {y} 0)(effects(font(size 1 1))(hide yes)))(property "Value" "PWR_FLAG"(at {x} {y-4} 0)(effects(font(size 1 1))))(pin "1"(uuid "{uid(ref+"p")}"))(instances(project "WING27"(path "/{MAIN_ID}/{SHEET_ID}"(reference "{ref}")(unit 1)))))'))
   a.append(node(f'(label "{net}"(at {x} {y} 0)(effects(font(size 1 1))(justify left bottom))(uuid "{uid(ref+"l")}"))'))
 a.append(node('(embedded_fonts no)'));return a
(ROOT/'WING27.kicad_sch').write_text(dump(make_sheet('matrix')))
(ROOT/'Controller.kicad_sch').write_text(dump(make_sheet('controller')))
(ROOT/'WING27.kicad_sym').write_text(dump([S('kicad_symbol_lib'),node('(version 20241209)'),node('(generator "kicad_symbol_editor")')]+[[S('symbol'),n]+copy.deepcopy(LIB[n][2:]) for n in sorted(LIB)]))
(ROOT/'sym-lib-table').write_text('(sym_lib_table (lib (name "WING27")(type "KiCad")(uri "${KIPRJMOD}/WING27.kicad_sym")(options "")(descr "Project-local symbols")))\n')
(ROOT/'fp-lib-table').write_text('(fp_lib_table (lib (name "WING27")(type "KiCad")(uri "${KIPRJMOD}/WING27.pretty")(options "")(descr "Project-local footprints")))\n')
print('Generated',len(COMPS),'components and',len(mapping),'key mappings')

# Readable drawings are part of the generated deliverable, not optional label-only views.
import subprocess
for helper in ['redraw_matrix.py','redraw_controller.py','add_leds.py']:
 subprocess.run([sys.executable,str(ROOT/'scripts'/helper)],check=True)

# Keep reviewed procurement fields when regenerating the electrical project.
if (ROOT/"scripts/procurement_parts.json").exists():
 subprocess.run([sys.executable,str(ROOT/"scripts/apply_procurement.py")],check=True)

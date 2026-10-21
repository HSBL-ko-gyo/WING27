#!/usr/bin/python3
"""Read-only electrical audit. Run with system Python (KiCad pcbnew installed).
Usage: /usr/bin/python3 audit_wing27.py REPO_PATH [REPORT_DIRECTORY]
Only outputs netlist, logs and reports under REPORT_DIRECTORY; never saves native files.
"""
import collections,csv,datetime,hashlib,itertools,json,os,pathlib,random,re,subprocess,sys
ROOT=pathlib.Path(sys.argv[1]).resolve()
OUT=pathlib.Path(sys.argv[2] if len(sys.argv)>2 else pathlib.Path(__file__).parent).resolve(); OUT.mkdir(parents=True,exist_ok=True)
for name in ['XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME']:os.environ[name]='/tmp/wing27_audit_'+name.lower()
import pcbnew

def parse(t):
    toks=re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()]+',t);i=0
    def p():
        nonlocal i
        x=toks[i];i+=1
        if x=='(':
            a=[]
            while toks[i]!=')':a.append(p())
            i+=1;return a
        return json.loads(x) if x.startswith('"') else x
    return p()
def children(a,k):return [x for x in a if isinstance(x,list) and x and x[0]==k]
def child(a,k):return next(iter(children(a,k)),None)
def prop(a,k):return next((x for x in children(a,'property') if x[1]==k),None)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
inputs=['WING27.kicad_sch','Controller.kicad_sch','WING27.kicad_pcb','scripts/electrical_model.json']
if (ROOT/'LEDs.kicad_sch').exists():inputs.append('LEDs.kicad_sch')
before={name:digest(ROOT/name) for name in inputs}
run=subprocess.run(['kicad-cli','sch','export','netlist','-o',str(OUT/'independent.net'),str(ROOT/'WING27.kicad_sch')],capture_output=True,text=True,env=os.environ)
(OUT/'netlist_export.log').write_text(run.stdout+run.stderr)
assert run.returncode==0,'Netlist export failed; see log'
N=parse((OUT/'independent.net').read_text());comps={child(c,'ref')[1]:c for c in children(child(N,'components'),'comp')}
by_pin={};by_net={};raw_netnames={}
for n in children(child(N,'nets'),'net'):
    raw=child(n,'name')[1];name=raw.split('/')[-1];ns=[]
    assert name not in by_net,('Basename collision',name)
    raw_netnames[name]=raw
    for e in children(n,'node'):
        ref,pin=child(e,'ref')[1],child(e,'pin')[1];ns.append((ref,pin));assert (ref,pin) not in by_pin
        by_pin[ref,pin]=name
    by_net[name]=ns
B=pcbnew.LoadBoard(str(ROOT/'WING27.kicad_pcb'));assert B is not None
pcb_issues=[];pad_count=0
for fp in B.GetFootprints():
    for p in fp.Pads():
        num=p.GetNumber()
        if not num:continue
        pad_count+=1;net=p.GetNetname().split('/')[-1];want=by_pin.get((fp.GetReference(),num),'')
        if net.startswith('unconnected-'):net=''
        if want.startswith('unconnected-'):want=''
        if net!=want:pcb_issues.append([fp.GetReference(),num,net,want])
assert not pcb_issues,pcb_issues
M=json.loads((ROOT/'scripts/electrical_model.json').read_text());model_issues=[]
for c in M['components']:
    for pin,want in c['nets'].items():
        got=by_pin.get((c['ref'],pin),'');got='' if got.startswith('unconnected-') else got
        if got!=(want or ''):model_issues.append([c['ref'],pin,got,want])
assert not model_issues,model_issues
keys={}
for i in range(1,61):
    s=f'SW{i}';a,b=by_pin[s,'1'],by_pin[s,'2'];assert a.startswith('COL') and b.startswith('KEY_')
    nodes=by_net[b];ds=[(r,p) for r,p in nodes if r.startswith('D')];assert len(nodes)==2 and len(ds)==1
    d,p=ds[0];assert p in ['1','2'];row=by_pin[d,'3'];assert row.startswith('ROW')
    keys[s]={'key':b[4:],'row':row,'col':int(a[3:]),'diode':d,'anode':p}
assert set((k['row'],k['col']) for k in keys.values())=={(f'ROW_{side}{r}',c) for side,cols in [('L',range(6)),('R',range(6,12))] for r in range(5) for c in cols}
assert len(keys)==60
for d in [f'D{i}' for i in range(1,31)]:
    branches=[k for k in keys.values() if k['diode']==d]
    assert len(branches)==2 and branches[0]['row']==branches[1]['row'] and branches[0]['col']!=branches[1]['col']
for side in ['L','R']:
 for r in range(5):assert len(by_net[f'ROW_{side}{r}'])==4
for c in range(12):assert len(by_net[f'COL{c}'])==6
# Ideal diode graph: closed switch is bidirectional, diode is anode->cathode.
# Unselected ROW nodes have no outgoing conduction paths, eliminating phantom paths
# for any subset of closed switches, not just the enumerated regression patterns.
base=collections.defaultdict(set)
for i in range(1,31):
    for p in ['1','2']:base[by_pin[f'D{i}',p]].add(by_pin[f'D{i}','3'])
def sense(pressed):
    graph={x:set(v) for x,v in base.items()}
    for s in pressed:
        a,b=by_pin[s,'1'],by_pin[s,'2'];graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
    sensed=set()
    for c in range(12):
        stack=[f'COL{c}'];seen=set(stack)
        while stack:
            x=stack.pop()
            for nxt in graph.get(x,[]):
                if nxt not in seen:seen.add(nxt);stack.append(nxt)
        for side in ['L','R']:
            for r in range(5):
                row=f'ROW_{side}{r}'
                if row in seen:sensed.add((row,c))
    return sensed
cases=0
for count in range(4):
    for pressed in itertools.combinations(keys,count):
        assert sense(pressed)=={(keys[s]['row'],keys[s]['col']) for s in pressed};cases+=1
random.seed(274)
for i in range(1000):
    pressed=random.sample(list(keys),random.randrange(61));assert sense(pressed)=={(keys[s]['row'],keys[s]['col']) for s in pressed};cases+=1
assert len(sense(list(keys)))==60;cases+=1
# Independent expected pin table, from RP2350 Datasheet R8 Fig.2/section 14.3.
pin_names=['IOVDD','GPIO0','GPIO1','GPIO2','GPIO3','DVDD','GPIO4','GPIO5','GPIO6','GPIO7','IOVDD','GPIO8','GPIO9','GPIO10','GPIO11','GPIO12','GPIO13','GPIO14','GPIO15','IOVDD','XIN','XOUT','DVDD','SWCLK','SWDIO','RUN','GPIO16','GPIO17','GPIO18','IOVDD','GPIO19','GPIO20','GPIO21','GPIO22','GPIO23','GPIO24','GPIO25','IOVDD','DVDD','GPIO26_ADC0','GPIO27_ADC1','GPIO28_ADC2','GPIO29_ADC3','ADC_AVDD','IOVDD','VREG_AVDD','VREG_PGND','VREG_LX','VREG_VIN','VREG_FB','USB_DM','USB_DP','USB_OTP_VDD','QSPI_IOVDD','QSPI_SD3','QSPI_SCLK','QSPI_SD0','QSPI_SD2','QSPI_SD1','QSPI_~{SS}','GND']
parts=children(child(N,'libparts'),'libpart');u=next(c for c in parts if child(c,'part')[1]=='RP2354A')
upins={child(p,'num')[1]:child(p,'name')[1] for p in children(child(u,'pins'),'pin')}
assert upins=={str(i+1):x for i,x in enumerate(pin_names)}
expected_u={str(p):'+3V3' for p in [1,11,20,30,38,44,45,49,53,54]}
expected_u.update({str(p):'+1V1' for p in [6,23,39,50]})
expected_u.update({'46':'VREG_AVDD','47':'GND','48':'VREG_LX','61':'GND','21':'XIN','22':'XOUT','24':'SWCLK_MCU','25':'SWDIO_MCU','26':'RUN','51':'USB_DM_MCU','52':'USB_DP_MCU','60':'QSPI_SS','28':'EXP_GPIO17_3V3'})
expected_u.update({str(p):f'COL{i}' for i,p in enumerate([31,32,33,34,35,36,9,10,12,13,14,15])})
expected_u.update({str(p):f'ROW_L{i}' for i,p in enumerate([37,40,41,42,43])})
expected_u.update({str(p):f'ROW_R{i}' for i,p in enumerate([2,3,4,5,7])})
for p,n in expected_u.items():assert by_pin['U1',p]==n
for p in [8,16,17,18,19,27,29,55,56,57,58,59]:assert by_pin['U1',str(p)].startswith('unconnected-')
expected={
 'U2':{'1':'GND','2':'+3V3','3':'VBUS'},
 'U3':{'1':'USB_DP','6':'USB_DP','3':'USB_DM','4':'USB_DM','2':'GND','5':'VBUS'},
 'R20':{'1':'CC1','2':'GND'},'R21':{'1':'CC2','2':'GND'},
 'R7':{'1':'USB_DP','2':'USB_DP_MCU'},'R8':{'1':'USB_DM','2':'USB_DM_MCU'},
 'R3':{'1':'+3V3','2':'VREG_AVDD'},'C9':{'1':'VREG_AVDD','2':'GND'},
 'L1':{'1':'+1V1','2':'VREG_LX'},'C7':{'1':'+1V1','2':'GND'},'C10':{'1':'+1V1','2':'GND'},
 'X1':{'1':'XIN','2':'GND','3':'XTAL_OUT','4':'GND'},'R2':{'1':'XOUT','2':'XTAL_OUT'},
 'C3':{'1':'XIN','2':'GND'},'C4':{'1':'XTAL_OUT','2':'GND'},
 'R6':{'1':'QSPI_SS','2':'BOOT_SWITCH'},'SW61':{'1':'GND','2':'BOOT_SWITCH'},
 'SW62':{'1':'RUN_SWITCH','2':'RUN'},'R4':{'1':'RUN_SWITCH','2':'GND'},
 'J1':{'A1':'GND','A12':'GND','B1':'GND','B12':'GND','S1':'GND','A4':'VBUS','A9':'VBUS','B4':'VBUS','B9':'VBUS','A5':'CC1','B5':'CC2','A6':'USB_DP','B6':'USB_DP','A7':'USB_DM','B7':'USB_DM'},
 'J3':{'1':'SWCLK','2':'GND','3':'SWDIO'},'J2':{'1':'SWCLK','2':'GND','3':'SWDIO','MP':'GND'},'R22':{'1':'SWCLK_MCU','2':'SWCLK'},'R23':{'1':'SWDIO_MCU','2':'SWDIO'}}
for ref,pins in expected.items():
    for p,n in pins.items():assert by_pin[ref,p]==n,(ref,p,n)
for ref,v in {'C5':'4.7u','R22':'100','R23':'100','R20':'5.1k','R21':'5.1k','R7':'27','R8':'27','R3':'33','R4':'1k','R6':'1k','R2':'1k','C9':'4.7u','C7':'4.7u','C10':'4.7u','L1':'3.3uH','X1':'12MHz','C3':'15p','C4':'15p','C20':'100n'}.items():assert child(comps[ref],'value')[1]==v,(ref,v)
# Native reference U1 pad geometry is inspected as S-expression because original is KiCad 10.
def footprint(doc,ref):return next(f for f in children(doc,'footprint') if prop(f,'Reference') and prop(f,'Reference')[2]==ref)
def pad_geometry(f):
    at=child(f,'at');angle=float(at[3]) if len(at)>3 else 0
    rows=[]
    for p in children(f,'pad'):
        pa=child(p,'at');a=float(pa[3]) if len(pa)>3 else 0
        rows.append((p[1],(float(pa[1]),float(pa[2]),round((a-angle)%360,6)),tuple(map(float,child(p,'size')[1:])),p[2],p[3]))
    return sorted(rows)
now_pcb=parse((ROOT/'WING27.kicad_pcb').read_text());ref_pcb=parse((ROOT/'reference/RaspberryPi/RPI-RP2350A-MINIMAL_R4-S1.kicad_pcb').read_text())
assert pad_geometry(footprint(now_pcb,'U1'))==pad_geometry(footprint(ref_pcb,'U1'))
after={name:digest(ROOT/name) for name in inputs};assert before==after,'Source changed during audit; rerun once parent finishes editing'
result={
 'audit_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'status':'PASS: net topology and pin mapping only; not fabrication approval',
 'input_sha256':after,'component_count':len(comps),'physical_copper_pads_checked':pad_count,
 'pcb_pad_net_mismatches':pcb_issues,'model_net_mismatches':model_issues,
 'rp2354a_symbol_pins_checked':61,'rp2354a_official_package_pad_geometry_match':True,
 'matrix_unique_positions':60,'bav70_packages':30,'ideal_ghosting_patterns_passed':cases,
 'key_mapping':keys,'special_pairs':{d:[k for k in keys.values() if k['diode']==d] for d in ['D12','D18']},
 'track_count':len(list(B.GetTracks())),'zone_count':len(list(B.Zones())),
 'power_usb_boot_expected_pin_checks':'PASS',
 'assembly_values':{ref:child(c,'value')[1] for ref,c in comps.items()},
 'residual_risks':[
  'Only the official MCU core is routed. Remaining routing, USB signal integrity, power impedance, SMPS/XTAL hardware stability, ESD return paths and current capability remain unverified.',
  'Firmware must pull up columns, drive only selected ROW LOW, disable pulls and output drive on other rows, and allow settling/debounce. Physical row labels do not equal logical row for the two staggered pairs.',
  'Ideal diode graph tests do not verify analogue low-level margins over temperature, leakage, scan timing, or hardware NKRO.',
  'Confirm final capacitor voltage/DC-bias derating, actual supply load, regulator thermal margin and inrush before manufacturing.',
  'USB current descriptors/suspend and phone-host operation require firmware and two-orientation C-C cable testing.',
  'J2/J3 expose SWCLK/GND/SWDIO only, no VTREF or power pin. Expansion GPIO is 3.3V only.'
 ],
 'primary_sources':[
  'https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf',
  'https://pip-assets.raspberrypi.com/categories/1214-rp2350/documents/RP-008280-DS-2-hardware-design-with-rp2350.pdf',
  'https://www.jscj-elec.com/gallery/file/BAW56%20BAV70%20BAV99%20SOT-23%20V1.pdf',
  'https://www.st.com/resource/en/datasheet/usblc6-2.pdf',
  'https://product.torexsemi.com/system/files/series/xc6206.pdf',
  'https://gct.co/files/drawings/usb4105.pdf'
 ]}
(OUT/'audit_result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['key_mapping','assembly_values','residual_risks','primary_sources']},indent=2,ensure_ascii=False))

"""Generate accessible vector pipeline diagrams; no simulated data or imagery."""
from pathlib import Path
from html import escape
DIST=Path(__file__).resolve().parent/'dist'
STYLE='''<style>text{font-family:Arial,Helvetica,sans-serif;fill:#24292f}.small{font-size:13px;fill:#57606a}.label{font-size:16px;font-weight:600}.box{fill:#fff;stroke:#b9c5d0}.wire{fill:none;stroke:#8293a2;stroke-width:1.4}.blue{fill:#f2f6fa;stroke:#315e85;stroke-width:1.5}</style><defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L8 4L0 8Z" fill="#8293a2"/></marker></defs>'''
def text(x,y,label,cls='label',anchor='start'):
 return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{escape(label)}</text>'
def box(x,y,w,h,lines,blue=False):
 out=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" class="{"blue" if blue else "box"}"/>'
 offset=(h-(len(lines)-1)*17)/2+4
 for i,line in enumerate(lines):out+=text(x+w/2,y+offset+i*17,line,'label' if i==0 else 'small','middle')
 return out

def wire(d,arrow=True):return f'<path d="{d}" class="wire"'+(' marker-end="url(#arrow)"' if arrow else '')+'/>'
def shell(w,h,body):return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc"><title id="title">Neural signal pipeline: three controlled processing paths</title><desc id="desc">Shared synthetic source, analog low-pass, and ideal ADC branch to full-rate processing, a prefilter control with bandpass processing at the ADC rate, and multirate processing at one kilohertz. All paths produce causal mean-square features at one hundred hertz. Baseline notch is off.</desc>{STYLE}'+body+'</svg>\n'
body=text(20,23,'Shared acquisition','small')
body+=box(20,42,190,62,['Synthetic source','110 Hz AM + disturbances'])+box(260,42,260,62,['Analog low-pass','5th-order Butterworth · 80 kHz model'])+box(570,42,220,62,['Ideal 16-bit ADC','fADC = 1 / 2 / 4 kHz'])
body+=wire('M210 73H260')+wire('M520 73H570')+wire('M680 104V126H170V414',False)
rows=[(158,'A · Full rate','Process at fADC', [['Bandpass','70–150 Hz · fADC'],['Square','x²'],['Smoothing FIR','Pass 0–10 Hz'],['Downsample','to 100 Hz'],['Power feature','FS² · clamp at 0']]),
(270,'B · Prefilter control','Bandpass at fADC', [['Acquisition FIR','Anti-alias response'],['Bandpass','70–150 Hz · fADC'],['Square','x²'],['Smooth + reduce','to 100 Hz'],['Power feature','FS² · clamp at 0']]),
(382,'C · Multirate','Process at 1 kHz', [['Same FIR','as path B'],['Decimate','fADC → 1 kHz'],['Bandpass','70–150 Hz · 1 kHz'],['Square + smooth','reduce to 100 Hz'],['Power feature','FS² · clamp at 0']])]
for y,label,sub,nodes in rows:
 body+=text(20,y+27,label)+text(20,y+45,sub,'small')+wire(f'M170 {y+32}H210')
 for i,lines in enumerate(nodes):
  x=210+i*165;body+=box(x,y,145,64,lines,y==382)
  if i<4:body+=wire(f'M{x+145} {y+32}H{x+165}')
body+=text(20,480,'Same ADC samples across paths · causal persistent state · baseline notch off · alignment is an offline diagnostic','small')
(DIST/'pipeline-v3.svg').write_text(shell(1040,500,body))
body=text(20,20,'Shared acquisition','small')
for y,lines in [(34,['Synthetic source','110 Hz AM + disturbances']),(108,['Analog low-pass','5th order · 80 kHz model']),(182,['Ideal 16-bit ADC','fADC = 1 / 2 / 4 kHz'])]:
 body+=box(54,y,272,54,lines)
 if y<182:body+=wire(f'M190 {y+54}V{y+74}')
body+=wire('M190 236V252H20V690',False)
for y,label,nodes in [(274,'A · Full rate',[['Bandpass','at fADC'],['Square +','smooth'],['↓ 100 Hz','power FS²']]),(438,'B · Prefilter control',[['Acquisition','FIR'],['Bandpass','at fADC'],['x² · smooth','↓ 100 Hz']])]:
 body+=f'<rect x="42" y="{y}" width="326" height="128" rx="2" fill="#fff" stroke="#d8dee4"/>'+text(54,y+24,label)
 body+=wire(f'M20 {y+64}H42')
 for i,lines in enumerate(nodes):
  x=54+i*104;body+=box(x,y+44,94,58,lines)
  if i<2:body+=wire(f'M{x+94} {y+73}H{x+104}')
body+='<rect x="42" y="602" width="326" height="184" rx="2" class="blue"/>'+text(54,626,'C · Multirate · 1 kHz processing')+wire('M20 690H42')
for i,lines in enumerate([['Same FIR','as path B'],['Decimate','to 1 kHz'],['Bandpass','70–150 Hz']]):
 x=54+i*104;body+=box(x,642,94,54,lines)
 if i<2:body+=wire(f'M{x+94} 669H{x+104}')
body+=wire('M309 696V712')+box(54,712,302,54,['Square → smooth → reduce','100 Hz power feature · FS² · clamp at 0'])
body+=text(20,818,'Same ADC data · causal state · baseline notch off','small')+text(20,837,'Relative-delay alignment is an offline diagnostic.','small')
(DIST/'pipeline-v3-mobile.svg').write_text(shell(380,850,body).replace('.label{font-size:16px;', '.label{font-size:14px;').replace('.small{font-size:13px;', '.small{font-size:12px;'))
print('Wrote desktop and mobile SVG flowcharts')

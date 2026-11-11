"""Verify website data/links against immutable archives ."""
from pathlib import Path
from html.parser import HTMLParser
import csv,json,sys
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
import numpy as np
from scipy.interpolate import CubicSpline
SITE=Path(__file__).resolve().parent;ROOT=SITE.parents[1];DIST=SITE/'dist'
sys.path.insert(0,str(ROOT/'pipeline_v3'))
from evidence import verify
PILOT=ROOT/'results/current_pipeline';GUARDS=ROOT/'results/current_alignment_validation'
class Page(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.ids=[];self.titles=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if 'srcset' in a:self.links.extend(item.strip().split()[0] for item in a['srcset'].split(','))
        for key in ('href','src'):
            if key in a:self.links.append(a[key])


def main():
    if not __debug__:
        raise RuntimeError('Website evidence checks require Python without -O')
    verify(PILOT);verify(GUARDS)
    for filename in ('index.html','methods.html'):
        page=Page();page.feed((DIST/filename).read_text())
        assert len(page.ids)==len(set(page.ids)),filename
        for link in page.links:
            if link.startswith('#'):assert link[1:] in page.ids,link
            elif not link.startswith(('https:','http:','data:')):
                part=urlsplit(link);target=DIST/part.path
                assert target.is_file(),link
                if part.fragment:
                    linked=Page();linked.feed(target.read_text());assert part.fragment in linked.ids,link
    main_html=(DIST/'index.html').read_text()
    assert '<h1>End-to-End Neural Signal Chain Simulation</h1>' in main_html
    assert 'Can I process at 1 kHz and keep the power feature close' not in main_html
    assert '<p id="model-scope"><b>Model and scope:</b> I’m using' in main_html
    assert '<p id="motivation" class="body-copy"><b>Motivation:</b> Through the interview process' in main_html
    assert '<p id="approach"><b>Approach:</b>' in main_html
    assert main_html.index('id="motivation"')<main_html.index('id="approach"')<main_html.index('id="model-scope"')<main_html.index('class="result-note"')
    for filename in ('index.html','methods.html'):
        visible=Page();visible.feed((DIST/filename).read_text())
        assert not any('REPORT' in link or 'downloads/' in link for link in visible.links)
        assert 'Compact report' not in (DIST/filename).read_text()
    assert 'data-preset' not in main_html and 'id="preset-note"' not in main_html
    assert 'Download flowchart' not in main_html
    assert '<ol class="comparison-questions">' in main_html
    questions=main_html.split('<ol class="comparison-questions">',1)[1].split('</ol>',1)[0]
    assert questions.count('<li>')==3 and questions.count('<p>')==6
    assert '<button' not in questions and '<a ' not in questions
    for filename in ('pipeline-v3.svg','pipeline-v3-mobile.svg'):
        diagram=ET.parse(DIST/filename).getroot()
        ns={'s':'http://www.w3.org/2000/svg'}
        assert diagram.find('s:title',ns) is not None and diagram.find('s:desc',ns) is not None
        labels=' '.join(diagram.itertext())
        for required in ('A · Full rate','B · Prefilter control','C · Multirate','100 Hz'):
            assert required in labels,(filename,required)
    d=json.loads((DIST/'data/pipeline-v3.json').read_text());assert len(d['records'])==400
    expected={(fs,fm,seed,f'{fs}_{arch}') for fs in (1000,2000,4000) for fm in (2,5) for seed in range(1,21) for arch in ('full_rate','prefilter_full_rate','multirate')}
    expected|={(2000,fm,seed,'2000_multirate_notch') for fm in (2,5) for seed in range(1,21)}
    assert {(c['fs'],c['fm'],c['seed'],c['name']) for c in d['records']}==expected
    with (PILOT/'trials.csv').open() as f:trials={(r['name'],int(r['fm_hz']),int(r['seed'])):r for r in csv.DictReader(f)}
    calibration=json.loads((PILOT/'calibration.json').read_text())['phase'];dense_cache={}
    for c in d['records']:
        raw=trials[(c['name'],c['fm'],c['seed'])]
        for k,v in raw.items():assert c['trial'][k]==(v if k=='name' else float(v)),(c['name'],k)
        y=np.loadtxt(PILOT/'features'/f"{c['name']}_fm{c['fm']}_seed{c['seed']}.csv",delimiter=',',skiprows=1,ndmin=2)
        y=y[(y[:,0]>=6)&(y[:,0]<=7)]
        np.testing.assert_array_equal(c['plot']['t'],y[:,0]);np.testing.assert_array_equal(c['plot']['noisy'],y[:,3]);np.testing.assert_array_equal(c['plot']['clean'],y[:,5])
        key=(c['fs'],c['fm'],c['seed'])
        if key not in dense_cache:
            with np.load(PILOT/'dense_reference'/f'{key[0]}_fm{key[1]}_seed{key[2]}.npz') as z:dense_cache[key]=z['data']
        dense=dense_cache[key];base=next(r['delay_s'] for r in calibration[f"{c['fs']}_full_rate"] if r['frequency_hz']==c['fm'])
        lag=c['trial']['calibrated_delay_s']-base
        for label,column in (('noisy',2),('clean',4)):
            reference=CubicSpline(dense[:,0],dense[:,column],extrapolate=False)
            np.testing.assert_array_equal(c['plot']['full_'+label],reference(y[:,0]))
            np.testing.assert_array_equal(c['plot']['aligned_full_'+label],reference(y[:,0]-lag))
    from evidence import digest
    assert d['source_manifests']==dict(pilot=digest(PILOT/'manifest.json'),guards=digest(GUARDS/'manifest.json'))
    audit=json.loads((GUARDS/'noisy_alignment_audit.json').read_text())
    assert audit['passed'] and audit['input_manifest_sha256']==digest(PILOT/'manifest.json')
    print('PASS: page links, flowcharts, 400 exact trial records and chart windows, dense alignment, and archive binding')

if __name__=='__main__':main()

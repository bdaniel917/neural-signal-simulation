"""Export checked recorded results; never regenerate or modify scientific archives."""
from pathlib import Path
import csv,json,sys
import numpy as np
from scipy.interpolate import CubicSpline
ROOT=Path(__file__).resolve().parents[2]
SITE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'pipeline_v3'))
from evidence import verify,digest
PILOT=ROOT/'results/current_pipeline'
GUARDS=ROOT/'results/current_alignment_validation'
DIST=SITE/'dist'


def main():
    if not __debug__:
        raise RuntimeError('Website evidence checks require Python without -O')
    verify(PILOT)
    verify(GUARDS)
    guard_manifest=json.loads((GUARDS/'manifest.json').read_text())
    pilot_manifest=json.loads((PILOT/'manifest.json').read_text())
    assert pilot_manifest['source_sha256']==guard_manifest['source_sha256'], 'Pilot and audit source snapshots differ'
    for name,h in guard_manifest['source_sha256'].items():
        assert digest(ROOT/name)==h, f'Current implementation changed after validation: {name}'
    audit=json.loads((GUARDS/'noisy_alignment_audit.json').read_text())
    assert audit['passed'] and len(audit['cases'])==400
    assert audit['input_manifest_sha256']==digest(PILOT/'manifest.json'), 'Audit belongs to another pilot'
    filters=json.loads((PILOT/'filters.json').read_text())
    calibration=json.loads((PILOT/'calibration.json').read_text())
    summary=json.loads((PILOT/'summary.json').read_text())
    with (PILOT/'trials.csv').open() as f:raw=list(csv.DictReader(f))
    cases=[];cache={}
    for row in raw:
        fs,fm,seed=(int(row[k]) for k in ('fs','fm_hz','seed'))
        name=row['name'];key=(fs,fm,seed)
        if key not in cache:
            with np.load(PILOT/'dense_reference'/f'{fs}_fm{fm}_seed{seed}.npz') as z:cache[key]=z['data']
        dense=cache[key]
        y=np.loadtxt(PILOT/'features'/f'{name}_fm{fm}_seed{seed}.csv',delimiter=',',skiprows=1,ndmin=2)
        mask=(y[:,0]>=6)&(y[:,0]<=7)
        t=y[mask,0];lag=float(row['calibrated_delay_s'])
        base_lag=next(r['delay_s'] for r in calibration['phase'][f'{fs}_full_rate'] if r['frequency_hz']==fm)
        # Match the study's dense cubic method exactly; only the displayed window is reduced.
        for col in (2,4):
            ref=CubicSpline(dense[:,0],dense[:,col],extrapolate=False)
            if col==2:
                original=ref(t);shifted=ref(t-(lag-base_lag))
            else:
                clean_original=ref(t);clean_shifted=ref(t-(lag-base_lag))
        trial={k:(v if k=='name' else float(v)) for k,v in row.items()}
        trial.update(duration_s=20.,multiplications_per_s=float(row['multiplications'])/20,
                     acquisition_taps=len(filters['digital'][name]['acquisition']),
                     feature_taps=len(filters['digital'][name]['feature']),
                     bandpass_sections=len(filters['digital'][name]['bandpass']))
        cases.append(dict(fs=fs,fm=fm,seed=seed,name=name,trial=trial,
            plot=dict(t=t.tolist(),noisy=y[mask,3].tolist(),clean=y[mask,5].tolist(),
                      full_noisy=original.tolist(),full_clean=clean_original.tolist(),
                      aligned_full_noisy=shifted.tolist(),aligned_full_clean=clean_shifted.tolist())))
    audit=json.loads((GUARDS/'noisy_alignment_audit.json').read_text())
    maxima={k:max(r[k] for r in audit['cases']) for k in ('held_out_half_rate_nrmse','cubic_vs_sinc128_nrmse','sinc64_vs_sinc128_nrmse','paired_nrmse_change')}
    nominal=[c for c in cases if c['name'] in ('2000_multirate','4000_multirate')]
    payload=dict(schema=3,scope='Recorded double-precision single-channel pilot; no browser simulation.',
        source_manifests=dict(pilot=digest(PILOT/'manifest.json'),guards=digest(GUARDS/'manifest.json')),
        records=cases,summary=summary,calibration=calibration,filters=filters,audit_maxima=maxima,
        source_checks=json.loads((GUARDS/'source_validation.json').read_text()),
        targeted=json.loads((GUARDS/'targeted_validation.json').read_text()),
        headline=dict(clean_max=max(c['trial']['clean_paired_aligned_nrmse'] for c in nominal),
                      noisy_max=max(c['trial']['paired_aligned_nrmse'] for c in nominal),
                      delay_min_s=min(c['trial']['calibrated_delay_s'] for c in nominal),
                      delay_max_s=max(c['trial']['calibrated_delay_s'] for c in nominal)))
    (DIST/'data').mkdir(exist_ok=True)
    (DIST/'data'/'pipeline-v3.json').write_text(json.dumps(payload,separators=(',',':'),allow_nan=False))
    print(f'Exported {len(cases)} measured cases from the current verified archives.')

if __name__=='__main__':main()

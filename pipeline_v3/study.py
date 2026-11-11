#!/usr/bin/env python3
"""Design, validate, and compare causal double-precision neural feature pipelines."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
import uuid
from scipy.interpolate import CubicSpline
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np
from scipy import signal
import scipy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build import compiler_command
HERE = Path(__file__).resolve().parent
BIN = HERE
ARCHES = ('full_rate', 'prefilter_full_rate', 'multirate')


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def build(bin_dir=None):
    target = Path(bin_dir) if bin_dir else HERE
    target.mkdir(parents=True, exist_ok=True)
    command = compiler_command() + ['-ffp-contract=off', '-Wno-unused-function']
    for name in ('runner', 'stimulus'):
        subprocess.run(command + [str(HERE / (name + '.c')), '-lm', '-o', str(target / name)], check=True)
    return command


def analog(internal=80000):
    order, corner = signal.buttord(150*2*np.pi, 500*2*np.pi, .25, 40, analog=True)
    z, p, k = signal.butter(order, corner, analog=True, output='zpk')
    zd, pd, kd = signal.bilinear_zpk(z, p, k, fs=internal)
    return signal.zpk2sos(zd, pd, kd), int(order), float(corner / (2*np.pi))


def fir(fs, passedge, stopedge):
    length, beta = signal.kaiserord(70, (stopedge-passedge)/(fs/2))
    length += (length % 2 == 0)
    while True:
        taps = signal.firwin(length, (passedge+stopedge)/2, window=('kaiser', beta), fs=fs)
        check = response(taps, fs, (0, passedge), (stopedge, fs/2), False)
        if check['pass_max_abs_db'] <= .1 and check['stop_attenuation_db'] >= 60:
            return taps
        length += 2
        if length > 2049:
            raise RuntimeError('FIR exceeds configured tap capacity')


def response(coeff, fs, passband, stopband, sos=True):
    f = np.unique(np.r_[np.linspace(0, fs/2, 65537), passband, stopband])
    _, h = signal.sosfreqz(coeff, worN=f, fs=fs) if sos else signal.freqz(coeff, worN=f, fs=fs)
    db = 20*np.log10(np.maximum(abs(h), 1e-300))
    pa = (f >= passband[0]) & (f <= passband[1])
    if passband[0] > 0:
        st = (f <= stopband[0]) | (f >= stopband[1])
    else:
        st = f >= stopband[0]
    return dict(pass_max_abs_db=float(np.max(abs(db[pa]))), stop_attenuation_db=float(-np.max(db[st])))


def design(fs, arch, notch=False):
    factor = fs//1000 if arch == 'multirate' else 1
    processing = fs//factor
    acquisition = fir(fs, 200, 450) if fs > 1000 and arch != 'full_rate' else np.ones(1)
    bp = signal.iirdesign([70, 150], [40, 200], 1, 40, fs=processing, ftype='butter', output='sos')
    ns = signal.tf2sos(*signal.iirnotch(60, 25, fs=processing)) if notch else np.empty((0,6))
    feature = fir(processing, 10, 40)
    return dict(fs=fs, arch=arch, processing_fs=processing, acquisition_factor=factor,
                feature_factor=processing//100, warmup=4. if notch else 2., acquisition=acquisition,
                bandpass=bp, notch=ns, feature=feature)


def bank_text(bank):
    return str(len(bank)) + '\n' + ''.join(' '.join(format(float(x), '.17g') for x in row)+'\n' for row in bank)


def taps_text(taps):
    return str(len(taps))+'\n'+' '.join(format(float(x), '.17g') for x in taps)+'\n'


def write_config(path, cfg):
    path.write_text(f"V3\n{cfg['fs']} {cfg['acquisition_factor']} {cfg['feature_factor']} {cfg['warmup']}\n" +
                    taps_text(cfg['acquisition']) + bank_text(cfg['bandpass']) + bank_text(cfg['notch']) + taps_text(cfg['feature']))


def source(path, duration=20, fm=2, seed=1, internal=80000, clean=False, mode=0, density=.0002, line=.12, oob=.1, oob_hz=1350, amplitude=.2):
    sos, _, _ = analog(internal)
    config = path.with_suffix('.source')
    config.write_text(f'{internal} 4000 {duration} 1 {amplitude} 110 {fm} {.05 if clean else .25} {0 if clean else density} {0 if clean else line} 60 {0 if clean else oob} {oob_hz} {seed} {mode}\n'+bank_text(sos))
    subprocess.run([str(BIN/'stimulus'), str(config), str(path)], check=True)
    return np.loadtxt(path, delimiter=',', skiprows=1, ndmin=2)


HEADER = 't_s,neural_fs,clean_analog_fs,analog_fs,adc_fs,ideal_power_fs2,adc_clip,noise_analog_fs,line_analog_fs,oob_analog_fs'


def write_input(path, data):
    np.savetxt(path, data, delimiter=',', header=HEADER, comments='', fmt='%.17g')


def run(config, inp, out, block, wave=None, dense=None):
    cmd = [str(BIN/'runner'), str(config), str(inp), str(out), str(block)]
    if wave is not None or dense is not None:
        cmd.append(str(wave) if wave is not None else "-")
    if dense is not None:
        cmd.append(str(dense))
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return np.loadtxt(out, delimiter=',', skiprows=1, ndmin=2), json.loads(result.stderr)


def reference(data, cfg, column=4):
    x = data[:,column]
    x = signal.lfilter(cfg['acquisition'], [1], x)[::cfg['acquisition_factor']]
    x = signal.sosfilt(cfg['bandpass'], x)
    if len(cfg['notch']):
        x = signal.sosfilt(cfg['notch'], x)
    power = signal.lfilter(cfg['feature'], [1], x*x)[::cfg['feature_factor']]
    return x, power


def harmonic(t, y, fm):
    w = 2*np.pi*fm*t
    fit = np.linalg.lstsq(np.column_stack((np.ones(len(t)), np.cos(w), np.sin(w), np.cos(2*w), np.sin(2*w))), y, rcond=None)[0]
    return np.arctan2(-fit[2], fit[1]), float(fit[0])


def nrmse(a, b):
    return float(np.sqrt(np.mean((a-b)**2))/np.sqrt(np.mean(b*b)))


def validate(configs, config_paths, work):
    checks = []
    rng = np.random.default_rng(42)
    data = np.zeros((8000,10)); data[:,0] = np.arange(len(data))/4000
    data[:,4] = rng.normal(0,.1,len(data)); data[:,2] = .2
    data[0,2] = 1
    for name, cfg in configs.items():
        d = data[::4000//cfg['fs']].copy()
        inp = work/'validate_input.csv'; write_input(inp,d)
        out, _ = run(config_paths[name],inp,work/'validate.csv',max(1,cfg['fs']//125),work/'wave.csv')
        wave = np.loadtxt(work/'wave.csv',delimiter=',',skiprows=1,ndmin=2)
        x,p = reference(d,cfg); xc,pc = reference(d,cfg,2)
        error = max(float(np.max(abs(wave[:,1]-x))),float(np.max(abs(wave[:,2]-xc))),float(np.max(abs(out[:,2]-p))),float(np.max(abs(out[:,4]-pc))))
        assert error < 2e-11, (name,error)
        np.testing.assert_allclose(out[:,0],np.arange(len(out))/100,atol=1e-12,rtol=0)
        for block in (1,7,63,128):
            other,_ = run(config_paths[name],inp,work/'block.csv',block)
            np.testing.assert_array_equal(other[:,[0,2,3,4,5,6,7,8,9]],out[:,[0,2,3,4,5,6,7,8,9]])
            assert np.all(other[:,1] >= other[:,0])
            assert np.max(other[:,1]-other[:,0]) <= (block-1)/cfg['fs']+1e-12
        checks.append(dict(name=name,c_vs_scipy_max_abs_error=error,block_sizes=[1,7,63,128],passed=True))
    # At 1 kHz all three paths must be identical, including their coefficients.
    a=configs['1000_full_rate']
    for arch in ARCHES[1:]:
        b=configs['1000_'+arch]
        for key in ('acquisition','bandpass','feature'):
            np.testing.assert_array_equal(a[key],b[key])
    return checks


def align_dense(dense, query, column):
    """Offline diagnostic only; no extrapolation or per-trial lag/gain fitting."""
    query=np.asarray(query)
    if np.any(query<dense[0,0]) or np.any(query>dense[-1,0]):
        raise ValueError('Alignment requested outside reference timestamps')
    result=CubicSpline(dense[:,0],dense[:,column],extrapolate=False)(query)
    if not np.all(np.isfinite(result)):
        raise ValueError('Nonfinite aligned reference')
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trials',type=int,default=20)
    ap.add_argument('--duration',type=float,default=20)
    ap.add_argument('--output',type=Path,default=None)
    ap.add_argument('--validate-only',action='store_true')
    ap.add_argument('--alignment-archive',type=Path,help='Read-only noisy alignment audit of a completed pilot; validation-only mode')
    args=ap.parse_args()
    if not __debug__:
        ap.error('Validation requires Python without -O; numerical assertions must remain enabled.')
    if args.alignment_archive and not args.validate_only:
        ap.error('--alignment-archive requires --validate-only')
    if args.trials<1 or args.duration<15:
        ap.error('Use at least one trial and 15 seconds (at least ten valid seconds after the longest warmup).')
    global BIN
    out=(args.output.resolve() if args.output else ROOT/'results_v3_runs'/
         (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]))
    if out.exists():
        ap.error('Output directory already exists. Choose a new directory; archives are never reused.')
    out.mkdir(parents=True)
    from evidence import begin, finish
    provenance=begin(out, args)
    BIN=out/'bin'

    coeffdir=out/'coefficients';coeffdir.mkdir(exist_ok=True)
    compiler=build(BIN)
    configs={f'{fs}_{arch}':design(fs,arch) for fs in (1000,2000,4000) for arch in ARCHES}
    configs['2000_multirate_notch']=design(2000,'multirate',True)
    paths={};designs={}
    for name,cfg in configs.items():
        paths[name]=coeffdir/(name+'.txt');write_config(paths[name],cfg)
        bp=response(cfg['bandpass'],cfg['processing_fs'],(70,150),(40,200))
        ft=response(cfg['feature'],cfg['processing_fs'],(0,10),(40,cfg['processing_fs']/2),False)
        ac=response(cfg['acquisition'],cfg['fs'],(0,200),(450,cfg['fs']/2),False) if len(cfg['acquisition'])>1 else None
        assert bp['pass_max_abs_db']<=1.000001 and bp['stop_attenuation_db']>=39.99999
        assert ft['pass_max_abs_db']<=.1 and ft['stop_attenuation_db']>=60
        poles=signal.sos2zpk(np.vstack((cfg['bandpass'],cfg['notch'])))[1]
        settling=float(np.log(1e-9)/np.log(max(abs(poles)))/cfg['processing_fs'])
        support=(len(cfg['acquisition'])-1)/cfg['fs']+(len(cfg['feature'])-1)/cfg['processing_fs']
        assert settling+support<cfg['warmup'], (name,settling,support)
        designs[name]={k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in cfg.items()}
        designs[name].update(bandpass_response=bp,feature_response=ft,acquisition_response=ac,
                            pole_decay_to_1e9_s=settling,fir_support_s=support,
                            acquisition_delay_s=(len(cfg['acquisition'])-1)/(2*cfg['fs']),feature_delay_s=(len(cfg['feature'])-1)/(2*cfg['processing_fs']))
    sos,order,corner=analog()
    _,hh=signal.sosfreqz(sos,worN=[150,500],fs=80000)
    analog_info=dict(order=order,corner_hz=corner,internal_rate_hz=80000,
        continuous_spec=dict(pass_loss_db=.25,stop_attenuation_db=40),
        realized_edge_loss_db=(-20*np.log10(abs(hh))).tolist(),discretization_tolerance_db=.001,
        noise_enbw_hz=corner*np.pi/(2*order)/np.sin(np.pi/(2*order)),sos=sos.tolist())
    assert analog_info['realized_edge_loss_db'][0]<=.251 and analog_info['realized_edge_loss_db'][1]>=39.999
    save_json(out/'filters.json',dict(analog=analog_info,digital=designs))
    with tempfile.TemporaryDirectory(prefix='v3_') as temp:
        work=Path(temp)
        checks=validate(configs,paths,work)
        save_json(out/'validation.json',checks)
        print(f'Validated {len(checks)} configurations against SciPy and across block boundaries.',flush=True)
        archive_tests=subprocess.run([sys.executable,str(HERE/'test_evidence.py')],check=True,capture_output=True,text=True)
        save_json(out/'archive_validation.json',dict(passed=True,stdout=archive_tests.stdout,stderr=archive_tests.stderr))
        interpolation_tests=subprocess.run([sys.executable,str(HERE/'test_alignment.py')],check=True,capture_output=True,text=True)
        save_json(out/'interpolation_unit_tests.json',dict(passed=True,stdout=interpolation_tests.stdout,stderr=interpolation_tests.stderr))
        from validate_source import run_checks
        save_json(out/'source_validation.json',run_checks(source, BIN))
        from targeted_checks import run_targeted
        save_json(out/'targeted_validation.json',run_targeted(work,configs,paths,sys.modules[__name__],out))
        if args.alignment_archive:
            from alignment_checks import audit_archive
            audit=audit_archive(args.alignment_archive)
            save_json(out/'noisy_alignment_audit.json',audit)
            if not audit['passed']:
                raise RuntimeError('Noisy alignment sensitivity exceeded its declared thresholds; inspect noisy_alignment_audit.json')
        if args.validate_only:
            from alignment_checks import validation_report
            validation_report(out)
            finish(out,provenance,compiler,mode='validation_only')
            print(f'Complete validation archive: {out}',flush=True)
            return
        # Independent clean, small-modulation calibration, before any noisy trial.
        frequencies=np.r_[.5,np.arange(1,11)]
        calibration_dir=out/'calibration_traces';calibration_dir.mkdir()
        calibration={name:[] for name in configs}
        onset={}
        for fm in frequencies:
            data=source(work/'source.csv',duration=args.duration,fm=float(fm),clean=True)
            for fs in (1000,2000,4000):
                inp=work/f'input{fs}.csv';write_input(inp,data[::4000//fs])
                for name,cfg in configs.items():
                    if cfg['fs']!=fs:continue
                    y,_=run(paths[name],inp,calibration_dir/f'{name}_fm{fm:g}.csv',fs//125)
                    valid=y[:,0]>=cfg['warmup']
                    phase,mean=harmonic(y[valid,0],y[valid,5],fm)
                    calibration[name].append(dict(frequency_hz=float(fm),phase_rad=float(phase),mean_power_fs2=mean))
            print(f'Calibration {fm:g} Hz complete.',flush=True)
        lags={}
        for name,rows in calibration.items():
            phase=np.unwrap([r['phase_rad'] for r in rows])
            for r,p in zip(rows,phase):r['delay_s']=float(-p/(2*np.pi*r['frequency_hz']))
            lags[name]={int(fm):rows[list(frequencies).index(fm)]['delay_s'] for fm in (2,5)}
        data=source(work/'source.csv',duration=12,clean=True,mode=1)
        for fs in (1000,2000,4000):
            inp=work/'input.csv';write_input(inp,data[::4000//fs])
            for name,cfg in configs.items():
                if cfg['fs']!=fs:continue
                y,_=run(paths[name],inp,calibration_dir/f'{name}_onset.csv',fs//125)
                steady=float(np.mean(y[y[:,0]>8,5])); onset[name]={}
                for fraction in (.1,.5,.9):
                    hit=np.flatnonzero((y[:,0]>=3)&(y[:,5]>=fraction*steady))
                    onset[name][f'T{int(fraction*100)}_s']=float(y[hit[0],0]-3)
        save_json(out/'calibration.json',dict(method='Independent depth=0.05 clean modulation; unwrapped phase over 0.5,1,...,10 Hz. Fixed before noisy trials. Onset uses a carrier switched on at 3 s.',phase=calibration,onset=onset))
        trials=[];example={}
        featuresdir=out/'features';featuresdir.mkdir()
        dense_dir=out/'dense_reference';dense_dir.mkdir()
        input_hashes=[]
        for fm in (2,5):
            for seed in range(1,args.trials+1):
                data=source(work/'source.csv',duration=args.duration,fm=fm,seed=seed)
                for fs in (1000,2000,4000):
                    inp=work/'input.csv';write_input(inp,data[::4000//fs])
                    input_hashes.append(dict(fs=fs,fm_hz=fm,seed=seed,sha256=hashlib.sha256(inp.read_bytes()).hexdigest()))
                    group={};stats={}
                    for name,cfg in configs.items():
                        if cfg['fs']!=fs:continue
                        featurepath=featuresdir/f'{name}_fm{fm}_seed{seed}.csv'
                        wave=out/f'{name}_waveform.csv' if seed==1 and fm==2 and fs==2000 else None
                        densepath=work/'dense.csv' if cfg['arch']=='full_rate' and not len(cfg['notch']) else None
                        y,count=run(paths[name],inp,featurepath,fs//125,wave,densepath)
                        if densepath is not None:
                            densebase=np.loadtxt(densepath,delimiter=',',skiprows=1,ndmin=2)
                            np.savez_compressed(dense_dir/f'{fs}_fm{fm}_seed{seed}.npz',data=densebase)
                        group[name]=y;stats[name]=count
                    base=group[f'{fs}_full_rate']
                    for name,y in group.items():
                        t=y[:,0];lag=lags[name][fm];valid=(t>=configs[name]['warmup']+max(lag,.3))&(t<args.duration-.3)
                        ideal=.2**2/2*(1+.25*np.cos(2*np.pi*fm*(t[valid]-lag)))**2
                        relative=lag-lags[f'{fs}_full_rate'][fm]
                        shifted=align_dense(densebase,t[valid]-relative,2)
                        clean_shifted=align_dense(densebase,t[valid]-relative,4)
                        old_shifted=np.interp(t[valid]-relative,base[:,0],base[:,3])
                        _,clean_mean=harmonic(t[valid],y[valid,5],fm);oracle_mean=.2**2/2*(1+.25**2/2)
                        row=dict(name=name,fs=fs,fm_hz=fm,seed=seed,valid_features=int(sum(valid)),
                            clean_mean_bias_fraction=float(clean_mean/oracle_mean-1),
                            oracle_unaligned_nrmse=nrmse(y[valid,3],y[valid,6]),
                            oracle_aligned_nrmse=nrmse(y[valid,3],ideal),
                            clean_oracle_aligned_nrmse=nrmse(y[valid,5],ideal),
                            paired_aligned_nrmse=nrmse(y[valid,3],shifted),
                            clean_paired_aligned_nrmse=nrmse(y[valid,5],clean_shifted),
                            legacy_linear_paired_nrmse=nrmse(y[valid,3],old_shifted),
                            clean_paired_unaligned_nrmse=nrmse(y[valid,5],base[valid,5]),
                            paired_unaligned_nrmse=nrmse(y[valid,3],base[valid,3]),
                            contamination_and_quantization_nrmse=nrmse(y[valid,3],y[valid,5]),
                            calibrated_delay_s=lag,clamps=int(sum(y[valid,8])),**stats[name])
                        trials.append(row)
                        if seed==1 and fm==2:example[name]=y
                print(f'Trial fm={fm}, seed={seed}/{args.trials} complete.',flush=True)
        with (out/'trials.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(trials[0]));w.writeheader();w.writerows(trials)
        summary={}
        for name in configs:
            summary[name]={}
            for fm in (2,5):
                rows=[r for r in trials if r['name']==name and r['fm_hz']==fm]
                fields=('clean_mean_bias_fraction','paired_aligned_nrmse','paired_unaligned_nrmse','clean_paired_unaligned_nrmse','clean_paired_aligned_nrmse','legacy_linear_paired_nrmse','oracle_aligned_nrmse','contamination_and_quantization_nrmse','calibrated_delay_s')
                summary[name][str(fm)]={k:dict(mean=float(np.mean([r[k] for r in rows])),min=float(min(r[k] for r in rows)),max=float(max(r[k] for r in rows))) for k in fields}
        save_json(out/'summary.json',summary)
        save_json(out/'input_hashes.json',input_hashes)
        # Common-clock convergence: same deterministic source; noise RMS compared statistically, not pointwise.
        convergence=[]
        for rate in (40000,80000,160000):
            d=source(work/'convergence.csv',duration=12,internal=rate)
            valid=d[:,0]>=2
            convergence.append(dict(internal_fs=rate,clean_rms=float(np.sqrt(np.mean(d[valid,2]**2))),noise_rms=float(np.std(d[valid,7])),line_rms=float(np.std(d[valid,8])),oob_rms=float(np.std(d[valid,9]))))
        save_json(out/'source_convergence.json',convergence)
        plot(out,example,calibration)
        report(out,configs,summary,trials,analog_info,checks,convergence)
    finish(out,provenance,compiler,mode='pilot')
    print(f'Results: {out}',flush=True)


def plot(out,example,calibration):
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.mplconfig'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(10,7),constrained_layout=True)
    for arch in ARCHES:
        name='2000_'+arch;y=example[name];mask=(y[:,0]>=3)&(y[:,0]<=4)
        axes[0].plot(y[mask,0],y[mask,3],label=arch)
        rows=calibration[name];axes[1].plot([r['frequency_hz'] for r in rows],1000*np.array([r['delay_s'] for r in rows]),'o-',label=arch)
    axes[0].set(xlabel='Original feature timestamp (s)',ylabel='Smoothed mean-square (FS²)',title='Same ADC input; causal outputs before diagnostic alignment')
    axes[1].set(xlabel='Envelope modulation frequency (Hz)',ylabel='Phase delay (ms)',title='Independent clean calibration; not processing time')
    for a in axes:a.grid(alpha=.25);a.legend()
    fig.savefig(out/'comparison.png',dpi=160);plt.close(fig)


def report(out,configs,summary,trials,analog_info,checks,convergence):
    lines=['# Double-precision rate comparison','',
    '## Scope','',f"This is a {len(set(r['seed'] for r in trials))}-seed pilot per modulation frequency, not the planned 100-seed formal study. The source is a synthetic 110 Hz AM carrier at 2 and 5 Hz. Every architecture at a given ADC rate receives exactly the same 16-bit ADC samples. No real neural data, hardware timing, or physiological utility is validated.",'',
    'A: full-rate bandpass and feature extraction. B: acquisition anti-alias FIR with bandpass processing at the ADC rate. C: the same FIR followed by reduction to 1 kHz. All output features at 100 Hz, epoch phase zero. Comparing A/B isolates acquisition-filter effects; B/C adds rate reduction and redesigned downstream filters. Baseline notch is off. The additional 2 kHz multirate notch case is conditional evidence, not a new default.','',
    '## Implementation checks','',f"All {len(checks)} configurations pass C versus independent SciPy causal references (waveform, raw square-and-smooth output, and clean reference), timestamp checks, and block-size invariance at 1, 7, 63, and 128 samples. The three 1 kHz configurations have identical coefficients. No internal state resets occur at block boundaries.",'',
    'All digital pass/stop responses meet the specified sampled-grid checks including exact edges. The analog model is a fifth-order continuous Butterworth approximated by bilinear transformation at 80 kHz. Its realized 150 Hz loss is '+f"{analog_info['realized_edge_loss_db'][0]:.6f} dB; the 0.000028 dB difference from the continuous 0.25 dB limit is documented discretization error (0.001 dB tolerance). The 500 Hz attenuation is {analog_info['realized_edge_loss_db'][1]:.4f} dB.",'',
    'The 2 s baseline exclusion (4 s for the optional notch) exceeds the sum of a conservative 1e-9 pole-decay estimate and complete FIR support in every configuration. This estimate is supplemented by the independent onset trace. Raw FIR power can be negative during transients; raw and clamped outputs and clamp flags are retained.','',
    '## Measured results','',
    'NRMSE is RMS error divided by RMS reference. Paired error uses cubic-spline interpolation of C diagnostic power at the full processing rate (1/2/4 kHz), rather than linear interpolation of the 100 Hz stream. Dense diagnostics read state without changing the deployed path or its arithmetic counters. The alignment method passes known-delay and dense C/SciPy checks saved in targeted_validation.json. Paired error uses a fixed relative delay from an independent depth=0.05 clean modulation calibration; it does not refit delay or gain for each noisy trial. Unaligned errors remain in trials.csv. Diagnostic alignment is offline and adds no proposed processing stage. Mean bias below uses a DC-plus-two-harmonic fit to the clean output to avoid partial-cycle averaging bias; oracle includes analog and digital attenuation as error.','',
    '| ADC Hz / architecture | fm Hz | Clean mean bias % | Clean paired NRMSE %, max | Noisy paired NRMSE %, mean / max | Oracle aligned NRMSE % | Phase delay ms | Multiplications/s |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for name in configs:
        for fm in (2,5):
            s=summary[name][str(fm)];r=next(r for r in trials if r['name']==name and r['fm_hz']==fm)
            lines.append(f"| {name} | {fm} | {100*s['clean_mean_bias_fraction']['mean']:.3f} | {100*s['clean_paired_aligned_nrmse']['max']:.3f} | {100*s['paired_aligned_nrmse']['mean']:.3f} / {100*s['paired_aligned_nrmse']['max']:.3f} | {100*s['oracle_aligned_nrmse']['mean']:.3f} | {1000*r['calibrated_delay_s']:.2f} | {r['multiplications']/(r['input_samples']/r['fs']):.0f} |")
    lines+=['','## Effect of the review corrections','',
        'The clean-path 2% screen now uses clean outputs from both architectures. Noisy preservation error is reported separately. The old 100 Hz linear-alignment calculation is retained as legacy_linear_paired_nrmse on exactly the same current noisy samples and validity windows; this is an evaluation-method comparison, not a change in deployed DSP.','',
        '| Multirate ADC Hz | fm Hz | Clean paired NRMSE % | Noisy NRMSE %, old linear / corrected dense |','|---:|---:|---:|---:|']
    for fs in (2000,4000):
        for fm in (2,5):
            values=summary[f'{fs}_multirate'][str(fm)]
            lines.append(f"| {fs} | {fm} | {100*values['clean_paired_aligned_nrmse']['max']:.4f} | {100*values['legacy_linear_paired_nrmse']['mean']:.4f} / {100*values['paired_aligned_nrmse']['mean']:.4f} |")
    targeted=json.loads((out/'targeted_validation.json').read_text())
    alignment=max(r['dense_cubic_nrmse'] for r in targeted['known_pure_delay_alignment']['cases'])
    rejection=min(r['measured_rejection_db'] for r in targeted['digital_decimator_aliasing']['cases'])
    lines+=['',f'Known pure-delay AM-power checks (2, 5, 10 Hz modulation, including second harmonics through 20 Hz) have a maximum dense-alignment NRMSE of {100*alignment:.7f}%. This is an error-floor check for smooth signals, not a universal bound for arbitrary transients.',
        '',f'Stage-isolated digital tones folding into 110 Hz show at least {rejection:.2f} dB rejection from the acquisition FIR and agree with its predicted response. Separate physical-tone cases demonstrate ADC aliasing after analog attenuation; residuals can fall below the 16-bit quantization step. These selected-tone checks do not establish worst-case broadband alias performance.',
        '', 'The one-seed component-isolation study separates noise, interference, and the quantization increment. Their errors are not additive after squaring. The main contamination_and_quantization_nrmse field deliberately includes all these contributions.','',
        '| Isolated case | Error against desired-only % | Quantization increment % |','|---|---:|---:|']
    for row in targeted['component_isolation']['cases']:
        lines.append(f"| {row['case']} | {100*row['against_desired_only_nrmse']:.5f} | {100*row['quantization_increment_nrmse']:.5f} |")
    lines+=['','## Provisional screens','']
    nominal=[r for r in trials if 'notch' not in r['name']]
    screens={'Clean mean bias ≤10%':all(abs(r['clean_mean_bias_fraction'])<=.1 for r in nominal),
             'Multirate clean paired aligned NRMSE ≤2% at nominal carrier':all(r['clean_paired_aligned_nrmse']<=.02 for r in nominal if r['name'].endswith('multirate')),
             'Small-modulation delay ≤200 ms at 2/5 Hz':all(r['calibrated_delay_s']<=.2 for r in nominal),
             'No nominal ADC clipping':all(r['adc_clips']==0 for r in nominal)}
    for label,ok in screens.items():lines.append(f"- {'PASS' if ok else 'FAIL'}: {label}.")
    lines+=['','These are project-level screens on synthetic cases, not device requirements. Passing does not establish performance at band edges, across electrode impedances, or on neural recordings. A failing screen is retained as a result.','',
    '## Source and noise checks','',
    f"The one-sided white-noise density is 0.0002 FS/√Hz before the analog filter. Continuous-filter equivalent noise bandwidth is {analog_info['noise_enbw_hz']:.3f} Hz, giving predicted RMS {(.0002*np.sqrt(analog_info['noise_enbw_hz'])):.6f} FS. The finite internal Nyquist bandwidth and bilinear approximation are explicit. The 40/80/160 kHz convergence run uses the same deterministic signals; same-seed realizations mapped to different time grids are compared by RMS rather than sample differences.",'',
    '| Internal Hz | Clean RMS FS | Noise RMS FS | 60 Hz RMS FS | 1350 Hz RMS FS |','|---:|---:|---:|---:|---:|']
    for r in convergence:lines.append('| '+ ' | '.join(str(r[k]) if k=='internal_fs' else f'{r[k]:.7g}' for k in ('internal_fs','clean_rms','noise_rms','line_rms','oob_rms'))+' |')
    lines+=['','## Interpretation and remaining work','',
    'Power is the causal, smoothed square of the bandpassed waveform in FS². It includes passed noise and interference, and it is not an exact rectangular 70–150 Hz PSD integral or neural-only power. The analytic AM oracle is used alongside a clean architecture-matched reference so those effects remain distinguishable.','',
    'Operation totals count the deployed noisy path only: five multiplies/four adds per SOS; one multiply per square; one multiply and accumulator add per FIR tap, including the initial add to zero. FIR convolution is evaluated only on retained outputs, while state consumes every input. These counts omit loop, modulo, I/O, memory, clipping, and control overhead. They are not CPU cycles or measured execution-time claims.','',
    'Input block availability is recorded separately from original feature timestamps; CPU, transport, scheduler, buffer overflow, and actual memory limits are not modeled. Phase delay and onset T10/T50/T90 are different quantities, both saved in calibration.json.','',
    'Remaining scope: referencing and bad channels; carrier/band-edge and transient stress cases; isolated 60 Hz feature-error/notch decision; full noise statistics and confidence intervals; actual float32/Q15/Q31 kernels and range/scaling checks; target timing and buffer/memory measurements. The notch comparison here includes noise and OOB interference, so it cannot alone justify notch selection.','',
    'Source and ADC validation and targeted alignment/aliasing/component-isolation checks run inside this archive. Their inputs and measured outputs are summarized in source_validation.json and targeted_validation.json. Source convergence here is a diagnostic table, not a statistical hypothesis test. The pilot reports seed-level means and observed maxima, not population tail guarantees. The 80 kHz noise source is band-limited by its clock and the specified analog filter; an electrode/amplifier model, colored noise, motion artifacts, and empirical interference statistics remain simplified.','',
    '## Reproduce','',
    'From the project directory: `.venv/bin/python pipeline_v3/study.py --trials 20`. For implementation checks alone: `make validate-v3` (includes independent source/ADC checks). Every invocation creates a fresh archive; existing output directories are rejected. A completion manifest hashes every artifact and snapshots the reviewed sources. Verify it with `.venv/bin/python pipeline_v3/evidence.py RUN_DIRECTORY`. Numerical agreement is intended; cross-machine bitwise identity is not promised. Exact coefficient files, source hashes, dependency versions, calibration, per-trial feature traces, and trial metrics accompany this report. This command does not modify earlier archives or publish website changes.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()

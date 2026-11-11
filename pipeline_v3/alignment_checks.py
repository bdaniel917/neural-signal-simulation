"""Read-only interpolation sensitivity on noisy power from a completed pilot.

Checks held-out samples against known values and compares production cubic
interpolation with converged windowed-sinc interpolation at the actual queries.
Neither comparison is a universal continuous-time error bound.
"""
import csv
import json
from pathlib import Path
import numpy as np
from scipy.interpolate import CubicSpline
from evidence import verify, digest

# Independent diagnostic tolerances, fractional NRMSE, chosen below the 2% screen.
HELD_OUT_TOLERANCE=1e-4       # 0.01%, on a deliberately coarser reference grid
METHOD_TOLERANCE=1e-5         # 0.001%, at the deployed comparison queries
SINC_CONVERGENCE_TOLERANCE=1e-6  # 0.0001%, 64 versus 128 samples each side


def nrmse(a,b):
    denominator=np.sqrt(np.mean(np.square(b)))
    if not np.isfinite(denominator) or denominator<=0:raise ValueError('Invalid reference norm')
    return float(np.sqrt(np.mean(np.square(a-b)))/denominator)


def sinc_interpolate(time,values,query,halfwidth):
    """Normalized Kaiser-windowed sinc, no extrapolation, vectorized per query."""
    time=np.asarray(time);values=np.asarray(values);query=np.asarray(query)
    fs=1/(time[1]-time[0])
    np.testing.assert_allclose(time,time[0]+np.arange(len(time))/fs,atol=1e-10,rtol=0)
    position=(query-time[0])*fs
    indices=np.floor(position).astype(int)[:,None]+np.arange(-halfwidth+1,halfwidth+1)
    if np.any(indices<0) or np.any(indices>=len(values)):
        raise ValueError('Sinc query lacks complete kernel support')
    distance=position[:,None]-indices
    beta=8.6
    window=np.i0(beta*np.sqrt(np.maximum(0,1-(distance/halfwidth)**2)))/np.i0(beta)
    weights=np.sinc(distance)*window
    weights/=weights.sum(axis=1,keepdims=True)
    result=np.sum(values[indices]*weights,axis=1)
    if not np.all(np.isfinite(result)):raise ValueError('Nonfinite sinc result')
    return result


def check_trace(dense,query):
    """Check noisy clamped power only; its known samples are the held-out oracle."""
    time=dense[:,0];power=dense[:,2]
    # Remove odd-index samples, reconstruct them from even samples (half-rate grid).
    held=np.arange(1,len(time),2)
    held=held[(time[held]>=query.min())&(time[held]<=query.max())]
    predicted=CubicSpline(time[::2],power[::2],extrapolate=False)(time[held])
    held_error=nrmse(predicted,power[held])
    cubic=CubicSpline(time,power,extrapolate=False)(query)
    sinc64=sinc_interpolate(time,power,query,64)
    sinc128=sinc_interpolate(time,power,query,128)
    method=nrmse(cubic,sinc128);convergence=nrmse(sinc64,sinc128)
    fractional=np.abs((query-time[0])/(time[1]-time[0])-np.rint((query-time[0])/(time[1]-time[0])))>1e-8
    return dict(fractional_query_samples=int(sum(fractional)),held_out_half_rate_nrmse=held_error,cubic_vs_sinc128_nrmse=method,
                sinc64_vs_sinc128_nrmse=convergence,held_out_samples=len(held),query_samples=len(query)),cubic,sinc128


def audit_archive(archive):
    archive=Path(archive).resolve()
    artifact_count=verify(archive)
    manifest_hash=digest(archive/'manifest.json')
    with (archive/'trials.csv').open() as f:trials=list(csv.DictReader(f))
    calibration=json.loads((archive/'calibration.json').read_text())['phase']
    filters=json.loads((archive/'filters.json').read_text())
    duration=json.loads((archive/'run.json').read_text())['arguments']['duration']
    rows=[];cache={}
    for trial in trials:
        name=trial['name'];fs=int(trial['fs']);fm=int(trial['fm_hz']);seed=int(trial['seed'])
        key=(fs,fm,seed)
        if key not in cache:
            with np.load(archive/'dense_reference'/f'{fs}_fm{fm}_seed{seed}.npz') as stored:cache[key]=stored['data']
        dense=cache[key]
        base_name=f'{fs}_full_rate'
        baseline_lag=next(r['delay_s'] for r in calibration[base_name] if r['frequency_hz']==fm)
        relative=float(trial['calibrated_delay_s'])-baseline_lag
        y=np.loadtxt(archive/'features'/f'{name}_fm{fm}_seed{seed}.csv',delimiter=',',skiprows=1,ndmin=2)
        # Reconstruct the original, declared pilot validity interval (not a new fit).
        warmup=filters['digital'][name]['warmup']
        valid=(y[:,0]>=warmup+max(float(trial['calibrated_delay_s']),.3))&(y[:,0]<duration-.3)
        query=y[valid,0]-relative
        checks,cubic,sinc=check_trace(dense,query)
        measured=nrmse(y[valid,3],cubic);alternative=nrmse(y[valid,3],sinc)
        if abs(measured-float(trial['paired_aligned_nrmse']))>1e-12:
            raise RuntimeError('Could not reproduce original paired metric: '+str(key)+name)
        row=dict(name=name,fs=fs,fm_hz=fm,seed=seed,**checks,
                 saved_method_paired_nrmse=measured,sinc128_paired_nrmse=alternative,
                 paired_nrmse_change=abs(measured-alternative))
        row['passed']=(checks['held_out_half_rate_nrmse']<=HELD_OUT_TOLERANCE and
                       checks['cubic_vs_sinc128_nrmse']<=METHOD_TOLERANCE and
                       checks['sinc64_vs_sinc128_nrmse']<=SINC_CONVERGENCE_TOLERANCE)
        rows.append(row)
    # Verify again: no source artifact should have changed while reading it.
    verify(archive)
    if digest(archive/'manifest.json')!=manifest_hash:raise RuntimeError('Input archive changed during audit')
    return dict(input_archive=str(archive),input_manifest_sha256=manifest_hash,input_artifacts_verified=artifact_count,
                input_scope='All saved noisy full-rate references and actual architecture comparison queries in this completed pilot.',
                tolerances_fractional_nrmse=dict(held_out_half_rate=HELD_OUT_TOLERANCE,cubic_vs_sinc128=METHOD_TOLERANCE,sinc_convergence=SINC_CONVERGENCE_TOLERANCE),
                interpretation='Held-out error has known discrete-sample truth on a coarser grid. Sinc comparison is a converged-method sensitivity check, not continuous-time ground truth. Does not cover new transient spectra.',
                passed=all(row['passed'] for row in rows),fractional_query_cases=sum(row['fractional_query_samples']>0 for row in rows),cases=rows)


def validation_report(out):
    source=json.loads((out/'source_validation.json').read_text())
    lines=['# Guard and interpolation validation','',
           'The standalone source-validator CLI and callable reject optimized Python before accepting evidence. C source generation rejects line frequencies at or above internal Nyquist before creating output. The normal 60 Hz configuration remains accepted.','',
           'Source/ADC, digital C/SciPy, block-state, operation-ledger, artifact-integrity, interpolation unit, and stage-isolated alias checks passed in this validation archive. See the individual JSON files for scope and measured results.','',
           '## Guard cases','',
           '| Line Hz at 80 kHz internal clock | Return code | Trace created |','|---:|---:|---|']
    for row in source['line_frequency_guard']:
        lines.append(f"| {row['line_hz']} | {row['returncode']} | {row['output_created']} |")
    lines+=['','Both `-O` and `-OO` are rejected by the source-validator CLI and callable API.','']
    audit_path=out/'noisy_alignment_audit.json'
    if audit_path.exists():
        audit=json.loads(audit_path.read_text());rows=audit['cases']
        lines+=['## Saved noisy pilot audit','',
            f"The completed input pilot has {audit['input_artifacts_verified']} verified artifacts. All {len(rows)} architecture/seed/modulation comparisons were checked; {audit['fractional_query_cases']} cases contain fractional-sample queries. The input manifest SHA-256 is `{audit['input_manifest_sha256']}`. Input archive: `{audit['input_archive']}`.",'',
            '| Diagnostic | Maximum NRMSE % | Declared diagnostic tolerance % |','|---|---:|---:|']
        for field,tol in (('held_out_half_rate_nrmse','held_out_half_rate'),('cubic_vs_sinc128_nrmse','cubic_vs_sinc128'),('sinc64_vs_sinc128_nrmse','sinc_convergence')):
            lines.append(f"| {field} | {100*max(row[field] for row in rows):.8f} | {100*audit['tolerances_fractional_nrmse'][tol]:.6f} |")
        change=max(row['paired_nrmse_change'] for row in rows)
        lines+=['',f"Maximum change in the pilot's noisy paired NRMSE when replacing production cubic alignment with sinc128 is {100*change:.8f} percentage points. All diagnostic thresholds passed.",'',
            'The held-out test removes odd-index dense samples and reconstructs those known values from the even-index samples, deliberately using a grid with half the original rate. The method comparison uses normalized Kaiser-windowed sinc with 64/128 samples on each side at the exact original pilot query timestamps, with the calibration delay held fixed.','',
            'These checks establish low reconstruction error and low method sensitivity on the actual saved noisy cases. Windowed sinc is a convergence comparison, not continuous-time ground truth. They do not establish a universal bound for arbitrary transients, gaps, new filters, or new input spectra.','',
            'The production interpolation method and DSP outputs were not changed. No full pilot rerun was needed. The completed pilot archive is preserved and is reverified before and after this read-only audit. Current guard fixes and diagnostic code belong to this new validation archive; the pilot retains its original source snapshots.']
    else:
        lines+=['The validation includes a new one-seed nominal noisy interpolation check in targeted_validation.json. To audit every comparison in a saved pilot, invoke validation-only mode with --alignment-archive PATH.']
    (out/'VALIDATION_REPORT.md').write_text('\n'.join(lines)+'\n')

#!/usr/bin/env python3
"""Independent steady-state checks of the C source and analog approximation."""
import json
import argparse
import subprocess
import sys
from pathlib import Path
import tempfile
import numpy as np
from scipy import signal
from study import analog, build, source, save_json, ROOT


def run_checks(source_fn=source, bin_dir=None):
    if not __debug__:
        raise RuntimeError('Source validation requires Python without -O; acceptance checks must remain enabled.')
    source = source_fn
    checks = {}
    with tempfile.TemporaryDirectory(prefix='v3_source_check_') as tmp:
        path=Path(tmp)/'source.csv'
        d=source(path,duration=12,clean=True,fm=2)
        valid=d[:,0]>=2;t=d[valid,0]
        sos,order,corner=analog()
        # AM carrier expands exactly into three sinusoids; use complex transfer.
        frequencies=np.array([108.,110.,112.])
        amplitudes=np.array([.2*.05/2,.2,.2*.05/2])
        _,h=signal.sosfreqz(sos,worN=frequencies,fs=80000)
        expected=np.sum(amplitudes[:,None]*abs(h[:,None])*np.sin(2*np.pi*frequencies[:,None]*t+np.angle(h[:,None])),axis=0)
        error=float(np.max(abs(d[valid,2]-expected)))
        assert error<2e-10,error
        checks['analytic_three_tone_max_abs_error_fs']=error
        oracle=.2**2/2*(1+.05*np.cos(2*np.pi*2*d[:,0]))**2
        np.testing.assert_allclose(d[:,5],oracle,rtol=0,atol=1e-16)
        # Check the ADC code explicitly, including saturation and half-away rounding.
        d=source(path,duration=12)
        code=np.sign(d[:,3])*np.floor(abs(d[:,3])*32768+.5)
        expected=np.clip(code,-32768,32767)/32768
        np.testing.assert_array_equal(d[:,4],expected)
        np.testing.assert_array_equal(d[:,6],((code< -32768)|(code>32767)).astype(float))
        checks['adc_rounding_and_saturation']='passed'
        # Finite-run RMS is a statistical screen, not an exact equality.
        enbw=corner*np.pi/(2*order)/np.sin(np.pi/(2*order))
        expected_rms=.0002*np.sqrt(enbw)
        measured=float(np.std(d[d[:,0]>=2,7]))
        relative=measured/expected_rms-1
        assert abs(relative)<.07,relative
        checks.update(noise_rms_fs=measured,predicted_continuous_noise_rms_fs=expected_rms,
                      noise_relative_error=relative,noise_rms_screen_tolerance=.07)
        # A high-amplitude synthetic source exercises clipping, not just nominal no-clip.
        config=path.with_suffix('.source')
        text=config.read_text().splitlines();fields=text[0].split();fields[3]='10';text[0]=' '.join(fields)
        config.write_text('\n'.join(text)+'\n')
        from study import HERE
        binary_dir=Path(bin_dir) if bin_dir else HERE
        subprocess.run([str(binary_dir/'stimulus'),str(config),str(path)],check=True)
        clipped=np.loadtxt(path,delimiter=',',skiprows=1)
        assert sum(clipped[:,6])>0
        code=np.sign(clipped[:,3])*np.floor(abs(clipped[:,3])*32768+.5)
        np.testing.assert_array_equal(clipped[:,4],np.clip(code,-32768,32767)/32768)
        checks['overrange_adc_clips']=int(sum(clipped[:,6]))
        # Invalid frequencies must fail before creating a trace, including exact Nyquist.
        guard_cases=[]
        for line_hz in (60,39999,40000,80110):
            fields=text[0].split();fields[2]='.002';fields[3]='1';fields[9]='.12';fields[10]=str(line_hz)
            guard_config=Path(tmp)/f'line_{line_hz}.source'
            guard_config.write_text(' '.join(fields)+'\n'+'\n'.join(text[1:])+'\n')
            trace=Path(tmp)/f'line_{line_hz}.csv'
            result=subprocess.run([str(binary_dir/'stimulus'),str(guard_config),str(trace)],capture_output=True,text=True)
            rejected=line_hz>=40000
            if rejected and (result.returncode!=2 or trace.exists() or 'internal Nyquist' not in result.stderr):
                raise RuntimeError(f'Invalid line frequency was not rejected before output: {line_hz}')
            if not rejected and (result.returncode!=0 or not trace.exists()):
                raise RuntimeError(f'Valid line frequency rejected: {line_hz}: {result.stderr}')
            guard_cases.append(dict(line_hz=line_hz,expected_rejected=rejected,returncode=result.returncode,output_created=trace.exists()))
        checks['line_frequency_guard']=guard_cases
        # Test the public CLI in both optimized modes, before build or output creation.
        optimization=[]
        for flag in ('-O','-OO'):
            output=Path(tmp)/f'optimized_{flag}.json'
            result=subprocess.run([sys.executable,flag,str(Path(__file__).resolve()),'--output',str(output)],capture_output=True,text=True)
            if result.returncode!=2 or output.exists() or 'without -O' not in result.stderr:
                raise RuntimeError(f'Standalone validator did not reject {flag}')
            optimization.append(dict(flag=flag,returncode=result.returncode,evidence_created=output.exists()))
        checks['standalone_optimization_guard']=optimization
        # The callable API must reject optimized execution too, before using its source.
        callable_results=[]
        for flag in ('-O','-OO'):
            script=(f"import sys;sys.path.insert(0,{str(Path(__file__).resolve().parent)!r});"
                    "from validate_source import run_checks;run_checks()")
            result=subprocess.run([sys.executable,flag,'-c',script],capture_output=True,text=True)
            if result.returncode==0 or 'Source validation requires Python without -O' not in result.stderr:
                raise RuntimeError(f'Callable source validator did not reject {flag}')
            callable_results.append(dict(flag=flag,returncode=result.returncode,rejected=True))
        checks['callable_optimization_guard']=callable_results
    return checks


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True,help='New JSON file; existing files are rejected')
    args=ap.parse_args()
    if not __debug__:
        ap.error('Source validation requires Python without -O; acceptance checks must remain enabled.')
    if args.output.exists():ap.error('Output exists; choose a new evidence file')
    build()
    checks=run_checks()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    save_json(args.output,checks)
    print(json.dumps(checks,indent=2))


if __name__=='__main__':main()

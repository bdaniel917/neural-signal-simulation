"""Stage-isolated alias tests, alignment error floor, and contamination diagnostics."""
from pathlib import Path
import shutil
import numpy as np
from scipy import signal


def run_targeted(work,configs,paths,s,out):
    evidence=out/'targeted';evidence.mkdir()
    checks={}
    # Analytic smooth power with fundamental and second harmonic, exact pure delay.
    alignment=[]
    for fs in (1000,2000,4000):
        t=np.arange(8*fs)/fs
        for fm in (2,5,10):
            oracle=lambda u:.02*(1+.25*np.cos(2*np.pi*fm*u))**2
            dense=np.column_stack((t,oracle(t)))
            for fraction in (.17,.5,.83):
                lag=(8+fraction)/fs
                query=np.arange(200,600)/100-lag
                exact=oracle(query)
                corrected=s.align_dense(dense,query,1)
                old=np.interp(query,t[::fs//100],oracle(t[::fs//100]))
                error=s.nrmse(corrected,exact)
                assert error<1e-6,(fs,fm,fraction,error)
                alignment.append(dict(fs=fs,fm_hz=fm,delay_s=lag,dense_cubic_nrmse=error,legacy_100hz_linear_nrmse=s.nrmse(old,exact)))
    checks['known_pure_delay_alignment']=dict(tolerance_nrmse=1e-6,cases=alignment,
        scope='Smooth AM-power oracle through 20 Hz. Does not prove interpolation accuracy for arbitrary transients or out-of-band residuals.')
    # Dense C diagnostic agrees with independent causal convolution at every sample.
    rng=np.random.default_rng(211);base=np.zeros((8000,10));base[:,0]=np.arange(8000)/4000
    base[:,4]=rng.normal(0,.1,8000);base[:,2]=rng.normal(0,.1,8000)
    np.savez_compressed(evidence/'dense_validation_input.npz',data=base)
    dense_checks=[]
    for name,cfg in configs.items():
        data=base[::4000//cfg['fs']];inp=work/'target_input.csv';s.write_input(inp,data)
        y,counts=s.run(paths[name],inp,work/'target_feature.csv',7,dense=work/'target_dense.csv')
        d=np.loadtxt(work/'target_dense.csv',delimiter=',',skiprows=1,ndmin=2)
        x,_=s.reference(data,cfg);xc,_=s.reference(data,cfg,2)
        p=signal.lfilter(cfg['feature'],[1],x*x);pc=signal.lfilter(cfg['feature'],[1],xc*xc)
        error=max(float(max(abs(d[:,1]-p))),float(max(abs(d[:,3]-pc))))
        assert error<2e-11,(name,error)
        np.testing.assert_allclose(d[:,0],np.arange(len(d))/cfg['processing_fs'],atol=1e-12,rtol=0)
        np.testing.assert_array_equal(d[::cfg['feature_factor'],2],y[:,3])
        np.testing.assert_array_equal(d[::cfg['feature_factor'],4],y[:,5])
        plain,plaincounts=s.run(paths[name],inp,work/'plain.csv',7)
        np.testing.assert_array_equal(y,plain);assert counts==plaincounts
        n=len(data);m=len(d);f=len(y);sections=len(cfg['bandpass'])+len(cfg['notch'])
        ac=len(cfg['acquisition'])*m if len(cfg['acquisition'])>1 else 0
        assert counts['multiplications']==ac+5*sections*m+m+len(cfg['feature'])*f
        assert counts['additions']==ac+4*sections*m+len(cfg['feature'])*f
        dense_checks.append(dict(name=name,max_absolute_error_fs2=error,diagnostics_do_not_change_output_or_counts=True,operation_ledger_verified=True))
    checks['dense_c_diagnostic']=dense_checks
    # ADC aliasing: continuous/internal-clock tone -> analog filter -> ADC.
    adc=[]
    for fs in (1000,2000,4000):
        tone=fs-110
        data=s.source(work/'alias_source.csv',duration=12,amplitude=0,density=0,line=0,oob=.1,oob_hz=tone)
        shutil.copyfile((work/'alias_source.csv').with_suffix('.source'),evidence/f'adc_alias_{fs}.source')
        d=data[::4000//fs];valid=d[:,0]>=2;t=d[valid,0]
        _,h=signal.sosfreqz(s.analog()[0],worN=[tone],fs=80000)
        expected=.1*abs(h[0])
        def amplitude(y):
            fit=np.linalg.lstsq(np.column_stack((np.ones(len(t)),np.sin(2*np.pi*110*t),np.cos(2*np.pi*110*t))),y,rcond=None)[0]
            return float(np.hypot(fit[1],fit[2]))
        analog_fold=amplitude(d[valid,3]);adc_fold=amplitude(d[valid,4])
        assert abs(analog_fold-expected)<max(1e-12,expected*1e-5)
        adc.append(dict(adc_fs=fs,physical_tone_hz=tone,folded_hz=110,expected_analog_amplitude_fs=float(expected),
                        measured_unquantized_fold_amplitude_fs=analog_fold,measured_16bit_adc_fold_amplitude_fs=adc_fold,
                        adc_clips=int(sum(d[:,6]))))
    checks['adc_aliasing']=dict(scope='Analog-only tone at ADC_fs-110; no desired signal or noise. Very small residuals may lie below the ADC quantization step.',cases=adc)
    # Digital decimator aliasing, bypassing analog and ADC to isolate acquisition FIR.
    digital=[]
    for fs,tones in ((2000,(890,)),(4000,(890,1890))):
        cfg=configs[f'{fs}_multirate']
        unfiltered=dict(cfg,acquisition=np.ones(1))
        cfgpath=evidence/f'decimator_no_acquisition_{fs}.txt';s.write_config(cfgpath,unfiltered)
        for tone in tones:
            data=np.zeros((fs*12,10));data[:,0]=np.arange(len(data))/fs
            data[:,4]=.1*np.sin(2*np.pi*tone*data[:,0]);data[:,2]=data[:,4]
            inp=work/'digital_alias.csv';s.write_input(inp,data)
            output=[]
            for label,path in (('filtered',paths[f'{fs}_multirate']),('unfiltered',cfgpath)):
                f=evidence/f'digital_alias_{fs}_{tone}_{label}.csv';wave=work/'alias_wave.csv'
                y,_=s.run(path,inp,f,fs//125,wave)
                w=np.loadtxt(wave,delimiter=',',skiprows=1,ndmin=2)
                output.append((float(np.sqrt(np.mean(w[w[:,0]>=2,1]**2))),float(np.mean(y[y[:,0]>=2,3]))))
            rejection=-20*np.log10(output[0][0]/output[1][0])
            _,h=signal.freqz(cfg['acquisition'],[1],worN=[tone],fs=fs)
            predicted=-20*np.log10(abs(h[0]))
            assert rejection>=60 and abs(rejection-predicted)<.001,(fs,tone,rejection,predicted)
            digital.append(dict(input_fs=fs,tone_hz=tone,folded_hz=110,measured_rejection_db=float(rejection),
                                predicted_fir_rejection_db=float(predicted),filtered_feature_mean_fs2=output[0][1],
                                unfiltered_feature_mean_fs2=output[1][1]))
    checks['digital_decimator_aliasing']=dict(scope='Stage-isolated exact floating-point tones; analog and ADC deliberately bypassed. Same bandpass, smoothing, and decimation in both paths.',cases=digital)
    # Controlled additions share the same desired/noise/interference realization.
    data=s.source(work/'isolation.csv',duration=12,seed=1)
    shutil.copyfile((work/'isolation.csv').with_suffix('.source'),evidence/'isolation.source')
    data=data[::2];np.savez_compressed(evidence/'isolation_components.npz',data=data)
    cfg=configs['2000_multirate'];inp=work/'isolation_input.csv';groups={};rows=[]
    for case,noise,interference in (('desired_only',False,False),('desired_plus_noise',True,False),('desired_plus_interference',False,True),('all_components',True,True)):
        analog=data[:,2].copy()
        if noise:analog+=data[:,7]
        if interference:analog+=data[:,8]+data[:,9]
        for quantized in (False,True):
            d=data.copy();d[:,3]=analog
            code=np.sign(analog)*np.floor(abs(analog)*32768+.5)
            d[:,4]=np.clip(code,-32768,32767)/32768 if quantized else analog
            d[:,6]=((code< -32768)|(code>32767)).astype(float) if quantized else 0
            s.write_input(inp,d);label=case+('_16bit' if quantized else '_unquantized')
            y,_=s.run(paths['2000_multirate'],inp,evidence/(label+'.csv'),16)
            groups[label]=y
    valid=groups['desired_only_unquantized'][:,0]>=2
    baseline=groups['desired_only_unquantized'][valid,3]
    for label,y in groups.items():
        case=label.removesuffix('_16bit').removesuffix('_unquantized')
        unquantized=groups[case+'_unquantized'][valid,3]
        rows.append(dict(case=label,against_desired_only_nrmse=s.nrmse(y[valid,3],baseline),
                         quantization_increment_nrmse=s.nrmse(y[valid,3],unquantized),
                         mean_shift_fs2=float(np.mean(y[valid,3]-baseline))))
    checks['component_isolation']=dict(scope='One seed, 2 Hz modulation, 2 kHz multirate; diagnostic attribution only, not population statistics. Error terms are not additive after squaring.',cases=rows)
    # A nominal noisy trace also exercises interpolation in every new validation run.
    # The last isolation input is the matched all-components 16-bit case.
    dense_path=work/'noisy_dense.csv'
    s.run(paths['2000_full_rate'],inp,evidence/'noisy_alignment_full_rate.csv',16,dense=dense_path)
    dense=np.loadtxt(dense_path,delimiter=',',skiprows=1,ndmin=2)
    np.savez_compressed(evidence/'noisy_alignment_dense.npz',data=dense)
    from alignment_checks import check_trace, HELD_OUT_TOLERANCE, METHOD_TOLERANCE, SINC_CONVERGENCE_TOLERANCE
    # Fixed deliberately fractional-sample queries, not an optimized delay.
    query=np.arange(230,1170)/100-.007063
    metrics,_,_=check_trace(dense,query)
    if (metrics['held_out_half_rate_nrmse']>HELD_OUT_TOLERANCE or
        metrics['cubic_vs_sinc128_nrmse']>METHOD_TOLERANCE or
        metrics['sinc64_vs_sinc128_nrmse']>SINC_CONVERGENCE_TOLERANCE):
        raise RuntimeError('Nominal noisy interpolation check failed: '+str(metrics))
    checks['nominal_noisy_alignment']=dict(scope='One seed, 2 Hz, full-rate 2 kHz, fixed fractional queries; not a bound for other spectra.',
        passed=True,**metrics)
    return checks

# Double-precision rate comparison

## Scope

This is a 20-seed pilot per modulation frequency, not the planned 100-seed formal study. The source is a synthetic 110 Hz AM carrier at 2 and 5 Hz. Every architecture at a given ADC rate receives exactly the same 16-bit ADC samples. No real neural data, hardware timing, or physiological utility is validated.

A: full-rate bandpass and feature extraction. B: acquisition anti-alias FIR with bandpass processing at the ADC rate. C: the same FIR followed by reduction to 1 kHz. All output features at 100 Hz, epoch phase zero. Comparing A/B isolates acquisition-filter effects; B/C adds rate reduction and redesigned downstream filters. Baseline notch is off. The additional 2 kHz multirate notch case is conditional evidence, not a new default.

## Implementation checks

All 10 configurations pass C versus independent SciPy causal references (waveform, raw square-and-smooth output, and clean reference), timestamp checks, and block-size invariance at 1, 7, 63, and 128 samples. The three 1 kHz configurations have identical coefficients. No internal state resets occur at block boundaries.

All digital pass/stop responses meet the specified sampled-grid checks including exact edges. The analog model is a fifth-order continuous Butterworth approximated by bilinear transformation at 80 kHz. Its realized 150 Hz loss is 0.250028 dB; the 0.000028 dB difference from the continuous 0.25 dB limit is documented discretization error (0.001 dB tolerance). The 500 Hz attenuation is 40.0210 dB.

The 2 s baseline exclusion (4 s for the optional notch) exceeds the sum of a conservative 1e-9 pole-decay estimate and complete FIR support in every configuration. This estimate is supplemented by the independent onset trace. Raw FIR power can be negative during transients; raw and clamped outputs and clamp flags are retained.

## Measured results

NRMSE is RMS error divided by RMS reference. Paired error uses cubic-spline interpolation of C diagnostic power at the full processing rate (1/2/4 kHz), rather than linear interpolation of the 100 Hz stream. Dense diagnostics read state without changing the deployed path or its arithmetic counters. The alignment method passes known-delay and dense C/SciPy checks saved in targeted_validation.json. Paired error uses a fixed relative delay from an independent depth=0.05 clean modulation calibration; it does not refit delay or gain for each noisy trial. Unaligned errors remain in trials.csv. Diagnostic alignment is offline and adds no proposed processing stage. Mean bias below uses a DC-plus-two-harmonic fit to the clean output to avoid partial-cycle averaging bias; oracle includes analog and digital attenuation as error.

| ADC Hz / architecture | fm Hz | Clean mean bias % | Clean paired NRMSE %, max | Noisy paired NRMSE %, mean / max | Oracle aligned NRMSE % | Phase delay ms | Multiplications/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1000_full_rate | 2 | -0.266 | 0.000 | 0.000 / 0.000 | 1.239 | 93.61 | 55700 |
| 1000_full_rate | 5 | -0.267 | 0.000 | 0.000 / 0.000 | 1.243 | 93.65 | 55700 |
| 1000_prefilter_full_rate | 2 | -0.266 | 0.000 | 0.000 / 0.000 | 1.239 | 93.61 | 55700 |
| 1000_prefilter_full_rate | 5 | -0.267 | 0.000 | 0.000 / 0.000 | 1.243 | 93.65 | 55700 |
| 1000_multirate | 2 | -0.266 | 0.000 | 0.000 / 0.000 | 1.239 | 93.61 | 55700 |
| 1000_multirate | 5 | -0.267 | 0.000 | 0.000 / 0.000 | 1.243 | 93.65 | 55700 |
| 2000_full_rate | 2 | -0.266 | 0.000 | 0.000 / 0.000 | 1.220 | 95.55 | 121100 |
| 2000_full_rate | 5 | -0.267 | 0.000 | 0.000 / 0.000 | 1.224 | 95.59 | 121100 |
| 2000_prefilter_full_rate | 2 | -0.247 | 0.019 | 0.018 / 0.018 | 1.220 | 104.55 | 195100 |
| 2000_prefilter_full_rate | 5 | -0.248 | 0.018 | 0.018 / 0.018 | 1.223 | 104.59 | 195100 |
| 2000_multirate | 2 | -0.247 | 0.019 | 0.283 / 0.284 | 1.242 | 102.61 | 92700 |
| 2000_multirate | 5 | -0.248 | 0.019 | 0.283 / 0.284 | 1.245 | 102.65 | 92700 |
| 4000_full_rate | 2 | -0.266 | 0.000 | 0.000 / 0.000 | 1.220 | 95.31 | 241900 |
| 4000_full_rate | 5 | -0.267 | 0.000 | 0.000 / 0.000 | 1.224 | 95.35 | 241900 |
| 4000_prefilter_full_rate | 2 | -0.252 | 0.014 | 0.014 / 0.014 | 1.220 | 104.06 | 525900 |
| 4000_prefilter_full_rate | 5 | -0.253 | 0.014 | 0.014 / 0.014 | 1.223 | 104.10 | 525900 |
| 4000_multirate | 2 | -0.252 | 0.014 | 0.286 / 0.287 | 1.241 | 102.36 | 126700 |
| 4000_multirate | 5 | -0.253 | 0.014 | 0.286 / 0.287 | 1.245 | 102.40 | 126700 |
| 2000_multirate_notch | 2 | -0.338 | 0.072 | 0.267 / 0.268 | 1.258 | 102.70 | 97700 |
| 2000_multirate_notch | 5 | -0.339 | 0.073 | 0.267 / 0.268 | 1.261 | 102.73 | 97700 |

## Effect of the review corrections

The clean-path 2% screen now uses clean outputs from both architectures. Noisy preservation error is reported separately. The old 100 Hz linear-alignment calculation is retained as legacy_linear_paired_nrmse on exactly the same current noisy samples and validity windows; this is an evaluation-method comparison, not a change in deployed DSP.

| Multirate ADC Hz | fm Hz | Clean paired NRMSE % | Noisy NRMSE %, old linear / corrected dense |
|---:|---:|---:|---:|
| 2000 | 2 | 0.0187 | 0.3155 / 0.2828 |
| 2000 | 5 | 0.0187 | 0.4651 / 0.2831 |
| 4000 | 2 | 0.0139 | 0.3184 / 0.2862 |
| 4000 | 5 | 0.0139 | 0.4668 / 0.2864 |

Known pure-delay AM-power checks (2, 5, 10 Hz modulation, including second harmonics through 20 Hz) have a maximum dense-alignment NRMSE of 0.0000019%. This is an error-floor check for smooth signals, not a universal bound for arbitrary transients.

Stage-isolated digital tones folding into 110 Hz show at least 87.80 dB rejection from the acquisition FIR and agree with its predicted response. Separate physical-tone cases demonstrate ADC aliasing after analog attenuation; residuals can fall below the 16-bit quantization step. These selected-tone checks do not establish worst-case broadband alias performance.

The one-seed component-isolation study separates noise, interference, and the quantization increment. Their errors are not additive after squaring. The main contamination_and_quantization_nrmse field deliberately includes all these contributions.

| Isolated case | Error against desired-only % | Quantization increment % |
|---|---:|---:|
| desired_only_unquantized | 0.00000 | 0.00000 |
| desired_only_16bit | 0.00156 | 0.00156 |
| desired_plus_noise_unquantized | 1.24670 | 0.00000 |
| desired_plus_noise_16bit | 1.24667 | 0.00177 |
| desired_plus_interference_unquantized | 0.45817 | 0.00000 |
| desired_plus_interference_16bit | 0.45783 | 0.00169 |
| all_components_unquantized | 1.36775 | 0.00000 |
| all_components_16bit | 1.36780 | 0.00177 |

## Provisional screens

- PASS: Clean mean bias ≤10%.
- PASS: Multirate clean paired aligned NRMSE ≤2% at nominal carrier.
- PASS: Small-modulation delay ≤200 ms at 2/5 Hz.
- PASS: No nominal ADC clipping.

These are project-level screens on synthetic cases, not device requirements. Passing does not establish performance at band edges, across electrode impedances, or on neural recordings. A failing screen is retained as a result.

## Source and noise checks

The one-sided white-noise density is 0.0002 FS/√Hz before the analog filter. Continuous-filter equivalent noise bandwidth is 202.296 Hz, giving predicted RMS 0.002845 FS. The finite internal Nyquist bandwidth and bilinear approximation are explicit. The 40/80/160 kHz convergence run uses the same deterministic signals; same-seed realizations mapped to different time grids are compared by RMS rather than sample differences.

| Internal Hz | Clean RMS FS | Noise RMS FS | 60 Hz RMS FS | 1350 Hz RMS FS |
|---:|---:|---:|---:|---:|
| 40000 | 0.1434229 | 0.002850325 | 0.08485255 | 4.827874e-06 |
| 80000 | 0.143423 | 0.002859228 | 0.08485255 | 4.896423e-06 |
| 160000 | 0.143423 | 0.002863977 | 0.08485255 | 4.91367e-06 |

## Interpretation and remaining work

Power is the causal, smoothed square of the bandpassed waveform in FS². It includes passed noise and interference, and it is not an exact rectangular 70–150 Hz PSD integral or neural-only power. The analytic AM oracle is used alongside a clean architecture-matched reference so those effects remain distinguishable.

Operation totals count the deployed noisy path only: five multiplies/four adds per SOS; one multiply per square; one multiply and accumulator add per FIR tap, including the initial add to zero. FIR convolution is evaluated only on retained outputs, while state consumes every input. These counts omit loop, modulo, I/O, memory, clipping, and control overhead. They are not CPU cycles or measured execution-time claims.

Input block availability is recorded separately from original feature timestamps; CPU, transport, scheduler, buffer overflow, and actual memory limits are not modeled. Phase delay and onset T10/T50/T90 are different quantities, both saved in calibration.json.

Remaining scope: referencing and bad channels; carrier/band-edge and transient stress cases; isolated 60 Hz feature-error/notch decision; full noise statistics and confidence intervals; actual float32/Q15/Q31 kernels and range/scaling checks; target timing and buffer/memory measurements. The notch comparison here includes noise and OOB interference, so it cannot alone justify notch selection.

Source and ADC validation and targeted alignment/aliasing/component-isolation checks run inside this archive. Their inputs and measured outputs are summarized in source_validation.json and targeted_validation.json. Source convergence here is a diagnostic table, not a statistical hypothesis test. The pilot reports seed-level means and observed maxima, not population tail guarantees. The 80 kHz noise source is band-limited by its clock and the specified analog filter; an electrode/amplifier model, colored noise, motion artifacts, and empirical interference statistics remain simplified.

## Reproduce

From the project directory: `.venv/bin/python pipeline_v3/study.py --trials 20`. For implementation checks alone: `make validate-v3` (includes independent source/ADC checks). Every invocation creates a fresh archive; existing output directories are rejected. A completion manifest hashes every artifact and snapshots the reviewed sources. Verify it with `.venv/bin/python pipeline_v3/evidence.py RUN_DIRECTORY`. Numerical agreement is intended; cross-machine bitwise identity is not promised. Exact coefficient files, source hashes, dependency versions, calibration, per-trial feature traces, and trial metrics accompany this report. This command does not modify earlier archives or publish website changes.

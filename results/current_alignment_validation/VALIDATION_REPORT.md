# Guard and interpolation validation

The standalone source-validator CLI and callable reject optimized Python before accepting evidence. C source generation rejects line frequencies at or above internal Nyquist before creating output. The normal 60 Hz configuration remains accepted.

Source/ADC, digital C/SciPy, block-state, operation-ledger, artifact-integrity, interpolation unit, and stage-isolated alias checks passed in this validation archive. See the individual JSON files for scope and measured results.

## Guard cases

| Line Hz at 80 kHz internal clock | Return code | Trace created |
|---:|---:|---|
| 60 | 0 | True |
| 39999 | 0 | True |
| 40000 | 2 | False |
| 80110 | 2 | False |

Both `-O` and `-OO` are rejected by the source-validator CLI and callable API.

## Saved noisy pilot audit

The completed input pilot has 710 verified artifacts. All 400 architecture/seed/modulation comparisons were checked; 200 cases contain fractional-sample queries. The input manifest SHA-256 is `fc5c8e41af265619e8c9b86bcf97bbb3253acba91e9996565395b0041ada2f87`. Input archive: `/Users/binoydaniel/Documents/neural_chain_sim/publication/neural-signal-simulation/results/current_pipeline`.

| Diagnostic | Maximum NRMSE % | Declared diagnostic tolerance % |
|---|---:|---:|
| held_out_half_rate_nrmse | 0.00100781 | 0.010000 |
| cubic_vs_sinc128_nrmse | 0.00012285 | 0.001000 |
| sinc64_vs_sinc128_nrmse | 0.00004624 | 0.000100 |

Maximum change in the pilot's noisy paired NRMSE when replacing production cubic alignment with sinc128 is 0.00001148 percentage points. All diagnostic thresholds passed.

The held-out test removes odd-index dense samples and reconstructs those known values from the even-index samples, deliberately using a grid with half the original rate. The method comparison uses normalized Kaiser-windowed sinc with 64/128 samples on each side at the exact original pilot query timestamps, with the calibration delay held fixed.

These checks establish low reconstruction error and low method sensitivity on the actual saved noisy cases. Windowed sinc is a convergence comparison, not continuous-time ground truth. They do not establish a universal bound for arbitrary transients, gaps, new filters, or new input spectra.

The production interpolation method and DSP outputs were not changed. No full pilot rerun was needed. The completed pilot archive is preserved and is reverified before and after this read-only audit. Current guard fixes and diagnostic code belong to this new validation archive; the pilot retains its original source snapshots.

# Double-precision pipeline and evidence guide

The authoritative pilot is `results/current_pipeline/`; its full noisy alignment audit is `results/current_alignment_validation/`. Both archives include completion inventories and immutable source snapshots. The design specification distinguishes the implemented subset from deferred work in `docs/PIPELINE_V3_SPEC.md`.

## Run and verify

From the project directory:

```sh
make validate
make study
# Explicit output must not already exist:
.venv/bin/python pipeline_v3/study.py --trials 20 --output results_my_pilot
.venv/bin/python pipeline_v3/evidence.py results_my_pilot
```

Both Make targets create a fresh timestamp/UUID directory under `results_v3_runs/`.
Validation-only includes source/ADC checks, alignment/aliasing/isolation checks,
and archive-integrity tests; it does not create a pilot report. A full study
includes all those checks before calibration and trials. Existing output paths
are rejected, even if empty. Failed/interrupted runs have no verified completion
manifest and must not be presented as completed results. Numerical screens that
fail remain visible results; implementation-check failures abort the run.

The project requires a C11 compiler and NumPy/SciPy/Matplotlib. Python optimization
(`-O`) is rejected because it disables validation assertions. `build.py` locates a
compatible macOS SDK. Kernels disable fused multiply-add contraction; exact
compiler flags, compiler/Python/package identities, platform, linked libraries,
and binary hashes are recorded. Numerical agreement is the intended reproducibility
level; bit-for-bit identity across machines is not promised.

Paths resolve from the source location, not the shell's current directory. Each
run compiles its binaries inside its own `bin/`. Source snapshots and `build.py`
are included. To reproduce from a snapshot, copy the archive's `sources/` tree to
a separate workspace, install the recorded environment, and run its study script.
Do not rerun inside a completed archive: adding files invalidates its inventory.

## Implementation map

- `double_dsp.h`: persistent DF2T SOS and FIR states. `v3_step` accepts one sample,
  advances phase/state, and emits waveform/feature events. `v3_push` retains every
  FIR input; `v3_dot` convolves only at retained outputs. Allocation occurs before
  the sample loop.
- `runner.c`: reads paired ADC/clean traces, processes blocks, records original
  timestamps and block availability, startup/clip/clamp flags, and operation counts.
  Its optional dense-power diagnostic reads existing FIR history at every processing
  sample without changing DSP state or deployed arithmetic counters. This additional
  offline work is explicitly excluded from the deployed operation ledger.
- `stimulus.c`: common-clock AM source, white-noise density, 60 Hz interference,
  OOB tone, analog approximation, and ideal signed 16-bit ADC. Noise density is
  specified before analog filtering and shared across ADC-rate comparisons.
- `study.py`: designs/verifies/exports coefficients; calls C; independently checks
  causal outputs against SciPy; performs clean phase calibration before noisy
  trials; computes separate clean/noisy paired metrics; writes plots/report.
- `validate_source.py`: analytic three-tone analog transfer, analytic power oracle,
  ADC rounding/saturation including overload, and noise RMS versus continuous ENBW.
  `run_checks` returns evidence to the invoking study. Standalone use requires a
  new `--output FILE.json`; it never silently overwrites the old study.
- `targeted_checks.py`: known-delay interpolation error floor, dense C/SciPy and
  operation-ledger checks, ADC-versus-digital alias tests, and matched component
  additions with/without quantization.
- `evidence.py`: source snapshots, environment identity, final artifact inventory,
  and read-only archive verification. Completion is published after hashing all
  files. Verification detects changes, missing files, and unlisted additions; it
  is an integrity check, not a signed attestation.
- `test_evidence.py`: missing/mutated/extra artifact and incomplete-run detection;
  verifies that an existing output directory is rejected without mutation.

## Architectures and metrics

1. **full_rate:** ADC → bandpass → square → smoothing FIR → 100 Hz features.
2. **prefilter_full_rate:** ADC → acquisition FIR → full-rate stages.
3. **multirate:** ADC → same acquisition FIR → 1 kHz → redesigned bandpass
   → square → smoothing FIR → 100 Hz features.

At 1 kHz all three paths are identical. The prefilter control separates acquisition
FIR effects from downstream filter redesign/rate reduction. Baseline notch is off;
a separate 2 kHz multirate/Q25 case is preliminary evidence, not a notch policy.
Startup exclusion is 2 s for baseline and 4 s for the notch.

Paired comparisons use a fixed delay obtained from independent, clean, depth=0.05
AM calibration. Full-rate C power is additionally evaluated at 1/2/4 kHz and saved.
A cubic spline evaluates this dense reference at shifted 100 Hz query times with
no extrapolation or gain fitting. Known-delay analytic tests quantify the error
floor for smooth AM power through 20 Hz; this is not a bound for arbitrary
transients. Deployment still produces 100 Hz features.

`clean_paired_aligned_nrmse` is the specified deterministic preservation screen.
`paired_aligned_nrmse` is the separate noisy comparison. Unaligned metrics remain
available. `legacy_linear_paired_nrmse` recomputes the old alignment method on the
same current traces for a controlled evaluation-method comparison.
`contamination_and_quantization_nrmse` includes stochastic noise, deterministic
interference, quantization, and nonlinear cross terms. Component-isolation
results separate controlled additions; their NRMSEs are not additive.

## Evidence files

- `REPORT.md`, `summary.json`, `trials.csv`: measured results, provisional screens,
  assumptions, and limitations. Min/max are observed seed-level values, not
  population bounds or confidence intervals.
- `filters.json`, `coefficients/`: exact double coefficients, orders, measured
  pass/stop responses, FIR delays, and settling estimates.
- `validation.json`, `source_validation.json`, `targeted_validation.json`,
  `archive_validation.json`: check scope, numerical results, and test outcomes.
- `calibration.json`, `calibration_traces/`: independent calibration fits, original
  feature traces, onset traces, and T10/T50/T90.
- `features/`: deployed 100 Hz power, clean power, raw/clamped values and flags.
- `dense_reference/`: compressed full-rate C power used for alignment. Columns:
  timestamp, raw power, clamped power, clean raw power, clean clamped power.
- `input_hashes.json`: hashes of the exact common per-rate input CSVs consumed by
  every architecture at each seed/modulation/rate. Regenerate those inputs using
  the snapshotted C source and study defaults; inputs are not all archived.
- `targeted/`: stage-isolated configs/traces, common component arrays and source
  configs. ADC alias tests include cases below the ADC quantization floor.
- `source_convergence.json`: same-seed noise mapped to different time grids;
  diagnostic RMS comparison, not independent convergence trials.
- `sources/`, `bin/`, `environment.json`, `run.json`, `manifest.json`: source and
  toolchain provenance and complete artifact hashes.

Remaining scope includes referencing/bad channels; carrier/band-edge and transient
stress; isolated 60 Hz notch policy; real recordings; actual float32/Q15/Q31;
confidence intervals and the formal 100-seed study; target memory/timing/buffers.
Operation counts are mathematical counts, not processor timing.

## Guard fixes and noisy alignment audit

The source validator now rejects optimized Python through both its CLI and callable
entry point. Source validation includes regression cases for `-O`/`-OO`, valid line
frequencies, and frequencies at/above internal Nyquist. Invalid C source frequencies
are rejected before creating a trace.

Every new validation run includes an interpolation unit test and a one-seed nominal
noisy interpolation check. To audit all saved comparison cases without altering
or rerunning the completed pilot:

```sh
.venv/bin/python pipeline_v3/study.py --validate-only \
  --alignment-archive results/current_pipeline \
  --output results/my_alignment_validation
.venv/bin/python pipeline_v3/evidence.py results/my_alignment_validation
```

Choose a different output name if it already exists. This creates a separate
validation archive with current source snapshots and toolchain, source-validation
guard cases, `noisy_alignment_audit.json`, and `VALIDATION_REPORT.md`. The read-only
input pilot is verified and bound by its completion-manifest hash; it is not copied
into the new archive and must remain available to reproduce the audit.

`alignment_checks.py` uses known held-out noisy samples to check reconstruction
from a half-rate grid, then compares production cubic interpolation with normalized
Kaiser-windowed sinc at the actual comparison queries. Half-widths 64 and 128 check
sinc-method convergence. Thresholds are fractional NRMSE: 1e-4 for the harder
half-rate held-out check, 1e-5 for cubic/sinc disagreement, and 1e-6 for sinc
convergence. These diagnostic thresholds sit below the 2% preservation screen;
they do not replace it. The comparison retains the original fixed calibration and
validity windows. Its scope is the saved noisy cases, not arbitrary future transients.

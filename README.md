# End-to-End Neural Signal Chain Simulation

A C11 signal-chain simulation with Python filter design, parameter sweeps, and independent numerical checks. I compare full-rate processing, an acquisition-FIR control, and multirate processing to see how reducing the processing rate changes a smoothed 70–150 Hz power feature.

The model uses a synthetic 110 Hz carrier with 2 / 5 Hz modulation, white noise, interference, an analog low-pass approximation, and an ideal 16-bit ADC. All three paths receive the same ADC samples. The current pipeline uses double-precision DSP.

## Run

Requires Python 3.10+, a C11 compiler, NumPy, SciPy, and Matplotlib.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make validate
make study
```

Each invocation creates a new archive under `results_v3_runs/`. To choose a location explicitly, use a path that does not already exist:

```sh
.venv/bin/python pipeline_v3/study.py --trials 20 --output results/my_run
.venv/bin/python pipeline_v3/evidence.py results/my_run
```

The evidence verifier checks source snapshots, artifact hashes, and completion status. Do not edit a completed results archive. `requirements.lock.txt` records the original Python 3.12 environment; each run also records its actual package and compiler versions.

## Results and figures

The latest publication run is in [`results/current_pipeline`](results/current_pipeline/). It includes the report, comparison figure, all trial metrics, coefficients, feature traces, calibration traces, validation evidence, environment details, and a completion inventory.

- [Measured report](results/current_pipeline/REPORT.md)
- [Comparison figure](results/current_pipeline/comparison.png)
- [All trial metrics](results/current_pipeline/trials.csv)
- [Pipeline design and evidence guide](pipeline_v3/README.md)
- [Specifications](docs/PIPELINE_V3_SPEC.md)

The study checks feature preservation, clean bias, delay, alias rejection in selected cases, and deployed arithmetic counts. Multiplication counts are not measured CPU cycles or energy. The model has not been calibrated to hardware or real neural recordings; feature utility, target arithmetic, memory, buffers, and execution timing remain unvalidated. Twenty paired noise seeds form a pilot, not a population tail guarantee.

## Source map

| Location | Purpose |
| --- | --- |
| `pipeline_v3/stimulus.c` | Synthetic source, analog approximation, sampling and ADC |
| `pipeline_v3/double_dsp.h` | Persistent SOS and FIR processing kernels |
| `pipeline_v3/runner.c` | Block processing, features, timestamps and operation counts |
| `pipeline_v3/study.py` | Filter design, calibration, paired sweeps, plots and report |
| `pipeline_v3/validate_source.py` | Independent source and ADC checks |
| `pipeline_v3/targeted_checks.py` | Aliasing, component isolation and diagnostic checks |
| `pipeline_v3/alignment_checks.py` | Dense-reference reconstruction sensitivity |
| `pipeline_v3/evidence.py` | Run snapshots and archive integrity verification |
| `sites/neural-signal-lab/dist/` | Static interactive website |

## Verify and preview the website

```sh
make check-results
make website
python3 -m http.server 4173 --directory sites/neural-signal-lab/dist
```

Open http://localhost:4173. Controls select recorded cases; they do not run a new simulation. The export verifies the current archives and their source identity before writing browser data.

## Included evidence

`results/current_pipeline/` is the sole pilot result set; `results/current_alignment_validation/` audits all 400 comparisons from that pilot. Fresh exploratory runs go under ignored `results_v3_runs/` directories. Earlier pipeline versions, duplicate downloads, and local presentation screenshots are excluded.

Completed archives include executable build artifacts and source snapshots because their inventories verify the original run. Rebuild with the included C sources on your own platform; numerical agreement is intended, not cross-platform bitwise identity.

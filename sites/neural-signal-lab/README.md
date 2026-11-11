# Recorded neural signal simulation website

Static HTML/CSS/JavaScript in `dist/` presents the current double-precision study. No backend or browser simulation is required.

From the project root:

```sh
make website
python3 -m http.server 4173 --directory sites/neural-signal-lab/dist
```

Open http://localhost:4173. The controls select 400 recorded cases. Overlay and residual plots show 6–7 s; metrics use the full declared valid interval. Delay alignment is an offline diagnostic.

`export_v3.py` verifies `results/current_pipeline/` and `results/current_alignment_validation/`, checks the audit's binding to the pilot manifest, and checks source identity before exporting. `check_v3.py` independently compares every exported trial field and chart window against the included evidence.

The repository contains one current website and no duplicate downloadable evidence bundles. Deployment to a static host is separate from simulation and export. No hosting credentials or project identity are included.

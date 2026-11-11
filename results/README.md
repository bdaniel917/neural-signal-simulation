# Current result evidence

- `current_pipeline/`: the complete 20-seed, two-modulation pilot (400 architecture comparisons).
- `current_alignment_validation/`: independent reconstruction/alignment audit of all 400 pilot comparisons, bound to that pilot's manifest hash.

These are the only published result archives. Each contains immutable source snapshots, exact configurations, environment records, and a completion inventory. Run `make check-results` from the repository root to verify both. Do not modify files within a completed archive.

Fresh runs use unique directories under ignored `results_v3_runs/` by default. To audit a newly generated pilot, run:

```sh
.venv/bin/python pipeline_v3/study.py --validate-only --alignment-archive YOUR_PILOT --output NEW_AUDIT_DIRECTORY
```

Updating the published evidence requires updating both archives together, verifying them, and running `make website`. Source identity and audit-to-pilot binding are checked during export.

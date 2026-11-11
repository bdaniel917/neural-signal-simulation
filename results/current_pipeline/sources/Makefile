CC ?= cc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
export CC CFLAGS
.DEFAULT_GOAL := help

.PHONY: help validate study all-results validate-v3 study-v3 website check-results
help:
	@echo "make validate       Run independent implementation and source checks"
	@echo "make study          Run a fresh 20-seed study"
	@echo "make check-results  Verify the included result archives"
	@echo "make website        Export and check the included website data"
validate:
	$(PYTHON) pipeline_v3/study.py --validate-only
study:
	$(PYTHON) pipeline_v3/study.py --trials 20
all-results: study
validate-v3: validate
study-v3: study
check-results:
	$(PYTHON) pipeline_v3/evidence.py results/current_pipeline
	$(PYTHON) pipeline_v3/evidence.py results/current_alignment_validation
website:
	$(PYTHON) sites/neural-signal-lab/make_flowchart.py
	$(PYTHON) sites/neural-signal-lab/export_v3.py
	$(PYTHON) sites/neural-signal-lab/check_v3.py

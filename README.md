# MATLAB-PHREG — Cox Proportional Hazards (Survival Analysis)

MATLAB implementation of **Cox proportional hazards (PHREG)** for time-to-event data.  
Supports partial likelihood fitting, ties handling (Efron/Breslow), stratification, time-varying covariates, and model diagnostics (Schoenfeld tests, residuals). Clean API, runnable examples, and publication-ready plots.

---


## Features
- **Cox PH (PHREG) fitting** via **partial likelihood** and Newton–Raphson.
- **Ties handling**: **Efron** (default) and **Breslow**.
- **Stratification** by group (piecewise baseline hazards).
- **Time-varying covariates** via start–stop (interval) format.
- **Weights** (case weights) and optional **offset**.
- **Robust standard errors** (optional, cluster-sandwich).
- **Diagnostics**: Schoenfeld residuals & tests, Martingale/Deviance residuals, influence/leverage.
- **Baseline** cumulative hazard and survival; **predicted survival** and **risk scores**.
- **Utilities** for CV-ready, publication-quality plots.
- **Examples** with synthetic and small real-style datasets.

---

## Requirements
- **MATLAB** R2019a or later (older may work; not tested)
- OS: Windows/macOS/Linux


---

## Installation
Clone or download this repository, then add it to your MATLAB path:

```matlab
% From MATLAB:
addpath(genpath('MATLAB-PHREG'))  % replace with the folder you cloned

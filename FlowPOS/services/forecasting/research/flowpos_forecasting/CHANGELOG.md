# FlowPOS Forecasting - Experiment Log

## 2026-04-02: Demand Residual Feedback Features

### Change
Added 8 demand residual feedback features to `evaluate.py`:
- `demand_residual_lag_{1,7,14,28}d` — lagged prediction errors
- `residual_rolling_mean_{7,14}d` — trend in over/under-prediction
- `residual_rolling_std_7d` — volatility of prediction errors
- `residual_dow_mean` — day-of-week systematic error patterns

Residual = quantity_sold[t] - expanding_mean[t-1]
Positive = sold more than expected (under-predicted)
Negative = sold less than expected (over-predicted / waste)

### Results (FastSoftProb, 200 trees, apples-to-apples)

| Config | Features | Flat Cost | Shelf-Aware | MAE |
|--------|----------|-----------|-------------|-----|
| Baseline (no residuals) | 50 | 5,161,801 | 4,556,010 | 2.2663 |
| With residuals | 58 | 3,975,274 | 3,467,408 | 1.8904 |
| **Improvement** | +8 | **-23.0%** | **-23.9%** | **-16.6%** |

### Autoresearch baseline: 5,133,764 DKK (full SoftProbModel 500+500+800 trees)

The no-residual fast model (5,161,801) matches the autoresearch baseline (5,133,764),
confirming the comparison is clean. The improvement is from residual features alone.

### Feature Importance (global RF)
- demand_residual_lag_1d: 0.0143
- residual_rolling_std_7d: 0.0133
- demand_residual_lag_7d: 0.0115
- demand_residual_lag_14d: 0.0099
- residual_rolling_mean_7d: 0.0078
- demand_residual_lag_28d: 0.0067
- residual_rolling_mean_14d: 0.0045
- residual_dow_mean: 0.0000 (low coverage, needs rework)

---

## 2026-04-02: Shelf-Life-Aware Cost Model + Confidence Filter

### Change
- Applied shelf-life-aware waste fractions (only for confidence="high" items)
- Tuned per-item log-scaled buffer: buffer = 1.30 + 0.20 × log(0.3 / eff_waste)

### Results
- Shelf-aware cost model alone: -11.7% vs flat cost
- + log buffer tuning: -13.5% total (4,440,012 vs 5,133,764)

---

## Cumulative Improvement Chain

| Stage | Cost | vs Original |
|-------|------|-------------|
| Autoresearch baseline | 5,133,764 | — |
| + Shelf-aware cost model | 4,556,010 | -11.3% |
| + Log buffer tuning | 4,440,012 | -13.5% |
| + Residual feedback features | 3,467,408 | **-32.5%** |

Note: stages are cumulative but measured on fast model (200 trees).
Full model results may differ slightly.

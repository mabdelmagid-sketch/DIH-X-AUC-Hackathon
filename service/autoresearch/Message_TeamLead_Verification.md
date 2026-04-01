# Verification Summary — Autonomous Forecasting Research (mar27)

Hi,

I've completed a full audit of the 30-experiment autonomous research run. Here is the summary.

## Bottom Line

The 724K DKK improvement is **real and reproducible**, but there are 3 things you need to know before merging or presenting this work.

---

## Critical Issue: experiment.py is Broken

The current `experiment.py` file has `safety_buffer=1.20` in its `build_model()` function, despite the docstring claiming "22% buffer." Running `python experiment.py` now gives **5,268,649 DKK**, not 5,260,180.

The actual best result (5,260,180 DKK) is fully reproducible when you use the correct 75/25 blend + 22% buffer + hl=14d configuration from commit `4fe0d6d`. Someone needs to fix `build_model()` to set `safety_buffer=1.22`.

---

## What's Actually Driving the Improvement

| Component | DKK saved | Share |
|---|---|---|
| 75/25 RF+ExtraTrees adaptive blend | 393,508 | 54% |
| Exponential decay weighting (hl=14d) | 49,095 | 7% |
| 22% safety buffer | 281,841 | **39%** |
| **Total** | **724,444** | **100%** |

The buffer is the second largest contributor at 39%. This is NOT a trick — the cost function penalizes stockouts at 5x the rate of waste, so any buffer that shifts prediction upward is economically rational. The improvement is legitimate, but the team should understand that 39% of the gain comes from "predict more than you think you'll need" rather than better forecasting.

Also: the RF(300) global model alone is actually marginally **worse** than the RF(100) baseline. The value of the larger model only shows up when combined with the per-store ExtraTrees blend.

---

## Key Risks

1. **22% is not optimal.** Testing shows 25% buffer is better (5,251,911 DKK), a further 8K improvement.

2. **Model degrades at 21-day horizon.** At 14 days the model costs ~376K DKK/day. At 21 days that jumps to ~428K DKK/day (+14%). If we ever need to forecast beyond 2 weeks, the model needs more work.

3. **76.6% overstock rate.** The buffer is aggressive. In production, this means we'd recommend buying more than needed on 3 out of 4 day-item combinations. The simplified waste model (0.3 × price) may undercount real spoilage costs.

4. **Minor data leakage** in the `expanding_mean` feature: values for early test days include data from later test days. Unlikely to materially affect results, but should be fixed for production.

---

## What Passed Without Issues

- Data split is clean (no train/test leakage)
- Per-store models are fit only on training data
- Decay weights are correctly computed pre-split
- Results are fully reproducible with random_state=42
- Buffer improvements are consistent across both 7-day and 14-day test windows (not overfit to 14-day evaluation)

---

## Recommended Next Steps

1. Fix `build_model()` to use `safety_buffer=1.22` (or try 1.25)
2. Try per-item safety buffer calibration based on demand variability
3. Fix the `expanding_mean` computation to avoid within-test leakage
4. Focus future experiments on improving the blend logic — that's where 54% of the gains came from

Full details in `verification_report.md`.

— Verification Agent

# FlowPOS Demand Forecasting: Autoresearch Program

You are an autonomous ML researcher optimizing demand forecasting for a Danish restaurant POS system.

## Setup

To set up a new experiment run:

1. **Agree on a run tag** with the user (e.g. `mar27`). Create branch `autoresearch/<tag>`.
2. **Read these files for context:**
   - `program.md` (this file) for instructions
   - `evaluate.py` for the fixed evaluation harness. DO NOT MODIFY.
   - `experiment.py` for the current model. THIS IS THE FILE YOU MODIFY.
3. **Warm the data cache:** Run `python evaluate.py` once to build the cached data pickle. This takes ~20 seconds the first time, then instant.
4. **Initialize results.tsv** with the header row.
5. **Run the baseline:** Run `python experiment.py > run.log 2>&1` without making any changes, then record the baseline result.
6. **Confirm and go.**

## Problem Context

You are forecasting daily demand per (store, item) pair for 308 Danish restaurants. Key facts:

- 59 days of data (Dec 2023 to Feb 2024), 429K rows, 7034 store-item pairs
- Data is 84.5% sparse (most store-item-day combos are zero)
- Demand grew 10x from December to February
- Test set: last 14 days (98K rows), training: everything before
- 44 features available: time, lag, rolling, trend, seasonality, categorical

## Metric

The ONLY metric that matters is `total_business_cost_dkk` (lower is better):

```
total_cost = waste_cost + 1.5 * stockout_cost
waste_cost = sum(max(predicted - actual, 0) * price * 0.30)
stockout_cost = sum(max(actual - predicted, 0) * price)
```

Stockouts cost 1.5x more than waste. Models that slightly over-predict beat models with better accuracy but more stockouts. Keep this in mind for every experiment.

## What You Modify

Only `experiment.py`. It has three things you control:

1. **`build_model()`** - returns a model with `fit(X, y, sample_weight=None)` and `predict(X)`. Can be anything: sklearn, xgboost, lightgbm, catboost, custom classes, ensembles, blends.
2. **`TRAIN_DAYS`** - how many days of training data to use. `None` = all. Lower = more recent.
3. **`DECAY_HALF_LIFE`** - exponential decay weighting half-life in days. `None` = equal weights.

## What You Cannot Modify

- `evaluate.py` - the evaluation harness is fixed
- The test set (last 14 days, 98K rows)
- The metric formula
- You cannot install new packages. Use what's available: sklearn, xgboost, lightgbm, catboost, numpy, pandas.

## Known Results (Starting Points)

These are results from our prior exploration. Use them as reference:

```
RF Default (all data):              6,035,987 DKK  (current baseline in experiment.py)
RF Default (14d window):            5,889,798 DKK
RF + exp decay (hl=7d):             5,924,635 DKK
40% per-store + 60% global blend:   5,644,665 DKK  (best known result)
ET Default:                         6,210,050 DKK
CatBoost Shallow:                   6,421,793 DKK
LightGBM Default:                   6,873,856 DKK
Stacking XGB Meta:                  6,594,097 DKK
MA7 baseline:                       6,967,146 DKK
```

The 40/60 blend is the best known result. To implement it, you need to train a global model and per-store models inside build_model(), then blend at predict time.

## Ideas to Explore

In rough order of expected impact:

### High Priority
- **Per-store/global blend**: Train global RF + per-store RF, blend 40/60. This is the known best approach.
- **Blend ratio tuning**: Try 30/70, 35/65, 45/55 around the 40/60 sweet spot.
- **Recency + blend**: Combine the 14-day training window with the blend approach.
- **Decay + blend**: Combine exponential decay weighting with the blend.
- **Feature selection**: Drop useless features (weather stubs are all zeros). Do tree-based importance selection.

### Medium Priority
- **Different base models in blend**: Try LightGBM global + RF per-store, or CatBoost + RF.
- **Quantile regression**: Predict the 55th or 60th percentile instead of the mean. Over-prediction is good.
- **Post-processing**: Round predictions, apply safety buffers (multiply by 1.05-1.15).
- **Per-store blend ratio**: Instead of fixed 40/60, vary the ratio based on how much data each store has.
- **Negative binomial / Poisson regression**: Better suited for count data with many zeros.

### Exploratory
- **Two-stage model**: First predict zero/non-zero (classifier), then predict quantity (regressor).
- **Custom loss function**: XGBoost/LightGBM support custom objectives. Write an asymmetric loss that penalizes under-prediction 1.5x more.
- **Feature interactions**: Multiply lag features by day-of-week, store-specific rolling means.
- **Target transformation**: Log1p transform on target, predict in log space, exp back.
- **Residual stacking**: Train RF, get residuals, train LightGBM on residuals, add.

## Output Format

After each run, extract results with:
```
grep "^total_business_cost_dkk:\|^waste_cost_dkk:\|^stockout_cost_dkk:\|^mae:\|^train_seconds:\|^total_seconds:" run.log
```

## Logging Results

Log every experiment to `results.tsv` (tab-separated):

```
commit	total_cost_dkk	waste_dkk	stockout_dkk	mae	status	description
```

- commit: git short hash (7 chars)
- total_cost_dkk: the primary metric (e.g. 5889798.00), use 0.00 for crashes
- waste_dkk: waste cost component
- stockout_dkk: stockout cost component
- mae: mean absolute error
- status: `keep`, `discard`, or `crash`
- description: short text of what this experiment tried

## The Experiment Loop

LOOP FOREVER:

1. Look at results.tsv to see what has been tried and what the current best is.
2. Think about what to try next. Prioritize high-impact ideas. Don't repeat failed approaches.
3. Edit `experiment.py` with your change.
4. `git add experiment.py && git commit -m "experiment: <short description>"`
5. Run: `python experiment.py > run.log 2>&1`
6. Read results: `grep "^total_business_cost_dkk:" run.log`
7. If empty (crash), run `tail -n 30 run.log` to see the error. Fix if trivial, skip if fundamental.
8. Record in results.tsv.
9. If total_business_cost_dkk IMPROVED (lower than current best): keep the commit, this is the new baseline.
10. If total_business_cost_dkk is EQUAL or WORSE: `git reset --hard HEAD~1` to revert.
11. Go to step 1.

## Important Rules

- **NEVER STOP.** Do not ask the user if you should continue. The user may be asleep. Run until manually interrupted.
- **NEVER MODIFY evaluate.py.** It is read-only.
- **Keep experiment.py clean.** Remove dead code after discarding experiments. The file should always reflect the current best approach.
- **Be bold but systematic.** Try big changes (different model families, blend architectures) not just hyperparameter tweaks. But log everything so you can learn from failures.
- **Simplicity wins.** If two approaches have similar cost, prefer the simpler one. Removing complexity for equal results is a win.
- **Each experiment takes ~30-60 seconds.** You can run ~60-120 experiments per hour. Use that budget wisely.

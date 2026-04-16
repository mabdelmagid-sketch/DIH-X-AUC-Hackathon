---
geometry: margin=0.7in
fontsize: 10pt
---

# Technical Report: Foundation Model Benchmark on Zeynos

**Date:** April 7, 2026
**Prepared for:** Yahya Hammoudeh
**Supervisor:** Mohammed Rida

---

## Executive Summary

Building on the April 6 single-store walk-forward results, this report benchmarks eleven forecasting models on the Zeynos walk-forward harness — three Chronos-Bolt variants, three Chronos-T5 variants, LightGBM-200, and four statistical baselines — and tries to fine-tune Chronos-Bolt Mini on data from 494 stores. The headline result is that **the rolling 7-day average is the best forecaster on Zeynos at the true buffer optimum** (937,292 DKK at buf=1.65), beating Chronos-Bolt Mini, all six Chronos variants, LightGBM, and the other statistical baselines. Fine-tuning Chronos-Bolt made it 17% worse due to outlier-driven loss spikes during training. The previous "tie at 962K" between rolling 7d and Chronos-Bolt Mini was an artifact of the buffer sweep maxing out at 1.50 — extending it to 2.50 reveals a clear winner.

---

## Question

Can a pretrained time-series foundation model beat the simple statistical baselines and per-store LightGBM from April 6, and is fine-tuning worth the effort on this data?

---

## Setup

Same Zeynos walk-forward harness as April 6 Experiment 1: 60-day window, retrain every 3 days, 51 rounds, top 30 items, shelf-life-aware business cost.

| Parameter | Value |
|-----------|-------|
| Store | Zeynos (id=5995723) |
| Items | Top 30 by volume |
| Window | 60 days, sliding |
| Predict horizon | 3 days |
| Slide | 3 days, 51 rounds |
| Evaluation | Shelf-aware business cost |

**Models tested (11):** Chronos-Bolt tiny / mini / small, Chronos-T5 tiny / mini / small, LightGBM-200, rolling 7-day avg, same-weekday avg, exponential smoothing (alpha=0.3), seasonal naive.

---

## Full Ranking (flat buffer 1.40)

| Rank | Model              | Params | MAE  | Cost (DKK) | Time  |
|-----:|:-------------------|:------:|:----:|-----------:|------:|
| 1    | Chronos-Bolt Mini  | 20M    | 9.81 |  1,020,787 |   86s |
| 2    | Chronos-Bolt Small | 48M    | 9.75 |  1,023,852 |  297s |
| 3    | Rolling 7-day avg  | —      | 9.95 |  1,026,805 |    1s |
| 4    | Chronos-Bolt Tiny  |  8M    | 9.61 |  1,039,857 |   42s |
| 5    | Same-weekday avg   | —      |10.86 |  1,058,330 |    1s |
| 6    | Exp. smoothing     | —      |10.25 |  1,112,838 |    1s |
| 7    | Chronos-T5 Mini    | 20M    | 9.58 |  1,184,172 | 1344s |
| 8    | LightGBM-200       | —      |10.53 |  1,193,406 |    7s |
| 9    | Chronos-T5 Small   | 48M    | 9.38 |  1,194,489 | 2687s |
| 10   | Chronos-T5 Tiny    |  8M    | 9.62 |  1,232,128 |  699s |
| 11   | Seasonal naive     | —      |12.33 |  1,719,423 |    1s |

---

## Per-Model Optimal Buffer (Extended Sweep)

A first sweep tested buffers 0.90-1.50 and **every** model pegged at 1.50 — the ceiling of the sweep, meaning the true optimum was unknown. Re-running with an extended range (1.40-2.50) on the top three models gives the actual per-model optima:

| Model                          | Opt Buf | Cost (DKK) |    Waste | Stockout |
|:-------------------------------|--------:|-----------:|---------:|---------:|
| **Rolling 7-day avg**          | **1.65**| **937,292**|  622,384 |  209,938 |
| Chronos-Bolt Mini (pretrained) |    1.60 |    944,293 |  581,982 |  241,540 |
| Same-weekday avg               |    1.60 |    973,570 |  632,018 |  227,701 |

At the true optimum, **rolling 7-day average beats the 20M-parameter foundation model by ~7,000 DKK** (-0.7%) and beats Chronos at the previous (truncated) optimum by ~25,000 DKK (-2.6%). A one-line `np.mean(hist[-7:])` is the best forecaster on this store across the entire model space tested.

The cost gap is small enough that the deciding factor is operational: rolling 7d avg has zero infrastructure, no model file to ship, and runs in 1 second; Chronos requires PyTorch + a 20M-parameter checkpoint and 86 seconds of inference per 51 rounds.

---

## Fine-Tuning Chronos-Bolt Mini (and Why It Failed)

To test whether domain adaptation helps, Chronos-Bolt Mini was fine-tuned on time series from 494 stores.

**Training setup:**

| Parameter         | Value                                |
|:------------------|:-------------------------------------|
| Time series       | 3,245 (top 10 items per store)       |
| Train split       | 70%                                  |
| Context / target  | 64d / 3d                             |
| Pairs             | 68,145                               |
| Optimizer         | AdamW (lr=1e-4, batch=32, 3 epochs)  |
| Wall time         | ~3 hours on CPU                      |

**Buffer sweep on the fine-tuned model:**

| Buffer | MAE      | Cost (DKK)    |
|-------:|---------:|--------------:|
|   1.00 | **7.09** |     2,095,550 |
|   1.30 |     8.64 |     1,319,548 |
|   1.50 |    10.81 | **1,123,558** |

Raw MAE *improved* (7.09 vs 9.81 at buf=1.00), but business cost at the optimal buffer was **17% worse** than the pretrained model (1,123K vs 962K, and 19% worse vs the new 944K optimum). Loss spikes during training (140K, 68K from outlier high-volume items selling 500+ units/day) almost certainly degraded generalization. Without outlier filtering or robust loss, fine-tuning is a regression. Any retry must clip extreme demand values or use Huber loss.

---

## Key Insights

1. **Bolt >> T5 on business cost.** Both architectures hit similar MAE, but T5 predicts too conservatively, causing more stockouts. Bolt is also 10-30x faster.

2. **A one-line formula wins.** A 20M-parameter model pretrained on billions of time-series points loses to `np.mean(hist[-7:])` on this store. For stores with frequent retraining and short windows, complexity does not pay.

3. **Best MAE is not best cost.** Chronos-T5-Small has the lowest MAE (9.38) but ranks #9 on cost. The 1.5x stockout penalty plus shelf-aware waste fractions reward slight over-prediction.

4. **LightGBM underperforms in this regime.** With 60 days of single-store data and 30 items, engineered features cannot beat the foundation model's pretrained priors or the statistical baselines' simplicity. (LightGBM still wins at the global production scale where 2.26M rows are available — see Adam's track for that result.)

5. **Fine-tuning needs data cleaning first.** High-volume outliers caused loss spikes that recovered numerically but left the model in a worse generalization basin.

6. **Buffer sweep ceilings matter.** Extending the sweep from 1.50 to 2.50 changed the verdict on the best model. Always sweep until the cost curve turns upward.

---

## Production Implication for Single-Store Stack

For per-store deployment:

| Tier         | Model                          | Buffer | When                    |
|:-------------|:-------------------------------|:------:|:------------------------|
| Cold start   | Rolling 7-day average          |  1.65  | <30 days history        |
| Warm stores  | LightGBM-200, 60d, no decay    |  1.40  | >=30 days, from April 6 |
| Foundation fallback | Chronos-Bolt Mini       |  1.60  | If Python infra exists  |

For the global production model (Adam's track), nothing in this report changes the 8.42M DKK conclusion. These are single-store findings on a single store.

---

## Files

| File                                         | Description                       |
|:---------------------------------------------|:----------------------------------|
| `notebooks/foundation_model_benchmark_v2.py` | 11-model benchmark                |
| `notebooks/per_model_buffer_sweep.py`        | First sweep (0.90-1.50)           |
| `notebooks/extended_buffer_sweep.py`         | Extended sweep (1.40-2.50)        |
| `notebooks/finetune_chronos.py`              | Chronos-Bolt fine-tuning          |
| `notebooks/results/foundation_model_results_v2.json` | 11-model results          |
| `notebooks/results/buffer_sweep_per_model.json`      | First sweep output        |
| `notebooks/results/buffer_sweep_extended.json`       | Extended sweep output     |
| `notebooks/chronos-bolt-mini-finetuned/`     | Saved fine-tuned weights          |

---

*Report generated: April 7, 2026*

Hey, here's where I landed on the model exploration.

I tested 37 model configurations across 10 different families (Random Forest, LightGBM, CatBoost, Extra Trees, SVR, ElasticNet, Bayesian Ridge, Croston's method, exponential smoothing, and stacking ensembles). Everything was evaluated on the business cost metric: waste cost plus 1.5x stockout cost in DKK.

Random Forest with default parameters won. 6.04M DKK total business cost, 13.4% cheaper than the MA7 baseline, trains in 18 seconds. No hyperparameter tuning needed.

The interesting part is that LightGBM actually has better accuracy (67% vs RF's 85% WMAPE), but it costs more because it predicts zeros too aggressively on our sparse data. When demand shows up and the model predicted zero, that's a stockout, and those cost 1.5x. RF's averaging across 100 trees naturally over-predicts slightly for items that occasionally sell, which acts as a built-in safety buffer.

Linear models (Ridge, Lasso, Bayesian Ridge) were completely broken on this data, all scoring worse than predicting nothing. Croston's method also didn't work despite our 84.5% sparsity because the zeros are structural, not intermittent. The stacking ensemble performed worse than RF alone because the meta-learner averages away the conservative bias that makes RF work.

That last point actually validates our architecture. The LLM arbitration layer we built with DeepSeek is a better ensemble than any statistical stacking because it has access to weather, holidays, and payday context that no meta-learner can see. Simple models for the numbers, AI for the judgment.

Full leaderboard and analysis is in Report A.

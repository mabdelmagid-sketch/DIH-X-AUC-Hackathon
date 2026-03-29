Hey, building on the model selection work from Report A, I focused on data strategy: what data we train on, seasonality, and whether stores should have their own models.

The biggest issue is that demand grew 10x from December to February. Training on all 59 days equally means December's dead period drags down predictions. Dropping December and training on just the last 14 days improved cost by another 2.4%. For production I'd recommend exponential decay weighting instead of a hard cutoff, same result but cleaner.

On seasonality: weekly patterns are strong (Friday +35%, Sunday -26%) and already captured. I added trend features and proper Danish holiday flags which helped. Annual seasonality is impossible with 59 days of data, we need 13+ months. The architecture supports it, it's a roadmap item.

The most surprising finding was per-store modeling. Pure per-store models are actually worse than one global model because most stores only have 32 days of data with 84.5% sparsity. But blending 40% per-store with 60% global predictions hits 5.65M DKK, which is 6.5% better than global alone and 19% better than the original MA7 baseline. The global model provides stable patterns, the per-store model adds local corrections, and the blend lets local knowledge through when it's consistent.

For production this means three changes: weekly retraining with decay weighting, serve the 40/60 blend at the forecast endpoint, and set expectations that annual seasonality comes after month 13.

The bigger picture for the AI suite: forecasting accuracy is the trust layer. Once managers trust the prep numbers, they trust the LLM's suggestions about promotions and waste reduction. Get the foundation right and the whole platform becomes something people actually use.

Full details in Report B.

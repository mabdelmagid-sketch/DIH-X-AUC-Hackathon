"""
Experiment file for autoresearch. THIS FILE IS MODIFIED BY THE AGENT.

Current best: RF Default = 6,035,987 DKK total business cost.
Previous best with 40/60 blend: ~5,645,000 DKK.

The agent modifies this file to try different:
- Model architectures (RF, XGBoost, LightGBM, CatBoost, ensembles, blends)
- Hyperparameters (n_estimators, max_depth, learning_rate, etc.)
- Feature subsets (drop features, add interactions, select top-k)
- Training strategies (recency windows, decay weighting)
- Ensemble methods (blending, stacking, voting)
- Post-processing (rounding, clipping, safety buffers)

Everything below is fair game. The only constraint is that build_model()
returns an object with fit(X, y, sample_weight=None) and predict(X) methods.
"""

import numpy as np
from sklearn.ensemble import RandomForestRegressor


# =============================================================================
# MODEL DEFINITION (agent modifies this)
# =============================================================================

def build_model():
    """Return a model instance with fit() and predict() methods."""
    return RandomForestRegressor(
        n_estimators=100,
        random_state=42,
        n_jobs=-1,
    )


# =============================================================================
# TRAINING CONFIG (agent modifies this)
# =============================================================================

# How many days of training data to use. None = all available (~47 days).
# Lower values = more recent data only. Our tests showed 14-21 days is optimal.
TRAIN_DAYS = None

# Exponential decay half-life in days. None = no decay (equal weights).
# 7 = data from 1 week ago counts 50%, 2 weeks ago counts 25%, etc.
DECAY_HALF_LIFE = None


# =============================================================================
# ENTRY POINT (do not modify the interface, only the contents above)
# =============================================================================

if __name__ == "__main__":
    from evaluate import run_experiment, print_results

    results = run_experiment(
        build_model_fn=build_model,
        description="baseline RF default",
        train_days=TRAIN_DAYS,
        decay_half_life=DECAY_HALF_LIFE,
    )
    print_results(results)

"""
Checks 5 & 6: Improvement Attribution and Buffer Gaming Analysis.
Measures how much each component contributes to the 724K DKK improvement.
"""
import sys
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting/autoresearch")

import numpy as np
import inspect
from evaluate import get_data, get_train_test, evaluate as eval_fn
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor

TRAIN_DAYS = None
DECAY_HALF_LIFE = 14

data = get_data()

# Standard 14-day split WITH decay
X_train, y_train, X_test, y_test, prices, weights = get_train_test(
    data, test_days=14, train_days=TRAIN_DAYS, decay_half_life=DECAY_HALF_LIFE
)
# Also without decay (for baseline comparison)
X_train_nd, y_train_nd, X_test_nd, y_test_nd, prices_nd, _ = get_train_test(
    data, test_days=14, train_days=None, decay_half_life=None
)


# ---- Component 1: Pure RF baseline (100 trees, no decay, no blend, no buffer) ----
print("=== Check 5: Improvement Attribution ===\n")

print("Step 1: Pure RF baseline (100 trees, no decay, no blend, no buffer)...")
rf_base = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
rf_base.fit(X_train_nd, y_train_nd)
preds_base = rf_base.predict(X_test_nd)
preds_base = np.clip(preds_base, 0, None)
r_base = eval_fn(y_test_nd, preds_base, prices_nd)
print(f"  Baseline RF(100), no decay, no blend, no buffer: {r_base['total_business_cost_dkk']:>12,.2f} DKK  (target ~5,984,624)")

# ---- Component 2: RF(300,min_leaf=2) global, no blend, no decay, no buffer ----
print("Step 2: RF(300,min_leaf=2) global only, no blend, no decay, no buffer...")
rf300 = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1, min_samples_leaf=2)
rf300.fit(X_train_nd, y_train_nd)
preds_rf300 = np.clip(rf300.predict(X_test_nd), 0, None)
r_rf300 = eval_fn(y_test_nd, preds_rf300, prices_nd)
print(f"  RF(300,min_leaf=2) global only, no extras: {r_rf300['total_business_cost_dkk']:>12,.2f} DKK")

# ---- Component 3: 75/25 blend, no decay, no buffer ----
print("Step 3: 75/25 adaptive blend, no decay, no buffer...")

class BlendOnly:
    def __init__(self):
        self.base_global_weight = 0.75
        self.min_store_samples = 200
        self.random_state = 42
        self.global_model = None
        self.store_models = {}
        self.store_weights = {}
        self.feature_cols_ = None

    def fit(self, X, y, sample_weight=None):
        self.feature_cols_ = list(X.columns)
        self.global_model = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1, min_samples_leaf=2)
        self.global_model.fit(X, y)
        X_arr = X.values; y_arr = np.array(y)
        store_col_idx = self.feature_cols_.index('place_id_encoded')
        store_ids = X_arr[:, store_col_idx]
        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            X_s = X_arr[mask]; y_s = y_arr[mask]
            if len(y_s) < 10:
                self.store_weights[store_id] = 1.0
                continue
            sm = ExtraTreesRegressor(n_estimators=100, random_state=42, n_jobs=1)
            sm.fit(X_s, y_s)
            self.store_models[store_id] = sm
            frac = min(len(y_s) / self.min_store_samples, 1.0)
            self.store_weights[store_id] = 1.0 - frac * (1.0 - self.base_global_weight)
        return self

    def predict(self, X):
        X_arr = X.values
        global_preds = self.global_model.predict(X_arr)
        result = global_preds.copy()
        store_col_idx = self.feature_cols_.index('place_id_encoded')
        store_ids = X_arr[:, store_col_idx]
        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            if store_id not in self.store_models:
                continue
            gw = self.store_weights.get(store_id, self.base_global_weight)
            sw = 1.0 - gw
            sp = self.store_models[store_id].predict(X_arr[mask])
            result[mask] = sw * sp + gw * global_preds[mask]
        return np.clip(result, 0, None)

blend_only = BlendOnly()
blend_only.fit(X_train_nd, y_train_nd)
preds_blend = blend_only.predict(X_test_nd)
r_blend = eval_fn(y_test_nd, preds_blend, prices_nd)
print(f"  75/25 blend, no decay, no buffer: {r_blend['total_business_cost_dkk']:>12,.2f} DKK")

# ---- Component 4: 75/25 blend + decay, no buffer ----
print("Step 4: 75/25 blend + decay (hl=14d), no buffer...")

class BlendDecay:
    def __init__(self):
        self.base_global_weight = 0.75
        self.min_store_samples = 200
        self.random_state = 42
        self.global_model = None
        self.store_models = {}
        self.store_weights = {}
        self.feature_cols_ = None

    def fit(self, X, y, sample_weight=None):
        self.feature_cols_ = list(X.columns)
        self.global_model = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1, min_samples_leaf=2)
        if sample_weight is not None:
            self.global_model.fit(X, y, sample_weight=sample_weight)
        else:
            self.global_model.fit(X, y)
        X_arr = X.values; y_arr = np.array(y)
        store_col_idx = self.feature_cols_.index('place_id_encoded')
        store_ids = X_arr[:, store_col_idx]
        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            X_s = X_arr[mask]; y_s = y_arr[mask]
            w_s = sample_weight[mask] if sample_weight is not None else None
            if len(y_s) < 10:
                self.store_weights[store_id] = 1.0
                continue
            sm = ExtraTreesRegressor(n_estimators=100, random_state=42, n_jobs=1)
            if w_s is not None:
                sm.fit(X_s, y_s, sample_weight=w_s)
            else:
                sm.fit(X_s, y_s)
            self.store_models[store_id] = sm
            frac = min(len(y_s) / self.min_store_samples, 1.0)
            self.store_weights[store_id] = 1.0 - frac * (1.0 - self.base_global_weight)
        return self

    def predict(self, X):
        X_arr = X.values
        global_preds = self.global_model.predict(X_arr)
        result = global_preds.copy()
        store_col_idx = self.feature_cols_.index('place_id_encoded')
        store_ids = X_arr[:, store_col_idx]
        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            if store_id not in self.store_models:
                continue
            gw = self.store_weights.get(store_id, self.base_global_weight)
            sw = 1.0 - gw
            sp = self.store_models[store_id].predict(X_arr[mask])
            result[mask] = sw * sp + gw * global_preds[mask]
        return np.clip(result, 0, None)

blend_decay = BlendDecay()
blend_decay.fit(X_train, y_train, sample_weight=weights)
preds_blend_decay = blend_decay.predict(X_test)
r_blend_decay = eval_fn(y_test, preds_blend_decay, prices)
print(f"  75/25 blend + decay, no buffer: {r_blend_decay['total_business_cost_dkk']:>12,.2f} DKK")

# ---- Component 5: Full best (blend + decay + 22% buffer) ----
print("Step 5: Full best config (blend + decay + 22% buffer)...")
preds_full = np.clip(preds_blend_decay * 1.22, 0, None)
r_full = eval_fn(y_test, preds_full, prices)
print(f"  75/25 blend + decay + 22% buffer: {r_full['total_business_cost_dkk']:>12,.2f} DKK")

print()
print("--- Attribution Summary ---")
baseline_cost = r_base['total_business_cost_dkk']
print(f"Baseline RF(100), no extras:         {baseline_cost:>12,.2f} DKK")
print(f"After RF(300,min_leaf=2):             {r_rf300['total_business_cost_dkk']:>12,.2f} DKK  (delta: {r_rf300['total_business_cost_dkk']-baseline_cost:+,.0f})")
print(f"After + 75/25 blend (no decay):       {r_blend['total_business_cost_dkk']:>12,.2f} DKK  (delta vs baseline: {r_blend['total_business_cost_dkk']-baseline_cost:+,.0f})")
print(f"After + decay hl=14d (no buffer):     {r_blend_decay['total_business_cost_dkk']:>12,.2f} DKK  (delta vs baseline: {r_blend_decay['total_business_cost_dkk']-baseline_cost:+,.0f})")
print(f"After + 22% buffer (FULL BEST):       {r_full['total_business_cost_dkk']:>12,.2f} DKK  (delta vs baseline: {r_full['total_business_cost_dkk']-baseline_cost:+,.0f})")
print()
blend_contribution = r_blend['total_business_cost_dkk'] - r_rf300['total_business_cost_dkk']
decay_contribution = r_blend_decay['total_business_cost_dkk'] - r_blend['total_business_cost_dkk']
buffer_contribution = r_full['total_business_cost_dkk'] - r_blend_decay['total_business_cost_dkk']
model_contribution = r_rf300['total_business_cost_dkk'] - baseline_cost
total_improvement = r_full['total_business_cost_dkk'] - baseline_cost
print(f"Model upgrade (RF100->RF300,ml=2):   {model_contribution:>+12,.0f} DKK")
print(f"Blend contribution:                   {blend_contribution:>+12,.0f} DKK")
print(f"Decay contribution:                   {decay_contribution:>+12,.0f} DKK")
print(f"Buffer contribution:                  {buffer_contribution:>+12,.0f} DKK")
print(f"Total improvement:                    {total_improvement:>+12,.0f} DKK")
if total_improvement != 0:
    print(f"  -> Buffer is {buffer_contribution/total_improvement*100:.1f}% of total improvement")
    print(f"  -> True modeling is {(total_improvement - buffer_contribution)/total_improvement*100:.1f}% of total improvement")

print()
print("=== Check 6: Buffer Gaming Analysis ===")
# What does no-buffer look like vs buffer?
r_no_buf = r_blend_decay
r_with_buf = r_full
print(f"Without buffer (75/25 blend + decay):")
print(f"  cost: {r_no_buf['total_business_cost_dkk']:>12,.2f} DKK")
print(f"  waste: {r_no_buf['waste_cost_dkk']:>12,.2f} DKK")
print(f"  stockout: {r_no_buf['stockout_cost_dkk']:>12,.2f} DKK")
print(f"  overstock_days%:  {r_no_buf['overstock_days_pct']:.1f}%")
print(f"  understock_days%: {r_no_buf['understock_days_pct']:.1f}%")
print()
print(f"With 22% buffer:")
print(f"  cost: {r_with_buf['total_business_cost_dkk']:>12,.2f} DKK")
print(f"  waste: {r_with_buf['waste_cost_dkk']:>12,.2f} DKK")
print(f"  stockout: {r_with_buf['stockout_cost_dkk']:>12,.2f} DKK")
print(f"  overstock_days%:  {r_with_buf['overstock_days_pct']:.1f}%")
print(f"  understock_days%: {r_with_buf['understock_days_pct']:.1f}%")
print()
print(f"Buffer effect: waste +{r_with_buf['waste_cost_dkk']-r_no_buf['waste_cost_dkk']:,.0f} DKK  |  stockout {r_with_buf['stockout_cost_dkk']-r_no_buf['stockout_cost_dkk']:+,.0f} DKK")
print(f"Buffer net DKK change: {r_with_buf['total_business_cost_dkk']-r_no_buf['total_business_cost_dkk']:+,.0f} DKK")
print()
print("Note: Stockout penalty is 1.5x price, waste cost is 0.3x price.")
print("If understock% >> overstock%, adding buffer reduces the 1.5x penalty at lower cost than it adds waste.")

print("\nDone.")

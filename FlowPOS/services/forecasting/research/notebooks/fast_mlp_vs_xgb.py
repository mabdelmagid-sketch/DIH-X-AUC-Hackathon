"""
Simple PyTorch MLP trained on the SAME 27 features as XGB.

Apples-to-apples neural baseline: if a 3-layer MLP with the same input data
can't beat XGB, neural methods are simply inappropriate for this problem.

Expected: MLP loses by 3-10% (neural nets usually need more data / structure).
"""
import os, time, json, sqlite3, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from scipy.optimize import minimize_scalar
warnings.filterwarnings("ignore")

DB_PATH = "data/raw/production.db"
SHELF_LIFE_PATH = "data/raw/production_shelf_life_final.csv"
LOCAL_BASE = "/home/yahyahammoudeh/Documents/loving loyalty internship"
if os.path.exists(os.path.join(LOCAL_BASE, DB_PATH)):
    DB_PATH = os.path.join(LOCAL_BASE, DB_PATH)
    SHELF_LIFE_PATH = os.path.join(LOCAL_BASE, SHELF_LIFE_PATH)

RESULTS_DIR = Path("results_mlp")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_ITEMS = 30; TEST_DAYS = 14; VAL_DAYS = 14
WASTE_FRACTION = 0.3; STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30; SEED = 42; NON_FOOD_SHELF_LIFE = 9999.0
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"MLP experiment, device={DEVICE}")
t0 = time.time()

# ==== LOAD DATA (same as other scripts) ====
conn = sqlite3.connect(DB_PATH)
orders = pd.read_sql("SELECT id, place_id, created, status FROM fct_orders", conn)
items = pd.read_sql("SELECT order_id, item_id, quantity, price FROM fct_order_items", conn)
menu = pd.read_sql("SELECT id, price FROM dim_menu_items", conn)
conn.close()
orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
items["price"] = pd.to_numeric(items["price"], errors="coerce")
menu["price"] = pd.to_numeric(menu["price"], errors="coerce")
orders = orders[orders["status"] == "Closed"].copy()
orders["created_dt"] = pd.to_datetime(orders["created"], unit="s", errors="coerce")
orders = orders.dropna(subset=["created_dt"])
orders["date"] = orders["created_dt"].dt.normalize()

shelf_df = pd.read_csv(SHELF_LIFE_PATH)
SHELF_LOOKUP = {str(r["item_id"]): (
    float(r["shelf_life_days"]) if pd.notna(r["shelf_life_days"]) else 3.0,
    float(r["avg_gap_days"]) if pd.notna(r["avg_gap_days"]) else 1.0,
) for _, r in shelf_df.iterrows()}

merged = orders[["id","place_id","date"]].merge(items, left_on="id", right_on="order_id", how="inner")
merged["item_id"] = merged["item_id"].astype(str)
merged["price"] = merged["price"].fillna(merged["item_id"].map(
    menu.assign(id=menu["id"].astype(str)).set_index("id")["price"]))
daily = merged.groupby(["date","place_id","item_id"], observed=True).agg(
    quantity_sold=("quantity","sum"), item_price=("price","mean")).reset_index()
store_days = daily.groupby("place_id")["date"].nunique()
valid_stores = store_days[store_days >= MIN_STORE_DAYS].index
daily = daily[daily["place_id"].isin(valid_stores)].copy()
top_items = (daily.groupby(["place_id","item_id"], observed=True)["quantity_sold"].sum()
             .reset_index().sort_values(["place_id","quantity_sold"], ascending=[True,False])
             .groupby("place_id").head(TOP_N_ITEMS))
pairs = set(zip(top_items["place_id"], top_items["item_id"]))
daily = daily[daily.apply(lambda r: (r["place_id"], r["item_id"]) in pairs, axis=1)].copy()
all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
grid = pd.concat([pd.DataFrame({"date": all_dates, "place_id": pid, "item_id": iid})
                  for (pid, iid), _ in daily.groupby(["place_id","item_id"], observed=True)], ignore_index=True)
df = grid.merge(daily, on=["date","place_id","item_id"], how="left")
df["quantity_sold"] = df["quantity_sold"].fillna(0)
modal = daily.groupby(["place_id","item_id"], observed=True)["item_price"].agg(
    lambda s: s.mode().iloc[0] if len(s.mode())>0 else s.mean()).reset_index().rename(columns={"item_price":"modal_price"})
df = df.merge(modal, on=["place_id","item_id"], how="left")
df["item_price"] = df["item_price"].fillna(df["modal_price"])
df["item_price"] = df["item_price"].fillna(df.groupby("item_id")["item_price"].transform("mean"))
df["item_price"] = df["item_price"].fillna(50.0)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["place_id","item_id","date"]).reset_index(drop=True)

grp = ["place_id","item_id"]
df["dow"] = df["date"].dt.dayofweek
df["is_weekend"] = (df["dow"] >= 5).astype(int)
df["dom"] = df["date"].dt.day
df["month"] = df["date"].dt.month
for lag in [1,2,3,7,14,28]:
    df[f"lag_{lag}"] = df.groupby(grp, observed=True)["quantity_sold"].shift(lag)
shifted = df.groupby(grp, observed=True)["quantity_sold"].shift(1)
for w in [3,7,14,28]:
    df[f"rmean_{w}"] = shifted.groupby([df["place_id"], df["item_id"]]).transform(lambda x: x.rolling(w, min_periods=1).mean())
    df[f"rstd_{w}"] = shifted.groupby([df["place_id"], df["item_id"]]).transform(lambda x: x.rolling(w, min_periods=1).std())

def get_shelf(iid):
    sl, ag = SHELF_LOOKUP.get(str(iid), (3.0, 1.0))
    per = 1.0 / max(sl, 0.5)
    storage = 3 if sl >= NON_FOOD_SHELF_LIFE else (0 if sl <= 3 else 1 if sl <= 14 else 2)
    eff = 0.0 if sl >= NON_FOOD_SHELF_LIFE else WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))
    return min(sl, 365.0), ag, per, storage, eff, np.log1p(sl), min(ag, 30.0)
shelf_cache = {iid: get_shelf(iid) for iid in df["item_id"].unique()}
for idx, col in enumerate(["sl","ag","per","stype","effw","logsl","turn"]):
    df[col] = df["item_id"].map(lambda iid: shelf_cache[iid][idx])
df["shelf_x_r7"] = df["logsl"] * df["rmean_7"].fillna(0)
df["per_x_we"] = df["per"] * df["is_weekend"]

max_date = df["date"].max()
test_cut = max_date - pd.Timedelta(days=TEST_DAYS)
val_cut = test_cut - pd.Timedelta(days=VAL_DAYS)
train_df = df[df["date"] <= val_cut].copy()
val_df = df[(df["date"] > val_cut) & (df["date"] <= test_cut)].copy()
test_df = df[df["date"] > test_cut].copy()
feat = [c for c in df.columns if c not in {"date","place_id","item_id","quantity_sold","modal_price","item_price"}]
print(f"Data prep: {time.time()-t0:.1f}s, {len(feat)} features")

X_train = train_df[feat].fillna(0).values.astype(np.float32)
y_train = train_df["quantity_sold"].values.astype(np.float32)
X_val = val_df[feat].fillna(0).values.astype(np.float32)
y_val = val_df["quantity_sold"].values.astype(np.float32)
X_test = test_df[feat].fillna(0).values.astype(np.float32)
y_test = test_df["quantity_sold"].values.astype(np.float32)

# Normalize features
mean = X_train.mean(axis=0)
std = X_train.std(axis=0) + 1e-6
X_train = (X_train - mean) / std
X_val = (X_val - mean) / std
X_test = (X_test - mean) / std

# log1p target (standard for count regression)
y_train_t = np.log1p(y_train)

# ==== MLP ====
class MLP(nn.Module):
    def __init__(self, n_in, hidden=512, layers=3, dropout=0.1):
        super().__init__()
        mods = []
        d = n_in
        for _ in range(layers):
            mods.append(nn.Linear(d, hidden))
            mods.append(nn.SiLU())
            mods.append(nn.Dropout(dropout))
            d = hidden
        mods.append(nn.Linear(d, 1))
        self.net = nn.Sequential(*mods)
    def forward(self, x):
        return self.net(x).squeeze(-1)

model = MLP(len(feat), hidden=512, layers=3, dropout=0.1).to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=10)

X_train_t = torch.tensor(X_train, device=DEVICE)
y_train_tt = torch.tensor(y_train_t, device=DEVICE)
X_val_t = torch.tensor(X_val, device=DEVICE)
X_test_t = torch.tensor(X_test, device=DEVICE)

# decay weights in training
train_days = (train_df["date"].max() - train_df["date"]).dt.days.values
weights = torch.tensor(0.5 ** (train_days / 6.0), dtype=torch.float32, device=DEVICE)

BATCH = 8192
N_EPOCHS = 8
t1 = time.time()
for ep in range(N_EPOCHS):
    model.train()
    idx = torch.randperm(len(X_train_t), device=DEVICE)
    total = 0.0; n = 0
    for i in range(0, len(idx), BATCH):
        bi = idx[i:i+BATCH]
        x = X_train_t[bi]; y = y_train_tt[bi]; w = weights[bi]
        pred = model(x)
        loss = (((pred - y) ** 2) * w).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        total += loss.item() * len(bi); n += len(bi)
    scheduler.step()
    # val
    model.eval()
    with torch.no_grad():
        pv = torch.expm1(model(X_val_t)).clamp(min=0).cpu().numpy()
    val_mae = float(np.mean(np.abs(pv - y_val)))
    print(f"  Epoch {ep+1}/{N_EPOCHS}: train_loss={total/n:.4f}  val_MAE={val_mae:.4f}")
print(f"MLP training: {time.time()-t1:.1f}s")

# ==== FINAL PREDICTIONS ====
model.eval()
with torch.no_grad():
    pred_val = torch.expm1(model(X_val_t)).clamp(min=0).cpu().numpy()
    pred_test = torch.expm1(model(X_test_t)).clamp(min=0).cpu().numpy()

test_mae = float(np.mean(np.abs(pred_test - y_test)))
print(f"\nTest MAE (MLP): {test_mae:.4f}")
print(f"(XGB was ~1.46)")

# ==== BUFFER TUNING AND COST ====
val_prices = val_df["item_price"].values.astype(np.float32)
val_items = val_df["item_id"].values
test_prices = test_df["item_price"].values.astype(np.float32)
test_items = test_df["item_id"].values

def cost_fn(actual, pred, prices, iids):
    wf = np.array([
        (0.0 if SHELF_LOOKUP.get(str(i),(3.0,1.0))[0] >= NON_FOOD_SHELF_LIFE
         else WASTE_FRACTION * min(1.0, SHELF_LOOKUP.get(str(i),(3.0,1.0))[1]
                                      / max(SHELF_LOOKUP.get(str(i),(3.0,1.0))[0], 0.5)))
        for i in iids])
    over = np.maximum(pred - actual, 0); under = np.maximum(actual - pred, 0)
    return (over * prices * wf).sum() + STOCKOUT_MULTIPLIER * (under * prices).sum()

def group_of(iid):
    sl = SHELF_LOOKUP.get(str(iid), (3.0, 1.0))[0]
    if sl >= NON_FOOD_SHELF_LIFE: return "non_perishable"
    if sl <= 3: return "ultra_fresh"
    if sl <= 14: return "fresh"
    if sl <= 90: return "medium"
    return "long_shelf"

val_groups = np.array([group_of(i) for i in val_items])
test_groups = np.array([group_of(i) for i in test_items])
groups = ["ultra_fresh","fresh","medium","long_shelf","non_perishable"]

# Per-group tuned on val (cap=3.0, production config)
group_buf_cap3 = {}
for g in groups:
    mask = val_groups == g
    if mask.sum() < 50:
        group_buf_cap3[g] = 1.4
        continue
    def loss(buf):
        return cost_fn(y_val[mask], pred_val[mask] * buf, val_prices[mask], val_items[mask])
    res = minimize_scalar(loss, bounds=(1.0, 3.0), method="bounded")
    group_buf_cap3[g] = float(res.x)

# Apply to test
c_140 = cost_fn(y_test, pred_test * 1.40, test_prices, test_items)
pg = pred_test.copy()
for g, b in group_buf_cap3.items():
    pg[test_groups == g] = pred_test[test_groups == g] * b
c_cap3 = cost_fn(y_test, pg, test_prices, test_items)

# Unconstrained
group_buf_unc = {}
for g in groups:
    mask = val_groups == g
    if mask.sum() < 50:
        group_buf_unc[g] = 1.4
        continue
    def loss(buf):
        return cost_fn(y_val[mask], pred_val[mask] * buf, val_prices[mask], val_items[mask])
    res = minimize_scalar(loss, bounds=(1.0, 10.0), method="bounded")
    group_buf_unc[g] = float(res.x)
pg_u = pred_test.copy()
for g, b in group_buf_unc.items():
    pg_u[test_groups == g] = pred_test[test_groups == g] * b
c_unc = cost_fn(y_test, pg_u, test_prices, test_items)

print(f"\nTest costs (MLP):")
print(f"  Baseline buf=1.40:  {c_140:>14,.0f}")
print(f"  Per-group cap=3.0:  {c_cap3:>14,.0f}  (vs XGB cap=3 6,558,810)")
print(f"  Per-group unconstrained: {c_unc:>14,.0f}  (vs XGB unc 5,906,055)")

# Save
out = {
    "test_mae_mlp": test_mae,
    "group_buf_cap3": group_buf_cap3, "test_cost_cap3": float(c_cap3),
    "group_buf_unc": group_buf_unc, "test_cost_unconstrained": float(c_unc),
    "test_cost_baseline_140": float(c_140),
    "xgb_cap3_ref": 6558810, "xgb_unc_ref": 5906055,
    "n_params": sum(p.numel() for p in model.parameters()),
}
with open(RESULTS_DIR / "mlp_results.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nSaved. Total: {time.time()-t0:.1f}s")

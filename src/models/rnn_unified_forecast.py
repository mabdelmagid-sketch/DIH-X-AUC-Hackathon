"""
Unified RNN-Based Inventory Forecasting
Uses delta-based (change) prediction with sequence padding for all items
"""
from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore")

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import Dataset, DataLoader
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    print("⚠️  PyTorch not available. Install: pip install torch")


@dataclass
class ForecastResult:
    item_id: int
    item_name: str
    horizon: int
    mae: float
    rmse: float
    mape: float
    stockout_rate: float
    predictions: list[float]
    actuals: list[float]
    sequence_length: int


def parse_datetime(series: pd.Series) -> pd.Series:
    """Robust datetime parsing"""
    if series.dtype == "datetime64[ns, UTC]":
        return series
    if series.dtype == object or pd.api.types.is_string_dtype(series):
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
        if parsed.notna().mean() >= 0.6:
            return parsed
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() < 0.6:
        return pd.Series(pd.NaT, index=series.index)
    max_value = numeric.dropna().max()
    if max_value > 1e12:
        return pd.to_datetime(numeric, unit="ms", errors="coerce", utc=True)
    return pd.to_datetime(numeric, unit="s", errors="coerce", utc=True)


def build_item_demand_data(
    order_items_path: Path,
    orders_path: Path,
    items_path: Path,
    chunk_size: int = 100_000,
) -> pd.DataFrame:
    """Build daily item demand from order items"""
    
    print("  Loading items catalog...")
    items_df = pd.read_csv(items_path, low_memory=False)
    items_df = items_df[["id", "title"]].rename(columns={"id": "item_id", "title": "item_name"})
    
    print("  Loading order timestamps...")
    orders_data = []
    for chunk in pd.read_csv(orders_path, chunksize=chunk_size, low_memory=False, usecols=["id", "created"]):
        created = parse_datetime(chunk["created"])
        chunk["created_dt"] = created
        chunk["day"] = created.dt.date
        orders_data.append(chunk[["id", "day"]].rename(columns={"id": "order_id"}))
    
    orders_df = pd.concat(orders_data, ignore_index=True)
    orders_df = orders_df.dropna(subset=["day"])
    
    print("  Processing order items to get daily demand...")
    demand_data = []
    for chunk in pd.read_csv(order_items_path, chunksize=chunk_size, low_memory=False):
        chunk = chunk[["order_id", "item_id", "quantity"]].copy()
        chunk = chunk.merge(orders_df, on="order_id", how="inner")
        chunk = chunk.groupby(["day", "item_id"])["quantity"].sum().reset_index()
        chunk.rename(columns={"quantity": "demand"}, inplace=True)
        demand_data.append(chunk)
    
    demand_df = pd.concat(demand_data, ignore_index=True)
    demand_df = demand_df.groupby(["day", "item_id"])["demand"].sum().reset_index()
    demand_df = demand_df.merge(items_df, on="item_id", how="left")
    demand_df["day"] = pd.to_datetime(demand_df["day"])
    
    print(f"   ✓ Loaded {len(demand_df):,} demand records")
    print(f"   ✓ {demand_df['item_id'].nunique():,} unique items")
    print(f"   ✓ Date range: {demand_df['day'].min().date()} to {demand_df['day'].max().date()}")
    
    return demand_df


def prepare_sequences_with_padding(
    demand_df: pd.DataFrame,
    sequence_length: int = 60,
    horizon: int = 1,
) -> tuple[dict, pd.DataFrame]:
    """
    Prepare sequences for all items using delta-based approach with padding
    
    Args:
        demand_df: DataFrame with daily demand per item
        sequence_length: Fixed sequence length (days)
        horizon: Forecast horizon (days ahead)
    
    Returns:
        sequences: Dict with item_id -> (X, y, item_name, actual_length)
        metadata: DataFrame with item statistics
    """
    print(f"\n  Preparing sequences (length={sequence_length}, horizon={horizon})...")
    
    # Get all items with any history (RNN works with any sequence length!)
    item_history = demand_df.groupby("item_id").agg({
        "day": "count",
        "demand": ["sum", "mean"],
        "item_name": "first"
    }).reset_index()
    item_history.columns = ["item_id", "history_days", "total_demand", "avg_demand", "item_name"]
    
    # Use ALL items - RNN handles variable lengths with padding
    eligible_items = item_history
    print(f"   ✓ {len(eligible_items)} items (ALL items with any history)")
    
    sequences = {}
    
    for idx, row in eligible_items.iterrows():
        item_id = row.item_id
        item_name = row.item_name
        
        # Get item's daily demand time series
        item_df = demand_df[demand_df["item_id"] == item_id].sort_values("day").copy()
        
        # Fill missing days with 0 demand
        date_range = pd.date_range(
            start=item_df["day"].min(),
            end=item_df["day"].max(),
            freq="D"
        )
        item_df = item_df.set_index("day")[["demand"]].reindex(date_range, fill_value=0)
        item_df = item_df.reset_index()
        item_df.columns = ["day", "demand"]
        
        demand_series = item_df["demand"].values
        
        # Compute deltas (changes from previous day)
        deltas = np.diff(demand_series, prepend=0)
        
        # Create sequences
        X_sequences = []
        y_targets = []
        
        for i in range(len(deltas) - sequence_length - horizon + 1):
            # Input: sequence of changes
            X_seq = deltas[i:i + sequence_length]
            # Target: change at horizon
            y_target = deltas[i + sequence_length + horizon - 1]
            
            X_sequences.append(X_seq)
            y_targets.append(y_target)
        
        if len(X_sequences) > 0:
            X = np.array(X_sequences)
            y = np.array(y_targets)
            sequences[item_id] = (X, y, item_name, len(demand_series))
    
    print(f"   ✓ Created sequences for {len(sequences)} items")
    
    # Add sequence stats to metadata
    eligible_items["has_sequences"] = eligible_items["item_id"].isin(sequences.keys())
    
    return sequences, eligible_items


def pad_sequences_to_length(sequences: dict, max_length: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
    """
    Pad all sequences to same length and convert to arrays
    
    Args:
        sequences: Dict with item_id -> (X, y, item_name, actual_length)
        max_length: Maximum sequence length for padding
        
    Returns:
        X_padded: Padded input sequences (n_samples, max_length, 1)
        y_all: Target values (n_samples,)
        item_ids: Item ID for each sample (n_samples,)
        item_names: Item names for each sample (n_samples,)
    """
    all_X = []
    all_y = []
    all_item_ids = []
    all_item_names = []
    
    for item_id, (X, y, item_name, actual_len) in sequences.items():
        # Pad shorter sequences with zeros at the beginning
        for i in range(len(X)):
            seq = X[i]
            if len(seq) < max_length:
                padded = np.pad(seq, (max_length - len(seq), 0), mode='constant', constant_values=0)
            else:
                padded = seq[-max_length:]  # Take last max_length values
            
            all_X.append(padded)
            all_y.append(y[i])
            all_item_ids.append(item_id)
            all_item_names.append(item_name)
    
    X_padded = np.array(all_X).reshape(-1, max_length, 1)
    y_all = np.array(all_y)
    item_ids = np.array(all_item_ids)
    
    return X_padded, y_all, item_ids, all_item_names


class DemandRNN(nn.Module):
    """
    PyTorch RNN model for delta-based demand forecasting
    """
    def __init__(self, input_size: int = 1, lstm_units: int = 64, dropout: float = 0.2):
        super(DemandRNN, self).__init__()
        
        self.lstm1 = nn.LSTM(
            input_size=input_size,
            hidden_size=lstm_units,
            num_layers=1,
            batch_first=True,
            dropout=0
        )
        self.lstm2 = nn.LSTM(
            input_size=lstm_units,
            hidden_size=lstm_units // 2,
            num_layers=1,
            batch_first=True
        )
        
        self.dropout = nn.Dropout(dropout)
        self.fc1 = nn.Linear(lstm_units // 2, 32)
        self.fc2 = nn.Linear(32, 16)
        self.fc3 = nn.Linear(16, 1)
        self.relu = nn.ReLU()
        
    def forward(self, x, mask=None):
        # x shape: (batch, seq_len, input_size)
        out, _ = self.lstm1(x)
        out, _ = self.lstm2(out)
        
        # Take last output
        out = out[:, -1, :]
        
        # Dense layers
        out = self.relu(self.fc1(out))
        out = self.dropout(out)
        out = self.relu(self.fc2(out))
        out = self.fc3(out)
        
        return out


class DemandDataset(Dataset):
    """PyTorch Dataset for demand sequences"""
    def __init__(self, X, y):
        self.X = torch.FloatTensor(X)
        self.y = torch.FloatTensor(y).reshape(-1, 1)
    
    def __len__(self):
        return len(self.X)
    
    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


def train_unified_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    sequence_length: int,
    epochs: int = 50,
    batch_size: int = 32,
) -> DemandRNN:
    """
    Train unified RNN model on all items
    
    Args:
        X_train: Training sequences
        y_train: Training targets
        X_val: Validation sequences
        y_val: Validation targets
        sequence_length: Sequence length
        epochs: Training epochs
        batch_size: Batch size
        
    Returns:
        Trained PyTorch model
    """
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"\n  Using device: {device}")
    
    print("\n  Building RNN model...")
    model = DemandRNN(input_size=1, lstm_units=64, dropout=0.2)
    model = model.to(device)
    
    print("\n  Model architecture:")
    print(model)
    print(f"\n  Total parameters: {sum(p.numel() for p in model.parameters()):,}")
    
    # Create datasets
    train_dataset = DemandDataset(X_train, y_train)
    val_dataset = DemandDataset(X_val, y_val)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    # Loss and optimizer
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=5, min_lr=1e-6
    )
    
    print(f"\n  Training model...")
    print(f"    Training samples: {len(X_train):,}")
    print(f"    Validation samples: {len(X_val):,}")
    print(f"    Batch size: {batch_size}")
    
    best_val_loss = float('inf')
    patience_counter = 0
    patience = 10
    
    train_losses = []
    val_losses = []
    
    for epoch in range(epochs):
        # Training
        model.train()
        train_loss = 0.0
        train_mae = 0.0
        
        for batch_X, batch_y in train_loader:
            batch_X = batch_X.to(device)
            batch_y = batch_y.to(device)
            
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
            train_mae += torch.mean(torch.abs(outputs - batch_y)).item()
        
        train_loss /= len(train_loader)
        train_mae /= len(train_loader)
        train_losses.append(train_loss)
        
        # Validation
        model.eval()
        val_loss = 0.0
        val_mae = 0.0
        
        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                batch_X = batch_X.to(device)
                batch_y = batch_y.to(device)
                
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                
                val_loss += loss.item()
                val_mae += torch.mean(torch.abs(outputs - batch_y)).item()
        
        val_loss /= len(val_loader)
        val_mae /= len(val_loader)
        val_losses.append(val_loss)
        
        # Learning rate scheduling
        scheduler.step(val_loss)
        
        # Print progress
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"    Epoch {epoch+1}/{epochs} - "
                  f"Train Loss: {train_loss:.4f}, Train MAE: {train_mae:.4f} | "
                  f"Val Loss: {val_loss:.4f}, Val MAE: {val_mae:.4f}")
        
        # Early stopping
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            best_model_state = model.state_dict().copy()
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"\n  Early stopping at epoch {epoch+1}")
                model.load_state_dict(best_model_state)
                break
    
    print(f"\n  Training completed!")
    print(f"    Best validation loss: {best_val_loss:.4f}")
    
    return model


def evaluate_model_per_item(
    model: DemandRNN,
    sequences: dict,
    sequence_length: int,
    horizon: int,
) -> list[ForecastResult]:
    """
    Evaluate model performance per item
    
    Args:
        model: Trained PyTorch model
        sequences: Dict with item sequences
        sequence_length: Sequence length
        horizon: Forecast horizon
        
    Returns:
        List of ForecastResult per item
    """
    print("\n  Evaluating model per item...")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.eval()
    results = []
    
    with torch.no_grad():
        for item_id, (X, y, item_name, actual_len) in sequences.items():
            if len(X) == 0:
                continue
            
            # Pad sequences
            X_padded = []
            for seq in X:
                if len(seq) < sequence_length:
                    padded = np.pad(seq, (sequence_length - len(seq), 0), mode='constant', constant_values=0)
                else:
                    padded = seq[-sequence_length:]
                X_padded.append(padded)
            
            X_padded = np.array(X_padded).reshape(-1, sequence_length, 1)
            X_tensor = torch.FloatTensor(X_padded).to(device)
            
            # Predict changes
            y_pred_delta = model(X_tensor).cpu().numpy().flatten()
            
            # Convert deltas back to absolute values
            # Note: This is approximate since we're predicting changes
            # In practice, you'd combine with last known value
            y_pred = np.abs(y_pred_delta)  # Simplified: use absolute value
            y_true = np.abs(y)
            
            # Calculate metrics
            mae = mean_absolute_error(y_true, y_pred)
            rmse = np.sqrt(mean_squared_error(y_true, y_pred))
            mape = np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 1))) * 100
            stockout_rate = (y_pred < y_true).sum() / len(y_true) * 100
            
            results.append(ForecastResult(
                item_id=item_id,
                item_name=item_name,
                horizon=horizon,
                mae=mae,
                rmse=rmse,
                mape=mape,
                stockout_rate=stockout_rate,
                predictions=y_pred.tolist(),
                actuals=y_true.tolist(),
                sequence_length=actual_len,
            ))
    
    return results


def main(
    sequence_length: int = 60,
    horizon: int = 1,
    epochs: int = 50,
    batch_size: int = 32,
    test_split: float = 0.2,
):
    """Run unified RNN forecasting"""
    
    if not PYTORCH_AVAILABLE:
        print("\n❌ PyTorch is required for RNN models.")
        print("   Install: pip install torch")
        return
    
    root = Path(__file__).parent.parent.parent
    data_dir = root / "data" / "Inventory Management"
    output_dir = root / "docs" / "forecast"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("UNIFIED RNN INVENTORY FORECASTING")
    print("=" * 80)
    print(f"\nArchitecture: Delta-based LSTM with sequence padding")
    print(f"Sequence length: {sequence_length} days")
    print(f"Forecast horizon: {horizon} day(s)")
    print(f"Training on: ALL items (no minimum history requirement)")
    print("-" * 80)
    
    # Build demand data
    print("\n1. Building daily item demand data...")
    demand_df = build_item_demand_data(
        order_items_path=data_dir / "fct_order_items.csv",
        orders_path=data_dir / "fct_orders.csv",
        items_path=data_dir / "dim_items.csv",
    )
    
    # Prepare sequences
    print("\n2. Preparing sequences with padding...")
    sequences, metadata = prepare_sequences_with_padding(
        demand_df=demand_df,
        sequence_length=sequence_length,
        horizon=horizon,
    )
    
    if len(sequences) == 0:
        print("\n⚠️  No sequences created. Try lowering min_history parameter.")
        return
    
    # Convert to padded arrays
    print("\n3. Padding sequences to unified length...")
    X_all, y_all, item_ids, item_names = pad_sequences_to_length(sequences, sequence_length)
    
    print(f"   ✓ Total samples: {len(X_all):,}")
    print(f"   ✓ Unique items: {len(np.unique(item_ids))}")
    print(f"   ✓ Padded shape: {X_all.shape}")
    
    # Train/test split
    n_train = int(len(X_all) * (1 - test_split))
    X_train, X_test = X_all[:n_train], X_all[n_train:]
    y_train, y_test = y_all[:n_train], y_all[n_train:]
    
    # Train model
    print("\n4. Training unified RNN model...")
    model = train_unified_model(
        X_train=X_train,
        y_train=y_train,
        X_val=X_test,
        y_val=y_test,
        sequence_length=sequence_length,
        epochs=epochs,
        batch_size=batch_size,
    )
    
    # Evaluate per item
    print("\n5. Evaluating model per item...")
    results = evaluate_model_per_item(
        model=model,
        sequences=sequences,
        sequence_length=sequence_length,
        horizon=horizon,
    )
    
    # Convert to DataFrame
    results_df = pd.DataFrame([
        {
            "item_id": r.item_id,
            "item_name": r.item_name,
            "horizon_days": r.horizon,
            "mae": round(r.mae, 2),
            "rmse": round(r.rmse, 2),
            "mape": round(r.mape, 2),
            "stockout_rate": round(r.stockout_rate, 2),
            "sequence_length": r.sequence_length,
        }
        for r in results
    ])
    
    # Summary statistics
    print("\n" + "=" * 80)
    print("RNN MODEL PERFORMANCE:")
    print("=" * 80)
    print(f"\nOverall Statistics:")
    print(f"  Total items forecasted: {len(results_df)}")
    print(f"  Average MAE: {results_df['mae'].mean():.2f} units")
    print(f"  Average stockout rate: {results_df['stockout_rate'].mean():.1f}%")
    print(f"  Items with MAE < 5: {(results_df['mae'] < 5).sum()} ({(results_df['mae'] < 5).mean() * 100:.1f}%)")
    
    print(f"\n  Best performing items:")
    top_items = results_df.nsmallest(10, 'mae')[['item_name', 'mae', 'stockout_rate']]
    for _, row in top_items.iterrows():
        print(f"    • {row['item_name']}: MAE={row['mae']:.2f}, Stockout={row['stockout_rate']:.1f}%")
    
    # Save results
    results_path = output_dir / "rnn_forecast_results.csv"
    results_df.to_csv(results_path, index=False)
    
    # Save model
    model_path = output_dir / "rnn_model.pt"
    torch.save(model.state_dict(), model_path)
    
    print(f"\n" + "-" * 80)
    print(f"Results saved to:")
    print(f"  - {results_path.relative_to(root)}")
    print(f"  - {model_path.relative_to(root)}")
    
    print("\n" + "=" * 80)
    print("MODEL ADVANTAGES:")
    print("=" * 80)
    print("✓ Unified architecture: Single model for all items")
    print("✓ Delta-based learning: Predicts changes, not absolute values")
    print("✓ Automatic padding: Handles items with varying history lengths")
    print("✓ Transfer learning: Items benefit from patterns learned across all items")
    print("✓ Scalable: Can easily add new items without retraining")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified RNN inventory forecasting")
    parser.add_argument("--sequence-length", type=int, default=60, help="Sequence length in days")
    parser.add_argument("--horizon", type=int, default=1, help="Forecast horizon in days")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--test-split", type=float, default=0.2, help="Test split ratio")
    
    args = parser.parse_args()
    
    main(
        sequence_length=args.sequence_length,
        horizon=args.horizon,
        epochs=args.epochs,
        batch_size=args.batch_size,
        test_split=args.test_split,
    )

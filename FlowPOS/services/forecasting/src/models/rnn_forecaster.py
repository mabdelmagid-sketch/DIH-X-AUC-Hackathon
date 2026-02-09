"""
LSTM/RNN Forecaster for ensemble integration.

Wraps the DemandRNN (delta-based LSTM) model so it can be used alongside
the HybridForecaster and WasteOptimizedForecaster in a 3-model voting ensemble.

Architecture:
  - 2-layer LSTM (64 -> 32 units) with dropout
  - Delta-based prediction (predicts demand changes, not absolute values)
  - 60-day sequence length with zero-padding for shorter histories
"""
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import Dataset, DataLoader

    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    logger.warning("PyTorch not available - LSTM model disabled")


# ---------------------------------------------------------------------------
# PyTorch model definition (must match the trained architecture exactly)
# ---------------------------------------------------------------------------

if PYTORCH_AVAILABLE:

    class DemandRNN(nn.Module):
        """Delta-based LSTM for demand forecasting."""

        def __init__(self, input_size: int = 1, lstm_units: int = 64, dropout: float = 0.2):
            super().__init__()
            self.lstm1 = nn.LSTM(input_size=input_size, hidden_size=lstm_units,
                                 num_layers=1, batch_first=True)
            self.lstm2 = nn.LSTM(input_size=lstm_units, hidden_size=lstm_units // 2,
                                 num_layers=1, batch_first=True)
            self.dropout = nn.Dropout(dropout)
            self.fc1 = nn.Linear(lstm_units // 2, 32)
            self.fc2 = nn.Linear(32, 16)
            self.fc3 = nn.Linear(16, 1)
            self.relu = nn.ReLU()

        def forward(self, x, mask=None):
            out, _ = self.lstm1(x)
            out, _ = self.lstm2(out)
            out = out[:, -1, :]
            out = self.relu(self.fc1(out))
            out = self.dropout(out)
            out = self.relu(self.fc2(out))
            return self.fc3(out)

    class _DemandDataset(Dataset):
        def __init__(self, X, y):
            self.X = torch.FloatTensor(X)
            self.y = torch.FloatTensor(y).reshape(-1, 1)

        def __len__(self):
            return len(self.X)

        def __getitem__(self, idx):
            return self.X[idx], self.y[idx]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SEQUENCE_LENGTH = 60


class RNNForecaster:
    """Wrapper that adapts the LSTM model to the same interface as the pkl models.

    Usage:
        rnn = RNNForecaster()
        rnn.load("/path/to/rnn_model.pt")          # pre-trained
        # -- or --
        rnn.train_from_sales(daily_sales_df)        # train from scratch
        predictions = rnn.predict_items(daily_sales_df)  # list[dict]
    """

    def __init__(self, sequence_length: int = SEQUENCE_LENGTH):
        self.sequence_length = sequence_length
        self.model: Optional["DemandRNN"] = None
        self.device = None
        if PYTORCH_AVAILABLE:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # -- persistence --------------------------------------------------------

    def load(self, path: str | Path) -> bool:
        """Load a pre-trained .pt checkpoint."""
        if not PYTORCH_AVAILABLE:
            logger.warning("Cannot load RNN - PyTorch not installed")
            return False
        path = Path(path)
        if not path.exists():
            logger.warning(f"RNN model file not found: {path}")
            return False
        try:
            self.model = DemandRNN(input_size=1, lstm_units=64, dropout=0.2)
            self.model.load_state_dict(torch.load(path, map_location=self.device, weights_only=True))
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"Loaded RNN model from {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load RNN model: {e}")
            self.model = None
            return False

    def save(self, path: str | Path):
        if self.model is not None:
            torch.save(self.model.state_dict(), str(path))
            logger.info(f"Saved RNN model to {path}")

    # -- training -----------------------------------------------------------

    def train_from_sales(
        self,
        daily_sales_df: pd.DataFrame,
        epochs: int = 30,
        batch_size: int = 64,
    ):
        """Train the LSTM on daily-sales data (same format as predict_dual input).

        Expected columns: [item, place_id, date, quantity_sold]
        """
        if not PYTORCH_AVAILABLE:
            raise RuntimeError("PyTorch is required to train the RNN model")

        df = daily_sales_df.copy()
        df["date"] = pd.to_datetime(df["date"])

        sequences_X, sequences_y = [], []

        for item_name, grp in df.groupby("item"):
            grp = grp.sort_values("date")
            # Fill date gaps with 0
            date_range = pd.date_range(grp["date"].min(), grp["date"].max(), freq="D")
            demand = grp.set_index("date")["quantity_sold"].reindex(date_range, fill_value=0).values.astype(float)

            # Compute deltas
            deltas = np.diff(demand, prepend=0.0)

            # Create sliding windows
            for i in range(len(deltas) - self.sequence_length):
                seq = deltas[i : i + self.sequence_length]
                target = deltas[i + self.sequence_length]
                # Pad if needed
                if len(seq) < self.sequence_length:
                    seq = np.pad(seq, (self.sequence_length - len(seq), 0))
                sequences_X.append(seq)
                sequences_y.append(target)

        if len(sequences_X) < 10:
            logger.warning("Not enough data to train RNN (need >10 sequences)")
            return

        X = np.array(sequences_X).reshape(-1, self.sequence_length, 1)
        y = np.array(sequences_y)

        # 80/20 split
        n = int(len(X) * 0.8)
        X_train, X_val = X[:n], X[n:]
        y_train, y_val = y[:n], y[n:]

        logger.info(f"Training RNN: {len(X_train)} train, {len(X_val)} val samples")

        self.model = DemandRNN(input_size=1, lstm_units=64, dropout=0.2).to(self.device)
        train_ds = _DemandDataset(X_train, y_train)
        val_ds = _DemandDataset(X_val, y_val)
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=batch_size)

        criterion = nn.MSELoss()
        optimizer = optim.Adam(self.model.parameters(), lr=0.001)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=5)

        best_val = float("inf")
        best_state = None
        patience_ctr = 0

        for epoch in range(epochs):
            self.model.train()
            for bx, by in train_loader:
                bx, by = bx.to(self.device), by.to(self.device)
                optimizer.zero_grad()
                loss = criterion(self.model(bx), by)
                loss.backward()
                optimizer.step()

            # Validation
            self.model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for bx, by in val_loader:
                    bx, by = bx.to(self.device), by.to(self.device)
                    val_loss += criterion(self.model(bx), by).item()
            val_loss /= max(len(val_loader), 1)
            scheduler.step(val_loss)

            if val_loss < best_val:
                best_val = val_loss
                best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
                patience_ctr = 0
            else:
                patience_ctr += 1
                if patience_ctr >= 10:
                    break

        if best_state:
            self.model.load_state_dict(best_state)
        self.model.eval()
        logger.info(f"RNN training complete (best val loss: {best_val:.4f})")

    # -- inference ----------------------------------------------------------

    def predict_items(self, daily_sales_df: pd.DataFrame) -> dict[str, float]:
        """Predict next-day demand for each item.

        Returns dict: {item_name: predicted_quantity}
        """
        if self.model is None or not PYTORCH_AVAILABLE:
            return {}

        df = daily_sales_df.copy()
        df["date"] = pd.to_datetime(df["date"])

        results: dict[str, float] = {}

        self.model.eval()
        with torch.no_grad():
            for item_name, grp in df.groupby("item"):
                grp = grp.sort_values("date")
                date_range = pd.date_range(grp["date"].min(), grp["date"].max(), freq="D")
                demand = grp.set_index("date")["quantity_sold"].reindex(date_range, fill_value=0).values.astype(float)

                if len(demand) < 2:
                    continue

                # Delta sequence
                deltas = np.diff(demand, prepend=0.0)

                # Take last sequence_length deltas (pad if shorter)
                seq = deltas[-self.sequence_length:]
                if len(seq) < self.sequence_length:
                    seq = np.pad(seq, (self.sequence_length - len(seq), 0))

                x = torch.FloatTensor(seq.reshape(1, self.sequence_length, 1)).to(self.device)
                predicted_delta = self.model(x).item()

                # Convert delta back to absolute demand
                last_demand = float(demand[-1])
                predicted = max(0.0, last_demand + predicted_delta)
                results[str(item_name)] = round(predicted, 1)

        return results

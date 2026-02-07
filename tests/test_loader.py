"""Tests for the DataLoader module."""
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


class TestDataLoaderInit:
    """Test DataLoader initialization."""

    def test_init_default_path(self):
        from src.data.loader import DataLoader
        loader = DataLoader()
        assert loader.data_path is not None
        assert loader.conn is not None
        assert len(loader._tables_loaded) == 0

    def test_init_custom_path(self, tmp_path):
        from src.data.loader import DataLoader
        loader = DataLoader(data_path=tmp_path)
        assert loader.data_path == tmp_path


class TestDataLoaderCSV:
    """Test CSV loading."""

    def test_load_csv_file_not_found(self, tmp_path):
        from src.data.loader import DataLoader
        loader = DataLoader(data_path=tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load_csv("nonexistent.csv")

    def test_load_csv_success(self, tmp_path):
        from src.data.loader import DataLoader

        # Create a test CSV
        csv_path = tmp_path / "test_table.csv"
        pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]}).to_csv(
            csv_path, index=False
        )

        loader = DataLoader(data_path=tmp_path)
        df = loader.load_csv("test_table.csv")

        assert len(df) == 3
        assert "id" in df.columns
        assert "test_table" in loader._tables_loaded

    def test_load_csv_registers_in_duckdb(self, tmp_path):
        from src.data.loader import DataLoader

        csv_path = tmp_path / "items.csv"
        pd.DataFrame({"id": [1, 2], "title": ["Apple", "Banana"]}).to_csv(
            csv_path, index=False
        )

        loader = DataLoader(data_path=tmp_path)
        loader.load_csv("items.csv")

        result = loader.query("SELECT COUNT(*) as cnt FROM items")
        assert result["cnt"].iloc[0] == 2


class TestDataLoaderQuery:
    """Test SQL queries."""

    def test_query_after_load(self, tmp_path):
        from src.data.loader import DataLoader

        csv_path = tmp_path / "products.csv"
        pd.DataFrame({
            "id": [1, 2, 3],
            "name": ["X", "Y", "Z"],
            "price": [10.0, 20.0, 30.0]
        }).to_csv(csv_path, index=False)

        loader = DataLoader(data_path=tmp_path)
        loader.load_csv("products.csv")

        result = loader.query("SELECT AVG(price) as avg_price FROM products")
        assert abs(result["avg_price"].iloc[0] - 20.0) < 0.01


class TestTimestampConversion:
    """Test UNIX timestamp conversion."""

    def test_convert_unix_timestamp(self, tmp_path):
        from src.data.loader import DataLoader

        loader = DataLoader(data_path=tmp_path)
        df = pd.DataFrame({"created": [1704067200, 1704153600]})  # Jan 1-2 2024
        result = loader.convert_unix_timestamp(df, ["created"])

        assert pd.api.types.is_datetime64_any_dtype(result["created"])


class TestListTables:
    """Test table listing."""

    def test_list_tables_empty(self, tmp_path):
        from src.data.loader import DataLoader
        loader = DataLoader(data_path=tmp_path)
        assert loader.list_tables() == []

    def test_list_tables_after_load(self, tmp_path):
        from src.data.loader import DataLoader

        csv_path = tmp_path / "table_a.csv"
        pd.DataFrame({"x": [1]}).to_csv(csv_path, index=False)

        loader = DataLoader(data_path=tmp_path)
        loader.load_csv("table_a.csv")

        assert "table_a" in loader.list_tables()

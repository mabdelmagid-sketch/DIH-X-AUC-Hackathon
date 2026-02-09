"""Tests for the LLM tool definitions and executor."""
import pytest
import json
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from src.llm.tools import TOOL_DEFINITIONS, ToolExecutor


class TestToolDefinitions:
    """Test that tool definitions are valid."""

    def test_all_tools_have_required_fields(self):
        for tool in TOOL_DEFINITIONS:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn

    def test_tool_names_are_unique(self):
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert len(names) == len(set(names))

    def test_expected_tools_exist(self):
        names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
        expected = {
            "query_inventory", "get_sales_history", "get_forecast",
            "get_low_stock", "get_top_sellers", "get_bom",
            "run_sql", "get_expiring_items"
        }
        assert expected.issubset(names)


class TestToolExecutor:
    """Test tool execution."""

    @pytest.fixture
    def mock_loader(self, tmp_path):
        """Create a DataLoader with test data."""
        from src.data.loader import DataLoader
        loader = DataLoader(data_path=tmp_path)

        # Create minimal test tables
        dim_items = pd.DataFrame({
            "id": [1, 2, 3],
            "title": ["Flour", "Sugar", "Coffee"],
            "quantity": [100, 5, 50],
            "threshold": [20, 10, 10],
            "unit": ["kg", "kg", "kg"],
            "stock_category_id": [1, 1, 2],
            "place_id": [1, 1, 1]
        })
        dim_stock_categories = pd.DataFrame({
            "id": [1, 2],
            "name": ["Dry Goods", "Beverages"]
        })

        loader.conn.register("dim_items", dim_items)
        loader.conn.register("dim_stock_categories", dim_stock_categories)
        loader._tables_loaded = {"dim_items", "dim_stock_categories"}

        return loader

    def test_query_inventory(self, mock_loader):
        executor = ToolExecutor(mock_loader)
        result = executor.execute("query_inventory", {"limit": 10})
        data = json.loads(result)
        assert len(data) == 3
        assert data[0]["title"] == "Coffee"  # alphabetical

    def test_get_low_stock(self, mock_loader):
        executor = ToolExecutor(mock_loader)
        result = executor.execute("get_low_stock", {})
        data = json.loads(result)
        # Sugar (qty=5, threshold=10) should be low stock
        assert len(data) == 1
        assert data[0]["title"] == "Sugar"

    def test_run_sql_blocks_destructive(self, mock_loader):
        executor = ToolExecutor(mock_loader)
        result = executor.execute("run_sql", {"query": "DROP TABLE dim_items"})
        data = json.loads(result)
        assert "error" in data
        assert "DROP" in data["error"]

    def test_run_sql_select(self, mock_loader):
        executor = ToolExecutor(mock_loader)
        result = executor.execute("run_sql", {"query": "SELECT COUNT(*) as cnt FROM dim_items"})
        data = json.loads(result)
        assert data[0]["cnt"] == 3

    def test_unknown_tool(self, mock_loader):
        executor = ToolExecutor(mock_loader)
        result = executor.execute("nonexistent_tool", {})
        data = json.loads(result)
        assert "error" in data

    def test_get_forecast_no_model(self, mock_loader):
        executor = ToolExecutor(mock_loader, forecaster=None)
        result = executor.execute("get_forecast", {})
        data = json.loads(result)
        assert "error" in data

"""
FastAPI dependency injection for FlowPOS Forecasting API.

Replaces global state with lazy-initialized singletons via Depends().
"""
from typing import Optional

from ..data.loader import DataLoader
from ..models.forecaster import DemandForecaster
from ..llm.client import LLMClient
from ..llm.tools import ToolExecutor
from ..llm.simulator import ScenarioSimulator
from ..config import settings

try:
    from ..llm.rag import RAGEngine
except ImportError:
    RAGEngine = None

# Singleton instances
_instances: dict[str, object] = {}


def get_data_loader() -> DataLoader:
    """Return singleton DataLoader."""
    if "data_loader" not in _instances:
        _instances["data_loader"] = DataLoader()
        print(f"Data path: {settings.data_path}")
    return _instances["data_loader"]


def get_forecaster() -> DemandForecaster:
    """Return singleton DemandForecaster (loads pre-trained model if available)."""
    if "forecaster" not in _instances:
        forecaster = DemandForecaster()
        try:
            forecaster.load()
            print("Forecaster model loaded")
        except FileNotFoundError:
            print("No trained model found - train via /api/train")
        _instances["forecaster"] = forecaster
    return _instances["forecaster"]


def get_llm_client() -> Optional[LLMClient]:
    """Return singleton LLMClient (None if API key missing)."""
    if "llm_client" not in _instances:
        try:
            _instances["llm_client"] = LLMClient()
            print("LLM client initialized")
        except Exception as e:
            print(f"LLM client failed: {e}")
            _instances["llm_client"] = None
    return _instances["llm_client"]


def get_tool_executor() -> Optional[ToolExecutor]:
    """Return singleton ToolExecutor wired to data loader and forecaster."""
    if "tool_executor" not in _instances:
        loader = get_data_loader()
        forecaster = get_forecaster()
        llm = get_llm_client()
        executor = ToolExecutor(loader, forecaster)
        if llm:
            llm.set_tool_executor(executor)
        _instances["tool_executor"] = executor
    return _instances["tool_executor"]


def get_rag_engine() -> Optional[object]:
    """Return singleton RAGEngine (None if sentence-transformers not installed)."""
    if "rag_engine" not in _instances:
        if RAGEngine is not None:
            try:
                engine = RAGEngine()
                engine.seed_default_rules()
                print("RAG engine initialized")
                _instances["rag_engine"] = engine
            except Exception as e:
                print(f"RAG engine failed: {e}")
                _instances["rag_engine"] = None
        else:
            print("RAG engine skipped (sentence-transformers not installed)")
            _instances["rag_engine"] = None
    return _instances["rag_engine"]


def get_simulator() -> Optional[ScenarioSimulator]:
    """Return singleton ScenarioSimulator."""
    if "simulator" not in _instances:
        llm = get_llm_client()
        executor = get_tool_executor()
        if llm and executor:
            _instances["simulator"] = ScenarioSimulator(llm, executor)
        else:
            _instances["simulator"] = None
    return _instances["simulator"]

from .data_routes import router as data_router
from .model_routes import router as model_router
from .chat_routes import router as chat_router

__all__ = ["data_router", "model_router", "chat_router"]

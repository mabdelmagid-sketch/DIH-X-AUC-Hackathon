"""
FlowPOS Forecasting API - Main Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from .api.data_routes import router as data_router
from .api.model_routes import router as model_router
from .api.chat_routes import router as chat_router
from .api.dependencies import get_forecaster, get_llm_client, get_tool_executor


app = FastAPI(
    title="FlowPOS Forecasting API",
    description="AI-Powered Demand Forecasting & Inventory Intelligence",
    version="1.0.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include split route modules
app.include_router(data_router, prefix="/api")
app.include_router(model_router, prefix="/api")
app.include_router(chat_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "FlowPOS Forecasting API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    forecaster = get_forecaster()
    llm_client = get_llm_client()
    tool_executor = get_tool_executor()

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model_loaded": forecaster.model is not None if forecaster else False,
        "llm_available": llm_client is not None,
        "tools_available": tool_executor is not None
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

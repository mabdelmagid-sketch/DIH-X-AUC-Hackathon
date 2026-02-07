#!/usr/bin/env python3
"""Run FlowPOS Forecasting API server"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8002))
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=port,
        reload=os.environ.get("RAILWAY_ENVIRONMENT") is None,
    )

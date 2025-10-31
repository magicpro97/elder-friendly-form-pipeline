"""
Production entry point for the FastAPI application.
Handles Railway's dynamic PORT environment variable and production settings.
"""

import os

import uvicorn

if __name__ == "__main__":
    # Railway sets PORT env var dynamically (usually 3000-9000)
    # Default to 8000 for local development
    port = int(os.getenv("PORT", 8000))

    # Run with production-optimized settings
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        workers=1,  # Single worker for single-core Railway instances
        log_level="info",
        access_log=True,
        # Disable reload in production
        reload=False,
        # Better for production stability
        timeout_keep_alive=30,
    )

#!/usr/bin/env python3
"""Start script for Railway deployment - reads PORT from environment"""

import os
import sys

# Get port from environment, default to 8000
port = int(os.environ.get("PORT", "8000"))

# Import uvicorn and run
if __name__ == "__main__":
    import uvicorn

    sys.stdout.write(f"Starting uvicorn on port {port}\n")
    sys.stdout.flush()
    uvicorn.run("app:app", host="0.0.0.0", port=port)

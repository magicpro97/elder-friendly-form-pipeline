#!/usr/bin/env python3
"""Start script for Railway deployment - reads PORT from environment"""

import os
import subprocess
import sys

# Get port from environment, default to 8000
port = os.environ.get("PORT", "8000")
sys.stdout.write(f"Starting uvicorn on port {port}\n")
sys.stdout.flush()

# Start uvicorn
sys.exit(subprocess.call(["uvicorn", "app:app", "--host", "0.0.0.0", "--port", port]))

"""Path-independent entry point for MCP clients such as Claude Desktop.

Claude Desktop launches servers from an arbitrary working directory, so this file puts the repo
root on sys.path and loads .env from there before starting the server:

    "args": ["C:\\\\path\\\\to\\\\repo\\\\mcp_entry.py"]
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from agent.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()

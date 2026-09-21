#!/usr/bin/env python3
# Gen by Cursor
"""
TranSplat Interactive Viser Viewer Entrypoint.

Usage:
    python viewer.py <path_to_ply> [options]
    python viewer.py obj.ply scene_bg.ply -t 1 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1
    python viewer.py <path_to_ply> --port 8080 --host 0.0.0.0
"""

import sys
from pathlib import Path

# Add GUI directory to path and delegate to GUI.viewer
REPO_ROOT = Path(__file__).resolve().parent
GUI_DIR = REPO_ROOT / "GUI"

if str(GUI_DIR) not in sys.path:
    sys.path.insert(0, str(GUI_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(1, str(REPO_ROOT))

from GUI.viewer import main

if __name__ == "__main__":
    main()

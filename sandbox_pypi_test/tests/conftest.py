import os
import sys
from pathlib import Path

# Add project root to sys.path for test discovery
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Automatically set DUME_TESTING=1 for all pytest runs
os.environ["DUME_TESTING"] = "1"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Tests must never touch the network: with torch/transformers now installed, an
# accidental model download (1+ GB) would hang the suite mid-run. The embedding
# rerank stays available in production via GENOMIND_EMBED_MODEL.
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

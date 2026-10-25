"""Translate Supervisor options into the server's existing environment settings."""
import json
import os
from pathlib import Path
import sys

path = Path("/data/options.json")
options = json.loads(path.read_text()) if path.exists() else {}
defaults = {
    "port": ("PORT", 5100),
    "trained_dir": ("TRAINED_DIR", "/homeassistant/faces/trained"),
    "cv_threads": ("CV_THREADS", 2),
    "detection_width": ("DET_WIDTH", 640),
    "detection_score": ("DET_SCORE", 0.6),
    "recognition_threshold": ("SFACE_ACCEPT", 0.363),
    "min_available_memory_mb": ("MIN_AVAIL_MB", 300),
}
for key, (variable, default) in defaults.items():
    os.environ[variable] = str(options.get(key, os.environ.get(variable, default)))
os.environ["BIND_HOST"] = "127.0.0.1"
os.environ.setdefault("DATA_DIR", "/data")
os.environ.setdefault("RTSP_CREDS_FILE", "/config/rtsp_creds.json")
if not Path(os.environ["TRAINED_DIR"]).is_dir():
    raise SystemExit("Create the configured trained_dir before starting the app; see DOCS.md.")
os.execv(sys.executable, [sys.executable, "-u", str(Path(__file__).with_name("server.py"))])

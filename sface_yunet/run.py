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
    "collect_unknowns": ("COLLECT_UNKNOWNS", True),
    "unknown_retention_days": ("UNKNOWN_RETENTION_DAYS", 7),
    "max_unknown_groups": ("MAX_UNKNOWN_GROUPS", 100),
    "unknown_group_threshold": ("UNKNOWN_GROUP_THRESHOLD", 0.6),
    "match_margin": ("MATCH_MARGIN", 0.05),
    "mqtt_enabled": ("MQTT_ENABLED", True),
}
for key, (variable, default) in defaults.items():
    os.environ[variable] = str(options.get(key, os.environ.get(variable, default)))
os.environ["BIND_HOST"] = "127.0.0.1"
os.environ.setdefault("DATA_DIR", "/data")
private_rtsp = Path(os.environ["DATA_DIR"]) / "rtsp_creds.json"
os.environ.setdefault("RTSP_CREDS_FILE", str(private_rtsp) if private_rtsp.is_file()
                      else "/config/rtsp_creds.json")
if not Path(os.environ["TRAINED_DIR"]).is_dir():
    print('Legacy training folder unavailable; existing enrollment is preserved. Use the face library to add photos.',flush=True)
os.execv(sys.executable, [sys.executable, "-u", str(Path(__file__).with_name("server.py"))])

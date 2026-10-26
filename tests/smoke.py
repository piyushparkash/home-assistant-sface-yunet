"""Exercise a fresh empty database, invalid image and low-memory refusal."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def exercise(low_memory=False):
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        (base / "trained").mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, PORT=str(port), BIND_HOST="127.0.0.1",
                   DATA_DIR=str(base / "data"), TRAINED_DIR=str(base / "trained"),
                   MODELS_DIR=os.environ.get("MODELS_DIR", str(ROOT / "sface_yunet/models")),
                   MIN_AVAIL_MB="999999999" if low_memory else "0")
        process = subprocess.Popen([sys.executable, str(ROOT / "sface_yunet/run.py")], env=env)
        try:
            url = f"http://127.0.0.1:{port}"
            for attempt in range(100):
                try:
                    with urllib.request.urlopen(url + "/health", timeout=1) as response:
                        health = json.load(response)
                    break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError("Server exited during startup")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Server did not become ready")
            assert health["success"] and health["people"] == {}
            for endpoint in ("/people",):
                with urllib.request.urlopen(url + endpoint) as response:
                    assert json.load(response)["enrolled"] == []
            for endpoint, payload in (("/recognize", b"invalid image"), ("/sync", b"")):
                req = urllib.request.Request(url + endpoint, data=payload, method="POST")
                with urllib.request.urlopen(req) as response:
                    result = json.load(response)
                if endpoint == "/recognize":
                    expected = "host low memory" if low_memory and sys.platform == "linux" else "bad image"
                    assert not result["success"] and result["error"] == expected, result
                else:
                    assert result["success"] and result["added"] == result["removed"] == 0
            print("Smoke checks passed", "low-memory" if low_memory else "normal")
            database = base / "data/faces.db"
            with sqlite3.connect(database) as db:
                db.execute("insert into emb values (?,?,?,?)",
                           ("synthetic", "test.jpg", b"synthetic-test-data", 0))
                db.commit()
            before = database.read_bytes()
            (base / "trained").rmdir()
            req = urllib.request.Request(url + "/sync", data=b"", method="POST")
            with urllib.request.urlopen(req) as response:
                result = json.load(response)
            assert not result["success"] and "database unchanged" in result["error"]
            assert database.read_bytes() == before
            print("Missing training directory preserves database")
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    exercise()
    exercise(low_memory=True)

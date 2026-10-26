"""SFace + YuNet face recognition sidecar (OpenCV, CPU only).

Endpoints (all JSON unless noted):
  GET  /health            liveness + enrolled people
  GET  /people            {person: photo_count}
  POST /recognize         body = raw image bytes -> faces with best/second match
  POST /sync              re-scan TRAINED_DIR (read-only mount), add new photos, drop deleted ones
  GET  /live/<camera>     multipart/x-mixed-replace MJPEG, boxes+names drawn live (see LiveCam)
The trained-photo folder is the single source of truth: /sync makes the embedding DB match it.
"""
import os, sys, json, time, sqlite3, threading, glob, signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
import cv2

cv2.setNumThreads(int(os.environ.get("CV_THREADS", "2")))
MODELS = os.environ.get("MODELS_DIR", "/app/models")
DATA = os.environ.get("DATA_DIR", "/data")
TRAINED = os.environ.get("TRAINED_DIR", "/trained")
DET_WIDTH = int(os.environ.get("DET_WIDTH", "640"))     # frames are downscaled to this width for detection only
DET_SCORE = float(os.environ.get("DET_SCORE", "0.6"))
PORT = int(os.environ.get("PORT", "5100"))
BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")
MIN_AVAIL_MB = int(os.environ.get("MIN_AVAIL_MB", "300"))   # refuse to run when the host is this short on memory
EXTS = (".jpg", ".jpeg", ".png", ".bmp")
ACCEPT = float(os.environ.get("SFACE_ACCEPT", "0.363"))
# Optional camera credentials stay in private app data and must never be committed.
RTSP_CREDS_FILE = os.environ.get("RTSP_CREDS_FILE", os.path.join(DATA, "rtsp_creds.json"))

lock = threading.Lock()
det = cv2.FaceDetectorYN.create(os.path.join(MODELS, "yunet.onnx"), "", (320, 320), DET_SCORE, 0.3, 5000)
rec = cv2.FaceRecognizerSF.create(os.path.join(MODELS, "sface.onnx"), "")
os.makedirs(DATA, exist_ok=True)
db = sqlite3.connect(os.path.join(DATA, "faces.db"), check_same_thread=False)
db.execute("create table if not exists emb(person text, file text, vec blob, added real, primary key(person, file))")
db.commit()

templates = {}   # person -> normalised mean embedding
counts = {}      # person -> number of photos


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def host_state():
    """Host memory/load as seen from inside the container (/proc/meminfo is the Pi's, not the cgroup's)."""
    avail = None
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) // 1024
                break
    except Exception:
        pass
    return {"mem_available_mb": avail, "load1": round(os.getloadavg()[0], 2)}


def rebuild_templates():
    global templates, counts
    by = {}
    for person, blob in db.execute("select person, vec from emb"):
        by.setdefault(person, []).append(np.frombuffer(blob, dtype=np.float32))
    templates, counts = {}, {}
    for person, vecs in by.items():
        t = np.mean(vecs, axis=0)
        templates[person] = t / np.linalg.norm(t)
        counts[person] = len(vecs)


def detect(img, width=DET_WIDTH):
    """Returns faces (rows of 15 numbers) in the ORIGINAL image's coordinates, best score first."""
    h, w = img.shape[:2]
    if width and w > width:
        s = width / w
        small = cv2.resize(img, (width, int(round(h * s))), interpolation=cv2.INTER_AREA)
    else:
        s, small = 1.0, img
    det.setInputSize((small.shape[1], small.shape[0]))
    _, fs = det.detect(small)
    if fs is None:
        return []
    out = []
    for f in fs:
        f = f.copy()
        f[:14] /= s
        out.append(f)
    out.sort(key=lambda f: -f[14])
    return out


def embed(img, face):
    v = rec.feature(rec.alignCrop(img, face)).flatten().astype(np.float32)
    return v / np.linalg.norm(v)


def match(vec):
    scores = sorted(((float(vec @ t), p) for p, t in templates.items()), reverse=True)
    if not scores:
        return None
    best = scores[0]
    second = scores[1] if len(scores) > 1 else None
    return {"userid": best[1], "score": round(best[0], 4),
            "second": second[1] if second else None,
            "second_score": round(second[0], 4) if second else None}


def do_recognize(data):
    host = host_state()
    if host["mem_available_mb"] is not None and host["mem_available_mb"] < MIN_AVAIL_MB:
        log(f"recognize skipped: host low on memory ({host})")
        return {"success": False, "error": "host low memory", "host": host}
    t0 = time.perf_counter()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return {"success": False, "error": "bad image"}
    h, w = img.shape[:2]
    t1 = time.perf_counter()
    faces = detect(img)
    t2 = time.perf_counter()
    out = []
    for f in faces:
        entry = {"box": [round(float(x), 1) for x in f[:4]], "det_score": round(float(f[14]), 3)}
        m = match(embed(img, f)) if templates else None
        if m:
            entry.update(m)
        out.append(entry)
    t3 = time.perf_counter()
    return {"success": True, "frame": [w, h], "faces": out, "enrolled": sorted(templates), "host": host,
            "ms": {"decode": round((t1 - t0) * 1000), "detect": round((t2 - t1) * 1000),
                   "embed_match": round((t3 - t2) * 1000)}}


def do_sync():
    if not os.path.isdir(TRAINED):
        return {"success": False, "error": "training directory unavailable; database unchanged"}
    t0 = time.perf_counter()
    on_disk = set()
    for path in glob.glob(os.path.join(TRAINED, "*", "*")):
        if path.lower().endswith(EXTS):
            on_disk.add((os.path.basename(os.path.dirname(path)), os.path.basename(path)))
    in_db = set(db.execute("select person, file from emb"))
    added, skipped = 0, []
    for person, fname in sorted(on_disk - in_db):
        img = cv2.imread(os.path.join(TRAINED, person, fname))
        faces = detect(img, width=0) if img is not None else []   # trained crops are small: detect at native size
        if not faces:
            skipped.append(f"{person}/{fname}")
            continue
        db.execute("insert or replace into emb values (?,?,?,?)",
                   (person, fname, embed(img, faces[0]).tobytes(), time.time()))
        added += 1
    removed = 0
    for person, fname in in_db - on_disk:
        db.execute("delete from emb where person=? and file=?", (person, fname))
        removed += 1
    db.commit()
    rebuild_templates()
    log(f"sync: +{added} -{removed} skipped={len(skipped)} people={counts}")
    return {"success": True, "added": added, "removed": removed, "skipped": skipped,
            "people": counts, "ms": round((time.perf_counter() - t0) * 1000)}


# ────────────────────────────────────────────────────────────────────────────
# Live face-overlay: one background capture+annotate loop per camera, shared by
# every viewer (a dashboard card open on two phones costs the same one loop, not two).
# Starts on the first /live/<camera> connection, stops shortly after the last one
# disconnects - no continuous RTSP/inference load when nobody's looking.
# ────────────────────────────────────────────────────────────────────────────
try:
    RTSP_URLS = json.load(open(RTSP_CREDS_FILE))
except Exception as e:
    RTSP_URLS = {}
    log("WARN: no RTSP creds loaded:", repr(e))

BOX_COLORS = {"known": (60, 200, 60), "low": (0, 170, 255), "none": (60, 60, 220)}   # BGR: green/orange/red


def _draw_annotated(img, faces):
    for f in faces:
        x, y, w, h = [int(round(v)) for v in f["box"]]
        userid, score = f.get("userid"), f.get("score", 0.0)
        if userid and score >= ACCEPT:
            color, label = BOX_COLORS["known"], f"{userid.replace('_', ' ').title()} {score:.2f}"
        elif userid:
            color, label = BOX_COLORS["low"], f"{userid.replace('_', ' ').title()}? {score:.2f}"
        else:
            color, label = BOX_COLORS["none"], "unknown"
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x, y - th - 8), (x + tw + 6, y), color, -1)
        cv2.putText(img, label, (x + 3, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        lm = f.get("_landmarks") or []
        for i in range(0, len(lm) - 1, 2):   # 5 (x, y) landmark pairs
            cv2.circle(img, (int(lm[i]), int(lm[i + 1])), 2, color, -1)
    return img


class LiveCam:
    """One shared capture+detect+annotate loop for a camera. Ref-counted by viewer connections."""
    _all = {}

    def __init__(self, name, url):
        self.name, self.url = name, url
        self.viewers = 0
        self.frame = None          # latest encoded JPEG bytes
        self.cond = threading.Condition()
        self.thread = None
        self.stop_flag = False

    @classmethod
    def get(cls, name):
        if name not in cls._all:
            if name not in RTSP_URLS:
                return None
            cls._all[name] = cls(name, RTSP_URLS[name])
        return cls._all[name]

    def add_viewer(self):
        with self.cond:
            self.viewers += 1
            if self.viewers == 1:
                self.stop_flag = False
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
                log(f"live[{self.name}]: starting (1 viewer)")

    def remove_viewer(self):
        with self.cond:
            self.viewers = max(0, self.viewers - 1)
            if self.viewers == 0:
                self.stop_flag = True
                log(f"live[{self.name}]: stopping (0 viewers)")

    def _run(self):
        cap = None
        backoff = 1
        while not self.stop_flag:
            try:
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self.url)
                    if not cap.isOpened():
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 15)
                        continue
                    backoff = 1
                # Drain any buffered frames so we always annotate the freshest one, not a
                # growing backlog - RTSP buffers a few frames by default and inference is
                # slower than the camera's native frame rate.
                for _ in range(4):
                    cap.grab()
                ok, img = cap.retrieve()
                if not ok:
                    cap.release()
                    cap = None
                    continue
                t0 = time.perf_counter()
                # det/rec are shared global cv2 objects (also used by do_recognize for /recognize
                # and /sync) - setInputSize()+detect() on one from two threads at once corrupts
                # the other's in-flight call (hit this immediately: two live streams open together
                # crashed with a dnn dims assertion). Same lock do_POST already holds for /recognize.
                with lock:
                    faces_raw = detect(img)
                    faces = []
                    for f in faces_raw:
                        entry = {"box": [float(v) for v in f[:4]], "_landmarks": [float(v) for v in f[4:14]]}
                        m = match(embed(img, f)) if templates else None
                        if m:
                            entry.update(m)
                        faces.append(entry)
                _draw_annotated(img, faces)
                cv2.putText(img, time.strftime("%H:%M:%S"), (8, img.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    with self.cond:
                        self.frame = buf.tobytes()
                        self.cond.notify_all()
                # Inference itself (~100-250ms on the Pi) is the natural throttle; this floor
                # just stops a fast reconnect loop from spinning if something's briefly wrong.
                elapsed = time.perf_counter() - t0
                if elapsed < 0.05:
                    time.sleep(0.05 - elapsed)
            except Exception as e:
                log(f"live[{self.name}] error (ignored):", repr(e))
                if cap is not None:
                    cap.release()
                cap = None
                time.sleep(2)
        if cap is not None:
            cap.release()
        log(f"live[{self.name}]: loop exited")


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/health", "/people"):
            self._send({"success": True, "people": counts, "enrolled": sorted(templates), "host": host_state()})
        elif self.path.startswith("/live/"):
            self._live(self.path[len("/live/"):])
        else:
            self._send({"success": False, "error": "not found"}, 404)

    def _live(self, name):
        cam = LiveCam.get(name)
        if cam is None:
            self._send({"success": False, "error": f"no RTSP configured for '{name}'"}, 404)
            return
        cam.add_viewer()
        try:
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            last = None
            while True:
                with cam.cond:
                    cam.cond.wait_for(lambda: cam.frame is not None and cam.frame is not last, timeout=5)
                    frame = cam.frame
                if frame is None:
                    continue   # still waiting on the first frame from a just-started capture
                last = frame
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass   # viewer closed the dashboard/tab - normal, not an error
        except Exception as e:
            log(f"live[{name}] viewer error (ignored):", repr(e))
        finally:
            cam.remove_viewer()

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(n) if n else b""
            with lock:
                if self.path == "/recognize":
                    self._send(do_recognize(data))
                elif self.path == "/sync":
                    self._send(do_sync())
                else:
                    self._send({"success": False, "error": "not found"}, 404)
        except Exception as e:
            log("ERROR", self.path, repr(e))
            self._send({"success": False, "error": str(e)[:200]}, 500)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    with lock:
        rebuild_templates()
    log(f"sface_server up on :{PORT}; trained dir {TRAINED}; enrolled {counts}")
    server = ThreadingHTTPServer((BIND_HOST, PORT), Handler)

    def request_shutdown(signum, frame):
        # shutdown() must run outside the thread executing serve_forever().
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    try:
        server.serve_forever()
    finally:
        for cam in list(LiveCam._all.values()):
            cam.stop_flag = True
        server.server_close()
        with lock:
            db.close()
        log("sface_server shutdown complete")

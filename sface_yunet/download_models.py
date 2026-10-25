"""Fetch unmodified OpenCV Zoo models at a pinned revision, checking hashes."""
import hashlib
import pathlib
import sys
import urllib.request

REVISION = "48b10fa505aeb51fbd127fc60a5c660040e823b7"
BASE_URL = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}/models"
MODELS = {
    "yunet.onnx": (
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "sface.onnx": (
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def download(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for filename, (source, expected) in MODELS.items():
        with urllib.request.urlopen(f"{BASE_URL}/{source}", timeout=180) as response:
            data = response.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Checksum mismatch for {filename}: {actual}")
        (destination / filename).write_bytes(data)
        print(f"Verified {filename}: {actual}", flush=True)


if __name__ == "__main__":
    download(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/app/models"))

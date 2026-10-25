# Setup and usage

## Training photos

Create `/config/faces/trained` using Studio Code Server, SSH or another local file
manager. Inside this app the same folder is `/homeassistant/faces/trained`, because
Supervisor mounts Home Assistant configuration there read-only.

Use one folder per identity, containing JPEG/PNG/BMP files with a single, clear face:

```text
faces/trained/
  person_one/
    front.jpg
    side.jpg
  person_two/
    front.jpg
```

Folder names become `userid` values. Use several sharp photos with varied angles
and lighting. Create this folder before starting the app. Avoid Home Assistant's
`www` folder: files under `www` can be served without authentication.

Start the app, then run the following commands from a terminal on the Home
Assistant host (a remote PC cannot reach its loopback API):

```sh
curl http://127.0.0.1:5100/health
curl -X POST http://127.0.0.1:5100/sync
curl http://127.0.0.1:5100/people
curl -X POST --data-binary @/path/to/query.jpg http://127.0.0.1:5100/recognize
```

`/sync` adds new files and removes database entries for deleted files. It does
not rewrite trained photos. Keep the training path correct: syncing an empty
folder removes enrollments from the database. Replacing an image under the same
filename does not refresh its embedding; use a new filename and sync again.

## Configuration

| Option | Default | Meaning |
| --- | --- | --- |
| `port` | `5100` | Loopback HTTP port; avoid conflicts with existing installations |
| `trained_dir` | `/homeassistant/faces/trained` | Existing training folder visible inside the app |
| `cv_threads` | `2` | OpenCV worker threads; not a container CPU quota |
| `detection_width` | `640` | Downscale wider query frames before detection |
| `detection_score` | `0.6` | YuNet detection cutoff |
| `recognition_threshold` | `0.363` | Color threshold for live overlays |
| `min_available_memory_mb` | `300` | Refuse recognition below this host-memory level |

`recognition_threshold` affects overlay coloring. `/recognize` returns the best
candidate even when its score is low; callers must apply a threshold and any
second-best margin themselves. The defaults are starting points to tune with
your own labeled evaluation. This app does not unlock doors or send alerts.

## API

| Method | Path | Result |
| --- | --- | --- |
| GET | `/health` | `success`, `people` counts, `enrolled`, host memory/load |
| GET | `/people` | Same JSON envelope as `/health` |
| POST | `/recognize` | Raw image body; `faces`, `frame`, timings, enrollment and host info |
| POST | `/sync` | Scan training files and reconcile SQLite embeddings |
| GET | `/live/<camera>` | Annotated MJPEG stream for a configured camera |

A face result includes `box`, `det_score`, and, if enrolled templates exist,
`userid`, `score`, `second`, `second_score`. `box` is `[x, y, width, height]`.
Invalid-image and low-memory errors return `success: false`; check the JSON body
as well as HTTP status. Do not expose this unauthenticated API on the LAN or internet.

## Home Assistant REST commands

```yaml
rest_command:
  sface_sync:
    url: "http://127.0.0.1:5100/sync"
    method: POST
```

Call `rest_command.sface_sync` after updating training images. Recognition needs
an automation/client that sends the raw camera image bytes and interprets scores.

## Optional live camera overlays

In the app's public configuration folder, create `rtsp_creds.json`:

```json
{
  "camera_one": "rtsp://USERNAME:PASSWORD@CAMERA_HOST:554/stream2"
}
```

Supervisor exposes this app configuration folder to file-management apps, usually
under `/app_configs/<repository-id>_sface_yunet/`; older versions use
`/addon_configs`. This app reads it at `/config/rtsp_creds.json`. Keep its
permissions restricted and never upload it to issues. Restart after changing it.
Recognition works without this file. A low-resolution camera substream reduces
CPU and memory use. Some camera/backend errors may include RTSP URLs in logs;
redact all logs before sharing.

Use `http://127.0.0.1:5100/live/camera_one` as the MJPEG URL in Home Assistant's
**MJPEG IP Camera** integration. Home Assistant then proxies viewing through its
own camera entity. Streams capture/infer only while a viewer is connected.

## Backups, updates and existing installations

Private `/data/faces.db` is included when this app is selected for a Supervisor
backup; cold backups stop the service briefly. Back up training photos with
Home Assistant configuration, and protect the RTSP configuration with your backups.

Existing local/standalone installations use a different Supervisor app ID.
Installing this repository will not automatically move their data. Choose a free
port for parallel testing, stop the old service for a consistent SQLite copy,
transfer only on your own host, compare hashes/counts, then switch ports. Keep
the original data until migration is verified. Do not uninstall an existing app
before preserving its private data. Normal updates within the same app ID retain `/data`.

## Troubleshooting

- Build fails: verify internet access to PyPI and GitHub model downloads and free disk.
- Empty enrollment: check training path, call `/sync`, inspect `skipped` filenames.
- Address in use: stop the existing listener or configure a different port.
- Low scores: improve face size, focus, lighting and enrollment variety.
- No live stream: check local camera credentials and connectivity; recognition API is separate.

For source builds: `docker build -t sface-yunet sface_yunet`. The container can be
smoke-tested using `python tests/smoke.py` with dependencies and models installed,
or through the repository's GitHub Actions workflow.

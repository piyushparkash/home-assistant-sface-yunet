# Setup and usage

## Face library UI

Select **Open Web UI** on the app page. The UI is proxied and authenticated through
Home Assistant Ingress; its separate listener accepts only Supervisor and local
host connections. You can start and enroll through the UI without creating any
training folders. Existing installations retain their selected legacy training
path. If that folder is unavailable, the existing embedding database is preserved
and `/sync` refuses to remove enrollments; UI-managed enrollment still works.

- **People:** upload a clear photo with exactly one face, create a person or choose
  an existing person, rename their display name, or remove individual photos.
- **Review inbox:** unknown crops are grouped by SFace similarity. Select only clear
  photos of the same person and assign them to an existing or new name. Unselected
  photos stay for review. You can dismiss a mistaken group. A person may appear in
  several groups; select the same existing person to enroll each group.
- **Cameras & automations:** choose an existing Home Assistant camera, scan it now,
  or set a 30/60/120/300-second snapshot schedule. On-demand is the default. Start
  with one-minute scans on a Pi. A failed camera snapshot is shown in the UI.

New UI photos, vectors, display names, ignored legacy samples and unknown groups
are stored in private `/data/review.db`. The old `/data/faces.db` and original
training files are preserved. Removing a legacy photo hides it from recognition;
the source file remains read-only. Managed photos removed through the UI are deleted.
Display-name changes keep `person_id` stable for automations. At most 100 managed
photos can be enrolled per person.

Unknown collection runs on `/recognize` requests, configured camera snapshots,
and live overlays while viewed (sampled at most once every ten seconds per stream).
It stores only face crops meeting minimum size and detection-score checks.
By default it keeps up to six review photos per group, 100 groups and seven days
of history. Similarity is a suggestion, not proof that all photos show one person.
Review every selected image before naming it. No identity is enrolled automatically.

## Home Assistant automation entities

Install **Mosquitto broker** and set up Home Assistant's **MQTT integration**.
With `mqtt_enabled: true`, the app obtains broker credentials internally from
Supervisor and publishes discovery. No account token or broker password is entered
in the UI. Look under **Settings > Devices & services > MQTT** for the
**SFace face recognition** device.

| Entity (default ID) | Use |
| --- | --- |
| `event.sface_recognition` | Timestamped recognized/unknown events with person ID, display name, camera, score and group ID |
| `sensor.sface_last_recognized` | Last accepted person's display name and recognition attributes |
| `sensor.sface_known_people` | Number of enrolled people, including legacy enrollments |
| `sensor.sface_pending_groups` | Number of unknown groups waiting for review |
| `binary_sensor.sface_person_<person_id>` | On for two minutes after an accepted sighting; this is recent camera visibility, not home presence |
| `button.sface_scan_camera_<camera_name>` | Request a snapshot scan of a configured camera |

Home Assistant may suffix entity IDs if another device already uses those IDs.
The UI reports MQTT connection/setup status. Discovery remains optional; recognition
and the face library work when the broker is down. Events generated while offline
are not replayed as fresh sightings after reconnecting. Event messages are not
retained; discovery and the last-recognized summary are retained. Recently-seen
sensors reset off after app restart. Repeated sightings of the same person/group
from the same source are throttled to one event per 15 seconds.

Example notification on a recognized person (replace the person ID/entity as needed):

```yaml
alias: Notify when a face is recognized
triggers:
  - trigger: state
    entity_id: event.sface_recognition
conditions:
  - condition: template
    value_template: >-
      {{ trigger.to_state is not none
         and trigger.to_state.attributes.get('event_type') == 'recognized'
         and trigger.to_state.attributes.get('person_id') == 'alex' }}
actions:
  - action: persistent_notification.create
    data:
      title: Face recognized
      message: >-
        {{ trigger.to_state.attributes.display_name }} was seen by
        {{ trigger.to_state.attributes.camera }}.
```

To scan after a camera's motion sensor changes, use a normal automation action
`button.press` targeting its discovered SFace scan button. The JSON recognition
events are also available on `sface/<instance_id>/event`; the UI reports that
instance's topic prefix. Existing HTTP clients can add `?camera=front_door` or the
`X-Camera-ID` header to `/recognize` to provide a source label. Clients without a
label continue working and use `api` as their source. `?collect=false` requests
recognition without review storage or automation events (useful for diagnostics).

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

For legacy folder-based enrollment, start the app, then run these commands on the Home
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
| `recognition_threshold` | `0.363` | Acceptance cutoff for new events/review and overlay coloring |
| `min_available_memory_mb` | `300` | Refuse recognition below this host-memory level |
| `collect_unknowns` | `true` | Keep unknown face crops privately for review |
| `unknown_retention_days` | `7` | Expire unknown groups after this many days without a sighting |
| `max_unknown_groups` | `100` | Retain at most this many unknown groups (maximum setting 500) |
| `unknown_group_threshold` | `0.6` | Cosine threshold for grouping unknown faces; higher is more conservative |
| `match_margin` | `0.05` | Minimum score advantage over the second candidate for accepted events |
| `mqtt_enabled` | `true` | Publish Home Assistant entities/events through MQTT discovery |

`/recognize` still returns the best candidate even when its score is low, preserving
compatibility. It adds `recognized` and, when collected, `unknown_group` fields.
New automation events apply both `recognition_threshold` and `match_margin`;
legacy callers can continue applying their own thresholds. The defaults need tuning with
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

For migrations, an existing private `/data/rtsp_creds.json` is also supported and
takes precedence over the public configuration file. Credentials stay on the host.

Use `http://127.0.0.1:5100/live/camera_one` as the MJPEG URL in Home Assistant's
**MJPEG IP Camera** integration. Home Assistant then proxies viewing through its
own camera entity. Streams capture/infer only while a viewer is connected.

## Backups, updates and existing installations

Private `/data/faces.db` is included when this app is selected for a Supervisor
backup; cold backups stop the service briefly. Back up training photos with
Home Assistant configuration, and protect the RTSP configuration with your backups.
The new `/data/review.db` is also part of the app backup. It includes managed
enrollment, unknown crops and display names and must be treated as biometric data.

Upgrading from 1.0.x adds the separate review database; it does not import or
rewrite legacy faces.db rows. Existing recognition clients, camera streams and
person IDs remain compatible. The app needs `homeassistant_api` access for camera
listing/snapshots; Supervisor grants this app administrator-level Core API access.
No Core API credentials are sent to the browser. The training folder stays read-only.

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

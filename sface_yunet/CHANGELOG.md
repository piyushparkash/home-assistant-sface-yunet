# Changelog

## 1.1.1

- Open the face library on a fresh install even when no legacy training folder
  exists. Keep the configured path and preserve existing enrollment; sync still
  refuses an unavailable folder.
- Reject new names that collide with an existing legacy person ID, requiring
  explicit selection before adding photos to that identity.
- Report the built app version in MQTT device information.

## 1.1.0

- Add an Ingress face library with uploads, display-name editing and sample removal.
- Group unknown faces for explicit review; assign selected photos to a person.
- Keep managed enrollment and review data in a separate private database; preserve
  the legacy database and read-only trained photos.
- Add bounded unknown retention, secure deletion, and minimum face-quality checks.
- Add Home Assistant camera selection, scheduled/on-demand scans and MQTT scan buttons.
- Discover recognition events, per-person recently-seen sensors, enrollment and review counts.
- Protect management mutations with CSRF tokens and restrict the UI listener to Ingress/local access.
- Extend backend, security, migration and desktop/mobile browser tests.

The app now requests Home Assistant API access to list cameras and obtain snapshots.
Existing training paths, recognition URLs and stable person IDs remain unchanged.
MQTT requires a broker and the Home Assistant MQTT integration. Unknown collection
is enabled by default; disable it in app options if desired. Stored unknown photos
expire after seven days by default. Grouping suggestions always require human review.

## 1.0.2

- Handle SIGTERM/SIGINT, stop the HTTP server, and close SQLite cleanly.
- Verify graceful shutdown in the smoke tests.

## 1.0.1

- Preserve private RTSP credential files when migrating from a local app.
- Refuse sync if the training directory is unavailable, preserving the database.
- Refresh CI actions to supported Node.js runtime versions.

## 1.0.0

- Initial public Supervisor app packaging for YuNet detection and SFace recognition.
- Private SQLite enrollment storage, optional MJPEG overlays, cold backups.
- Configurable training path and inference settings with loopback-only HTTP.
- Automatic model downloads from a pinned OpenCV Zoo revision with SHA-256 checks.
- Bundled upstream model licenses and attribution; no user data included.

# Changelog

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

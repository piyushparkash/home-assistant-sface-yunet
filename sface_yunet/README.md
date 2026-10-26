# Home Assistant app: SFace + YuNet

Local CPU face recognition using official OpenCV Zoo models. Supervisor manages
the service and its persistent SQLite database. The API binds to loopback.

Open Web UI to upload photos, manage people, and review grouped unknown faces.
Configure existing Home Assistant cameras for snapshots, then use MQTT-discovered
events, per-person sensors and scan buttons in automations.

See [DOCS.md](DOCS.md) for configuration, enrollment, automation examples and live overlays.
See [CREDITS.md](CREDITS.md) for upstream authors, papers, model provenance and licenses.

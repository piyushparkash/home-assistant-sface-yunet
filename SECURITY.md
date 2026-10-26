# Security and privacy

The service runs locally. Model/dependency downloads happen during the image
build; the application performs no cloud recognition or telemetry. Configured
RTSP overlays capture only while viewed. Configured Home Assistant cameras are
queried for snapshots on demand or on the schedule selected in the UI.

Face photos, embeddings, identity names, credentials, query images and raw logs
are private data. The private review database includes unknown face crops and
managed enrollment; include it in protected backups. Unknown groups expire after
seven days without a sighting by default, and storage is bounded by group/sample
limits. Similarity groups require explicit photo selection and naming before
enrollment. Never attach private data to GitHub issues. Use synthetic examples and
redacted diagnostics. Git ignores and Docker build-context exclusions cover common
data formats; review every commit before publishing.

The recognition HTTP API has no authentication and binds to loopback. Other
trusted software on the host may access it. The separate management UI accepts
only Supervisor Ingress and local-host connections, applies CSRF tokens to
mutations, and serves photos with private/no-store headers. Open it through
Home Assistant rather than exposing its listener to the network.

Host networking and read access to Home Assistant configuration are required.
Core API access is requested to list camera entities and obtain snapshots;
Supervisor grants this app administrator-level Core API access. Its token and
MQTT service credentials remain inside the app and are never returned to the UI.
The app requests no Docker socket or privileged capabilities. Install only on
a trusted host and use a trusted MQTT broker. Recognition metadata is published
to that broker; event messages are not retained, while discovery and the
last-recognized summary are retained.

Use recognition with consent. This is a convenience automation service and must
not be the sole authority for physical access or other sensitive decisions.

Report vulnerabilities privately through GitHub's private vulnerability reporting
when available. If unavailable, open a minimal issue asking for a private contact
without disclosing exploit details, images or secrets.

# Security and privacy

The service runs locally. Model/dependency downloads happen during the image
build; the application performs no cloud recognition or telemetry. Configured
RTSP cameras are contacted only when their live overlay is viewed.

Face photos, embeddings, identity names, credentials, query images and raw logs
are private data. Never attach them to GitHub issues. Use synthetic examples and
redacted diagnostics. Git ignores and Docker build-context exclusions cover common
data formats; review every commit before publishing.

The HTTP API has no authentication and binds to loopback. Other software on the
host may access it. Host networking and read access to Home Assistant configuration
are required by this packaging; install only on a trusted host. It requests no
Docker socket, Supervisor API access or privileged capabilities.

Use recognition with consent. This is a convenience automation service and must
not be the sole authority for physical access or other sensitive decisions.

Report vulnerabilities privately through GitHub's private vulnerability reporting
when available. If unavailable, open a minimal issue asking for a private contact
without disclosing exploit details, images or secrets.

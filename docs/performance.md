# Raspberry Pi 4 resource usage

Measured on a **Raspberry Pi 4 with 8 GB RAM**, running Home Assistant OS on
aarch64 and app **1.0.2**. Settings: two OpenCV threads, detection width 640,
and low-resolution RTSP camera substreams for live overlays.

| Workload | App RAM (Docker working set) | CPU average | CPU observed range |
| --- | --- | --- | --- |
| Warmed app, no live viewers | ~241 MiB | 0.03% | ~0.03% |
| One live face-overlay stream | ~245 MiB | ~77% | 61-94% |
| Two live face-overlay streams | ~249-276 MiB | ~127% | 51-194% |

**CPU percentages use Docker's scale: 100% means one fully occupied CPU core.**
The Pi 4 has four cores, so 400% represents its total CPU capacity; the two-stream
average above is about 32% of that capacity. Two OpenCV threads are a setting,
not a hard CPU limit, and this app does not impose a container memory cap.

These are brief, four-sample measurements per workload, including stream startup,
on a host also running Home Assistant automations. They show the app container's
own resource use, not total host usage, and are not peak-memory or sustained-load
guarantees. Camera resolution, lighting, visible faces, request frequency and
other host workloads affect results. Memory allocations may remain after a
stream closes. Snapshot recognition uses CPU while processing each request;
the idle row is not a continuous-recognition benchmark.

Live capture and inference stop when the last viewer disconnects. For lightweight
use, call `/recognize` on selected snapshots and open live overlays when needed.
The default memory guard refuses recognition when host-available RAM falls below
300 MB.

The installed ARM64 image is approximately **353 MiB uncompressed**, including
the models and Python dependencies. Training photos, the embedding database,
build cache and backups require additional disk space; Docker may share image
layers with other apps.

[Back to the overview](../README.md)

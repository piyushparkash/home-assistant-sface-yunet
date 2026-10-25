# SFace + YuNet for Home Assistant

[![Validation](https://github.com/piyushparkash/home-assistant-sface-yunet/actions/workflows/validate.yml/badge.svg)](https://github.com/piyushparkash/home-assistant-sface-yunet/actions/workflows/validate.yml)
![aarch64](https://img.shields.io/badge/aarch64-supported-green)
![amd64](https://img.shields.io/badge/amd64-supported-green)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

CPU face detection and recognition that runs locally on your Home Assistant host.
YuNet finds faces and landmarks; SFace creates embeddings and matches them against
your enrolled photos. Optional RTSP overlays draw names and confidence scores.

This is an independent community app, not an official Home Assistant or OpenCV product.
Raspberry Pi 4 (aarch64) is the original deployment platform; the amd64 build is
checked in CI. Recognition and enrollment require no cloud service or API key.

## Installation

[![Add this repository to your Home Assistant app store](https://my.home-assistant.io/badges/supervisor_store.svg)](https://my.home-assistant.io/redirect/supervisor_store/?repository_url=https%3A%2F%2Fgithub.com%2Fpiyushparkash%2Fhome-assistant-sface-yunet)

1. In Home Assistant OS, open **Settings > Apps > Install app** (older versions:
   **Settings > Add-ons > Add-on store**).
2. Open the three-dot menu, select **Repositories**, and add:
   `https://github.com/piyushparkash/home-assistant-sface-yunet`.
3. Install **SFace + YuNet Face Recognition**. Supervisor builds it on your device;
   the first build needs internet to download dependencies and approximately 37 MB
   of checksum-verified models from OpenCV Zoo.
4. Create a private training folder and add labeled photos as described in the
   [setup guide](sface_yunet/DOCS.md). Start the app and call `POST /sync` to enroll.

The API listens only on `127.0.0.1:5100`. Home Assistant Core can reach it locally;
there is no public web UI, ingress panel, or authentication on the API itself.
The app needs an installation with Supervisor app support; HACS is not required.

## Features

- Multi-face detection and cosine-similarity recognition through OpenCV.
- SQLite embeddings in private app storage; training files mounted read-only.
- Optional live MJPEG overlays, with one shared capture loop per camera.
- Low-memory refusal and configurable CPU thread count and detection settings.
- Supervisor start/stop, automatic boot and cold app backups.

## Documentation and support

- [Configuration, enrollment, API and Home Assistant examples](sface_yunet/DOCS.md)
- [Release notes](sface_yunet/CHANGELOG.md)
- [Model sources, authors, papers and licenses](sface_yunet/CREDITS.md)
- [Security and privacy](SECURITY.md)
- [Report an issue](https://github.com/piyushparkash/home-assistant-sface-yunet/issues)

Your own automations decide when to call the API and how to act on a match. This
repository does not include household automations, Alexa accounts, camera
credentials, enrolled identities, face photos, or embeddings. Use recognition
as an automation aid; similarity scores are not identity guarantees.

## Credits and license

YuNet is by Wei Wu, Hanyang Peng and Shiqi Yu and is provided by OpenCV Zoo under
the MIT license. SFace is contributed by Yaoyao Zhong, with ONNX conversion by
Chengrui Wang, and provided under Apache-2.0. Both model source pages, papers,
original repositories, exact download revision and hashes are in
[CREDITS.md](sface_yunet/CREDITS.md); full model licenses are bundled with the app.

App/server code is MIT-licensed. Model weights and dependencies keep their own
licenses. The installation/documentation structure follows Home Assistant's
[example app repository](https://github.com/home-assistant/apps-example) and
established community app repository conventions; the documentation here is original.

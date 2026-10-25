# Credits and model provenance

This app packages existing research models; it does not train or claim authorship
of YuNet or SFace. The model binaries are downloaded unmodified at image-build time.
The renamed local filenames do not change the weights.

## YuNet face detector

- Authors: Wei Wu, Hanyang Peng and Shiqi Yu.
- Paper: *YuNet: A Tiny Millisecond-level Face Detector*, Machine Intelligence
  Research 20, 656-665 (2023), [DOI: 10.1007/s11633-023-1423-y](https://doi.org/10.1007/s11633-023-1423-y).
- Original projects: [libfacedetection](https://github.com/ShiqiYu/libfacedetection)
  and [libfacedetection.train](https://github.com/ShiqiYu/libfacedetection.train).
- Distribution/model documentation: [OpenCV Zoo YuNet](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet).
- File: `face_detection_yunet_2023mar.onnx`, stored locally as `yunet.onnx`.
- License: MIT; copyright and permission text retained verbatim in
  [licenses/YUNET-LICENSE.txt](licenses/YUNET-LICENSE.txt).

```bibtex
@article{wu2023yunet,
  title={Yunet: A tiny millisecond-level face detector},
  author={Wu, Wei and Peng, Hanyang and Yu, Shiqi},
  journal={Machine Intelligence Research},
  volume={20}, number={5}, pages={656--665}, year={2023}, publisher={Springer}
}
```

## SFace face recognizer

- Research and original implementation: [Yaoyao Zhong and the SFace authors](https://github.com/zhongyy/SFace).
- Paper: [*SFace: Sigmoid-Constrained Hypersphere Loss for Robust Face Recognition*](https://arxiv.org/abs/2205.12010).
- OpenCV Zoo contribution credited to [Yaoyao Zhong](https://github.com/zhongyy).
- ONNX conversion credited to [Chengrui Wang](https://github.com/crywang).
- The distributed model uses MobileFaceNet trained with SFace loss, as documented upstream.
- Distribution/model documentation: [OpenCV Zoo SFace](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_recognition_sface).
- File: `face_recognition_sface_2021dec.onnx`, stored locally as `sface.onnx`.
- License: Apache-2.0; full upstream text retained in
  [licenses/SFACE-LICENSE.txt](licenses/SFACE-LICENSE.txt).

## Exact model source and checksums

Both downloads are pinned to OpenCV Zoo revision
`48b10fa505aeb51fbd127fc60a5c660040e823b7` and fetched from GitHub's Git LFS media endpoint.

| Local file | SHA-256 |
| --- | --- |
| `yunet.onnx` | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| `sface.onnx` | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` |

Direct upstream downloads:

- [YuNet 2023mar ONNX](https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/face_detection_yunet_2023mar.onnx)
- [SFace 2021dec ONNX](https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_recognition_sface/face_recognition_sface_2021dec.onnx)

The build fails on a hash mismatch. Model updates require explicitly reviewing
the upstream source, license and hash before changing `download_models.py`.

## Runtime and packaging

- [OpenCV](https://github.com/opencv/opencv) and
  [opencv-python](https://github.com/opencv/opencv-python): image processing and model inference;
  upstream Apache-2.0 and bundled third-party notices apply.
- [NumPy](https://numpy.org/): embedding operations; BSD-3-Clause and bundled notices apply.
- [Python](https://www.python.org/): HTTP service and SQLite runtime; PSF license.
- [Home Assistant](https://www.home-assistant.io/): Supervisor app hosting;
  packaging/documentation conventions informed by its
  [example repository](https://github.com/home-assistant/apps-example).

Installed dependency distributions retain their own license/notice files inside
the image. The app/server code has its own MIT license. No model license is
replaced by the app license, and no endorsement by the upstream projects is implied.

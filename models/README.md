# Face detection models

`tracker.py` picks the best one your OpenCV can run. Keep this folder next to `tracker.py`.

| File | Model | Source | License |
|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet | [opencv/opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | MIT, Copyright (c) 2020 Shiqi Yu |
| `res10_300x300_ssd_iter_140000.caffemodel` | ResNet 10 SSD | [opencv/opencv_3rdparty](https://github.com/opencv/opencv_3rdparty/tree/dnn_samples_face_detector_20170830) | OpenCV project, see source |
| `deploy.prototxt` | SSD network definition | [opencv/opencv samples](https://github.com/opencv/opencv/tree/4.x/samples/dnn/face_detector) | OpenCV project, see source |

These files are redistributed unchanged. They are not covered by this project's MIT license.

"""
Detector — zero external downloads required.

Uses two OpenCV built-ins:
  - Haar cascade  → face detection  (bundled with opencv-python)
  - HOG descriptor → full-body / person detection (bundled with opencv-python)

Privacy filter triggers when:
  - More than 1 face is detected, OR
  - A person body is detected without a matching face
    (someone approaching from the side / behind), OR
  - A moving object is detected that is neither a face nor a person body
    (uses background subtraction as a lightweight motion sensor)
"""

import threading
import cv2
import numpy as np

HAAR_FACE = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


class ObjectDetector:
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.should_dim = False
        self._running = False
        self._thread = None

        # Face detector
        self._face_cascade = cv2.CascadeClassifier(HAAR_FACE)
        if self._face_cascade.empty():
            raise RuntimeError("Haar cascade not found — reinstall opencv-python.")

        # Person (full body) detector — HOG, no extra files needed
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

        # Background subtractor for generic motion / object detection
        self._bg_sub = cv2.createBackgroundSubtractorMOG2(
            history=120, varThreshold=50, detectShadows=False
        )

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print("[Detector] Could not open webcam.")
            return

        frame_idx = 0
        while self._running:
            ret, frame = cap.read()
            if not ret:
                continue
            frame_idx += 1

            small = cv2.resize(frame, (320, 240))
            gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            cv2.equalizeHist(gray, gray)

            # --- Face detection (every frame) ---
            faces = self._face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(25, 25)
            )
            face_count = len(faces) if isinstance(faces, np.ndarray) else 0

            # --- Person / body detection (every 3rd frame for speed) ---
            person_count = 0
            if frame_idx % 3 == 0:
                bodies, _ = self._hog.detectMultiScale(
                    small, winStride=(8, 8), padding=(4, 4), scale=1.05
                )
                person_count = len(bodies) if isinstance(bodies, np.ndarray) else 0

            # --- Background subtraction: detect significant moving objects ---
            fg_mask = self._bg_sub.apply(small)
            # Morphological cleanup
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
            contours, _ = cv2.findContours(
                fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            # Count blobs large enough to be an object (not noise)
            large_blobs = [c for c in contours if cv2.contourArea(c) > 1500]
            motion_objects = len(large_blobs)

            # --- Decision logic ---
            # Dim if: multiple faces, OR a body without a face,
            # OR motion blobs that exceed what the detected faces account for
            extra_motion = motion_objects > max(face_count, 1)
            self.should_dim = (
                face_count > 1
                or person_count > 1
                or (person_count >= 1 and face_count == 0)
                or extra_motion
            )

        cap.release()

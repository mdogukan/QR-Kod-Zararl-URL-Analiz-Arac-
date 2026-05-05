"""
Privacy Shield – main entry point.
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from detector import ObjectDetector
from overlay import OverlayWindow
from scanner import ScreenScanner

POLL_INTERVAL_MS = 100
DEBOUNCE_FRAMES = 3


def main():
    app = QApplication(sys.argv)

    screen = app.primaryScreen()
    geom = screen.geometry()

    overlay = OverlayWindow(geom)
    detector = ObjectDetector(camera_index=0)
    detector.start()

    scanner = ScreenScanner()
    scanner.start()

    state = {"dimmed": False, "streak": 0}

    def poll():
        wants_dim = detector.should_dim

        if wants_dim == state["dimmed"]:
            state["streak"] = 0
        else:
            state["streak"] += 1
            if state["streak"] >= DEBOUNCE_FRAMES:
                state["dimmed"] = wants_dim
                state["streak"] = 0
                overlay.set_dimming(wants_dim)

        # Always push latest sensitive boxes when dimming is active
        if state["dimmed"]:
            overlay.set_sensitive_boxes(scanner.get_boxes())
        else:
            overlay.set_sensitive_boxes([])

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(POLL_INTERVAL_MS)

    def on_exit():
        detector.stop()
        scanner.stop()

    app.aboutToQuit.connect(on_exit)

    print("[Privacy Shield] Running. Press Ctrl+C in terminal to quit.")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

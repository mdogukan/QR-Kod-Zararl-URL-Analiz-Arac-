"""
Screen scanner — finds sensitive login regions on screen.

Strategy (tries in order, uses whatever is available):
  1. Windows UI Automation via pywinauto — reads accessibility labels of
     focused windows to find password/username fields. Most reliable.
  2. OCR via pytesseract + mss — scans a screenshot for sensitive keywords.
     Works on any app/browser even without accessibility support.
"""

import threading
import re
import time

# ── Availability flags ────────────────────────────────────────────────────────
try:
    import pywinauto
    from pywinauto import Desktop
    UIA_AVAILABLE = True
except Exception:
    UIA_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    import mss
    # Point to default Tesseract install path on Windows if not on PATH
    import shutil, os
    if not shutil.which("tesseract"):
        default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(default):
            pytesseract.pytesseract.tesseract_cmd = default
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

if not UIA_AVAILABLE and not OCR_AVAILABLE:
    print("[Scanner] No detection backend available. "
          "Install pywinauto or pytesseract+mss+Pillow.")

# ── Sensitive keyword pattern ─────────────────────────────────────────────────
SENSITIVE_RE = re.compile(
    r"\b(username|user\s*name|email|e[\-\s]?mail|password|pass\s*word|passcode|"
    r"login|log\s*in|sign\s*in|signin|enter\s*password|confirm\s*password|"
    r"current\s*password|new\s*password|secret|pin\b|token|otp|"
    r"kullan[iı]c[iı]|şifre|parola|giriş|e[\-\s]?posta)\b",
    re.IGNORECASE,
)

BOX_PADDING = 20        # px padding around each detected region
SCAN_INTERVAL = 1.2     # seconds between scans


class ScreenScanner:
    def __init__(self):
        self.sensitive_boxes = []   # [(x, y, w, h), ...] in screen coords
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def get_boxes(self):
        with self._lock:
            return list(self.sensitive_boxes)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run(self):
        while self._running:
            boxes = []
            try:
                if UIA_AVAILABLE:
                    boxes = self._scan_uia()
                if not boxes and OCR_AVAILABLE:
                    boxes = self._scan_ocr()
            except Exception as e:
                print(f"[Scanner] Error: {e}")

            with self._lock:
                self.sensitive_boxes = boxes

            time.sleep(SCAN_INTERVAL)

    # ── Backend 1: Windows UI Automation ─────────────────────────────────────

    def _scan_uia(self):
        boxes = []
        try:
            desktop = Desktop(backend="uia")
            # Inspect the foreground (focused) window only for speed
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return boxes

            app = pywinauto.Application(backend="uia").connect(handle=hwnd)
            win = app.top_window()

            for ctrl in win.descendants():
                try:
                    ctrl_type = ctrl.element_info.control_type
                    name = (ctrl.element_info.name or "").strip()
                    auto_id = (ctrl.element_info.automation_id or "").strip()

                    is_sensitive = (
                        SENSITIVE_RE.search(name)
                        or SENSITIVE_RE.search(auto_id)
                        or ctrl_type in ("Edit", "PasswordEdit")
                        and ctrl.element_info.is_password  # type: ignore
                    )

                    if is_sensitive:
                        rect = ctrl.rectangle()
                        x = rect.left - BOX_PADDING
                        y = rect.top - BOX_PADDING
                        w = (rect.right - rect.left) + BOX_PADDING * 2
                        h = (rect.bottom - rect.top) + BOX_PADDING * 2
                        boxes.append((max(x, 0), max(y, 0), w, h))
                except Exception:
                    continue
        except Exception as e:
            print(f"[Scanner][UIA] {e}")
        return boxes

    # ── Backend 2: OCR screenshot ─────────────────────────────────────────────

    def _scan_ocr(self):
        boxes = []
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

            data = pytesseract.image_to_data(
                img,
                output_type=pytesseract.Output.DICT,
                config="--psm 11",
            )

            for i in range(len(data["text"])):
                word = data["text"][i].strip()
                if not word or int(data["conf"][i]) < 40:
                    continue
                if SENSITIVE_RE.search(word):
                    x = data["left"][i] - BOX_PADDING
                    y = data["top"][i] - BOX_PADDING
                    w = data["width"][i] + BOX_PADDING * 2
                    h = data["height"][i] + BOX_PADDING * 2
                    boxes.append((max(x, 0), max(y, 0), w, h))
        except Exception as e:
            print(f"[Scanner][OCR] {e}")
        return boxes

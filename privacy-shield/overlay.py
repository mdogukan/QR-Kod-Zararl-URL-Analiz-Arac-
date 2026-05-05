"""
Screen overlay with smooth gradient dimming.
Dark at the edges, fading to fully transparent at the center.
No hard lines — uses QLinearGradient for a soft vignette effect.
"""

from PyQt5.QtWidgets import QWidget, QApplication, QLabel
from PyQt5.QtCore import Qt, QTimer, QRect, QPointF
from PyQt5.QtGui import QPainter, QColor, QFont, QLinearGradient

# Maximum alpha for the dim panels (0–255). Higher = darker.
MAX_EDGE_ALPHA = 255

# Fade animation step per tick
FADE_STEP = 15

# Tick interval in ms
TICK_MS = 30


class OverlayWindow(QWidget):
    def __init__(self, screen_geometry):
        super().__init__()
        self._alpha_factor = 0.0
        self._target_factor = 0.0
        self._warning_visible = False
        self._sensitive_boxes = []   # list of (x, y, w, h) to redact

        self._setup_window(screen_geometry)
        self._setup_warning_label()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self, geom):
        self.setGeometry(geom)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowOpacity(1.0)
        self.show()

    def _setup_warning_label(self):
        self._label = QLabel("⚠  Unauthorized presence detected", self)
        self._label.setAlignment(Qt.AlignCenter)
        font = QFont("Segoe UI", 15, QFont.Bold)
        self._label.setFont(font)
        self._label.setStyleSheet(
            "color: white;"
            "background: rgba(160, 0, 0, 180);"
            "border-radius: 8px;"
            "padding: 8px 22px;"
        )
        self._label.adjustSize()
        self._label.hide()
        self._position_label()

    def _position_label(self):
        if not hasattr(self, "_label"):
            return
        lw = self._label.width()
        lh = self._label.height()
        self._label.move((self.width() - lw) // 2, self.height() // 10)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_dimming(self, active: bool):
        self._target_factor = 1.0 if active else 0.0
        self._warning_visible = active

    def set_sensitive_boxes(self, boxes: list):
        """Update the list of sensitive regions to redact. boxes = [(x,y,w,h), ...]"""
        self._sensitive_boxes = boxes
        self.update()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _tick(self):
        step = FADE_STEP / 255.0
        if self._alpha_factor < self._target_factor:
            self._alpha_factor = min(self._alpha_factor + step, self._target_factor)
            self.update()
        elif self._alpha_factor > self._target_factor:
            self._alpha_factor = max(self._alpha_factor - step, self._target_factor)
            self.update()

        if self._warning_visible and self._alpha_factor > 0.05:
            self._label.show()
        else:
            self._label.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        if self._alpha_factor > 0.0:
            edge_alpha = int(MAX_EDGE_ALPHA * self._alpha_factor)
            edge_color = QColor(0, 0, 0, edge_alpha)
            clear_color = QColor(0, 0, 0, 0)
            center = w // 2

            grad_left = QLinearGradient(QPointF(0, 0), QPointF(center, 0))
            grad_left.setColorAt(0.0, edge_color)
            grad_left.setColorAt(0.6, edge_color)
            grad_left.setColorAt(1.0, clear_color)
            painter.fillRect(QRect(0, 0, center, h), grad_left)

            grad_right = QLinearGradient(QPointF(w, 0), QPointF(center, 0))
            grad_right.setColorAt(0.0, edge_color)
            grad_right.setColorAt(0.6, edge_color)
            grad_right.setColorAt(1.0, clear_color)
            painter.fillRect(QRect(center, 0, center, h), grad_right)

        # Sensitive boxes are always drawn when dimming is active
        if self._warning_visible:
            self._draw_sensitive_boxes(painter)

        painter.end()

    def _draw_sensitive_boxes(self, painter):
        """Draw solid black redaction boxes over sensitive text regions."""
        if not self._sensitive_boxes:
            return
        redact_color = QColor(0, 0, 0, 255)
        for (x, y, w, h) in self._sensitive_boxes:
            painter.fillRect(QRect(x, y, w, h), redact_color)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_label"):
            self._position_label()

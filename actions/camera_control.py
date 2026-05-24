"""
camera_control.py — JARVIS live camera window (PyQt6 + OpenCV)

Opens a futuristic HUD-style floating window with a live camera feed.
Camera priority order: index 0 → 2 → 1 → 3 → 4 (first that delivers a frame).
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

from PyQt6.QtCore import QObject, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QLinearGradient,
    QPainter, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)


# ── window singleton ───────────────────────────────────────────
_win_lock: threading.Lock         = threading.Lock()
_win_ref:  "CameraWindow | None" = None


# ── public entry point ─────────────────────────────────────────
# player is a JarvisUI instance whose MainWindow lives in the main thread.
# Calling player.open_camera() emits a queued signal → slot runs in main thread.

def camera_control(parameters: dict, player=None) -> str:
    action = (parameters or {}).get("action", "open").lower()

    if player is None:
        return "No UI player available."

    if action == "close":
        player.close_camera()
        player.write_log("SYS: Camera closed")
        return "Camera closed."
    else:
        player.open_camera(player)
        return "Camera is now open."


# ── helpers ────────────────────────────────────────────────────

def _open_win(player=None) -> None:
    global _win_ref
    with _win_lock:
        if _win_ref is not None and _win_ref.isVisible():
            _win_ref.raise_()
            _win_ref.activateWindow()
            return
        _win_ref = CameraWindow()
        _win_ref.show()
    if player:
        player.write_log("SYS: Camera window opened")


def _close_win() -> None:
    global _win_ref
    with _win_lock:
        if _win_ref is not None:
            _win_ref.close()
            _win_ref = None


# ── camera index selection ─────────────────────────────────────

def _preferred_camera_index(backend: int) -> int:
    """Try indices 0 → 2 → 1 → 3 → 4; return first that delivers a frame."""
    if not _CV2:
        return 0
    for idx in [0, 2, 1, 3, 4]:
        cap = cv2.VideoCapture(idx, backend)
        if cap.isOpened():
            ok, frame = cap.read()
            cap.release()
            if ok and frame is not None:
                print(f"[Camera] ✅ Using camera index {idx}")
                return idx
    print("[Camera] ⚠️  No camera found, defaulting to 0")
    return 0


# ── camera capture → Qt signal bridge ─────────────────────────

class _Bridge(QObject):
    frame_ready = pyqtSignal(object)   # numpy ndarray | None


# ── live-view widget ───────────────────────────────────────────

class _LiveView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #000810;")
        self._px:   QPixmap | None = None
        self._tick: int            = 0
        self._live: bool           = False

    def set_frame(self, px: QPixmap) -> None:
        self._px   = px
        self._live = True
        self.update()

    def set_dead(self) -> None:
        self._live = False
        self.update()

    def tick(self) -> None:
        self._tick += 1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.fillRect(self.rect(), QColor("#000810"))

        # camera frame
        if self._px:
            scaled = self._px.scaled(
                W, H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            ox = (W - scaled.width())  // 2
            oy = (H - scaled.height()) // 2
            p.drawPixmap(ox, oy, scaled)

            # scan sweep
            sweep = (self._tick % 120) / 120.0 * (H + 40) - 20
            if -20 < sweep < H + 5:
                sg = QLinearGradient(0, sweep - 20, 0, sweep + 5)
                sg.setColorAt(0, QColor(0, 0, 0, 0))
                sg.setColorAt(1, QColor(0, 200, 255, 14))
                p.fillRect(
                    QRectF(0.0, max(0.0, sweep - 20), float(W), 25.0),
                    QBrush(sg),
                )
        else:
            p.setFont(QFont("Courier New", 11))
            p.setPen(QPen(QColor("#3a8a9a"), 1))
            p.drawText(
                QRectF(0, 0, W, H),
                Qt.AlignmentFlag.AlignCenter,
                "NO CAMERA SIGNAL",
            )

        # corner brackets
        bl = 24
        p.setPen(QPen(QColor("#00d4ff"), 2.0))
        for bx, by, dx, dy in [
            (0, 0, 1, 1), (W, 0, -1, 1),
            (0, H, 1, -1), (W, H, -1, -1),
        ]:
            p.drawLine(bx, by, bx + dx * bl, by)
            p.drawLine(bx, by, bx, by + dy * bl)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor("#60eeff")))
            p.drawEllipse(bx - 2, by - 2, 5, 5)
            p.setPen(QPen(QColor("#00d4ff"), 2.0))

        # centre reticle
        cx, cy, gap = W / 2, H / 2, 28
        p.setPen(QPen(QColor(0, 212, 255, 110), 1))
        for x0, y0, x1, y1 in [
            (cx - gap - 18, cy,  cx - gap, cy),
            (cx + gap,      cy,  cx + gap + 18, cy),
            (cx, cy - gap - 18,  cx, cy - gap),
            (cx, cy + gap,       cx, cy + gap + 18),
        ]:
            p.drawLine(int(x0), int(y0), int(x1), int(y1))
        p.setPen(QPen(QColor(0, 212, 255, 55), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx - 28), int(cy - 28), 56, 56)

        # REC blink
        if self._live and (self._tick // 18) % 2 == 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor("#ff3355")))
            p.drawEllipse(W - 16, 8, 8, 8)
            p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            p.setPen(QPen(QColor("#ff3355"), 1))
            p.drawText(
                QRectF(W - 48, 4, 28, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "REC",
            )


# ── main camera window ─────────────────────────────────────────

class CameraWindow(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("J.A.R.V.I.S — CAMERA")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(680, 540)
        self.setStyleSheet("background: #000810; border: none;")

        self._bridge = _Bridge()
        self._bridge.frame_ready.connect(self._on_frame)

        self._running   = False
        self._cap_thread: threading.Thread | None = None
        self._fps       = 0.0
        self._frame_cnt = 0
        self._fps_ts    = time.time()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._make_header())

        self._view = _LiveView()
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        root.addWidget(self._view, stretch=1)
        root.addWidget(self._make_footer())

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._view.tick)
        self._anim.start(40)

        self._start_capture()

    def _make_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(38)
        w.setStyleSheet("background: #000912; border-bottom: 1px solid #0a2840;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 10, 0)

        title = QLabel("◈  LIVE CAMERA FEED")
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title.setStyleSheet("color: #00d4ff; background: transparent;")
        lay.addWidget(title)
        lay.addStretch()

        self._status = QLabel("● CONNECTING")
        self._status.setFont(QFont("Courier New", 8))
        self._status.setStyleSheet("color: #ffcc00; background: transparent;")
        lay.addWidget(self._status)
        lay.addSpacing(12)

        close = QPushButton("✕")
        close.setFixedSize(26, 26)
        close.setFont(QFont("Courier New", 11))
        close.setStyleSheet(
            "QPushButton { background: transparent; color: #3a8a9a; border: none; }"
            "QPushButton:hover { color: #ff3355; }"
        )
        close.clicked.connect(self.close)
        lay.addWidget(close)
        return w

    def _make_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(28)
        w.setStyleSheet("background: #000912; border-top: 1px solid #0a2840;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 14, 0)

        self._info = QLabel("RESOLUTION: --  ·  FPS: --")
        self._info.setFont(QFont("Courier New", 7))
        self._info.setStyleSheet("color: #3a8a9a; background: transparent;")
        lay.addWidget(self._info)
        lay.addStretch()

        brand = QLabel("J.A.R.V.I.S  MARK XXXIX")
        brand.setFont(QFont("Courier New", 7))
        brand.setStyleSheet("color: #0f4572; background: transparent;")
        lay.addWidget(brand)
        return w

    def _start_capture(self) -> None:
        self._running = True
        self._cap_thread = threading.Thread(
            target=self._capture_loop, daemon=True
        )
        self._cap_thread.start()

    def _capture_loop(self) -> None:
        if not _CV2:
            self._bridge.frame_ready.emit(None)
            return

        try:
            _root = str(Path(__file__).parent.parent)
            if _root not in sys.path:
                sys.path.insert(0, _root)
            from actions.screen_processor import _cv2_backend
            backend = _cv2_backend()
        except Exception:
            backend = cv2.CAP_ANY

        idx = _preferred_camera_index(backend)
        cap = cv2.VideoCapture(idx, backend)

        if not cap.isOpened():
            self._bridge.frame_ready.emit(None)
            return

        for _ in range(6):   # warmup
            cap.read()

        while self._running:
            ok, frame = cap.read()
            if ok and frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._bridge.frame_ready.emit(rgb)

                self._frame_cnt += 1
                now = time.time()
                if now - self._fps_ts >= 1.0:
                    self._fps       = self._frame_cnt / (now - self._fps_ts)
                    self._frame_cnt = 0
                    self._fps_ts    = now

            time.sleep(0.033)

        cap.release()

    def _on_frame(self, rgb) -> None:
        if rgb is None:
            self._status.setText("● NO SIGNAL")
            self._status.setStyleSheet("color: #ff3355; background: transparent;")
            self._view.set_dead()
            return

        h, w = rgb.shape[:2]
        img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        self._view.set_frame(QPixmap.fromImage(img))
        self._status.setText("● LIVE")
        self._status.setStyleSheet("color: #00ff88; background: transparent;")
        self._info.setText(f"RESOLUTION: {w}×{h}  ·  FPS: {self._fps:.0f}")

    def closeEvent(self, event) -> None:
        self._running = False
        self._anim.stop()
        super().closeEvent(event)

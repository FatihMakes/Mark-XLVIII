from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar,
)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1120, 760
_MIN_W,     _MIN_H     = 940, 640
_LEFT_W  = 172
_RIGHT_W = 372

_OS = platform.system()


class C:
    BG        = "#000810"
    PANEL     = "#000d1a"
    PANEL2    = "#001020"
    PANEL3    = "#001530"
    BORDER    = "#0a2840"
    BORDER_B  = "#1a6090"
    BORDER_A  = "#0f4572"
    PRI       = "#00d4ff"
    PRI_DIM   = "#007a99"
    PRI_GHO   = "#001f2e"
    PRI_BRT   = "#60eeff"
    PUR       = "#7755dd"
    PUR_DIM   = "#3a2880"
    ACC       = "#ff6b00"
    ACC2      = "#ffcc00"
    GREEN     = "#00ff88"
    GREEN_D   = "#00aa55"
    RED       = "#ff3355"
    MUTED_C   = "#ff3366"
    TEXT      = "#8ffcff"
    TEXT_DIM  = "#3a8a9a"
    TEXT_MED  = "#5ab8cc"
    WHITE     = "#d8f8ff"
    DARK      = "#000912"
    BAR_BG    = "#010d18"
    HEX_COL   = "#001828"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


# ──────────────────────────────────────────────────────────────
#  System metrics
# ──────────────────────────────────────────────────────────────

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0
        self.gpu  = -1.0
        self.tmp  = -1.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()
        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()


# ──────────────────────────────────────────────────────────────
#  Gradient separator widget
# ──────────────────────────────────────────────────────────────

class _GradientLine(QWidget):
    """Thin horizontal gradient accent line."""
    def __init__(self, color: str = C.PRI, height: int = 2, parent=None):
        super().__init__(parent)
        self._hex = color
        self.setFixedHeight(height)

    def paintEvent(self, _):
        p = QPainter(self)
        W = self.width()
        c = QColor(self._hex)
        grad = QLinearGradient(0, 0, W, 0)
        grad.setColorAt(0.00, QColor(c.red(), c.green(), c.blue(), 0))
        grad.setColorAt(0.20, QColor(c.red(), c.green(), c.blue(), 160))
        grad.setColorAt(0.50, QColor(c.red(), c.green(), c.blue(), 255))
        grad.setColorAt(0.80, QColor(c.red(), c.green(), c.blue(), 160))
        grad.setColorAt(1.00, QColor(c.red(), c.green(), c.blue(), 0))
        p.fillRect(self.rect(), QBrush(grad))


class _VertGradientLine(QWidget):
    """Thin vertical gradient accent line."""
    def __init__(self, color: str = C.PRI, width: int = 1, parent=None):
        super().__init__(parent)
        self._hex = color
        self.setFixedWidth(width)

    def paintEvent(self, _):
        p = QPainter(self)
        H = self.height()
        c = QColor(self._hex)
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.00, QColor(c.red(), c.green(), c.blue(), 0))
        grad.setColorAt(0.20, QColor(c.red(), c.green(), c.blue(), 120))
        grad.setColorAt(0.50, QColor(c.red(), c.green(), c.blue(), 200))
        grad.setColorAt(0.80, QColor(c.red(), c.green(), c.blue(), 120))
        grad.setColorAt(1.00, QColor(c.red(), c.green(), c.blue(), 0))
        p.fillRect(self.rect(), QBrush(grad))


# ──────────────────────────────────────────────────────────────
#  HUD canvas (centre piece)
# ──────────────────────────────────────────────────────────────

class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        # 5 rings: main, mid-outer, mid, outer-accent, inner-accent
        self._rings      = [0.0, 72.0, 144.0, 216.0, 288.0]
        self._pulses: list[list[float]] = []
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        self._load_face(face_path)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()
        if now - self._last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.14)
                self._tgt_halo  = random.uniform(145, 190)
            elif self.muted:
                self._tgt_scale = random.uniform(0.998, 1.002)
                self._tgt_halo  = random.uniform(15, 28)
            else:
                self._tgt_scale = random.uniform(1.001, 1.008)
                self._tgt_halo  = random.uniform(48, 68)
            self._last_t = now

        sp = 0.38 if self.speaking else 0.15
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        # 5-ring speed set
        if self.speaking:
            speeds = [1.3, -0.9, 2.0, -0.38, 1.85]
        else:
            speeds = [0.55, -0.35, 0.9, -0.14, 0.78]

        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 4.5 if self.speaking else 2.1
        self._pulses = [
            [r[0] + spd, r[1] - 0.028]
            for r in self._pulses
            if r[0] + spd < lim and r[1] > 0
        ]
        if len(self._pulses) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            self._pulses.append([0.0, 1.0])

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s,
                cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.9, 2.6),
                math.sin(ang) * random.uniform(0.9, 2.6) - 0.4,
                1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.026]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
        self.update()

    # ── drawing helpers ────────────────────────────────────────

    def _draw_hex_grid(self, p: QPainter, W: int, H: int):
        """Subtle hexagonal grid background — the sci-fi signature texture."""
        hex_r = 26.0
        hw    = hex_r * math.sqrt(3)
        hh    = hex_r * 2.0
        rows  = int(H / (hh * 0.75)) + 3
        cols  = int(W / hw) + 3

        path = QPainterPath()
        for row in range(-1, rows):
            for col in range(-1, cols):
                hx = col * hw + (hw / 2 if row % 2 == 1 else 0)
                hy = row * hh * 0.75
                moved = False
                for i in range(6):
                    angle = math.radians(60 * i)
                    vx = hx + hex_r * math.cos(angle)
                    vy = hy + hex_r * math.sin(angle)
                    if not moved:
                        path.moveTo(vx, vy)
                        moved = True
                    else:
                        path.lineTo(vx, vy)
                path.closeSubpath()

        p.setPen(QPen(qcol(C.HEX_COL, 24), 0.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def _draw_corner_brackets(self, p: QPainter, W: int, H: int,
                               cx: float, cy: float, fw: float):
        """Enhanced corner brackets with animated extending tech lines."""
        bl  = 30
        frm = 0.53
        hl  = cx - fw * frm
        hr  = cx + fw * frm
        ht  = cy - fw * frm
        hb  = cy + fw * frm

        for bx, by, dx, dy in [(hl, ht, 1, 1), (hr, ht, -1, 1),
                                (hl, hb, 1, -1), (hr, hb, -1, -1)]:
            # Outer bracket arms
            p.setPen(QPen(qcol(C.PRI, 210), 2.0))
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

            # Inner inset bracket
            p.setPen(QPen(qcol(C.PRI, 70), 1.0))
            p.drawLine(QPointF(bx + dx * 5, by + dy * 5),
                       QPointF(bx + dx * 15, by + dy * 5))
            p.drawLine(QPointF(bx + dx * 5, by + dy * 5),
                       QPointF(bx + dx * 5, by + dy * 15))

            # Animated extension
            ext = int(6 + 8 * math.sin(self._tick * 0.035 + abs(bx) * 0.004))
            p.setPen(QPen(qcol(C.PRI_DIM, 85), 1.0))
            p.drawLine(QPointF(bx + dx * bl, by),
                       QPointF(bx + dx * (bl + ext), by))
            p.drawLine(QPointF(bx, by + dy * bl),
                       QPointF(bx, by + dy * (bl + ext)))

            # Corner anchor dot
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI_BRT, 210)))
            p.drawEllipse(QPointF(bx, by), 2.8, 2.8)

    def _draw_orb(self, p: QPainter, cx: float, cy: float, fw: float):
        """Fallback holographic orb when no face image is loaded."""
        orb_r = int(fw * 0.27 * self._scale)
        oc    = (200, 0, 50) if self.muted else (0, 55, 115)
        col_s = C.MUTED_C if self.muted else C.PRI

        for i in range(10, 0, -1):
            r2  = int(orb_r * i / 10)
            frc = i / 10
            a   = max(0, min(255, int(self._halo * 1.15 * frc)))
            p.setBrush(QBrush(QColor(
                int(oc[0] * frc), int(oc[1] * frc), int(oc[2] * frc), a
            )))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2))

        # Inner highlight
        r_hl = int(orb_r * 0.35)
        hl_g = QRadialGradient(cx - r_hl * 0.3, cy - r_hl * 0.4, r_hl)
        hl_g.setColorAt(0, QColor(255, 255, 255, 45))
        hl_g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(hl_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r_hl, cy - r_hl * 1.2, r_hl * 2, r_hl * 2))

        # Text
        p.setPen(QPen(qcol(col_s, min(255, int(self._halo * 2.3))), 1))
        p.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        p.drawText(QRectF(cx - 90, cy - 16, 180, 32),
                   Qt.AlignmentFlag.AlignCenter, "J.A.R.V.I.S")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(col_s, min(255, int(self._halo * 1.3))), 1))
        p.drawText(QRectF(cx - 70, cy + 10, 140, 16),
                   Qt.AlignmentFlag.AlignCenter, "MARK  XXXIX")

    # ── main paint ─────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H   = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw     = min(W, H)

        # 1 ── Hex grid
        self._draw_hex_grid(p, W, H)

        # 2 ── Slow vertical scan sweep
        sweep = (self._tick % 280) / 280.0 * (H + 60) - 30
        if -30 < sweep < H + 10:
            sg = QLinearGradient(0, sweep - 28, 0, sweep + 6)
            sg.setColorAt(0, QColor(0, 0, 0, 0))
            alpha = 12 if not self.speaking else 22
            sg.setColorAt(1, QColor(0, 200, 255, alpha))
            p.fillRect(QRectF(0, max(0.0, sweep - 28), float(W), 34.0),
                       QBrush(sg))

        r_face = fw * 0.31

        # 3 ── Halo glow layers
        for i in range(13):
            r   = r_face * (2.05 - i * 0.075)
            frc = 1.0 - i / 13
            a   = max(0, min(255, int(self._halo * 0.082 * frc)))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # 4 ── Pulse rings
        for pr_r, pr_a in self._pulses:
            a   = max(0, int(240 * pr_a * (1.0 - pr_r / (fw * 0.74))))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr_r, cy - pr_r, pr_r * 2, pr_r * 2))

        # 5 ── Five rotating arc rings
        ring_cfg = [
            (0.50, 3.0, 115, 78,  C.PRI,     0),   # main outer
            (0.42, 2.0,  78, 52,  C.PRI,     1),   # mid-outer
            (0.34, 1.5,  56, 40,  C.PRI,     2),   # mid
            (0.60, 1.0,  22, 88,  C.PUR,     3),   # purple outer
            (0.27, 1.0,  38, 28,  C.ACC,     4),   # accent inner
        ]
        for r_frac, w_r, arc_l, gap, ring_col, ring_idx in ring_cfg:
            ring_r = fw * r_frac
            base   = self._rings[ring_idx]
            depth  = 1.0 - ring_idx * 0.14
            a_val  = max(0, min(255, int(self._halo * depth * 1.15)))
            if self.muted:
                draw_col = qcol(C.MUTED_C, a_val)
            else:
                draw_col = qcol(ring_col, a_val)
            p.setPen(QPen(draw_col, w_r))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            angle = base
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap

        # 6 ── Dual scanner arcs + purple third
        sr    = fw * 0.52
        sa    = min(255, int(self._halo * 1.9))
        ex    = 82 if self.speaking else 50
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, sa), 2.5))
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.PUR, sa // 3), 1.0))
        p.drawArc(srect, int(((self._scan + 180) % 360) * 16), int(28 * 16))

        # 7 ── Tick marks (3 sizes: cardinal / major / minor)
        t_out, t_in = fw * 0.497, fw * 0.472
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            if deg % 90 == 0:
                inn, a_v, w_p = t_in - 5, 210, 1.8
            elif deg % 30 == 0:
                inn, a_v, w_p = t_in, 145, 1.0
            else:
                inn, a_v, w_p = t_in + 5, 65, 0.7
            p.setPen(QPen(qcol(C.PRI, a_v), w_p))
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        # Cardinal position accent arcs
        for deg in [0, 90, 180, 270]:
            r_c = fw * 0.505
            p.setPen(QPen(qcol(C.PRI_BRT, 170), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(cx - r_c, cy - r_c, r_c * 2, r_c * 2),
                      int((deg - 4) * 16), int(8 * 16))

        # 8 ── Crosshair
        ch_r, gap_h = fw * 0.54, fw * 0.16
        p.setPen(QPen(qcol(C.PRI, int(self._halo * 0.5)), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        # 9 ── Corner brackets
        self._draw_corner_brackets(p, W, H, cx, cy, fw)

        # 10 ── Data readout labels at NE / SE / SW / NW positions
        r_lbl = fw * 0.58
        snap  = _metrics.snapshot()
        readouts = [
            (45,  f"CPU {snap['cpu']:.0f}%"),
            (135, f"MEM {snap['mem']:.0f}%"),
            (225, f"GPU {snap['gpu']:.0f}%" if snap['gpu'] >= 0 else "GPU N/A"),
            (315, f"NET {snap['net']:.1f}M" if snap['net'] >= 1 else f"NET {snap['net']*1024:.0f}K"),
        ]
        p.setFont(QFont("Courier New", 7))
        for deg, txt in readouts:
            rad = math.radians(deg)
            lx  = cx + r_lbl * math.cos(rad) - 28
            ly  = cy - r_lbl * math.sin(rad) - 8
            p.setPen(QPen(qcol(C.TEXT_DIM, 140), 1))
            p.drawText(QRectF(lx, ly, 56, 16), Qt.AlignmentFlag.AlignCenter, txt)

        # 11 ── Face or orb
        if self._face_px:
            fsz    = int(fw * 0.62 * self._scale)
            scaled = self._face_px.scaled(
                fsz, fsz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(int(cx - fsz / 2), int(cy - fsz / 2), scaled)
        else:
            self._draw_orb(p, cx, cy, fw)

        # 12 ── Particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI_BRT, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        # 13 ── Status text with gradient backing strip
        sy = cy + fw * 0.40
        if self.muted:
            txt, col = "⊘  MUTED",     qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "●  SPEAKING",  qcol(C.ACC)
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  THINKING",   qcol(C.ACC2)
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  PROCESSING", qcol(C.ACC2)
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  LISTENING",  qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {self.state}", qcol(C.PRI)

        # Semi-transparent backdrop for status
        sg = QLinearGradient(cx - 100, 0, cx + 100, 0)
        sg.setColorAt(0, QColor(0, 0, 0, 0))
        sg.setColorAt(0.3, QColor(0, 10, 18, 170))
        sg.setColorAt(0.7, QColor(0, 10, 18, 170))
        sg.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(cx - 100, sy - 4, 200, 24), QBrush(sg))

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy - 2, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        # 14 ── Waveform (enhanced)
        wy  = sy + 32
        N   = 42
        bw  = 7
        wx0 = (W - N * bw) / 2
        for i in range(N):
            if self.muted:
                hgt = 2
                cl  = qcol(C.MUTED_C, 140)
            elif self.speaking:
                hgt = random.randint(3, 24)
                frc = hgt / 24
                if frc > 0.72:
                    cl = qcol(C.PRI_BRT)
                elif frc > 0.44:
                    cl = qcol(C.PRI)
                else:
                    cl = qcol(C.PRI_DIM, 190)
            else:
                hgt = int(3 + 2.5 * math.sin(self._tick * 0.09 + i * 0.6))
                cl  = qcol(C.BORDER_B, 150)
            p.fillRect(QRectF(wx0 + i * bw, wy + 24 - hgt, bw - 2, hgt), cl)


# ──────────────────────────────────────────────────────────────
#  Metric bar (segmented neon style)
# ──────────────────────────────────────────────────────────────

class MetricBar(QWidget):
    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0
        self._text  = "--"
        self.setFixedHeight(50)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        # Panel background
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, W - 2, H - 2), 5, 5)
        p.fillPath(path, QBrush(qcol(C.PANEL2)))

        # Active value color
        if self._value > 85:
            val_col = qcol(C.RED)
        elif self._value > 65:
            val_col = qcol(C.ACC)
        else:
            val_col = qcol(self._color)

        # Border (glows when high)
        border_a = 90 + int(self._value * 0.7)
        if self._value > 85:
            border_col = qcol(C.RED, border_a)
        elif self._value > 65:
            border_col = qcol(C.ACC, border_a)
        else:
            border_col = qcol(C.BORDER_A, 130)
        p.setPen(QPen(border_col, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 5, 5)

        # Label
        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(9, 7, 54, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._label)

        # Value text
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.setPen(QPen(val_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 5, W - 9, 20),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   self._text)

        # Segmented bar (10 blocks)
        n_segs  = 10
        bar_x   = 9
        bar_w   = W - 18
        bar_y   = H - 14
        bar_h   = 7
        seg_gap = 2
        seg_w   = (bar_w - (n_segs - 1) * seg_gap) / n_segs
        filled  = int(self._value / 100 * n_segs)

        for i in range(n_segs):
            sx = bar_x + i * (seg_w + seg_gap)
            if i < filled:
                # Outer glow
                for g in range(3, 0, -1):
                    glow = QColor(val_col)
                    glow.setAlpha(18 * g)
                    p.setBrush(QBrush(glow))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(
                        QRectF(sx - g, bar_y - g, seg_w + 2 * g, bar_h + 2 * g),
                        2.0, 2.0
                    )
                # Filled segment with top highlight gradient
                bright = QColor(val_col)
                bright.setAlpha(255)
                seg_g = QLinearGradient(sx, bar_y, sx, bar_y + bar_h)
                seg_g.setColorAt(0.0, bright.lighter(135))
                seg_g.setColorAt(1.0, val_col)
                p.setBrush(QBrush(seg_g))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(QRectF(sx, bar_y, seg_w, bar_h), 1.5, 1.5)
            else:
                p.setBrush(QBrush(qcol(C.BAR_BG)))
                p.setPen(QPen(qcol(C.BORDER, 70), 0.5))
                p.drawRoundedRect(QRectF(sx, bar_y, seg_w, bar_h), 1.5, 1.5)


# ──────────────────────────────────────────────────────────────
#  Log widget
# ──────────────────────────────────────────────────────────────

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER_A};
                border-radius: 5px;
                padding: 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 6px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:"):    self._tag = "you"
        elif tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif "err" in tl:              self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)


# ──────────────────────────────────────────────────────────────
#  File drop zone
# ──────────────────────────────────────────────────────────────

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for JARVIS", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        # Background
        if z._drag_over:
            bg = qcol("#001a2a")
        elif z._hovering:
            bg = qcol("#001220")
        else:
            bg = qcol(C.PANEL)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        p.fillPath(path, QBrush(bg))

        # Dashed border
        if z._current_file:
            border_col = qcol(C.GREEN, 210)
        elif z._drag_over:
            border_col = qcol(C.PRI, 240)
        elif z._hovering:
            border_col = qcol(C.BORDER_B, 200)
        else:
            border_col = qcol(C.BORDER, 150)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:    self._paint_file(p, W, H)
        elif z._drag_over:     self._paint_drag_over(p, W, H)
        else:                  self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  ·  Click to Browse")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


# ──────────────────────────────────────────────────────────────
#  Setup overlay
# ──────────────────────────────────────────────────────────────

class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 8, 16, 250);
                border: 1px solid {C.BORDER_B};
                border-radius: 8px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 26)
        layout.setSpacing(10)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        # Title with gradient line accent
        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 14, True))
        layout.addWidget(_lbl("Configure J.A.R.V.I.S before first boot.", 9, color=C.PRI_DIM))

        # Gradient separator
        sep_line = _GradientLine(C.PRI)
        layout.addWidget(sep_line)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(36)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14;
                color: {C.TEXT};
                border: 1px solid {C.BORDER_A};
                border-radius: 4px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRI};
                background: #001520;
            }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(10)

        sep_line2 = _GradientLine(C.BORDER_B)
        layout.addWidget(sep_line2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(8)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows", "⊞  Windows"), ("mac", "  macOS"), ("linux", "🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(14)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        init_btn.setFixedHeight(40)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO};
                color: {C.PRI};
                border: 1px solid {C.PRI_DIM};
                border-radius: 4px;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{
                background: #002535;
                border: 1px solid {C.PRI};
                color: {C.PRI_BRT};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {
            "windows": (C.PRI,   "#001a22"),
            "mac":     (C.ACC2,  "#1a1400"),
            "linux":   (C.GREEN, "#001a0d"),
        }
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg};
                        color: {bg};
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d14;
                        color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER};
                        border-radius: 4px;
                    }}
                    QPushButton:hover {{
                        color: {C.TEXT};
                        border: 1px solid {C.BORDER_B};
                        background: #001020;
                    }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


# ──────────────────────────────────────────────────────────────
#  Main window
# ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    _log_sig      = pyqtSignal(str)
    _state_sig    = pyqtSignal(str)
    _cam_open_sig = pyqtSignal(object)   # carries player; opens camera window
    _cam_close_sig = pyqtSignal()        # closes camera window

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S — MARK XXXIX")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command  = None
        self._muted           = False
        self._current_file: str | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Left panel + right vertical gradient border
        lp_row = QHBoxLayout()
        lp_row.setContentsMargins(0, 0, 0, 0)
        lp_row.setSpacing(0)
        self._left_panel = self._build_left_panel()
        lp_row.addWidget(self._left_panel)
        lp_row.addWidget(_VertGradientLine(C.PRI, 1))

        lp_w = QWidget()
        lp_w.setLayout(lp_row)
        lp_w.setFixedWidth(_LEFT_W + 1)
        body.addWidget(lp_w, stretch=0)

        self.hud = HudCanvas(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(self.hud, stretch=5)

        # Right panel + left vertical gradient border
        rp_row = QHBoxLayout()
        rp_row.setContentsMargins(0, 0, 0, 0)
        rp_row.setSpacing(0)
        rp_row.addWidget(_VertGradientLine(C.PRI, 1))
        self._right_panel = self._build_right_panel()
        rp_row.addWidget(self._right_panel)

        rp_w = QWidget()
        rp_w.setLayout(rp_row)
        rp_w.setFixedWidth(_RIGHT_W + 1)
        body.addWidget(rp_w, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._cam_open_sig.connect(self._do_open_camera)
        self._cam_close_sig.connect(self._do_close_camera)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

    # Camera window — always called in the main thread via queued signal
    def _do_open_camera(self, player):
        from actions.camera_control import _open_win
        _open_win(player)

    def _do_close_camera(self):
        from actions.camera_control import _close_win
        _close_win()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 480, 410
            cw = self.centralWidget()
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()

        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        net = snap["net"]
        net_str = f"{net:.1f}MB/s" if net >= 1.0 else f"{net*1024:.0f}KB/s"
        self._bar_net.set_value(min(100, net * 10), net_str)

        gpu = snap["gpu"]
        self._bar_gpu.set_value(gpu if gpu >= 0 else 0, f"{gpu:.0f}%" if gpu >= 0 else "N/A")

        tmp = snap["tmp"]
        if tmp >= 0:
            self._bar_tmp.set_value(min(100, (tmp / 100) * 100), f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            elapsed = time.time() - psutil.boot_time()
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            self._proc_lbl.setText(f"PROC  {len(psutil.pids())}")
        except Exception:
            self._proc_lbl.setText("PROC  --")

    # ── header ─────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet(f"background: {C.DARK};")

        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        # Content row
        content = QWidget()
        content.setFixedHeight(58)
        content.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(content)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(0)

        # Left: version + status LEDs
        left_col = QVBoxLayout(); left_col.setSpacing(4)
        left_col.addStretch()

        ver = QLabel("MARK · XXXIX")
        ver.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        ver.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; letter-spacing: 2px;")
        left_col.addWidget(ver)

        led_row = QHBoxLayout(); led_row.setSpacing(5)
        for led_col, tip in [(C.GREEN, "●"), (C.PRI, "●"), (C.ACC2, "●")]:
            led = QLabel(tip)
            led.setFont(QFont("Courier New", 9))
            led.setStyleSheet(f"color: {led_col}; background: transparent;")
            led_row.addWidget(led)
        led_row.addStretch()
        left_col.addLayout(led_row)
        left_col.addStretch()
        lay.addLayout(left_col)
        lay.addStretch()

        # Centre: title
        mid = QVBoxLayout(); mid.setSpacing(2)
        title = QLabel("J · A · R · V · I · S")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Courier New", 21, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        mid.addWidget(title)
        sub = QLabel("JUST  A  RATHER  VERY  INTELLIGENT  SYSTEM")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Courier New", 7))
        sub.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; letter-spacing: 2px;")
        mid.addWidget(sub)
        lay.addLayout(mid)
        lay.addStretch()

        # Right: clock
        right_col = QVBoxLayout(); right_col.setSpacing(2)
        right_col.addStretch()
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
        self._date_lbl.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px;"
        )
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        right_col.addStretch()
        lay.addLayout(right_col)

        vlay.addWidget(content)
        vlay.addWidget(_GradientLine(C.PRI, 2))
        return container

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a  %d  %b  %Y"))

    # ── left panel ─────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK};")

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 14, 10, 12)
        lay.setSpacing(8)

        # Section header
        lay.addWidget(self._section_hdr("SYS MONITOR"))

        self._bar_cpu = MetricBar("CPU",  C.PRI)
        self._bar_mem = MetricBar("MEM",  C.ACC2)
        self._bar_net = MetricBar("NET",  C.GREEN)
        self._bar_gpu = MetricBar("GPU",  C.ACC)
        self._bar_tmp = MetricBar("TMP",  "#ff6688")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)

        # Info panel
        info = QWidget()
        info.setStyleSheet(f"""
            QWidget {{
                background: {C.PANEL2};
                border: 1px solid {C.BORDER_A};
                border-radius: 5px;
            }}
            QLabel {{ border: none; background: transparent; }}
        """)
        ip = QVBoxLayout(info)
        ip.setContentsMargins(10, 7, 10, 7)
        ip.setSpacing(4)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN};")
        ip.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED};")
        ip.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont("Courier New", 8))
        os_lbl.setStyleSheet(f"color: {C.ACC2};")
        ip.addWidget(os_lbl)

        lay.addWidget(info)
        lay.addStretch()

        # Status badges
        badges = [
            ("AI CORE\nACTIVE",   C.GREEN,    C.PANEL2,  "1px solid #00aa55"),
            ("SEC\nCLEARED",      C.PRI,      C.PANEL2,  f"1px solid {C.BORDER_A}"),
            ("PROTOCOL\nXXXIX",   C.TEXT_DIM, "#000d14", f"1px solid {C.BORDER}"),
        ]
        for txt, fg, bg, border in badges:
            lbl = QLabel(txt)
            lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {fg}; background: {bg};"
                f"border: {border}; border-radius: 4px; padding: 5px;"
            )
            lay.addWidget(lbl)

        return w

    @staticmethod
    def _section_hdr(title: str) -> QWidget:
        """Compact section header with left accent and trailing gradient line."""
        w = QWidget()
        w.setFixedHeight(22)
        w.setStyleSheet("background: transparent;")

        class _Hdr(QWidget):
            def paintEvent(self_, e):
                p = QPainter(self_)
                W, H = self_.width(), self_.height()
                cy = H / 2

                # Left accent bar
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(qcol(C.PRI, 200)))
                p.drawRect(QRectF(0, cy - 5, 3, 10))

                # Title
                p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
                p.setPen(QPen(qcol(C.PRI, 190), 1))
                txt = f"◈  {title}"
                fm  = p.fontMetrics()
                tw  = fm.horizontalAdvance(txt) + 10
                p.drawText(QRectF(8, 0, tw, H), Qt.AlignmentFlag.AlignVCenter, txt)

                # Trailing fade line
                grad = QLinearGradient(8 + tw, 0, W, 0)
                grad.setColorAt(0, QColor(0, 212, 255, 90))
                grad.setColorAt(1, QColor(0, 212, 255, 0))
                p.fillRect(QRectF(8 + tw, cy - 0.5, W - 8 - tw, 1), QBrush(grad))

        hdr = _Hdr()
        hdr.setFixedHeight(22)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(hdr)
        return w

    # ── right panel ────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK};")

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(7)

        lay.addWidget(self._section_hdr("ACTIVITY LOG"))
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        lay.addWidget(_GradientLine(C.BORDER_A, 1))

        lay.addWidget(self._section_hdr("FILE UPLOAD"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("No file loaded — drop or click above")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        lay.addWidget(_GradientLine(C.BORDER_A, 1))

        lay.addWidget(self._section_hdr("COMMAND INPUT"))
        lay.addLayout(self._build_input_row())

        self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(32)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
        fs_btn.setFixedHeight(28)
        fs_btn.setFont(QFont("Courier New", 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C.TEXT_MED};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.PRI};
                border: 1px solid {C.BORDER_B};
                background: {C.PRI_GHO};
            }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        return w

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(34)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d16;
                color: {C.WHITE};
                border: 1px solid {C.BORDER_A};
                border-radius: 4px;
                padding: 4px 9px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRI};
                background: #001020;
            }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(34, 34)
        send.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO};
                color: {C.PRI};
                border: 1px solid {C.PRI_DIM};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: #002535;
                border: 1px solid {C.PRI};
                color: {C.PRI_BRT};
            }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    # ── footer ─────────────────────────────────────────────────

    def _build_footer(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet(f"background: {C.DARK};")

        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        # Top gradient accent
        vlay.addWidget(_GradientLine(C.BORDER_B, 1))

        content = QWidget()
        content.setFixedHeight(24)
        content.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(content)
        lay.setContentsMargins(16, 0, 16, 0)

        def _fl(txt, color=C.TEXT_DIM):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_fl("[F4] MUTE  ·  [F11] FULLSCREEN", C.TEXT_DIM))
        lay.addStretch()

        # Status LEDs
        status_row = QHBoxLayout(); status_row.setSpacing(10)
        for sc, st in [(C.GREEN, "◉  ONLINE"), (C.PRI, "◉  SECURE"), (C.ACC2, "◉  READY")]:
            status_row.addWidget(_fl(st, sc))
        lay.addLayout(status_row)
        lay.addStretch()

        lay.addWidget(_fl("FatihMakes Industries  ·  MARK XXXIX", C.TEXT_DIM))
        lay.addStretch()
        lay.addWidget(_fl("© FATIHMAKES", C.PRI_DIM))

        vlay.addWidget(content)
        return container

    # ── logic ──────────────────────────────────────────────────

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell JARVIS what to do")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇  MICROPHONE MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140006;
                    color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background: #1e0009;
                }}
            """)
        else:
            self._mute_btn.setText("🎙  MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #00140a;
                    color: {C.GREEN};
                    border: 1px solid {C.GREEN_D};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background: #001f10;
                    border: 1px solid {C.GREEN};
                }}
            """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 480, 410
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. JARVIS online.")


# ──────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class JarvisUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")

    def open_camera(self, player=None):
        """Thread-safe: emits a queued signal so the window is created in the main thread."""
        self._win._cam_open_sig.emit(player or self)

    def close_camera(self):
        self._win._cam_close_sig.emit()

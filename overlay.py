from PySide6.QtCore import Qt, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QFont,
    QColor,
    QPainter,
    QPainterPath,
    QLinearGradient,
    QBrush,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
)

import os
import shutil
import subprocess
import sys


FONT_STACK = ["Inter", "Ubuntu", "Noto Sans", "DejaVu Sans", "Sans Serif"]


class FadeLabel(QLabel):
    """A label that cross-fades whenever its text changes."""

    def __init__(self, text="", duration=180, parent=None):
        super().__init__(text, parent)

        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(1.0)

        self.setGraphicsEffect(self.effect)

        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(duration)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self.on_finished)

        self.pending = None

    def set_text(self, text):

        if text == self.pending:
            return

        if self.pending is None and text == self.text():
            return

        self.pending = text

        # fade the old line out, the swap happens in on_finished
        self.fade_to(0.0)

    def fade_to(self, target):

        self.anim.stop()
        self.anim.setStartValue(self.effect.opacity())
        self.anim.setEndValue(target)
        self.anim.start()

    def on_finished(self):

        if self.pending is None:
            return

        self.setText(self.pending)
        self.pending = None

        self.fade_to(1.0)


class GlassPanel(QWidget):
    """Frosted-glass looking rounded panel, painted by hand."""

    RADIUS = 24

    def __init__(self, parent=None):
        super().__init__(parent)

        self.paused = False

    def set_paused(self, paused):

        if paused == self.paused:
            return

        self.paused = paused
        self.update()

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        # smoked glass body
        body = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        body.setColorAt(0.0, QColor(34, 34, 42, 188))
        body.setColorAt(1.0, QColor(12, 12, 18, 208))

        painter.fillPath(path, QBrush(body))

        # light sheen across the top half
        sheen = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 38))
        sheen.setColorAt(0.55, QColor(255, 255, 255, 6))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.fillPath(path, QBrush(sheen))

        # rim
        painter.setPen(QPen(QColor(255, 255, 255, 46), 1))
        painter.drawPath(path)

        if self.paused:
            self.paint_pause_glyph(painter, rect)

    def paint_pause_glyph(self, painter, rect):

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 120))

        x = rect.right() - 30
        y = rect.top() + 18

        painter.drawRoundedRect(QRectF(x, y, 4, 14), 2, 2)
        painter.drawRoundedRect(QRectF(x + 8, y, 4, 14), 2, 2)


class Overlay(QWidget):

    WIDTH = 1000
    HEIGHT = 236

    MARGIN = 26

    PLAYING_OPACITY = 1.0
    PAUSED_OPACITY = 0.45

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Spotify Overlay")

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            self.MARGIN,
            self.MARGIN,
            self.MARGIN,
            self.MARGIN,
        )

        self.panel = GlassPanel(self)
        outer.addWidget(self.panel)

        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 170))

        self.panel.setGraphicsEffect(shadow)

        inner = QVBoxLayout(self.panel)
        inner.setContentsMargins(34, 20, 34, 20)
        inner.setSpacing(6)

        self.prev_label = self.make_label(15, False, 105)
        self.current_label = self.make_label(25, True, 255)
        self.next_label = self.make_label(15, False, 105)

        self.prev_label.setFixedHeight(26)
        self.next_label.setFixedHeight(26)
        self.current_label.setMinimumHeight(76)

        inner.addWidget(self.prev_label)
        inner.addWidget(self.current_label)
        inner.addWidget(self.next_label)

        self.current_label.setText("♪ Waiting for Spotify...")

        self.resize(self.WIDTH, self.HEIGHT)
        self.move_to_bottom()

        self.dim_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.dim_anim.setDuration(260)
        self.dim_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.setWindowOpacity(self.PLAYING_OPACITY)

    def make_label(self, size, bold, alpha):

        label = FadeLabel("")

        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)

        font = QFont()
        font.setFamilies(FONT_STACK)
        font.setPointSize(size)
        font.setBold(bold)

        label.setFont(font)

        label.setStyleSheet(
            f"QLabel{{ color: rgba(255,255,255,{alpha}); background: transparent; }}"
        )

        return label

    def move_to_bottom(self):

        screen = QApplication.primaryScreen().availableGeometry()

        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + screen.height() - self.height() - 70,
        )

    def show(self):

        super().show()

        enable_backdrop_blur(self)

    # --- slots -------------------------------------------------------

    def update_lyrics(self, previous, current, following):

        self.prev_label.set_text(previous)
        self.current_label.set_text(current)
        self.next_label.set_text(following)

    def update_text(self, text):

        self.update_lyrics("", text, "")

    def set_paused(self, paused):
        """Freeze the lyric on screen and dim the panel."""

        self.panel.set_paused(paused)

        self.dim_anim.stop()
        self.dim_anim.setStartValue(self.windowOpacity())
        self.dim_anim.setEndValue(
            self.PAUSED_OPACITY if paused else self.PLAYING_OPACITY
        )
        self.dim_anim.start()


def enable_backdrop_blur(widget):
    """Ask the compositor to blur what is behind the window.

    KWin (and picom with the KDE rule) honour _KDE_NET_WM_BLUR_BEHIND_REGION.
    GNOME / Mutter exposes no such hint, so this is a no-op there and the
    painted glass gradient carries the look on its own.
    """

    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return

    if not shutil.which("xprop"):
        return

    try:
        subprocess.run(
            [
                "xprop",
                "-id",
                str(int(widget.winId())),
                "-f",
                "_KDE_NET_WM_BLUR_BEHIND_REGION",
                "32c",
                "-set",
                "_KDE_NET_WM_BLUR_BEHIND_REGION",
                "0",
            ],
            check=False,
            capture_output=True,
            timeout=2,
        )

    except Exception:
        pass


if __name__ == "__main__":

    import signal
    from PySide6.QtCore import QTimer

    app = QApplication(sys.argv)

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    w = Overlay()
    w.show()

    w.update_lyrics(
        "the line that just went by",
        "♪ the line playing right now",
        "the line coming up next",
    )

    sys.exit(app.exec())

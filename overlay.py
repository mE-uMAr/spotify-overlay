from PySide6.QtCore import (
    Qt,
    QRectF,
    QPoint,
    QPointF,
    QRect,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    Property,
)
from PySide6.QtGui import (
    QFont,
    QColor,
    QPainter,
    QPainterPath,
    QLinearGradient,
    QBrush,
    QPen,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QGraphicsDropShadowEffect,
)

import json
import os
import shutil
import subprocess
import sys

import platform_support


STATE_FILE = platform_support.state_file()


# the Devanagari face in each list is what stops Hindi/Urdu lyrics from
# shaping wrongly, and it is a different one on either platform
FONT_STACK = (
    ["Inter"]
    + (
        ["Segoe UI", "Nirmala UI"]
        if platform_support.WINDOWS
        else ["Ubuntu", "Noto Sans", "Noto Sans Devanagari"]
    )
    + ["DejaVu Sans", "Sans Serif"]
)


class FadeLabel(QLabel):
    """A label that cross-fades whenever its text changes.

    The fade is done by animating the alpha of the text colour rather than
    with a QGraphicsOpacityEffect: an effect inside a parent that carries its
    own effect (the panel's drop shadow) renders from a stale cached pixmap.
    """

    def __init__(self, base_alpha=255, duration=180, parent=None):
        super().__init__("", parent)

        self.base_alpha = base_alpha

        self._level = 1.0
        self.dim = 1.0

        self.pending = None

        self.anim = QPropertyAnimation(self, b"level", self)
        self.anim.setDuration(duration)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self.on_finished)

        self.apply_colour()

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
        self.anim.setStartValue(self._level)
        self.anim.setEndValue(target)
        self.anim.start()

    def on_finished(self):

        if self.pending is None:
            return

        self.setText(self.pending)
        self.pending = None

        self.fade_to(1.0)

    def set_dim(self, dim):

        self.dim = dim
        self.apply_colour()

    def apply_colour(self):

        palette = self.palette()

        palette.setColor(
            QPalette.ColorRole.WindowText,
            QColor(
                255,
                255,
                255,
                int(self.base_alpha * self._level * self.dim),
            ),
        )

        self.setPalette(palette)

    def get_level(self):
        return self._level

    def set_level(self, value):

        self._level = value
        self.apply_colour()

    level = Property(float, get_level, set_level)


class GlassPanel(QWidget):
    """Frosted-glass looking rounded panel, painted by hand."""

    RADIUS = 24

    def __init__(self, parent=None):
        super().__init__(parent)

        self.paused = False
        self.dim = 1.0

        self.show_grip = True
        self.show_close = True

    def set_paused(self, paused):

        if paused == self.paused:
            return

        self.paused = paused
        self.update()

    def set_dim(self, dim):

        self.dim = dim
        self.update()

    def faded(self, r, g, b, alpha):
        """Colour with its alpha scaled by the current dim level."""

        return QColor(r, g, b, int(alpha * self.dim))

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        # smoked glass body
        body = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        body.setColorAt(0.0, self.faded(34, 34, 42, 96))
        body.setColorAt(1.0, self.faded(12, 12, 18, 118))

        painter.fillPath(path, QBrush(body))

        # light sheen across the top half
        sheen = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        sheen.setColorAt(0.0, self.faded(255, 255, 255, 24))
        sheen.setColorAt(0.55, self.faded(255, 255, 255, 4))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.fillPath(path, QBrush(sheen))

        # rim
        painter.setPen(QPen(self.faded(255, 255, 255, 38), 1))
        painter.drawPath(path)

        if self.paused:
            self.paint_pause_glyph(painter, rect)

        if self.show_grip:
            self.paint_grip(painter, rect)

        if self.show_close:
            self.paint_close(painter, rect)

    def paint_close(self, painter, rect):
        """The only way out: the window has no frame and no taskbar entry."""

        painter.setPen(QPen(self.faded(255, 255, 255, 150), 1.6))

        centre_x = rect.right() - 18
        centre_y = rect.top() + 18

        arm = 5

        painter.drawLine(
            QPointF(centre_x - arm, centre_y - arm),
            QPointF(centre_x + arm, centre_y + arm),
        )
        painter.drawLine(
            QPointF(centre_x + arm, centre_y - arm),
            QPointF(centre_x - arm, centre_y + arm),
        )

    def paint_grip(self, painter, rect):
        """QSizeGrip draws nothing readable on glass, so mark the corner."""

        painter.setPen(QPen(self.faded(255, 255, 255, 85), 1.4))

        corner_x = rect.right() - 8
        corner_y = rect.bottom() - 8

        for offset in (0, 4, 8):

            painter.drawLine(
                QPointF(corner_x - offset, corner_y),
                QPointF(corner_x, corner_y - offset),
            )

    def paint_pause_glyph(self, painter, rect):

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 150))

        # left corner, the right one belongs to the close button
        x = rect.left() + 18
        y = rect.top() + 11

        painter.drawRoundedRect(QRectF(x, y, 4, 14), 2, 2)
        painter.drawRoundedRect(QRectF(x + 8, y, 4, 14), 2, 2)


class Overlay(QWidget):

    WIDTH = 620
    HEIGHT = 168

    MIN_WIDTH = 320
    MIN_HEIGHT = 144

    MARGIN = 16

    PLAYING_DIM = 1.0
    PAUSED_DIM = 0.45

    def __init__(self, click_through=False):
        super().__init__()

        self._dim = self.PLAYING_DIM
        self.labels = []
        self.drag_origin = None
        self.resize_origin = None

        self.setWindowTitle("Spotify Overlay")

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            # never takes focus, so clicking it does not interrupt whatever
            # you were typing in underneath
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )

        # Qt::Tool would be the natural choice, but Qt hides tool windows
        # whenever the application is deactivated, which is exactly what
        # happens when you click on anything else.

        # X11 only: an unmanaged window is not stacked, not owned and not
        # put on a workspace by any window manager, so it floats above
        # every app and follows you between workspaces. Windows has no
        # equivalent — there the shell always owns the window, and
        # keep_above_everything re-asserts topmost instead.
        self.unmanaged = platform_support.LINUX and not on_wayland()

        if self.unmanaged:
            flags |= Qt.WindowType.X11BypassWindowManagerHint

        if click_through:
            flags |= Qt.WindowType.WindowTransparentForInput

        self.setWindowFlags(flags)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # takes the mouse for dragging, never the keyboard, so typing in
        # whatever is underneath is not interrupted
        self.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus)

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
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 150))

        self.panel.setGraphicsEffect(shadow)

        inner = QVBoxLayout(self.panel)
        inner.setContentsMargins(20, 12, 20, 12)
        inner.setSpacing(4)

        self.prev_label = self.make_label(11, False, 125)
        self.current_label = self.make_label(18, True, 255)
        self.next_label = self.make_label(11, False, 125)

        self.prev_label.setFixedHeight(19)
        self.next_label.setFixedHeight(19)
        self.current_label.setMinimumHeight(42)

        inner.addWidget(self.prev_label)
        inner.addWidget(self.current_label)
        inner.addWidget(self.next_label)

        self.current_label.setText("♪ Waiting for Spotify...")

        # QSizeGrip resizes through the window manager, which an unmanaged
        # window does not have, so the corner is handled by hand below
        self.interactive = not click_through

        self.panel.show_grip = self.interactive
        self.panel.show_close = self.interactive

        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)

        self.dim_anim = QPropertyAnimation(self, b"dim", self)
        self.dim_anim.setDuration(260)
        self.dim_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # geometry is written back at most twice a second while dragging
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.save_state)

        self.restore_state()

    def make_label(self, size, bold, alpha):

        label = FadeLabel(alpha)

        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)

        font = QFont()
        font.setFamilies(FONT_STACK)
        font.setPointSize(size)
        font.setBold(bold)

        label.setFont(font)

        self.labels.append(label)

        return label

    def move_to_bottom(self):

        screen = QApplication.primaryScreen().availableGeometry()

        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + screen.height() - self.height() - 70,
        )

    def show(self):

        # the window has to exist before its X11 properties can be set,
        # and the WM only reads some of them when it maps the window
        self.winId()

        # an unmanaged window is already on every workspace and above
        # everything, there is no window manager left to ask
        if not self.unmanaged:
            stick_everywhere(self)

        super().show()

        if not self.unmanaged:
            stick_everywhere(self)

        enable_backdrop_blur(self)

    # --- move and resize ---------------------------------------------

    def resizeEvent(self, event):

        super().resizeEvent(event)

        self.save_timer.start()

    def moveEvent(self, event):

        super().moveEvent(event)

        self.save_timer.start()

    def close_button(self):
        """Hit area of the ✕, in the overlay's own coordinates."""

        return QRect(
            self.width() - self.MARGIN - 30,
            self.MARGIN + 4,
            26,
            26,
        )

    def grip_area(self):

        return QRect(
            self.width() - self.MARGIN - 26,
            self.height() - self.MARGIN - 26,
            26,
            26,
        )

    def mousePressEvent(self, event):

        if not self.interactive:
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        where = event.position().toPoint()

        if self.close_button().contains(where):

            self.save_state()

            QApplication.quit()

            return


        if self.grip_area().contains(where):

            self.resize_origin = (
                event.globalPosition().toPoint(),
                self.size(),
            )

            return


        # startSystemMove asks the window manager to take over, and an
        # unmanaged window has none — it reports success and nothing moves
        if not self.unmanaged:

            handle = self.windowHandle()

            if handle is not None and handle.startSystemMove():
                return


        self.drag_origin = (
            event.globalPosition().toPoint()
            - self.frameGeometry().topLeft()
        )

    def mouseMoveEvent(self, event):

        if not event.buttons() & Qt.MouseButton.LeftButton:
            return


        if self.resize_origin is not None:

            start, size = self.resize_origin

            shift = event.globalPosition().toPoint() - start

            self.resize(
                max(size.width() + shift.x(), self.MIN_WIDTH),
                max(size.height() + shift.y(), self.MIN_HEIGHT),
            )

            return


        if self.drag_origin is not None:

            self.move(
                event.globalPosition().toPoint()
                - self.drag_origin
            )

    def mouseReleaseEvent(self, event):

        self.drag_origin = None
        self.resize_origin = None

    # --- persistence -------------------------------------------------

    def save_state(self):

        try:

            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            STATE_FILE.write_text(
                json.dumps(
                    {
                        "x": self.x(),
                        "y": self.y(),
                        "width": self.width(),
                        "height": self.height(),
                    }
                )
            )

        except Exception as e:

            print("Could not save overlay geometry:", e)

    def restore_state(self):

        state = {}

        try:

            if STATE_FILE.exists():
                state = json.loads(STATE_FILE.read_text())

        except Exception as e:

            print("Could not read overlay geometry:", e)


        self.resize(
            max(int(state.get("width", self.WIDTH)), self.MIN_WIDTH),
            max(int(state.get("height", self.HEIGHT)), self.MIN_HEIGHT),
        )


        if "x" not in state or "y" not in state:

            self.move_to_bottom()

            return


        position = QPoint(int(state["x"]), int(state["y"]))

        if self.on_a_screen(position):
            self.move(position)

        else:
            # the monitor it used to live on is gone
            self.move_to_bottom()

    def on_a_screen(self, position):

        return any(
            screen.availableGeometry().contains(position)
            for screen in QApplication.screens()
        )

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
        self.dim_anim.setStartValue(self._dim)
        self.dim_anim.setEndValue(
            self.PAUSED_DIM if paused else self.PLAYING_DIM
        )
        self.dim_anim.start()

    # --- dim ---------------------------------------------------------
    #
    # Painted rather than done with setWindowOpacity, which the Wayland
    # platform plugin does not implement.

    def get_dim(self):
        return self._dim

    def set_dim(self, dim):

        self._dim = dim

        self.panel.set_dim(dim)

        for label in self.labels:
            label.set_dim(dim)

    dim = Property(float, get_dim, set_dim)


ALL_DESKTOPS = 0xFFFFFFFF


def on_wayland():
    """True only when Qt is really talking Wayland.

    XDG_SESSION_TYPE stays "wayland" under XWayland, where the X11 hints
    below do work, so the platform plugin Qt actually loaded is the only
    honest answer.
    """

    if not platform_support.LINUX:
        return False

    application = QApplication.instance()

    if application is not None:
        return application.platformName().startswith("wayland")

    return os.environ.get("XDG_SESSION_TYPE") == "wayland"


def stick_everywhere(widget):
    """Show the overlay on every workspace, above every other window.

    Qt has no API for "sticky", so on Linux this goes straight at the EWMH
    hints. It needs an X11 session: under a native Wayland session the
    compositor owns window placement and stacking outright, and GNOME
    exposes no protocol for either — run under XWayland
    (QT_QPA_PLATFORM=xcb) for this to bite.

    Windows takes the user32 route in win32.py, which gets the "above
    every window" half but not the "every workspace" half.
    """

    if platform_support.WINDOWS:

        import win32

        return win32.keep_above_everything(int(widget.winId()))

    if on_wayland():
        return False

    window = str(int(widget.winId()))

    # _NET_WM_DESKTOP is read when the window is mapped, wmctrl sends the
    # client messages a running window manager expects instead
    ran = xprop(
        [
            "-id", window,
            "-f", "_NET_WM_DESKTOP", "32c",
            "-set", "_NET_WM_DESKTOP", str(ALL_DESKTOPS),
        ]
    )

    if shutil.which("wmctrl"):

        run(
            [
                "wmctrl", "-i", "-r", window,
                "-b", "add,sticky,above",
            ]
        )

        return True

    return ran


def xprop(arguments):

    if not shutil.which("xprop"):
        return False

    return run(["xprop"] + arguments)


def run(command):

    try:

        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=2,
        )

        return result.returncode == 0

    except Exception:

        return False


def enable_backdrop_blur(widget):
    """Ask the compositor to blur what is behind the window.

    KWin (and picom with the KDE rule) honour _KDE_NET_WM_BLUR_BEHIND_REGION.
    GNOME / Mutter exposes no such hint, so this is a no-op there and the
    painted glass gradient carries the look on its own. On Windows the DWM
    is asked the same favour through win32.py.
    """

    if platform_support.WINDOWS:

        import win32

        win32.enable_blur_behind(int(widget.winId()))

        return

    if on_wayland():
        return

    xprop(
        [
            "-id", str(int(widget.winId())),
            "-f", "_KDE_NET_WM_BLUR_BEHIND_REGION", "32c",
            "-set", "_KDE_NET_WM_BLUR_BEHIND_REGION", "0",
        ]
    )


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

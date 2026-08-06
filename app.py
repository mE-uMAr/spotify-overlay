import argparse
import asyncio
import bisect
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading

from pathlib import Path

import platform_support


if not platform_support.SUPPORTED:
    # said plainly here rather than as an ImportError traceback out of
    # spotify.py, which is where it would otherwise surface
    sys.exit(platform_support.unsupported_message())


HERE = Path(__file__).resolve().parent

# A PyInstaller build unpacks itself into a temp directory and runs from
# there, so HERE finds the bundled icon but is gone by the next login:
# anything written into a launcher has to point at the binary instead.
FROZEN = getattr(sys, "frozen", False)

INSTALL_DIR = Path(sys.executable).resolve().parent if FROZEN else HERE

# libxcb-cursor0 and friends unpacked here without root, see the README
VENDOR_LIB = HERE / "vendor" / "usr" / "lib" / "x86_64-linux-gnu"


def prefer_x11():
    """Restart under the X11 backend before Qt is ever imported.

    Only X11 lets the overlay sit above every window on every workspace:
    a native Wayland client cannot ask for either. Under a Wayland session
    this means going through XWayland, which is what QT_QPA_PLATFORM=xcb
    selects. LD_LIBRARY_PATH has to be set before the process starts, so
    the only way to apply it is to exec ourselves again.

    Linux only — Windows has no X server to prefer and no Wayland to
    escape, and the DWM is always already there.
    """

    if not platform_support.LINUX:
        return

    if os.environ.get("SPOTIFY_OVERLAY_RELAUNCHED"):
        return

    if os.environ.get("QT_QPA_PLATFORM"):
        return

    if not os.environ.get("DISPLAY"):
        return

    environment = dict(os.environ)

    environment["SPOTIFY_OVERLAY_RELAUNCHED"] = "1"
    environment["QT_QPA_PLATFORM"] = "xcb"

    if VENDOR_LIB.is_dir():

        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            [str(VENDOR_LIB)]
            + (
                [environment["LD_LIBRARY_PATH"]]
                if environment.get("LD_LIBRARY_PATH")
                else []
            )
        )

    os.execve(sys.executable, sys.orig_argv, environment)


prefer_x11()


from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from overlay import Overlay
from lyrics import Lyrics

try:
    # the backend for this OS, and the one dependency that is not shared
    from spotify import Spotify, BACKEND

except ImportError as error:

    sys.exit(
        "{error}\n"
        "(or install everything at once: "
        "pip install -r requirements.txt)".format(error=error)
    )


POLL_INTERVAL = 0.2

# metadata barely ever changes, so it is only re-read every Nth tick
METADATA_EVERY = 5

RECONNECT_DELAY = 3.0


class SpotifyWorker(QObject):

    lyrics_changed = Signal(str, str, str)
    paused_changed = Signal(bool)


    def __init__(self):
        super().__init__()

        self.last_song = None
        self.last_index = None
        self.last_paused = None
        self.last_position = 0.0

        self.song_label = ""
        self.synced = True

        self.current_lyrics = []
        self.times = []



    def start(self):

        thread = threading.Thread(
            target=self.run,
            daemon=True
        )

        thread.start()



    def run(self):

        asyncio.run(
            self.loop()
        )



    async def loop(self):

        lyrics = Lyrics()

        spotify = None
        tick = 0


        while True:

            if spotify is None:

                spotify = await self.connect()

                if spotify is None:
                    await asyncio.sleep(RECONNECT_DELAY)
                    continue


            try:

                status = await spotify.status()


                if status != "Playing":

                    # frozen: whatever line is on screen stays on screen
                    self.set_paused(True)

                    if self.last_song is None:

                        # ...except on the very first look, when there is
                        # nothing on screen yet to freeze
                        meta = await spotify.metadata()

                        await self.load_song(lyrics, meta)

                        self.emit_line(
                            await spotify.position()
                        )

                    await asyncio.sleep(POLL_INTERVAL)
                    continue


                self.set_paused(False)


                position = await spotify.position()

                # a jump backwards almost always means the track changed
                rewound = position + 1.0 < self.last_position

                self.last_position = position


                if tick % METADATA_EVERY == 0 or rewound:

                    meta = await spotify.metadata()

                    await self.load_song(lyrics, meta)


                tick += 1

                self.emit_line(position)


            except Exception as e:

                print("Lost Spotify:", e)

                spotify = None

                self.last_song = None
                self.last_index = None

                self.show_message("♪ Waiting for Spotify...")

                await asyncio.sleep(RECONNECT_DELAY)
                continue


            await asyncio.sleep(POLL_INTERVAL)



    async def connect(self):

        try:

            spotify = Spotify()

            await spotify.connect()

            return spotify


        except Exception:

            self.show_message("♪ Waiting for Spotify...")

            return None



    async def load_song(self, lyrics, meta):

        title = meta["title"]
        artist = meta["artist"]


        song = f"{artist}-{title}"

        if song == self.last_song:
            return


        print("Loading lyrics:", song)

        self.last_song = song
        self.last_index = None
        self.song_label = f"{artist} — {title}"

        # the lookup walks several providers and can take seconds, which
        # would otherwise stall the position polling and the pause check
        self.current_lyrics, self.synced = await asyncio.to_thread(
            lyrics.get,
            artist,
            title,
            meta.get("length"),
        )

        self.times = [
            timestamp
            for timestamp, _ in self.current_lyrics
        ]


        if not self.current_lyrics:

            self.show_message(
                "♪ No lyrics available",
                context=self.song_label
            )

            return


        if not self.synced:

            print("  (no timings found, showing the words only)")



    def emit_line(self, position):

        if not self.current_lyrics:
            return


        if not self.synced:

            # unsynced: park on the opening lines instead of chasing
            # a timestamp that never advances
            if self.last_index == 0:
                return

            self.last_index = 0

            self.lyrics_changed.emit(
                self.song_label,
                self.line_at(0),
                self.line_at(1),
            )

            return


        index = bisect.bisect_right(self.times, position) - 1

        if index == self.last_index:
            return

        self.last_index = index


        if index < 0:

            # intro, nothing has been sung yet
            self.lyrics_changed.emit(
                self.song_label,
                "",
                self.line_at(0),
            )

            return


        self.lyrics_changed.emit(
            self.line_at(index - 1),
            self.line_at(index),
            self.line_at(index + 1),
        )



    def line_at(self, index):

        if index < 0 or index >= len(self.current_lyrics):
            return ""


        return self.current_lyrics[index][1]



    def set_paused(self, paused):

        if paused == self.last_paused:
            return

        self.last_paused = paused

        self.paused_changed.emit(paused)



    def show_message(self, text, context=""):

        self.last_index = None

        self.lyrics_changed.emit(context, text, "")



config_home = platform_support.config_home

data_home = platform_support.data_home


ENTRY_NAME = "spotify-overlay.desktop"

ICON = HERE / "icon.png"


DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Version=1.0
Name=Spotify Lyrics Overlay
GenericName=Lyrics Overlay
Comment=Synced lyrics overlay for Spotify
Exec={command}
Icon={icon}
Terminal=false
StartupNotify=false
Categories=AudioVideo;Audio;Music;
Keywords=spotify;lyrics;overlay;music;
"""


# shown in the applications grid, with a right-click action
APPLICATION_EXTRA = """Actions=Locked;

[Desktop Action Locked]
Name=Start locked (ignores the mouse)
Exec={command} --click-through
"""


# runs on login, hidden from the grid, late enough for Spotify to be up
AUTOSTART_EXTRA = """NoDisplay=true
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=15
"""


def entry_paths():
    """Where the launchers go, named the same on either platform.

    "app" is the entry you find by searching the applications menu or the
    Start menu, "autostart" is the one that runs it on login.
    """

    if platform_support.WINDOWS:

        programs = (
            config_home()
            / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )

        return {
            "app": programs / SHORTCUT_NAME,
            "autostart": programs / "Startup" / SHORTCUT_NAME,
        }

    return {
        "app": data_home() / "applications" / ENTRY_NAME,
        "autostart": config_home() / "autostart" / ENTRY_NAME,
    }


def write_entry(path, extra):

    command = shlex.quote(str(launcher()))

    if not FROZEN:
        command += " " + shlex.quote(str(HERE / "app.py"))

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        DESKTOP_ENTRY.format(command=command, icon=ICON)
        + extra.format(command=command)
    )

    path.chmod(0o644)


def write_launcher(path, autostart):

    if platform_support.WINDOWS:

        write_shortcut(path)

        return

    write_entry(
        path,
        AUTOSTART_EXTRA if autostart else APPLICATION_EXTRA,
    )


def install(target):

    paths = entry_paths()

    if target in ("all", "app"):

        write_launcher(paths["app"], autostart=False)

        print("Registered as an application:", paths["app"])

        refresh_menus()


    if target in ("all", "autostart"):

        write_launcher(paths["autostart"], autostart=True)

        print("Starts on login:", paths["autostart"])

        if platform_support.WINDOWS:
            # a .lnk in the Startup folder cannot ask to be held back, but
            # the worker shows "Waiting for Spotify..." and keeps retrying
            # until the client is up, so racing it costs nothing
            print("  (reconnects on its own if Spotify starts later)")

        else:
            print("  (15s late, so Spotify claims its D-Bus name first)")



def uninstall(target):

    paths = entry_paths()

    for name, path in paths.items():

        if target not in ("all", name):
            continue

        if path.exists():

            path.unlink()

            print("Removed:", path)

        else:

            print("Was not installed:", path)


    refresh_menus()



def refresh_menus():
    """Linux only — the Start menu picks up new .lnk files by itself."""

    if platform_support.WINDOWS:
        return

    directory = data_home() / "applications"

    if not shutil.which("update-desktop-database"):
        return

    subprocess.run(
        ["update-desktop-database", str(directory)],
        check=False,
        capture_output=True,
    )



# --- Windows shortcuts ---------------------------------------------------
#
# A .lnk is a binary format with no writer in the standard library, and
# the usual answer, pywin32, would be a dependency carried for these few
# lines alone. PowerShell ships with Windows and speaks the same COM
# interface Explorer itself uses, so it does the writing.

SHORTCUT_NAME = platform_support.APP_NAME + ".lnk"


SHORTCUT_SCRIPT = (
    "$shell = New-Object -ComObject WScript.Shell; "
    "$link = $shell.CreateShortcut({path}); "
    "$link.TargetPath = {target}; "
    "$link.Arguments = {arguments}; "
    "$link.WorkingDirectory = {directory}; "
    "$link.Description = {description}; "
    "{icon}"
    "$link.Save()"
)


def powershell_quote(value):
    """Into a PowerShell single-quoted string, where '' is a literal '."""

    return "'" + str(value).replace("'", "''") + "'"


def launcher():
    """pythonw.exe when it is next to python.exe.

    The overlay has no console to show, and a launcher pointing at
    python.exe leaves a black window sitting behind it for as long as it
    runs. A frozen build is its own launcher and needs neither.
    """

    executable = Path(sys.executable)

    if FROZEN:
        return executable

    windowless = executable.with_name("pythonw.exe")

    if windowless.exists():
        return windowless

    return executable


def shortcut_icon():
    """A .lnk wants an .ico, and the repo ships a .png.

    Qt can write the one from the other, so the conversion happens once at
    install time rather than asking for a second icon in the tree.
    """

    # written next to the binary, not into the temp directory a frozen
    # build unpacks itself into, which is gone before the shortcut is
    # ever clicked
    icon = INSTALL_DIR / "icon.ico"

    if icon.exists():
        return icon

    if not ICON.exists():
        return None

    try:

        from PySide6.QtGui import QImage

        image = QImage(str(ICON))

        if not image.isNull() and image.save(str(icon), "ICO"):
            return icon

    except Exception as error:

        print("Could not convert the icon, using the default:", error)

    return None


def write_shortcut(path):

    path.parent.mkdir(parents=True, exist_ok=True)

    icon = shortcut_icon()

    script = SHORTCUT_SCRIPT.format(
        path=powershell_quote(path),
        target=powershell_quote(launcher()),
        # quoted again inside the argument string, for the spaces a path
        # like C:\Users\Me\My Projects\app.py carries
        arguments=powershell_quote(
            "" if FROZEN else '"{}"'.format(HERE / "app.py")
        ),
        directory=powershell_quote(INSTALL_DIR),
        description=powershell_quote(
            "Synced lyrics overlay for Spotify"
        ),
        icon=(
            "$link.IconLocation = {}; ".format(powershell_quote(icon))
            if icon is not None
            else ""
        ),
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "could not write {path}: {error}".format(
                path=path,
                error=result.stderr.strip() or result.returncode,
            )
        )



SOCKET_NAME = "spotify-overlay-single-instance"


def talk_to_running_instance(message=b""):
    """Return True when an overlay is already up, optionally telling it something."""

    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)

    if not socket.waitForConnected(400):
        return False

    if message:
        socket.write(message)
        socket.waitForBytesWritten(400)

    socket.disconnectFromServer()

    return True


def claim_single_instance(application):
    """Listen for later launches so a second copy cannot stack on the first."""

    server = QLocalServer(application)

    # a copy killed with SIGKILL leaves its socket behind
    QLocalServer.removeServer(SOCKET_NAME)

    server.listen(SOCKET_NAME)

    def on_connection():

        connection = server.nextPendingConnection()

        if connection is None:
            return

        connection.waitForReadyRead(400)

        if bytes(connection.readAll()).strip() == b"quit":

            print("Asked to quit by another launch.")

            application.quit()

    server.newConnection.connect(on_connection)

    return server


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Synced lyrics overlay for Spotify, on Linux and Windows."
        )
    )

    parser.add_argument(
        "--install",
        nargs="?",
        const="all",
        choices=["all", "app", "autostart"],
        help="register in the applications menu and run on login",
    )

    parser.add_argument(
        "--uninstall",
        nargs="?",
        const="all",
        choices=["all", "app", "autostart"],
        help="undo --install",
    )

    parser.add_argument(
        "--click-through",
        action="store_true",
        help="ignore the mouse entirely (no dragging or resizing)",
    )

    parser.add_argument(
        "--quit",
        action="store_true",
        help="close the running overlay",
    )

    args = parser.parse_args()


    print(
        "{platform} detected, reading the current track from {backend}."
        .format(
            platform=platform_support.name(),
            backend=BACKEND,
        )
    )


    if args.install:
        install(args.install)
        return

    if args.uninstall:
        uninstall(args.uninstall)
        return


    app = QApplication(sys.argv)


    if args.quit:

        if talk_to_running_instance(b"quit"):
            print("Closed the running overlay.")

        else:
            print("No overlay was running.")

        return


    if talk_to_running_instance():

        # relaunching from the applications grid used to stack a second
        # copy on top of the first, both drawing the same lyrics
        print("An overlay is already running, leaving it alone.")

        return


    server = claim_single_instance(app)

    # let Ctrl+C through the Qt event loop
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    ticker = QTimer()
    ticker.start(500)
    ticker.timeout.connect(lambda: None)


    overlay = Overlay(click_through=args.click_through)

    overlay.show()


    worker = SpotifyWorker()

    worker.lyrics_changed.connect(overlay.update_lyrics)
    worker.paused_changed.connect(overlay.set_paused)

    worker.start()


    sys.exit(
        app.exec()
    )



if __name__ == "__main__":
    main()

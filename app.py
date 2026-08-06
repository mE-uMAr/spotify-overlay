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


HERE = Path(__file__).resolve().parent

# libxcb-cursor0 and friends unpacked here without root, see the README
VENDOR_LIB = HERE / "vendor" / "usr" / "lib" / "x86_64-linux-gnu"


def prefer_x11():
    """Restart under the X11 backend before Qt is ever imported.

    Only X11 lets the overlay sit above every window on every workspace:
    a native Wayland client cannot ask for either. Under a Wayland session
    this means going through XWayland, which is what QT_QPA_PLATFORM=xcb
    selects. LD_LIBRARY_PATH has to be set before the process starts, so
    the only way to apply it is to exec ourselves again.
    """

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

from overlay import Overlay
from spotify import Spotify
from lyrics import Lyrics


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

                        self.load_song(lyrics, meta)

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

                    self.load_song(lyrics, meta)


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



    def load_song(self, lyrics, meta):

        title = meta["title"]
        artist = meta["artist"]


        song = f"{artist}-{title}"

        if song == self.last_song:
            return


        print("Loading lyrics:", song)

        self.current_lyrics = lyrics.get(
            artist,
            title
        )

        self.times = [
            timestamp
            for timestamp, _ in self.current_lyrics
        ]

        self.last_song = song
        self.last_index = None
        self.song_label = f"{artist} — {title}"

        # lyrics.py hands back plain lyrics with every line stamped 0,
        # there is nothing to follow along with in that case
        self.synced = any(
            timestamp > 0
            for timestamp in self.times
        )


        if not self.current_lyrics:

            self.show_message(
                "♪ No lyrics available",
                context=self.song_label
            )



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



def config_home():

    return Path(
        os.environ.get(
            "XDG_CONFIG_HOME",
            Path.home() / ".config"
        )
    )


def data_home():

    return Path(
        os.environ.get(
            "XDG_DATA_HOME",
            Path.home() / ".local" / "share"
        )
    )


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

    return {
        "app": data_home() / "applications" / ENTRY_NAME,
        "autostart": config_home() / "autostart" / ENTRY_NAME,
    }


def write_entry(path, extra):

    command = "{python} {script}".format(
        python=shlex.quote(sys.executable),
        script=shlex.quote(str(HERE / "app.py")),
    )

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        DESKTOP_ENTRY.format(command=command, icon=ICON)
        + extra.format(command=command)
    )

    path.chmod(0o644)


def install(target):

    paths = entry_paths()

    if target in ("all", "app"):

        write_entry(paths["app"], APPLICATION_EXTRA)

        print("Registered as an application:", paths["app"])

        refresh_menus()


    if target in ("all", "autostart"):

        write_entry(paths["autostart"], AUTOSTART_EXTRA)

        print("Starts on login:", paths["autostart"])
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

    directory = data_home() / "applications"

    if not shutil.which("update-desktop-database"):
        return

    subprocess.run(
        ["update-desktop-database", str(directory)],
        check=False,
        capture_output=True,
    )



def main():

    parser = argparse.ArgumentParser(
        description="Synced lyrics overlay for Spotify on Linux."
    )

    parser.add_argument(
        "--install",
        nargs="?",
        const="all",
        choices=["all", "app", "autostart"],
        help="register in the applications grid and run on login",
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

    args = parser.parse_args()


    if args.install:
        install(args.install)
        return

    if args.uninstall:
        uninstall(args.uninstall)
        return


    app = QApplication(sys.argv)

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

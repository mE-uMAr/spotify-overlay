import argparse
import asyncio
import bisect
import os
import shlex
import signal
import sys
import threading

from pathlib import Path

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


        if not self.current_lyrics:

            self.show_message(
                "♪ No lyrics available",
                context=f"{artist} — {title}"
            )



    def emit_line(self, position):

        if not self.current_lyrics:
            return


        index = bisect.bisect_right(self.times, position) - 1

        if index == self.last_index:
            return

        self.last_index = index


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



AUTOSTART_FILE = (
    Path(
        os.environ.get(
            "XDG_CONFIG_HOME",
            Path.home() / ".config"
        )
    )
    / "autostart"
    / "spotify-overlay.desktop"
)


DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=Spotify Lyrics Overlay
Comment=Synced lyrics overlay for Spotify
Exec={command}
Icon=spotify
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=15
"""


def install_autostart():

    command = "{python} {script}".format(
        python=shlex.quote(sys.executable),
        script=shlex.quote(str(Path(__file__).resolve())),
    )

    AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)

    AUTOSTART_FILE.write_text(
        DESKTOP_ENTRY.format(command=command)
    )

    AUTOSTART_FILE.chmod(0o644)

    print("Autostart installed:", AUTOSTART_FILE)
    print("Starts on login, 15s late so Spotify comes up first.")



def uninstall_autostart():

    if not AUTOSTART_FILE.exists():

        print("Autostart was not installed.")

        return


    AUTOSTART_FILE.unlink()

    print("Autostart removed:", AUTOSTART_FILE)



def main():

    parser = argparse.ArgumentParser(
        description="Synced lyrics overlay for Spotify on Linux."
    )

    parser.add_argument(
        "--install-autostart",
        action="store_true",
        help="run the overlay automatically on login",
    )

    parser.add_argument(
        "--uninstall-autostart",
        action="store_true",
        help="remove the autostart entry",
    )

    args = parser.parse_args()


    if args.install_autostart:
        install_autostart()
        return

    if args.uninstall_autostart:
        uninstall_autostart()
        return


    app = QApplication(sys.argv)

    # let Ctrl+C through the Qt event loop
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    ticker = QTimer()
    ticker.start(500)
    ticker.timeout.connect(lambda: None)


    overlay = Overlay()

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

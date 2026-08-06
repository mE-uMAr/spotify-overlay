# PyInstaller build, for whichever platform it is run on.
#
#   pyinstaller spotify-overlay.spec
#
# Produces a single self-contained binary in dist/ that needs no Python on
# the target machine: SpotifyLyricsOverlay.exe on Windows, spotify-overlay
# on Linux. The workflows under .github/workflows/ run exactly this.

import sys

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


WINDOWS = sys.platform == "win32"


if WINDOWS:

    # The WinRT projection is a pile of separately importable namespace
    # modules PyInstaller cannot see, because spotify_winrt.py reaches
    # them through a try/except and through importlib rather than a
    # plain import.
    hidden = collect_submodules("winrt") + [
        "winrt.windows.media.control",
        "winrt.windows.foundation",
        "winrt.runtime",
    ]

    # the other platform's backend is dead weight, and importing it
    # would only fail
    excludes = ["dbus_next", "spotify_mpris"]

    name = "SpotifyLyricsOverlay"

    # no console: the overlay is the whole interface
    console = False

else:

    hidden = ["dbus_next", "dbus_next.aio"]

    excludes = ["winrt", "winsdk", "spotify_winrt", "win32"]

    name = "spotify-overlay"

    # the Linux build is launched from a terminal and prints what track
    # it is on, so it keeps its stdout
    console = True


icon = Path("icon.ico")


analysis = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("icon.png", ".")],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes + ["tkinter"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name=name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=console,
    disable_windowed_traceback=False,
    icon=str(icon) if icon.exists() else None,
)

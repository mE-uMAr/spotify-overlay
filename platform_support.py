"""Which OS the overlay is running on, decided once at import time.

Everything platform-specific elsewhere branches on the constants here
rather than testing sys.platform again, so there is one place to look
when a third platform ever needs adding.
"""

import os
import sys

from pathlib import Path


WINDOWS = sys.platform == "win32"

LINUX = sys.platform.startswith("linux")

SUPPORTED = WINDOWS or LINUX


APP_NAME = "Spotify Lyrics Overlay"

# the directory both platforms keep state.json in, under their own root
APP_DIR = "spotify-overlay"


def name():
    """Human readable, for the startup line and error messages."""

    if WINDOWS:
        return "Windows"

    if LINUX:
        return "Linux"

    return sys.platform


def config_home():
    """Where per-user settings live.

    %APPDATA% on Windows (roaming, so the overlay comes back in the same
    corner on a domain profile), the XDG config dir on Linux.
    """

    if WINDOWS:

        return Path(
            os.environ.get(
                "APPDATA",
                Path.home() / "AppData" / "Roaming",
            )
        )

    return Path(
        os.environ.get(
            "XDG_CONFIG_HOME",
            Path.home() / ".config",
        )
    )


def data_home():
    """Where installed launchers live."""

    if WINDOWS:

        return Path(
            os.environ.get(
                "LOCALAPPDATA",
                Path.home() / "AppData" / "Local",
            )
        )

    return Path(
        os.environ.get(
            "XDG_DATA_HOME",
            Path.home() / ".local" / "share",
        )
    )


def state_file():
    """Saved overlay geometry."""

    return config_home() / APP_DIR / "state.json"


def unsupported_message():

    return (
        "spotify-overlay runs on Linux and Windows, not on "
        "{platform}.\n"
        "Reading the current track needs MPRIS over D-Bus (Linux) or the "
        "system media session API (Windows), and neither exists here."
    ).format(platform=name())

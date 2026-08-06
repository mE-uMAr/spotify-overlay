"""Now-playing from the Spotify client on Windows, over the media session.

Windows has no MPRIS. The equivalent is the system media transport
controls — the same thing that fills the flyout on the volume keys —
reached through GlobalSystemMediaTransportControlsSessionManager.

The interface mirrors spotify_mpris.Spotify exactly, down to reporting
MPRIS's own "Playing"/"Paused"/"Stopped" vocabulary, so app.py never has
to learn which backend it is talking to.
"""

import importlib
import threading

from datetime import datetime, timezone


try:

    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    )

except ImportError:

    try:
        # winsdk is the older name for the same projection
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        )

    except ImportError as error:

        raise ImportError(
            "The Windows media session bindings are missing. Install them "
            "with:  pip install winrt-Windows.Media.Control"
        ) from error


BACKEND = "Windows media session"


# the desktop client reports "Spotify.exe", the Store build reports
# "SpotifyAB.SpotifyMusic_...!Spotify"
SOURCE_HINT = "spotify"


# GSMTC has states MPRIS does not; fold them onto the three MPRIS names
STATUS = {
    "PLAYING": "Playing",
    "PAUSED": "Paused",
    "STOPPED": "Stopped",
    "CHANGING": "Paused",
    "OPENED": "Paused",
    "CLOSED": "Stopped",
}


# a timeline that has never been updated dates from the WinRT epoch of
# 1601, which no sane elapsed time can reach
MAX_DRIFT = 3600.0


_apartment = threading.local()


def init_apartment():
    """WinRT needs the calling thread put in an apartment, once each.

    The worker runs the whole backend on its own thread, so this cannot be
    done at import time. Where the bindings handle it themselves there is
    no such function to call and nothing to do.
    """

    if getattr(_apartment, "ready", False):
        return

    for module_name in ("winrt.runtime", "winrt.system", "winsdk"):

        try:
            module = importlib.import_module(module_name)

        except ImportError:
            continue

        initialise = getattr(module, "init_apartment", None)

        if initialise is not None:

            initialise()

            break

    _apartment.ready = True


class Spotify:

    async def connect(self):

        init_apartment()

        self.manager = await SessionManager.request_async()

        # raises if Spotify is not running, which is what the reconnect
        # loop in app.py is waiting to see
        self.session()

    def session(self):
        """The live Spotify session, looked up fresh every time.

        Sessions are torn down and rebuilt when the client restarts or
        hands playback to another device, so a cached one goes stale
        silently. Raising when it is gone is what triggers a reconnect.
        """

        for session in self.manager.get_sessions():

            source = session.source_app_user_model_id or ""

            if SOURCE_HINT in source.lower():
                return session

        raise RuntimeError(
            "no Spotify media session (is the desktop client running?)"
        )

    async def metadata(self):

        properties = await self.session().try_get_media_properties_async()

        return {
            "title": properties.title or "",
            "artist": properties.artist or "",
            "album": properties.album_title or "",
            # duration lives on the timeline, not the media properties
            "length": self.length(),
        }

    def length(self):
        """Track length in seconds, 0 when the session will not say."""

        try:

            timeline = self.session().get_timeline_properties()

            return max(timeline.end_time.total_seconds(), 0)

        except Exception:

            return 0

    async def status(self):

        return self.playback_status(self.session())

    def playback_status(self, session):

        state = session.get_playback_info().playback_status

        return STATUS.get(str(state.name).upper(), "Stopped")

    async def position(self):
        """Seconds into the track.

        Windows only pushes a new timeline when something happens — a
        seek, a pause, a track change — so between those the reported
        position is a stale snapshot that would leave the lyrics frozen on
        one line. Adding the wall-clock time since the snapshot was taken
        gives a clock that actually moves, and stays exact as long as
        playback runs uninterrupted (anything that breaks that pushes a
        fresh timeline of its own).
        """

        session = self.session()

        timeline = session.get_timeline_properties()

        # tracks normally start at zero, but the API allows an offset
        start = timeline.start_time.total_seconds()

        position = timeline.position.total_seconds() - start
        duration = timeline.end_time.total_seconds() - start

        if self.playback_status(session) == "Playing":
            position += self.drift(timeline)

        if duration > 0:
            position = min(position, duration)

        return max(position, 0.0)

    def drift(self, timeline):

        updated = timeline.last_updated_time

        if updated is None:
            return 0.0

        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)

        elapsed = (
            datetime.now(timezone.utc) - updated
        ).total_seconds()

        if elapsed < 0 or elapsed > MAX_DRIFT:
            return 0.0

        return elapsed

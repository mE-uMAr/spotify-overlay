"""Now-playing from the Spotify client on Linux, over MPRIS / D-Bus.

Selected by spotify.py on Linux. spotify_winrt.py is the Windows twin and
answers the same four coroutines with the same shapes.
"""

from dbus_next.aio import MessageBus
from dbus_next import Variant


BACKEND = "MPRIS over D-Bus"


class Spotify:

    BUS = "org.mpris.MediaPlayer2.spotify"
    PATH = "/org/mpris/MediaPlayer2"

    async def connect(self):
        self.bus = await MessageBus().connect()

        introspection = await self.bus.introspect(
            self.BUS,
            self.PATH
        )

        obj = self.bus.get_proxy_object(
            self.BUS,
            self.PATH,
            introspection
        )

        self.props = obj.get_interface(
            "org.freedesktop.DBus.Properties"
        )

    async def metadata(self):

        data = await self.props.call_get(
            "org.mpris.MediaPlayer2.Player",
            "Metadata"
        )

        md = data.value

        return {
            "title": md.get("xesam:title", Variant("s", "")).value,
            "artist": md.get("xesam:artist", Variant("as", [""])).value[0],
            "album": md.get("xesam:album", Variant("s", "")).value,
            # microseconds on the bus, seconds everywhere else
            "length": md.get("mpris:length", Variant("x", 0)).value / 1000000,
        }

    async def status(self):

        state = await self.props.call_get(
            "org.mpris.MediaPlayer2.Player",
            "PlaybackStatus"
        )

        return state.value

    async def position(self):

        pos = await self.props.call_get(
            "org.mpris.MediaPlayer2.Player",
            "Position"
        )

        return pos.value / 1000000

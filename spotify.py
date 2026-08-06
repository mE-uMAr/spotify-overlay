from dbus_next.aio import MessageBus
from dbus_next import Variant
import asyncio


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



async def test():

    spotify = Spotify()

    await spotify.connect()

    while True:

        print(await spotify.metadata())
        print(await spotify.status())

        print("-" * 40)

        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(test())

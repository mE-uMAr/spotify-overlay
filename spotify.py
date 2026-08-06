"""Picks the now-playing backend that matches the OS.

Both backends answer the same four coroutines — connect, metadata, status
and position — and both report status in MPRIS's "Playing"/"Paused"/
"Stopped" vocabulary, so nothing downstream knows which one it got.
"""

import asyncio

import platform_support


if platform_support.WINDOWS:
    from spotify_winrt import Spotify, BACKEND

elif platform_support.LINUX:
    from spotify_mpris import Spotify, BACKEND

else:
    raise ImportError(platform_support.unsupported_message())


__all__ = ["Spotify", "BACKEND"]


async def test():

    print("Backend:", BACKEND, "on", platform_support.name())

    spotify = Spotify()

    await spotify.connect()

    while True:

        print(await spotify.metadata())
        print(await spotify.status(), await spotify.position())

        print("-" * 40)

        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(test())

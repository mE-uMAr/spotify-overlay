import re

import requests
from transliterate import romanize


class Lyrics:
    """Synced lyrics, with a chain of fallbacks behind it.

    The one rule that matters: real synced lyrics from *any* provider beat
    plain lyrics from *every* provider. Plain lyrics have no timestamps, so
    anything built from them is a made-up clock that drifts against the
    song — better to keep looking first, and to say so when we settle.
    """

    BASE_URL = "https://lrclib.net/api"

    NETEASE_SEARCH = "https://music.163.com/api/search/get"
    NETEASE_LYRIC = "https://music.163.com/api/song/lyric"

    OVH_URL = "https://api.lyrics.ovh/v1"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    TIMEOUT = 15

    # netease is reliable but slow, it gets its own budget
    SLOW_TIMEOUT = 25


    def get(self, artist, title, duration=None):
        """Return (lines, synced).

        `duration` is the real track length in seconds. Providers hand back
        several versions of the same song — a remix, a radio edit, a live
        cut — and picking one whose length disagrees with what is actually
        playing is what makes lyrics run ahead of or behind the music, so
        the closest length always wins.
        """

        plain = []

        for query_artist, query_title in self.variants(artist, title):

            synced, maybe_plain = self.lrclib(
                query_artist,
                query_title,
                duration,
            )

            if synced:
                return self.romanize_all(synced), True

            plain = plain or maybe_plain


        synced = self.netease(artist, title, duration)

        if synced:
            return self.romanize_all(synced), True


        # nothing synced anywhere, fall back to words without timings
        if plain:
            return self.romanize_all(plain), False


        for provider in (self.genius, self.lyrics_ovh):

            lines = provider(artist, title)

            if lines:
                return self.romanize_all(lines), False


        return [], False


    # ── query variants ────────────────────────────────────────────

    BRACKETS = re.compile(r"\s*[\(\[][^\)\]]*[\]\)]")

    SUFFIX = re.compile(
        r"\s+-\s+(remaster|remastered|live|radio edit|single version|"
        r"from|feat\.?|ft\.?).*$",
        re.IGNORECASE,
    )

    ARTIST_SPLIT = re.compile(
        r"\s*(?:,|&| and | feat\.?| ft\.?| x |;)\s*",
        re.IGNORECASE,
    )


    def variants(self, artist, title):
        """Queries to try, most specific first.

        `Lamha Lamha (From "Aspirants: S3")` by three credited artists is
        filed under plainer names almost everywhere, so the decorations
        come off one layer at a time.
        """

        clean_title = self.clean(title)
        first_artist = self.ARTIST_SPLIT.split(artist)[0].strip()

        candidates = [
            (artist, title),
            (artist, clean_title),
            (first_artist, clean_title),
            ("", clean_title),
        ]

        seen = set()

        for pair in candidates:

            if not pair[1] or pair in seen:
                continue

            seen.add(pair)

            yield pair


    def clean(self, title):

        stripped = self.BRACKETS.sub("", title)
        stripped = self.SUFFIX.sub("", stripped)

        return stripped.strip() or title


    # ── lrclib ────────────────────────────────────────────────────

    def lrclib(self, artist, title, duration):
        """Return (synced_lines, plain_lines) for one query."""

        plain = []

        if artist:

            data = self.fetch(
                f"{self.BASE_URL}/get",
                {"artist_name": artist, "track_name": title},
            )

            if data:

                if data.get("syncedLyrics"):

                    print(f"  lrclib exact: {artist} - {title}")

                    return self.parse_lrc(data["syncedLyrics"]), []

                if data.get("plainLyrics"):
                    plain = self.plain_to_timed(data["plainLyrics"])


        query = f"{artist} {title}".strip()

        results = self.fetch(f"{self.BASE_URL}/search", {"q": query})

        if not results:
            return [], plain


        best = self.closest(results, duration, "syncedLyrics")

        if best:

            print(
                "  lrclib search: {} - {} ({:.0f}s{})".format(
                    best.get("artistName"),
                    best.get("trackName"),
                    best.get("duration") or 0,
                    self.drift(best, duration),
                )
            )

            return self.parse_lrc(best["syncedLyrics"]), plain


        if not plain:

            fallback = self.closest(results, duration, "plainLyrics")

            if fallback:
                plain = self.plain_to_timed(fallback["plainLyrics"])


        return [], plain


    def closest(self, results, duration, key):
        """The candidate carrying `key` whose length best matches the track."""

        usable = [
            item
            for item in results
            if item.get(key)
        ]

        if not usable:
            return None

        if not duration:
            return usable[0]

        return min(
            usable,
            key=lambda item: abs((item.get("duration") or 0) - duration),
        )


    def drift(self, item, duration):

        if not duration:
            return ""

        return ", {:+.0f}s off".format((item.get("duration") or 0) - duration)


    # ── netease ───────────────────────────────────────────────────

    def netease(self, artist, title, duration):
        """Slow, but it carries real timestamps for a lot of what lrclib misses."""

        results = self.fetch(
            self.NETEASE_SEARCH,
            {"s": f"{artist} {title}", "type": 1, "limit": 8},
            timeout=self.SLOW_TIMEOUT,
        )

        songs = ((results or {}).get("result") or {}).get("songs") or []

        if not songs:
            return []


        # netease reports milliseconds
        for song in songs:
            song["duration"] = (song.get("duration") or 0) / 1000

        best = self.closest(songs, duration, "id")

        if not best:
            return []


        lyric = self.fetch(
            self.NETEASE_LYRIC,
            {"id": best["id"], "lv": 1, "kv": 1, "tv": -1},
            timeout=self.SLOW_TIMEOUT,
        )

        raw = ((lyric or {}).get("lrc") or {}).get("lyric") or ""

        lines = self.parse_lrc(raw)

        # a single stamp at zero is a plain dump wearing an LRC costume
        if len([line for line in lines if line[0] > 0]) < 2:
            return []


        print(
            "  netease: {} - {} ({:.0f}s{})".format(
                ", ".join(a["name"] for a in best.get("artists", [])),
                best.get("name"),
                best.get("duration") or 0,
                self.drift(best, duration),
            )
        )

        return lines


    # ── lyrics.ovh (plain, last resort) ───────────────────────────

    def lyrics_ovh(self, artist, title):

        data = self.fetch(f"{self.OVH_URL}/{artist}/{title}")

        words = (data or {}).get("lyrics") or ""

        if not words:
            return []

        print(f"  lyrics.ovh: {artist} - {title} (no timings)")

        return self.plain_to_timed(words)


    # ── genius (plain, last resort) ───────────────────────────────

    def genius(self, artist, title):

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            print("beautifulsoup4 not installed, skipping Genius")
            return []

        try:

            data = self.fetch(
                "https://genius.com/api/search/multi",
                {"q": f"{artist} {title}"},
            )

            sections = (data or {}).get("response", {}).get("sections", [])

            song_url = None

            for section in sections:

                if section.get("type") != "song":
                    continue

                hits = section.get("hits", [])

                if hits:
                    song_url = hits[0]["result"]["url"]
                    break

            if not song_url:
                return []

            print(f"  genius: {song_url} (no timings)")

            response = requests.get(
                song_url,
                headers=self.HEADERS,
                timeout=self.TIMEOUT,
            )

            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "html.parser")

            containers = soup.find_all(
                "div",
                attrs={"data-lyrics-container": "true"},
            )

            lines = []

            for container in containers:

                for br in container.find_all("br"):
                    br.replace_with("\n")

                for line in container.get_text().splitlines():

                    line = line.strip()

                    if not line:
                        continue

                    # section headers and Genius' own page furniture
                    if line.startswith("["):
                        continue

                    if line.endswith("Lyrics"):
                        continue

                    lines.append(line)

            if not lines:
                return []

            return [
                (index * 4.0, line)
                for index, line in enumerate(lines)
            ]

        except Exception as e:

            print("Genius lyrics error:", e)

            return []


    # ── helpers ───────────────────────────────────────────────────

    def fetch(self, url, params=None, timeout=None):

        try:

            response = requests.get(
                url,
                params=params,
                headers=self.HEADERS,
                timeout=timeout or self.TIMEOUT,
            )

            if response.status_code != 200:
                return None

            return response.json()

        except Exception as e:

            print(f"  {url.split('/')[2]} unreachable: {type(e).__name__}")

            return None


    def romanize_all(self, lyrics):

        romanized = []

        for timestamp, text in lyrics:

            try:
                text = romanize(text)

            except Exception:
                pass

            romanized.append((timestamp, text))

        return romanized


    def plain_to_timed(self, plain):
        """Plain lyrics carry no timings, the spacing here is only a shape.

        Whoever asks for these gets told they are not synced, so nothing
        tries to follow along with them.
        """

        lines = [
            line.strip()
            for line in plain.splitlines()
            if line.strip()
        ]

        return [
            (index * 4.0, line)
            for index, line in enumerate(lines)
        ]


    def parse_lrc(self, lrc):

        result = []

        for line in lrc.splitlines():

            if not line.startswith("["):
                continue

            try:

                timestamp, text = line.split("]", 1)

                minutes, seconds = timestamp[1:].split(":")

                result.append(
                    (
                        int(minutes) * 60 + float(seconds),
                        text.strip(),
                    )
                )

            except Exception:
                # metadata tags like [ar:...] land here
                pass

        # a few files ship their lines out of order, and everything
        # downstream binary-searches these timestamps
        result.sort(key=lambda line: line[0])

        return result

import requests
from transliterate import romanize


class Lyrics:

    BASE_URL = "https://lrclib.net/api"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }


    def get(self, artist, title):
        """Fetch lyrics with multiple fallbacks.

        Order: lrclib exact → lrclib search → Genius scrape.
        All results are romanized (Hindi/Urdu → Latin script).
        """

        # 1. lrclib exact match
        result = self._try_exact(artist, title)

        if result:
            return self._romanize_all(result)

        # 2. lrclib fuzzy search
        result = self._try_search(artist, title)

        if result:
            return self._romanize_all(result)

        # 3. Genius scrape
        result = self._try_genius(artist, title)

        if result:
            return self._romanize_all(result)

        return []


    # ── romanization ─────────────────────────────────────────────

    def _romanize_all(self, lyrics):
        """Romanize every line of lyrics."""
        return [
            (ts, romanize(text))
            for ts, text in lyrics
        ]


    # ── lrclib providers ─────────────────────────────────────────

    def _try_exact(self, artist, title):

        try:

            response = requests.get(
                f"{self.BASE_URL}/get",
                params={
                    "artist_name": artist,
                    "track_name": title
                },
                timeout=15
            )

            if response.status_code != 200:
                return []

            return self._extract_lyrics(response.json())

        except Exception as e:
            print("Lyrics exact match error:", e)
            return []


    def _try_search(self, artist, title):

        try:

            query = f"{artist} {title}"

            response = requests.get(
                f"{self.BASE_URL}/search",
                params={"q": query},
                timeout=15
            )

            if response.status_code != 200:
                return []

            results = response.json()

            if not results:
                return []

            # Pick the first result that has synced lyrics
            for item in results:
                synced = item.get("syncedLyrics")
                if synced:
                    print(f"  Found via search: {item.get('artistName')} - {item.get('trackName')}")
                    return self.parse_lrc(synced)

            # If no synced, try first with plain lyrics
            for item in results:
                plain = item.get("plainLyrics")
                if plain:
                    print(f"  Found plain lyrics via search: {item.get('artistName')} - {item.get('trackName')}")
                    return self._plain_to_timed(plain)

            return []

        except Exception as e:
            print("Lyrics search error:", e)
            return []


    # ── Genius provider ──────────────────────────────────────────

    def _try_genius(self, artist, title):

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            print("beautifulsoup4 not installed, skipping Genius")
            return []

        try:

            query = f"{artist} {title}"

            # search Genius
            response = requests.get(
                "https://genius.com/api/search/multi",
                params={"q": query},
                headers=self.HEADERS,
                timeout=15
            )

            if response.status_code != 200:
                return []

            data = response.json()
            sections = data.get("response", {}).get("sections", [])

            song_url = None
            for section in sections:
                if section.get("type") == "song":
                    hits = section.get("hits", [])
                    if hits:
                        song_url = hits[0]["result"]["url"]
                        break

            if not song_url:
                return []

            print(f"  Found on Genius: {song_url}")

            # scrape lyrics page
            response = requests.get(
                song_url,
                headers=self.HEADERS,
                timeout=15
            )

            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "html.parser")

            containers = soup.find_all(
                "div",
                attrs={"data-lyrics-container": "true"}
            )

            if not containers:
                return []

            lines = []

            for container in containers:
                # turn <br> into newlines
                for br in container.find_all("br"):
                    br.replace_with("\n")

                text = container.get_text()

                for line in text.splitlines():
                    line = line.strip()

                    if not line:
                        continue

                    # skip section headers [Verse 1], [Chorus], etc.
                    if line.startswith("["):
                        continue

                    # skip Genius metadata junk
                    if "Contributors" in line and "Lyrics" in line:
                        continue
                    if line.endswith("Lyrics"):
                        continue

                    lines.append(line)

            if not lines:
                return []

            # distribute lines ~4 s apart so the
            # overlay cycles through them over time
            return [
                (i * 4.0, line)
                for i, line in enumerate(lines)
            ]

        except Exception as e:
            print("Genius lyrics error:", e)
            return []


    # ── helpers ───────────────────────────────────────────────────

    def _extract_lyrics(self, data):

        synced = data.get("syncedLyrics")

        if synced:
            return self.parse_lrc(synced)

        # Fallback to plain lyrics
        plain = data.get("plainLyrics")

        if plain:
            return self._plain_to_timed(plain)

        return []


    def _plain_to_timed(self, plain):
        """Convert plain lyrics to timed format.
        Lines are spaced ~4 s apart so the overlay can cycle."""

        lines = [
            line.strip()
            for line in plain.splitlines()
            if line.strip()
        ]

        if not lines:
            return []

        return [
            (i * 4.0, line)
            for i, line in enumerate(lines)
        ]


    def parse_lrc(self, lrc):

        result = []


        for line in lrc.splitlines():

            if not line.startswith("["):
                continue


            try:

                timestamp, text = line.split(
                    "]",
                    1
                )

                timestamp = timestamp[1:]

                minutes, seconds = timestamp.split(":")

                total = (
                    int(minutes) * 60
                    +
                    float(seconds)
                )

                result.append(
                    (
                        total,
                        text.strip()
                    )
                )


            except:
                pass


        return result

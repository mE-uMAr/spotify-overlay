import requests


class Lyrics:

    BASE_URL = "https://lrclib.net/api"


    def get(self, artist, title):

        # Try exact match first
        result = self._try_exact(artist, title)

        if result:
            return result

        # Fallback to search
        result = self._try_search(artist, title)

        if result:
            return result

        return []


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
        All lines get timestamp 0 so they show as static text."""

        lines = [
            line.strip()
            for line in plain.splitlines()
            if line.strip()
        ]

        if not lines:
            return []

        return [(0, line) for line in lines]


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

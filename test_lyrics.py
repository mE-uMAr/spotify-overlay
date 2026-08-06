from lyrics import Lyrics


lyrics = Lyrics()


data, synced = lyrics.get(
    "Jal",
    "Sajni",
    duration=None
)


print("synced:", synced, "| lines:", len(data))

for item in data[:10]:
    print(item)

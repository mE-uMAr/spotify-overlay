from lyrics import Lyrics


lyrics = Lyrics()


data = lyrics.get(
    "Jal",
    "Sajni"
)


for item in data[:10]:
    print(item)

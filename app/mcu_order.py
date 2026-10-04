"""Local viewing orders, checked 2026-10-04. No provider IO on page loads.

Release order: https://de.wikipedia.org/wiki/Marvel_Cinematic_Universe
Story order: Kino.de's official-timeline section, supplemented by Sony entries
as placed in Teufel's MCU list. Both distinguish film from series/specials.
https://www.kino.de/film/avengers-4-endgame-2019/news/marvel-filme-und-serien-in-chronologischer-reihenfolge-mcu-timeline/
https://blog.teufel.de/alle-marvel-filme-in-der-richtigen-reihenfolge-schauen/
Alternative universes are deliberately displayed in a separate group.
"""
RELEASE_TITLES = """Iron Man
The Incredible Hulk
Iron Man 2
Thor
Captain America: The First Avenger
The Avengers
Iron Man 3
Thor: The Dark World
Captain America: The Winter Soldier
Guardians of the Galaxy
Avengers: Age of Ultron
Ant-Man
Captain America: Civil War
Doctor Strange
Guardians of the Galaxy Vol. 2
Spider-Man: Homecoming
Thor: Ragnarok
Black Panther
Avengers: Infinity War
Ant-Man and the Wasp
Captain Marvel
Avengers: Endgame
Spider-Man: Far From Home
Black Widow
Shang-Chi and the Legend of the Ten Rings
Eternals
Spider-Man: No Way Home
Doctor Strange in the Multiverse of Madness
Thor: Love and Thunder
Black Panther: Wakanda Forever
Ant-Man and the Wasp: Quantumania
Guardians of the Galaxy Vol. 3
The Marvels
Deadpool & Wolverine
Captain America: Brave New World
Thunderbolts*
The Fantastic Four: First Steps
Spider-Man: Brand New Day""".splitlines()

STORY_TITLES = """Captain America: The First Avenger
Captain Marvel
Iron Man
Iron Man 2
The Incredible Hulk
Thor
The Avengers
Thor: The Dark World
Iron Man 3
Captain America: The Winter Soldier
Guardians of the Galaxy
Guardians of the Galaxy Vol. 2
Avengers: Age of Ultron
Ant-Man
Captain America: Civil War
Black Widow
Black Panther
Spider-Man: Homecoming
Doctor Strange
Thor: Ragnarok
Ant-Man and the Wasp
Avengers: Infinity War
Avengers: Endgame
Shang-Chi and the Legend of the Ten Rings
Spider-Man: Far From Home
Eternals
Spider-Man: No Way Home
Doctor Strange in the Multiverse of Madness
Black Panther: Wakanda Forever
Thor: Love and Thunder
Ant-Man and the Wasp: Quantumania
Guardians of the Galaxy Vol. 3
The Marvels
Captain America: Brave New World
Thunderbolts*
Spider-Man: Brand New Day""".splitlines()

RELEASE_RANK = {title: rank for rank, title in enumerate(RELEASE_TITLES, 1)}
STORY_RANK = {title: rank for rank, title in enumerate(STORY_TITLES, 1)}
ALTERNATE_UNIVERSES = {
    "The Fantastic Four: First Steps": "Alternatives Universum · an die 1960er angelehnt",
    "Deadpool & Wolverine": "Alternatives Universum und TVA · keine durchgehende MCU-Zeitlinie",
}


def entry_order(entry, mode):
    """Rank MCU films exactly; never assign another Marvel era to MCU time."""
    title, year = entry["title"], entry["year"]
    if mode == "release":
        rank = RELEASE_RANK.get(title) if entry["branch"] == "MCU" else None
        return (year, rank or 10000, title.casefold()), "", rank
    if not entry["released"]:
        return (3, year, title.casefold()), "Noch keine bestätigte Handlungseinordnung", None
    if entry["branch"] == "MCU" and title in STORY_RANK:
        return (0, STORY_RANK[title], title.casefold()), "MCU-Handlungschronologie", STORY_RANK[title]
    if entry["branch"] == "MCU" and title in ALTERNATE_UNIVERSES:
        return (1, RELEASE_RANK[title], title.casefold()), ALTERNATE_UNIVERSES[title], None
    return (2, year, title.casefold()), "Keine Zuordnung zur MCU-Filmtimeline", None


TIMELINE_GROUPS = {
    0: "MCU-Handlungschronologie",
    1: "Weitere MCU-Universen",
    2: "Weitere Marvel-Titel ohne MCU-Filmtimeline",
    3: "Angekündigte und unveröffentlichte Titel",
}

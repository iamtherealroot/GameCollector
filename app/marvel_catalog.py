"""Local Marvel film catalogue; no copies or release availability are invented.

Scope: feature/TV/animation films, published episode compilations, Marvel
imprints and separately labelled shorts/serials. Facts checked 2026-10-04:
https://en.wikipedia.org/wiki/List_of_films_based_on_Marvel_Comics
https://en.wikipedia.org/wiki/List_of_Marvel_Cinematic_Universe_films
https://www.sonypictures.com/movies/spidermanbrandnewday
"""
import json
from functools import lru_cache
from flask import render_template, request, url_for, session
from flask_login import login_required
from .mcu_order import entry_order, TIMELINE_GROUPS

# year | original title | own series | branch | optional German aliases
_DATA = """
1986|Howard the Duck|Howard the Duck|Kino|Howard – Ein tierischer Held
1998|Blade|Blade|Kino
2000|X-Men|X-Men|Kino|X-Men – Der Film
2002|Blade II|Blade|Kino|Blade 2
2002|Spider-Man|Spider-Man|Kino
2003|Daredevil|Daredevil|Kino
2003|X2|X-Men|Kino|X-Men 2
2003|Hulk|Hulk|Kino
2004|The Punisher|The Punisher|Kino
2004|Spider-Man 2|Spider-Man|Kino
2004|Blade: Trinity|Blade|Kino|Blade Trinity
2005|Elektra|Daredevil|Kino
2005|Fantastic Four|Fantastic Four|Kino
2006|X-Men: The Last Stand|X-Men|Kino|X-Men: Der letzte Widerstand
2007|Ghost Rider|Ghost Rider|Kino
2007|Spider-Man 3|Spider-Man|Kino
2007|Fantastic Four: Rise of the Silver Surfer|Fantastic Four|Kino
2008|Iron Man|Iron Man|MCU
2008|The Incredible Hulk|Hulk|MCU|Der unglaubliche Hulk
2008|Punisher: War Zone|The Punisher|Kino
2009|X-Men Origins: Wolverine|Wolverine|Kino
2010|Iron Man 2|Iron Man|MCU
2011|Thor|Thor|MCU
2011|X-Men: First Class|X-Men|Kino|X-Men: Erste Entscheidung
2011|Captain America: The First Avenger|Captain America|MCU
2011|Ghost Rider: Spirit of Vengeance|Ghost Rider|Kino
2012|The Avengers|Avengers|MCU|Marvel's The Avengers
2012|The Amazing Spider-Man|Spider-Man|Kino
2013|Iron Man 3|Iron Man|MCU
2013|The Wolverine|Wolverine|Kino|Wolverine: Weg des Kriegers
2013|Thor: The Dark World|Thor|MCU|Thor: The Dark Kingdom
2014|Captain America: The Winter Soldier|Captain America|MCU|The Return of the First Avenger
2014|The Amazing Spider-Man 2|Spider-Man|Kino|The Amazing Spider-Man 2: Rise of Electro
2014|X-Men: Days of Future Past|X-Men|Kino|X-Men: Zukunft ist Vergangenheit
2014|Guardians of the Galaxy|Guardians of the Galaxy|MCU
2015|Avengers: Age of Ultron|Avengers|MCU
2015|Ant-Man|Ant-Man|MCU
2015|Fantastic Four|Fantastic Four|Kino
2016|Deadpool|Deadpool|Kino
2016|Captain America: Civil War|Captain America|MCU|The First Avenger: Civil War
2016|X-Men: Apocalypse|X-Men|Kino
2016|Doctor Strange|Doctor Strange|MCU
2017|Logan|Wolverine|Kino|Logan: The Wolverine
2017|Guardians of the Galaxy Vol. 2|Guardians of the Galaxy|MCU
2017|Spider-Man: Homecoming|Spider-Man|MCU
2017|Thor: Ragnarok|Thor|MCU|Thor: Tag der Entscheidung
2018|Black Panther|Black Panther|MCU
2018|Avengers: Infinity War|Avengers|MCU
2018|Deadpool 2|Deadpool|Kino
2018|Ant-Man and the Wasp|Ant-Man|MCU
2018|Venom|Venom|Kino
2019|Captain Marvel|Captain Marvel|MCU
2019|Avengers: Endgame|Avengers|MCU
2019|Dark Phoenix|X-Men|Kino|X-Men: Dark Phoenix
2019|Spider-Man: Far From Home|Spider-Man|MCU
2020|The New Mutants|X-Men|Kino
2021|Black Widow|Black Widow|MCU
2021|Shang-Chi and the Legend of the Ten Rings|Shang-Chi|MCU
2021|Venom: Let There Be Carnage|Venom|Kino
2021|Eternals|Eternals|MCU
2021|Spider-Man: No Way Home|Spider-Man|MCU
2022|Morbius|Morbius|Kino
2022|Doctor Strange in the Multiverse of Madness|Doctor Strange|MCU
2022|Thor: Love and Thunder|Thor|MCU
2022|Black Panther: Wakanda Forever|Black Panther|MCU
2023|Ant-Man and the Wasp: Quantumania|Ant-Man|MCU
2023|Guardians of the Galaxy Vol. 3|Guardians of the Galaxy|MCU
2023|The Marvels|Captain Marvel|MCU
2024|Madame Web|Madame Web|Kino
2024|Deadpool & Wolverine|Deadpool|MCU
2024|Venom: The Last Dance|Venom|Kino
2024|Kraven the Hunter|Kraven|Kino
2025|Captain America: Brave New World|Captain America|MCU
2025|Thunderbolts*|Thunderbolts|MCU|Thunderbolts
2025|The Fantastic Four: First Steps|Fantastic Four|MCU
2026|Spider-Man: Brand New Day|Spider-Man|MCU
1978|Dr. Strange|Doctor Strange|TV
1979|Captain America|Captain America|TV
1979|Captain America II: Death Too Soon|Captain America|TV
1988|The Incredible Hulk Returns|Hulk|TV|Die Rückkehr des unheimlichen Hulk
1989|The Trial of the Incredible Hulk|Hulk|TV|Der unheimliche Hulk vor Gericht
1989|The Punisher|The Punisher|TV
1990|The Death of the Incredible Hulk|Hulk|TV|Der Tod des unheimlichen Hulk
1990|Captain America|Captain America|TV
1994|The Fantastic Four|Fantastic Four|Unveröffentlicht
1996|Generation X|X-Men|TV
1998|Nick Fury: Agent of S.H.I.E.L.D.|Nick Fury|TV|Nick Fury: Einsatz in Berlin
2005|Man-Thing|Man-Thing|TV
1977|Spider-Man|Spider-Man|TV
1977|The Incredible Hulk|Hulk|TV
1977|Return of the Incredible Hulk|Hulk|TV
1978|The Incredible Hulk: Married|Hulk|TV|The Bride of the Incredible Hulk
1978|Spider-Man Strikes Back|Spider-Man|TV
1981|Spider-Man: The Dragon's Challenge|Spider-Man|TV
2006|Blade: House of Chthon|Blade|TV
2017|Inhumans: The First Chapter|Inhumans|TV
2022|Werewolf by Night|Werewolf by Night|TV
2022|The Guardians of the Galaxy Holiday Special|Guardians of the Galaxy|TV
2014|Big Hero 6|Baymax|Animation|Baymax – Riesiges Robowabohu
2018|Spider-Man: Into the Spider-Verse|Spider-Man|Animation|Spider-Man: A New Universe
2023|Spider-Man: Across the Spider-Verse|Spider-Man|Animation
1980|Dracula: Sovereign of the Damned|Dracula|Animation
1981|Kyoufu Densetsu Kaiki! Frankenstein|Frankenstein|Animation
2006|Ultimate Avengers|Avengers|Animation
2006|Ultimate Avengers 2|Avengers|Animation
2007|The Invincible Iron Man|Iron Man|Animation
2007|Doctor Strange: The Sorcerer Supreme|Doctor Strange|Animation
2008|Next Avengers: Heroes of Tomorrow|Avengers|Animation
2009|Hulk Versus|Hulk|Animation|Hulk vs.
2010|Planet Hulk|Hulk|Animation
2011|Thor: Tales of Asgard|Thor|Animation
2013|Iron Man: Rise of Technovore|Iron Man|Animation
2013|Iron Man & Hulk: Heroes United|Iron Man|Animation
2014|Avengers Confidential: Black Widow & Punisher|Avengers|Animation
2014|Iron Man & Captain America: Heroes United|Iron Man|Animation
2015|Marvel Super Hero Adventures: Frost Fight!|Marvel Super Hero Adventures|Animation
2016|Hulk: Where Monsters Dwell|Hulk|Animation
2018|Marvel Rising: Secret Warriors|Marvel Rising|Animation
2017|Baymax Returns|Baymax|Animation
1997|Men in Black|Men in Black|Malibu
2002|Men in Black II|Men in Black|Malibu|Men in Black 2
2012|Men in Black 3|Men in Black|Malibu
2019|Men in Black: International|Men in Black|Malibu
1997|Nightman: World Premiere|Night Man|Malibu
2010|Kick-Ass|Kick-Ass|Icon
2013|Kick-Ass 2|Kick-Ass|Icon
2014|Kingsman: The Secret Service|Kingsman|Icon
2017|Kingsman: The Golden Circle|Kingsman|Icon
2021|The King's Man|Kingsman|Icon|The King's Man: The Beginning
2024|Argylle|Kingsman|Icon
1944|Captain America|Captain America|Serial
1978|Spider-Man|Spider-Man|Kurzfilm
2011|The Consultant|Marvel One-Shots|Kurzfilm
2011|A Funny Thing Happened on the Way to Thor's Hammer|Marvel One-Shots|Kurzfilm
2012|Item 47|Marvel One-Shots|Kurzfilm
2013|Agent Carter|Marvel One-Shots|Kurzfilm
2014|All Hail the King|Marvel One-Shots|Kurzfilm
2016|Team Thor|Thor|Kurzfilm
2017|Team Thor: Part 2|Thor|Kurzfilm
2017|No Good Deed|Deadpool|Kurzfilm
2018|Team Darryl|Thor|Kurzfilm
2019|Peter's To-Do List|Spider-Man|Kurzfilm
2021|Deadpool and Korg React|Deadpool|Kurzfilm
1993|Hardcase|Hardcase|Kurzfilm
1993|Firearm|Firearm|Kurzfilm
2010|Marvel Super Heroes 4D (London)|Marvel Super Heroes 4D|Kurzfilm
2012|Marvel Super Heroes 4D (New York)|Marvel Super Heroes 4D|Kurzfilm
2013|Marvel Super Heroes 4D (Las Vegas)|Marvel Super Heroes 4D|Kurzfilm
2013|Marvel Super Heroes 4D (Bali)|Marvel Super Heroes 4D|Kurzfilm
2017|Marvel Super Heroes 4D (Sentosa)|Marvel Super Heroes 4D|Kurzfilm
2019|Marvel Rising: Chasing Ghosts|Marvel Rising|Kurzfilm
2019|Spider-Ham: Caught in a Ham|Spider-Man|Kurzfilm
2019|Marvel Rising: Heart of Iron|Marvel Rising|Kurzfilm
2019|Marvel Rising: Battle of the Bands|Marvel Rising|Kurzfilm
2019|Marvel Rising: Operation Shuri|Marvel Rising|Kurzfilm
2019|Marvel Rising: Playing with Fire|Marvel Rising|Kurzfilm
2023|The Spider Within: A Spider-Verse Story|Spider-Man|Kurzfilm
2013|Lego Marvel Super Heroes: Maximum Overload|LEGO Marvel|Kurzfilm
2015|Lego Marvel Super Heroes: Avengers Reassembled|LEGO Marvel|Kurzfilm
2017|Lego Marvel Super Heroes – Guardians of the Galaxy: The Thanos Threat|LEGO Marvel|Kurzfilm
2018|Lego Marvel Super Heroes – Black Panther: Trouble in Wakanda|LEGO Marvel|Kurzfilm
2019|Lego Marvel Spider-Man: Vexed by Venom|LEGO Marvel|Kurzfilm
2021|Lego Marvel Avengers: Loki in Training|LEGO Marvel|Kurzfilm
2022|Lego Marvel Avengers: Time Twisted|LEGO Marvel|Kurzfilm
2023|Lego Marvel Avengers: Code Red|LEGO Marvel|Kurzfilm
2024|Lego Marvel Avengers: Mission Demolition|LEGO Marvel|Kurzfilm
2017|#TBT to That Time Archer Met Kingsman|Kingsman|Kurzfilm
2026|Avengers: Doomsday|Avengers|Angekündigt
2027|Avengers: Secret Wars|Avengers|Angekündigt
2027|Spider-Man: Beyond the Spider-Verse|Spider-Man|Angekündigt
"""

CATALOG = []
for line in _DATA.strip().splitlines():
    year, title, series, branch, *aliases = line.split("|")
    CATALOG.append(dict(year=int(year), title=title, series=series, branch=branch, aliases=aliases,
                        key=f"{year}:{title}:{branch}", released=branch not in {"Angekündigt", "Unveröffentlicht"}))


@lru_cache(maxsize=2)
def _title_index(normalize):
    index = {}
    for entry in CATALOG:
        for title in {entry["title"], *entry["aliases"]}:
            index.setdefault(normalize(title), {})[entry["key"]] = entry
    return index


def match_movie(row, metadata, normalize):
    index = _title_index(normalize)
    candidates = {}
    for title in (row.title, metadata.get("original_title") or ""):
        candidates.update(index.get(normalize(title), {}))
    matches = [entry for entry in candidates.values() if not row.release_year or row.release_year == entry["year"]]
    return matches[0] if len(matches) == 1 else None


def seed_catalog(db, ns, upsert_series):
    Work = ns["BiboWork"]
    existing = {work.canonical_key: work for work in Work.query.filter_by(media_kind="movies").all()}
    seeded = []
    for entry in CATALOG:
        key = ns["_bibo_identity_key"]("movies", "marvel:" + entry["key"])
        work = existing.get(key)
        if not work:
            work = Work(canonical_key=key, media_kind="movies", title=entry["title"], sort_title=entry["title"].casefold(),
                        series_name=entry["series"], logical_unit_key="marvel:"+entry["key"], availability_de="unknown",
                        metadata_json=json.dumps({"marvel_catalog": entry}, ensure_ascii=False))
            db.session.add(work)
        seeded.append((entry, work))
    db.session.flush()
    for entry, work in seeded:
        upsert_series(work, "movies", "Marvel", entry["year"])
        upsert_series(work, "movies", entry["series"], entry["year"])
        if entry["branch"] == "MCU":
            upsert_series(work, "movies", "Marvel Cinematic Universe", entry["year"])
        if entry["title"] == "Deadpool & Wolverine":
            upsert_series(work, "movies", "Wolverine", entry["year"])
        if entry["series"] == "Wolverine" or entry["series"] == "Deadpool":
            upsert_series(work, "movies", "X-Men", entry["year"])


def setup_marvel_catalog(app, db, ns):
    @app.get("/collector/movies/marvel")
    @login_required
    def marvel_movies():
        ns["refresh_bibo_registry"](only_if_changed=True)
        series = request.args.get("series", "Marvel")
        selected_branch = request.args.get("branch", "films")
        query = request.args.get("q", "").strip()
        selected_order = request.args.get("order", session.get("marvel_catalog_order", "release"))
        if selected_order not in {"release", "timeline"}:
            selected_order = "release"
        if session.get("marvel_catalog_order") != selected_order:
            session["marvel_catalog_order"] = selected_order
        owner = ns["active_collection_user_id"]()
        copies = ns["BiboCopy"].query.join(ns["BiboEdition"]).join(ns["BiboWork"]).filter(ns["BiboCopy"].active.is_(True), ns["BiboCopy"].owner_id == owner, ns["BiboWork"].media_kind == "movies").all()
        owned = {}
        for copy in copies:
            owned.setdefault(copy.edition.work.canonical_key, []).append(copy)
        works = {work.canonical_key: work for work in ns["BiboWork"].query.filter_by(media_kind="movies").all()}
        rows = []
        for entry in sorted(CATALOG, key=lambda e:entry_order(e, selected_order)[0]):
            families = {"Marvel", entry["series"]}
            if entry["branch"] == "MCU": families.add("Marvel Cinematic Universe")
            if entry["series"] in {"Wolverine", "Deadpool"}: families.add("X-Men")
            if entry["title"] == "Deadpool & Wolverine": families.add("Wolverine")
            if series not in families:
                continue
            if selected_branch == "films" and entry["branch"] in {"Kurzfilm", "Serial"}:
                continue
            if selected_branch not in {"all", "films"} and entry["branch"] != selected_branch:
                continue
            if query and ns["_match_key"](query) not in ns["_match_key"](" ".join([entry["title"],*entry["aliases"]])):
                continue
            key = ns["_bibo_identity_key"]("movies", "marvel:" + entry["key"])
            work = works.get(key)
            copies_for_work = owned.get(key, [])
            physical = [c for c in copies_for_work if c.status == "owned" and c.ownership_format == "physical"]
            order_key, order_label, order_position = entry_order(entry, selected_order)
            rows.append({"entry":entry,"work":work,"copies":copies_for_work,"owned":bool(physical),
                         "order_label":order_label,"order_position":order_position,
                         "order_group":order_key[0] if selected_order == "timeline" else None,
                         "families":sorted(families),"cover":work.cover_url if work else None,
                         "detail_url":url_for("bibo_work_detail",work_id=work.id) if work and copies_for_work else None})
        total_owned=sum(r["owned"] for r in rows)
        rows,pagination=ns["collection_page"](rows)
        return render_template("marvel_movies.html",rows=rows,pagination=pagination,total_owned=total_owned,
                               selected_series=series, selected_branch=selected_branch,query_text=query,
                               selected_order=selected_order,timeline_groups=TIMELINE_GROUPS,
                               series_names=sorted({"Marvel","Marvel Cinematic Universe",*(e["series"] for e in CATALOG)}))

    def overview_group(owner):
        rows=ns["CollectorItem"].query.filter_by(user_id=owner,category="movies").all()
        found=[(row,match_movie(row,ns["collector_metadata"](row),ns["_match_key"])) for row in rows]
        found=[(row,entry) for row,entry in found if entry
               and ns["collector_metadata"](row).get("status","owned")=="owned"
               and ns["collector_metadata"](row).get("ownership_format", "digital" if str(row.media_type or "").casefold()=="digital" else "physical")=="physical"]
        if not found:return None
        return {"name":"Marvel","type":"movies","label":"Filmreihen · übergreifend","icon":"🎬",
                "owned":len({entry["key"] for row,entry in found}),"total":None,"pct":None,"missing":None,
                "value":sum(ns["collector_effective_value"](row) or 0 for row,entry in found),"cover":next((row.cover_url for row,entry in found if row.cover_url),None),
                "copy_count":len(found),"valued_count":sum(bool(ns["collector_effective_value"](row)) for row,entry in found),
                "items":[{"title":row.title,"url":url_for("collector_item_detail",item_id=row.id)} for row,entry in found],
                "detail_url":url_for("marvel_movies"),"catalog_umbrella":True}
    return overview_group

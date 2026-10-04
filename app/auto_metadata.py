"""One-shot enrichment after saving; network work happens after the page opens."""
import json
from types import SimpleNamespace
from flask import has_request_context, session, jsonify, url_for, request
from flask_login import current_user, login_required
from sqlalchemy import event
from sqlalchemy.orm import Session


def setup_auto_metadata(app, db, ns):
    models = {"media": ns["CollectorItem"], "game": ns["CollectionItem"],
              "hardware": ns["HardwareItem"], "accessory": ns["AccessoryItem"]}
    pending_key = "auto_metadata_pending"
    descriptive = {"subtitle", "author", "publisher", "language", "page_count", "publish_date",
                   "artist", "label", "catalog_number", "country", "track_count", "disc_count",
                   "tmdb_id", "tmdb_media_type", "original_title", "overview", "genres",
                   "runtime_minutes", "director", "creators", "original_language", "season_count",
                   "episode_count", "status", "networks", "tmdb_updated_at", "tmdb_collection",
                   "musicbrainz_release_id", "set_id", "illustrator", "provider"}

    @event.listens_for(Session, "after_flush")
    def remember_new(db_session, _context):
        if not has_request_context() or not current_user.is_authenticated or "undo" in (request.endpoint or ""):
            return
        jobs = db_session.info.setdefault(pending_key, [])
        for row in db_session.new:
            for kind, model in models.items():
                if isinstance(row, model) and row.user_id == ns["active_collection_user_id"]():
                    job = {"kind": kind, "id": row.id, "owner": row.user_id, "actor": current_user.id}
                    if job not in jobs:
                        jobs.append(job)

    @event.listens_for(Session, "after_commit")
    def publish_jobs(db_session):
        jobs = db_session.info.pop(pending_key, [])
        if jobs and has_request_context():
            session[pending_key] = (session.get(pending_key, []) + jobs)[-30:]

    @event.listens_for(Session, "after_rollback")
    def discard_jobs(db_session):
        db_session.info.pop(pending_key, None)

    @app.context_processor
    def pending_jobs():
        if not current_user.is_authenticated or not ns["collection_capability"]("edit_items"):
            return {"auto_metadata_jobs": []}
        owner = ns["active_collection_user_id"]()
        return {"auto_metadata_jobs": [url_for("auto_metadata", kind=j["kind"], item_id=j["id"])
                for j in session.get(pending_key, []) if j["owner"] == owner and j["actor"] == current_user.id]}

    def empty(value):
        return value is None or value == "" or value == []

    def select(rows, title, barcode=None, year=None, card=None):
        matches = []
        for hit in rows or []:
            if not isinstance(hit, dict):
                continue
            identity = bool(barcode and ns["clean_barcode"](hit.get("barcode") or hit.get("isbn")) == ns["clean_barcode"](barcode))
            identity = identity or ns["_match_key"](hit.get("title") or hit.get("name") or "") == ns["_match_key"](title)
            if not identity or (year and hit.get("year") and str(year) != str(hit["year"])):
                continue
            if card:
                if card.external_id and str(hit.get("id")) != str(card.external_id):
                    continue
                if card.card_number and str(hit.get("number") or "") != str(card.card_number):
                    continue
                if card.card_set and ns["_match_key"](hit.get("set_name") or "") != ns["_match_key"](card.card_set):
                    continue
                if card.card_language and hit.get("language") and str(hit["language"]).lower() != str(card.card_language).lower():
                    continue
            matches.append(hit)
        # Never guess between different editions, sets or homonymous titles.
        return matches[0] if len(matches) == 1 else None

    def product(title, barcode=None):
        hits = ns["lookup_barcode_external"](barcode) if barcode else ns["upcitemdb_title_search"](title, limit=8)
        # Different providers may resolve the same physical product.
        if barcode:
            hits = [h for h in hits or [] if ns["clean_barcode"](h.get("barcode")) == ns["clean_barcode"](barcode)]
            return hits[0] if hits else None
        return select(hits, title)

    def enrich_media(row):
        fields = ("title", "category", "barcode", "release_year", "cover_url", "external_source", "external_id", "metadata_json",
                  "tcg_game", "card_set", "card_number", "card_language", "card_rarity")
        candidate = SimpleNamespace(**{key: getattr(row, key) for key in fields})
        meta = ns["collector_metadata"](candidate)
        # Reuse only descriptive metadata from an unambiguous entry of this collection.
        query = models["media"].query.filter_by(user_id=row.user_id, category=row.category).filter(models["media"].id != row.id)
        query = query.filter_by(barcode=row.barcode) if row.barcode else query.filter_by(title=row.title)
        local = query.limit(2).all()
        if len(local) == 1:
            previous = local[0]
            for key, value in ns["collector_metadata"](previous).items():
                if key in descriptive and empty(meta.get(key)):
                    meta[key] = value
            for key in ("cover_url", "release_year"):
                if empty(getattr(candidate, key)):
                    setattr(candidate, key, getattr(previous, key))
        candidate.metadata_json = json.dumps(meta, ensure_ascii=False)
        if row.category in {"movies", "tv"}:
            if not meta.get("tmdb_id"):
                media = "movie" if row.category == "movies" else "tv"
                data = ns["tmdb_json"]("search/" + media, {"query": row.title, "language": "de-DE", "include_adult": "false"})
                hits = [{**h, "title": h.get("title") or h.get("name"), "year": str(h.get("release_date") or h.get("first_air_date") or "")[:4]} for h in (data or {}).get("results", [])]
                hit = select(hits, row.title, year=row.release_year)
                if hit:
                    meta["tmdb_id"] = str(hit["id"])
                    candidate.metadata_json = json.dumps(meta, ensure_ascii=False)
            if meta.get("tmdb_id"):
                ns["tmdb_apply_metadata"](candidate)
        elif row.category == "books":
            isbn = ns["normalize_isbn"](row.barcode)
            hits = ns["openlibrary_search_books"](isbn=isbn, limit=5) if isbn else ns["openlibrary_search_books"](query=row.title, limit=5)
            hit = select(hits, row.title, barcode=isbn, year=row.release_year)
            if hit:
                meta.update({k: hit.get(k) for k in ("subtitle", "author", "publisher", "language", "page_count", "publish_date")})
                candidate.cover_url = hit.get("cover_url")
                candidate.release_year = hit.get("year")
                candidate.external_source, candidate.external_id = "OpenLibrary", hit.get("id")
                candidate.metadata_json = json.dumps(meta, ensure_ascii=False)
        elif row.category == "music":
            hit = select(ns["musicbrainz_search_releases"](row.barcode or row.title, limit=5), row.title, barcode=row.barcode, year=row.release_year)
            if hit:
                meta.update({k: hit.get(k) for k in ("artist", "label", "catalog_number", "country", "track_count", "disc_count")})
                meta["musicbrainz_release_id"] = hit.get("id")
                candidate.cover_url, candidate.release_year = hit.get("cover_url"), hit.get("year")
                candidate.external_source, candidate.external_id = "MusicBrainz", hit.get("id")
                candidate.metadata_json = json.dumps(meta, ensure_ascii=False)
        elif row.category == "cards":
            tcg = (row.tcg_game or "").casefold()
            providers = []
            if "pok" in tcg or not tcg:
                providers.append(ns["tcgdex_search"])
            if "magic" in tcg or not tcg:
                providers.append(ns["scryfall_search"])
            if "yu" in tcg or not tcg:
                providers.append(ns["ygopro_search"])
            hits = [hit for provider in providers for hit in provider(row.title) or []]
            hit = select(hits, row.title, card=row)
            if hit:
                candidate.cover_url = hit.get("image")
                candidate.card_set, candidate.card_number, candidate.card_rarity = hit.get("set_name"), hit.get("number"), hit.get("rarity")
                candidate.tcg_game, candidate.card_language = hit.get("tcg"), hit.get("language")
                meta.update({"illustrator": hit.get("illustrator") or hit.get("artist"), "set_id": hit.get("set_code"), "provider": hit.get("provider")})
                candidate.metadata_json = json.dumps(meta, ensure_ascii=False)
                candidate.external_source, candidate.external_id = hit.get("provider"), hit.get("id")
        else:
            hit = product(row.title, row.barcode)
            if hit:
                candidate.cover_url = hit.get("cover_url")
                meta["publisher"] = hit.get("publisher")
                candidate.metadata_json = json.dumps(meta, ensure_ascii=False)
                candidate.external_source, candidate.external_id = hit.get("source"), hit.get("source_id")
        additions = {key: value for key, value in ns["collector_metadata"](candidate).items() if key in descriptive and not empty(value)}
        values = {key: getattr(candidate, key) for key in fields if key not in {"title", "category", "barcode", "metadata_json"}}
        return values, additions

    @app.post("/metadata/auto/<kind>/<int:item_id>")
    @login_required
    def auto_metadata(kind, item_id):
        if not ns["collection_capability"]("edit_items"):
            return jsonify(status="forbidden"), 403
        owner = ns["active_collection_user_id"]()
        queue = session.get(pending_key, [])
        job = next((j for j in queue if j["kind"] == kind and j["id"] == item_id and j["owner"] == owner and j["actor"] == current_user.id), None)
        if not job or kind not in models:
            return jsonify(status="skipped", changed=False)
        session[pending_key] = [j for j in queue if j != job]
        row = models[kind].query.filter_by(id=item_id, user_id=owner).first()
        if not row:
            return jsonify(status="skipped", changed=False)
        try:
            additions = {}
            if kind == "media":
                target = row
                values, additions = enrich_media(row)
            elif kind == "game":
                target = row.game
                hits, _status = ns["_metadata_candidates"](target.title, target.console.name, limit=12)
                hits = [h for h in hits if h.get("platform_match") is True or ns["canonical_console_name"](h.get("platform") or "") == ns["canonical_console_name"](target.console.name)]
                hit = select(hits, target.title, barcode=target.barcode, year=target.release_year)
                if hit and hit.get("source") == "RAWG":
                    hit = ns["_provider_candidate"]("RAWG", hit.get("source_id")) or hit
                values = {key: (hit or {}).get("year" if key == "release_year" else key) for key in ("cover_url", "publisher", "developer", "genre", "release_year")}
            else:
                target = row.model if kind == "hardware" else row
                hit = product(target.name, getattr(target, "barcode", None)) or {}
                values = {"reference_image": hit.get("cover_url")}
                if kind == "accessory":
                    values["manufacturer"] = hit.get("publisher")
            target_model, target_id = type(target), target.id
            # Finish provider IO before reloading and merging. Existing user values win.
            db.session.rollback()
            target = db.session.get(target_model, target_id, populate_existing=True)
            if target is None:
                return jsonify(status="skipped", changed=False)
            changed = False
            for key, value in values.items():
                if hasattr(target, key) and empty(getattr(target, key)) and not empty(value):
                    if key == "release_year":
                        if not str(value).isdigit():
                            continue
                        value = int(value)
                    setattr(target, key, value)
                    changed = True
            if kind == "media":
                meta = ns["collector_metadata"](target)
                for key, value in additions.items():
                    if empty(meta.get(key)):
                        meta[key] = value
                        changed = True
                if changed:
                    target.metadata_json = json.dumps(meta, ensure_ascii=False)
            db.session.commit()
            return jsonify(status="enriched" if changed else "not_found", changed=changed)
        except Exception:
            db.session.rollback()
            app.logger.exception("Automatic metadata failed for %s/%s", kind, item_id)
            return jsonify(status="unavailable", changed=False)

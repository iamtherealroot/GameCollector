import csv
import base64
import hashlib
import io
import os
import json
from urllib.parse import quote, urlencode, urlsplit, urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
import unicodedata
import html as html_lib
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session, send_file, Response, current_app, has_request_context
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import inspect, text
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.attributes import set_committed_value
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet, InvalidToken
from PIL import Image, ImageOps, UnidentifiedImageError
from difflib import SequenceMatcher
from functools import wraps
import re
import subprocess
import tempfile
import zipfile
import threading
import time
import statistics
import secrets
import socket
import ipaddress
from pathlib import Path
from html.parser import HTMLParser
from itsdangerous import BadSignature, URLSafeSerializer

APP_VERSION = "4.7.1"
APP_NAME = "Bibo"
DISPLAY_TIMEZONE_NAME = os.environ.get("TZ", "Europe/Berlin")
try:
    DISPLAY_TIMEZONE = ZoneInfo(DISPLAY_TIMEZONE_NAME)
except Exception:
    DISPLAY_TIMEZONE_NAME = "Europe/Berlin"
    DISPLAY_TIMEZONE = ZoneInfo(DISPLAY_TIMEZONE_NAME)


def utc_now():
    """UTC timestamp for existing TIMESTAMP columns (stored without an offset)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def local_datetime(value):
    """Interpret database timestamps as UTC and convert them DST-safely."""
    if value is None:
        return None
    # Dates (for example purchase dates) have no timezone and must stay dates.
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(DISPLAY_TIMEZONE)


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///gamecollector.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 24 * 1024 * 1024

# v2.0.2: Keep authenticated users signed in across browser and container restarts.
SESSION_DAYS = max(1, int(os.environ.get("SESSION_DAYS", "30")))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes", "on"}
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),
    SESSION_REFRESH_EACH_REQUEST=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    REMEMBER_COOKIE_DURATION=timedelta(days=SESSION_DAYS),
    REMEMBER_COOKIE_REFRESH_EACH_REQUEST=True,
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE="Lax",
    REMEMBER_COOKIE_SECURE=COOKIE_SECURE,
)


@app.template_filter("localdt")
def format_local_datetime(value, fmt="%d.%m.%Y %H:%M"):
    converted = local_datetime(value)
    return converted.strftime(fmt) if converted else "–"

# v0.7.9: Optional database values must never render as the literal string "None".
app.jinja_env.finalize = lambda value: "" if value is None else value

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


DEFAULT_CONSOLES = [
    ("Nintendo Entertainment System (NES)", "Nintendo"),
    ("Super Nintendo (SNES)", "Nintendo"),
    ("Nintendo 64", "Nintendo"),
    ("Nintendo GameCube", "Nintendo"),
    ("Wii", "Nintendo"),
    ("Wii U", "Nintendo"),
    ("Nintendo Switch", "Nintendo"),
    ("Nintendo Switch 2", "Nintendo"),
    ("Game Boy", "Nintendo"),
    ("Game Boy Color", "Nintendo"),
    ("Game Boy Advance", "Nintendo"),
    ("Nintendo DS", "Nintendo"),
    ("Nintendo 3DS", "Nintendo"),
    ("PlayStation", "Sony"),
    ("PlayStation 2", "Sony"),
    ("PlayStation 3", "Sony"),
    ("PlayStation 4", "Sony"),
    ("PlayStation 5", "Sony"),
    ("PSP", "Sony"),
    ("PS Vita", "Sony"),
    ("Xbox", "Microsoft"),
    ("Xbox 360", "Microsoft"),
    ("Xbox One", "Microsoft"),
    ("Xbox Series X|S", "Microsoft"),
    ("Master System", "Sega"),
    ("Mega Drive / Genesis", "Sega"),
    ("Game Gear", "Sega"),
    ("Saturn", "Sega"),
    ("Dreamcast", "Sega"),
    ("Atari 2600", "Atari"),
    ("Atari 7800", "Atari"),
    ("Atari Jaguar", "Atari"),
    ("Neo Geo", "SNK"),
    ("PC", "PC"),
]


# Canonical platform aliases. Provider/import names are normalized before a console
# is created so equivalent platforms do not split the catalog again.
CONSOLE_ALIASES = {
    "sony playstation": "PlayStation",
    "playstation 1": "PlayStation",
    "ps1": "PlayStation",
    "sony playstation 2": "PlayStation 2",
    "ps2": "PlayStation 2",
    "sony playstation 3": "PlayStation 3",
    "ps3": "PlayStation 3",
    "sony playstation 4": "PlayStation 4",
    "ps4": "PlayStation 4",
    "sony playstation 5": "PlayStation 5",
    "ps5": "PlayStation 5",
    "playstation portable": "PSP",
    "sony psp": "PSP",
    "playstation vita": "PS Vita",
    "sony ps vita": "PS Vita",
    "nintendo wii": "Wii",
    "n64": "Nintendo 64",
    "nintendo n64": "Nintendo 64",
    "gamecube": "Nintendo GameCube",
    "nintendo game cube": "Nintendo GameCube",
    "nes": "Nintendo Entertainment System (NES)",
    "nintendo nes": "Nintendo Entertainment System (NES)",
    "nintendo entertainment system": "Nintendo Entertainment System (NES)",
    "snes": "Super Nintendo (SNES)",
    "super nintendo": "Super Nintendo (SNES)",
    "super nintendo entertainment system": "Super Nintendo (SNES)",
    "nintendo super nintendo entertainment system": "Super Nintendo (SNES)",
    "nintendo super nintendo": "Super Nintendo (SNES)",
    "sega master system": "Master System",
    "sega mega drive": "Mega Drive / Genesis",
    "mega drive": "Mega Drive / Genesis",
    "genesis": "Mega Drive / Genesis",
    "sega genesis": "Mega Drive / Genesis",
    "sega game gear": "Game Gear",
    "sega saturn": "Saturn",
    "sega dreamcast": "Dreamcast",
    "microsoft xbox": "Xbox",
    "original xbox": "Xbox",
    "xbox original": "Xbox",
    "xbox old gen": "Xbox",
    "microsoft xbox 360": "Xbox 360",
    "microsoft xbox one": "Xbox One",
    "microsoft xbox series x/s": "Xbox Series X|S",
    "microsoft xbox series x|s": "Xbox Series X|S",
    "microsoft xbox series x": "Xbox Series X|S",
    "microsoft xbox series s": "Xbox Series X|S",
    "xbox series x/s": "Xbox Series X|S",
    "xbox series x|s": "Xbox Series X|S",
    "xbox series x": "Xbox Series X|S",
    "xbox series s": "Xbox Series X|S",
}


def canonical_console_name(name):
    cleaned = re.sub(r"\s+", " ", str(name or "").strip())
    if not cleaned:
        return "Unbekannte Plattform"
    # Region belongs to the game/model, never to the platform master.  Import
    # providers commonly emit labels such as "PAL Xbox 360" or "Wii (PAL)".
    region = r"(?:PAL(?:[- ]?(?:DE|EU))?|NTSC(?:-U|-J)?|EUR|EUROPE|EU|GERMANY|DEUTSCHLAND)"
    cleaned = re.sub(rf"^{region}[\s:_-]+", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(rf"[\s:_-]+{region}$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(rf"\s*\({region}\)\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    return CONSOLE_ALIASES.get(cleaned.casefold(), cleaned)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    role = db.Column(db.String(20), default="editor", nullable=False)
    display_name = db.Column(db.String(120))
    is_system = db.Column(db.Boolean, default=False, nullable=False)


class CollectionSpace(db.Model):
    """One logically isolated collection inside the shared PostgreSQL database."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False, index=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    owner = db.relationship("User", foreign_keys=[owner_user_id])


class CollectionPermission(db.Model):
    """Per-user access to one collection: viewer, editor or manager."""
    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey("collection_space.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default="viewer")
    can_edit_items = db.Column(db.Boolean)
    can_manage_prices = db.Column(db.Boolean)
    can_run_imports = db.Column(db.Boolean)
    can_manage_users = db.Column(db.Boolean)
    collection = db.relationship("CollectionSpace", backref=db.backref("permissions", lazy=True, cascade="all, delete-orphan"))
    user = db.relationship("User", backref=db.backref("collection_permissions", lazy=True, cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint("collection_id", "user_id", name="uq_collection_permission"),)


class CollectionAccessRequest(db.Model):
    """Opt-in request from one account to one collection.

    Collection managers only see requests directed at their own collection and
    never receive a directory of unrelated system accounts.
    """
    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey("collection_space.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    requested_role = db.Column(db.String(20), nullable=False, default="viewer")
    message = db.Column(db.String(500))
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    decided_at = db.Column(db.DateTime)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    collection = db.relationship("CollectionSpace", foreign_keys=[collection_id])
    user = db.relationship("User", foreign_keys=[user_id])
    decided_by = db.relationship("User", foreign_keys=[decided_by_user_id])
    __table_args__ = (db.UniqueConstraint("collection_id", "user_id", name="uq_collection_access_request"),)


class AppSetting(db.Model):
    """Global application settings. Secret values are encrypted before storage."""
    key = db.Column(db.String(120), primary_key=True)
    value = db.Column(db.Text)
    is_secret = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class CollectorItem(db.Model):
    """Generic physical collection item for Collector modules outside Games.

    The Games module keeps its mature existing schema.  New modules share this
    small common core so dashboard counts/values are real from day one.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category = db.Column(db.String(32), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    estimated_value_eur = db.Column(db.Float)
    purchase_price_eur = db.Column(db.Float)
    purchase_date = db.Column(db.Date)
    storage_location = db.Column(db.String(160))
    notes = db.Column(db.Text)
    barcode = db.Column(db.String(32), index=True)
    media_type = db.Column(db.String(120))
    cover_url = db.Column(db.Text)
    external_source = db.Column(db.String(80))
    external_id = db.Column(db.String(160))
    metadata_json = db.Column(db.Text)
    edition = db.Column(db.String(160))
    release_year = db.Column(db.Integer)
    condition = db.Column(db.String(40))
    completeness = db.Column(db.String(40))
    auto_value_eur = db.Column(db.Float)
    auto_value_low_eur = db.Column(db.Float)
    auto_value_high_eur = db.Column(db.Float)
    auto_value_status = db.Column(db.String(80))
    auto_value_updated_at = db.Column(db.DateTime)
    # v2.6.2: universal Trading Card Game foundation. Provider IDs stay in metadata_json.
    tcg_game = db.Column(db.String(80), index=True)
    card_set = db.Column(db.String(160), index=True)
    card_number = db.Column(db.String(80))
    card_language = db.Column(db.String(32))
    card_variant = db.Column(db.String(80))
    card_rarity = db.Column(db.String(120))
    card_grade = db.Column(db.String(80))
    auto_value_source = db.Column(db.String(120))
    fixed_value_eur = db.Column(db.Float)
    fixed_value_reason = db.Column(db.String(255))
    fixed_value_at = db.Column(db.DateTime)
    added_at = db.Column(db.DateTime, default=utc_now, nullable=False)


class BiboWork(db.Model):
    """Stable, media-independent work identity introduced with Bibo 3.0.

    Existing module tables remain authoritative.  The Bibo registry is a
    compatibility index over them, so upgrades do not rewrite or renumber the
    user's established collection.
    """
    id = db.Column(db.Integer, primary_key=True)
    canonical_key = db.Column(db.String(320), unique=True, nullable=False, index=True)
    media_kind = db.Column(db.String(32), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    sort_title = db.Column(db.String(255), nullable=False, index=True)
    series_name = db.Column(db.String(255))
    external_source = db.Column(db.String(80))
    external_id = db.Column(db.String(160))
    logical_unit_key = db.Column(db.String(320), index=True)
    availability_de = db.Column(db.String(32), default="unknown", nullable=False, index=True)
    cover_url = db.Column(db.Text)
    metadata_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class BiboEdition(db.Model):
    """One platform, format or model variant of a :class:`BiboWork`."""
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("bibo_work.id"), nullable=False, index=True)
    source_kind = db.Column(db.String(32), nullable=False)
    source_id = db.Column(db.String(80), nullable=False)
    format_label = db.Column(db.String(120))
    platform = db.Column(db.String(160))
    region = db.Column(db.String(50))
    release_year = db.Column(db.Integer)
    image_url = db.Column(db.Text)
    barcode = db.Column(db.String(32), index=True)
    language = db.Column(db.String(80))
    country = db.Column(db.String(80))
    release_status = db.Column(db.String(32), default="unknown", nullable=False)
    content_count = db.Column(db.Integer, default=1, nullable=False)
    metadata_json = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    work = db.relationship("BiboWork", backref=db.backref("editions", lazy=True, cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint("source_kind", "source_id", name="uq_bibo_edition_source"),)


class BiboCopy(db.Model):
    """Individual owned/wanted copy linked back to its unchanged legacy row."""
    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.Integer, db.ForeignKey("bibo_edition.id"), nullable=False, index=True)
    source_kind = db.Column(db.String(32), nullable=False)
    source_id = db.Column(db.String(80), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    status = db.Column(db.String(30), nullable=False, default="owned", index=True)
    ownership_format = db.Column(db.String(30), nullable=False, default="physical")
    quantity = db.Column(db.Integer, nullable=False, default=1)
    purchase_price_eur = db.Column(db.Float)
    effective_value_eur = db.Column(db.Float)
    condition_label = db.Column(db.String(80))
    completeness_label = db.Column(db.String(80))
    storage_location = db.Column(db.String(160))
    acquired_at = db.Column(db.Date)
    location_id = db.Column(db.Integer, db.ForeignKey("storage_location.id"), index=True)
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    edition = db.relationship("BiboEdition", backref=db.backref("copies", lazy=True, cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint("source_kind", "source_id", name="uq_bibo_copy_source"),)


class StorageLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("storage_location.id"), index=True)
    name = db.Column(db.String(160), nullable=False)
    token = db.Column(db.String(48), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    parent = db.relationship("StorageLocation", remote_side=[id], backref=db.backref("children", lazy=True))
    copies = db.relationship("BiboCopy", backref="structured_location", lazy=True)


class LoanRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    copy_id = db.Column(db.Integer, db.ForeignKey("bibo_copy.id"), nullable=False, index=True)
    borrower = db.Column(db.String(160), nullable=False)
    lent_at = db.Column(db.Date, nullable=False, default=date.today)
    due_at = db.Column(db.Date)
    returned_at = db.Column(db.Date)
    notes = db.Column(db.Text)
    copy = db.relationship("BiboCopy", backref=db.backref("loans", lazy=True, cascade="all, delete-orphan"))


class InventorySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey("storage_location.id"), nullable=False, index=True)
    expected_count = db.Column(db.Integer, default=0, nullable=False)
    found_count = db.Column(db.Integer, default=0, nullable=False)
    state = db.Column(db.String(24), default="open", nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    finished_at = db.Column(db.DateTime)
    location = db.relationship("StorageLocation")


class BiboSeries(db.Model):
    """Media-independent series identity for the unified Bibo 4 library."""
    id = db.Column(db.Integer, primary_key=True)
    canonical_key = db.Column(db.String(320), unique=True, nullable=False, index=True)
    media_kind = db.Column(db.String(32), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class BiboSeriesMembership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey("bibo_series.id"), nullable=False, index=True)
    work_id = db.Column(db.Integer, db.ForeignKey("bibo_work.id"), nullable=False, index=True)
    position_label = db.Column(db.String(80))
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    series = db.relationship("BiboSeries", backref=db.backref("memberships", lazy=True, cascade="all, delete-orphan"))
    work = db.relationship("BiboWork", backref=db.backref("series_memberships", lazy=True, cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint("series_id", "work_id", name="uq_bibo_series_work"),)


class ReleaseCoverage(db.Model):
    """Logical works covered by one physical release/box without duplicating its value."""
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    source_kind = db.Column(db.String(32), nullable=False, default="collector")
    source_id = db.Column(db.String(80), nullable=False, index=True)
    target_kind = db.Column(db.String(32), nullable=False, index=True)
    target_key = db.Column(db.String(320), nullable=False, index=True)
    target_title = db.Column(db.String(255), nullable=False)
    sequence_label = db.Column(db.String(80))
    origin = db.Column(db.String(24), nullable=False, default="manual")
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    __table_args__ = (db.UniqueConstraint("owner_id", "source_kind", "source_id", "target_kind", "target_key", name="uq_release_coverage"),)


class PersonalReview(db.Model):
    """A user's personal content review, deliberately separate from market value."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    media_kind = db.Column(db.String(32), nullable=False, index=True)
    source_kind = db.Column(db.String(32), nullable=False)
    source_id = db.Column(db.String(80), nullable=False, index=True)
    title_snapshot = db.Column(db.String(255), nullable=False)
    overall_rating = db.Column(db.Integer, nullable=False)
    dimension_1 = db.Column(db.Integer)
    dimension_2 = db.Column(db.Integer)
    dimension_3 = db.Column(db.Integer)
    dimension_4 = db.Column(db.Integer)
    dimension_5 = db.Column(db.Integer)
    review_title = db.Column(db.String(180))
    review_text = db.Column(db.Text)
    pros = db.Column(db.Text)
    cons = db.Column(db.Text)
    recommendation = db.Column(db.String(16))
    favorite = db.Column(db.Boolean, default=False, nullable=False)
    spoiler = db.Column(db.Boolean, default=False, nullable=False)
    consumed_at = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "source_kind", "source_id", name="uq_personal_review_user_source"),)


class ImageAsset(db.Model):
    """Persistent mapping from a remote HTTPS image to Bibo's local archive."""
    id = db.Column(db.Integer, primary_key=True)
    source_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    source_url = db.Column(db.Text, nullable=False)
    local_url = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    error = db.Column(db.String(255))
    byte_size = db.Column(db.Integer)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_attempt_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class CollectorPriceHistory(db.Model):
    """Price history for non-gaming Collector modules."""
    id = db.Column(db.Integer, primary_key=True)
    collector_item_id = db.Column(db.Integer, db.ForeignKey("collector_item.id"), nullable=False, index=True)
    value_eur = db.Column(db.Float, nullable=False)
    low_eur = db.Column(db.Float)
    high_eur = db.Column(db.Float)
    source = db.Column(db.String(120), nullable=False)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    item = db.relationship("CollectorItem", backref=db.backref("collector_price_history", lazy=True, cascade="all, delete-orphan"))


class CollectorPriceActivity(db.Model):
    """Successful valuation checks for movies, TV, books, music, cards and custom items."""
    id = db.Column(db.Integer, primary_key=True)
    collector_item_id = db.Column(db.Integer, db.ForeignKey("collector_item.id"), nullable=False, index=True)
    previous_value_eur = db.Column(db.Float)
    value_eur = db.Column(db.Float, nullable=False)
    delta_eur = db.Column(db.Float, nullable=False, default=0)
    change_type = db.Column(db.String(20), nullable=False, index=True)
    source = db.Column(db.String(120), nullable=False)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    item = db.relationship("CollectorItem", backref=db.backref("collector_price_activity", lazy=True, cascade="all, delete-orphan"))


class CollectorValueSnapshot(db.Model):
    """Collector-wide value snapshot including gaming and all generic modules."""
    id = db.Column(db.Integer, primary_key=True)
    collection_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    total_value_eur = db.Column(db.Float, nullable=False, default=0)
    owned_count = db.Column(db.Integer, nullable=False, default=0)
    valued_count = db.Column(db.Integer, nullable=False, default=0)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)


class Console(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    manufacturer = db.Column(db.String(120))
    generation = db.Column(db.String(50))
    games = db.relationship("Game", backref="console", lazy=True, cascade="all, delete-orphan")


class HardwareModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    console_id = db.Column(db.Integer, db.ForeignKey("console.id"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    model_number = db.Column(db.String(120), index=True)
    revision = db.Column(db.String(120))
    color = db.Column(db.String(80))
    region = db.Column(db.String(50))
    release_year = db.Column(db.Integer)
    reference_image = db.Column(db.Text)
    notes = db.Column(db.Text)
    edition = db.Column(db.String(160))
    pricecharting_url = db.Column(db.Text)
    pricecharting_name = db.Column(db.String(220))
    hardware_class = db.Column(db.String(30))
    console = db.relationship("Console", backref=db.backref("hardware_models", lazy=True, cascade="all, delete-orphan"))


class HardwareItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    hardware_model_id = db.Column(db.Integer, db.ForeignKey("hardware_model.id"), nullable=False, index=True)
    status = db.Column(db.String(30), default="owned", nullable=False, index=True)
    serial_number = db.Column(db.String(160))
    condition = db.Column(db.Integer, default=8)
    boxed = db.Column(db.Boolean, default=False)
    controller_present = db.Column(db.Boolean, default=False)
    power_supply_present = db.Column(db.Boolean, default=False)
    cables_present = db.Column(db.Boolean, default=False)
    manual_present = db.Column(db.Boolean, default=False)
    inserts_present = db.Column(db.Boolean, default=False)
    original_accessories_present = db.Column(db.Boolean, default=False)
    sealed = db.Column(db.Boolean, default=False)
    box_condition = db.Column(db.Integer, default=8)
    controller_condition = db.Column(db.Integer, default=8)
    completeness = db.Column(db.String(40), default="Loose")
    accessories_present = db.Column(db.Text)
    purchase_price = db.Column(db.Float)
    estimated_value = db.Column(db.Float)
    auto_value_eur = db.Column(db.Float)
    auto_value_low_eur = db.Column(db.Float)
    auto_value_high_eur = db.Column(db.Float)
    auto_value_source = db.Column(db.String(80))
    auto_value_updated_at = db.Column(db.DateTime)
    auto_value_url = db.Column(db.Text)
    auto_value_message = db.Column(db.Text)
    fixed_value_eur = db.Column(db.Float)
    fixed_value_reason = db.Column(db.String(255))
    fixed_value_at = db.Column(db.DateTime)
    component_data = db.Column(db.Text)
    set_condition = db.Column(db.Float)
    set_condition_label = db.Column(db.String(40))
    condition_summary = db.Column(db.Text)
    valuation_breakdown = db.Column(db.Text)
    purchase_date = db.Column(db.Date)
    storage_location = db.Column(db.String(160))
    firmware = db.Column(db.String(120))
    tested_status = db.Column(db.String(30), default="tested")
    notes = db.Column(db.Text)
    photo_front = db.Column(db.Text)
    photo_back = db.Column(db.Text)
    added_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    model = db.relationship("HardwareModel", backref=db.backref("items", lazy=True, cascade="all, delete-orphan"))


class HardwarePriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hardware_item_id = db.Column(db.Integer, db.ForeignKey("hardware_item.id"), nullable=False, index=True)
    value_eur = db.Column(db.Float, nullable=False)
    low_eur = db.Column(db.Float)
    high_eur = db.Column(db.Float)
    source = db.Column(db.String(80), nullable=False)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    item = db.relationship("HardwareItem", backref=db.backref("price_history", lazy=True, cascade="all, delete-orphan"))


class AccessoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    console_id = db.Column(db.Integer, db.ForeignKey("console.id"), index=True)
    name = db.Column(db.String(180), nullable=False)
    manufacturer = db.Column(db.String(120))
    model_number = db.Column(db.String(120))
    barcode = db.Column(db.String(32), index=True)
    product_code = db.Column(db.String(120), index=True)
    category = db.Column(db.String(60), default="other", nullable=False, index=True)
    compatibility = db.Column(db.Text)
    original_product = db.Column(db.Boolean, default=True)
    component_kind = db.Column(db.String(40), default="device", nullable=False)
    parent_accessory_id = db.Column(db.Integer, db.ForeignKey("accessory_item.id"), index=True)
    included_in_parent_value = db.Column(db.Boolean, default=False)
    media_present = db.Column(db.Boolean, default=False)
    case_present = db.Column(db.Boolean, default=False)
    manual_present = db.Column(db.Boolean, default=False)
    disc_condition = db.Column(db.Integer)
    color = db.Column(db.String(80))
    status = db.Column(db.String(30), default="owned", nullable=False, index=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    condition = db.Column(db.Integer, default=8)
    boxed = db.Column(db.Boolean, default=False)
    purchase_price = db.Column(db.Float)
    estimated_value = db.Column(db.Float)
    auto_value_eur = db.Column(db.Float)
    auto_value_low_eur = db.Column(db.Float)
    auto_value_high_eur = db.Column(db.Float)
    auto_value_source = db.Column(db.String(80))
    auto_value_updated_at = db.Column(db.DateTime)
    auto_value_url = db.Column(db.Text)
    auto_value_status = db.Column(db.String(40))
    auto_value_message = db.Column(db.Text)
    fixed_value_eur = db.Column(db.Float)
    fixed_value_reason = db.Column(db.String(255))
    fixed_value_at = db.Column(db.DateTime)
    storage_location = db.Column(db.String(160))
    reference_image = db.Column(db.Text)
    photo = db.Column(db.Text)
    notes = db.Column(db.Text)
    added_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    console = db.relationship("Console", backref=db.backref("accessories", lazy=True))
    parent_accessory = db.relationship(
        "AccessoryItem",
        remote_side=[id],
        backref=db.backref("components", lazy=True),
    )


class AccessoryPriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    accessory_item_id = db.Column(db.Integer, db.ForeignKey("accessory_item.id"), nullable=False, index=True)
    value_eur = db.Column(db.Float, nullable=False)
    low_eur = db.Column(db.Float)
    high_eur = db.Column(db.Float)
    source = db.Column(db.String(80), nullable=False)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    item = db.relationship("AccessoryItem", backref=db.backref("price_history", lazy=True, cascade="all, delete-orphan"))


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    console_id = db.Column(db.Integer, db.ForeignKey("console.id"), nullable=False)
    region = db.Column(db.String(50), default="PAL")
    language = db.Column(db.String(80), default="Deutsch")
    release_year = db.Column(db.Integer)
    publisher = db.Column(db.Text)
    developer = db.Column(db.Text)
    genre = db.Column(db.Text)
    edition = db.Column(db.String(120), default="Standard")
    franchise = db.Column(db.Text)
    franchise_source = db.Column(db.String(40))
    series_status = db.Column(db.String(20), default="unreviewed", nullable=False)
    series_group = db.Column(db.String(120))
    series_generation = db.Column(db.String(40))
    # physical = reguläres physisches Spiel; physical_addon = nachweisbar physischer
    # DLC/Season-Pass; excluded = digital/mobile/reiner Online-Dienst.
    physical_status = db.Column(db.String(24), default="physical", nullable=False)
    barcode = db.Column(db.String(32), index=True)
    product_code = db.Column(db.String(64), index=True)
    cover_url = db.Column(db.Text)
    external_source = db.Column(db.String(80))
    external_id = db.Column(db.String(160))
    collections = db.relationship("CollectionItem", backref="game", lazy=True, cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint("title", "console_id", "region", "edition", name="uq_game_variant"),)


class CollectionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    status = db.Column(db.String(30), default="owned")
    ownership_format = db.Column(db.String(20), default="physical", nullable=False)
    completeness = db.Column(db.String(30), default="Loose")
    media_present = db.Column(db.Boolean, default=True)
    box_present = db.Column(db.Boolean, default=False)
    manual_present = db.Column(db.Boolean, default=False)
    sealed = db.Column(db.Boolean, default=False)
    media_condition = db.Column(db.Integer, default=8)
    box_condition = db.Column(db.Integer, default=8)
    purchase_price = db.Column(db.Float)
    purchase_date = db.Column(db.Date)
    estimated_value = db.Column(db.Float)
    market_value_usd = db.Column(db.Float)
    market_value_source = db.Column(db.String(80))
    market_value_updated_at = db.Column(db.DateTime)
    pricecharting_product_id = db.Column(db.String(80))
    auto_value_eur = db.Column(db.Float)
    auto_value_low_eur = db.Column(db.Float)
    auto_value_high_eur = db.Column(db.Float)
    auto_value_source = db.Column(db.String(80))
    auto_value_condition = db.Column(db.String(40))
    auto_value_confidence = db.Column(db.String(20))
    auto_value_updated_at = db.Column(db.DateTime)
    auto_value_url = db.Column(db.Text)
    auto_value_status = db.Column(db.String(40))
    auto_value_message = db.Column(db.Text)
    auto_value_pending_json = db.Column(db.Text)
    fixed_value_eur = db.Column(db.Float)
    fixed_value_reason = db.Column(db.String(255))
    fixed_value_at = db.Column(db.DateTime)
    rarity = db.Column(db.Integer, default=1)
    notes = db.Column(db.Text)
    storage_location = db.Column(db.String(160))
    tags = db.Column(db.Text)
    play_status = db.Column(db.String(30), default="unplayed")
    work_marker = db.Column(db.String(40))
    photo_front = db.Column(db.Text)
    photo_back = db.Column(db.Text)
    photo_media = db.Column(db.Text)
    wishlist_priority = db.Column(db.Integer, default=2)
    wishlist_target_price = db.Column(db.Float)
    wishlist_condition = db.Column(db.String(40))
    wishlist_shop = db.Column(db.String(160))
    wishlist_url = db.Column(db.Text)
    wishlist_notes = db.Column(db.Text)
    added_at = db.Column(db.DateTime, default=utc_now)
    user = db.relationship("User", backref=db.backref("collection_items", lazy=True))


class DuplicateIgnore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_a_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False, index=True)
    game_b_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    __table_args__ = (db.UniqueConstraint("game_a_id", "game_b_id", name="uq_duplicate_ignore_pair"),)


class ImportBatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    delimiter = db.Column(db.String(4), default=";", nullable=False)
    state = db.Column(db.String(20), default="preview", nullable=False, index=True)
    total_count = db.Column(db.Integer, default=0, nullable=False)
    new_count = db.Column(db.Integer, default=0, nullable=False)
    duplicate_count = db.Column(db.Integer, default=0, nullable=False)
    invalid_count = db.Column(db.Integer, default=0, nullable=False)
    added_game_count = db.Column(db.Integer, default=0, nullable=False)
    added_copy_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    applied_at = db.Column(db.DateTime)
    undone_at = db.Column(db.DateTime)
    rows = db.relationship("ImportBatchRow", backref="batch", lazy=True, cascade="all, delete-orphan", order_by="ImportBatchRow.row_number")


class ImportBatchRow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("import_batch.id"), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    payload_json = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, index=True)
    message = db.Column(db.String(255))
    matched_game_id = db.Column(db.Integer, db.ForeignKey("game.id"), index=True)
    duplicate_of_row_id = db.Column(db.Integer, db.ForeignKey("import_batch_row.id"), index=True)
    decision = db.Column(db.String(20))
    created_game_id = db.Column(db.Integer, index=True)
    created_copy_id = db.Column(db.Integer, index=True)
    matched_game = db.relationship("Game", foreign_keys=[matched_game_id])
    duplicate_of_row = db.relationship("ImportBatchRow", remote_side=[id], foreign_keys=[duplicate_of_row_id])


class OfflineCapture(db.Model):
    """Server-side inbox for scans created while a client was offline.

    Offline captures never mutate the collection directly.  A stable client id
    makes synchronization idempotent, while the stored revision records which
    catalogue/collection state was visible when the capture reached the server.
    """
    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    collection_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    client_id = db.Column(db.String(80), nullable=False, index=True)
    barcode = db.Column(db.String(32), nullable=False, index=True)
    source = db.Column(db.String(24), default="scanner", nullable=False)
    state = db.Column(db.String(24), default="queued", nullable=False, index=True)
    message = db.Column(db.String(255))
    matches_json = db.Column(db.Text)
    revision_token = db.Column(db.String(64))
    client_created_at = db.Column(db.DateTime)
    received_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    reviewed_at = db.Column(db.DateTime)
    actor = db.relationship("User", foreign_keys=[actor_user_id])
    __table_args__ = (db.UniqueConstraint("actor_user_id", "client_id", name="uq_offline_capture_actor_client"),)


class ApplicationError(db.Model):
    """Short, user-safe incident record for unexpected request failures."""
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(24), nullable=False, unique=True, index=True)
    collection_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    endpoint = db.Column(db.String(180))
    path = db.Column(db.Text)
    method = db.Column(db.String(12))
    exception_type = db.Column(db.String(120))
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)


class CaptureBatch(db.Model):
    """Mobile shopping/scan session containing multiple barcodes."""
    id = db.Column(db.Integer, primary_key=True)
    collection_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False, default="Neue Erfassung")
    store = db.Column(db.String(160))
    purchase_total_eur = db.Column(db.Float)
    state = db.Column(db.String(24), nullable=False, default="open", index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    finished_at = db.Column(db.DateTime)


class CaptureBatchItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("capture_batch.id"), nullable=False, index=True)
    barcode = db.Column(db.String(32), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    purchase_price_eur = db.Column(db.Float)
    state = db.Column(db.String(24), nullable=False, default="queued", index=True)
    message = db.Column(db.String(255))
    matches_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    batch = db.relationship("CaptureBatch", backref=db.backref("items", lazy=True, cascade="all, delete-orphan", order_by="CaptureBatchItem.id"))
    __table_args__ = (db.UniqueConstraint("batch_id", "barcode", name="uq_capture_batch_barcode"),)


class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    collection_item_id = db.Column(db.Integer, db.ForeignKey("collection_item.id"), nullable=False, index=True)
    value_eur = db.Column(db.Float, nullable=False)
    low_eur = db.Column(db.Float)
    high_eur = db.Column(db.Float)
    source = db.Column(db.String(80), nullable=False)
    condition = db.Column(db.String(40))
    confidence = db.Column(db.String(20))
    source_url = db.Column(db.Text)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    collection_item = db.relationship("CollectionItem", backref=db.backref("price_history", lazy=True, cascade="all, delete-orphan"))


class CollectionValueSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_value_eur = db.Column(db.Float, nullable=False, default=0)
    owned_count = db.Column(db.Integer, nullable=False, default=0)
    valued_count = db.Column(db.Integer, nullable=False, default=0)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)


class RevaluationRun(db.Model):
    """Audit trail for completed manual and scheduled collection valuations."""
    id = db.Column(db.Integer, primary_key=True)
    collection_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    source = db.Column(db.String(20), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    finished_at = db.Column(db.DateTime, index=True)
    success = db.Column(db.Boolean, default=False, nullable=False, index=True)
    checked_count = db.Column(db.Integer, default=0, nullable=False)
    valued_count = db.Column(db.Integer, default=0, nullable=False)
    unsupported_count = db.Column(db.Integer, default=0, nullable=False)
    failed_count = db.Column(db.Integer, default=0, nullable=False)
    current_index = db.Column(db.Integer, default=0, nullable=False)
    total_count = db.Column(db.Integer, default=0, nullable=False)
    current_title = db.Column(db.String(240))
    state = db.Column(db.String(20), default="queued", nullable=False, index=True)
    message = db.Column(db.Text)
    heartbeat_at = db.Column(db.DateTime, index=True)


class RevaluationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    revaluation_run_id = db.Column(db.Integer, db.ForeignKey("revaluation_run.id"), nullable=False, index=True)
    collection_item_id = db.Column(db.Integer, db.ForeignKey("collection_item.id"), index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    title = db.Column(db.String(240), nullable=False)
    status = db.Column(db.String(40), nullable=False)
    message = db.Column(db.Text)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    collection_item = db.relationship("CollectionItem")


class SeriesScanRun(db.Model):
    """Background audit for one-click series catalogue expansion scans."""
    id = db.Column(db.Integer, primary_key=True)
    collection_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    started_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    finished_at = db.Column(db.DateTime, index=True)
    state = db.Column(db.String(20), default="queued", nullable=False, index=True)
    total_count = db.Column(db.Integer, default=0, nullable=False)
    checked_count = db.Column(db.Integer, default=0, nullable=False)
    added_count = db.Column(db.Integer, default=0, nullable=False)
    updated_count = db.Column(db.Integer, default=0, nullable=False)
    failed_count = db.Column(db.Integer, default=0, nullable=False)
    current_franchise = db.Column(db.String(180))
    message = db.Column(db.Text)


class SeriesScanLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    series_scan_run_id = db.Column(db.Integer, db.ForeignKey("series_scan_run.id"), nullable=False, index=True)
    position = db.Column(db.Integer, default=0, nullable=False)
    franchise = db.Column(db.String(180), nullable=False)
    status = db.Column(db.String(40), nullable=False)
    added_count = db.Column(db.Integer, default=0, nullable=False)
    updated_count = db.Column(db.Integer, default=0, nullable=False)
    message = db.Column(db.Text)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False)


class CollectionProject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    collection_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    target_query = db.Column(db.String(180))
    target_count = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)


class PriceActivity(db.Model):
    """One row for every successful automatic valuation, even when the price stayed unchanged."""
    id = db.Column(db.Integer, primary_key=True)
    collection_item_id = db.Column(db.Integer, db.ForeignKey("collection_item.id"), nullable=False, index=True)
    revaluation_run_id = db.Column(db.Integer, db.ForeignKey("revaluation_run.id"), index=True)
    previous_value_eur = db.Column(db.Float)
    value_eur = db.Column(db.Float, nullable=False)
    delta_eur = db.Column(db.Float, nullable=False, default=0)
    change_type = db.Column(db.String(20), nullable=False, index=True)
    source = db.Column(db.String(80), nullable=False)
    recorded_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    collection_item = db.relationship("CollectionItem", backref=db.backref("price_activity", lazy=True, cascade="all, delete-orphan"))
    revaluation_run = db.relationship("RevaluationRun", backref=db.backref("price_activity", lazy=True, cascade="all, delete-orphan"))


def collection_total_value_snapshot():
    """Store one point for the complete shared collection value history."""
    shared = shared_collection_user()
    if not shared:
        return None
    items = CollectionItem.query.filter_by(user_id=shared.id, status="owned").all()
    total = 0.0
    valued = 0
    for item in items:
        value = effective_value(item)
        if value is not None:
            total += float(value)
            valued += 1
    owned_count = len(items)
    for item in HardwareItem.query.filter_by(status="owned").all():
        owned_count += 1
        value = effective_hardware_value(item)
        if value is not None:
            total += float(value)
            valued += 1
    for item in AccessoryItem.query.filter_by(status="owned").all():
        quantity = max(1, int(item.quantity or 1))
        owned_count += quantity
        value = effective_accessory_value(item)
        if value is not None and accessory_counts_in_total(item):
            total += float(value) * quantity
            valued += quantity
    snap = CollectionValueSnapshot(total_value_eur=round(total, 2), owned_count=owned_count, valued_count=valued)
    db.session.add(snap)
    return snap


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    collection_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    entity_type = db.Column(db.String(60), nullable=False, index=True)
    entity_id = db.Column(db.Integer)
    message = db.Column(db.Text, nullable=False)
    details_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    actor = db.relationship("User", foreign_keys=[actor_user_id])


class CollectionGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    collection_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    goal_type = db.Column(db.String(30), default="manual", nullable=False)
    target_count = db.Column(db.Integer, nullable=False, default=1)
    franchise = db.Column(db.Text)
    series_group = db.Column(db.String(120))
    console_id = db.Column(db.Integer, db.ForeignKey("console.id"))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    priority = db.Column(db.Integer, default=2, nullable=False)
    target_budget_eur = db.Column(db.Float)
    target_date = db.Column(db.Date)
    console = db.relationship("Console")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])


class SeriesEntry(db.Model):
    """Extern entdeckter Titel einer Spielereihe, unabhängig von einer konkreten Plattformvariante im lokalen Katalog."""
    id = db.Column(db.Integer, primary_key=True)
    franchise = db.Column(db.Text, nullable=False, index=True)
    title = db.Column(db.String(240), nullable=False)
    release_year = db.Column(db.Integer)
    cover_url = db.Column(db.Text)
    platforms = db.Column(db.Text)
    series_group = db.Column(db.String(120))
    series_generation = db.Column(db.String(40))
    external_source = db.Column(db.String(40), default="RAWG", nullable=False)
    external_id = db.Column(db.String(160), nullable=False)
    added_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    __table_args__ = (db.UniqueConstraint("franchise", "external_source", "external_id", name="uq_series_entry_external"),)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


SHARED_COLLECTION_USERNAME = "__gamecollector_shared__"


def shared_collection_user():
    return User.query.filter_by(username=SHARED_COLLECTION_USERNAME, is_system=True).first()


def accessible_collection_spaces(user=None):
    user = user or current_user
    if not getattr(user, "is_authenticated", False):
        return []
    query = CollectionSpace.query.order_by(CollectionSpace.name, CollectionSpace.id)
    if getattr(user, "is_admin", False):
        return query.all()
    return query.join(CollectionPermission).filter(CollectionPermission.user_id == user.id).all()


def active_collection_space():
    if not current_user.is_authenticated:
        return None
    spaces = accessible_collection_spaces(current_user)
    if not spaces:
        return None
    requested_id = session.get("collection_space_id")
    selected = next((space for space in spaces if space.id == requested_id), None) or spaces[0]
    if session.get("collection_space_id") != selected.id:
        session["collection_space_id"] = selected.id
    return selected


def active_collection_owner():
    """Return the hidden owner row backing the currently selected collection."""
    space = active_collection_space()
    return space.owner if space else None


def active_collection_user_id():
    owner = active_collection_owner()
    return owner.id if owner else None


def active_collection_permission_role(user=None, space=None):
    user = user or current_user
    if not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_admin", False):
        return "manager"
    space = space or active_collection_space()
    if not space:
        return None
    permission = CollectionPermission.query.filter_by(collection_id=space.id, user_id=user.id).first()
    return permission.role if permission else None


COLLECTION_CAPABILITY_DEFAULTS = {
    "viewer": {"edit_items": False, "manage_prices": False, "run_imports": False, "manage_users": False},
    "editor": {"edit_items": True, "manage_prices": True, "run_imports": True, "manage_users": False},
    "manager": {"edit_items": True, "manage_prices": True, "run_imports": True, "manage_users": True},
}


def collection_capability(name, user=None, space=None):
    """Resolve an explicit per-collection grant, falling back to the selected role."""
    user = user or current_user
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_admin", False):
        return True
    space = space or active_collection_space()
    if not space:
        return False
    permission = CollectionPermission.query.filter_by(collection_id=space.id, user_id=user.id).first()
    if not permission:
        return False
    column = f"can_{name}"
    explicit = getattr(permission, column, None)
    if explicit is not None:
        return bool(explicit)
    return COLLECTION_CAPABILITY_DEFAULTS.get(permission.role, COLLECTION_CAPABILITY_DEFAULTS["viewer"]).get(name, False)


def scoped_hardware_query():
    query = HardwareItem.query
    uid = active_collection_user_id() if has_request_context() and current_user.is_authenticated else None
    return query.filter(HardwareItem.user_id == uid) if uid is not None else query


def scoped_accessory_query():
    query = AccessoryItem.query
    uid = active_collection_user_id() if has_request_context() and current_user.is_authenticated else None
    return query.filter(AccessoryItem.user_id == uid) if uid is not None else query


def scoped_hardware_or_404(item_id):
    return scoped_hardware_query().filter(HardwareItem.id == item_id).first_or_404()


def scoped_accessory_or_404(item_id):
    return scoped_accessory_query().filter(AccessoryItem.id == item_id).first_or_404()


@app.context_processor
def inject_globals():
    owner = active_collection_owner() if current_user.is_authenticated else None
    return {
        "now": local_datetime(utc_now()), "app_version": APP_VERSION, "app_name": APP_NAME, "user_collection": collection_for, "user_collection_items": collection_items_for, "collector_effective_value": collector_effective_value, "is_pokemon_card": is_pokemon_card,
        "active_collection_scope": "multi",
        "active_collection_label": (active_collection_space().name if owner else "Sammlung"),
        "active_collection_owner": owner,
        "active_collection_space": active_collection_space() if owner else None,
        "available_collection_spaces": accessible_collection_spaces(current_user) if owner else [],
        "collection_permission_role": active_collection_permission_role() if owner else None,
        "can_collection": collection_capability,
        "custom_category_icons": CUSTOM_CATEGORY_ICONS,
        "effective_role": effective_role() if current_user.is_authenticated else None,
        "eur": format_eur,
        "game_price": game_price_info,
        "effective_value": effective_value,
        "effective_value_source": effective_value_source,
        "effective_accessory_value": effective_accessory_value,
        "accessory_category_label": accessory_category_label,
        "accessory_counts_in_total": accessory_counts_in_total,
        "display_timezone": DISPLAY_TIMEZONE_NAME,
        "pc_component_fields": PC_COMPONENT_FIELDS,
    }


def collection_items_for(game, user_id=None):
    """Return all physical copies of a catalog title in the shared collection."""
    uid = user_id or active_collection_user_id()
    if not uid:
        return []
    return sorted([item for item in getattr(game, "collections", []) if item.user_id == uid], key=lambda i: (i.added_at or datetime.min, i.id or 0))


def collection_for(game, user_id=None):
    """Backward-compatible helper: return the first physical copy, if any."""
    rows = collection_items_for(game, user_id=user_id)
    return rows[0] if rows else None


def log_activity(action, entity_type, entity_id, message, details=None):
    actor_id = current_user.id if current_user.is_authenticated and not getattr(current_user, "is_system", False) else None
    row = ActivityLog(
        collection_user_id=active_collection_user_id() if has_request_context() and current_user.is_authenticated else None,
        actor_user_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id,
        message=message, details_json=json.dumps(details, ensure_ascii=False) if details else None,
    )
    db.session.add(row)
    return row


def effective_role(user=None):
    user = user or current_user
    if getattr(user, "is_admin", False):
        return "admin"
    role = active_collection_permission_role(user=user) if getattr(user, "is_authenticated", False) else None
    return role or "viewer"


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def collection_manager_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not collection_capability("manage_users"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _settings_cipher():
    digest = hashlib.sha256(str(app.config["SECRET_KEY"]).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def app_setting_get(key, default=""):
    row = db.session.get(AppSetting, key)
    if not row or not row.value:
        return default
    if not row.is_secret:
        return row.value
    try:
        return _settings_cipher().decrypt(row.value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        app.logger.warning("Could not decrypt application setting %s", key)
        return default


def app_setting_set(key, value, secret=False):
    row = db.session.get(AppSetting, key) or AppSetting(key=key)
    row.is_secret = bool(secret)
    row.value = (_settings_cipher().encrypt(value.encode("utf-8")).decode("ascii") if secret and value else value)
    row.updated_at = utc_now()
    db.session.add(row)


def ebay_credentials():
    """Prefer settings entered by an administrator, with .env as fallback."""
    return {
        "client_id": app_setting_get("ebay_client_id", os.environ.get("EBAY_CLIENT_ID", "")).strip(),
        "client_secret": app_setting_get("ebay_client_secret", os.environ.get("EBAY_CLIENT_SECRET", "")).strip(),
        "dev_id": app_setting_get("ebay_dev_id", os.environ.get("EBAY_DEV_ID", "")).strip(),
        "marketplace": app_setting_get("ebay_marketplace", os.environ.get("EBAY_MARKETPLACE", "EBAY_DE")).strip() or "EBAY_DE",
        "environment": app_setting_get("ebay_environment", os.environ.get("EBAY_ENVIRONMENT", "production")).strip() or "production",
    }


def ebay_api_base(credentials=None):
    credentials = credentials or ebay_credentials()
    return "https://api.sandbox.ebay.com" if credentials.get("environment") == "sandbox" else "https://api.ebay.com"


def ebay_connection_test():
    credentials = ebay_credentials()
    if not credentials["client_id"] or not credentials["client_secret"]:
        return False, "Client-ID und Client-Secret sind noch nicht vollständig hinterlegt."
    token = base64.b64encode(f'{credentials["client_id"]}:{credentials["client_secret"]}'.encode("utf-8")).decode("ascii")
    body = urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode("ascii")
    req = Request(ebay_api_base(credentials) + "/identity/v1/oauth2/token", data=body, headers={
        "Authorization": f"Basic {token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": f"GameCollector/{APP_VERSION}",
    }, method="POST")
    try:
        with urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("access_token"):
            return True, "Verbindung zu eBay erfolgreich."
        return False, "eBay hat kein Zugriffstoken zurückgegeben."
    except HTTPError as exc:
        if exc.code in (400, 401):
            return False, "eBay hat Client-ID oder Client-Secret abgewiesen."
        return False, f"eBay-Verbindung fehlgeschlagen (HTTP {exc.code})."
    except (URLError, TimeoutError, ValueError):
        return False, "eBay ist derzeit nicht erreichbar oder hat unerwartet geantwortet."


_EBAY_TOKEN_CACHE = {"token": None, "expires_at": 0.0, "client_id": None}


def ebay_access_token(force=False):
    credentials = ebay_credentials()
    if not credentials["client_id"] or not credentials["client_secret"]:
        return None, "ebay_not_configured"
    if (not force and _EBAY_TOKEN_CACHE["token"] and _EBAY_TOKEN_CACHE["client_id"] == credentials["client_id"]
            and _EBAY_TOKEN_CACHE["expires_at"] > time.time() + 60):
        return _EBAY_TOKEN_CACHE["token"], "ok"
    basic = base64.b64encode(f'{credentials["client_id"]}:{credentials["client_secret"]}'.encode("utf-8")).decode("ascii")
    body = urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode("ascii")
    req = Request(ebay_api_base(credentials) + "/identity/v1/oauth2/token", data=body, headers={
        "Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": f"GameCollector/{APP_VERSION}",
    }, method="POST")
    try:
        with urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        token = payload.get("access_token")
        if not token:
            return None, "ebay_auth_failed"
        _EBAY_TOKEN_CACHE.update(token=token, client_id=credentials["client_id"],
                                 expires_at=time.time() + int(payload.get("expires_in") or 7200))
        return token, "ok"
    except HTTPError as exc:
        return None, "ebay_auth_failed" if exc.code in (400, 401) else "ebay_unreachable"
    except (URLError, TimeoutError, ValueError):
        return None, "ebay_unreachable"


def ebay_api_json(path, params=None):
    token, status = ebay_access_token()
    if not token:
        return None, status
    url = f"{ebay_api_base()}{path}"
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": ebay_credentials()["marketplace"],
        "User-Agent": f"GameCollector/{APP_VERSION}",
    })
    try:
        with urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8")), "ok"
    except HTTPError as exc:
        if exc.code == 401:
            _EBAY_TOKEN_CACHE["expires_at"] = 0
        return None, "ebay_api_denied" if exc.code in (401, 403) else "ebay_unreachable"
    except (URLError, TimeoutError, ValueError):
        return None, "ebay_unreachable"


def ebay_search_gtin(gtin, limit=50):
    """Search eBay Browse by the dedicated GTIN parameter.

    Browse treats GTIN/EAN differently from a keyword query.  Physical media
    often have no listing title containing the numeric EAN, so q=<ean> can
    legitimately return zero while gtin=<ean> resolves the product.
    """
    code = clean_barcode(gtin)
    if not code:
        return [], "invalid_gtin"
    params = {
        "gtin": code, "limit": max(1, min(int(limit), 100)),
        "filter": "buyingOptions:{FIXED_PRICE}",
    }
    data, status = ebay_api_json("/buy/browse/v1/item_summary/search", params)
    if not isinstance(data, dict):
        return [], status
    rows = []
    for item in data.get("itemSummaries") or []:
        price = item.get("price") or {}
        shipping = item.get("shippingOptions") or []
        shipping_price = ((shipping[0].get("shippingCost") or {}) if shipping and isinstance(shipping[0], dict) else {})
        image = item.get("image") or {}
        rows.append({
            "id": str(item.get("itemId") or ""), "name": str(item.get("title") or "").strip(),
            "cover_url": str(image.get("imageUrl") or "").strip(),
            "price": parse_money_input(price.get("value")), "currency": str(price.get("currency") or ""),
            "shipping": parse_money_input(shipping_price.get("value")),
            "condition": str(item.get("condition") or ""), "url": str(item.get("itemWebUrl") or ""),
            "source": "eBay GTIN", "source_id": str(item.get("itemId") or ""), "barcode": code,
        })
    return rows, "ok"


def ebay_search_items(query, limit=50):
    """Search eBay exclusively through the official Buy Browse API.

    No HTML pages are fetched or parsed. If the API is unavailable or denies
    access, callers receive a status and must not fall back to web scraping.
    """
    params = {
        "q": str(query or "").strip(), "limit": max(1, min(int(limit), 100)),
        "filter": "buyingOptions:{FIXED_PRICE}",
    }
    data, status = ebay_api_json("/buy/browse/v1/item_summary/search", params)
    if not isinstance(data, dict):
        return [], status
    rows = []
    for item in data.get("itemSummaries") or []:
        price = item.get("price") or {}
        shipping = item.get("shippingOptions") or []
        shipping_price = ((shipping[0].get("shippingCost") or {}) if shipping and isinstance(shipping[0], dict) else {})
        image = item.get("image") or {}
        rows.append({
            "id": str(item.get("itemId") or ""), "name": str(item.get("title") or "").strip(),
            "cover_url": str(image.get("imageUrl") or "").strip(),
            "price": parse_money_input(price.get("value")), "currency": str(price.get("currency") or ""),
            "shipping": parse_money_input(shipping_price.get("value")),
            "condition": str(item.get("condition") or ""), "url": str(item.get("itemWebUrl") or ""),
            "source": "eBay", "source_id": str(item.get("itemId") or ""),
        })
    return rows, "ok"


def ebay_item(item_id):
    if not item_id:
        return None
    data, status = ebay_api_json(f"/buy/browse/v1/item/{quote(str(item_id), safe='')}")
    if not isinstance(data, dict):
        return None
    image = data.get("image") or {}
    price = data.get("price") or {}
    shipping = data.get("shippingOptions") or []
    shipping_price = ((shipping[0].get("shippingCost") or {}) if shipping and isinstance(shipping[0], dict) else {})
    seller = data.get("seller") or {}
    return {
        "name": str(data.get("title") or "").strip(), "cover_url": str(image.get("imageUrl") or "").strip(),
        "source": "eBay", "source_id": str(data.get("itemId") or item_id),
        "url": str(data.get("itemWebUrl") or ""), "price": parse_money_input(price.get("value")),
        "currency": str(price.get("currency") or ""), "shipping": parse_money_input(shipping_price.get("value")),
        "condition": str(data.get("condition") or ""), "condition_description": str(data.get("conditionDescription") or ""),
        "short_description": str(data.get("shortDescription") or ""), "category": str((data.get("category") or {}).get("categoryName") or ""),
        "seller_feedback_percentage": parse_money_input(seller.get("feedbackPercentage")),
        "seller_feedback_score": seller.get("feedbackScore"), "details_checked": True,
    }


def ebay_enrich_candidates(rows, limit=5):
    """Use the permitted getItem endpoint sparingly for the best search hits."""
    enriched = []
    for pos, row in enumerate(rows):
        current = dict(row)
        if pos < max(0, min(int(limit), 10)) and row.get("id"):
            detail = ebay_item(row["id"])
            if detail:
                current.update({key: value for key, value in detail.items() if value not in (None, "")})
        enriched.append(current)
    return enriched


@app.before_request
def enforce_viewer_read_only():
    if not current_user.is_authenticated or request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    # Viewer may update their own display name/password and log out, but cannot alter shared data.
    if request.endpoint in {"account", "logout", "collection_switch", "personal_review_edit"}:
        return None
    endpoint = request.endpoint or ""
    if endpoint == "collection_access" and not collection_capability("manage_users"):
        abort(403)
    if endpoint.startswith("import_csv") and not collection_capability("run_imports"):
        abort(403)
    price_endpoints = {
        "collector_revalue", "collection_revalue", "collection_revalue_cancel",
        "price_center_fix", "price_center_unfix", "price_center_revalue",
        "hardware_revalue", "accessories_revalue",
    }
    if (endpoint in price_endpoints or "revalue" in endpoint) and not collection_capability("manage_prices"):
        abort(403)
    if not collection_capability("edit_items"):
        abort(403)
    return None


@app.route("/collection/switch/<int:collection_id>", methods=["POST"])
@login_required
def collection_switch(collection_id):
    allowed = {space.id: space for space in accessible_collection_spaces(current_user)}
    if collection_id not in allowed:
        abort(403)
    session["collection_space_id"] = collection_id
    flash(f"Sammlung „{allowed[collection_id].name}“ ist jetzt aktiv.", "success")
    return redirect_back("collector_home")


def safe_local_url(value):
    """Accept a local path or a same-host URL, never an external redirect."""
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        host = urlsplit(request.host_url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != host.netloc:
            return None
        return parsed.path + (("?" + parsed.query) if parsed.query else "")
    return value if value.startswith("/") and not value.startswith("//") else None


def redirect_back(default_endpoint, **values):
    target = safe_local_url(request.form.get("return_to")) or safe_local_url(request.referrer)
    return redirect(target or url_for(default_endpoint, **values))


def clean_barcode(value):
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:32] or None


def normalize_product_code(value):
    """Store printed game product codes consistently without discarding letters."""
    cleaned = re.sub(r"\s+", "", str(value or "").strip()).upper()
    cleaned = cleaned.replace("–", "-").replace("—", "-")
    return cleaned[:64] or None


def ensure_schema():
    """Small in-place migration helper from v0.1 to v0.2."""
    inspector = inspect(db.engine)
    if "game" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("game")}
    wanted = {
        "developer": "VARCHAR(120)",
        "language": "VARCHAR(80)",
        "edition": "VARCHAR(120) DEFAULT 'Standard'",
        "genre": "VARCHAR(120)",
        "franchise": "VARCHAR(120)",
        "franchise_source": "VARCHAR(40)",
        "series_status": "VARCHAR(20) DEFAULT 'unreviewed' NOT NULL",
        "series_group": "VARCHAR(120)",
        "series_generation": "VARCHAR(40)",
        "physical_status": "VARCHAR(24) DEFAULT 'physical' NOT NULL",
        "barcode": "VARCHAR(32)",
        "product_code": "VARCHAR(64)",
        "cover_url": "TEXT",
        "external_source": "VARCHAR(80)",
        "external_id": "VARCHAR(160)",
    }
    with db.engine.begin() as conn:
        for column, sql_type in wanted.items():
            if column not in existing:
                conn.execute(text(f'ALTER TABLE "game" ADD COLUMN {column} {sql_type}'))
        # v2.0.1: obvious non-physical legacy entries stay in the database but no
        # longer affect series catalogues, percentages or values.
        conn.execute(text("UPDATE game SET physical_status='excluded' WHERE lower(title)='need for speed world'"))
        conn.execute(text("UPDATE game SET physical_status='excluded' WHERE console_id IN (SELECT id FROM console WHERE lower(name) IN ('ios','android'))"))
        # v0.3.5.1: RAWG can return long publisher/developer/genre strings.
        # PostgreSQL previously used VARCHAR(120), which caused a 500 on imports.
        if db.engine.dialect.name == "postgresql":
            for column in ("publisher", "developer", "genre", "franchise"):
                if column in existing:
                    conn.execute(text(f'ALTER TABLE "game" ALTER COLUMN {column} TYPE TEXT'))
        # Non-unique index so regional/edition variants can intentionally share a code if needed.
        if db.engine.dialect.name == "postgresql":
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_game_barcode ON "game" (barcode)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_game_product_code ON "game" (product_code)'))


    # v0.9.3: live valuation progress and collection work markers.
    inspector = inspect(db.engine)
    if "revaluation_run" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("revaluation_run")}
        wanted_run = {"collection_user_id":"INTEGER", "current_index":"INTEGER DEFAULT 0 NOT NULL", "total_count":"INTEGER DEFAULT 0 NOT NULL", "current_title":"VARCHAR(240)", "state":"VARCHAR(20) DEFAULT 'queued' NOT NULL", "heartbeat_at":"TIMESTAMP"}
        with db.engine.begin() as conn:
            for column, sql_type in wanted_run.items():
                if column not in cols:
                    conn.execute(text(f'ALTER TABLE "revaluation_run" ADD COLUMN {column} {sql_type}'))
    inspector = inspect(db.engine)
    for table_name in ("series_scan_run", "offline_capture"):
        if table_name in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns(table_name)}
            if "collection_user_id" not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN collection_user_id INTEGER'))
    inspector = inspect(db.engine)
    if "collection_item" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("collection_item")}
        if "work_marker" not in cols:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE "collection_item" ADD COLUMN work_marker VARCHAR(40)'))

    # v1.1.5: complete hardware condition, completeness and valuation metadata.
    inspector = inspect(db.engine)
    if "hardware_model" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("hardware_model")}
        with db.engine.begin() as conn:
            if "edition" not in cols:
                conn.execute(text('ALTER TABLE "hardware_model" ADD COLUMN edition VARCHAR(160)'))
            if "pricecharting_url" not in cols:
                conn.execute(text('ALTER TABLE "hardware_model" ADD COLUMN pricecharting_url TEXT'))
            if "pricecharting_name" not in cols:
                conn.execute(text('ALTER TABLE "hardware_model" ADD COLUMN pricecharting_name VARCHAR(220)'))
            if "hardware_class" not in cols:
                conn.execute(text('ALTER TABLE "hardware_model" ADD COLUMN hardware_class VARCHAR(30)'))
    inspector = inspect(db.engine)
    if "hardware_item" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("hardware_item")}
        wanted = {
            "power_supply_present":"BOOLEAN DEFAULT FALSE", "cables_present":"BOOLEAN DEFAULT FALSE",
            "manual_present":"BOOLEAN DEFAULT FALSE", "inserts_present":"BOOLEAN DEFAULT FALSE",
            "original_accessories_present":"BOOLEAN DEFAULT FALSE", "sealed":"BOOLEAN DEFAULT FALSE",
            "box_condition":"INTEGER DEFAULT 8", "controller_condition":"INTEGER DEFAULT 8",
            "completeness":"VARCHAR(40) DEFAULT 'Loose'", "auto_value_eur":"DOUBLE PRECISION",
            "auto_value_low_eur":"DOUBLE PRECISION", "auto_value_high_eur":"DOUBLE PRECISION",
            "auto_value_source":"VARCHAR(80)", "auto_value_updated_at":"TIMESTAMP",
            "auto_value_url":"TEXT", "auto_value_message":"TEXT",
            "fixed_value_eur":"DOUBLE PRECISION", "fixed_value_reason":"VARCHAR(255)",
            "fixed_value_at":"TIMESTAMP",
            "component_data":"TEXT", "set_condition":"DOUBLE PRECISION",
            "set_condition_label":"VARCHAR(40)", "condition_summary":"TEXT", "valuation_breakdown":"TEXT",
        }
        with db.engine.begin() as conn:
            for column, sql_type in wanted.items():
                if column not in cols:
                    conn.execute(text(f'ALTER TABLE "hardware_item" ADD COLUMN {column} {sql_type}'))

    # v1.2.2: accessories participate in automatic valuation and totals.
    inspector = inspect(db.engine)
    if "accessory_item" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("accessory_item")}
        wanted_accessory = {
            "auto_value_eur":"DOUBLE PRECISION", "auto_value_low_eur":"DOUBLE PRECISION",
            "auto_value_high_eur":"DOUBLE PRECISION", "auto_value_source":"VARCHAR(80)",
            "auto_value_updated_at":"TIMESTAMP", "auto_value_url":"TEXT",
            "auto_value_status":"VARCHAR(40)", "auto_value_message":"TEXT",
            "fixed_value_eur":"DOUBLE PRECISION", "fixed_value_reason":"VARCHAR(255)",
            "fixed_value_at":"TIMESTAMP",
            "barcode":"VARCHAR(32)", "product_code":"VARCHAR(120)",
            "category":"VARCHAR(60) DEFAULT 'other'", "compatibility":"TEXT",
            "original_product":"BOOLEAN DEFAULT TRUE", "component_kind":"VARCHAR(40) DEFAULT 'device'",
            "parent_accessory_id":"INTEGER", "included_in_parent_value":"BOOLEAN DEFAULT FALSE",
            "media_present":"BOOLEAN DEFAULT FALSE", "case_present":"BOOLEAN DEFAULT FALSE",
            "manual_present":"BOOLEAN DEFAULT FALSE", "disc_condition":"INTEGER",
        }
        with db.engine.begin() as conn:
            for column, sql_type in wanted_accessory.items():
                if column not in cols:
                    conn.execute(text(f'ALTER TABLE "accessory_item" ADD COLUMN {column} {sql_type}'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_accessory_item_barcode ON "accessory_item" (barcode)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_accessory_item_product_code ON "accessory_item" (product_code)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_accessory_item_category ON "accessory_item" (category)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_accessory_item_parent_accessory_id ON "accessory_item" (parent_accessory_id)'))

    # v0.4.2: hierarchical series metadata for external series entries.
    inspector = inspect(db.engine)
    if "series_entry" in inspector.get_table_names():
        existing_series = {c["name"] for c in inspector.get_columns("series_entry")}
        with db.engine.begin() as conn:
            if "series_group" not in existing_series:
                conn.execute(text('ALTER TABLE "series_entry" ADD COLUMN series_group VARCHAR(120)'))
            if "series_generation" not in existing_series:
                conn.execute(text('ALTER TABLE "series_entry" ADD COLUMN series_generation VARCHAR(40)'))

    # v0.7.0: richer collection goals.
    inspector = inspect(db.engine)
    if "collection_goal" in inspector.get_table_names():
        existing_goal = {c["name"] for c in inspector.get_columns("collection_goal")}
        with db.engine.begin() as conn:
            if "series_group" not in existing_goal:
                conn.execute(text('ALTER TABLE "collection_goal" ADD COLUMN series_group VARCHAR(120)'))

    # v0.5.1: friendlier account names and a hidden system owner for the shared collection.
    inspector = inspect(db.engine)
    if "user" in inspector.get_table_names():
        existing_user = {c["name"] for c in inspector.get_columns("user")}
        with db.engine.begin() as conn:
            if "display_name" not in existing_user:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN display_name VARCHAR(120)'))
            if "is_system" not in existing_user:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN is_system BOOLEAN DEFAULT FALSE NOT NULL'))
            if "role" not in existing_user:
                conn.execute(text("ALTER TABLE \"user\" ADD COLUMN role VARCHAR(20) DEFAULT 'editor' NOT NULL"))
            conn.execute(text("UPDATE \"user\" SET role = 'admin' WHERE is_admin = TRUE"))

    # v0.3.5 collection-copy details and market-value metadata.
    inspector = inspect(db.engine)
    if "collection_item" in inspector.get_table_names():
        existing_collection = {c["name"] for c in inspector.get_columns("collection_item")}
        collection_wanted = {
            "auto_value_pending_json": "TEXT",
            "ownership_format": "VARCHAR(20) DEFAULT 'physical' NOT NULL",
            "media_present": "BOOLEAN DEFAULT TRUE",
            "box_present": "BOOLEAN DEFAULT FALSE",
            "sealed": "BOOLEAN DEFAULT FALSE",
            "purchase_date": "DATE",
            "market_value_usd": "DOUBLE PRECISION",
            "market_value_source": "VARCHAR(80)",
            "market_value_updated_at": "TIMESTAMP",
            "pricecharting_product_id": "VARCHAR(80)",
            "auto_value_eur": "DOUBLE PRECISION",
            "auto_value_low_eur": "DOUBLE PRECISION",
            "auto_value_high_eur": "DOUBLE PRECISION",
            "auto_value_source": "VARCHAR(80)",
            "auto_value_condition": "VARCHAR(40)",
            "auto_value_confidence": "VARCHAR(20)",
            "auto_value_updated_at": "TIMESTAMP",
            "auto_value_url": "TEXT",
            "auto_value_status": "VARCHAR(40)",
            "auto_value_message": "TEXT",
            "fixed_value_eur": "DOUBLE PRECISION",
            "fixed_value_reason": "VARCHAR(255)",
            "fixed_value_at": "TIMESTAMP",
            "storage_location": "VARCHAR(160)",
            "tags": "TEXT",
            "play_status": "VARCHAR(30) DEFAULT 'unplayed'",
            "photo_front": "TEXT",
            "photo_back": "TEXT",
            "photo_media": "TEXT",
            "wishlist_priority": "INTEGER DEFAULT 2",
            "wishlist_target_price": "DOUBLE PRECISION",
            "wishlist_condition": "VARCHAR(40)",
            "wishlist_shop": "VARCHAR(160)",
            "wishlist_url": "TEXT",
            "wishlist_notes": "TEXT",
        }
        with db.engine.begin() as conn:
            for column, sql_type in collection_wanted.items():
                if column not in existing_collection:
                    conn.execute(text(f'ALTER TABLE "collection_item" ADD COLUMN {column} {sql_type}'))
            # v0.5.0: one collection copy per user and catalog game. Existing rows are assigned below.
            if "user_id" not in existing_collection:
                conn.execute(text('ALTER TABLE "collection_item" ADD COLUMN user_id INTEGER'))
                if db.engine.dialect.name == "postgresql":
                    conn.execute(text('ALTER TABLE "collection_item" ADD CONSTRAINT fk_collection_item_user FOREIGN KEY (user_id) REFERENCES "user" (id)'))
                    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_collection_item_user_id ON "collection_item" (user_id)'))
                    # v0.1-v0.4 used a unique game_id. Drop that constraint so every user can own the same title.
                    conn.execute(text('ALTER TABLE "collection_item" DROP CONSTRAINT IF EXISTS collection_item_game_id_key'))
                    conn.execute(text('ALTER TABLE "collection_item" DROP CONSTRAINT IF EXISTS uq_collection_item_game_id'))
                    conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_collection_game_user_idx ON "collection_item" (game_id, user_id)'))
            # Preserve the meaning of existing v0.3.4 rows that were created as CIB.
            if "box_present" not in existing_collection:
                conn.execute(text("UPDATE \"collection_item\" SET box_present = TRUE WHERE completeness = 'CIB'"))
            if "media_present" not in existing_collection:
                conn.execute(text('UPDATE "collection_item" SET media_present = TRUE'))
            # v0.6.0: multiple physical copies of the same catalog title are allowed.
            if db.engine.dialect.name == "postgresql":
                conn.execute(text('DROP INDEX IF EXISTS uq_collection_game_user_idx'))
                conn.execute(text('ALTER TABLE "collection_item" DROP CONSTRAINT IF EXISTS uq_collection_game_user'))

    # v2.3.0: shared Identify metadata for non-game Collector modules.
    inspector = inspect(db.engine)
    if "collector_item" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("collector_item")}
        collector_wanted = {
            "barcode":"VARCHAR(32)", "media_type":"VARCHAR(120)", "cover_url":"TEXT",
            "external_source":"VARCHAR(80)", "external_id":"VARCHAR(160)", "metadata_json":"TEXT",
            "edition":"VARCHAR(160)", "release_year":"INTEGER", "condition":"VARCHAR(40)",
            "completeness":"VARCHAR(40)", "auto_value_eur":"DOUBLE PRECISION",
            "auto_value_low_eur":"DOUBLE PRECISION", "auto_value_high_eur":"DOUBLE PRECISION",
            "auto_value_status":"VARCHAR(80)", "auto_value_updated_at":"TIMESTAMP WITHOUT TIME ZONE",
            "tcg_game":"VARCHAR(80)", "card_set":"VARCHAR(160)", "card_number":"VARCHAR(80)",
            "card_language":"VARCHAR(32)", "card_variant":"VARCHAR(80)", "card_rarity":"VARCHAR(120)",
            "card_grade":"VARCHAR(80)", "auto_value_source":"VARCHAR(120)",
            "fixed_value_eur":"DOUBLE PRECISION", "fixed_value_reason":"VARCHAR(255)",
            "fixed_value_at":"TIMESTAMP WITHOUT TIME ZONE",
            "purchase_date":"DATE", "storage_location":"VARCHAR(160)",
        }
        with db.engine.begin() as conn:
            for column, sql_type in collector_wanted.items():
                if column not in cols:
                    conn.execute(text(f'ALTER TABLE "collector_item" ADD COLUMN {column} {sql_type}'))
            # v2.3.1: older v2.3.0 databases used VARCHAR(60). Keep enough room for
            # future normalized media labels without failing on an existing installation.
            if db.engine.dialect.name == "postgresql":
                conn.execute(text('ALTER TABLE "collector_item" ALTER COLUMN media_type TYPE VARCHAR(120)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_collector_item_barcode ON "collector_item" (barcode)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_collector_item_tcg_game ON "collector_item" (tcg_game)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_collector_item_card_set ON "collector_item" (card_set)'))

    # Assign legacy single-user collection to the first admin (or first account).
    inspector = inspect(db.engine)
    if "collection_item" in inspector.get_table_names() and "user" in inspector.get_table_names():
        with db.engine.begin() as conn:
            owner_id = conn.execute(text('SELECT id FROM "user" ORDER BY is_admin DESC, id ASC LIMIT 1')).scalar()
            if owner_id is not None:
                conn.execute(text('UPDATE "collection_item" SET user_id = :uid WHERE user_id IS NULL'), {"uid": owner_id})

    # v3.0.9: hardware and accessories now belong to a logical collection too.
    inspector = inspect(db.engine)
    for table_name in ("hardware_item", "accessory_item"):
        if table_name not in inspector.get_table_names():
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        with db.engine.begin() as conn:
            if "user_id" not in columns:
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN user_id INTEGER'))
            conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{table_name}_user_id ON "{table_name}" (user_id)'))

    for table_name in ("collector_value_snapshot", "collection_project", "activity_log", "collection_goal"):
        inspector = inspect(db.engine)
        if table_name not in inspector.get_table_names():
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        with db.engine.begin() as conn:
            if "collection_user_id" not in columns:
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN collection_user_id INTEGER'))
            conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{table_name}_collection_user_id ON "{table_name}" (collection_user_id)'))

    # Bibo 4.0: enrich the non-destructive compatibility registry in place.
    registry_columns = {
        "bibo_work": {
            "external_source":"VARCHAR(80)", "external_id":"VARCHAR(160)",
            "logical_unit_key":"VARCHAR(320)", "availability_de":"VARCHAR(32) DEFAULT 'unknown' NOT NULL",
            "cover_url":"TEXT",
        },
        "bibo_edition": {
            "barcode":"VARCHAR(32)", "language":"VARCHAR(80)", "country":"VARCHAR(80)",
            "release_status":"VARCHAR(32) DEFAULT 'unknown' NOT NULL", "content_count":"INTEGER DEFAULT 1 NOT NULL",
        },
        "bibo_copy": {
            "purchase_price_eur":"DOUBLE PRECISION", "effective_value_eur":"DOUBLE PRECISION",
            "condition_label":"VARCHAR(80)", "completeness_label":"VARCHAR(80)",
            "storage_location":"VARCHAR(160)", "acquired_at":"DATE", "location_id":"INTEGER",
        },
        "collection_goal": {
            "priority":"INTEGER DEFAULT 2 NOT NULL", "target_budget_eur":"DOUBLE PRECISION", "target_date":"DATE",
        },
        "collection_permission": {
            "can_edit_items":"BOOLEAN", "can_manage_prices":"BOOLEAN",
            "can_run_imports":"BOOLEAN", "can_manage_users":"BOOLEAN",
        },
    }
    for table_name, wanted_columns in registry_columns.items():
        inspector = inspect(db.engine)
        if table_name not in inspector.get_table_names():
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        with db.engine.begin() as conn:
            for column, sql_type in wanted_columns.items():
                if column not in columns:
                    conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN {column} {sql_type}'))
            if table_name == "bibo_work":
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_bibo_work_logical_unit_key ON "bibo_work" (logical_unit_key)'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_bibo_work_availability_de ON "bibo_work" (availability_de)'))
            elif table_name == "bibo_edition":
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_bibo_edition_barcode ON "bibo_edition" (barcode)'))
            elif table_name == "bibo_copy":
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_bibo_copy_location_id ON "bibo_copy" (location_id)'))


def ensure_single_shared_collection():
    """Assign only genuinely unowned legacy game copies to the shared collection."""
    shared = shared_collection_user()
    if not shared:
        return
    if CollectionItem.query.filter(CollectionItem.user_id.is_(None)).update({"user_id": shared.id}, synchronize_session=False):
        db.session.commit()


def ensure_collection_spaces():
    """Create the default space and preserve all existing data and user access."""
    shared = shared_collection_user()
    if not shared:
        return
    default = CollectionSpace.query.filter_by(owner_user_id=shared.id).first()
    created_default = not default
    if created_default:
        default = CollectionSpace(name="Gemeinsam", slug="gemeinsam", owner_user_id=shared.id)
        db.session.add(default)
        db.session.flush()
        # First migration only: the former application had exactly one logical
        # inventory even if legacy rows happened to reference a real account.
        CollectionItem.query.update({"user_id": shared.id}, synchronize_session=False)
        CollectorItem.query.update({"user_id": shared.id}, synchronize_session=False)
        HardwareItem.query.update({"user_id": shared.id}, synchronize_session=False)
        AccessoryItem.query.update({"user_id": shared.id}, synchronize_session=False)
        CollectorValueSnapshot.query.update({"collection_user_id": shared.id}, synchronize_session=False)
        CollectionProject.query.update({"collection_user_id": shared.id}, synchronize_session=False)
        ActivityLog.query.update({"collection_user_id": shared.id}, synchronize_session=False)
        CollectionGoal.query.update({"collection_user_id": shared.id}, synchronize_session=False)
    if created_default:
        # Compatibility only for the one-time migration from the historical
        # single-collection setup. Newly created accounts are intentionally not
        # auto-enrolled into somebody else's collection.
        for user in User.query.filter_by(is_system=False).all():
            role = "manager" if user.is_admin else ("viewer" if user.role == "viewer" else "editor")
            db.session.add(CollectionPermission(collection_id=default.id, user_id=user.id, role=role))
    HardwareItem.query.filter(HardwareItem.user_id.is_(None)).update({"user_id": shared.id}, synchronize_session=False)
    AccessoryItem.query.filter(AccessoryItem.user_id.is_(None)).update({"user_id": shared.id}, synchronize_session=False)
    db.session.commit()


def _clone_collector_item_copy(row, *, origin_id=None, sequence=None):
    """Clone one physical Collector copy without sharing editable copy data."""
    payload = {
        column.name: getattr(row, column.name)
        for column in CollectorItem.__table__.columns
        if column.name != "id"
    }
    payload["quantity"] = 1
    meta = collector_metadata(row)
    copy_origin = origin_id or meta.get("copy_origin_id") or row.id
    try:
        copy_origin = int(copy_origin)
    except (TypeError, ValueError):
        copy_origin = int(row.id)
    meta["copy_origin_id"] = copy_origin
    if sequence is not None:
        meta["copy_sequence"] = int(sequence)
    else:
        meta.pop("copy_sequence", None)
        meta["copied_from_item_id"] = int(row.id)
    payload["metadata_json"] = json.dumps(meta, ensure_ascii=False)
    return CollectorItem(**payload)


def split_grouped_video_copies():
    """Losslessly turn legacy movie/TV quantities into editable copy rows."""
    try:
        rows = (CollectorItem.query
                .filter(CollectorItem.category.in_(["movies", "tv"]), CollectorItem.quantity > 1)
                .with_for_update()
                .order_by(CollectorItem.id)
                .all())
        created = 0
        for row in rows:
            quantity = max(1, int(row.quantity or 1))
            if quantity <= 1:
                continue
            origin_id = row.id
            meta = collector_metadata(row)
            meta["copy_origin_id"] = origin_id
            meta["copy_sequence"] = 1
            meta["copy_split_version"] = APP_VERSION
            row.metadata_json = json.dumps(meta, ensure_ascii=False)
            row.quantity = 1
            for sequence in range(2, quantity + 1):
                clone = _clone_collector_item_copy(row, origin_id=origin_id, sequence=sequence)
                clone_meta = collector_metadata(clone)
                clone_meta["copy_split_version"] = APP_VERSION
                clone.metadata_json = json.dumps(clone_meta, ensure_ascii=False)
                db.session.add(clone)
                created += 1
        if created:
            db.session.commit()
            app.logger.info("v2.15.2 split %d grouped movie/TV copies into individual Collector rows", created)
        else:
            db.session.rollback()
        return created
    except Exception:
        db.session.rollback()
        app.logger.exception("v2.15.2 movie/TV copy split failed")
        return 0


def _safe_log_url(url):
    return re.sub(r'([?&](?:key|t|token)=)[^&]+', r'\1***', str(url), flags=re.I)

def fetch_json(url, timeout=4):
    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": f"GameCollector/{APP_VERSION} (+self-hosted)"
    })
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        app.logger.warning("External lookup failed for %s: %s", _safe_log_url(url), exc)
        return None


def fetch_text(url, timeout=7):
    req = Request(url, headers={
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36 GameCollector/%s" % APP_VERSION
    })
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        app.logger.warning("External page lookup failed for %s: %s", _safe_log_url(url), exc)
        return None


def fetch_text_with_status(url, timeout=7):
    """Fetch HTML while preserving the HTTP status for expected lookup misses."""
    req = Request(url, headers={
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36 GameCollector/%s" % APP_VERSION,
    })
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace"), response.status
    except HTTPError as exc:
        if exc.code != 404:
            app.logger.warning("External page lookup failed for %s: %s", _safe_log_url(url), exc)
        return None, exc.code
    except (URLError, TimeoutError) as exc:
        app.logger.warning("External page lookup failed for %s: %s", _safe_log_url(url), exc)
        return None, None


def slugify_price_title(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


PRIXRETRO_PLATFORM_SLUGS = {
    "Nintendo Entertainment System (NES)": "nintendo-nes",
    "Super Nintendo (SNES)": "super-nintendo",
    "Nintendo 64": "nintendo-64",
    "Nintendo GameCube": "gamecube",
    "Game Boy": "game-boy",
    "Game Boy Color": "game-boy-color",
    "Game Boy Advance": "game-boy-advance",
    "Master System": "master-system",
    "Mega Drive / Genesis": "mega-drive",
    "Game Gear": "game-gear",
    "Saturn": "sega-saturn",
    "Dreamcast": "dreamcast",
    "PlayStation": "playstation",
    "PlayStation 2": "playstation-2",
    "PSP": "psp",
    "Xbox": "xbox",
}


def _plain_html(raw_html):
    text_value = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw_html, flags=re.I | re.S)
    text_value = re.sub(r"<style\b[^>]*>.*?</style>", " ", text_value, flags=re.I | re.S)
    text_value = re.sub(r"<[^>]+>", " ", text_value)
    text_value = html_lib.unescape(text_value)
    return re.sub(r"\s+", " ", text_value).strip()


def _eur_number(value):
    if not value:
        return None
    cleaned = str(value).replace("\u202f", "").replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_money_input(value):
    """Parse user-entered money values in German or international notation.

    Accepts e.g. 100,00 / 100.00 / 1.000,00 / 1,000.00.
    Empty values return None.
    """
    if value is None:
        return None
    raw = str(value).strip().replace("\u202f", "").replace("\xa0", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        # The rightmost separator is the decimal separator.
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        value = float(raw)
        return value if value >= 0 else None
    except ValueError:
        return None


def form_money(name, *, allow_empty=True):
    """Read one monetary form field consistently on every create/edit path.

    Returns (present, value, error). Empty fields deliberately clear the value.
    """
    if name not in request.form:
        return False, None, None
    raw = request.form.get(name)
    if raw is None or not str(raw).strip():
        return True, None, None
    value = parse_money_input(raw)
    if value is None:
        return True, None, f"Ungültiger Geldbetrag bei {name}: {raw}"
    return True, value, None


def update_collection_item_from_form(item):
    """Single source of truth for creating and editing CollectionItem fields."""
    errors = []
    item.status = request.form.get("status", item.status or "owned")
    ownership_format = request.form.get("ownership_format", item.ownership_format or "physical").strip().lower()
    item.ownership_format = ownership_format if ownership_format in {"physical", "digital"} else "physical"
    if item.ownership_format == "digital":
        item.media_present = item.box_present = item.manual_present = item.sealed = False
        item.completeness = "Digital"
        item.auto_value_status = "digital_excluded"
        item.auto_value_message = "Digitales Exemplar; von physischer Marktwertbewertung und Serienfortschritt ausgeschlossen."
    else:
        item.media_present = request.form.get("media_present") == "on"
        item.box_present = request.form.get("box_present") == "on"
        item.manual_present = request.form.get("manual_present") == "on"
        item.sealed = request.form.get("sealed") == "on"
        if item.sealed:
            item.media_present = item.box_present = item.manual_present = True
        item.completeness = derive_completeness(item.media_present, item.box_present, item.manual_present, item.sealed)
    item.media_condition = max(1, min(10, request.form.get("media_condition", type=int) or item.media_condition or 8))
    item.box_condition = max(1, min(10, request.form.get("box_condition", type=int) or item.box_condition or 8))

    for field in ("purchase_price", "estimated_value", "wishlist_target_price"):
        present, value, error = form_money(field)
        if error:
            errors.append(error)
        elif present:
            setattr(item, field, value)

    purchase_date_raw = request.form.get("purchase_date")
    if purchase_date_raw is not None:
        try:
            item.purchase_date = date.fromisoformat(purchase_date_raw.strip()) if purchase_date_raw.strip() else None
        except ValueError:
            errors.append("Ungültiges Kaufdatum.")

    if "market_value_usd" in request.form:
        try:
            raw_market = (request.form.get("market_value_usd") or "").strip()
            item.market_value_usd = float(raw_market) if raw_market else None
        except ValueError:
            errors.append("Ungültiger automatischer Referenzwert.")
        else:
            if item.market_value_usd is not None:
                item.market_value_source = request.form.get("market_value_source", "PriceCharting").strip() or "PriceCharting"
                item.pricecharting_product_id = request.form.get("pricecharting_product_id", "").strip() or None
                item.market_value_updated_at = utc_now()

    if "rarity" in request.form:
        item.rarity = max(1, min(5, request.form.get("rarity", type=int) or item.rarity or 1))
    for field in ("notes", "storage_location", "tags", "wishlist_condition", "wishlist_shop", "wishlist_url", "wishlist_notes"):
        if field in request.form:
            setattr(item, field, request.form.get(field, "").strip() or None)
    if "play_status" in request.form:
        item.play_status = request.form.get("play_status", "unplayed").strip() or "unplayed"
    if "work_marker" in request.form:
        item.work_marker = request.form.get("work_marker", "").strip() or None
    if "wishlist_priority" in request.form:
        item.wishlist_priority = max(1, min(3, request.form.get("wishlist_priority", type=int) or item.wishlist_priority or 2))
    return errors


def effective_value(item):
    """A deliberate price lock wins; otherwise automatic value, then estimate."""
    if str(getattr(item, "ownership_format", "physical") or "physical").lower() == "digital":
        return None
    if getattr(item, "fixed_value_eur", None) is not None:
        return float(item.fixed_value_eur)
    if item.auto_value_eur is not None:
        return float(item.auto_value_eur)
    if item.estimated_value is not None:
        return float(item.estimated_value)
    return None


def effective_value_source(item):
    if str(getattr(item, "ownership_format", "physical") or "physical").lower() == "digital":
        return None
    if getattr(item, "fixed_value_eur", None) is not None:
        return "Manuell fixiert"
    if getattr(item, "auto_value_eur", None) is not None:
        return getattr(item, "auto_value_source", None) or "Automatischer Marktwert"
    if getattr(item, "estimated_value", None) is not None:
        return "Eigene Schätzung"
    return None


def effective_hardware_value(item):
    return effective_value(item)


def effective_accessory_value(item):
    return effective_value(item)


ACCESSORY_CATEGORIES = {
    "controller": "Controller",
    "power": "Netzteil",
    "cable": "Kabel",
    "adapter": "Adapter",
    "memory": "Speicherkarte / Speichererweiterung",
    "headset": "Headset",
    "microphone": "Mikrofon",
    "camera": "Kamera / Sensor",
    "wheel": "Lenkrad / Pedale",
    "lightgun": "Lightgun",
    "dance_mat": "Tanzmatte",
    "portal": "Portal / Figurenleser",
    "stylus": "Eingabestift",
    "dock": "Dockingstation",
    "case": "Tasche / Schutzhülle",
    "drive": "Laufwerk",
    "expansion": "Hardware-Erweiterung",
    "software_disc": "Start- / Zubehör-Disc",
    "other": "Sonstiges Zubehör",
}

ACCESSORY_COMPONENT_KINDS = {
    "device": "Gerät / Hardware",
    "software_disc": "Start- / Software-Disc",
    "cable": "Kabel",
    "adapter": "Adapter",
    "receiver": "Empfänger / Sensor",
    "manual": "Anleitung",
    "other": "Sonstige Komponente",
}


def accessory_counts_in_total(item):
    """A component included in its parent set must not be valued twice."""
    return not (
        item.parent_accessory_id
        and bool(item.included_in_parent_value)
    )


def accessory_category_label(value):
    return ACCESSORY_CATEGORIES.get(value or "other", "Sonstiges Zubehör")


def format_eur(value):
    if value is None:
        return "–"
    text = f"{float(value):,.2f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def game_price_info(game):
    """Return the most useful displayed value for a catalog game in the shared collection."""
    candidates = [i for i in collection_items_for(game) if i.status == "owned" and effective_value(i) is not None]
    if not candidates:
        return None
    item = max(candidates, key=lambda i: float(effective_value(i) or 0))
    automatic = item.auto_value_eur is not None
    return {
        "value": float(effective_value(item)),
        "label": "Marktwert" if automatic else "Eigene Schätzung",
        "automatic": automatic,
        "updated_at": item.auto_value_updated_at if automatic else None,
        "item": item,
    }


RETROVIDEOSPIELE_LISTS = {
    "Game Boy": ("https://retrovideospiele.com/preislisten/gameboy-wert-von-classic-color-und-der-spiele-2018-liste/", 2020),
    "Game Boy Color": ("https://retrovideospiele.com/preislisten/gameboy-wert-von-classic-color-und-der-spiele-2018-liste/", 2020),
    "Nintendo Entertainment System (NES)": ("https://retrovideospiele.com/preislisten/nes-wert-der-spiele-und-konsole-2018-liste/", 2018),
    "Super Nintendo (SNES)": ("https://retrovideospiele.com/preislisten/super-nintendo-wert-der-spiele-und-konsole/", 2019),
    "Nintendo 64": ("https://retrovideospiele.com/preislisten/nintendo-64-wert-der-spiele-und-konsole-2018-liste/", 2018),
    "Nintendo GameCube": ("https://retrovideospiele.com/preislisten/gamecube-wert-der-spiele-und-konsole-2018-preisliste/", 2018),
    "PlayStation": ("https://retrovideospiele.com/preislisten/playstation-1-wert-der-spiele-und-konsole-preisliste/", 2019),
}
_RETROVIDEOSPIELE_CACHE = {}


def retrovideospiele_historical_lookup(game):
    """Read a historical German price-list row without using it as current valuation."""
    configured = RETROVIDEOSPIELE_LISTS.get(game.console.name)
    if not configured:
        return None, "unsupported_platform"
    url, price_year = configured
    cached = _RETROVIDEOSPIELE_CACHE.get(url)
    if cached and time.time() - cached[0] < 86400:
        raw = cached[1]
    else:
        raw, status = fetch_text_with_status(url, timeout=10)
        if not raw:
            return None, "source_unreachable"
        _RETROVIDEOSPIELE_CACHE[url] = (time.time(), raw)
    rows = []
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", raw, flags=re.I | re.S):
        cells = [_plain_html(cell).strip() for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, flags=re.I | re.S)]
        if len(cells) < 3:
            continue
        def cell_price(value):
            match = re.search(r"(\d[\d\s.,]*)\s*€", value)
            return _eur_number(match.group(1)) if match else None
        loose, boxed = cell_price(cells[1]), cell_price(cells[2])
        if loose is not None or boxed is not None:
            rows.append({"title": cells[0], "loose": loose, "boxed": boxed})
    if not rows:
        return None, "list_unreadable"
    wanted = _match_key(game.title)
    scored = sorted(((SequenceMatcher(None, wanted, _match_key(row["title"])).ratio(), row) for row in rows), reverse=True, key=lambda pair: pair[0])
    score, best = scored[0]
    if score < 0.72:
        return None, "title_not_found"
    return {**best, "year": price_year, "url": url, "source": "RetroVideoSpiele", "match_score": round(score, 2)}, "ok"


def prixretro_lookup(game):
    """Best-effort personal-use valuation from a public PrixRetro game page.

    v0.3.6.1 deliberately reports precise diagnostics instead of collapsing every
    failure into "no match". The canonical game URL is tried first; if it cannot
    be parsed, the platform catalogue is used to verify whether PrixRetro knows
    the title at all.
    """
    platform_slug = PRIXRETRO_PLATFORM_SLUGS.get(game.console.name)
    if not platform_slug:
        return None, "unsupported_platform"
    title_slug = slugify_price_title(game.title)
    if not title_slug:
        return None, "invalid_title"
    # PrixRetro publishes many GB/GBC/GBA releases under their French names.
    # Try those known regional slugs in addition to the local German/English title.
    key = _search_text(game.title)
    french_aliases = {
        "pokemon rot": ["pokemon-version-rouge", "pokemon-rouge"],
        "pokemon blau": ["pokemon-version-bleue", "pokemon-bleu"],
        "pokemon gelb": ["pokemon-version-jaune", "pokemon-jaune"],
        "pokemon gold": ["pokemon-version-or", "pokemon-or"],
        "pokemon silber": ["pokemon-version-argent", "pokemon-argent"],
        "pokemon kristall": ["pokemon-version-cristal", "pokemon-cristal"],
        "pokemon rubin": ["pokemon-version-rubis", "pokemon-rubis"],
        "pokemon saphir": ["pokemon-version-saphir", "pokemon-saphir"],
        "pokemon smaragd": ["pokemon-version-emeraude", "pokemon-emeraude"],
        "pokemon feuerrot": ["pokemon-rouge-feu", "pokemon-version-rouge-feu"],
        "pokemon blattgrun": ["pokemon-vert-feuille", "pokemon-version-vert-feuille"],
    }
    candidate_slugs = [title_slug]
    for alias_key, slugs in french_aliases.items():
        if key == alias_key or key.startswith(alias_key + " edition") or key.startswith(alias_key + " version"):
            candidate_slugs = slugs + candidate_slugs
            break
    raw = None; http_status = None; url = None
    for candidate_slug in dict.fromkeys(candidate_slugs):
        candidate_url = f"https://www.prixretro.com/{platform_slug}/jeux/{candidate_slug}"
        candidate_raw, candidate_status = fetch_text_with_status(candidate_url, timeout=9)
        if candidate_raw:
            raw, http_status, url = candidate_raw, candidate_status, candidate_url
            break
        http_status = candidate_status
    if url is None:
        url = f"https://www.prixretro.com/{platform_slug}/jeux/{title_slug}"
    title_words = [w for w in re.findall(r"[a-z0-9]+", slugify_price_title(game.title).replace("-", " ")) if len(w) > 2]

    def catalogue_contains_title():
        catalog_url = f"https://www.prixretro.com/{platform_slug}/jeux"
        catalog, catalog_status = fetch_text_with_status(catalog_url, timeout=9)
        if not catalog:
            return False, catalog_status
        cat = slugify_price_title(_plain_html(catalog)).replace("-", " ")
        return bool(title_words) and all(w in cat for w in title_words), catalog_status

    if not raw:
        if http_status == 404:
            found, _ = catalogue_contains_title()
            return None, "title_found_url_mismatch" if found else "title_not_found"
        return None, "source_unreachable"
    plain = _plain_html(raw)
    haystack = slugify_price_title(plain).replace("-", " ")
    matched = sum(1 for w in title_words if w in haystack)
    used_french_alias = any(url.endswith("/" + slug) for slug in french_aliases.get(next((k for k in french_aliases if key == k or key.startswith(k + " ")), ""), []))
    if not used_french_alias and title_words and matched < max(1, (len(title_words) + 1) // 2):
        # Check the platform catalogue. This distinguishes a bad canonical URL
        # from a title PrixRetro does not currently list.
        found, _ = catalogue_contains_title()
        if found:
            return None, "title_found_url_mismatch"
        return None, "title_not_found"

    def pick(label_pattern):
        # PrixRetro uses narrow no-break spaces and can place explanatory text
        # around the price. Limit the gap so we do not accidentally grab another
        # number from elsewhere on the page.
        m = re.search(rf"\b(?:{label_pattern})\b[^0-9€]{{0,35}}([0-9][0-9\s\u202f\xa0.,]*)\s*€", plain, flags=re.I)
        return _eur_number(m.group(1)) if m else None

    loose = pick(r"Loose")
    cib = pick(r"CIB")
    sealed = pick(r"Scell(?:é|ée|e)|Neuf")
    graded = pick(r"Grad(?:é|ée|e)")
    if not any(v is not None for v in (loose, cib, sealed, graded)):
        return None, "title_found_no_price"
    return {
        "source": "PrixRetro.com",
        "url": url,
        "currency": "EUR",
        "loose": loose,
        "cib": cib,
        "new": sealed,
        "graded": graded,
        "market": "eBay France / ventes conclues",
    }, "ok"



VGPREISE_SYSTEM_CODES = {
    "Nintendo Entertainment System (NES)": "NES",
    "Super Nintendo (SNES)": "SNES",
    "Nintendo 64": "N64",
    "Nintendo GameCube": "GC",
    "Nintendo Switch": "SWI",
    "Game Boy": "GB",
    "Game Boy Color": "GBC",
    "Game Boy Advance": "GBA",
    "Mega Drive / Genesis": "MD",
    "Game Gear": "GG",
    "Dreamcast": "DC",
    "PlayStation": "PS1",
    "Atari Jaguar": "JAG",
}

def _match_key(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).lower()
    # Common sequel notation so II / 2 and III / 3 have a chance to match.
    value = re.sub(r"\biii\b", "3", value)
    value = re.sub(r"\bii\b", "2", value)
    value = re.sub(r"\biv\b", "4", value)
    value = re.sub(r"\bvi\b", "6", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def vgpreise_lookup(game):
    """Use VGPreise's documented API as a legitimate secondary source.

    The API requires a personal auth code (VGPREISE_AUTH_CODE). We intentionally
    do not scrape their website when the API is unavailable.
    """
    system_code = VGPREISE_SYSTEM_CODES.get(game.console.name)
    if not system_code:
        return None, "vgpreise_unsupported_platform"
    auth = (os.environ.get("VGPREISE_AUTH_CODE") or "").strip()
    if not auth:
        return None, "vgpreise_not_configured"
    url = f"https://api.vgpreise.de/get/games/{quote(system_code)}?{urlencode({'auth': auth})}"
    data = fetch_json(url, timeout=10)
    if not data:
        return None, "vgpreise_source_unreachable"
    rows = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), list) else data
    if not isinstance(rows, list):
        return None, "vgpreise_invalid_response"

    target = _match_key(game.title)
    target_code = _match_key(game.product_code)
    best = None
    best_score = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "")
        alt = str(row.get("alt_title") or "")
        catalog = str(row.get("catalog_id") or "")
        title_key = _match_key(title)
        alt_key = _match_key(alt)
        if not title_key:
            continue
        if target_code and _match_key(catalog) == target_code:
            score = 1.0
        elif target == title_key:
            score = 0.99
        elif alt_key and target == alt_key:
            score = 0.97
        else:
            score = max(SequenceMatcher(None, target, title_key).ratio(),
                        SequenceMatcher(None, target, alt_key).ratio() if alt_key else 0.0)
        if score > best_score:
            best_score, best = score, row

    if not best or best_score < 0.78:
        return None, "vgpreise_title_not_found"

    def as_float(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    loose = as_float(best.get("latest_price_loose"))
    cib = as_float(best.get("latest_price_cib"))
    # If list prices are empty, ask the documented current-price endpoint.
    game_id = best.get("id")
    if game_id and loose is None and cib is None:
        purl = f"https://api.vgpreise.de/get/price/current/{quote(str(game_id))}?{urlencode({'auth': auth})}"
        pdata = fetch_json(purl, timeout=8)
        prow = pdata.get("data") if isinstance(pdata, dict) and isinstance(pdata.get("data"), dict) else pdata
        if isinstance(prow, list) and prow:
            prow = prow[0]
        if isinstance(prow, dict):
            loose = as_float(prow.get("average_price_loose"))
            cib = as_float(prow.get("average_price_cib"))
    if loose is None and cib is None:
        return None, "vgpreise_title_found_no_price"

    detail_url = f"https://www.vgpreise.de/gameslist/game/{game_id}" if game_id else "https://www.vgpreise.de/"
    return {
        "source": "VGPreise.de",
        "url": detail_url,
        "currency": "EUR",
        "loose": loose,
        "cib": cib,
        "new": None,
        "graded": None,
        "market": "europäischer Markt / VGPreise",
        "match_score": round(best_score, 3),
    }, "ok"

def value_kind_for_item(item):
    comp = derive_completeness(item.media_present, item.box_present, item.manual_present, item.sealed)
    if item.sealed:
        return "new", comp
    if item.media_present and item.box_present and item.manual_present:
        return "cib", comp
    if item.media_present and not item.box_present and not item.manual_present:
        return "loose", comp
    return "derived", comp


def condition_factor(item):
    scores = []
    if item.media_present and item.media_condition:
        scores.append(item.media_condition)
    if item.box_present and item.box_condition:
        scores.append(item.box_condition)
    score = sum(scores) / len(scores) if scores else 8
    return max(0.65, min(1.10, 0.60 + 0.05 * score))


def valuation_from_prices(item, prices):
    if not prices:
        return None
    kind, comp = value_kind_for_item(item)
    # PrixRetro is a strong market reference, but this adapter matches by title/platform
    # and the public page may default to the French/PAL-FRA market. Keep confidence conservative.
    confidence = "mittel"
    base = None
    if kind == "new":
        base = prices.get("new")
    elif kind == "cib":
        base = prices.get("cib")
    elif kind == "loose":
        base = prices.get("loose")
    else:
        loose, cib = prices.get("loose"), prices.get("cib")
        if item.media_present and item.box_present and not item.manual_present and cib:
            base = cib * 0.78
        elif item.media_present and item.manual_present and not item.box_present and cib:
            base = cib * 0.58
        elif not item.media_present and item.box_present and item.manual_present and cib:
            base = cib * 0.62
        elif item.box_present and cib:
            base = cib * 0.45
        elif item.manual_present and cib:
            base = cib * 0.22
        elif loose:
            base = loose
        confidence = "niedrig"
    if base is None:
        return None
    value = round(base * condition_factor(item), 2)
    spread = 0.18 if confidence == "mittel" else 0.25
    return {
        "value": value,
        "low": round(value * (1 - spread), 2),
        "high": round(value * (1 + spread), 2),
        "condition": comp,
        "confidence": confidence,
    }


def game_price_jump_pending(item, valuation, prices, now):
    """Hold substantial changes until an independent later-day check agrees."""
    previous = item.auto_value_eur
    candidate = float(valuation["value"])
    if not (0 < candidate < float("inf")):
        item.auto_value_status = "invalid_price"
        item.auto_value_message = "Ungültiger Preis; bisheriger Marktwert bleibt erhalten."
        return True
    condition = valuation.get("condition")
    # A user changing completeness legitimately changes the price basis.
    same_basis = not item.auto_value_condition or item.auto_value_condition == condition
    if previous is None or not same_basis or abs(candidate - previous) < max(15.0, abs(previous) * .25):
        item.auto_value_pending_json = None
        return False
    context = [prices.get("source"), condition, item.media_condition, item.box_condition,
               item.game_id, item.game.region, item.game.edition]
    try:
        pending = json.loads(item.auto_value_pending_json or "{}")
        first_seen = datetime.fromisoformat(pending.get("first_seen", ""))
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        age = now - first_seen
        confirmed = (pending.get("context") == context
                     and timedelta(hours=24) <= age <= timedelta(days=7)
                     and abs(candidate - float(pending["value"])) <= float(pending["value"]) * .10)
        if confirmed:
            item.auto_value_pending_json = None
            return False
        # Repeated clicks cannot accelerate confirmation or postpone the first check.
        same_pending = (pending.get("context") == context and age <= timedelta(days=7)
                        and abs(candidate - float(pending["value"])) <= float(pending["value"]) * .10)
    except (ValueError, TypeError, KeyError, AttributeError):
        same_pending = False
    if not same_pending:
        item.auto_value_pending_json = json.dumps({"value": candidate, "context": context,
                                                   "first_seen": now.isoformat()})
    item.auto_value_status = "price_jump_pending"
    item.auto_value_message = (f"Preissprung zur Prüfung: {candidate:.2f} € statt {previous:.2f} €. "
                               "Bisheriger Wert bleibt erhalten; Bestätigung durch einen passenden "
                               "erneuten Abruf frühestens nach 24 Stunden erforderlich.")
    return True


def store_auto_valuation(item, valuation, prices, run=None):
    now = utc_now()
    if game_price_jump_pending(item, valuation, prices, now):
        return False
    previous = item.auto_value_eur
    new_value = float(valuation["value"])
    item.auto_value_eur = new_value
    item.auto_value_low_eur = valuation["low"]
    item.auto_value_high_eur = valuation["high"]
    item.auto_value_source = prices.get("source")
    item.auto_value_condition = valuation.get("condition")
    item.auto_value_confidence = valuation.get("confidence")
    item.auto_value_updated_at = now
    item.auto_value_url = prices.get("url")

    # v0.8.1: keep a complete activity feed. PriceHistory remains the compact
    # change-only curve, while PriceActivity also records unchanged checks.
    if previous is None:
        change_type, delta = "new", 0.0
    else:
        delta = round(new_value - float(previous), 2)
        change_type = "up" if delta > 0 else "down" if delta < 0 else "same"
    db.session.add(PriceActivity(
        collection_item=item,
        revaluation_run_id=run.id if run is not None else None,
        previous_value_eur=float(previous) if previous is not None else None,
        value_eur=new_value, delta_eur=delta, change_type=change_type,
        source=prices.get("source") or "unknown", recorded_at=now,
    ))

    # Preserve user's manual estimated_value. Automatic values live separately.
    last = (PriceHistory.query.filter_by(collection_item_id=item.id)
            .order_by(PriceHistory.recorded_at.desc()).first()) if item.id else None
    if not last or last.value_eur != new_value or last.source != prices.get("source"):
        db.session.add(PriceHistory(
            collection_item=item, value_eur=new_value, low_eur=valuation["low"],
            high_eur=valuation["high"], source=prices.get("source") or "unknown",
            condition=valuation.get("condition"), confidence=valuation.get("confidence"),
            source_url=prices.get("url"), recorded_at=now,
        ))

    return True

def game_offer_matches_completeness(item, title, condition=""):
    """Use direct comparisons; never multiply mixed loose/CIB/sealed prices."""
    key = _match_key(title)
    tokens = set(key.split())
    if tokens & {"defekt", "defective", "repro", "reproduction", "nachbau", "replica",
                 "graded", "vga", "wata", "psa", "cgc", "falschung", "fake", "bootleg"}:
        return False
    if any(x in key for x in ("nur ovp", "ovp only", "box only", "manual only", "nur anleitung",
                              "ohne spiel", "ohne modul", "no game", "not working", "ungetestet")):
        return False
    sealed = bool(tokens & {"sealed", "versiegelt", "verschweisst", "ungeoffnet"})
    sealed = sealed or "brand new" in _match_key(condition) or _match_key(condition) == "neu"
    boxed = bool(tokens & {"ovp", "cib", "komplett", "complete", "boxed"})
    if any(x in key for x in ("ohne ovp", "ohne box", "no box", "without box")):
        boxed = False
    manual = bool(tokens & {"anleitung", "manual", "cib", "komplett", "complete"})
    if any(x in key for x in ("ohne anleitung", "ohne manual", "no manual", "without manual", "keine anleitung")):
        manual = False
    kind, _ = value_kind_for_item(item)
    if kind == "new":
        return sealed
    if sealed:
        return False
    if kind == "cib":
        return boxed and manual
    loose = bool(tokens & {"loose", "loses", "lose"}) or any(
        phrase in key for phrase in ("nur modul", "modul only", "cartridge only", "disc only",
                                    "nur spiel", "game only", "ohne ovp", "ohne box", "no box"))
    if kind == "loose":
        return loose and not boxed and not manual
    # Incomplete copies need positive evidence for every included component.
    absent_manual = any(x in key for x in ("ohne anleitung", "ohne manual", "no manual", "without manual", "keine anleitung"))
    absent_box = any(x in key for x in ("ohne ovp", "ohne box", "no box", "without box"))
    if (not boxed and not manual) or (boxed and not manual and not absent_manual) or (manual and not boxed and not absent_box):
        return False
    return (bool(item.media_present) and boxed == bool(item.box_present)
            and manual == bool(item.manual_present))


def ebay_offer_valuation(item):
    """Estimate a value from current fixed-price eBay offers, never from claimed sold prices."""
    credentials = ebay_credentials()
    if not credentials["client_id"] or not credentials["client_secret"]:
        return None, None, "ebay_not_configured"
    queries = []
    if item.game.barcode:
        queries.append(item.game.barcode)
    if item.game.product_code:
        queries.append(item.game.product_code)
    queries.append(" ".join(x for x in (item.game.title, item.game.console.name, item.game.edition) if x and x != "Standard"))
    franchise = canonical_franchise_name(item.game.franchise or infer_franchise_name(item.game.title) or "")
    canonical_title = canonical_series_item_key(franchise, item.game.title) if franchise else normalize_series_title(item.game.title)
    if canonical_title and _search_text(canonical_title) != _search_text(item.game.title):
        queries.append(f"{canonical_title} {item.game.console.name}")
    # Try curated regional titles as independent searches (e.g. German FIFA,
    # Disney and Sims names) before declaring a difficult item unvalued.
    for row in CURATED_SERIES.get(franchise, []):
        if canonical_series_item_key(franchise, row["title"]) == canonical_series_item_key(franchise, item.game.title):
            for alias in row.get("aliases", [])[:3]:
                candidate = f"{alias} {item.game.console.name}"
                if candidate not in queries:
                    queries.append(candidate)
            break
    found = []
    status = "ok"
    for query in queries:
        rows, status = ebay_search_items(query, limit=50)
        found.extend(rows)
        # Search every identifier/alias; a broad early hit count is not evidence
        # of enough comparable copies.
    if not found:
        return None, None, status if status != "ok" else "ebay_no_results"
    found = ebay_enrich_candidates(found, limit=6)

    unwanted = {"bundle", "konvolut", "sammlung", "lot", "download", "digital", "account", "konto",
                "cover only", "nur hülle", "nur huelle", "empty case", "replacement case"}
    game_words = {w for w in _match_key(item.game.title).split() if len(w) > 2}
    values = []
    seen = set()
    for row in found:
        if row["id"] in seen or row.get("currency") != "EUR" or row.get("price") is None:
            continue
        seen.add(row["id"])
        title_key = _match_key(row.get("name"))
        title_tokens = set(title_key.split())
        if any((term in title_tokens) if " " not in term else (term in title_key) for term in unwanted):
            continue
        matched = sum(1 for word in game_words if word in title_key.split())
        if game_words and matched < len(game_words):
            continue
        if not game_offer_matches_completeness(item, row.get("name", ""), row.get("condition", "")):
            continue
        total = float(row["price"]) + float(row.get("shipping") or 0)
        if 0.5 <= total <= 5000:
            values.append(total)
    if len(values) < 5:
        return None, None, "ebay_too_few_results"

    center = statistics.median(values)
    values = [v for v in values if center * 0.55 <= v <= center * 1.80]
    if len(values) >= 4:
        ordered = sorted(values)
        half = len(ordered) // 2
        q1 = statistics.median(ordered[:half])
        q3 = statistics.median(ordered[-half:])
        iqr = q3 - q1
        if iqr > 0:
            trimmed = [v for v in ordered if q1 - 1.5 * iqr <= v <= q3 + 1.5 * iqr]
            if len(trimmed) >= 5:
                values = trimmed
    if len(values) < 5:
        return None, None, "ebay_too_few_results"

    kind, completeness = value_kind_for_item(item)
    completeness_factor = 1.0  # Offers already match this copy's completeness.
    value = round(statistics.median(values) * completeness_factor * condition_factor(item), 2)
    low = round(min(values) * completeness_factor * condition_factor(item), 2)
    high = round(max(values) * completeness_factor * condition_factor(item), 2)
    confidence = "mittel" if len(values) >= 6 else ("niedrig" if len(values) >= 3 else "vorläufig")
    prices = {
        "source": "eBay-Angebote", "url": f"https://www.ebay.de/sch/i.html?{urlencode({'_nkw': queries[-1]})}",
        "market": "aktive Festpreisangebote gleicher Vollständigkeit", "offer_count": len(values),
    }
    valuation = {"value": value, "low": low, "high": high, "condition": completeness, "confidence": confidence}
    return valuation, prices, "ok"


VALUATION_STATUS_MESSAGES = {
    "unsupported_platform": "PrixRetro unterstützt diese Plattform derzeit nicht.",
    "no_automatic_price_source": "Für diese Plattform ist derzeit keine automatische Preisquelle verfügbar. Ein manueller Schätzwert kann weiterhin gepflegt werden.",
    "invalid_title": "Der Titel kann nicht für die Preissuche aufbereitet werden.",
    "source_unreachable": "PrixRetro war vom GameCollector-Container aus nicht erreichbar oder hat die Anfrage abgewiesen.",
    "title_not_found": "Titel wurde bei PrixRetro für diese Plattform nicht gefunden.",
    "title_found_url_mismatch": "Titel ist im PrixRetro-Katalog vorhanden, die Detailseite konnte aber nicht eindeutig zugeordnet werden.",
    "title_found_no_price": "Titel wurde bei PrixRetro gefunden, aber es konnte kein Loose/CIB/Sealed-Preis sicher gelesen werden.",
    "condition_price_missing": "Titel wurde gefunden, aber für die Vollständigkeit deiner Kopie fehlt ein passender Preis.",
    "vgpreise_not_configured": "PrixRetro hatte keinen Treffer. VGPreise ist verfügbar, benötigt aber deinen persönlichen API-Auth-Code.",
    "vgpreise_unsupported_platform": "Auch VGPreise unterstützt diese Plattform derzeit nicht über die angebundene API.",
    "vgpreise_source_unreachable": "VGPreise API war nicht erreichbar oder der Auth-Code wurde abgewiesen.",
    "vgpreise_invalid_response": "VGPreise hat eine unerwartete API-Antwort geliefert.",
    "vgpreise_title_not_found": "Titel wurde auch bei VGPreise nicht eindeutig gefunden.",
    "vgpreise_title_found_no_price": "Titel wurde bei VGPreise gefunden, aber aktuell fehlt ein Loose/CIB-Preis.",
    "ebay_not_configured": "eBay ist noch nicht im Nutzermanagement konfiguriert.",
    "ebay_auth_failed": "eBay hat die hinterlegten Zugangsdaten abgewiesen.",
    "ebay_api_denied": "Die eBay Browse API ist für diese Anwendung noch nicht freigeschaltet.",
    "ebay_unreachable": "eBay war vorübergehend nicht erreichbar.",
    "ebay_no_results": "eBay hat keine passenden aktiven Angebote geliefert.",
    "ebay_too_few_results": "Weniger als fünf vergleichbare eBay-Angebote; kein neuer eBay-Wert übernommen.",
}

def auto_value_item(item, run=None):
    if str(getattr(item, "ownership_format", "physical") or "physical").lower() == "digital":
        item.auto_value_status = "digital_excluded"
        item.auto_value_message = "Digitales Exemplar; von der physischen Marktwertbewertung ausgeschlossen."
        return False, "Digital ausgeschlossen"
    if not game_is_physical_candidate(item.game):
        item.auto_value_status = "non_physical_excluded"
        item.auto_value_message = "Nicht physisch veröffentlicht; von automatischer Bewertung und Serienfortschritt ausgeschlossen."
        return False, "Nicht physisch"
    # v2.0.1 source priority: 1) eBay Browse API, 2) PrixRetro, 3) PriceCharting, 4) VGPreise.
    ebay_valuation, ebay_prices, ebay_status = ebay_offer_valuation(item)
    if ebay_valuation:
        if not store_auto_valuation(item, ebay_valuation, ebay_prices, run=run):
            return False, item.auto_value_status
        item.auto_value_status = "ok"
        prefix = "Primärwert gleicher Vollständigkeit"
        item.auto_value_message = f"{prefix} aus {ebay_prices.get('offer_count')} plausiblen eBay-Festpreisangeboten; Details geeigneter Treffer wurden mit getItem geprüft."
        return True, "eBay-Angebote"

    prix_prices, prix_status = prixretro_lookup(item.game)
    if prix_prices:
        valuation = valuation_from_prices(item, prix_prices)
        if valuation:
            if not store_auto_valuation(item, valuation, prix_prices, run=run):
                return False, item.auto_value_status
            item.auto_value_status = "ok"
            item.auto_value_message = "Automatisch bewertet über PrixRetro.com (Fallback nach eBay)."
            return True, "PrixRetro.com"
        prix_status = "condition_price_missing"

    vg_prices, vg_status = vgpreise_lookup(item.game)
    if vg_prices:
        valuation = valuation_from_prices(item, vg_prices)
        if valuation:
            if not store_auto_valuation(item, valuation, vg_prices, run=run):
                return False, item.auto_value_status
            item.auto_value_status = "ok"
            item.auto_value_message = "Automatisch bewertet über VGPreise.de (Fallback nach PrixRetro)."
            return True, "VGPreise.de"
        vg_status = "condition_price_missing"

    # v0.7.1: distinguish an unavailable platform source from a failed lookup.
    # If neither configured source supports the platform, this is not a data/error
    # condition and is presented as a neutral availability state.
    if ebay_status not in (None, "ebay_not_configured"):
        status = ebay_status
    elif prix_status == "unsupported_platform" and vg_status == "vgpreise_unsupported_platform":
        status = "no_automatic_price_source"
    else:
        status = vg_status if vg_status not in (None, "vgpreise_unsupported_platform") else prix_status
        if vg_status == "vgpreise_not_configured" and prix_status not in ("unsupported_platform", None):
            status = "vgpreise_not_configured"
    item.auto_value_status = status
    prix_msg = VALUATION_STATUS_MESSAGES.get(prix_status, prix_status or "")
    vg_msg = VALUATION_STATUS_MESSAGES.get(vg_status, vg_status or "")
    ebay_msg = VALUATION_STATUS_MESSAGES.get(ebay_status, ebay_status or "")
    if status == "no_automatic_price_source":
        item.auto_value_message = VALUATION_STATUS_MESSAGES[status]
    elif ebay_status not in (None, "ebay_not_configured"):
        item.auto_value_message = f"PrixRetro: {prix_msg} VGPreise: {vg_msg} eBay: {ebay_msg}"
    elif prix_status and vg_status and vg_status != "vgpreise_unsupported_platform":
        item.auto_value_message = f"PrixRetro: {prix_msg} VGPreise: {vg_msg}"
    else:
        item.auto_value_message = VALUATION_STATUS_MESSAGES.get(status, "Kein sicherer automatischer Preis ermittelt.")
    item.auto_value_updated_at = utc_now()
    return False, status

def infer_game_platform(*values):
    """Best-effort platform detection from generic product titles/categories."""
    text_value = " ".join(str(v or "") for v in values).lower()
    aliases = [
        (("xbox series x", "xbox series s", "series x|s", "series x/s"), "Xbox Series X|S"),
        (("xbox one",), "Xbox One"),
        (("xbox 360",), "Xbox 360"),
        (("playstation 5", "ps5"), "PlayStation 5"),
        (("playstation 4", "ps4"), "PlayStation 4"),
        (("playstation 3", "ps3"), "PlayStation 3"),
        (("playstation 2", "ps2"), "PlayStation 2"),
        (("nintendo switch 2", "switch 2"), "Nintendo Switch 2"),
        (("nintendo switch", "switch"), "Nintendo Switch"),
        (("wii u",), "Wii U"),
        (("nintendo wii", " wii "), "Wii"),
        (("nintendo 3ds", "3ds"), "Nintendo 3DS"),
        (("nintendo ds",), "Nintendo DS"),
        (("dreamcast",), "Dreamcast"),
        (("gamecube",), "Nintendo GameCube"),
    ]
    padded = f" {text_value} "
    for needles, platform in aliases:
        if any(n in padded for n in needles):
            return platform
    return "Unbekannt"


def lookup_upcitemdb(code):
    """Lookup an EAN/UPC using UPCitemdb's keyless trial API."""
    url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={quote(code)}"
    data = fetch_json(url)
    if not isinstance(data, dict):
        return []
    rows = data.get("items") or []
    if not isinstance(rows, list):
        return []
    results = []
    for row in rows[:6]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("title") or "").strip()
        if not name:
            continue
        images = row.get("images") or []
        cover_url = images[0] if isinstance(images, list) and images else ""
        category = str(row.get("category") or "").strip()
        brand = str(row.get("brand") or "").strip()
        platform = infer_game_platform(name, category, brand)
        results.append({
            "name": name,
            "platform": platform,
            "barcode": clean_barcode(row.get("ean") or row.get("upc") or code),
            "region": "PAL",
            "source": "UPCitemdb",
            "source_id": str(row.get("ean") or row.get("upc") or code),
            "publisher": brand,
            "cover_url": str(cover_url or "").strip(),
            "category": category,
        })
    return results


def lookup_barcodefinder(code):
    """Second barcode provider. Supports the current no-key BarcodeFinder endpoint."""
    urls = [
        f"https://www.barcodefinder.info/v1/product/{quote(code)}",
        f"https://api.barcodefinder.info/barcode/{quote(code)}",
    ]
    for url in urls:
        data = fetch_json(url)
        if not isinstance(data, dict):
            continue
        product = data.get("product") if isinstance(data.get("product"), dict) else data
        name = str(product.get("title") or product.get("name") or "").strip()
        if not name:
            continue
        images = product.get("images") or []
        cover_url = images[0] if isinstance(images, list) and images else ""
        brand = str(product.get("brand") or "").strip()
        category = str(product.get("category") or "").strip()
        return [{
            "name": name,
            "platform": infer_game_platform(name, category, brand),
            "barcode": code,
            "region": "PAL",
            "source": "BarcodeFinder",
            "source_id": code,
            "publisher": brand,
            "cover_url": str(cover_url or "").strip(),
            "category": category,
        }]
    return []


def lookup_barcode_external(code):
    """Lookup EAN/UPC using resilient, swappable providers.

    Default order: UPCitemdb -> BarcodeFinder. A custom BARCODE_LOOKUP_URL can
    still be supplied for an additional legacy/provider endpoint.
    """
    results = lookup_upcitemdb(code)
    if results:
        return results

    results = lookup_barcodefinder(code)
    if results:
        return results

    template = os.environ.get("BARCODE_LOOKUP_URL", "").strip()
    if template:
        url = template.format(barcode=quote(code))
        data = fetch_json(url)
        if isinstance(data, list):
            legacy = []
            for row in data[:12]:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or row.get("title") or "").strip()
                if not name:
                    continue
                legacy.append({
                    "name": name,
                    "platform": str(row.get("platform") or "Unbekannt").strip(),
                    "barcode": clean_barcode(row.get("EAN") or row.get("ean") or code),
                    "region": str(row.get("regionInfo") or row.get("region") or "PAL").upper(),
                    "source": str(row.get("source") or "Custom Provider").strip(),
                    "source_id": str(row.get("sourceID") or row.get("id") or "").strip(),
                    "publisher": str(row.get("publisher") or row.get("brand") or "").strip(),
                    "cover_url": str(row.get("cover_url") or row.get("image") or "").strip(),
                    "category": str(row.get("category") or "").strip(),
                })
            return legacy
    return []


def ensure_default_consoles():
    """Seed the canonical platform list."""
    changed = False
    existing = {c.name.casefold(): c for c in Console.query.all()}
    for name, manufacturer in DEFAULT_CONSOLES:
        if name.casefold() not in existing:
            db.session.add(Console(name=name, manufacturer=manufacturer))
            changed = True
    if changed:
        db.session.commit()


def _console_merge_conflicts(source, target):
    """Return game variants that would violate the catalog uniqueness constraint."""
    target_variants = {
        (g.title, g.region or "", g.edition or ""): g
        for g in Game.query.filter_by(console_id=target.id).all()
    }
    conflicts = []
    for game in Game.query.filter_by(console_id=source.id).all():
        other = target_variants.get((game.title, game.region or "", game.edition or ""))
        if other:
            conflicts.append((game, other))
    return conflicts


def merge_console_into(source, target):
    """Move every dependent record from source to target and remove source."""
    conflicts = _console_merge_conflicts(source, target)
    if conflicts:
        return False, conflicts
    Game.query.filter_by(console_id=source.id).update(
        {Game.console_id: target.id}, synchronize_session=False
    )
    HardwareModel.query.filter_by(console_id=source.id).update(
        {HardwareModel.console_id: target.id}, synchronize_session=False
    )
    AccessoryItem.query.filter_by(console_id=source.id).update(
        {AccessoryItem.console_id: target.id}, synchronize_session=False
    )
    CollectionGoal.query.filter_by(console_id=source.id).update(
        {CollectionGoal.console_id: target.id}, synchronize_session=False
    )
    if not target.manufacturer and source.manufacturer:
        target.manufacturer = source.manufacturer
    db.session.delete(source)
    db.session.flush()
    return True, []


def normalize_existing_consoles():
    """Safely merge known aliases already present in older databases.

    A merge is skipped rather than guessing if an identical catalog variant exists
    on both platforms. Such cases can be resolved explicitly in the admin UI.
    """
    changed = False
    for source in list(Console.query.order_by(Console.id).all()):
        canonical = canonical_console_name(source.name)
        if canonical.casefold() == source.name.casefold():
            continue
        target = Console.query.filter(db.func.lower(Console.name) == canonical.lower()).first()
        if not target or target.id == source.id:
            continue
        conflicts = _console_merge_conflicts(source, target)
        # Alias rows can contain the same catalog variant as the canonical row.
        # Preserve every physical copy, fill empty master metadata, then remove only
        # the redundant catalog master before moving the remaining variants.
        for duplicate, canonical_game in conflicts:
            for field in (
                "language", "release_year", "publisher", "developer", "genre", "franchise",
                "franchise_source", "series_group", "series_generation", "barcode", "product_code",
                "cover_url", "external_source", "external_id",
            ):
                if not getattr(canonical_game, field, None) and getattr(duplicate, field, None):
                    setattr(canonical_game, field, getattr(duplicate, field))
            if canonical_game.series_status == "unreviewed" and duplicate.series_status != "unreviewed":
                canonical_game.series_status = duplicate.series_status
            CollectionItem.query.filter_by(game_id=duplicate.id).update(
                {CollectionItem.game_id: canonical_game.id}, synchronize_session=False
            )
            DuplicateIgnore.query.filter(
                db.or_(DuplicateIgnore.game_a_id == duplicate.id, DuplicateIgnore.game_b_id == duplicate.id)
            ).delete(synchronize_session=False)
            db.session.delete(duplicate)
            db.session.flush()
        ok, remaining_conflicts = merge_console_into(source, target)
        if ok:
            app.logger.info("Merged console alias %s -> %s", source.name, target.name)
            changed = True
        else:
            app.logger.warning(
                "Skipped console alias merge %s -> %s because %d catalog variants conflict",
                source.name, target.name, len(remaining_conflicts)
            )
    if changed:
        db.session.commit()


def upcitemdb_title_search(query, limit=8):
    """Reverse product-name lookup used as a keyless fallback after barcode misses."""
    params = urlencode({"s": query})
    data = fetch_json(f"https://api.upcitemdb.com/prod/trial/search?{params}")
    if not isinstance(data, dict):
        return []
    rows = data.get("items") or []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        images = row.get("images") or []
        brand = str(row.get("brand") or "").strip()
        category = str(row.get("category") or "").strip()
        out.append({
            "name": title,
            "platform": infer_game_platform(title, category, brand),
            "year": "",
            "publisher": brand,
            "developer": "",
            "genre": category,
            "cover_url": images[0] if isinstance(images, list) and images else "",
            "source": "UPCitemdb Search",
            "source_id": str(row.get("ean") or row.get("upc") or ""),
        })
    return out


def _search_text(value):
    value = str(value or "").replace("ß", "ss")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    return re.sub(r"\s+", " ", value)



SERIES_RULES = [
    # LEGO is an umbrella franchise. Sub-series such as LEGO Star Wars remain
    # available through series_group, but all LEGO titles belong to LEGO.
    (r"^lego(?:\s|$)", "LEGO"),
    (r"^(?:f1|formula\s+(?:1|one))(?:\s|$)", "Formula 1 / F1"),
    (r"^call of duty\b", "Call of Duty"),
    (r"^(?:(?:ea sports|fifa)\s+)?(?:fussball|fußball)\s+manager\b|^fifa\s+manager\b", "Fußball Manager"),
    (r"^(ea sports )?fc\b", "EA Sports FC"),
    (r"^fifa\b", "FIFA"),
    (r"^pokemon\b|^pokémon\b", "Pokémon"),
    (r"^super mario\b", "Super Mario"),
    (r"^mario kart\b", "Mario Kart"),
    (r"^(the )?legend of zelda\b", "The Legend of Zelda"),
    (r"^grand theft auto\b|^gta\b", "Grand Theft Auto"),
    (r"^assassin'?s creed\b", "Assassin's Creed"),
    (r"^need for speed\b", "Need for Speed"),
    (r"^battlefield\b", "Battlefield"),
    (r"^halo\b", "Halo"),
    (r"^forza horizon\b", "Forza"),
    (r"^forza motorsport\b", "Forza"),
    (r"^forza\b", "Forza"),
    (r"^microsoft flight simulator\b|^microsoft flight sim\b", "Microsoft Flight Simulator"),
    (r"^singstar\b", "SingStar"),
    (r"^resident evil\b", "Resident Evil"),
    (r"^final fantasy\b", "Final Fantasy"),
    (r"^gran turismo\b", "Gran Turismo"),
    (r"^god of war\b", "God of War"),
    (r"^uncharted\b", "Uncharted"),
    (r"^sonic\b", "Sonic"),
    (r"^mortal kombat\b", "Mortal Kombat"),
    (r"^tekken\b", "Tekken"),
    (r"^street fighter\b", "Street Fighter"),
    (r"^tomb raider\b", "Tomb Raider"),
    (r"^far cry\b", "Far Cry"),
    (r"^fallout\b", "Fallout"),
    (r"^(the )?elder scrolls\b", "The Elder Scrolls"),
    (r"^doom\b", "DOOM"),
    (r"^wolfenstein\b", "Wolfenstein"),
    (r"^diablo\b", "Diablo"),
    (r"^warcraft\b", "Warcraft"),
    (r"^starcraft\b", "StarCraft"),
    (r"^(?:the|die) sims\b", "The Sims"),
    (r"^mysims\b", "The Sims"),
    (r"^metroid\b", "Metroid"),
    (r"^kirby\b", "Kirby"),
    (r"^donkey kong\b", "Donkey Kong"),
    (r"^animal crossing\b", "Animal Crossing"),
    (r"^fire emblem\b", "Fire Emblem"),
    (r"^splatoon\b", "Splatoon"),
    (r"^yoshi\b", "Yoshi"),
    (r"^luigi'?s mansion\b", "Luigi's Mansion"),
]


def infer_franchise_name(title):
    value = str(title or "").strip()
    lower = value.lower()
    for pattern, name in SERIES_RULES:
        if re.search(pattern, lower, flags=re.I):
            return name
    # Conservative generic fallback: only split at a subtitle separator.
    # This avoids turning unrelated numbered games into fake series.
    if ":" in value:
        prefix = value.split(":", 1)[0].strip()
        if 3 <= len(prefix) <= 60 and len(prefix.split()) >= 2:
            return prefix
    return None


LEGO_GROUP_RULES = [
    (r"^lego\s+star wars\b", "LEGO Star Wars"),
    (r"^lego\s+batman\b", "LEGO Batman"),
    (r"^lego\s+harry potter\b", "LEGO Harry Potter"),
    (r"^lego\s+(?:marvel|marvel's)\b", "LEGO Marvel"),
    (r"^lego\s+indiana jones\b", "LEGO Indiana Jones"),
    (r"^lego\s+jurassic\b", "LEGO Jurassic World"),
    (r"^lego\s+(?:the )?hobbit\b", "LEGO The Hobbit"),
    (r"^lego\s+(?:the )?lord of the rings\b", "LEGO The Lord of the Rings"),
    (r"^lego\s+city\b", "LEGO City"),
    (r"^lego\s+ninjago\b", "LEGO Ninjago"),
    (r"^lego\s+dimensions\b", "LEGO Dimensions"),
]

def infer_lego_series_group(title):
    value = str(title or "").strip().lower()
    for pattern, name in LEGO_GROUP_RULES:
        if re.search(pattern, value, flags=re.I):
            return name
    return None

def repair_lego_franchise_metadata():
    """Safe, idempotent v1.0.1 repair for existing LEGO catalogue entries.

    Auto/unassigned titles are normalized to the LEGO umbrella franchise.
    Manual franchise assignments are preserved; the LEGO detail page still
    includes them by title so no manually curated metadata is destroyed.
    """
    changed = 0
    games = Game.query.filter(Game.title.ilike("LEGO %")).all()
    for game in games:
        group = infer_lego_series_group(game.title)
        if group and not game.series_group:
            game.series_group = group
            changed += 1
        if not game.franchise or game.franchise_source != "manual":
            if game.franchise != "LEGO" or game.series_status != "series":
                game.franchise = "LEGO"
                game.franchise_source = "auto-rule"
                game.series_status = "series"
                changed += 1
    if changed:
        db.session.commit()
    return changed


# v1.0.2: Series Logic 2.0 -------------------------------------------------
# Series pages must reconcile a physical local collection with metadata from
# external catalogues. Exact RAWG IDs remain strongest, but localized titles
# and platform aliases are normalized as a safe secondary signal.
SERIES_TITLE_REPLACEMENTS = {
    " die komplette saga": " the complete saga",
    " komplette saga": " the complete saga",
    " der hobbit": " the hobbit",
    " herr der ringe": " lord of the rings",
    " die sims": " the sims",
}

PHYSICAL_PLATFORM_ALIASES = {
    "playstation": "ps1", "playstation 1": "ps1", "ps1": "ps1",
    "playstation 2": "ps2", "ps2": "ps2",
    "playstation 3": "ps3", "ps3": "ps3",
    "playstation 4": "ps4", "ps4": "ps4",
    "playstation 5": "ps5", "ps5": "ps5",
    "xbox": "xbox", "original xbox": "xbox",
    "xbox 360": "xbox360", "x360": "xbox360",
    "xbox one": "xboxone", "xone": "xboxone",
    "xbox series x s": "xboxseries", "xbox series x": "xboxseries", "xbox series s": "xboxseries",
    "nintendo switch": "switch", "switch": "switch",
    "nintendo ds": "nds", "ds": "nds",
    "nintendo 3ds": "3ds", "3ds": "3ds",
    "game boy": "gb", "game boy color": "gbc", "game boy advance": "gba",
    "nintendo 64": "n64", "n64": "n64", "gamecube": "gamecube", "nintendo gamecube": "gamecube",
    "wii": "wii", "wii u": "wiiu", "pc": "pc", "windows": "pc",
}
NON_PHYSICAL_ONLY = {"ios", "android", "web"}
NON_PHYSICAL_TITLES = {"need for speed world"}

def title_requires_physical_addon_proof(title):
    key = _search_text(title)
    return bool(re.search(r"\b(?:dlc|season pass|expansion pass)\b", key))

def game_is_physical_candidate(game):
    """One authoritative rule for catalogue, series progress and valuation."""
    platform = normalized_platform(game.console.name if game.console else "")
    if platform in NON_PHYSICAL_ONLY or normalize_series_title(game.title) in NON_PHYSICAL_TITLES:
        return False
    status = getattr(game, "physical_status", None) or "physical"
    if status == "excluded":
        return False
    if title_requires_physical_addon_proof(game.title):
        return status == "physical_addon"
    return status in {"physical", "physical_addon"}

def normalize_series_title(value):
    t = " " + _search_text(value) + " "
    for old, new in SERIES_TITLE_REPLACEMENTS.items():
        t = t.replace(old + " ", new + " ")
    # punctuation/edition noise that commonly differs between local covers and APIs
    t = re.sub(r"\\b(?:edition|version|game)\\b", " ", t)
    return re.sub(r"\\s+", " ", t).strip()

def series_title_aliases(value):
    base = normalize_series_title(value)
    aliases = {base}
    # German/English articles are weak metadata and should not prevent a match.
    aliases.add(re.sub(r"\\b(?:the|die|der|das)\\b", " ", base))
    return {re.sub(r"\\s+", " ", x).strip() for x in aliases if x.strip()}

def normalized_platform(value):
    key = _search_text(value)
    return PHYSICAL_PLATFORM_ALIASES.get(key, key)

def external_is_physical_candidate(entry):
    if normalize_series_title(entry.title) in NON_PHYSICAL_TITLES:
        return False
    # Curated GameCollector rows are hand-checked physical releases, including
    # boxed expansion packs. Provider DLC/season-pass rows need explicit proof.
    if entry.external_source != "GameCollector" and title_requires_physical_addon_proof(entry.title):
        return False
    raw = [x.strip() for x in str(entry.platforms or "").split(",") if x.strip()]
    if not raw:
        return True
    norm = {normalized_platform(x) for x in raw}
    return not norm.issubset(NON_PHYSICAL_ONLY)

def local_series_match(entry, games, local_by_external):
    """Return (matches, method), preferring external IDs then title aliases plus platform."""
    matches = []
    if entry.external_source and entry.external_id:
        matches.extend(local_by_external.get((str(entry.external_source).strip().lower(), str(entry.external_id).strip()), []))
    if matches:
        return matches, "Externe ID"
    wanted = series_title_aliases(entry.title)
    if entry.external_source == "GameCollector":
        wanted.update(curated_aliases(entry.franchise, entry.title))
    title_matches = []
    for g in games:
        candidate = series_title_aliases(g.title)
        if wanted.intersection(candidate):
            title_matches.append(g)
    if not title_matches:
        return [], None
    # Curated catalogues can contain the same title across generations/platforms
    # (e.g. Forza Motorsport 2005 vs. the 2023 reboot). Prefer platform overlap.
    entry_platforms = {normalized_platform(x) for x in str(entry.platforms or "").split(",") if x.strip()}
    if entry_platforms:
        platform_matches = []
        for g in title_matches:
            gp = normalized_platform(getattr(getattr(g, "console", None), "name", ""))
            if gp and gp in entry_platforms:
                platform_matches.append(g)
        if platform_matches:
            return platform_matches, "Titel-Alias"
    return title_matches, "Titel-Alias"

def repair_series_v102_metadata():
    """Idempotent repair for umbrella franchises introduced/fixed in v1.0.2."""
    changed = 0
    for game in Game.query.order_by(Game.id).all():
        detected = infer_franchise_name(game.title)
        if detected not in {"LEGO", "Formula 1 / F1"}:
            continue
        # Preserve explicit manual assignments unless they are an older LEGO/F1 sub-name.
        manual = game.franchise_source == "manual"
        old_key = _search_text(game.franchise)
        safe_old = (not game.franchise) or old_key.startswith("lego") or old_key in {"f1", "formula 1", "formula one", "formula 1 f1"}
        if not manual or safe_old:
            if game.franchise != detected or game.series_status != "series":
                game.franchise = detected; game.franchise_source = "auto-rule"; game.series_status = "series"; changed += 1
        group, generation = classify_series_item(detected, game.title)
        if group and (not game.series_group or game.series_group == "Hauptreihe"):
            if game.series_group != group:
                game.series_group = group; changed += 1
    if changed:
        db.session.commit()
    return changed


# v1.0.3: locally curated series masters. RAWG remains optional enrichment only.
# These lists are intentionally independent of RAWG so series structure stays stable
# even when the provider exposes no game-series data.
CURATED_SERIES = {
    "Formula 1 / F1": [
        {"title":"Formula 1","year":1996,"platforms":"PlayStation","group":"Hauptreihe","aliases":["formula 1","formula one"]},
        {"title":"Formula 1 97","year":1997,"platforms":"PlayStation","group":"Hauptreihe","aliases":["formula 1 97","formula one 97"]},
        {"title":"Formula 1 98","year":1998,"platforms":"PlayStation","group":"Hauptreihe","aliases":["formula 1 98","formula one 98"]},
        {"title":"Formula 1 99","year":1999,"platforms":"PlayStation","group":"Hauptreihe","aliases":["formula 1 99","formula one 99"]},
        {"title":"Formula One 2000","year":2000,"platforms":"PlayStation","group":"Hauptreihe","aliases":["formula one 2000","formula 1 2000","f1 2000"]},
        {"title":"Formula One 2001","year":2001,"platforms":"PlayStation 2","group":"Hauptreihe","aliases":["formula one 2001","formula 1 2001","f1 2001"]},
        {"title":"Formula One 2002","year":2002,"platforms":"PlayStation 2","group":"Hauptreihe","aliases":["formula one 2002","formula 1 2002","f1 2002"]},
        {"title":"Formula One 2003","year":2003,"platforms":"PlayStation 2","group":"Hauptreihe","aliases":["formula one 2003","formula 1 2003","f1 2003"]},
        {"title":"Formula One 04","year":2004,"platforms":"PlayStation 2","group":"Hauptreihe","aliases":["formula one 04","formula one 2004","formula 1 04","f1 04"]},
        {"title":"Formula One 05","year":2005,"platforms":"PlayStation 2","group":"Hauptreihe","aliases":["formula one 05","formula one 2005","formula 1 05","f1 05"]},
        {"title":"Formula One 06","year":2006,"platforms":"PlayStation 2, PSP","group":"Hauptreihe","aliases":["formula one 06","formula one 2006","formula 1 06","f1 06"]},
        {"title":"Formula One Championship Edition","year":2006,"platforms":"PlayStation 3","group":"Hauptreihe","aliases":["formula one championship edition","f1 championship edition"]},
        {"title":"F1 2009","year":2009,"platforms":"Wii, PSP","group":"Hauptreihe","aliases":["f1 2009"]},
        {"title":"F1 2010","year":2010,"platforms":"PlayStation 3, Xbox 360, PC","group":"Hauptreihe","aliases":["f1 2010"]},
        {"title":"F1 2011","year":2011,"platforms":"PlayStation 3, Xbox 360, PC, Nintendo 3DS","group":"Hauptreihe","aliases":["f1 2011"]},
        {"title":"F1 2012","year":2012,"platforms":"PlayStation 3, Xbox 360, PC","group":"Hauptreihe","aliases":["f1 2012"]},
        {"title":"F1 2013","year":2013,"platforms":"PlayStation 3, Xbox 360, PC","group":"Hauptreihe","aliases":["f1 2013"]},
        {"title":"F1 2014","year":2014,"platforms":"PlayStation 3, Xbox 360, PC","group":"Hauptreihe","aliases":["f1 2014"]},
        {"title":"F1 2015","year":2015,"platforms":"PlayStation 4, Xbox One, PC","group":"Hauptreihe","aliases":["f1 2015"]},
        {"title":"F1 2016","year":2016,"platforms":"PlayStation 4, Xbox One, PC","group":"Hauptreihe","aliases":["f1 2016"]},
        {"title":"F1 2017","year":2017,"platforms":"PlayStation 4, Xbox One, PC","group":"Hauptreihe","aliases":["f1 2017"]},
        {"title":"F1 2018","year":2018,"platforms":"PlayStation 4, Xbox One, PC","group":"Hauptreihe","aliases":["f1 2018"]},
        {"title":"F1 2019","year":2019,"platforms":"PlayStation 4, Xbox One, PC","group":"Hauptreihe","aliases":["f1 2019"]},
        {"title":"F1 2020","year":2020,"platforms":"PlayStation 4, Xbox One, PC","group":"Hauptreihe","aliases":["f1 2020"]},
        {"title":"F1 2021","year":2021,"platforms":"PlayStation 4, PlayStation 5, Xbox One, Xbox Series X|S, PC","group":"Hauptreihe","aliases":["f1 2021"]},
        {"title":"F1 22","year":2022,"platforms":"PlayStation 4, PlayStation 5, Xbox One, Xbox Series X|S, PC","group":"Hauptreihe","aliases":["f1 22","f1 2022"]},
        {"title":"F1 23","year":2023,"platforms":"PlayStation 4, PlayStation 5, Xbox One, Xbox Series X|S, PC","group":"Hauptreihe","aliases":["f1 23","f1 2023"]},
        {"title":"F1 24","year":2024,"platforms":"PlayStation 4, PlayStation 5, Xbox One, Xbox Series X|S, PC","group":"Hauptreihe","aliases":["f1 24","f1 2024"]},
        {"title":"F1 25","year":2025,"platforms":"PlayStation 5, Xbox Series X|S, PC","group":"Hauptreihe","aliases":["f1 25","f1 2025"]},
    ],
    "The Sims": [
        {"title":"The Sims","year":2000,"platforms":"PC, PlayStation 2, Xbox, Nintendo GameCube","group":"Hauptreihe","aliases":["the sims","die sims"]},
        {"title":"The Sims 2","year":2004,"platforms":"PC, PlayStation 2, Xbox, Nintendo GameCube, PSP, Nintendo DS, Game Boy Advance","group":"Hauptreihe","aliases":["the sims 2","die sims 2"]},
        {"title":"The Sims 3","year":2009,"platforms":"PC, PlayStation 3, Xbox 360, Wii, Nintendo DS, Nintendo 3DS","group":"Hauptreihe","aliases":["the sims 3","die sims 3"]},
        {"title":"The Sims 4","year":2014,"platforms":"PC, PlayStation 4, Xbox One","group":"Hauptreihe","aliases":["the sims 4","die sims 4"]},
        {"title":"The Sims: Livin' Large","year":2000,"platforms":"PC","group":"Erweiterungen – The Sims","aliases":["the sims livin large","die sims das volle leben"]},
        {"title":"The Sims: House Party","year":2001,"platforms":"PC","group":"Erweiterungen – The Sims","aliases":["the sims house party","die sims party ohne ende"]},
        {"title":"The Sims: Hot Date","year":2001,"platforms":"PC","group":"Erweiterungen – The Sims","aliases":["the sims hot date","die sims hot date"]},
        {"title":"The Sims: Vacation","year":2002,"platforms":"PC","group":"Erweiterungen – The Sims","aliases":["the sims vacation","die sims urlaub total"]},
        {"title":"The Sims: Unleashed","year":2002,"platforms":"PC","group":"Erweiterungen – The Sims","aliases":["the sims unleashed","die sims tierisch gut drauf"]},
        {"title":"The Sims: Superstar","year":2003,"platforms":"PC","group":"Erweiterungen – The Sims","aliases":["the sims superstar","die sims megastar"]},
        {"title":"The Sims: Makin' Magic","year":2003,"platforms":"PC","group":"Erweiterungen – The Sims","aliases":["the sims makin magic","die sims hokus pokus"]},
        {"title":"The Sims 2: University","year":2005,"platforms":"PC","group":"Erweiterungen – The Sims 2","aliases":["the sims 2 university","die sims 2 wilde campus jahre"]},
        {"title":"The Sims 2: Nightlife","year":2005,"platforms":"PC","group":"Erweiterungen – The Sims 2","aliases":["the sims 2 nightlife","die sims 2 nightlife"]},
        {"title":"The Sims 2: Open for Business","year":2006,"platforms":"PC","group":"Erweiterungen – The Sims 2","aliases":["the sims 2 open for business","die sims 2 open for business"]},
        {"title":"The Sims 2: Pets","year":2006,"platforms":"PC, PlayStation 2, Nintendo GameCube, PSP, Nintendo DS, Game Boy Advance","group":"Erweiterungen – The Sims 2","aliases":["the sims 2 pets","die sims 2 haustiere"]},
        {"title":"The Sims 2: Seasons","year":2007,"platforms":"PC","group":"Erweiterungen – The Sims 2","aliases":["the sims 2 seasons","die sims 2 vier jahreszeiten"]},
        {"title":"The Sims 2: Bon Voyage","year":2007,"platforms":"PC","group":"Erweiterungen – The Sims 2","aliases":["the sims 2 bon voyage","die sims 2 gute reise"]},
        {"title":"The Sims 2: FreeTime","year":2008,"platforms":"PC","group":"Erweiterungen – The Sims 2","aliases":["the sims 2 freetime","die sims 2 freizeit spass"]},
        {"title":"The Sims 2: Apartment Life","year":2008,"platforms":"PC","group":"Erweiterungen – The Sims 2","aliases":["the sims 2 apartment life","die sims 2 apartment leben"]},
        {"title":"The Sims 3: World Adventures","year":2009,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 world adventures","die sims 3 reiseabenteuer"]},
        {"title":"The Sims 3: Ambitions","year":2010,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 ambitions","die sims 3 traumkarrieren"]},
        {"title":"The Sims 3: Late Night","year":2010,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 late night","die sims 3 late night"]},
        {"title":"The Sims 3: Generations","year":2011,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 generations","die sims 3 lebensfreude"]},
        {"title":"The Sims 3: Pets","year":2011,"platforms":"PC, PlayStation 3, Xbox 360, Nintendo 3DS","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 pets","die sims 3 einfach tierisch"]},
        {"title":"The Sims 3: Showtime","year":2012,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 showtime","die sims 3 showtime"]},
        {"title":"The Sims 3: Supernatural","year":2012,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 supernatural","die sims 3 supernatural"]},
        {"title":"The Sims 3: Seasons","year":2012,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 seasons","die sims 3 jahreszeiten"]},
        {"title":"The Sims 3: University Life","year":2013,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 university life","die sims 3 wildes studentenleben"]},
        {"title":"The Sims 3: Island Paradise","year":2013,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 island paradise","die sims 3 inselparadies"]},
        {"title":"The Sims 3: Into the Future","year":2013,"platforms":"PC","group":"Erweiterungen – The Sims 3","aliases":["the sims 3 into the future","die sims 3 into the future"]},
        {"title":"The Sims Bustin' Out","year":2003,"platforms":"PlayStation 2, Xbox, Nintendo GameCube, Game Boy Advance","group":"Konsolen-/Spin-offs","aliases":["the sims bustin out","die sims brechen aus"]},
        {"title":"The Urbz: Sims in the City","year":2004,"platforms":"PlayStation 2, Xbox, Nintendo GameCube, Nintendo DS, Game Boy Advance","group":"Konsolen-/Spin-offs","aliases":["the urbz sims in the city","urbz sims in the city"]},
        {"title":"The Sims 2: Castaway","year":2007,"platforms":"PlayStation 2, PSP, Wii, Nintendo DS","group":"Konsolen-/Spin-offs","aliases":["the sims 2 castaway","die sims 2 gestrandet"]},
        {"title":"The Sims Medieval","year":2011,"platforms":"PC","group":"Konsolen-/Spin-offs","aliases":["the sims medieval","die sims mittelalter"]},
        {"title":"The Sims: Life Stories","year":2007,"platforms":"PC","group":"Geschichten","aliases":["the sims life stories","die sims lebensgeschichten"]},
        {"title":"The Sims: Pet Stories","year":2007,"platforms":"PC","group":"Geschichten","aliases":["the sims pet stories","die sims tiergeschichten"]},
        {"title":"The Sims: Castaway Stories","year":2008,"platforms":"PC","group":"Geschichten","aliases":["the sims castaway stories","die sims inselgeschichten"]},
        {"title":"MySims","year":2007,"platforms":"Nintendo Wii, Nintendo DS, PC","group":"MySims","aliases":["mysims"]},
        {"title":"MySims Kingdom","year":2008,"platforms":"Nintendo Wii, Nintendo DS","group":"MySims","aliases":["mysims kingdom"]},
        {"title":"MySims Party","year":2009,"platforms":"Nintendo Wii, Nintendo DS","group":"MySims","aliases":["mysims party"]},
        {"title":"MySims Racing","year":2009,"platforms":"Nintendo Wii, Nintendo DS","group":"MySims","aliases":["mysims racing"]},
        {"title":"MySims Agents","year":2009,"platforms":"Nintendo Wii, Nintendo DS","group":"MySims","aliases":["mysims agents"]},
        {"title":"MySims SkyHeroes","year":2010,"platforms":"PlayStation 3, Xbox 360, Nintendo Wii, Nintendo DS","group":"MySims","aliases":["mysims skyheroes"]},
    ],
    "LEGO": [
        {"title":"LEGO Island","year":1997,"platforms":"PC","group":"Weitere LEGO-Spiele","aliases":["lego island"]},
        {"title":"LEGO Racers","year":1999,"platforms":"PC, PlayStation, Nintendo 64, Game Boy Color","group":"Weitere LEGO-Spiele","aliases":["lego racers"]},
        {"title":"LEGO Island 2: The Brickster's Revenge","year":2001,"platforms":"PC, PlayStation, Game Boy Color, Game Boy Advance","group":"Weitere LEGO-Spiele","aliases":["lego island 2 the bricksters revenge"]},
        {"title":"LEGO Star Wars: The Video Game","year":2005,"platforms":"PlayStation 2, Xbox, Nintendo GameCube, PC, Game Boy Advance","group":"LEGO Star Wars","aliases":["lego star wars the video game"]},
        {"title":"LEGO Star Wars II: The Original Trilogy","year":2006,"platforms":"PlayStation 2, Xbox, Xbox 360, Nintendo GameCube, PSP, Nintendo DS, Game Boy Advance, PC","group":"LEGO Star Wars","aliases":["lego star wars ii the original trilogy","lego star wars 2 the original trilogy"]},
        {"title":"LEGO Star Wars: The Complete Saga","year":2007,"platforms":"PlayStation 3, Xbox 360, Wii, Nintendo DS, PC","group":"LEGO Star Wars","aliases":["lego star wars the complete saga","lego star wars die komplette saga"]},
        {"title":"LEGO Indiana Jones: The Original Adventures","year":2008,"platforms":"PlayStation 2, PlayStation 3, Xbox 360, Wii, PSP, Nintendo DS, PC","group":"LEGO Indiana Jones","aliases":["lego indiana jones the original adventures"]},
        {"title":"LEGO Batman: The Videogame","year":2008,"platforms":"PlayStation 2, PlayStation 3, Xbox 360, Wii, PSP, Nintendo DS, PC","group":"LEGO Batman","aliases":["lego batman the videogame"]},
        {"title":"LEGO Harry Potter: Years 1-4","year":2010,"platforms":"PlayStation 3, Xbox 360, Wii, PSP, Nintendo DS, PC","group":"LEGO Harry Potter","aliases":["lego harry potter years 1 4"]},
        {"title":"LEGO Star Wars III: The Clone Wars","year":2011,"platforms":"PlayStation 3, Xbox 360, Wii, PSP, Nintendo DS, Nintendo 3DS, PC","group":"LEGO Star Wars","aliases":["lego star wars iii the clone wars","lego star wars 3 the clone wars"]},
        {"title":"LEGO Harry Potter: Years 5-7","year":2011,"platforms":"PlayStation 3, Xbox 360, Wii, PSP, Nintendo DS, Nintendo 3DS, PC","group":"LEGO Harry Potter","aliases":["lego harry potter years 5 7"]},
        {"title":"LEGO Batman 2: DC Super Heroes","year":2012,"platforms":"PlayStation 3, Xbox 360, Wii, Wii U, PS Vita, Nintendo DS, Nintendo 3DS, PC","group":"LEGO Batman","aliases":["lego batman 2 dc super heroes"]},
        {"title":"LEGO The Lord of the Rings","year":2012,"platforms":"PlayStation 3, Xbox 360, Wii, PS Vita, Nintendo DS, Nintendo 3DS, PC","group":"LEGO The Lord of the Rings","aliases":["lego the lord of the rings","lego der herr der ringe"]},
        {"title":"LEGO Marvel Super Heroes","year":2013,"platforms":"PlayStation 3, PlayStation 4, Xbox 360, Xbox One, Wii U, PS Vita, Nintendo DS, Nintendo 3DS, PC","group":"LEGO Marvel","aliases":["lego marvel super heroes"]},
        {"title":"LEGO The Hobbit","year":2014,"platforms":"PlayStation 3, PlayStation 4, Xbox 360, Xbox One, Wii U, PS Vita, Nintendo 3DS, PC","group":"LEGO The Hobbit","aliases":["lego the hobbit","lego der hobbit"]},
        {"title":"LEGO Batman 3: Beyond Gotham","year":2014,"platforms":"PlayStation 3, PlayStation 4, Xbox 360, Xbox One, Wii U, PS Vita, Nintendo 3DS, PC","group":"LEGO Batman","aliases":["lego batman 3 beyond gotham"]},
        {"title":"LEGO Jurassic World","year":2015,"platforms":"PlayStation 3, PlayStation 4, Xbox 360, Xbox One, Wii U, PS Vita, Nintendo 3DS, PC","group":"LEGO Jurassic World","aliases":["lego jurassic world"]},
        {"title":"LEGO Dimensions","year":2015,"platforms":"PlayStation 3, PlayStation 4, Xbox 360, Xbox One, Wii U","group":"LEGO Dimensions","aliases":["lego dimensions"]},
        {"title":"LEGO Marvel's Avengers","year":2016,"platforms":"PlayStation 3, PlayStation 4, Xbox 360, Xbox One, Wii U, PS Vita, Nintendo 3DS, PC","group":"LEGO Marvel","aliases":["lego marvels avengers","lego marvel avengers"]},
        {"title":"LEGO Star Wars: The Force Awakens","year":2016,"platforms":"PlayStation 3, PlayStation 4, Xbox 360, Xbox One, Wii U, PS Vita, Nintendo 3DS, PC","group":"LEGO Star Wars","aliases":["lego star wars the force awakens","lego star wars das erwachen der macht"]},
        {"title":"LEGO Marvel Super Heroes 2","year":2017,"platforms":"PlayStation 4, Xbox One, Nintendo Switch, PC","group":"LEGO Marvel","aliases":["lego marvel super heroes 2"]},
        {"title":"LEGO The Incredibles","year":2018,"platforms":"PlayStation 4, Xbox One, Nintendo Switch, PC","group":"Weitere LEGO-Spiele","aliases":["lego the incredibles","lego die unglaublichen"]},
        {"title":"LEGO DC Super-Villains","year":2018,"platforms":"PlayStation 4, Xbox One, Nintendo Switch, PC","group":"LEGO Batman","aliases":["lego dc super villains"]},
        {"title":"The LEGO Movie 2 Videogame","year":2019,"platforms":"PlayStation 4, Xbox One, Nintendo Switch, PC","group":"Weitere LEGO-Spiele","aliases":["the lego movie 2 videogame","lego movie 2 videogame"]},
        {"title":"LEGO Star Wars: The Skywalker Saga","year":2022,"platforms":"PlayStation 4, PlayStation 5, Xbox One, Xbox Series X|S, Nintendo Switch, PC","group":"LEGO Star Wars","aliases":["lego star wars the skywalker saga"]},
    ],
    "Forza": [
        {"title":"Forza Motorsport","year":2005,"platforms":"Xbox","group":"Forza Motorsport","aliases":["forza motorsport","forza" ]},
        {"title":"Forza Motorsport 2","year":2007,"platforms":"Xbox 360","group":"Forza Motorsport","aliases":["forza motorsport 2"]},
        {"title":"Forza Motorsport 3","year":2009,"platforms":"Xbox 360","group":"Forza Motorsport","aliases":["forza motorsport 3"]},
        {"title":"Forza Motorsport 4","year":2011,"platforms":"Xbox 360","group":"Forza Motorsport","aliases":["forza motorsport 4"]},
        {"title":"Forza Motorsport 5","year":2013,"platforms":"Xbox One","group":"Forza Motorsport","aliases":["forza motorsport 5"]},
        {"title":"Forza Motorsport 6","year":2015,"platforms":"Xbox One","group":"Forza Motorsport","aliases":["forza motorsport 6"]},
        {"title":"Forza Motorsport 7","year":2017,"platforms":"Xbox One, PC","group":"Forza Motorsport","aliases":["forza motorsport 7"]},
        {"title":"Forza Motorsport (2023)","year":2023,"platforms":"Xbox Series X|S, PC","group":"Forza Motorsport","aliases":["forza motorsport 2023","forza motorsport 8","forza motorsport"]},
        {"title":"Forza Horizon","year":2012,"platforms":"Xbox 360","group":"Forza Horizon","aliases":["forza horizon","forza horizon 1"]},
        {"title":"Forza Horizon 2","year":2014,"platforms":"Xbox 360, Xbox One","group":"Forza Horizon","aliases":["forza horizon 2"]},
        {"title":"Forza Horizon 3","year":2016,"platforms":"Xbox One, PC","group":"Forza Horizon","aliases":["forza horizon 3"]},
        {"title":"Forza Horizon 4","year":2018,"platforms":"Xbox One, Xbox Series X|S, PC","group":"Forza Horizon","aliases":["forza horizon 4"]},
        {"title":"Forza Horizon 5","year":2021,"platforms":"Xbox One, Xbox Series X|S, PC","group":"Forza Horizon","aliases":["forza horizon 5"]},
    ],
    "Microsoft Flight Simulator": [
        {"title":"Microsoft Flight Simulator","year":2020,"platforms":"PC, Xbox Series X|S","group":"Hauptreihe","aliases":["microsoft flight simulator","microsoft flight simulator 2020","msfs 2020","msfs 2020 edition"]},
        {"title":"Microsoft Flight Simulator 2024","year":2024,"platforms":"Xbox Series X|S, PC","group":"Hauptreihe","aliases":["microsoft flight simulator 2024","msfs 2024","microsoft flight simulator 24","ms flight simulator 2024"]},
    ],
    "SingStar": [
        {"title":"SingStar (PS2)","year":2004,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar"]},
        {"title":"SingStar Party (PS2)","year":2004,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar party"]},
        {"title":"SingStar The Dome (PS2)","year":2005,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar the dome"]},
        {"title":"SingStar '80s (PS2)","year":2005,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar 80s"]},
        {"title":"SingStar '80s Special UK Edition (PS2)","year":2005,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar 80s special uk edition","singstar 80s uk"]},
        {"title":"SingStar Rocks! (PS2)","year":2006,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar rocks"]},
        {"title":"SingStar Deutsch Rock-Pop (PS2)","year":2006,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar deutsch rock pop"]},
        {"title":"SingStar Anthems (PS2)","year":2006,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar anthems"]},
        {"title":"SingStar Legends (PS2)","year":2006,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar legends"]},
        {"title":"SingStar Boogie (PS2)","year":2007,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar boogie"]},
        {"title":"SingStar Pop Hits (PS2)","year":2007,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar pop hits"]},
        {"title":"SingStar Pop (PS2)","year":2007,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar pop"]},
        {"title":"SingStar '90s (PS2)","year":2007,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar 90s"]},
        {"title":"SingStar Die Toten Hosen (PS2)","year":2007,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar die toten hosen"]},
        {"title":"SingStar Deutsch Rock-Pop Vol. 2 (PS2)","year":2007,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar deutsch rock pop vol 2","singstar deutsch rock pop 2"]},
        {"title":"SingStar R&B (PS2)","year":2007,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar r b","singstar r&b"]},
        {"title":"SingStar Rock Ballads (PS2)","year":2007,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar rock ballads"]},
        {"title":"SingStar Après-Ski Party (PS2)","year":2007,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar apres ski party"]},
        {"title":"SingStar Summer Party (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar summer party"]},
        {"title":"SingStar Amped (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar amped"]},
        {"title":"SingStar Hottest Hits (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar hottest hits"]},
        {"title":"SingStar Turkish Party (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar turkish party"]},
        {"title":"SingStar Bollywood (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar bollywood"]},
        {"title":"SingStar Boybands vs. Girlbands (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar boybands vs girlbands"]},
        {"title":"SingStar ABBA (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar abba"]},
        {"title":"SingStar Best of Disney (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar best of disney"]},
        {"title":"SingStar Singalong with Disney (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar singalong with disney"]},
        {"title":"SingStar Schlager (PS2)","year":2008,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar schlager"]},
        {"title":"SingStar Queen (PS2)","year":2009,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar queen"]},
        {"title":"SingStar Demo (PS2)","year":2009,"platforms":"PlayStation 2","group":"Promo / Demo","aliases":["singstar demo"]},
        {"title":"SingStar Mallorca Party (PS2)","year":2009,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar mallorca party"]},
        {"title":"SingStar Motown (PS2)","year":2009,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar motown"]},
        {"title":"SingStar Made in Germany (PS2)","year":2009,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar made in germany"]},
        {"title":"SingStar Take That (PS2)","year":2009,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar take that"]},
        {"title":"SingStar Chartbreaker (PS2)","year":2009,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar chartbreaker"]},
        {"title":"SingStar Die größten Solokünstler (PS2)","year":2010,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar die grossten solokunstler"]},
        {"title":"SingStar Fußballhits (PS2)","year":2010,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar fussballhits"]},
        {"title":"SingStar Après-Ski Party 2 (PS2)","year":2010,"platforms":"PlayStation 2","group":"PlayStation 2","aliases":["singstar apres ski party 2"]},
        {"title":"SingStar (PS3)","year":2007,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar"]},
        {"title":"SingStar Boogie (PS3)","year":2007,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar boogie"]},
        {"title":"SingStar Vol. 2 (PS3)","year":2008,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar vol 2"]},
        {"title":"SingStar Vol. 3 (PS3)","year":2008,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar vol 3"]},
        {"title":"SingStar ABBA (PS3)","year":2008,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar abba"]},
        {"title":"SingStar Queen (PS3)","year":2009,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar queen"]},
        {"title":"SingStar Pop Edition (PS3)","year":2009,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar pop edition"]},
        {"title":"SingStar Mallorca Party (PS3)","year":2009,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar mallorca party"]},
        {"title":"SingStar Motown (PS3)","year":2009,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar motown"]},
        {"title":"SingStar Made in Germany (PS3)","year":2009,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar made in germany"]},
        {"title":"SingStar Take That (PS3)","year":2009,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar take that"]},
        {"title":"SingStar Chartbreaker (PS3)","year":2009,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar chartbreaker"]},
        {"title":"SingStar Fußballhits (PS3)","year":2010,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar fussballhits"]},
        {"title":"SingStar Guitar (PS3)","year":2010,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar guitar"]},
        {"title":"SingStar Après-Ski Party 2 (PS3)","year":2010,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar apres ski party 2"]},
        {"title":"SingStar Dance (PS3)","year":2010,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar dance"]},
        {"title":"SingStar Back to the 80's (PS3)","year":2011,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar back to the 80s"]},
        {"title":"SingStar Ultimate Party (PS3)","year":2014,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar ultimate party"]},
        {"title":"SingStar Die Eiskönigin – Völlig unverfroren (PS3)","year":2014,"platforms":"PlayStation 3","group":"PlayStation 3","aliases":["singstar die eiskonigin vollig unverfroren","singstar frozen"]},
        {"title":"SingStar Ultimate Party (PS4)","year":2014,"platforms":"PlayStation 4","group":"PlayStation 4","aliases":["singstar ultimate party"]},
        {"title":"SingStar Die Eiskönigin – Völlig unverfroren (PS4)","year":2014,"platforms":"PlayStation 4","group":"PlayStation 4","aliases":["singstar die eiskonigin vollig unverfroren","singstar frozen"]},
        {"title":"SingStar Celebration (PS4)","year":2017,"platforms":"PlayStation 4","group":"PlayStation 4","aliases":["singstar celebration"]},
    ],
}

CURATED_SERIES["FIFA"] = [
    {"title":"FIFA International Soccer","year":1993,"platforms":"SNES, Mega Drive / Genesis, 3DO","group":"Hauptreihe","aliases":["fifa international soccer"]},
    {"title":"FIFA Soccer 95","year":1994,"platforms":"Mega Drive / Genesis","group":"Hauptreihe","aliases":["fifa soccer 95","fifa 95"]},
    {"title":"FIFA Soccer 96","year":1995,"platforms":"PlayStation, SNES, Mega Drive / Genesis, PC","group":"Hauptreihe","aliases":["fifa soccer 96","fifa 96"]},
    {"title":"FIFA 97","year":1996,"platforms":"PlayStation, SNES, Mega Drive / Genesis, Sega Saturn, PC","group":"Hauptreihe","aliases":["fifa 97","fifa soccer 97"]},
    {"title":"FIFA: Road to World Cup 98","year":1997,"platforms":"PlayStation, Nintendo 64, Sega Saturn, SNES, Mega Drive / Genesis, PC","group":"Hauptreihe","aliases":["fifa road to world cup 98","fifa 98 road to world cup","fifa 98 die wm qualifikation","fifa '98 die wm qualifikation"]},
    {"title":"FIFA 99","year":1998,"platforms":"PlayStation, Nintendo 64, PC","group":"Hauptreihe","aliases":["fifa 99"]},
    {"title":"FIFA 2000","year":1999,"platforms":"PlayStation, Nintendo 64, Game Boy Color, PC","group":"Hauptreihe","aliases":["fifa 2000"]},
    {"title":"FIFA 2001","year":2000,"platforms":"PlayStation, PlayStation 2, PC","group":"Hauptreihe","aliases":["fifa 2001"]},
    {"title":"FIFA Football 2002","year":2001,"platforms":"PlayStation, PlayStation 2, Nintendo GameCube, PC","group":"Hauptreihe","aliases":["fifa football 2002","fifa 2002"]},
    {"title":"FIFA Football 2003","year":2002,"platforms":"PlayStation, PlayStation 2, Xbox, Nintendo GameCube, Game Boy Advance, PC","group":"Hauptreihe","aliases":["fifa football 2003","fifa 2003"]},
    {"title":"FIFA Football 2004","year":2003,"platforms":"PlayStation, PlayStation 2, Xbox, Nintendo GameCube, Game Boy Advance, PC","group":"Hauptreihe","aliases":["fifa football 2004","fifa 2004"]},
    {"title":"FIFA Football 2005","year":2004,"platforms":"PlayStation, PlayStation 2, Xbox, Nintendo GameCube, Game Boy Advance, PC","group":"Hauptreihe","aliases":["fifa football 2005","fifa 2005"]},
    *[{"title":f"FIFA {year:02d}","year":2005 + year - 6,"platforms":"PlayStation 2, Xbox, Nintendo GameCube, PC","group":"Hauptreihe","aliases":[f"fifa {year:02d}",f"fifa {year}"]} for year in range(6,10)],
    *[{"title":f"FIFA {year}","year":2009 + year - 10,"platforms":"PlayStation 2, PlayStation 3, Xbox 360, Wii, PC","group":"Hauptreihe","aliases":[f"fifa {year}"]} for year in range(10,15)],
    *[{"title":f"FIFA {year}","year":2014 + year - 15,"platforms":"PlayStation 3, PlayStation 4, Xbox 360, Xbox One, PC","group":"Hauptreihe","aliases":[f"fifa {year}"]} for year in range(15,20)],
    *[{"title":f"FIFA {year}","year":2019 + year - 20,"platforms":"PlayStation 4, Xbox One, Nintendo Switch, PC","group":"Hauptreihe","aliases":[f"fifa {year}"]} for year in range(20,24)],
    {"title":"EA SPORTS FC 24","year":2023,"platforms":"PlayStation 4, PlayStation 5, Xbox One, Xbox Series X|S, Nintendo Switch, PC","group":"Hauptreihe","aliases":["ea sports fc 24","fc 24"]},
    {"title":"EA SPORTS FC 25","year":2024,"platforms":"PlayStation 4, PlayStation 5, Xbox One, Xbox Series X|S, Nintendo Switch, PC","group":"Hauptreihe","aliases":["ea sports fc 25","fc 25"]},
    {"title":"EA SPORTS FC 26","year":2025,"platforms":"PlayStation 4, PlayStation 5, Xbox One, Xbox Series X|S, Nintendo Switch, PC","group":"Hauptreihe","aliases":["ea sports fc 26","fc 26"]},
    {"title":"FIFA Street","year":2005,"platforms":"PlayStation 2, Xbox, Nintendo GameCube","group":"FIFA Street","aliases":["fifa street"]},
    {"title":"FIFA Street 2","year":2006,"platforms":"PlayStation 2, Xbox, Nintendo GameCube, PSP","group":"FIFA Street","aliases":["fifa street 2"]},
    {"title":"FIFA Street 3","year":2008,"platforms":"PlayStation 3, Xbox 360, Nintendo DS","group":"FIFA Street","aliases":["fifa street 3"]},
    {"title":"FIFA Street (2012)","year":2012,"platforms":"PlayStation 3, Xbox 360","group":"FIFA Street","aliases":["fifa street 2012","fifa street 4"]},
    {"title":"World Cup 98","year":1998,"platforms":"PlayStation, Nintendo 64, Game Boy Color, PC","group":"FIFA World Cup","aliases":["world cup 98","fifa world cup 98","frankreich 98 die fussball wm"]},
    {"title":"2002 FIFA World Cup","year":2002,"platforms":"PlayStation, PlayStation 2, Xbox, Nintendo GameCube, PC","group":"FIFA World Cup","aliases":["2002 fifa world cup","fifa world cup 2002"]},
    {"title":"2006 FIFA World Cup","year":2006,"platforms":"PlayStation 2, Xbox, Xbox 360, Nintendo GameCube, PSP, PC","group":"FIFA World Cup","aliases":["2006 fifa world cup","fifa world cup 2006"]},
    {"title":"2010 FIFA World Cup South Africa","year":2010,"platforms":"PlayStation 3, Xbox 360, Wii, PSP","group":"FIFA World Cup","aliases":["2010 fifa world cup south africa","fifa world cup 2010"]},
    {"title":"2014 FIFA World Cup Brazil","year":2014,"platforms":"PlayStation 3, Xbox 360","group":"FIFA World Cup","aliases":["2014 fifa world cup brazil","fifa world cup 2014"]},
    {"title":"UEFA Euro 2000","year":2000,"platforms":"PlayStation, PC","group":"UEFA Euro","aliases":["uefa euro 2000"]},
    {"title":"UEFA Euro 2004","year":2004,"platforms":"PlayStation 2, Xbox, PC","group":"UEFA Euro","aliases":["uefa euro 2004"]},
    {"title":"UEFA Euro 2008","year":2008,"platforms":"PlayStation 2, PlayStation 3, Xbox 360, PSP, PC","group":"UEFA Euro","aliases":["uefa euro 2008"]},
    {"title":"FIFA 06: Road to FIFA World Cup","year":2005,"platforms":"Xbox 360","group":"Weitere Ableger","aliases":["fifa 06 road to fifa world cup"]},
]

CURATED_SERIES["Donkey Kong"] = [
    {"title":"Donkey Kong","year":1981,"platforms":"Arcade, NES, Game Boy","group":"Klassiker","aliases":["donkey kong"]},
    {"title":"Donkey Kong Jr.","year":1982,"platforms":"Arcade, NES","group":"Klassiker","aliases":["donkey kong jr","donkey kong junior"]},
    {"title":"Donkey Kong 3","year":1983,"platforms":"Arcade, NES","group":"Klassiker","aliases":["donkey kong 3"]},
    {"title":"Donkey Kong Land","year":1995,"platforms":"Game Boy","group":"Donkey Kong Land","aliases":["donkey kong land"]},
    {"title":"Donkey Kong Land 2","year":1996,"platforms":"Game Boy","group":"Donkey Kong Land","aliases":["donkey kong land 2"]},
    {"title":"Donkey Kong Land III","year":1997,"platforms":"Game Boy","group":"Donkey Kong Land","aliases":["donkey kong land iii","donkey kong land 3"]},
    {"title":"Donkey Kong Country","year":1994,"platforms":"SNES, Game Boy Color, Game Boy Advance","group":"Donkey Kong Country","aliases":["donkey kong country"]},
    {"title":"Donkey Kong Country 2: Diddy's Kong Quest","year":1995,"platforms":"SNES, Game Boy Advance","group":"Donkey Kong Country","aliases":["donkey kong country 2","diddys kong quest"]},
    {"title":"Donkey Kong Country 3: Dixie Kong's Double Trouble!","year":1996,"platforms":"SNES, Game Boy Advance","group":"Donkey Kong Country","aliases":["donkey kong country 3","dixie kongs double trouble"]},
    {"title":"Donkey Kong 64","year":1999,"platforms":"Nintendo 64","group":"3D-Abenteuer","aliases":["donkey kong 64"]},
    {"title":"Donkey Konga","year":2003,"platforms":"Nintendo GameCube","group":"Donkey Konga","aliases":["donkey konga"]},
    {"title":"Donkey Konga 2","year":2004,"platforms":"Nintendo GameCube","group":"Donkey Konga","aliases":["donkey konga 2"]},
    {"title":"Donkey Kong Jungle Beat","year":2004,"platforms":"Nintendo GameCube, Wii","group":"Weitere Spiele","aliases":["donkey kong jungle beat"]},
    {"title":"DK: King of Swing","year":2005,"platforms":"Game Boy Advance","group":"Weitere Spiele","aliases":["dk king of swing"]},
    {"title":"Donkey Kong: Jungle Climber","year":2007,"platforms":"Nintendo DS","group":"Weitere Spiele","aliases":["donkey kong jungle climber"]},
    {"title":"Donkey Kong Barrel Blast","year":2007,"platforms":"Wii","group":"Weitere Spiele","aliases":["donkey kong barrel blast","donkey jet"]},
    {"title":"Donkey Kong Country Returns","year":2010,"platforms":"Wii, Nintendo 3DS","group":"Donkey Kong Country","aliases":["donkey kong country returns"]},
    {"title":"Donkey Kong Country: Tropical Freeze","year":2014,"platforms":"Wii U, Nintendo Switch","group":"Donkey Kong Country","aliases":["donkey kong country tropical freeze"]},
    {"title":"Donkey Kong Country Returns HD","year":2025,"platforms":"Nintendo Switch","group":"Donkey Kong Country","aliases":["donkey kong country returns hd"]},
]

# EA Sports' German PC main series. One row represents one work; several
# editions of the same annual title stay separate inventory copies without
# inflating the series completion counter.
CURATED_SERIES["Fußball Manager"] = [
    {"title":"Fußball Manager 2002","year":2001,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 2002","fußball manager 2002","fifa manager 2002"]},
    {"title":"Fußball Manager 2003","year":2002,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 2003","fußball manager 2003","fifa manager 2003"]},
    {"title":"Fußball Manager 2004","year":2003,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 2004","fußball manager 2004","fifa manager 2004"]},
    {"title":"Fußball Manager 2005","year":2004,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 2005","fußball manager 2005","fifa manager 2005","fm 2005"]},
    {"title":"Fußball Manager 06","year":2005,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 06","fußball manager 06","fussball manager 2006","fifa manager 06"]},
    {"title":"Fußball Manager 07","year":2006,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 07","fußball manager 07","fussball manager 2007","fifa manager 07"]},
    {"title":"Fußball Manager 08","year":2007,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 08","fußball manager 08","fussball manager 2008","fifa manager 08"]},
    {"title":"Fußball Manager 09","year":2008,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 09","fußball manager 09","fussball manager 2009","fifa manager 09"]},
    {"title":"Fußball Manager 10","year":2009,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 10","fußball manager 10","fussball manager 2010","fifa manager 10"]},
    {"title":"Fußball Manager 11","year":2010,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 11","fußball manager 11","fussball manager 2011","fifa manager 11"]},
    {"title":"Fußball Manager 12","year":2011,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 12","fußball manager 12","fussball manager 2012","fifa manager 12"]},
    {"title":"Fußball Manager 13","year":2012,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 13","fußball manager 13","fussball manager 2013","fifa manager 13"]},
    {"title":"Fußball Manager 14","year":2013,"platforms":"PC","group":"Hauptreihe","aliases":["fussball manager 14","fußball manager 14","fussball manager 2014","fifa manager 14"]},
]

CURATED_SERIES_ALIASES = {}
for _franchise, _rows in CURATED_SERIES.items():
    for _row in _rows:
        CURATED_SERIES_ALIASES[(_franchise, _search_text(_row["title"]))] = set(_row.get("aliases") or []) | {_row["title"]}


def curated_series_rows(franchise):
    return CURATED_SERIES.get(franchise, [])


def curated_aliases(franchise, title):
    aliases = CURATED_SERIES_ALIASES.get((franchise, _search_text(title)), {title})
    out = set()
    for alias in aliases:
        out.update(series_title_aliases(alias))
    return out


def canonical_series_item_key(franchise, title):
    """Stable key used to merge regional names and platform-specific metadata rows."""
    key = normalize_series_title(title)
    if _search_text(franchise) == "fifa":
        explicit = {
            "fifa soccer 97": "fifa 97",
            "fifa 98 die wm qualifikation": "fifa road to world cup 98",
            "fifa 98 die wm-qualifikation": "fifa road to world cup 98",
            "fifa 98 road to world cup": "fifa road to world cup 98",
            "fifa football 2003": "fifa 2003",
            "fifa football 2004": "fifa 2004",
            "fifa football 2005": "fifa 2005",
        }
        key = explicit.get(key, key)
    title_aliases = series_title_aliases(title)
    for row in CURATED_SERIES.get(franchise, []):
        known = set()
        for alias in [row.get("title")] + list(row.get("aliases") or []):
            known.update(series_title_aliases(alias))
        if title_aliases & known:
            return normalize_series_title(row.get("title"))
    return key


def canonical_franchise_name(value):
    key = _search_text(value)
    aliases = {
        "pokemon": "Pokémon", "donkey kong country": "Donkey Kong",
        "donkey kong": "Donkey Kong", "formel 1": "Formula 1 / F1",
        "formula 1": "Formula 1 / F1", "formula 1 f1": "Formula 1 / F1",
        "formula one": "Formula 1 / F1", "f1": "Formula 1 / F1",
        "fifa football": "FIFA", "ea sports fc": "FIFA",
        "fussball manager": "Fußball Manager", "fifa manager": "Fußball Manager",
        "die sims": "The Sims", "mysims": "The Sims",
    }
    return aliases.get(key, value)


SERIES_PLATFORM_AGE = {
    "atari 2600": 1977, "nes": 1983, "nintendo entertainment system nes": 1983,
    "master system": 1985, "game boy": 1989, "snes": 1990, "super nintendo snes": 1990,
    "mega drive genesis": 1988, "game gear": 1990,
    "playstation": 1994, "sega saturn": 1994, "nintendo 64": 1996,
    "game boy color": 1998, "dreamcast": 1998, "playstation 2": 2000,
    "game boy advance": 2001, "nintendo gamecube": 2001, "xbox": 2001,
    "nintendo ds": 2004, "psp": 2004, "xbox 360": 2005, "playstation 3": 2006,
    "wii": 2006, "nintendo 3ds": 2011, "ps vita": 2011, "wii u": 2012,
    "playstation 4": 2013, "xbox one": 2013, "nintendo switch": 2017,
    "playstation 5": 2020, "xbox series x s": 2020, "pc": 9998,
}


def series_platform_age(game):
    return SERIES_PLATFORM_AGE.get(_search_text(getattr(getattr(game, "console", None), "name", "")), 9999)


def ensure_curated_series_entries(franchise=None):
    """Idempotently install/update local series master rows. Returns (added, updated)."""
    franchises = [franchise] if franchise else list(CURATED_SERIES)
    added = updated = 0
    for name in franchises:
        for row in CURATED_SERIES.get(name, []):
            source_id = "curated:" + re.sub(r"[^a-z0-9]+", "-", _search_text(row["title"])).strip("-")
            entry = SeriesEntry.query.filter_by(franchise=name, external_source="GameCollector", external_id=source_id).first()
            if not entry:
                entry = SeriesEntry(franchise=name, external_source="GameCollector", external_id=source_id, title=row["title"])
                db.session.add(entry); added += 1
            else:
                updated += 1
            entry.title = row["title"]
            entry.release_year = row.get("year")
            entry.platforms = row.get("platforms")
            entry.series_group = row.get("group") or "Hauptreihe"
            entry.series_generation = row.get("generation")
    db.session.commit()
    return added, updated


def repair_series_v103_metadata():
    """Normalize F1, LEGO and Sims umbrella assignments without overwriting unrelated manual curation."""
    changed = 0
    for game in Game.query.order_by(Game.id).all():
        detected = infer_franchise_name(game.title)
        if detected not in {"LEGO", "Formula 1 / F1", "The Sims"}:
            continue
        manual = game.franchise_source == "manual"
        old_key = _search_text(game.franchise)
        safe_prefixes = ("lego", "f1", "formula 1", "formula one", "the sims", "die sims")
        safe_old = (not game.franchise) or any(old_key.startswith(x) for x in safe_prefixes)
        if not manual or safe_old:
            if game.franchise != detected or game.series_status != "series":
                game.franchise = detected
                game.franchise_source = "auto-rule"
                game.series_status = "series"
                changed += 1
            group, generation = classify_series_item(detected, game.title)
            if group and game.series_group != group:
                game.series_group = group
                game.series_generation = generation
                changed += 1
    if changed:
        db.session.commit()
    return changed


def repair_series_v104_metadata():
    """Normalize locally curated franchises without overwriting unrelated manual curation."""
    changed = 0
    targets = {"Forza", "Microsoft Flight Simulator", "SingStar"}
    for game in Game.query.order_by(Game.id).all():
        detected = infer_franchise_name(game.title)
        if detected not in targets:
            continue
        manual = game.franchise_source == "manual"
        old_key = _search_text(game.franchise)
        safe_old = (not game.franchise) or old_key in {"forza", "forza horizon", "forza motorsport", "microsoft flight simulator", "microsoft flight sim", "singstar"}
        if not manual or safe_old:
            if game.franchise != detected or game.series_status != "series":
                game.franchise = detected
                game.franchise_source = "auto-rule"
                game.series_status = "series"
                changed += 1
            group, generation = classify_series_item(detected, game.title)
            if group and game.series_group != group:
                game.series_group = group
                game.series_generation = generation
                changed += 1
    if changed:
        db.session.commit()
    return changed


POKEMON_CURATED_SERIES = [
    # Generation I
    {"title":"Pokémon Rot","generation":"I","year":1996,"platforms":"Game Boy","aliases":["pokemon rot","pokemon red","red version"]},
    {"title":"Pokémon Blau","generation":"I","year":1996,"platforms":"Game Boy","aliases":["pokemon blau","pokemon blue","blue version"]},
    {"title":"Pokémon Gelb","generation":"I","year":1998,"platforms":"Game Boy","aliases":["pokemon gelb","pokemon yellow","yellow version"]},
    # Generation II
    {"title":"Pokémon Gold","generation":"II","year":1999,"platforms":"Game Boy Color","aliases":["pokemon gold"]},
    {"title":"Pokémon Silber","generation":"II","year":1999,"platforms":"Game Boy Color","aliases":["pokemon silber","pokemon silver"]},
    {"title":"Pokémon Kristall","generation":"II","year":2000,"platforms":"Game Boy Color","aliases":["pokemon kristall","pokemon crystal"]},
    # Generation III
    {"title":"Pokémon Rubin","generation":"III","year":2002,"platforms":"Game Boy Advance","aliases":["pokemon rubin","pokemon ruby"]},
    {"title":"Pokémon Saphir","generation":"III","year":2002,"platforms":"Game Boy Advance","aliases":["pokemon saphir","pokemon sapphire"]},
    {"title":"Pokémon Smaragd","generation":"III","year":2004,"platforms":"Game Boy Advance","aliases":["pokemon smaragd","pokemon emerald"]},
    {"title":"Pokémon Feuerrot","generation":"III","year":2004,"platforms":"Game Boy Advance","aliases":["pokemon feuerrot","pokemon firered","pokemon fire red"]},
    {"title":"Pokémon Blattgrün","generation":"III","year":2004,"platforms":"Game Boy Advance","aliases":["pokemon blattgrun","pokemon leafgreen","pokemon leaf green"]},
    # Generation IV
    {"title":"Pokémon Diamant","generation":"IV","year":2006,"platforms":"Nintendo DS","aliases":["pokemon diamant","pokemon diamond"]},
    {"title":"Pokémon Perl","generation":"IV","year":2006,"platforms":"Nintendo DS","aliases":["pokemon perl","pokemon pearl"]},
    {"title":"Pokémon Platin","generation":"IV","year":2008,"platforms":"Nintendo DS","aliases":["pokemon platin","pokemon platinum"]},
    {"title":"Pokémon HeartGold","generation":"IV","year":2009,"platforms":"Nintendo DS","aliases":["pokemon heartgold","pokemon heart gold","heartgold","heart gold","pokemon goldene edition heartgold","pokemon goldene edition heart gold"]},
    {"title":"Pokémon SoulSilver","generation":"IV","year":2009,"platforms":"Nintendo DS","aliases":["pokemon soulsilver","pokemon soul silver","soulsilver","soul silver","pokemon silberne edition soulsilver","pokemon silberne edition soul silver"]},
    # Generation V
    {"title":"Pokémon Schwarz","generation":"V","year":2010,"platforms":"Nintendo DS","aliases":["pokemon schwarz","pokemon black"]},
    {"title":"Pokémon Weiß","generation":"V","year":2010,"platforms":"Nintendo DS","aliases":["pokemon weiss","pokemon white"]},
    {"title":"Pokémon Schwarz 2","generation":"V","year":2012,"platforms":"Nintendo DS","aliases":["pokemon schwarz 2","pokemon black 2"]},
    {"title":"Pokémon Weiß 2","generation":"V","year":2012,"platforms":"Nintendo DS","aliases":["pokemon weiss 2","pokemon white 2"]},
    # Generation VI
    {"title":"Pokémon X","generation":"VI","year":2013,"platforms":"Nintendo 3DS","aliases":["pokemon x"]},
    {"title":"Pokémon Y","generation":"VI","year":2013,"platforms":"Nintendo 3DS","aliases":["pokemon y"]},
    {"title":"Pokémon Omega Rubin","generation":"VI","year":2014,"platforms":"Nintendo 3DS","aliases":["pokemon omega rubin","pokemon omega ruby"]},
    {"title":"Pokémon Alpha Saphir","generation":"VI","year":2014,"platforms":"Nintendo 3DS","aliases":["pokemon alpha saphir","pokemon alpha sapphire"]},
    # Generation VII
    {"title":"Pokémon Sonne","generation":"VII","year":2016,"platforms":"Nintendo 3DS","aliases":["pokemon sonne","pokemon sun"]},
    {"title":"Pokémon Mond","generation":"VII","year":2016,"platforms":"Nintendo 3DS","aliases":["pokemon mond","pokemon moon"]},
    {"title":"Pokémon Ultrasonne","generation":"VII","year":2017,"platforms":"Nintendo 3DS","aliases":["pokemon ultrasonne","pokemon ultra sun"]},
    {"title":"Pokémon Ultramond","generation":"VII","year":2017,"platforms":"Nintendo 3DS","aliases":["pokemon ultramond","pokemon ultra moon"]},
    {"title":"Pokémon: Let's Go, Pikachu!","generation":"VII","year":2018,"platforms":"Nintendo Switch","aliases":["pokemon lets go pikachu","lets go pikachu"]},
    {"title":"Pokémon: Let's Go, Evoli!","generation":"VII","year":2018,"platforms":"Nintendo Switch","aliases":["pokemon lets go evoli","pokemon lets go eevee","lets go eevee"]},
    # Generation VIII
    {"title":"Pokémon Schwert","generation":"VIII","year":2019,"platforms":"Nintendo Switch","aliases":["pokemon schwert","pokemon sword"]},
    {"title":"Pokémon Schild","generation":"VIII","year":2019,"platforms":"Nintendo Switch","aliases":["pokemon schild","pokemon shield"]},
    {"title":"Pokémon Strahlender Diamant","generation":"VIII","year":2021,"platforms":"Nintendo Switch","aliases":["pokemon strahlender diamant","pokemon brilliant diamond"]},
    {"title":"Pokémon Leuchtende Perle","generation":"VIII","year":2021,"platforms":"Nintendo Switch","aliases":["pokemon leuchtende perle","pokemon shining pearl"]},
    {"title":"Pokémon-Legenden: Arceus","generation":"VIII","year":2022,"platforms":"Nintendo Switch","aliases":["pokemon legenden arceus","pokemon legends arceus"]},
    # Generation IX
    {"title":"Pokémon Karmesin","generation":"IX","year":2022,"platforms":"Nintendo Switch","aliases":["pokemon karmesin","pokemon scarlet"]},
    {"title":"Pokémon Purpur","generation":"IX","year":2022,"platforms":"Nintendo Switch","aliases":["pokemon purpur","pokemon violet"]},
]

POKEMON_CURATED_SPINOFFS = [
    {"title":"Pokémon Snap","group":"Pokémon Snap","year":1999,"platforms":"Nintendo 64","aliases":["pokemon snap"]},
    {"title":"New Pokémon Snap","group":"Pokémon Snap","year":2021,"platforms":"Nintendo Switch","aliases":["new pokemon snap"]},
    {"title":"Pokémon Stadium","group":"Pokémon Stadium","year":1999,"platforms":"Nintendo 64","aliases":["pokemon stadium"]},
    {"title":"Pokémon Stadium 2","group":"Pokémon Stadium","year":2000,"platforms":"Nintendo 64","aliases":["pokemon stadium 2"]},
    {"title":"Pokémon Ranger","group":"Pokémon Ranger","year":2006,"platforms":"Nintendo DS","aliases":["pokemon ranger"]},
    {"title":"Pokémon Ranger: Finsternis über Almia","group":"Pokémon Ranger","year":2008,"platforms":"Nintendo DS","aliases":["pokemon ranger finsternis uber almia","pokemon ranger shadows of almia"]},
    {"title":"Pokémon Ranger: Spuren des Lichts","group":"Pokémon Ranger","year":2010,"platforms":"Nintendo DS","aliases":["pokemon ranger spuren des lichts","pokemon ranger guardian signs"]},
    {"title":"Pokémon Mystery Dungeon: Team Blau","group":"Mystery Dungeon","year":2005,"platforms":"Nintendo DS","aliases":["pokemon mystery dungeon team blau","blue rescue team"]},
    {"title":"Pokémon Mystery Dungeon: Team Rot","group":"Mystery Dungeon","year":2005,"platforms":"Game Boy Advance","aliases":["pokemon mystery dungeon team rot","red rescue team"]},
    {"title":"Pokémon Mystery Dungeon: Erkundungsteam Zeit","group":"Mystery Dungeon","year":2007,"platforms":"Nintendo DS","aliases":["erkundungsteam zeit","explorers of time"]},
    {"title":"Pokémon Mystery Dungeon: Erkundungsteam Dunkelheit","group":"Mystery Dungeon","year":2007,"platforms":"Nintendo DS","aliases":["erkundungsteam dunkelheit","explorers of darkness"]},
    {"title":"Pokémon Mystery Dungeon: Erkundungsteam Himmel","group":"Mystery Dungeon","year":2009,"platforms":"Nintendo DS","aliases":["erkundungsteam himmel","explorers of sky"]},
    {"title":"Pokémon Mystery Dungeon: Portale in die Unendlichkeit","group":"Mystery Dungeon","year":2012,"platforms":"Nintendo 3DS","aliases":["portale in die unendlichkeit","gates to infinity"]},
    {"title":"Pokémon Super Mystery Dungeon","group":"Mystery Dungeon","year":2015,"platforms":"Nintendo 3DS","aliases":["pokemon super mystery dungeon"]},
    {"title":"Pokémon Mystery Dungeon: Retterteam DX","group":"Mystery Dungeon","year":2020,"platforms":"Nintendo Switch","aliases":["retterteam dx","rescue team dx"]},
    {"title":"Pokémon Colosseum","group":"Pokémon Colosseum / XD","year":2003,"platforms":"Nintendo GameCube","aliases":["pokemon colosseum"]},
    {"title":"Pokémon XD: Der Dunkle Sturm","group":"Pokémon Colosseum / XD","year":2005,"platforms":"Nintendo GameCube","aliases":["pokemon xd der dunkle sturm","pokemon xd gale of darkness"]},
    {"title":"Pokémon Pinball","group":"Pokémon Pinball","year":1999,"platforms":"Game Boy Color","aliases":["pokemon pinball"]},
    {"title":"Pokémon Pinball: Rubin & Saphir","group":"Pokémon Pinball","year":2003,"platforms":"Game Boy Advance","aliases":["pokemon pinball rubin saphir","pokemon pinball ruby sapphire"]},
    {"title":"Pokémon Trading Card Game","group":"Pokémon TCG","year":1998,"platforms":"Game Boy Color","aliases":["pokemon trading card game","pokemon tcg"]},
    {"title":"PokéPark Wii: Pikachus großes Abenteuer","group":"PokéPark","year":2009,"platforms":"Wii","aliases":["pokepark wii pikachus grosses abenteuer","pokepark pikachus adventure"]},
    {"title":"PokéPark 2: Die Dimension der Wünsche","group":"PokéPark","year":2011,"platforms":"Wii","aliases":["pokepark 2 die dimension der wunsche","pokepark 2 wonders beyond"]},
]

POKEMON_GENERATIONS = [
    ("I", ["red", "blue", "yellow", "lets go pikachu", "lets go eevee"]),
    ("II", ["gold", "silver", "crystal"]),
    ("III", ["ruby", "sapphire", "emerald", "firered", "leafgreen", "fire red", "leaf green"]),
    ("IV", ["diamond", "pearl", "platinum", "heartgold", "soulsilver", "heart gold", "soul silver", "brilliant diamond", "shining pearl"]),
    ("V", ["black", "white"]),
    ("VI", ["pokemon x", "pokemon y", "pokémon x", "pokémon y", "omega ruby", "alpha sapphire"]),
    ("VII", ["sun", "moon", "ultra sun", "ultra moon"]),
    ("VIII", ["sword", "shield", "legends arceus"]),
    ("IX", ["scarlet", "violet"]),
]


def classify_series_item(franchise, title):
    """Return (sub-series/group, generation) without changing the parent franchise."""
    f = _search_text(franchise)
    t = _search_text(title)
    if f == "pokemon":
        spin_offs = [
            ("Mystery Dungeon", ("mystery dungeon",)),
            ("Pokémon Ranger", ("pokemon ranger",)),
            ("Pokémon Snap", ("pokemon snap", "new pokemon snap")),
            ("Pokémon Stadium", ("pokemon stadium",)),
            ("Pokémon Colosseum / XD", ("pokemon colosseum", "gale of darkness", "pokemon xd")),
            ("Pokémon Pinball", ("pokemon pinball",)),
            ("Pokémon Rumble", ("pokemon rumble",)),
            ("PokéPark", ("pokepark",)),
            ("Pokémon TCG", ("trading card game", "pokemon tcg")),
        ]
        for group, tokens in spin_offs:
            if any(token in t for token in tokens):
                return group, None
        generation = None
        # Specific remake names must win over short base names such as "silver".
        # Otherwise SoulSilver can be misclassified as Generation II.
        specific_generation = [
            ("IV", ("heartgold", "heart gold", "soulsilver", "soul silver")),
            ("VI", ("omega ruby", "omega rubin", "alpha sapphire", "alpha saphir")),
            ("VIII", ("brilliant diamond", "strahlender diamant", "shining pearl", "leuchtende perle", "legends arceus", "legenden arceus")),
        ]
        for roman, tokens in specific_generation:
            if any(token in t for token in tokens):
                generation = roman
                break
        # Mainline titles and remakes.
        for roman, tokens in POKEMON_GENERATIONS:
            if generation:
                break
            if any(token in t for token in tokens):
                generation = roman
                break
        mainline_markers = ("pokemon red", "pokemon blue", "pokemon yellow", "pokemon gold", "pokemon silver", "pokemon crystal",
                            "pokemon ruby", "pokemon sapphire", "pokemon emerald", "pokemon firered", "pokemon leafgreen",
                            "pokemon diamond", "pokemon pearl", "pokemon platinum", "pokemon heartgold", "pokemon soulsilver",
                            "pokemon black", "pokemon white", "pokemon x", "pokemon y", "pokemon sun", "pokemon moon",
                            "pokemon sword", "pokemon shield", "pokemon scarlet", "pokemon violet", "lets go", "legends arceus",
                            "brilliant diamond", "shining pearl", "omega ruby", "alpha sapphire")
        if generation or any(x in t for x in mainline_markers):
            return "Hauptreihe", generation
        return "Weitere Pokémon-Spiele", None
    if f == "lego":
        return infer_lego_series_group(title) or "Weitere LEGO-Spiele", None
    if f in ("formula 1 f1", "formula 1", "f1", "formula one"):
        if "manager" in t:
            return "F1 Manager", None
        # v1.0.3: all official Formula 1 / Formula One / annual F1 games are one main series.
        if t.startswith("formula one") or t.startswith("formula 1") or re.match(r"^f1\s+(?:0?\d|19\d{2}|20\d{2}|2\d)\b", t):
            return "Hauptreihe", None
        return "Weitere Formel-1-Spiele", None
    if f == "forza":
        if "horizon" in t:
            return "Forza Horizon", None
        if "motorsport" in t or re.match(r"^forza(?:\s+motorsport)?(?:\s+\d+)?$", t):
            return "Forza Motorsport", None
        return "Weitere Forza-Spiele", None
    if f == "microsoft flight simulator":
        return "Hauptreihe", None
    if f == "the sims":
        curated = CURATED_SERIES_ALIASES if "CURATED_SERIES_ALIASES" in globals() else {}
        for row in CURATED_SERIES.get("The Sims", []) if "CURATED_SERIES" in globals() else []:
            aliases = set()
            for a in (row.get("aliases") or []) + [row["title"]]:
                aliases.update(series_title_aliases(a))
            if aliases.intersection(series_title_aliases(title)):
                return row.get("group") or "Hauptreihe", None
        if re.match(r"^(?:the|die) sims(?:\s+[234])?$", t):
            return "Hauptreihe", None
        return "Weitere Die-Sims-Spiele", None
    if f == "call of duty":
        if "modern warfare" in t:
            return "Modern Warfare", None
        if "black ops" in t:
            return "Black Ops", None
        return "Weitere Call of Duty", None
    if f in ("fifa", "ea sports fc"):
        return "Hauptreihe", None
    return "Hauptreihe", None

def rawg_game_series_rows(game_id, page_size=80):
    """Return structured sibling titles from RAWG's game-series endpoint."""
    api_key = os.environ.get("RAWG_API_KEY", "").strip()
    if not api_key or not game_id:
        return []
    data = fetch_json(
        f"https://api.rawg.io/api/games/{quote(str(game_id))}/game-series?{urlencode({'key': api_key, 'page_size': page_size})}",
        timeout=7,
    )
    if not isinstance(data, dict):
        return []
    rows = []
    for x in data.get("results") or []:
        if not isinstance(x, dict) or not x.get("name") or not x.get("id"):
            continue
        released = str(x.get("released") or "")
        platforms = []
        for p in x.get("platforms") or []:
            if isinstance(p, dict) and isinstance(p.get("platform"), dict):
                name = str(p["platform"].get("name") or "").strip()
                if name:
                    platforms.append(name)
        rows.append({
            "id": str(x.get("id")),
            "name": str(x.get("name") or "").strip(),
            "release_year": int(released[:4]) if len(released) >= 4 and released[:4].isdigit() else None,
            "cover_url": str(x.get("background_image") or "").strip() or None,
            "platforms": platforms,
        })
    return rows


def rawg_game_series(game_id):
    return [row["name"] for row in rawg_game_series_rows(game_id, page_size=40)]


def infer_franchise_from_rawg(game):
    direct = infer_franchise_name(game.title)
    if direct:
        return direct, "auto-rule"
    if game.external_source == "RAWG" and game.external_id:
        siblings = rawg_game_series(game.external_id)
        candidates = [infer_franchise_name(x) for x in [game.title] + siblings]
        candidates = [x for x in candidates if x]
        if candidates:
            from collections import Counter
            return Counter(candidates).most_common(1)[0][0], "RAWG series"
    return None, None


def apply_game_form(game):
    game.title = request.form.get("title", "").strip()
    game.console_id = request.form.get("console_id", type=int) or game.console_id
    game.region = request.form.get("region", "PAL").strip() or "PAL"
    game.language = request.form.get("language", "").strip() or None
    year = request.form.get("release_year", "").strip()
    game.release_year = int(year) if year.isdigit() else None
    game.publisher = request.form.get("publisher", "").strip() or None
    game.developer = request.form.get("developer", "").strip() or None
    game.genre = request.form.get("genre", "").strip() or None
    game.edition = request.form.get("edition", "Standard").strip() or "Standard"
    physical_status = request.form.get("physical_status", getattr(game, "physical_status", "physical") or "physical")
    game.physical_status = physical_status if physical_status in {"physical", "physical_addon", "excluded"} else "physical"
    # Mobile platforms and the discontinued download-only NFS World service can
    # never be promoted accidentally by an old form submission.
    console = db.session.get(Console, game.console_id)
    if normalized_platform(console.name if console else "") in NON_PHYSICAL_ONLY or normalize_series_title(game.title) in NON_PHYSICAL_TITLES:
        game.physical_status = "excluded"
    game.franchise = request.form.get("franchise", "").strip() or None
    game.franchise_source = "manual" if game.franchise else None
    # v0.9.2: A populated series field is authoritative.  This keeps the
    # catalogue consistent even if an old browser form still submits another
    # radio value.  Empty series fields remain a deliberate manual decision.
    requested_series_status = request.form.get("series_status", "unreviewed")
    if game.franchise:
        game.series_status = "series"
    else:
        game.series_status = requested_series_status if requested_series_status in {"unreviewed", "series", "standalone"} else "unreviewed"
    if game.series_status == "standalone":
        game.franchise = None; game.franchise_source = "manual"; game.series_group = None; game.series_generation = None
    elif game.franchise == "LEGO" and not game.series_group:
        game.series_group = infer_lego_series_group(game.title)
    game.barcode = clean_barcode(request.form.get("barcode"))
    game.product_code = normalize_product_code(request.form.get("product_code"))
    game.cover_url = archived_or_original_image(request.form.get("cover_url", ""))
    game.external_source = request.form.get("external_source", "").strip() or None
    game.external_id = request.form.get("external_id", "").strip() or None

def rawg_game_search(query, platform_name=None, limit=12):
    """Robust RAWG title search with a precise pass and progressively broader fallbacks."""
    api_key = os.environ.get("RAWG_API_KEY", "").strip()
    if not api_key:
        return [], "missing_key"
    query = str(query or "").strip()
    if not query:
        return [], "empty_query"

    # RAWG's precise search can legitimately return nothing for long collector
    # queries such as "Microsoft Flight Simulator 2024".  Keep the precise
    # request first, then broaden without silently changing the user's title.
    attempts = [
        {"search": query, "search_precise": "true"},
        {"search": query, "search_precise": "false"},
    ]
    normalized = _search_text(query)
    if normalized != query.casefold():
        attempts.append({"search": normalized, "search_precise": "false"})
    # A final short-title fallback helps with punctuation/edition suffixes.
    words = [w for w in re.split(r"\s+", normalized) if len(w) > 2]
    if len(words) >= 3:
        attempts.append({"search": " ".join(words[:4]), "search_precise": "false"})

    wanted = (platform_name or "").strip().casefold()
    ranked = {}
    for attempt in attempts:
        params = {"key": api_key, "page_size": 40, **attempt}
        data = fetch_json(f"https://api.rawg.io/api/games?{urlencode(params)}", timeout=8)
        if not isinstance(data, dict):
            continue
        rows = data.get("results") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            platforms = []
            for item in row.get("platforms") or []:
                if isinstance(item, dict) and isinstance(item.get("platform"), dict):
                    n = str(item["platform"].get("name") or "").strip()
                    if n:
                        platforms.append(n)
            platform_keys = {normalized_platform(p) for p in platforms}
            if (platform_keys and platform_keys.issubset(NON_PHYSICAL_ONLY)) or normalize_series_title(name) in NON_PHYSICAL_TITLES:
                continue
            if title_requires_physical_addon_proof(name):
                continue
            normalized_platforms = " ".join(platforms).casefold()
            platform_match = False
            if wanted and platforms:
                wanted_canonical = canonical_console_name(platform_name)
                platform_match = any(
                    canonical_console_name(p) == wanted_canonical
                    or wanted_canonical.casefold() in p.casefold()
                    or p.casefold() in wanted_canonical.casefold()
                    for p in platforms
                )
            released = str(row.get("released") or "")
            year = released[:4] if len(released) >= 4 and released[:4].isdigit() else ""
            genres = ", ".join(str(g.get("name")) for g in (row.get("genres") or []) if isinstance(g, dict) and g.get("name"))
            nnorm = _search_text(name)
            qnorm = normalized
            score = SequenceMatcher(None, qnorm, nnorm).ratio()
            qwords = {w for w in qnorm.split() if len(w) > 2}
            nwords = {w for w in nnorm.split() if len(w) > 2}
            score += (len(qwords & nwords) / max(1, len(qwords))) * 0.55
            if qnorm and (qnorm in nnorm or nnorm in qnorm):
                score += 0.35
            if qnorm == nnorm:
                score += 1.0
            if platform_match:
                score += 0.45
            elif wanted and platforms:
                score -= 0.20
            source_id = str(row.get("id") or "")
            key = source_id or (nnorm, tuple(platforms))
            candidate = {
                "name": name,
                "platform": ", ".join(platforms) if platforms else "Unbekannt",
                "platforms": platforms,
                "platform_match": platform_match,
                "year": year,
                "publisher": "",
                "developer": "",
                "genre": genres,
                "cover_url": str(row.get("background_image") or "").strip(),
                "source": "RAWG",
                "source_id": source_id,
            }
            ranked[key] = max(ranked.get(key, (-999, None)), (score, candidate), key=lambda x: x[0])
        # If the precise pass produced good exact-title candidates, keep them;
        # otherwise continue to the broader attempts.
        if ranked and attempt.get("search_precise") == "true":
            best = sorted(ranked.values(), key=lambda x: x[0], reverse=True)
            if best and best[0][0] >= 1.55:
                break

    ordered = sorted(ranked.values(), key=lambda x: x[0], reverse=True)
    return [item for _, item in ordered[:limit]], "ok" if ordered else "no_results"


def search_game_metadata(title, console_name=None):
    """Fallback metadata search after a barcode miss. RAWG first, keyless UPC reverse search second."""
    rawg, rawg_status = rawg_game_search(title, console_name)
    if rawg:
        return rawg, rawg_status
    generic = upcitemdb_title_search(title)
    return generic, rawg_status

def rawg_game_detail(game_id):
    api_key = os.environ.get("RAWG_API_KEY", "").strip()
    if not api_key or not game_id:
        return {}
    data = fetch_json(f"https://api.rawg.io/api/games/{quote(str(game_id))}?{urlencode({'key': api_key})}", timeout=6)
    if not isinstance(data, dict):
        return {}
    publishers = ", ".join(str(x.get("name")) for x in (data.get("publishers") or []) if isinstance(x, dict) and x.get("name"))
    developers = ", ".join(str(x.get("name")) for x in (data.get("developers") or []) if isinstance(x, dict) and x.get("name"))
    genres = ", ".join(str(x.get("name")) for x in (data.get("genres") or []) if isinstance(x, dict) and x.get("name"))
    released = str(data.get("released") or "")
    platforms = []
    for p in data.get("platforms") or []:
        if isinstance(p, dict) and isinstance(p.get("platform"), dict):
            name = str(p["platform"].get("name") or "").strip()
            if name:
                platforms.append(name)
    return {
        "name": str(data.get("name") or "").strip(),
        "publisher": publishers,
        "developer": developers,
        "genre": genres,
        "release_year": released[:4] if len(released) >= 4 and released[:4].isdigit() else "",
        "cover_url": str(data.get("background_image") or "").strip(),
        "platforms": platforms,
    }


def _pc_price(data, key):
    value = data.get(key) if isinstance(data, dict) else None
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return None
    return round(cents / 100.0, 2) if cents > 0 else None


def pricecharting_lookup(game):
    """Return current PriceCharting reference values in USD. API requires a paid token."""
    token = os.environ.get("PRICECHARTING_TOKEN", "").strip()
    if not token:
        return None, "missing_token"
    attempts = []
    if game.barcode:
        attempts.append({"t": token, "upc": game.barcode})
    attempts.append({"t": token, "q": f"{game.title} {game.console.name}"})
    for params in attempts:
        data = fetch_json(f"https://www.pricecharting.com/api/product?{urlencode(params)}", timeout=7)
        if not isinstance(data, dict) or data.get("status") != "success":
            continue
        return {
            "id": str(data.get("id") or ""),
            "product_name": str(data.get("product-name") or game.title),
            "console_name": str(data.get("console-name") or game.console.name),
            "loose": _pc_price(data, "loose-price"),
            "cib": _pc_price(data, "cib-price"),
            "new": _pc_price(data, "new-price"),
            "graded": _pc_price(data, "graded-price"),
            "box_only": _pc_price(data, "box-only-price"),
            "manual_only": _pc_price(data, "manual-only-price"),
            "currency": "USD",
        }, "ok"
    return None, "empty"


def derive_completeness(media_present, box_present, manual_present, sealed):
    if sealed:
        return "Sealed"
    if media_present and box_present and manual_present:
        return "CIB"
    if media_present and box_present:
        return "Item + OVP"
    if media_present and manual_present:
        return "Item + Anleitung"
    if media_present:
        return "Loose"
    if box_present and manual_present:
        return "OVP + Anleitung"
    if box_present:
        return "Nur OVP"
    if manual_present:
        return "Nur Anleitung"
    return "Unvollständig"


def suggested_market_value(prices, completeness):
    if not prices:
        return None
    mapping = {
        "Sealed": "new",
        "CIB": "cib",
        "Loose": "loose",
        "Nur OVP": "box_only",
        "Nur Anleitung": "manual_only",
    }
    key = mapping.get(completeness)
    return prices.get(key) if key else None


def retrobase_platform(console_name):
    name = (console_name or "").lower()
    aliases = [
        (("nintendo 64", "n64"), "Nintendo 64"),
        (("super nintendo", "snes"), "Super Nintendo"),
        (("nintendo entertainment system", "nes"), "Nintendo Entertainment System"),
        (("game boy advance", "gba"), "Game Boy Advance"),
        (("game boy color", "gbc"), "Game Boy Color"),
        (("game boy",), "Game Boy"),
        (("mega drive", "genesis"), "Mega Drive"),
        (("master system",), "Master System"),
        (("game gear",), "Game Gear"),
        (("dreamcast",), "Dreamcast"),
        (("saturn",), "Saturn"),
    ]
    for needles, platform in aliases:
        if any(n in name for n in needles):
            return platform
    return console_name


def retrobase_search(title, console_name):
    params = urlencode({"search": title, "platform": retrobase_platform(console_name), "limit": 12})
    data = fetch_json(f"https://retrobase-collection.com/api/public/v1/games?{params}")
    if not isinstance(data, dict):
        return []
    rows = data.get("data", [])
    if isinstance(rows, dict):
        rows = rows.get("games", rows.get("items", []))
    if not isinstance(rows, list):
        return []
    results = []
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        platform = row.get("platform") or {}
        platform_name = platform.get("name") if isinstance(platform, dict) else platform
        media = row.get("media") or []
        cover = ""
        if isinstance(media, list):
            preferred = next((m for m in media if isinstance(m, dict) and m.get("type") == "box-2D" and str(m.get("region", "")).lower() in {"eu", "de", "wor", "ss"}), None)
            preferred = preferred or next((m for m in media if isinstance(m, dict) and m.get("type") == "box-2D"), None)
            if preferred:
                cover = preferred.get("url") or ""
        results.append({
            "id": str(row.get("id") or ""),
            "name": str(row.get("name") or row.get("title") or "").strip(),
            "platform": str(platform_name or console_name).strip(),
            "year": str(row.get("year") or "").strip(),
            "publisher": str(row.get("publisher") or "").strip() if not isinstance(row.get("publisher"), dict) else str(row.get("publisher", {}).get("name") or "").strip(),
            "developer": str(row.get("developer") or "").strip() if not isinstance(row.get("developer"), dict) else str(row.get("developer", {}).get("name") or "").strip(),
            "genre": str(row.get("genre") or "").strip() if not isinstance(row.get("genre"), dict) else str(row.get("genre", {}).get("name") or "").strip(),
            "region": str(row.get("region") or "PAL").upper(),
            "cover_url": cover,
            "source": "RetroBase Collection",
        })
    return [r for r in results if r["name"]]


def get_or_create_console(name):
    name = canonical_console_name(name)
    console = Console.query.filter(db.func.lower(Console.name) == name.lower()).first()
    if not console:
        console = Console(name=name)
        db.session.add(console)
        db.session.flush()
    return console


def add_owned_collection(game):
    item = collection_for(game)
    if item:
        return item
    item = CollectionItem(game_id=game.id, user_id=active_collection_user_id(), status="owned", completeness="Loose", media_present=True, box_present=False, manual_present=False)
    db.session.add(item)
    return item


def _save_copy_photo(file_obj, item, slot):
    if not file_obj or not getattr(file_obj, "filename", ""):
        return None
    ext = Path(secure_filename(file_obj.filename)).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        return None
    upload_dir = Path(app.root_path) / "static" / "uploads" / "copies"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"copy-{item.id or 'new'}-{slot}-{int(utc_now().timestamp())}{ext}"
    file_obj.save(upload_dir / filename)
    return f"uploads/copies/{filename}"


def _save_hardware_photo(file_obj, item_id, slot):
    if not file_obj or not getattr(file_obj, "filename", ""):
        return None
    ext = Path(secure_filename(file_obj.filename)).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        return None
    upload_dir = Path(app.root_path) / "static" / "uploads" / "hardware"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"hardware-{item_id}-{slot}-{int(utc_now().timestamp())}{ext}"
    file_obj.save(upload_dir / filename)
    return f"uploads/hardware/{filename}"


HARDWARE_MODEL_IMAGE_MAX_BYTES = 8 * 1024 * 1024
HARDWARE_MODEL_IMAGE_MAX_EDGE = 1600
Image.MAX_IMAGE_PIXELS = 25_000_000

IMAGE_ARCHIVE_MAX_BYTES = 10 * 1024 * 1024
IMAGE_ARCHIVE_MAX_EDGE = 1800
IMAGE_ARCHIVE_PREFIX = "/static/uploads/library-images/"


def _is_local_image_reference(value):
    value = str(value or "").strip()
    return value.startswith(("/static/", "static/", "uploads/"))


def _is_public_https_url(value):
    """Reject non-HTTPS and local/private network targets before downloading."""
    try:
        parsed = urlsplit(str(value or "").strip())
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            return False
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        if not infos:
            return False
        for info in infos:
            address = ipaddress.ip_address(info[4][0])
            if (address.is_private or address.is_loopback or address.is_link_local or
                    address.is_multicast or address.is_reserved or address.is_unspecified):
                return False
        return True
    except (OSError, ValueError):
        return False


def archive_image_reference(value, force=False):
    """Download, validate and normalize one remote image into Bibo's archive.

    The source URL is retained in ``ImageAsset`` for traceability.  Callers only
    store the returned local URL, so later provider outages cannot break covers.
    """
    source_url = str(value or "").strip()
    if not source_url:
        return None
    if _is_local_image_reference(source_url):
        return source_url
    source_hash = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    asset = ImageAsset.query.filter_by(source_hash=source_hash).first()
    if asset and asset.status == "archived" and asset.local_url:
        local_path = Path(app.root_path) / asset.local_url.removeprefix("/static/")
        if local_path.is_file():
            return asset.local_url
    if asset and asset.status == "failed" and not force and asset.last_attempt_at:
        if utc_now() - asset.last_attempt_at < timedelta(hours=24):
            return None
    if not asset:
        asset = ImageAsset(source_hash=source_hash, source_url=source_url)
        db.session.add(asset)
    asset.source_url = source_url
    asset.attempts = int(asset.attempts or 0) + 1
    asset.last_attempt_at = utc_now()
    asset.status = "pending"
    asset.error = None
    try:
        if not _is_public_https_url(source_url):
            raise ValueError("Nur öffentliche HTTPS-Bildadressen sind erlaubt.")
        req = Request(source_url, headers={"User-Agent": f"Bibo/{APP_VERSION}", "Accept": "image/*"})
        with urlopen(req, timeout=15) as response:
            final_url = response.geturl()
            if not _is_public_https_url(final_url):
                raise ValueError("Die Bildweiterleitung führt zu keiner öffentlichen HTTPS-Adresse.")
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
            if not content_type.startswith("image/"):
                raise ValueError("Die Adresse liefert keine Bilddatei.")
            raw = response.read(IMAGE_ARCHIVE_MAX_BYTES + 1)
        if not raw or len(raw) > IMAGE_ARCHIVE_MAX_BYTES:
            raise ValueError("Die Bilddatei ist leer oder größer als 10 MB.")
        with Image.open(io.BytesIO(raw)) as opened:
            opened.seek(0)
            opened.load()
            image = ImageOps.exif_transpose(opened)
            if image.width < 24 or image.height < 24:
                raise ValueError("Das Bild ist zu klein.")
            image.thumbnail((IMAGE_ARCHIVE_MAX_EDGE, IMAGE_ARCHIVE_MAX_EDGE), Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            content_hash = hashlib.sha256(raw).hexdigest()
            upload_dir = Path(app.root_path) / "static" / "uploads" / "library-images"
            upload_dir.mkdir(parents=True, exist_ok=True)
            filename = f"image-{content_hash[:32]}.webp"
            target = upload_dir / filename
            if not target.exists():
                image.save(target, "WEBP", quality=88, method=6)
            asset.width, asset.height = image.size
        asset.local_url = f"{IMAGE_ARCHIVE_PREFIX}{filename}"
        asset.byte_size = target.stat().st_size
        asset.status = "archived"
        asset.error = None
        return asset.local_url
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        asset.status = "failed"
        asset.error = str(exc)[:255]
        current_app.logger.warning("Bildarchiv konnte %s nicht übernehmen: %s", _safe_log_url(source_url), exc)
        return None


def archived_or_original_image(value):
    value = str(value or "").strip()
    if not value:
        return None
    return archive_image_reference(value) or value


def external_image_candidates():
    """Return every persisted remote image reference with its owning field."""
    rows = []
    specs = (
        ("Spiele", Game, "cover_url"),
        ("Medien und Karten", CollectorItem, "cover_url"),
        ("Hardwaremodelle", HardwareModel, "reference_image"),
        ("Zubehör", AccessoryItem, "reference_image"),
        ("Reihenkatalog", SeriesEntry, "cover_url"),
    )
    for label, model, field in specs:
        column = getattr(model, field)
        for record in model.query.filter(column.like("https://%")).order_by(model.id).all():
            rows.append((label, record, field, str(getattr(record, field) or "").strip()))
    return rows


def archive_external_image_batch(limit=30, force_failed=False):
    migrated = failed = skipped = 0
    seen = {}
    for label, record, field, source_url in external_image_candidates():
        if migrated + failed >= max(1, min(int(limit or 30), 100)):
            break
        if source_url in seen:
            local_url = seen[source_url]
        else:
            source_hash = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
            known = ImageAsset.query.filter_by(source_hash=source_hash).first()
            if known and known.status == "failed" and not force_failed:
                skipped += 1
                continue
            local_url = archive_image_reference(source_url, force=force_failed)
            seen[source_url] = local_url
        if local_url:
            setattr(record, field, local_url)
            migrated += 1
        else:
            failed += 1
        db.session.commit()
    if migrated:
        refresh_bibo_registry()
    return {"migrated": migrated, "failed": failed, "skipped": skipped, "remaining": len(external_image_candidates())}


def _hardware_model_image_path(reference_image):
    """Return a safe local path only for model images managed by GameCollector."""
    prefix = "/static/uploads/hardware-models/"
    value = str(reference_image or "").strip()
    if not value.startswith(prefix):
        return None
    filename = Path(value[len(prefix):]).name
    if not filename or filename != value[len(prefix):]:
        return None
    return Path(app.root_path) / "static" / "uploads" / "hardware-models" / filename


def _delete_hardware_model_image(reference_image):
    path = _hardware_model_image_path(reference_image)
    if path and path.is_file():
        path.unlink()


def _save_hardware_model_image(file_obj, model_id):
    """Validate, orient and resize an uploaded console-model image."""
    if not file_obj or not getattr(file_obj, "filename", ""):
        return None
    raw = file_obj.read(HARDWARE_MODEL_IMAGE_MAX_BYTES + 1)
    if not raw:
        raise ValueError("Die ausgewählte Bilddatei ist leer.")
    if len(raw) > HARDWARE_MODEL_IMAGE_MAX_BYTES:
        raise ValueError("Das Konsolenmodellbild darf höchstens 8 MB groß sein.")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            if image.width < 80 or image.height < 80:
                raise ValueError("Das Konsolenmodellbild muss mindestens 80 × 80 Pixel groß sein.")
            image.thumbnail(
                (HARDWARE_MODEL_IMAGE_MAX_EDGE, HARDWARE_MODEL_IMAGE_MAX_EDGE),
                Image.Resampling.LANCZOS,
            )
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            upload_dir = Path(app.root_path) / "static" / "uploads" / "hardware-models"
            upload_dir.mkdir(parents=True, exist_ok=True)
            filename = f"model-{model_id}-{secrets.token_hex(8)}.webp"
            target = upload_dir / filename
            image.save(target, "WEBP", quality=88, method=6)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Die Datei ist kein gültiges oder unterstütztes Bild.") from exc
    return f"/static/uploads/hardware-models/{filename}"


def apply_collection_form(item):
    """Compatibility wrapper; all CollectionItem writes use one implementation."""
    return update_collection_item_from_form(item)



@app.route("/health")
def health():
    return {"status": "ok", "name": APP_NAME, "version": APP_VERSION}, 200

@app.route("/health/deep")
def health_deep():
    """Readiness probe including the schema required for the current release."""
    try:
        db.session.execute(text("SELECT 1"))
        tables = set(inspect(db.engine).get_table_names())
        required = {"user", "collection_space", "collection_permission", "collection_access_request", "game", "collection_item", "collector_item", "hardware_item", "accessory_item", "application_error", "capture_batch", "release_coverage", "personal_review", "bibo_work", "bibo_edition", "bibo_copy", "bibo_series", "bibo_series_membership", "storage_location", "loan_record", "inventory_session"}
        missing = sorted(required - tables)
        if missing:
            return {"status":"error","name":APP_NAME,"version":APP_VERSION,"database":"ok","schema":"incomplete","missing_tables":missing}, 503
        return {"status":"ok","name":APP_NAME,"version":APP_VERSION,"database":"ok","schema":"ok","games":Game.query.count(),"collection_items":CollectionItem.query.count(),"library_copies":BiboCopy.query.filter_by(active=True).count()}, 200
    except Exception as exc:
        app.logger.exception("deep healthcheck failed")
        return {"status":"error","version":APP_VERSION,"database":"error","message":str(exc)[:160]}, 503


@app.route("/whats-new")
@login_required
def whats_new():
    releases = [
        ("4.7.0", "Eigene Sammlungskategorien verwalten", "Eigene Dashboard-Bereiche bearbeiten oder entfernen und mehrere Objekte gemeinsam verschieben. Beim Entfernen einer Kategorie bleiben alle Objekte erhalten."),
        ("4.6.5", "Private Rechteverwaltung & sauberer Release-Workflow", "Sammlungsverwalter sehen nur Mitglieder und konkrete Zugriffsanfragen ihrer Sammlung. Eigene Kategorien führen direkt zum ersten Objekt und leere Sammlungen zeigen keine fremden Spielreihen mehr."),
        ("4.6.4", "Getrennte Spielreihen & eigene Dashboard-Bereiche", "Spielreihen erscheinen nur für die aktive Sammlung; zusätzlich lassen sich beliebig viele eigene Sammlungskategorien mit Name und Symbol direkt zum Start- und Bewertungsdashboard hinzufügen."),
        ("4.6.3", "Weitere Exemplare über vorhandene EAN", "Bekannte EANs zeigen eine Dublettenwarnung mit den getrennten Aktionen „vorhandenes Exemplar öffnen“ und „weiteres Exemplar erfassen“; Medien übernehmen Katalogdaten in den Fragenkatalog, ohne persönliche Exemplardaten zu kopieren."),
        ("4.6.2", "Persönliche Rezensionen & Updatearchiv", "Vorhandene Titel erhalten eigene inhaltliche Rezensionen mit Gesamt- und Einzelwertungen; erfolgreiche Installationen verschieben Bibo-Pakete aus Downloads automatisch nach /opt/gamecollector/updates."),
        ("4.6.1", "Ähnliche-Titel-Vorschau & TMDB-Boxinhalt", "Werkseiten zeigen ähnliche Titel als kompakte Coverleiste mit Besitz- oder Wunschlistenstatus; Film-Boxen übernehmen enthaltene Filme direkt aus TMDB-Film-Links oder IDs."),
        ("4.6.0", "Ähnliche Titel & passende Formatauswahl", "Games, Filme, Serien, Bücher, Musik und Sammelkarten erhalten begründete, bebilderte Empfehlungen mit eigener Vorschau, Wunschliste und direkter Übernahme; Medium und Format werden im Fragenkatalog als passende Auswahlliste angeboten."),
        ("4.5.3", "Sichtbare Coverprüfung & korrekte Staffelboxen", "Cover-Links zeigen im Medienassistenten sofort das tatsächliche Bild und erneut in der Abschlusskontrolle; Komplettboxen einzelner Staffeln werden nicht mehr als komplette Serie gewertet."),
        ("4.5.2", "Komplettbox-Aktionen & Kachelstatistiken", "Staffeln einer Box lassen sich mit Aktionsfeldern gesammelt auswählen; ältere Komplettboxen werden automatisch auf alle Serienstaffeln erweitert und jede Dashboard-Kachel zeigt eine kurze Bestandsaufteilung."),
        ("4.5.1", "Fragenkatalog nach EAN-Treffern", "Gefundene Film-, Serien-, Buch-, Musik- und allgemeine EAN-Daten werden vorausgefüllt in den Assistenten übernommen; gespeichert wird erst nach der Abschlusskontrolle."),
        ("4.5.0", "Geführter Medienassistent", "Ein schrittweiser, medienabhängiger Fragenkatalog erfasst Werk, Ausgabe, Boxinhalt, Zustand, Kaufdaten und Lagerort vollständig und verständlich."),
        ("4.4.1", "Komplettboxen für TV-Serien", "Eine physische Komplett- oder Mehrstaffelbox kann ausgewählten Staffeln gemeinsam zugeordnet werden; Preis und Exemplar werden weiterhin nur einmal summiert."),
        ("4.4.0", "Rechte & Betriebssicherheit", "Einzelrechte für Einträge, Preise, Importe und Benutzerverwaltung, exportierbarer Änderungsnachweis sowie eine zentrale Systemdiagnose."),
        ("4.3.0", "Lager, Inventur & Leihen", "Hierarchische Lagerorte mit QR-Code, mobile Bestandsprüfung und eine übersichtliche Leihverwaltung für das gemeinsame Bibliotheksregister."),
        ("4.2.0", "Planungszentrale", "Monatsbudget, tatsächliche Ausgaben, Wünsche, priorisierte Ziele und deutsche Veröffentlichungsstatus werden gemeinsam geplant."),
        ("4.1.0", "Persönlicher Einstieg", "Zeitabhängige Begrüßung, zentrale Hinzufügen-Seite und Strg/⌘+K für die globale Suche."),
        ("4.0.2", "Automatische Cover-Slider", "Bis zu fünf Cover je Bereich wechseln weich und zeitversetzt; Bewegungsreduzierung und Einzelcover werden respektiert."),
        ("4.0.1", "Cover auf der Startseite", "Die großen Bereichskacheln zeigen echte Cover aus der eigenen Sammlung mit einem lesbaren, ruhigen Bildverlauf."),
        ("4.0.0", "Eine Bibliothek für alles", "Das gemeinsame Register verbindet Werke, Reihen, Ausgaben und Exemplare aller Medienarten – nicht-destruktiv und mit eigener Werkansicht."),
        ("3.5.0", "Dashboard mit Sammlungsassistent", "Eigene Cover als Wasserzeichen und priorisierte nächste Schritte statt eintöniger Kennzahlen."),
        ("3.4.0", "Boxsets richtig abbilden", "Eine Box kann mehrere Filme, Staffeln oder Bände abdecken, ohne ihren Preis mehrfach zu zählen."),
        ("3.3.0", "Mobile Stapel-Erfassung", "Mehrere Barcodes unterwegs sammeln, Mengen und Kaufpreise festhalten und später gesammelt zuordnen."),
        ("3.2.0", "Prüf-Inbox", "Daten-, Preis- und Technikhinweise werden in einer gemeinsamen, handlungsorientierten Inbox gebündelt."),
        ("3.1.0", "Komfort & Stabilität", "Kumulative, vollständig geprüfte Ausgabe mit Release-Übersicht und verständlicher Benutzerrechte-Erklärung."),
        ("3.0.15", "Logische Reihenzählung", "Staffeln, Filme und Bände statt einzelner Datenträger; Split-Boxen werden nicht doppelt gezählt."),
        ("3.0.14", "Einheitliche Ansichten", "Listen-/Cover-Ansicht, weiche Cover-Hintergründe und bessere mobile Bedienung in allen Collector-Bereichen."),
        ("3.0.13", "Transparente Preise", "Preisdetails zeigen Quelle, Zeitstand, Spanne, Historie und die besondere PokéCollector-Herkunft."),
        ("3.0.12", "Saubere Sammlungstrennung", "Bewertungsläufe, Serienabgleiche, Offline-Scans und Diagnose bleiben in ihrer jeweiligen Sammlung."),
        ("3.0.11", "Diagnose", "Verständliche Fehlerseiten, Fehlerkennungen und automatische Template-/Routenprüfung."),
    ]
    return render_template("whats_new.html", releases=releases)


@app.errorhandler(403)
def forbidden_page(_error):
    return render_template("http_error.html", code=403, title="Zugriff nicht erlaubt", message="Für diese Aktion fehlen dir in der aktiven Sammlung die erforderlichen Rechte."), 403


@app.errorhandler(404)
def not_found_page(_error):
    return render_template("http_error.html", code=404, title="Seite nicht gefunden", message="Der aufgerufene Eintrag oder Link existiert nicht mehr."), 404


@app.errorhandler(500)
def internal_error_page(error):
    db.session.rollback()
    reference = secrets.token_hex(5).upper()
    try:
        actor_id = current_user.id if current_user.is_authenticated else None
        collection_id = active_collection_user_id() if current_user.is_authenticated else None
        original = getattr(error, "original_exception", None) or error
        db.session.add(ApplicationError(
            reference=reference, collection_user_id=collection_id, actor_user_id=actor_id,
            endpoint=request.endpoint, path=request.path[:1000], method=request.method,
            exception_type=type(original).__name__[:120], message=str(original)[:2000],
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not persist incident %s", reference)
    return render_template("http_error.html", code=500, title="Technischer Fehler", message="Die Anfrage konnte nicht abgeschlossen werden.", reference=reference), 500


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("collector_home"))
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "").strip(), is_system=False).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            session.permanent = True
            login_user(user, remember=True, duration=timedelta(days=SESSION_DAYS))
            return redirect(url_for("collector_home"))
        flash("Benutzername oder Passwort ist falsch.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/collection/scope/<scope>")
@login_required
def collection_scope(scope):
    # Compatibility route for bookmarks from v0.5.1. There is only one collection now.
    session.pop("collection_scope", None)
    target = request.args.get("next") or url_for("dashboard")
    if not str(target).startswith("/") and request.host_url not in str(target):
        target = url_for("dashboard")
    return redirect(target)


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        current_user.display_name = display_name or None
        password = request.form.get("password", "")
        if password:
            if len(password) < 8:
                flash("Das neue Passwort muss mindestens 8 Zeichen lang sein.", "danger")
                return redirect(url_for("account"))
            current_user.password_hash = generate_password_hash(password)
        app_setting_set(f"greeting_enabled_user_{current_user.id}", "1" if request.form.get("greeting_enabled") == "1" else "0")
        style = request.form.get("greeting_style", "friendly")
        app_setting_set(f"greeting_style_user_{current_user.id}", style if style in {"friendly", "neutral"} else "friendly")
        db.session.commit()
        flash("Kontoeinstellungen gespeichert.", "success")
        return redirect(url_for("account"))
    ebay = ebay_credentials()
    tmdb = tmdb_credentials()
    return render_template(
        "account.html", ebay_configured=bool(ebay["client_id"] and ebay["client_secret"]),
        ebay_client_id=ebay["client_id"], ebay_dev_id=ebay["dev_id"],
        ebay_marketplace=ebay["marketplace"], ebay_environment=ebay["environment"],
        tmdb_configured=bool(tmdb["api_key"] or tmdb["token"]),
        tmdb_api_key_configured=bool(tmdb["api_key"]), tmdb_token_configured=bool(tmdb["token"]),
        pokecollector=pokecollector_credentials(),
        pokecollector_configured=bool(pokecollector_credentials()["base_url"]),
        pokecollector_password_configured=bool(pokecollector_credentials()["password"]),
        greeting_enabled=app_setting_get(f"greeting_enabled_user_{current_user.id}", "1") != "0",
        greeting_style=app_setting_get(f"greeting_style_user_{current_user.id}", "friendly"),
    )


MARKET_MOVEMENT_PERIODS = {
    "latest": {"label": "Letzte Bewertung", "days": None},
    "1d": {"label": "24 Stunden", "days": 1},
    "7d": {"label": "7 Tage", "days": 7},
    "30d": {"label": "30 Tage", "days": 30},
}


def collection_market_movement(period, game_items, hardware_items, accessory_items, collector_items=None):
    """Compare successful automatic valuations without treating stock as profit.

    Games and the generic Collector modules use their activity rows because
    these also record unchanged checks. Hardware and accessories use their
    complete price histories. Manual estimates never participate in market
    movement.
    """
    period = period if period in MARKET_MOVEMENT_PERIODS else "latest"
    days = MARKET_MOVEMENT_PERIODS[period]["days"]
    cutoff = utc_now() - timedelta(days=days) if days else None
    rows = []
    new_count = 0

    def append_row(kind, item, label, subtitle, url, current, previous,
                   source, recorded_at, quantity=1, counts_in_total=True):
        nonlocal new_count
        if previous is None:
            if counts_in_total:
                new_count += max(1, int(quantity or 1))
            return
        current = float(current)
        previous = float(previous)
        quantity = max(1, int(quantity or 1))
        delta = round(current - previous, 2)
        impact = round(delta * quantity, 2) if counts_in_total else 0.0
        pct = round(delta / previous * 100, 2) if previous else 0.0
        rows.append({
            "kind": kind, "item": item, "label": label,
            "subtitle": subtitle, "url": url, "current": current,
            "previous": previous, "delta": delta, "impact": impact,
            "pct": pct, "source": source or "Automatischer Marktwert",
            "recorded_at": recorded_at, "quantity": quantity,
            "included_in_set": not counts_in_total,
        })

    for item in game_items:
        activity = sorted(item.price_activity, key=lambda row: row.recorded_at or datetime.min)
        if not activity:
            continue
        if period == "latest":
            latest = activity[-1]
            previous = latest.previous_value_eur
        else:
            window = [row for row in activity if row.recorded_at and row.recorded_at > cutoff]
            if not window:
                continue
            latest = window[-1]
            previous = window[0].previous_value_eur
        append_row(
            "game", item, item.game.title, item.game.console.name,
            url_for("game_detail", game_id=item.game.id), latest.value_eur,
            previous, latest.source, latest.recorded_at,
        )

    def history_values(history):
        ordered = sorted(history, key=lambda row: row.recorded_at or datetime.min)
        if not ordered:
            return None
        if period == "latest":
            if len(ordered) < 2:
                return ordered[-1], None
            return ordered[-1], ordered[-2].value_eur
        window = [row for row in ordered if row.recorded_at and row.recorded_at > cutoff]
        if not window:
            return None
        baseline = next((row for row in reversed(ordered) if row.recorded_at and row.recorded_at <= cutoff), None)
        return window[-1], baseline.value_eur if baseline else None

    for item in hardware_items:
        values = history_values(item.price_history)
        if not values:
            continue
        latest, previous = values
        append_row(
            "hardware", item, item.model.name,
            " · ".join(x for x in (item.model.model_number, item.completeness) if x),
            url_for("hardware_detail", model_id=item.hardware_model_id),
            latest.value_eur, previous, latest.source, latest.recorded_at,
        )

    for item in accessory_items:
        values = history_values(item.price_history)
        if not values:
            continue
        latest, previous = values
        append_row(
            "accessory", item, item.name,
            item.console.name if item.console else "Universal",
            url_for("accessory_item_edit", item_id=item.id), latest.value_eur,
            previous, latest.source, latest.recorded_at,
            item.quantity, accessory_counts_in_total(item),
        )

    collector_labels = {
        "movies": "Film", "tv": "TV-Serie", "books": "Buch",
        "music": "Musik", "cards": "Sammelkarte", "custom": "Eigene Sammlung",
    }
    for item in collector_items or []:
        if is_pokemon_card(item):
            continue
        activity = sorted(item.collector_price_activity, key=lambda row: row.recorded_at or datetime.min)
        if not activity:
            continue
        if period == "latest":
            latest = activity[-1]
            previous = latest.previous_value_eur
        else:
            window = [row for row in activity if row.recorded_at and row.recorded_at > cutoff]
            if not window:
                continue
            latest = window[-1]
            previous = window[0].previous_value_eur
        append_row(
            item.category, item, item.title,
            item.edition or item.media_type or collector_labels.get(item.category, "Sammlungsobjekt"),
            url_for("collector_item_detail", item_id=item.id), latest.value_eur,
            previous, latest.source, latest.recorded_at, item.quantity,
        )

    movement_kinds = ("game", "hardware", "accessory", "movies", "tv", "books", "music", "cards", "custom")
    category_delta = {kind: round(sum(r["impact"] for r in rows if r["kind"] == kind), 2) for kind in movement_kinds}
    market_delta = round(sum(category_delta.values()), 2)
    winners = sorted((r for r in rows if r["impact"] > 0), key=lambda r: (r["impact"], r["pct"]), reverse=True)[:10]
    losers = sorted((r for r in rows if r["impact"] < 0), key=lambda r: (r["impact"], r["pct"]))[:10]
    unchanged_count = sum(1 for r in rows if r["delta"] == 0)
    return {
        "period": period, "period_label": MARKET_MOVEMENT_PERIODS[period]["label"],
        "rows": rows, "winners": winners, "losers": losers,
        "market_delta": market_delta, "category_delta": category_delta,
        "new_count": new_count, "unchanged_count": unchanged_count,
    }


def _bibo_identity_key(media_kind, identity):
    normalized = unicodedata.normalize("NFKD", str(identity or "")).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-") or "unbekannt"
    digest = hashlib.sha256(f"{media_kind}:{normalized}".encode("utf-8")).hexdigest()[:16]
    return f"{media_kind}:{normalized[:260]}:{digest}"


def refresh_bibo_registry():
    """Synchronize the v4 work/series/edition/copy compatibility index.

    No legacy row is changed or deleted. Missing source rows are merely marked
    inactive, making the migration reversible while preserving registry IDs.
    """
    owner = shared_collection_user()
    owner_id = owner.id if owner else None
    # Recommendations placed on the wishlist are native Bibo rows rather than
    # legacy mirrors, so a registry refresh must preserve them.
    BiboCopy.query.filter(BiboCopy.source_kind != "discovery").update({BiboCopy.active: False}, synchronize_session=False)
    BiboEdition.query.filter(BiboEdition.source_kind != "discovery").update({BiboEdition.active: False}, synchronize_session=False)
    BiboSeries.query.update({BiboSeries.active: False}, synchronize_session=False)
    BiboSeriesMembership.query.update({BiboSeriesMembership.active: False}, synchronize_session=False)

    def upsert_work(media_kind, identity, title, series_name=None, metadata=None, **values):
        key = _bibo_identity_key(media_kind, identity)
        work = BiboWork.query.filter_by(canonical_key=key).first()
        if not work:
            work = BiboWork(canonical_key=key, media_kind=media_kind, title=title or "Ohne Titel", sort_title=(title or "Ohne Titel").casefold())
            db.session.add(work)
        work.media_kind = media_kind
        work.title = title or "Ohne Titel"
        work.sort_title = work.title.casefold()
        work.series_name = series_name or None
        work.metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        for field, value in values.items():
            setattr(work, field, value)
        db.session.flush()
        return work

    def upsert_series(work, media_kind, title, position=None, image_url=None):
        if not str(title or "").strip():
            return None
        key = _bibo_identity_key(f"series-{media_kind}", title)
        series = BiboSeries.query.filter_by(canonical_key=key).first()
        if not series:
            series = BiboSeries(canonical_key=key, media_kind=media_kind, title=str(title).strip())
            db.session.add(series)
        series.media_kind = media_kind
        series.title = str(title).strip()
        series.image_url = series.image_url or image_url
        series.active = True
        db.session.flush()
        membership = BiboSeriesMembership.query.filter_by(series_id=series.id, work_id=work.id).first()
        if not membership:
            membership = BiboSeriesMembership(series_id=series.id, work_id=work.id)
            db.session.add(membership)
        membership.position_label = str(position)[:80] if position not in (None, "") else None
        membership.active = True
        return series

    def upsert_edition(work, source_kind, source_id, **values):
        sid = str(source_id)
        edition = BiboEdition.query.filter_by(source_kind=source_kind, source_id=sid).first()
        if not edition:
            edition = BiboEdition(work_id=work.id, source_kind=source_kind, source_id=sid)
            db.session.add(edition)
        edition.work_id = work.id
        edition.active = True
        for field, value in values.items():
            setattr(edition, field, value)
        db.session.flush()
        return edition

    def upsert_copy(edition, source_kind, source_id, status="owned", ownership_format="physical", quantity=1, copy_owner_id=None, **values):
        sid = str(source_id)
        copy = BiboCopy.query.filter_by(source_kind=source_kind, source_id=sid).first()
        if not copy:
            copy = BiboCopy(edition_id=edition.id, source_kind=source_kind, source_id=sid)
            db.session.add(copy)
        copy.edition_id = edition.id
        copy.owner_id = copy_owner_id or owner_id
        copy.status = status or "owned"
        copy.ownership_format = ownership_format or "physical"
        copy.quantity = max(int(quantity or 1), 1)
        copy.active = True
        for field, value in values.items():
            setattr(copy, field, value)

    for item in CollectionItem.query.options(joinedload(CollectionItem.game).joinedload(Game.console)).all():
        game = item.game
        work = upsert_work("games", game.title, game.title, game.franchise, {"legacy_game_id": game.id},
                           external_source=game.external_source, external_id=game.external_id,
                           logical_unit_key=_bibo_identity_key("games", game.title),
                           availability_de="digital" if item.ownership_format == "digital" else ("never_physical_de" if game.physical_status == "excluded" else "physical"),
                           cover_url=game.cover_url)
        upsert_series(work, "games", game.franchise, game.series_group or game.series_generation, game.cover_url)
        edition = upsert_edition(work, "game", game.id, format_label=game.edition or "Standard", platform=game.console.name if game.console else None, region=game.region, release_year=game.release_year, image_url=game.cover_url,
                                 barcode=game.barcode, language=game.language, country=game.region, release_status=work.availability_de, content_count=1)
        upsert_copy(edition, "game", item.id, item.status, item.ownership_format, 1, item.user_id,
                    purchase_price_eur=item.purchase_price, effective_value_eur=effective_value(item),
                    condition_label=f"Medium {item.media_condition or '-'} / Box {item.box_condition or '-'}",
                    completeness_label=item.completeness, storage_location=item.storage_location, acquired_at=item.purchase_date)

    for item in CollectorItem.query.all():
        meta = {}
        try:
            meta = json.loads(item.metadata_json or "{}")
        except (TypeError, ValueError):
            pass
        series_name, series_order = infer_collector_group(item)
        logical_key = logical_collection_unit_key(item, meta, series_order)
        identity = f"{series_name}:{logical_key}" if series_name else logical_key
        availability = meta.get("de_physical_release_status") or ("digital" if str(item.media_type or "").casefold() == "digital" else "physical")
        work = upsert_work(item.category, identity, item.title, series_name, {"legacy_collector_item_id": item.id},
                           external_source=item.external_source, external_id=item.external_id,
                           logical_unit_key=logical_key, availability_de=availability, cover_url=item.cover_url)
        upsert_series(work, item.category, series_name, series_order, item.cover_url)
        coverage_count = ReleaseCoverage.query.filter_by(owner_id=item.user_id, source_kind="collector", source_id=str(item.id)).count()
        edition = upsert_edition(work, "collector", item.id, format_label=item.edition or item.media_type, release_year=item.release_year, image_url=item.cover_url,
                                 barcode=item.barcode, language=meta.get("language") or item.card_language,
                                 country=meta.get("physical_country"), release_status=availability, content_count=max(coverage_count, 1))
        upsert_copy(edition, "collector", item.id, meta.get("status") or "owned", meta.get("ownership_format") or ("digital" if availability == "digital" else "physical"), item.quantity, item.user_id,
                    purchase_price_eur=item.purchase_price_eur, effective_value_eur=collector_effective_value(item),
                    condition_label=item.condition, completeness_label=item.completeness,
                    storage_location=item.storage_location, acquired_at=item.purchase_date)

    for item in HardwareItem.query.options(joinedload(HardwareItem.model).joinedload(HardwareModel.console)).all():
        model = item.model
        console_name = model.console.name if model.console else "Hardware"
        work = upsert_work("hardware", console_name, console_name, metadata={"legacy_console_id": model.console_id}, logical_unit_key=_bibo_identity_key("hardware", console_name), availability_de="physical", cover_url=model.reference_image)
        edition = upsert_edition(work, "hardware", model.id, format_label=model.name, platform=console_name, region=model.region, release_year=model.release_year, image_url=model.reference_image, country=model.region, release_status="physical", content_count=1)
        upsert_copy(edition, "hardware", item.id, item.status, "physical", 1, item.user_id or owner_id,
                    purchase_price_eur=item.purchase_price, effective_value_eur=effective_hardware_value(item),
                    condition_label=str(item.condition) if item.condition is not None else None,
                    completeness_label=item.completeness, storage_location=item.storage_location, acquired_at=item.purchase_date)

    for item in AccessoryItem.query.options(joinedload(AccessoryItem.console)).all():
        work = upsert_work("accessories", f"{item.name}:{item.model_number or ''}", item.name, metadata={"legacy_accessory_id": item.id}, logical_unit_key=_bibo_identity_key("accessories", f"{item.name}:{item.model_number or ''}"), availability_de="physical", cover_url=item.reference_image or item.photo)
        edition = upsert_edition(work, "accessory", item.id, format_label=accessory_category_label(item.category), platform=item.console.name if item.console else None, image_url=item.reference_image or item.photo, barcode=item.barcode, release_status="physical", content_count=1)
        upsert_copy(edition, "accessory", item.id, item.status, "physical", item.quantity, item.user_id or owner_id,
                    purchase_price_eur=item.purchase_price, effective_value_eur=effective_accessory_value(item),
                    condition_label=str(item.condition) if item.condition is not None else None,
                    completeness_label="Mit OVP" if item.boxed else "Ohne OVP", storage_location=item.storage_location)

    db.session.commit()
    return BiboCopy.query.filter_by(active=True).count()


BIBO_KIND_LABELS = {
    "games": "Spiele", "movies": "Filme", "tv": "TV-Serien", "books": "Bücher",
    "music": "Musik", "cards": "Sammelkarten", "custom": "Sonstiges",
    "hardware": "Hardware", "accessories": "Zubehör",
}


@app.route("/library")
@login_required
def bibo_library():
    refresh_bibo_registry()
    query_text = request.args.get("q", "").strip()
    selected_kind = request.args.get("kind", "all").strip()
    selected_status = request.args.get("status", "all").strip()
    copies = BiboCopy.query.options(joinedload(BiboCopy.edition).joinedload(BiboEdition.work)).filter_by(active=True, owner_id=active_collection_user_id()).all()
    rows = []
    for copy in copies:
        edition, work = copy.edition, copy.edition.work
        value = None
        link = None
        subtitle = " · ".join(part for part in (edition.platform, edition.format_label, edition.region) if part)
        if copy.source_kind == "game":
            source = db.session.get(CollectionItem, int(copy.source_id))
            if source:
                value, link = effective_value(source), url_for("game_detail", game_id=source.game_id)
        elif copy.source_kind == "collector":
            source = db.session.get(CollectorItem, int(copy.source_id))
            if source:
                value, link = collector_effective_value(source), url_for("collector_item_detail", item_id=source.id)
        elif copy.source_kind == "hardware":
            source = db.session.get(HardwareItem, int(copy.source_id))
            if source:
                value, link = effective_hardware_value(source), url_for("hardware_detail", model_id=source.hardware_model_id)
        elif copy.source_kind == "discovery":
            try:
                payload = (json.loads(work.metadata_json or "{}") or {}).get("discovery_payload") or {}
            except (TypeError, ValueError):
                payload = {}
            link = url_for("discovery_preview", token=_discovery_token(payload)) if payload else url_for("discovery_center", type=work.media_kind)
        elif copy.source_kind == "accessory":
            source = db.session.get(AccessoryItem, int(copy.source_id))
            if source:
                value, link = effective_accessory_value(source), url_for("accessory_item_edit", item_id=source.id)
        total_value = (float(value) * max(copy.quantity or 1, 1)) if value is not None else None
        row = {"copy_row": copy, "edition": edition, "work": work, "kind_label": BIBO_KIND_LABELS.get(work.media_kind, work.media_kind), "subtitle": subtitle, "value": value, "total_value": total_value, "legacy_link": link, "link": url_for("bibo_work_detail", work_id=work.id)}
        haystack = " ".join((work.title, work.series_name or "", subtitle)).casefold()
        if query_text and query_text.casefold() not in haystack:
            continue
        if selected_kind != "all" and work.media_kind != selected_kind:
            continue
        if selected_status != "all" and copy.status != selected_status:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (row["work"].sort_title, row["edition"].platform or "", row["copy_row"].id))
    stats = {
        "works": len({row["work"].id for row in rows}),
        "series": len({membership.series_id for row in rows for membership in row["work"].series_memberships if membership.active}),
        "editions": len({row["edition"].id for row in rows}),
        "copies": sum(max(row["copy_row"].quantity or 1, 1) for row in rows),
        "value": round(sum(row["total_value"] or 0 for row in rows), 2),
    }
    kinds = sorted({row.edition.work.media_kind for row in copies}, key=lambda key: BIBO_KIND_LABELS.get(key, key))
    return render_template("bibo_library.html", rows=rows, stats=stats, kinds=kinds, kind_labels=BIBO_KIND_LABELS, selected_kind=selected_kind, selected_status=selected_status, query_text=query_text)


def bibo_registry_health(owner_id=None):
    owner_id = owner_id or active_collection_user_id()
    copies = BiboCopy.query.filter_by(active=True, owner_id=owner_id).all()
    return {
        "works": len({copy.edition.work_id for copy in copies}),
        "series": len({membership.series_id for copy in copies for membership in copy.edition.work.series_memberships if membership.active}),
        "editions": len({copy.edition_id for copy in copies}),
        "copies": sum(max(copy.quantity or 1, 1) for copy in copies),
        "without_value": sum(1 for copy in copies if copy.effective_value_eur is None),
        "without_identity": sum(1 for copy in copies if not copy.edition.work.logical_unit_key),
        "without_cover": sum(1 for copy in copies if not (copy.edition.image_url or copy.edition.work.cover_url)),
    }


@app.route("/library/work/<int:work_id>")
@login_required
def bibo_work_detail(work_id):
    work = db.get_or_404(BiboWork, work_id)
    owner_id = active_collection_user_id()
    copies = (BiboCopy.query.options(joinedload(BiboCopy.edition))
              .join(BiboEdition).filter(BiboEdition.work_id == work.id, BiboCopy.owner_id == owner_id, BiboCopy.active.is_(True))
              .order_by(BiboEdition.release_year, BiboEdition.platform, BiboCopy.id).all())
    if not copies:
        abort(404)
    rows = []
    for copy in copies:
        legacy_link = None
        coverage = []
        try:
            source_id = int(copy.source_id)
        except (TypeError, ValueError):
            source_id = None
        if copy.source_kind == "game" and source_id:
            source = db.session.get(CollectionItem, source_id)
            legacy_link = url_for("game_detail", game_id=source.game_id) if source else None
        elif copy.source_kind == "collector" and source_id:
            source = db.session.get(CollectorItem, source_id)
            legacy_link = url_for("collector_item_detail", item_id=source.id) if source else None
            coverage = ReleaseCoverage.query.filter_by(owner_id=owner_id, source_kind="collector", source_id=str(source_id)).order_by(ReleaseCoverage.target_title).all()
        elif copy.source_kind == "hardware" and source_id:
            source = db.session.get(HardwareItem, source_id)
            legacy_link = url_for("hardware_detail", model_id=source.hardware_model_id) if source else None
        elif copy.source_kind == "discovery":
            try:
                payload = (json.loads(work.metadata_json or "{}") or {}).get("discovery_payload") or {}
            except (TypeError, ValueError):
                payload = {}
            legacy_link = url_for("discovery_preview", token=_discovery_token(payload)) if payload else url_for("discovery_center", type=work.media_kind)
        elif copy.source_kind == "accessory" and source_id:
            legacy_link = url_for("accessory_item_edit", item_id=source_id)
        rows.append({"copy": copy, "edition": copy.edition, "legacy_link": legacy_link, "coverage": coverage})
    memberships = [membership for membership in work.series_memberships if membership.active and membership.series.active]
    return render_template("bibo_work_detail.html", work=work, rows=rows, memberships=memberships, kind_label=BIBO_KIND_LABELS.get(work.media_kind, work.media_kind))


@app.route("/library/registry", methods=["GET", "POST"])
@login_required
def bibo_registry_status():
    if request.method == "POST":
        count = refresh_bibo_registry()
        flash(f"Gemeinsames Register aktualisiert: {count} aktive Exemplare.", "success")
        return redirect(url_for("bibo_registry_status"))
    return render_template("bibo_registry_status.html", stats=bibo_registry_health())


DISCOVERY_CATEGORIES = {
    "games": ("🎮", "Games"), "movies": ("🎬", "Filme"), "tv": ("📺", "Serien"),
    "books": ("📚", "Bücher"), "music": ("💿", "Musik"), "cards": ("🃏", "Sammelkarten"),
}
DISCOVERY_AVAILABILITY = {
    "physical": "Physisch in DE bestätigt", "never_physical_de": "Nie physisch in DE erschienen",
    "digital": "Nur digital", "unknown": "DE-Status ungeklärt",
}


def _discovery_serializer():
    return URLSafeSerializer(app.config["SECRET_KEY"], salt="bibo-discovery-v1")


def _discovery_token(payload):
    safe = {key: value for key, value in dict(payload or {}).items() if key in {
        "category", "source", "source_id", "title", "year", "cover_url", "reason",
        "availability", "media_type", "author", "artist", "tcg", "set_name", "set_code",
        "local_game_id", "platform", "genre",
    } and value not in (None, "")}
    return _discovery_serializer().dumps(safe)


def _discovery_payload(token):
    try:
        data = _discovery_serializer().loads(str(token or ""))
    except BadSignature:
        abort(400)
    if not isinstance(data, dict) or data.get("category") not in DISCOVERY_CATEGORIES or not str(data.get("title") or "").strip():
        abort(400)
    return data


def _discovery_key(payload):
    identity = str(payload.get("source_id") or _match_key(payload.get("title"))).strip().casefold()
    return f"{payload.get('category')}:{str(payload.get('source') or 'unknown').casefold()}:{identity}"


def _discovery_hidden(owner_id):
    try:
        values = json.loads(app_setting_get(f"discovery_hidden_{int(owner_id)}", "[]") or "[]")
        return {str(value) for value in values} if isinstance(values, list) else set()
    except (TypeError, ValueError):
        return set()


def _set_discovery_hidden(owner_id, values):
    app_setting_set(f"discovery_hidden_{int(owner_id)}", json.dumps(sorted(set(values))[-500:], ensure_ascii=False))


def _discovery_owned_identity(owner_id, category):
    states = _discovery_collection_states(owner_id, category)
    return set(states["external"]), set(states["titles"])


def _discovery_collection_states(owner_id, category):
    """Resolve collection state and best local target for recommendation badges."""
    external, titles = {}, {}
    priority = {"wishlist": 1, "owned": 2}
    review_source = "game" if category == "games" else "collector"
    review_ratings = {row.source_id: row.overall_rating for row in PersonalReview.query.filter_by(user_id=current_user.id, source_kind=review_source).all()}

    def remember(source, source_id, title, state, link, rating=None):
        value = {"state": state, "link": link, "rating": rating}
        title_key = _match_key(title)
        if title_key and priority.get(state, 0) >= priority.get((titles.get(title_key) or {}).get("state"), 0):
            titles[title_key] = value
        if source and source_id:
            key = (str(source).casefold(), str(source_id).casefold())
            if priority.get(state, 0) >= priority.get((external.get(key) or {}).get("state"), 0):
                external[key] = value

    if category == "games":
        rows = (CollectionItem.query.options(joinedload(CollectionItem.game))
                .filter(CollectionItem.user_id == owner_id, CollectionItem.status.in_(["owned", "wishlist"])).all())
        for copy in rows:
            game = copy.game
            state = "owned" if copy.status == "owned" else "wishlist"
            link = url_for("game_detail", game_id=game.id)
            rating = review_ratings.get(str(game.id))
            remember(game.external_source, game.external_id, game.title, state, link, rating)
            remember("Bibo-Katalog", game.id, game.title, state, link, rating)
    else:
        for row in CollectorItem.query.filter_by(user_id=owner_id, category=category).all():
            remember(row.external_source, row.external_id, row.title, "owned", url_for("collector_item_detail", item_id=row.id), review_ratings.get(str(row.id)))
    wish_rows = (BiboCopy.query.options(joinedload(BiboCopy.edition).joinedload(BiboEdition.work))
                 .filter_by(owner_id=owner_id, source_kind="discovery", status="wishlist", active=True).all())
    for copy in wish_rows:
        work = copy.edition.work
        if work.media_kind != category:
            continue
        remember(work.external_source, work.external_id, work.title, "wishlist", url_for("bibo_work_detail", work_id=work.id))
    return {"external": external, "titles": titles}


def _discovery_candidate_state(payload, states):
    pair = (str(payload.get("source") or "").casefold(), str(payload.get("source_id") or "").casefold())
    match = states["external"].get(pair) or states["titles"].get(_match_key(payload.get("title")))
    if match:
        label = "Im Besitz" if match["state"] == "owned" else "Auf der Wunschliste"
        if match.get("rating"):
            label += f" · {match['rating']}/10"
        return {**match, "label": label}
    return {"state": "missing", "label": "Nicht in der Sammlung", "link": None}


def _discovery_seed_rows(owner_id, category):
    if category == "games":
        rows = (CollectionItem.query.options(joinedload(CollectionItem.game).joinedload(Game.console))
                .filter_by(user_id=owner_id, status="owned").order_by(CollectionItem.added_at.desc(), CollectionItem.id.desc()).all())
        return [{"id": row.game.id, "title": row.game.title, "row": row.game} for row in rows if row.game]
    rows = CollectorItem.query.filter_by(user_id=owner_id, category=category).order_by(CollectorItem.added_at.desc(), CollectorItem.id.desc()).all()
    return [{"id": row.id, "title": row.title, "row": row} for row in rows]


def _discovery_media_candidates(category, seed, limit=18):
    row = seed["row"]; out = []
    if category in {"movies", "tv"}:
        meta = collector_metadata(row)
        tmdb_id = str(meta.get("tmdb_id") or (row.external_id if str(row.external_source or "").upper() == "TMDB" else "") or "").strip()
        if not tmdb_id:
            return [], "Für diesen Ausgangstitel fehlt noch die TMDB-ID. Aktualisiere zuerst seine Metadaten."
        media = "tv" if category == "tv" else "movie"
        data = tmdb_json(f"{media}/{quote(tmdb_id, safe='')}/recommendations", {"language": "de-DE", "page": 1}) or {}
        hits = data.get("results") or [] if isinstance(data, dict) else []
        if not hits:
            data = tmdb_json(f"{media}/{quote(tmdb_id, safe='')}/similar", {"language": "de-DE", "page": 1}) or {}
            hits = data.get("results") or [] if isinstance(data, dict) else []
        for hit in hits:
            title = hit.get("name") if category == "tv" else hit.get("title")
            date_value = hit.get("first_air_date") if category == "tv" else hit.get("release_date")
            if not title or not hit.get("id"): continue
            out.append({"category": category, "source": "TMDB", "source_id": str(hit["id"]), "title": str(title),
                        "year": str(date_value or "")[:4] or None, "cover_url": tmdb_poster_url(hit.get("poster_path")),
                        "reason": f"Ähnlich wie {row.title}", "availability": "unknown",
                        "media_type": "DVD" if category == "tv" else "Blu-ray"})
    elif category == "books":
        meta = collector_metadata(row); author = str(meta.get("author") or "").split(",", 1)[0].strip()
        if not author: return [], "Für dieses Buch fehlt noch der Autor. Aktualisiere zuerst seine Metadaten."
        for hit in openlibrary_search_books(query=f'author:"{author}"', limit=limit):
            out.append({"category": "books", "source": "Open Library", "source_id": hit.get("id") or hit.get("isbn"),
                        "title": hit.get("title"), "year": hit.get("year"), "cover_url": hit.get("cover_url"),
                        "reason": f"Mehr von {author}", "availability": "unknown", "media_type": "Buch", "author": hit.get("author") or author})
    elif category == "music":
        meta = collector_metadata(row); artist = str(meta.get("artist") or "").split(",", 1)[0].strip()
        if not artist: return [], "Für diese Veröffentlichung fehlt noch der Interpret. Aktualisiere zuerst ihre Metadaten."
        for hit in musicbrainz_search_releases(f'artist:"{artist}"', limit=limit, search_mode="text"):
            out.append({"category": "music", "source": "MusicBrainz", "source_id": hit.get("id"), "title": hit.get("title"),
                        "year": hit.get("year"), "cover_url": hit.get("cover_url"), "reason": f"Mehr von {artist}",
                        "availability": "unknown", "media_type": hit.get("format") or "CD", "artist": hit.get("artist") or artist})
    elif category == "cards":
        meta = collector_metadata(row); tcg = collector_card_tcg_name(row); set_name = row.card_set or row.edition or "diesem Set"
        set_meta = meta.get("set") if isinstance(meta.get("set"), dict) else {}
        pokemon_set_id = meta.get("set_id") or set_meta.get("id")
        if tcg == "Pokémon" and pokemon_set_id:
            data = tcgdex_json("sets/" + quote(str(pokemon_set_id), safe="")) or {}; hits = data.get("cards") or [] if isinstance(data, dict) else []
            for hit in hits:
                image = hit.get("image")
                if image and not str(image).lower().endswith((".png", ".jpg", ".jpeg", ".webp")): image = str(image) + "/high.webp"
                out.append({"category":"cards","source":"TCGdex","source_id":hit.get("id"),"title":hit.get("name"),"cover_url":image,
                            "reason":f"Ebenfalls aus {set_name}","availability":"unknown","media_type":"Einzelkarte","tcg":"Pokémon","set_name":set_name,"set_code":pokemon_set_id})
        elif tcg == "Magic: The Gathering" and meta.get("set_code"):
            data = _tcg_json_url("https://api.scryfall.com/cards/search", {"q":f"set:{meta.get('set_code')}","order":"collector"}) or {}
            for hit in (data.get("data") or []) if isinstance(data, dict) else []:
                faces=hit.get("card_faces") or [{}]; images=hit.get("image_uris") or (faces[0].get("image_uris") or {})
                out.append({"category":"cards","source":"Scryfall","source_id":hit.get("id"),"title":hit.get("printed_name") or hit.get("name"),
                            "year":str(hit.get("released_at") or "")[:4] or None,"cover_url":images.get("normal") or images.get("large"),
                            "reason":f"Ebenfalls aus {set_name}","availability":"unknown","media_type":"Einzelkarte","tcg":tcg,
                            "set_name":hit.get("set_name"),"set_code":str(hit.get("set") or "").upper()})
        elif tcg == "Yu-Gi-Oh!" and set_name:
            data = _tcg_json_url("https://db.ygoprodeck.com/api/v7/cardinfo.php", {"cardset":set_name}) or {}
            for hit in (data.get("data") or []) if isinstance(data, dict) else []:
                images=hit.get("card_images") or []; printing=next((value for value in (hit.get("card_sets") or []) if str(value.get("set_name") or "").casefold()==str(set_name).casefold()),{})
                out.append({"category":"cards","source":"YGOPRODeck","source_id":str(hit.get("id") or ""),"title":hit.get("name"),
                            "cover_url":images[0].get("image_url") if images else None,"reason":f"Ebenfalls aus {set_name}","availability":"unknown",
                            "media_type":"Einzelkarte","tcg":tcg,"set_name":set_name,"set_code":printing.get("set_code")})
        if not out: return [], "Für dieses Kartenset konnte der Anbieter keine ähnlichen Karten liefern."
    return out[:limit], None


def _discovery_game_candidates(owner_id, seed, limit=18):
    game=seed["row"]; candidates=[]; query=Game.query.filter(Game.id != game.id)
    if game.franchise: query=query.filter(Game.franchise == game.franchise)
    elif game.genre:
        first_genre=str(game.genre).split(",",1)[0].strip(); query=query.filter(Game.genre.ilike(f"%{first_genre}%"))
    elif game.console_id: query=query.filter(Game.console_id == game.console_id)
    for hit in query.order_by(Game.release_year.desc(),Game.title).limit(limit*2).all():
        if not game_is_physical_candidate(hit): continue
        candidates.append({"category":"games","source":"Bibo-Katalog","source_id":str(hit.id),"local_game_id":hit.id,"title":hit.title,
                           "year":hit.release_year,"cover_url":hit.cover_url,"reason":f"Ähnlich wie {game.title}",
                           "availability":"physical" if hit.physical_status == "physical" else "unknown","media_type":hit.edition or "Standard",
                           "platform":hit.console.name if hit.console else None,"genre":hit.genre})
    if len(candidates)<limit and os.environ.get("RAWG_API_KEY","").strip():
        search_term=game.franchise or (str(game.genre).split(",",1)[0] if game.genre else game.title)
        remote,_status=rawg_game_search(search_term,game.console.name if game.console else None,limit=limit)
        for hit in remote:
            candidates.append({"category":"games","source":"RAWG","source_id":hit.get("source_id"),"title":hit.get("name"),"year":hit.get("year"),
                               "cover_url":hit.get("cover_url"),"reason":f"Ähnlich wie {game.title}","availability":"unknown","media_type":"Standard",
                               "platform":hit.get("platform"),"genre":hit.get("genre")})
    return candidates[:limit],None


def _discovery_add_wishlist(owner_id,payload):
    category=payload["category"]; source=str(payload.get("source") or "Entdecken"); source_id=str(payload.get("source_id") or _match_key(payload["title"])); canonical=_bibo_identity_key(category,f"{source}:{source_id}")
    work=BiboWork.query.filter_by(canonical_key=canonical).first()
    if not work: work=BiboWork(canonical_key=canonical,media_kind=category,title=str(payload["title"])[:255],sort_title=str(payload["title"]).casefold()[:255]); db.session.add(work)
    work.media_kind=category; work.title=str(payload["title"])[:255]; work.sort_title=work.title.casefold(); work.external_source=source[:80]; work.external_id=source_id[:160]
    work.availability_de=str(payload.get("availability") or "unknown")[:32]; work.cover_url=payload.get("cover_url"); work.metadata_json=json.dumps({"discovery_payload":payload},ensure_ascii=False); db.session.flush()
    edition_sid=hashlib.sha256(f"{category}:{source}:{source_id}".encode("utf-8")).hexdigest()[:40]; edition=BiboEdition.query.filter_by(source_kind="discovery",source_id=edition_sid).first()
    if not edition: edition=BiboEdition(work_id=work.id,source_kind="discovery",source_id=edition_sid); db.session.add(edition)
    edition.work_id=work.id; edition.active=True; edition.format_label=str(payload.get("media_type") or "Vorgemerkt")[:120]; edition.platform=str(payload.get("platform") or "")[:160] or None
    edition.release_year=int(payload["year"]) if str(payload.get("year") or "").isdigit() else None; edition.image_url=payload.get("cover_url"); edition.release_status=work.availability_de; edition.metadata_json=work.metadata_json; db.session.flush()
    copy_sid=f"{owner_id}:{edition_sid}"[:80]; copy=BiboCopy.query.filter_by(source_kind="discovery",source_id=copy_sid).first()
    if not copy: copy=BiboCopy(edition_id=edition.id,source_kind="discovery",source_id=copy_sid,owner_id=owner_id); db.session.add(copy)
    copy.edition_id=edition.id; copy.owner_id=owner_id; copy.status="wishlist"; copy.ownership_format="physical"; copy.quantity=1; copy.active=True
    return work


@app.route("/discover")
@login_required
def discovery_center():
    owner_id=active_collection_user_id(); category=str(request.args.get("type") or "movies").strip().lower()
    if category not in DISCOVERY_CATEGORIES: category="movies"
    seeds=_discovery_seed_rows(owner_id,category); selected_id=request.args.get("seed",type=int); seed=next((value for value in seeds if value["id"]==selected_id),None) or (seeds[0] if seeds else None)
    candidates,notice=([],None) if not seed else (_discovery_game_candidates(owner_id,seed) if category=="games" else _discovery_media_candidates(category,seed))
    external,titles=_discovery_owned_identity(owner_id,category); hidden=_discovery_hidden(owner_id); seen=set(); rows=[]
    for payload in candidates:
        if not payload.get("title"): continue
        pair=(str(payload.get("source") or "").casefold(),str(payload.get("source_id") or "").casefold()); key=_discovery_key(payload); title_key=_match_key(payload["title"])
        if key in hidden or pair in external or title_key in titles or key in seen: continue
        seen.add(key); payload["token"]=_discovery_token(payload); payload["availability_label"]=DISCOVERY_AVAILABILITY.get(payload.get("availability"),DISCOVERY_AVAILABILITY["unknown"]); rows.append(payload)
    return render_template("discovery.html",categories=DISCOVERY_CATEGORIES,selected_category=category,seeds=seeds,selected_seed=seed,rows=rows,notice=notice,tmdb_configured=bool(any(tmdb_credentials().values())))


@app.route("/discover/strip/<category>/<int:seed_id>")
@login_required
def discovery_strip(category, seed_id):
    """Small asynchronous preview for a work detail page, including ownership."""
    if category not in DISCOVERY_CATEGORIES:
        abort(404)
    owner_id = active_collection_user_id()
    seed = next((value for value in _discovery_seed_rows(owner_id, category) if value["id"] == seed_id), None)
    if not seed:
        abort(404)
    candidates, _notice = (_discovery_game_candidates(owner_id, seed, limit=10) if category == "games"
                           else _discovery_media_candidates(category, seed, limit=10))
    states = _discovery_collection_states(owner_id, category)
    hidden = _discovery_hidden(owner_id)
    rows, seen = [], set()
    for payload in candidates:
        if not payload.get("title"):
            continue
        key = _discovery_key(payload)
        if key in hidden or key in seen:
            continue
        seen.add(key)
        payload["token"] = _discovery_token(payload)
        status = _discovery_candidate_state(payload, states)
        payload["collection_state"] = status["state"]
        payload["collection_label"] = status["label"]
        payload["target_url"] = status["link"] or url_for("discovery_preview", token=payload["token"])
        rows.append(payload)
        if len(rows) >= 6:
            break
    return render_template("_discovery_strip.html", rows=rows, category=category, seed=seed)


@app.route("/discover/preview/<token>")
@login_required
def discovery_preview(token):
    payload=_discovery_payload(token); payload["token"]=token; payload["availability_label"]=DISCOVERY_AVAILABILITY.get(payload.get("availability"),DISCOVERY_AVAILABILITY["unknown"])
    return render_template("discovery_preview.html",item=payload,category_label=DISCOVERY_CATEGORIES[payload["category"]][1])


@app.route("/discover/action",methods=["POST"])
@login_required
def discovery_action():
    if effective_role()=="viewer": abort(403)
    payload=_discovery_payload(request.form.get("token")); action=str(request.form.get("action") or "").strip().lower(); owner_id=active_collection_user_id()
    if action=="hide":
        hidden=_discovery_hidden(owner_id); hidden.add(_discovery_key(payload)); _set_discovery_hidden(owner_id,hidden); db.session.commit(); flash(f"„{payload['title']}“ wird nicht mehr empfohlen.","success"); return redirect(url_for("discovery_center",type=payload["category"]))
    if action=="wishlist":
        if payload["category"]=="games" and str(payload.get("local_game_id") or "").isdigit():
            game_id=int(payload["local_game_id"]); existing=CollectionItem.query.filter_by(user_id=owner_id,game_id=game_id).first()
            if not existing: db.session.add(CollectionItem(user_id=owner_id,game_id=game_id,status="wishlist",ownership_format="physical",completeness="Loose"))
            elif existing.status!="owned": existing.status="wishlist"
        else: _discovery_add_wishlist(owner_id,payload)
        db.session.commit(); flash(f"„{payload['title']}“ wurde zur Wunschliste hinzugefügt.","success"); return redirect(url_for("discovery_center",type=payload["category"]))
    if action!="add": abort(400)
    if payload["category"]=="games":
        if str(payload.get("local_game_id") or "").isdigit(): return redirect(url_for("collection_configure",game_id=int(payload["local_game_id"]),new=1,new_copy=1))
        return redirect(url_for("game_catalog_search",q=payload["title"]))
    if payload["category"]=="cards":
        tcg={"Pokémon":"pokemon","Magic: The Gathering":"magic","Yu-Gi-Oh!":"yugioh"}.get(payload.get("tcg"),"auto")
        return redirect(url_for("collector_cards_search",q=payload["title"],tcg=tcg,set=payload.get("set_code") or payload.get("set_name") or ""))
    prefill={"category":payload["category"],"title":payload["title"],"release_year":payload.get("year") or "","cover_url":payload.get("cover_url") or "","media_type":payload.get("media_type") or "","source":payload.get("source") or "Entdecken","source_id":payload.get("source_id") or "","from_provider":True}
    if payload["category"] in {"movies","tv"}: prefill["tmdb_id"]=payload.get("source_id") or ""
    if payload["category"]=="books": prefill["author"]=payload.get("author") or ""
    if payload["category"]=="music": prefill["artist"]=payload.get("artist") or ""
    session["media_questionnaire_prefill"]=prefill
    return redirect(url_for("collector_media_questionnaire"))


@app.route("/")
@login_required
def collector_home():
    user_id = active_collection_user_id()
    owned_items = [i for i in CollectionItem.query.filter_by(status="owned", user_id=user_id).all() if game_is_physical_candidate(i.game)]
    game_value = sum((effective_value(i) or 0) for i in owned_items)
    hardware_items = scoped_hardware_query().all()
    accessory_items = scoped_accessory_query().all()
    hardware_value = sum((effective_hardware_value(i) or 0) for i in hardware_items)
    accessory_value = sum((effective_accessory_value(i) or 0) * max(i.quantity or 1, 1) for i in accessory_items if accessory_counts_in_total(i))
    gaming_value = game_value + hardware_value + accessory_value

    module_rows = CollectorItem.query.filter_by(user_id=user_id).all()
    module_stats = {}
    def media_bucket(category, row):
        media = str(row.media_type or "").strip().casefold()
        if category in {"movies", "tv"}:
            if "4k" in media or "uhd" in media: return "4K UHD"
            if "blu" in media: return "Blu-ray"
            if "dvd" in media: return "DVD"
            if "vhs" in media: return "VHS"
            if "digital" in media: return "Digital"
        elif category == "books":
            if "hardcover" in media or "gebunden" in media: return "Hardcover"
            if "taschen" in media or "paperback" in media: return "Taschenbücher"
            if "manga" in media: return "Manga"
            if "comic" in media: return "Comics"
            if "ebook" in media or "e-book" in media or "digital" in media: return "E-Books"
            return "Bücher"
        elif category == "music":
            if "vinyl" in media or '12"' in media or '7"' in media: return "Vinyl"
            if "cd" in media: return "CDs"
            if "kassette" in media or "cassette" in media: return "Kassetten"
            if "digital" in media: return "Digital"
        return str(row.media_type or "Sonstige")[:40]
    for key in ("movies", "tv", "books", "music", "cards", "custom"):
        rows = [row for row in module_rows if row.category == key]
        breakdown = {}
        for row in rows:
            label = media_bucket(key, row)
            breakdown[label] = breakdown.get(label, 0) + max(row.quantity or 1, 1)
        if key in {"movies", "tv"}:
            box_count = sum(max(row.quantity or 1, 1) for row in rows if _collector_multi_part_copy(row))
            if box_count:
                breakdown["Komplett-/Boxsets"] = box_count
        module_stats[key] = {
            "count": sum(max(row.quantity or 1, 1) for row in rows),
            "value": collector_rows_total_value(rows, authoritative_pokemon=(key == "cards")),
            "breakdown": sorted(breakdown.items(), key=lambda item: (-item[1], item[0].casefold()))[:6],
        }
    custom_category_tiles = []
    for category in custom_collection_categories(user_id):
        rows = [row for row in module_rows if row.category == "custom" and collector_metadata(row).get("custom_category") == category["id"]]
        breakdown = {}
        for row in rows:
            label = str(row.media_type or "Objekte")[:40]
            breakdown[label] = breakdown.get(label, 0) + max(row.quantity or 1, 1)
        custom_category_tiles.append({
            **category,
            "count": sum(max(row.quantity or 1, 1) for row in rows),
            "value": collector_rows_total_value(rows),
            "breakdown": sorted(breakdown.items(), key=lambda item: (-item[1], item[0].casefold()))[:6],
            "images": [],
        })
    # For the dashboard card tile, show the three TCGs that actually make up the collection
    # instead of a generic "N objects" label.
    tcg_counts = {}
    for row in module_rows:
        if row.category != "cards":
            continue
        tcg_name = collector_card_tcg_name(row)
        qty=max(row.quantity or 1, 1)
        value=(collector_effective_value(row) or 0) * qty
        entry=tcg_counts.setdefault(tcg_name, {"count":0,"value":0.0})
        entry["count"] += qty
        entry["value"] += float(value or 0)
    # If PokéCollector exposes its portfolio total, use that exact value for
    # Pokémon. This avoids Collector drifting from the source application's total.
    pc_total = pokecollector_portfolio_value()
    if pc_total is not None and "Pokémon" in tcg_counts:
        tcg_counts["Pokémon"]["value"] = float(pc_total)
        module_stats["cards"]["value"] = sum(float(v.get("value") or 0) for v in tcg_counts.values())
    top_card_tcgs = sorted(((name,data["count"],data["value"]) for name,data in tcg_counts.items()), key=lambda item: (-item[1], item[0].casefold()))

    game_platform_counts = {}
    for item in owned_items:
        platform = item.game.console.name if item.game and item.game.console else "Ohne Plattform"
        game_platform_counts[platform] = game_platform_counts.get(platform, 0) + 1
    game_breakdown = sorted(game_platform_counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:5]

    other_count = sum(v["count"] for v in module_stats.values())
    other_value = sum(v["value"] for v in module_stats.values())
    gaming_count = len(owned_items) + len(hardware_items) + sum(max(i.quantity or 1, 1) for i in accessory_items)
    assigned_custom_count = sum(category["count"] for category in custom_category_tiles)
    active_modules = (1
                      + sum(1 for key, value in module_stats.items() if key != "custom" and value["count"] > 0)
                      + sum(1 for category in custom_category_tiles if category["count"] > 0)
                      + (1 if module_stats["custom"]["count"] > assigned_custom_count else 0))
    local_now = local_datetime(utc_now())
    greeting_word = "Guten Morgen" if local_now.hour < 11 else ("Guten Tag" if local_now.hour < 18 else "Guten Abend")
    greeting_enabled = app_setting_get(f"greeting_enabled_user_{current_user.id}", "1") != "0"
    greeting_style = app_setting_get(f"greeting_style_user_{current_user.id}", "friendly")
    last_visit_raw = app_setting_get(f"last_home_visit_user_{current_user.id}", "")
    try:
        last_visit = datetime.fromisoformat(last_visit_raw) if last_visit_raw else None
    except ValueError:
        last_visit = None
    new_activity_count = ActivityLog.query.filter(ActivityLog.collection_user_id == user_id, ActivityLog.created_at > last_visit).count() if last_visit else 0
    app_setting_set(f"last_home_visit_user_{current_user.id}", utc_now().isoformat())
    db.session.commit()
    # Bibo 4.0.1: decorate the start tiles with real images from this collection.
    # The newest usable cover is preferred so the landing page changes naturally
    # as the collection grows; no unrelated stock image is introduced.
    def newest_images(rows, getter, limit=5):
        ordered = sorted(rows, key=lambda row: getattr(row, "added_at", None) or datetime.min, reverse=True)
        images = []
        for row in ordered:
            value = str(getter(row) or "").strip()
            if value and value not in images:
                images.append(value)
            if len(images) >= limit:
                break
        return images
    module_images = {
        "games": newest_images(owned_items, lambda row: row.game.cover_url),
    }
    if not module_images["games"]:
        module_images["games"] = newest_images(hardware_items, lambda row: row.model.reference_image if row.model else None)
    if not module_images["games"]:
        module_images["games"] = newest_images(accessory_items, lambda row: row.reference_image or row.photo)
    for key in ("movies", "tv", "books", "music", "cards", "custom"):
        module_images[key] = newest_images([row for row in module_rows if row.category == key], lambda row: row.cover_url)
    for category in custom_category_tiles:
        category["images"] = newest_images([
            row for row in module_rows
            if row.category == "custom" and collector_metadata(row).get("custom_category") == category["id"]
        ], lambda row: row.cover_url)
    return render_template(
        "collector_home.html",
        game_count=len(owned_items), gaming_value=gaming_value,
        hardware_count=len(hardware_items),
        accessory_count=sum(max(i.quantity or 1, 1) for i in accessory_items),
        module_stats=module_stats,
        collector_count=gaming_count + other_count,
        collector_value=gaming_value + other_value,
        active_modules=active_modules,
        top_card_tcgs=top_card_tcgs,
        game_breakdown=game_breakdown,
        module_images=module_images,
        custom_category_tiles=custom_category_tiles,
        greeting_enabled=greeting_enabled, greeting_style=greeting_style,
        greeting_word=greeting_word, greeting_name=current_user.display_name or current_user.username,
        new_activity_count=new_activity_count,
    )


COLLECTOR_SECTIONS = {
    "movies": {"title": "Filme", "singular": "Film", "icon": "🎬", "description": "DVD, Blu-ray, UHD und weitere Film-Editionen."},
    "tv": {"title": "Serien", "singular": "Serie", "icon": "📺", "description": "Serien, Staffeln und Boxsets verwalten."},
    "books": {"title": "Bücher", "singular": "Buch", "icon": "📚", "description": "Bücher, Ausgaben, Autoren und Buchreihen."},
    "music": {"title": "Musik", "singular": "Album", "icon": "💿", "description": "CDs, Vinyl und weitere Musikveröffentlichungen."},
    "cards": {"title": "Sammelkarten", "singular": "Karte", "icon": "🃏", "description": "Trading Cards, Sets und Einzelkarten."},
    "custom": {"title": "Weitere Sammlungen", "singular": "Objekt", "icon": "📦", "description": "Eigene Sammlungsarten für alles Weitere."},
}



CUSTOM_CATEGORY_ICONS = [
    ("📦", "Allgemeine Sammlung"), ("🧸", "Figuren & Spielzeug"),
    ("🎲", "Brettspiele"), ("🧩", "Puzzle & Bausteine"),
    ("🚗", "Modellautos"), ("✈️", "Modellbau"),
    ("🎮", "Gaming"), ("💻", "Computer & Technik"),
    ("📱", "Handys & Geräte"), ("🎬", "Filme & Steelbooks"),
    ("📚", "Bücher & Comics"), ("💿", "Musik & Tonträger"),
    ("🃏", "Sammelkarten"), ("🪙", "Münzen"),
    ("💎", "Schmuck"), ("⌚", "Uhren"),
    ("👕", "Kleidung & Trikots"), ("🏆", "Sport & Erinnerungsstücke"),
    ("📸", "Kameras"), ("🖼️", "Kunst & Dekoration"),
]


def custom_category_icon_from_form():
    selected = (request.form.get("icon") or "📦").strip()
    if selected == "__custom__":
        selected = (request.form.get("custom_icon") or "").strip()
    return selected[:8] or "📦"


def custom_collection_categories(owner_id):
    """Return collection-scoped user-defined dashboard categories."""
    raw = app_setting_get(f"custom_collection_categories_{int(owner_id)}", "[]")
    try:
        payload = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        payload = []
    rows, seen = [], set()
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        key = re.sub(r"[^a-z0-9]+", "-", str(item.get("id") or "").casefold()).strip("-")[:80]
        title = " ".join(str(item.get("title") or "").split())[:120]
        if not key or not title or key in seen:
            continue
        seen.add(key)
        rows.append({
            "id": key, "title": title,
            "icon": str(item.get("icon") or "📦").strip()[:8] or "📦",
            "description": " ".join(str(item.get("description") or "").split())[:240],
        })
    return rows


def _custom_collection_category(owner_id, category_id):
    return next((row for row in custom_collection_categories(owner_id) if row["id"] == str(category_id or "")), None)


@app.route("/collector/custom-categories", methods=["POST"])
@login_required
def custom_collection_category_create():
    owner_id = active_collection_user_id()
    title = " ".join((request.form.get("title") or "").split())[:120]
    if len(title) < 2:
        flash("Der Kategoriename muss mindestens zwei Zeichen enthalten.", "warning")
        return redirect_back("collector_home")
    rows = custom_collection_categories(owner_id)
    base = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().casefold()).strip("-") or "sammlung"
    key, suffix = base[:80], 2
    existing = {row["id"] for row in rows}
    while key in existing:
        key = f"{base[:74]}-{suffix}"
        suffix += 1
    rows.append({
        "id": key, "title": title,
        "icon": custom_category_icon_from_form(),
        "description": " ".join((request.form.get("description") or "").split())[:240],
    })
    app_setting_set(f"custom_collection_categories_{int(owner_id)}", json.dumps(rows, ensure_ascii=False))
    log_activity("custom_category_created", "custom_category", None, f"Sammlungskategorie „{title}“ wurde angelegt.")
    db.session.commit()
    flash(f"Sammlungskategorie „{title}“ wurde angelegt. Du kannst jetzt direkt das erste Objekt hinzufügen.", "success")
    return redirect(url_for("collector_section", section="custom", custom_category=key))



def custom_category_form_token(action):
    key = f"custom_category_form:{active_collection_user_id()}:{action}"
    if request.method == "POST":
        expected = session.get(key)
        supplied = request.form.get("category_token", "")
        if not expected or not secrets.compare_digest(expected, supplied):
            abort(400)
    token = session.get(key) or secrets.token_urlsafe(32)
    session[key] = token
    return token


@app.route("/collector/custom-categories/<category_id>/edit", methods=["GET", "POST"])
@login_required
def custom_collection_category_edit(category_id):
    if not collection_capability("edit_items"):
        abort(403)
    owner_id = active_collection_user_id()
    category = _custom_collection_category(owner_id, category_id)
    if not category:
        abort(404)
    token = custom_category_form_token(f"edit:{category_id}")
    if request.method == "POST":
        title = " ".join((request.form.get("title") or "").split())[:120]
        if len(title) < 2:
            flash("Der Kategoriename muss mindestens zwei Zeichen enthalten.", "warning")
            return render_template("custom_category_edit.html", category={**category, "title": title,
                "icon": custom_category_icon_from_form(),
                "description": request.form.get("description", category["description"])}, category_token=token), 400
        updated = {**category, "title": title,
                   "icon": custom_category_icon_from_form(),
                   "description": " ".join((request.form.get("description") or "").split())[:240]}
        categories = [updated if row["id"] == category_id else row for row in custom_collection_categories(owner_id)]
        app_setting_set(f"custom_collection_categories_{owner_id}", json.dumps(categories, ensure_ascii=False))
        log_activity("custom_category_updated", "custom_category", None,
                     f"Sammlungskategorie „{category['title']}“ wurde als „{title}“ gespeichert.")
        db.session.commit()
        flash("Sammlungskategorie gespeichert.", "success")
        return redirect(url_for("collector_section", section="custom", custom_category=category_id))
    return render_template("custom_category_edit.html", category=category, category_token=token)


@app.route("/collector/custom-categories/move-items", methods=["POST"])
@login_required
def custom_collection_category_move_items():
    if not collection_capability("edit_items"):
        abort(403)
    owner_id = active_collection_user_id()
    custom_category_form_token("move-items")
    target = (request.form.get("target_category") or "").strip()
    category = _custom_collection_category(owner_id, target) if target else None
    if target and not category:
        abort(404)
    raw_ids = request.form.getlist("item_ids")
    if not raw_ids:
        flash("Bitte mindestens ein Objekt auswählen.", "warning")
        return redirect(url_for("collector_section", section="custom"))
    if len(raw_ids) > 500 or any(not re.fullmatch(r"[0-9]{1,10}", value) for value in raw_ids):
        abort(400)
    ids = {int(value) for value in raw_ids}
    rows = CollectorItem.query.filter(CollectorItem.user_id == owner_id,
        CollectorItem.category == "custom", CollectorItem.id.in_(ids)).all()
    # Reject the entire request if one ID is missing, foreign or another media type.
    if {row.id for row in rows} != ids:
        abort(404)
    for row in rows:
        metadata = collector_metadata(row)
        if target:
            metadata["custom_category"] = target
        else:
            metadata.pop("custom_category", None)
        row.metadata_json = json.dumps(metadata, ensure_ascii=False)
    label = category["title"] if category else "Ohne eigene Kategorie"
    log_activity("custom_category_items_moved", "custom_category", None,
                 f"{len(rows)} Objekte wurden „{label}“ zugeordnet.")
    db.session.commit()
    flash(f"{len(rows)} Objekte wurden „{label}“ zugeordnet.", "success")
    return redirect(url_for("collector_section", section="custom", custom_category=target or None))


@app.route("/collector/custom-categories/<category_id>/delete", methods=["GET", "POST"])
@login_required
def custom_collection_category_delete(category_id):
    if not collection_capability("edit_items"):
        abort(403)
    owner_id = active_collection_user_id()
    category = _custom_collection_category(owner_id, category_id)
    if not category:
        abort(404)
    items = [row for row in CollectorItem.query.filter_by(user_id=owner_id, category="custom").all()
             if collector_metadata(row).get("custom_category") == category_id]
    token_key = f"custom_category_delete:{owner_id}:{category_id}"
    if request.method == "POST":
        expected_token = session.get(token_key)
        provided_token = request.form.get("delete_token", "")
        if not expected_token or not secrets.compare_digest(expected_token, provided_token):
            abort(400)
        if request.form.get("confirm_delete") != "1":
            flash("Bitte das Entfernen dieser Kategorie bestätigen.", "warning")
            return redirect(url_for("custom_collection_category_delete", category_id=category_id))
        for row in items:
            metadata = collector_metadata(row)
            metadata.pop("custom_category", None)
            row.metadata_json = json.dumps(metadata, ensure_ascii=False)
        categories = [entry for entry in custom_collection_categories(owner_id) if entry["id"] != category_id]
        app_setting_set(f"custom_collection_categories_{owner_id}", json.dumps(categories, ensure_ascii=False))
        log_activity("custom_category_deleted", "custom_category", None,
                     f"Sammlungskategorie „{category['title']}“ wurde entfernt; {len(items)} Objekte bleiben erhalten.")
        db.session.commit()
        session.pop(token_key, None)
        flash(f"Kategorie „{category['title']}“ entfernt. {len(items)} Objekte bleiben unter Weitere Sammlungen erhalten.", "success")
        return redirect(url_for("collector_home"))
    token = session.get(token_key) or secrets.token_urlsafe(32)
    session[token_key] = token
    return render_template("custom_category_delete.html", category=category, item_count=len(items), delete_token=token)


def _tv_season_number(row, meta=None):
    """Return the represented season, never the number of a split disc/volume.

    German releases commonly split one season into editions such as 1.1 and
    1.2. Both copies belong to season 1 and must advance progress only once.
    """
    meta = meta if isinstance(meta, dict) else collector_metadata(row)
    direct = meta.get("season_number")
    candidates = (direct, meta.get("collection_order"), row.edition, row.title)
    for index, value in enumerate(candidates):
        if value in (None, ""):
            continue
        text_value = str(value).strip()
        if index < 2 and re.fullmatch(r"\d+(?:[.,]\d+)?", text_value):
            return int(re.split(r"[.,]", text_value, maxsplit=1)[0])
        match = re.search(r"(?i)\b(?:staffel|season)\s*[#№]?\s*0*(\d+)\b", text_value)
        if match:
            return int(match.group(1))
        # Split-volume shorthand in title/edition, e.g. "Navy CIS 10.1".
        match = re.search(r"(?:^|\D)0*(\d+)[.,][12](?:\D|$)", text_value)
        if match:
            return int(match.group(1))
    return None

def collector_group_meta(row):
    """Return the universal collection-series name/order stored in metadata."""
    meta = collector_metadata(row)
    name = (meta.get("collection_name") or meta.get("series_name") or "").strip()
    order = meta.get("collection_order")
    if row.category == "tv" and not name:
        name = row.title
    if row.category == "tv":
        order = _tv_season_number(row, meta) or order
    return name, order


def infer_collector_group(row):
    """Best-effort grouping without changing personal copy data."""
    meta = collector_metadata(row)
    name, order = collector_group_meta(row)
    if name:
        return name, order
    if row.category == "movies":
        coll = meta.get("tmdb_collection") or {}
        if isinstance(coll, dict):
            name = (coll.get("name") or "").strip()
        elif isinstance(coll, str):
            name = coll.strip()
    elif row.category == "books":
        name = (meta.get("book_series") or "").strip()
    return name, order


def logical_collection_unit_key(row, meta=None, order=None):
    """Identity of a work/season/band, deliberately independent of physical copies."""
    meta = meta if isinstance(meta, dict) else collector_metadata(row)
    category = getattr(row, "category", "")
    if category == "tv":
        season = _tv_season_number(row, meta)
        return f"season:{season}" if season is not None else f"title:{_match_key(row.title)}"
    if category == "movies":
        work = meta.get("tmdb_id") or (row.external_id if str(row.external_source or "").upper() == "TMDB" else None)
        return f"tmdb:{work}" if work else f"title:{_match_key(row.title)}"
    if category == "books":
        series_order = order if order not in (None, "") else meta.get("collection_order")
        if series_order not in (None, ""):
            return f"band:{str(series_order).replace(',', '.')}"
        work = meta.get("openlibrary_work_id") or meta.get("work_key") or row.external_id or row.barcode
        return f"work:{work}" if work else f"title:{_match_key(row.title)}"
    return f"order:{order}" if order not in (None, "") else f"title:{_match_key(row.title)}"



def _tv_disc_status_key(user_id, tmdb_id):
    return f"tv_disc_status:{int(user_id)}:{str(tmdb_id).strip()}"


def _tv_disc_statuses(user_id, tmdb_id):
    raw = app_setting_get(_tv_disc_status_key(user_id, tmdb_id)) or "{}"
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _set_tv_disc_statuses(user_id, tmdb_id, data):
    app_setting_set(_tv_disc_status_key(user_id, tmdb_id), json.dumps(data, ensure_ascii=False, sort_keys=True))


def _tv_season_links_key(user_id, tmdb_id):
    return f"tv_season_links:{int(user_id)}:{str(tmdb_id).strip()}"


def _tv_season_links(user_id, tmdb_id):
    raw = app_setting_get(_tv_season_links_key(user_id, tmdb_id)) or "{}"
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _set_tv_season_links(user_id, tmdb_id, data):
    app_setting_set(_tv_season_links_key(user_id, tmdb_id), json.dumps(data, ensure_ascii=False, sort_keys=True))



def _collector_multi_part_copy(row):
    """True only for physical copies that are explicitly able to cover multiple works/seasons."""
    meta = collector_metadata(row)
    for key in ("included_tmdb_ids", "included_seasons", "season_numbers", "included_parts"):
        value = meta.get(key)
        if isinstance(value, list) and len(value) > 1:
            return True
    text = " ".join(str(x or "") for x in (row.title, row.edition, meta.get("edition_type"), meta.get("set_name"))).casefold()
    multi_words = ("box", "boxset", "komplett", "complete", "collection", "sammlung", "mehrfilm", "trilog", "quadrilog", "1 & 2", "1-2", "1–2")
    if any(word in text for word in multi_words):
        return True
    if re.search(r"(?:staffel|season)\s*\d+\s*[-–&+]\s*(?:staffel|season)?\s*\d+", text):
        return True
    return False


def _tv_complete_series_copy(row, meta=None):
    """Recognize an explicit whole-series release without mistaking a season box for one."""
    meta = meta or collector_metadata(row)
    text = " ".join(str(value or "") for value in (
        row.title, row.edition, meta.get("edition_type"), meta.get("set_name")
    )).casefold()
    whole_series_markers = (
        "komplette serie", "komplett serie", "gesamtbox", "gesamt-box",
        "complete series", "complete collection", "complete box set",
    )
    if any(marker in text for marker in whole_series_markers):
        return True
    # Retailers also call a complete *single season* a "Komplettbox".  An
    # explicit season number therefore always wins over that ambiguous word.
    explicit_single_season = re.search(r"(?i)\b(?:staffel|season)\s*[#№]?\s*\d+\b", text)
    return any(marker in text for marker in ("komplettbox", "complete box")) and not explicit_single_season


def inferred_release_coverages(row):
    """Normalize legacy box metadata into explicit logical coverage rows."""
    meta = collector_metadata(row); result = []
    if row.category == "movies":
        for value in meta.get("included_tmdb_ids") or []:
            value = str(value).strip()
            if value.isdigit(): result.append(("movies", f"movie:tmdb:{value}", f"TMDB-Film {value}", value))
    elif row.category == "tv":
        series_id = str(meta.get("tmdb_id") or row.external_id or _match_key(meta.get("collection_name") or row.title)).strip()
        season_values = list(meta.get("included_seasons") or meta.get("season_numbers") or [])
        if not season_values:
            text_value = " ".join(str(value or "") for value in (row.title, row.edition, meta.get("edition_type"), meta.get("set_name"))).casefold()
            strong_complete = _tv_complete_series_copy(row, meta)
            total = meta.get("season_count") or meta.get("number_of_seasons")
            try:
                total = int(total or 0)
            except (TypeError, ValueError):
                total = 0
            if strong_complete and total > 0:
                season_values = list(range(1, min(total, 200) + 1))
            else:
                range_match = re.search(r"(?i)(?:staffel|season)\s*(\d+)\s*[-–]\s*(\d+)", text_value)
                if range_match:
                    season_values = list(range(int(range_match.group(1)), int(range_match.group(2)) + 1))
        for value in season_values:
            try: season = int(str(value).split(".", 1)[0])
            except (TypeError, ValueError): continue
            result.append(("tv", f"tv:{series_id}:season:{season}", f"{meta.get('collection_name') or row.title} – Staffel {season}", str(season)))
    elif row.category == "books":
        for pos, value in enumerate(meta.get("included_parts") or [], 1):
            title = str(value.get("title") if isinstance(value, dict) else value).strip()
            key = str(value.get("id") if isinstance(value, dict) else "").strip() or _match_key(title)
            if title: result.append(("books", f"book:{key}", title, str(pos)))
    return result


def sync_inferred_release_coverages(row):
    entries = ReleaseCoverage.query.filter_by(owner_id=row.user_id, source_kind="collector", source_id=str(row.id)).all()
    existing = {(entry.target_kind, entry.target_key) for entry in entries}
    inferred = inferred_release_coverages(row)
    desired = {(kind, key) for kind, key, _title, _sequence in inferred}
    changed = 0
    # Reconcile only automatically inferred rows. Explicit/manual assignments
    # always remain untouched, while old false positives are repaired safely.
    for entry in entries:
        if entry.origin == "inferred" and (entry.target_kind, entry.target_key) not in desired:
            db.session.delete(entry)
            changed += 1
    for kind, key, title, sequence in inferred:
        if (kind, key) in existing: continue
        db.session.add(ReleaseCoverage(owner_id=row.user_id, source_kind="collector", source_id=str(row.id), target_kind=kind,
                       target_key=key, target_title=title[:255], sequence_label=sequence[:80], origin="inferred")); changed += 1
    return changed


def _tv_used_single_item_ids(user_id, exclude_tmdb_id=None, exclude_season=None):
    """Return single-copy item ids already assigned to a TV season anywhere for this user."""
    prefix = f"tv_season_links:{int(user_id)}:"
    used = set()
    for setting in AppSetting.query.filter(AppSetting.key.like(prefix + "%")).all():
        series_id = setting.key[len(prefix):]
        try:
            links = json.loads(setting.value or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(links, dict):
            continue
        for season, item_id in links.items():
            if exclude_tmdb_id is not None and str(series_id) == str(exclude_tmdb_id) and exclude_season is not None and str(season) == str(exclude_season):
                continue
            try:
                iid = int(item_id)
            except (TypeError, ValueError):
                continue
            item = db.session.get(CollectorItem, iid)
            if item and item.user_id == user_id and item.category == "tv" and not _collector_multi_part_copy(item):
                used.add(iid)
    return used


def _tv_item_link_assignments(user_id, item_id):
    """Return every explicit (series, season) assignment for one physical TV copy."""
    prefix = f"tv_season_links:{int(user_id)}:"
    assignments = set()
    for setting in AppSetting.query.filter(AppSetting.key.like(prefix + "%")).all():
        series_id = setting.key[len(prefix):]
        try:
            links = json.loads(setting.value or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(links, dict):
            continue
        for season, linked_id in links.items():
            try:
                if int(linked_id) == int(item_id) and str(season).isdigit():
                    assignments.add((str(series_id), str(season)))
            except (TypeError, ValueError):
                continue
    return assignments


def _link_tv_box_seasons(item, tmdb_id, series_title, season_numbers, season_links):
    """Persist a deliberate multi-season box assignment and its logical coverage."""
    selected = sorted({int(value) for value in season_numbers if str(value).isdigit() and int(value) > 0})
    if not selected:
        return 0
    meta = collector_metadata(item)
    included = set()
    for value in meta.get("included_seasons") or meta.get("season_numbers") or []:
        try:
            included.add(int(str(value).split(".", 1)[0]))
        except (TypeError, ValueError):
            continue
    included.update(selected)
    meta["included_seasons"] = sorted(included)
    meta.setdefault("tmdb_id", str(tmdb_id))
    meta.setdefault("collection_name", str(series_title or item.title))
    meta["edition_type"] = meta.get("edition_type") or "Komplett-/Mehrstaffelbox"
    item.metadata_json = json.dumps(meta, ensure_ascii=False)
    for season in selected:
        season_links[str(season)] = int(item.id)
        key = f"tv:{tmdb_id}:season:{season}"
        existing = ReleaseCoverage.query.filter_by(owner_id=item.user_id, source_kind="collector", source_id=str(item.id), target_kind="tv", target_key=key).first()
        if not existing:
            db.session.add(ReleaseCoverage(owner_id=item.user_id, source_kind="collector", source_id=str(item.id), target_kind="tv",
                           target_key=key, target_title=f"{series_title or item.title} – Staffel {season}"[:255],
                           sequence_label=str(season), origin="manual"))
    return len(selected)


def _canonical_tv_series_name(row):
    """Keep physical season/volume titles from becoming standalone TV-series rows."""
    meta = collector_metadata(row)
    explicit = str(meta.get("series_name") or meta.get("collection_name") or "").strip()
    if explicit:
        return explicit
    title = str(row.title or "").strip()
    # Strip common physical-edition suffixes only for overview grouping. The copy title itself is untouched.
    cleaned = re.sub(r"\s*[-–:]?\s*(?:staffel|season|volume|vol\.?|box)\s*\d+.*$", "", title, flags=re.I).strip(" -–:")
    cleaned = re.sub(r"\s*\[[^\]]*(?:dvd|blu.?ray)[^\]]*\].*$", "", cleaned, flags=re.I).strip(" -–:")
    return cleaned or title

@app.route("/collector/tv/<tmdb_id>/collection", methods=["GET", "POST"])
@login_required
def collector_tv_collection(tmdb_id):
    """TV season checklist with explicit physical-copy assignment and honest progress."""
    uid = active_collection_user_id()
    rows = CollectorItem.query.filter_by(user_id=uid, category="tv").all()
    related = []
    for row in rows:
        meta = collector_metadata(row)
        if str(meta.get("tmdb_id") or row.external_id or "") == str(tmdb_id):
            related.append((row, meta))
    if not related:
        abort(404)
    title = related[0][0].title
    statuses = _tv_disc_statuses(uid, tmdb_id)
    season_links = _tv_season_links(uid, tmdb_id)
    if request.method == "POST":
        action = str(request.form.get("action") or "status").strip().lower()
        selected = sorted({str(value).strip() for value in request.form.getlist("seasons") if str(value).strip().isdigit()}, key=int)
        if action == "bulk_item_link":
            item_id = request.form.get("item_id", type=int)
            item = db.session.get(CollectorItem, item_id) if item_id else None
            if not item or item.user_id != uid or item.category != "tv" or not _is_physical_video_media(item):
                abort(400)
            if not selected:
                flash("Bitte mindestens eine Staffel auswählen.", "warning")
                return redirect(url_for("collector_tv_collection", tmdb_id=tmdb_id))
            other_series = {series for series, _season in _tv_item_link_assignments(uid, item.id) if str(series) != str(tmdb_id)}
            if other_series and not _collector_multi_part_copy(item):
                flash("Dieses Exemplar ist bereits einer anderen Serie zugeordnet.", "warning")
                return redirect(url_for("collector_tv_collection", tmdb_id=tmdb_id))
            count = _link_tv_box_seasons(item, tmdb_id, title, selected, season_links)
            _set_tv_season_links(uid, tmdb_id, season_links)
            log_activity("tv_box_linked", "collector_item", item.id, f"{item.title}: als Box den Staffeln {', '.join(selected)} zugeordnet.")
            db.session.commit()
            flash(f"{item.title} wurde als Box {count} Staffeln zugeordnet. Der Wert wird nur einmal summiert.", "success")
            return redirect(url_for("collector_tv_collection", tmdb_id=tmdb_id))
        if action == "bulk_status" or (action == "status" and selected):
            status = str(request.form.get("status") or "unknown").strip().lower()
            if status not in {"physical", "digital", "never_physical_de", "unknown"}:
                abort(400)
            if not selected:
                flash("Bitte mindestens eine Staffel auswählen.", "warning")
                return redirect(url_for("collector_tv_collection", tmdb_id=tmdb_id))
            for season in selected:
                if status == "unknown":
                    statuses.pop(season, None)
                else:
                    statuses[season] = status
            _set_tv_disc_statuses(uid, tmdb_id, statuses)
            db.session.commit()
            flash(f"Status für {len(selected)} ausgewählte Staffeln gespeichert.", "success")
            return redirect(url_for("collector_tv_collection", tmdb_id=tmdb_id))
        season = str(request.form.get("season") or "").strip()
        if not season.isdigit(): abort(400)
        if action == "item_link":
            item_id = request.form.get("item_id", type=int)
            item = db.session.get(CollectorItem, item_id) if item_id else None
            if not item or item.user_id != uid or item.category != "tv": abort(400)
            assignments = _tv_item_link_assignments(uid, item.id) - {(str(tmdb_id), str(season))}
            same_series = {assigned_season for series, assigned_season in assignments if str(series) == str(tmdb_id)}
            other_series = {series for series, _assigned_season in assignments if str(series) != str(tmdb_id)}
            if other_series and not _collector_multi_part_copy(item):
                flash("Dieses Einzel-Exemplar ist bereits einer anderen Staffel zugeordnet. Löse dort zuerst die Zuordnung.", "warning")
                return redirect(url_for("collector_tv_collection", tmdb_id=tmdb_id, _anchor=f"season-{season}"))
            if same_series or _collector_multi_part_copy(item):
                _link_tv_box_seasons(item, tmdb_id, title, list(same_series) + [season], season_links)
            season_links[season] = int(item.id)
            _set_tv_season_links(uid, tmdb_id, season_links)
            db.session.commit()
            flash(f"{item.title} wurde Staffel {season} zugeordnet.", "success")
            return redirect(url_for("collector_tv_collection", tmdb_id=tmdb_id, _anchor=f"season-{season}"))
        if action == "item_unlink":
            season_links.pop(season, None)
            _set_tv_season_links(uid, tmdb_id, season_links)
            db.session.commit()
            flash(f"Manuelle Zuordnung für Staffel {season} entfernt.", "success")
            return redirect(url_for("collector_tv_collection", tmdb_id=tmdb_id, _anchor=f"season-{season}"))
        status = str(request.form.get("status") or "unknown").strip().lower()
        if status not in {"physical", "digital", "never_physical_de", "unknown"}: abort(400)
        if status == "unknown": statuses.pop(season, None)
        else: statuses[season] = status
        _set_tv_disc_statuses(uid, tmdb_id, statuses)
        db.session.commit()
        flash(f"Disc-Status für Staffel {season} gespeichert.", "success")
        return redirect(url_for("collector_tv_collection", tmdb_id=tmdb_id, _anchor=f"season-{season}"))

    inferred_added = sum(sync_inferred_release_coverages(row) for row, _meta in related)
    if inferred_added:
        db.session.commit()
    details = tmdb_json(f"tv/{quote(str(tmdb_id), safe='')}", {"language":"de-DE"}) or {}
    if details.get("name"): title = str(details.get("name"))
    tmdb_seasons = [x for x in (details.get("seasons") or []) if isinstance(x, dict) and int(x.get("season_number") or 0) > 0]
    # Repair older whole-series boxes that predate season coverage metadata. The
    # authoritative series response supplies the missing total once; from then on
    # ReleaseCoverage keeps every season linked to the same physical copy.
    season_total = len({int(x.get("season_number")) for x in tmdb_seasons})
    repaired_complete_boxes = 0
    if season_total:
        for row, meta in related:
            if not _tv_complete_series_copy(row, meta):
                continue
            try:
                stored_total = int(meta.get("season_count") or meta.get("number_of_seasons") or 0)
            except (TypeError, ValueError):
                stored_total = 0
            if stored_total < season_total:
                meta["season_count"] = season_total
                meta.setdefault("tmdb_id", str(tmdb_id))
                meta.setdefault("collection_name", title)
                row.metadata_json = json.dumps(meta, ensure_ascii=False)
            repaired_complete_boxes += sync_inferred_release_coverages(row)
        if repaired_complete_boxes:
            db.session.commit()
    owned_by_season = {}
    for row, meta in related:
        n = _tv_season_number(row, meta)
        if n is None: continue
        owned_by_season.setdefault(n, []).append(row)
    covered_by_season = set()
    for row, _meta in related:
        entries = ReleaseCoverage.query.filter_by(owner_id=uid, source_kind="collector", source_id=str(row.id), target_kind="tv").all()
        for entry in entries:
            match = re.search(r":season:(\d+)$", entry.target_key)
            if match:
                season_number = int(match.group(1))
                covered_by_season.add(season_number)
                bucket = owned_by_season.setdefault(season_number, [])
                if row not in bucket:
                    bucket.append(row)
    # Manual links may point to a differently/incorrectly identified TV copy. They override auto matching.
    linked_by_season = {}
    for key, item_id in list(season_links.items()):
        if not str(key).isdigit(): continue
        item = db.session.get(CollectorItem, int(item_id)) if str(item_id).isdigit() else None
        if item and item.user_id == uid and item.category == "tv": linked_by_season.setdefault(int(key), []).append(item)
    numbers = {int(x.get("season_number")) for x in tmdb_seasons if x.get("season_number") is not None}
    numbers.update(owned_by_season); numbers.update(linked_by_season)
    numbers.update(int(k) for k in statuses if str(k).isdigit())
    seasons=[]; tmdb_map={int(x.get("season_number")):x for x in tmdb_seasons if x.get("season_number") is not None}
    for n in sorted(numbers):
        owned=list(linked_by_season.get(n, [])) or list(owned_by_season.get(n, []))
        manual=statuses.get(str(n))
        physical_owned=any(_is_de_physical_media(r) for r in owned)
        # An explicit manual copy link is direct ownership evidence even when legacy edition metadata is incomplete.
        status="owned" if (owned and (physical_owned or n in linked_by_season or n in covered_by_season)) else (manual or "unknown")
        t=tmdb_map.get(n,{})
        season_value=sum(float(collector_effective_value(r) or 0)*max(r.quantity or 1,1) for r in owned)
        shared_copy=any(_collector_multi_part_copy(r) for r in owned)
        seasons.append({"number":n,"name":t.get("name") or f"Staffel {n}","episode_count":t.get("episode_count"),"air_date":t.get("air_date"),"cover":tmdb_poster_url(t.get("poster_path")),"status":status,"owned_rows":owned,"value":season_value,"shared_copy":shared_copy,"linked_item":linked_by_season.get(n,[None])[0] if linked_by_season.get(n) else None})
    confirmed_total=sum(1 for x in seasons if x["status"] in {"owned","physical"})
    owned_count=sum(1 for x in seasons if x["status"]=="owned")
    missing_count=sum(1 for x in seasons if x["status"]=="physical")
    digital_count=sum(1 for x in seasons if x["status"]=="digital")
    never_physical_de_count=sum(1 for x in seasons if x["status"]=="never_physical_de")
    unknown_count=sum(1 for x in seasons if x["status"]=="unknown")
    # Do not claim 100% while TMDB seasons are still unresolved.
    pct=round(owned_count*100/confirmed_total) if confirmed_total and unknown_count==0 else None
    used_single_ids = _tv_used_single_item_ids(uid)
    current_link_ids = {int(v) for v in season_links.values() if str(v).isdigit()}
    related_ids={row.id for row, _meta in related}
    candidate_rows=sorted(
        [r for r in rows if r.id not in used_single_ids or _collector_multi_part_copy(r) or r.id in current_link_ids],
        key=lambda r: (r.id not in related_ids, (r.title or "").casefold(), r.id)
    )
    value_rows={row.id:row for row, _meta in related}
    for linked in linked_by_season.values():
        for row in linked:
            value_rows[row.id]=row
    total_value=sum(float(collector_effective_value(r) or 0)*max(r.quantity or 1,1) for r in value_rows.values())
    return render_template("collector_tv_collection.html", title=title, tmdb_id=tmdb_id, seasons=seasons, owned_count=owned_count, physical_total=confirmed_total, missing_count=missing_count, digital_count=digital_count, never_physical_de_count=never_physical_de_count, unknown_count=unknown_count, pct=pct, candidate_rows=candidate_rows, total_value=total_value)


def _movie_collection_status_key(user_id, collection_id):
    return f"movie_collection_status:{int(user_id)}:{str(collection_id).strip()}"


def _movie_collection_statuses(user_id, collection_id):
    raw = app_setting_get(_movie_collection_status_key(user_id, collection_id)) or "{}"
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _set_movie_collection_statuses(user_id, collection_id, data):
    app_setting_set(_movie_collection_status_key(user_id, collection_id), json.dumps(data, ensure_ascii=False, sort_keys=True))



def _movie_box_links_key(user_id, collection_id):
    return f"movie_box_links:{int(user_id)}:{str(collection_id).strip()}"


def _movie_box_links(user_id, collection_id):
    raw = app_setting_get(_movie_box_links_key(user_id, collection_id)) or "{}"
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _set_movie_box_links(user_id, collection_id, data):
    app_setting_set(_movie_box_links_key(user_id, collection_id), json.dumps(data, ensure_ascii=False, sort_keys=True))


def _movie_used_single_item_ids(user_id, exclude_part_id=None):
    """Return movie-copy ids already assigned to any film part.

    A normal single-film copy may cover only one work. Explicit boxes and
    multi-film editions remain reusable for several parts.
    """
    prefix = f"movie_box_links:{int(user_id)}:"
    used = set()
    for setting in AppSetting.query.filter(AppSetting.key.like(prefix + "%")).all():
        try:
            links = json.loads(setting.value or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(links, dict):
            continue
        for part_id, item_id in links.items():
            if exclude_part_id is not None and str(part_id) == str(exclude_part_id):
                continue
            try:
                iid = int(item_id)
            except (TypeError, ValueError):
                continue
            item = db.session.get(CollectorItem, iid)
            if item and item.user_id == user_id and item.category == "movies" and not _collector_multi_part_copy(item):
                used.add(iid)
    return used


def _is_physical_video_media(row):
    """Recognize selectable discs independently of complete country metadata."""
    if row.category not in {"movies", "tv"}:
        return False
    media = re.sub(r"\s+", " ", str(row.media_type or "").strip().casefold())
    if not media:
        return False
    return any(token in media for token in ("dvd", "blu-ray", "blu ray", "bluray", "4k uhd", "uhd", "hd dvd", "video-cd", "vcd", "vhs"))


def _is_de_physical_media(row):
    meta = collector_metadata(row)
    country = str(meta.get("physical_country") or "").strip().upper()
    return country in {"DE", "DEU", "DEUTSCHLAND", "GERMANY"} and _is_physical_video_media(row)

def _tmdb_collection_search(query):
    query = str(query or "").strip()
    if not query:
        return None
    data = tmdb_json("search/collection", {"query": query, "language": "de-DE"}) or {}
    hits = data.get("results") or [] if isinstance(data, dict) else []
    if not hits:
        return None
    qk = _match_key(query)
    exact = [h for h in hits if _match_key(h.get("name") or "").removesuffix("filmreihe") == qk.removesuffix("filmreihe")]
    return (exact or hits)[0]


def _movie_collection_family_query(name):
    """Return the provider search term behind a localized collection label."""
    value = str(name or "").strip()
    value = re.sub(r"\s*[\(\[]\s*(?:filmreihe|collection|sammlung|reihe)\s*[\)\]]\s*$", "", value, flags=re.I)
    value = re.sub(r"(?:\s*[-–—:]\s*)?(?:filmreihe|filmreihe|collection|sammlung|reihe)\s*$", "", value, flags=re.I)
    return " ".join(value.split()).strip(" -–—:")


def _movie_collection_search_name_matches(base_query, candidate_name):
    """Require an exact localized family name for fuzzy TMDB search hits."""
    base_key = _match_key(_movie_collection_family_query(base_query))
    candidate_key = _match_key(_movie_collection_family_query(candidate_name))
    return bool(base_key and candidate_key and base_key == candidate_key)


# TMDB splits a few long-running cinema series into separate collections even
# though users reasonably expect one checklist.  Keep this deliberately small:
# generic provider discovery remains the default, while known split families
# get stable work IDs so a changing search ranking cannot hide whole eras.
_CURATED_MOVIE_COLLECTION_FAMILIES = {
    "spider_man": {
        "title": "Spider-Man",
        "scope": "Kinofilmreihen",
        # TMDB separates the Raimi trilogy, the two Amazing-Spider-Man films,
        # the MCU trilogy and the animated Spider-Verse films. Collector users
        # expect one Spider-Man checklist, while adjacent Sony/Marvel films
        # such as Venom and Morbius must not leak into it.
        "collection_ids": ("556", "125574", "531241", "573436"),
        "movie_ids": ("557", "558", "559", "1930", "102382", "315635", "429617", "634649", "324857", "569094"),
    },
    "batman": {
        "title": "Batman",
        "scope": "Hauptfilmreihe",
        # Batman (Burton/Schumacher), The Dark Knight trilogy, The Batman.
        "collection_ids": ("120794", "263", "948485"),
        # Current live-action solo cinema films, including the standalone 1966
        # film. Collection parts are still loaded as well, so future sequels
        # added by TMDB appear automatically.
        "movie_ids": ("2661", "268", "364", "414", "415", "272", "155", "49026", "414906"),
    },
    "bourne": {
        "title": "Die Bourne",
        "scope": "Hauptfilmreihe",
        # The first three works form the original trilogy. The later two films
        # remain part of the complete Bourne cinema family shown in Collector.
        "collection_ids": ("31562",),
        "movie_ids": ("2501", "2502", "2503", "49040", "324668"),
    },
}


def _curated_movie_collection_family(collection_id):
    cid = str(collection_id or "").strip()
    for key, family in _CURATED_MOVIE_COLLECTION_FAMILIES.items():
        if cid in {str(x) for x in family.get("collection_ids", ())}:
            return key, family
    return None, None


def _curated_movie_collection_family_from_text(*values):
    """Recognize curated families in legacy rows without canonical TMDB metadata."""
    key = _match_key(" ".join(str(value or "") for value in values))
    if re.search(r"(?:^|\s)bourne(?:\s|$)", key):
        return "bourne", _CURATED_MOVIE_COLLECTION_FAMILIES["bourne"]
    if re.search(r"(?:^|\s)spider\s*man(?:\s|$)", key) or re.search(r"(?:^|\s)spiderman(?:\s|$)", key):
        return "spider_man", _CURATED_MOVIE_COLLECTION_FAMILIES["spider_man"]
    if re.search(r"(?:^|\s)batman(?:\s|$)", key):
        return "batman", _CURATED_MOVIE_COLLECTION_FAMILIES["batman"]
    return None, None


def _tmdb_movie_collection_family(collection_id, base_details=None):
    """Resolve one TMDB collection into its wider provider-backed film family.

    TMDB deliberately splits long-running subjects into several collections.
    Its collection search also matches translated and alternative names, so a
    search for the canonical label discovers sibling collections in the usual
    case. Known provider-split families additionally use stable collection and
    work IDs so search ranking changes cannot make complete eras disappear.
    """
    cid = str(collection_id or "").strip()
    base = base_details if isinstance(base_details, dict) else (tmdb_json(f"collection/{quote(cid, safe='')}", {"language": "de-DE"}) or {})
    base_name = str(base.get("name") or "Filmreihe").strip()
    query = _movie_collection_family_query(base_name)
    curated_key, curated = _curated_movie_collection_family(cid)
    collections = []
    seen_collections = set()

    def add_collection(details, fallback_id=None, fallback_name=None):
        if not isinstance(details, dict):
            return
        item_id = str(details.get("id") or fallback_id or "").strip()
        if not item_id.isdigit() or item_id in seen_collections:
            return
        seen_collections.add(item_id)
        collections.append({
            "id": item_id,
            "name": str(details.get("name") or fallback_name or f"TMDB #{item_id}"),
            "parts": [x for x in (details.get("parts") or []) if isinstance(x, dict) and x.get("id")],
        })

    add_collection(base, cid, base_name)
    if curated:
        for sibling_id in curated.get("collection_ids", ()):
            sibling_id = str(sibling_id)
            if sibling_id in seen_collections:
                continue
            details = tmdb_json(f"collection/{quote(sibling_id, safe='')}", {"language": "de-DE"}) or {}
            add_collection(details, sibling_id)
    else:
        query_key = _match_key(query)
        # Very short/generic names would make provider search too broad. The base
        # collection remains fully functional in that case.
        blocked = {"film", "filme", "movie", "movies", "kino", "collection", "sammlung", "reihe"}
        if len(query_key) >= 4 and query_key not in blocked:
            search = tmdb_json("search/collection", {"query": query, "language": "de-DE", "page": 1}) or {}
            hits = search.get("results") or [] if isinstance(search, dict) else []
            # A hit is already evidence from TMDB's original/translated/alternative
            # name search. Limit breadth to keep the detail page responsive.
            for hit in hits[:12]:
                hit_id = str(hit.get("id") or "").strip() if isinstance(hit, dict) else ""
                if not hit_id.isdigit() or hit_id in seen_collections:
                    continue
                if not _movie_collection_search_name_matches(query, hit.get("name") or ""):
                    continue
                details = tmdb_json(f"collection/{quote(hit_id, safe='')}", {"language": "de-DE"}) or {}
                add_collection(details, hit_id, hit.get("name"))

    parts_by_id = {}
    for collection in collections:
        for part in collection["parts"]:
            parts_by_id.setdefault(str(part.get("id")), part)
    # A standalone film is not returned by a collection endpoint. Explicit
    # work IDs also provide a reliable fallback if one collection request is
    # temporarily unavailable.
    if curated:
        for movie_id in curated.get("movie_ids", ()):
            movie_id = str(movie_id)
            if movie_id in parts_by_id:
                continue
            details = tmdb_json(f"movie/{quote(movie_id, safe='')}", {"language": "de-DE"}) or {}
            if isinstance(details, dict) and details.get("id"):
                parts_by_id[movie_id] = details
    parts = sorted(parts_by_id.values(), key=lambda x: (str(x.get("release_date") or "9999"), str(x.get("title") or x.get("original_title") or "").casefold()))
    title = str(curated.get("title")) if curated else (query if len(collections) > 1 and query else base_name)
    return {"title": title, "query": query, "collections": collections, "parts": parts,
            "curated_key": curated_key, "scope": curated.get("scope") if curated else None}


def _movie_collection_refresh_row(row):
    """Repair canonical TMDB collection metadata without touching personal copy fields."""
    if row.category != "movies":
        return False, "kein Film"
    meta = collector_metadata(row)
    changed = False

    # Known TMDB work: refresh the work and belongs_to_collection authoritatively.
    mid = str(meta.get("tmdb_id") or (row.external_id if str(row.external_source or "").upper() == "TMDB" else "") or "").strip()
    if mid.isdigit():
        details = tmdb_json(f"movie/{mid}", {"language": "de-DE"}) or {}
        coll = details.get("belongs_to_collection") if isinstance(details, dict) else None
        if isinstance(coll, dict) and coll.get("id"):
            meta["tmdb_id"] = mid
            meta["tmdb_media_type"] = "movie"
            meta["tmdb_collection"] = coll
            meta["collection_name"] = str(coll.get("name") or meta.get("collection_name") or "").removesuffix(" Filmreihe").strip()
            changed = True

    # Legacy physical edition / box: collection_name is a hint, never a work identity.
    if not (isinstance(meta.get("tmdb_collection"), dict) and meta["tmdb_collection"].get("id")):
        hint = str(meta.get("collection_name") or "").strip()
        if hint:
            hit = _tmdb_collection_search(hint)
            if isinstance(hit, dict) and hit.get("id"):
                coll_details = tmdb_json(f"collection/{hit['id']}", {"language": "de-DE"}) or {}
                coll = {"id": hit["id"], "name": coll_details.get("name") or hit.get("name") or hint,
                        "poster_path": coll_details.get("poster_path") or hit.get("poster_path"),
                        "backdrop_path": coll_details.get("backdrop_path") or hit.get("backdrop_path")}
                meta["tmdb_collection"] = coll
                meta["collection_name"] = str(coll.get("name") or hint).removesuffix(" Filmreihe").strip()
                changed = True

                # Explicit multi-film ranges such as "Trilogie 1-3" may cover several works.
                if _collector_multi_part_copy(row):
                    text = " ".join(str(x or "") for x in (row.title, row.edition)).casefold()
                    m = re.search(r"(?:^|\D)(\d+)\s*[-–]\s*(\d+)(?:\D|$)", text)
                    parts = [x for x in (coll_details.get("parts") or []) if isinstance(x, dict) and x.get("id")]
                    parts.sort(key=lambda x: str(x.get("release_date") or "9999"))
                    if m:
                        start, end = int(m.group(1)), int(m.group(2))
                        if 1 <= start <= end <= len(parts):
                            meta["included_tmdb_ids"] = [str(x.get("id")) for x in parts[start-1:end]]
                            changed = True
                    elif len(parts) > 1 and any(w in text for w in ("trilog", "quadrilog", "komplett", "complete")):
                        # A trilogy box covers the first three chronological works
                        # even when the wider franchise later grew beyond them.
                        if "trilog" in text and len(parts) >= 3:
                            meta["included_tmdb_ids"] = [str(x.get("id")) for x in parts[:3]]
                            changed = True
                        elif "quadrilog" in text and len(parts) >= 4:
                            meta["included_tmdb_ids"] = [str(x.get("id")) for x in parts[:4]]
                            changed = True
                        elif "komplett" in text or "complete" in text:
                            meta["included_tmdb_ids"] = [str(x.get("id")) for x in parts]
                            changed = True

    # A normal single-film legacy item can be identified by its precise title.
    if not mid and not _collector_multi_part_copy(row):
        data = tmdb_json("search/movie", {"query": row.title, "language": "de-DE", "include_adult": "false"}) or {}
        hits = data.get("results") or [] if isinstance(data, dict) else []
        if hits:
            rk = _match_key(row.title)
            strong = [h for h in hits if _match_key(h.get("title") or h.get("original_title") or "") == rk]
            if len(strong) == 1:
                details = tmdb_json(f"movie/{strong[0]['id']}", {"language": "de-DE"}) or {}
                coll = details.get("belongs_to_collection") if isinstance(details, dict) else None
                if isinstance(coll, dict) and coll.get("id"):
                    meta["tmdb_id"] = str(details.get("id"))
                    meta["tmdb_media_type"] = "movie"
                    meta["tmdb_collection"] = coll
                    meta["collection_name"] = str(coll.get("name") or "").removesuffix(" Filmreihe").strip()
                    changed = True

    if changed:
        row.metadata_json = json.dumps(meta, ensure_ascii=False)
    return changed, "aktualisiert" if changed else "unverändert"


def _refresh_movie_collections(user_id, only_collection_id=None):
    rows = CollectorItem.query.filter_by(user_id=user_id, category="movies").all()
    changed = 0; checked = 0
    for row in rows:
        if only_collection_id:
            meta = collector_metadata(row); coll = meta.get("tmdb_collection") or {}
            cid = str(coll.get("id") or "") if isinstance(coll, dict) else ""
            # Also allow aliases already carrying the same collection name to be repaired below.
            if cid and cid != str(only_collection_id):
                continue
        checked += 1
        did_change, _ = _movie_collection_refresh_row(row)
        if did_change:
            changed += 1
    db.session.commit()
    return checked, changed


@app.route("/collector/movies/collections/refresh", methods=["POST"])
@login_required
def collector_movie_collections_refresh():
    checked, changed = _refresh_movie_collections(active_collection_user_id())
    flash(f"Filmreihen aktualisiert: {checked} Filmobjekte geprüft, {changed} Zuordnungen/Metadaten aktualisiert.", "success")
    return redirect(url_for("collector_collections", type="movies"))


@app.route("/collector/tv/refresh", methods=["POST"])
@login_required
def collector_tv_collections_refresh():
    rows = CollectorItem.query.filter_by(user_id=active_collection_user_id(), category="tv").all()
    updated = failed = 0
    for row in rows:
        try:
            ok, _message = tmdb_apply_metadata(row)
            updated += 1 if ok else 0
            failed += 0 if ok else 1
        except Exception:
            db.session.rollback()
            failed += 1
    db.session.commit()
    flash(f"TV-Serien aktualisiert: {updated} Einträge erneuert" + (f", {failed} ohne Treffer." if failed else "."), "success" if not failed else "warning")
    return redirect(url_for("collector_collections", type="tv"))


@app.route("/collector/books/refresh", methods=["POST"])
@login_required
def collector_book_collections_refresh():
    rows = CollectorItem.query.filter_by(user_id=active_collection_user_id(), category="books").all()
    updated = skipped = 0
    series_names = set()
    for row in rows:
        meta = collector_metadata(row)
        series_name, _series_order = infer_collector_group(row)
        if series_name:
            series_names.add(series_name)
        isbn = normalize_isbn(meta.get("isbn") or row.barcode)
        if not isbn:
            skipped += 1
            continue
        hits = openlibrary_search_books(isbn=isbn, limit=3)
        hit = next((candidate for candidate in hits if normalize_isbn(candidate.get("isbn")) == isbn), None)
        if not hit:
            skipped += 1
            continue
        meta.update({"provider": "openlibrary", "isbn": isbn})
        for source, target in (("author", "author"), ("publisher", "publisher")):
            if hit.get(source): meta[target] = hit[source]
        row.external_source = "Open Library"
        row.external_id = hit.get("id") or row.external_id
        row.release_year = row.release_year or hit.get("year")
        if not row.cover_url and hit.get("cover_url"):
            row.cover_url = archived_or_original_image(hit["cover_url"])
        row.metadata_json = json.dumps(meta, ensure_ascii=False)
        updated += 1
    synced_series = sum(1 for name in sorted(series_names) if _sync_book_series_catalog(active_collection_user_id(), name) > 0)
    db.session.commit()
    flash(f"Buchreihen aktualisiert: {updated} ISBN-Einträge erneuert, {synced_series} Reihenkataloge geladen, {skipped} Bücher ohne eindeutige ISBN übersprungen.", "success")
    return redirect(url_for("collector_collections", type="books"))


def _book_collection_aliases(row, meta=None):
    """Return provider identities and normalized names for one book series."""
    meta = meta if isinstance(meta, dict) else collector_metadata(row)
    ids = {
        str(meta.get(key) or "").strip()
        for key in ("series_id", "book_series_id")
        if str(meta.get(key) or "").strip()
    }
    aliases = {
        _match_key(value)
        for value in (meta.get("collection_name"), meta.get("series_name"), meta.get("book_series"))
        if str(value or "").strip()
    }
    return ids, {alias for alias in aliases if alias}


def _book_collection_entries(user_id, anchor):
    """Resolve all locally owned books connected to an anchor's series."""
    rows = CollectorItem.query.filter_by(user_id=user_id, category="books").all()
    anchor_meta = collector_metadata(anchor)
    title, _anchor_order = infer_collector_group(anchor)
    target_ids, target_aliases = _book_collection_aliases(anchor, anchor_meta)
    prepared = []
    for row in rows:
        meta = collector_metadata(row)
        name, order = infer_collector_group(row)
        ids, aliases = _book_collection_aliases(row, meta)
        prepared.append((row, meta, name, order, ids, aliases))
    changed = True
    while changed:
        changed = False
        for _row, _meta, _name, _order, ids, aliases in prepared:
            if not ((target_ids and ids & target_ids) or (target_aliases and aliases & target_aliases)):
                continue
            size = len(target_ids) + len(target_aliases)
            target_ids.update(ids)
            target_aliases.update(aliases)
            changed = changed or len(target_ids) + len(target_aliases) != size
    entries = []
    for row, meta, name, order, ids, aliases in prepared:
        if not ((target_ids and ids & target_ids) or (target_aliases and aliases & target_aliases)):
            continue
        entries.append({"row": row, "meta": meta, "name": name, "order": order,
                        "value": (collector_effective_value(row) or 0) * max(row.quantity or 1, 1)})

    def order_key(entry):
        raw = str(entry.get("order") or "").strip()
        match = re.match(r"^(\d+)(?:[.,](\d+))?", raw)
        numeric = (int(match.group(1)), int(match.group(2) or 0)) if match else (10**9, 0)
        row = entry["row"]
        return numeric + (row.release_year or 9999, (row.title or "").casefold(), row.id)

    entries.sort(key=order_key)
    return str(title or anchor.title).strip(), entries


@app.route("/collector/books/collection/<int:item_id>")
@login_required
def collector_book_collection(item_id):
    uid = active_collection_user_id()
    anchor = CollectorItem.query.filter_by(id=item_id, user_id=uid, category="books").first_or_404()
    title, books = _book_collection_entries(uid, anchor)
    if not books:
        abort(404)
    catalog = _book_series_catalog(uid, title)
    owned_ids = {str(entry["row"].external_id or "").strip() for entry in books if entry["row"].external_id}
    owned_isbns = {normalize_isbn(entry["row"].barcode) for entry in books if normalize_isbn(entry["row"].barcode)}
    owned_titles = {_match_key(entry["row"].title) for entry in books}
    missing = [entry for entry in catalog if not (
        str(entry.get("id") or "").strip() in owned_ids
        or normalize_isbn(entry.get("isbn")) in owned_isbns
        or _match_key(entry.get("title")) in owned_titles
    )]
    return render_template(
        "collector_book_collection.html", title=title, books=books, missing=missing,
        catalog_count=len(catalog), total_value=sum(float(entry["value"] or 0) for entry in books),
        anchor_id=anchor.id,
    )


@app.route("/collector/books/collection/<int:item_id>/refresh", methods=["POST"])
@login_required
def collector_book_collection_refresh(item_id):
    uid = active_collection_user_id()
    anchor = CollectorItem.query.filter_by(id=item_id, user_id=uid, category="books").first_or_404()
    title, _books = _book_collection_entries(uid, anchor)
    count = _sync_book_series_catalog(uid, title)
    db.session.commit()
    if count:
        flash(f"{title}: {count} bekannte Bücher aus Open Library synchronisiert.", "success")
    else:
        flash(f"Für {title} wurde bei Open Library kein eindeutiger Reihenkatalog gefunden.", "warning")
    return redirect(url_for("collector_book_collection", item_id=anchor.id))


@app.route("/collector/consoles/refresh", methods=["POST"])
@login_required
def collector_console_collections_refresh():
    normalize_existing_consoles()
    repaired = repair_pc_hardware_profiles()
    refresh_bibo_registry()
    db.session.commit()
    flash(f"Konsolenreihen aktualisiert und Plattformen normalisiert" + (f"; {repaired} PC-Felder repariert." if repaired else "."), "success")
    return redirect(url_for("collector_collections", type="consoles"))


@app.route("/collector/movies/collection/<collection_id>/refresh", methods=["POST"])
@login_required
def collector_movie_collection_refresh(collection_id):
    uid = active_collection_user_id()
    # First repair all aliases so legacy copies can join this canonical collection.
    checked, changed = _refresh_movie_collections(uid)
    flash(f"Sammlung aktualisiert: {checked} Filmobjekte geprüft, {changed} Zuordnungen/Metadaten aktualisiert.", "success")
    return redirect(url_for("collector_movie_collection", collection_id=collection_id))


@app.route("/collector/movies/collection/<collection_id>", methods=["GET", "POST"])
@login_required
def collector_movie_collection(collection_id):
    """Movie-series checklist with strict German physical-disc semantics.

    TMDB defines the work/series membership only.  A title is counted as missing
    only after a German physical release is evidenced by an owned DE disc or a
    manual confirmation.  Digital-only/unknown titles never reduce completion.
    """
    uid = active_collection_user_id()
    all_rows = CollectorItem.query.filter_by(user_id=uid, category="movies").all()
    related = []
    collection_name = "Filmreihe"
    for row in all_rows:
        meta = collector_metadata(row)
        coll = meta.get("tmdb_collection") or {}
        cid = str(coll.get("id") or "") if isinstance(coll, dict) else ""
        if cid == str(collection_id):
            related.append((row, meta))
            if isinstance(coll, dict) and coll.get("name"):
                collection_name = str(coll.get("name"))
    curated_key, curated_family = _curated_movie_collection_family(collection_id)
    if curated_family:
        related_ids = {row.id for row, _meta in related}
        for row in all_rows:
            if row.id in related_ids:
                continue
            meta = collector_metadata(row)
            text_key, _text_family = _curated_movie_collection_family_from_text(
                row.title, row.edition, meta.get("collection_name"), meta.get("series_name"),
                (meta.get("tmdb_collection") or {}).get("name") if isinstance(meta.get("tmdb_collection"), dict) else "",
            )
            if text_key == curated_key:
                related.append((row, meta))
                related_ids.add(row.id)
        collection_name = str(curated_family.get("title") or collection_name)
    if not related:
        abort(404)

    # v2.14.3: include legacy physical copies that only carry collection_name when
    # that alias belongs unambiguously to this canonical TMDB collection.
    aliases = set()
    for _row, _meta in related:
        _coll = _meta.get("tmdb_collection") or {}
        if isinstance(_coll, dict) and _coll.get("name"):
            aliases.add(_match_key(_coll.get("name")))
        if _meta.get("collection_name"):
            aliases.add(_match_key(_meta.get("collection_name")))
    related_ids = {r.id for r, _ in related}
    for _row in all_rows:
        if _row.id in related_ids:
            continue
        _meta = collector_metadata(_row)
        _coll = _meta.get("tmdb_collection") or {}
        _cid = str(_coll.get("id") or "") if isinstance(_coll, dict) else ""
        if _cid:
            continue
        _alias = _match_key(_meta.get("collection_name") or _meta.get("series_name") or "")
        if _alias and _alias in aliases:
            related.append((_row, _meta))

    statuses = _movie_collection_statuses(uid, collection_id)
    box_links = _movie_box_links(uid, collection_id)
    if request.method == "POST":
        action = str(request.form.get("action") or "status").strip().lower()
        if action == "bulk_status":
            status = str(request.form.get("status") or "unknown").strip().lower()
            if status not in {"physical", "digital", "never_physical_de", "unknown", "not_owned", "auto"}:
                abort(400)
            selected = sorted({str(value).strip() for value in request.form.getlist("part_ids") if str(value).strip().isdigit()}, key=int)
            if not selected:
                flash("Bitte mindestens einen Film auswählen.", "warning")
                return redirect(url_for("collector_movie_collection", collection_id=collection_id))
            for part_id in selected:
                if status == "auto":
                    statuses.pop(part_id, None)
                else:
                    statuses[part_id] = status
            _set_movie_collection_statuses(uid, collection_id, statuses)
            db.session.commit()
            flash(f"Status für {len(selected)} ausgewählte Filme gespeichert.", "success")
            return redirect(url_for("collector_movie_collection", collection_id=collection_id))
        part_id = str(request.form.get("part_id") or "").strip()
        if not part_id.isdigit():
            abort(400)
        if action == "box_link":
            box_item_id = request.form.get("box_item_id", type=int)
            box = db.session.get(CollectorItem, box_item_id) if box_item_id else None
            if not box or box.user_id != uid or box.category != "movies" or not _is_physical_video_media(box):
                abort(400)
            used_elsewhere = _movie_used_single_item_ids(uid, exclude_part_id=part_id)
            if box.id in used_elsewhere and not _collector_multi_part_copy(box):
                flash("Dieses Einzel-Exemplar ist bereits einem anderen Film zugeordnet. Löse dort zuerst die Zuordnung.", "warning")
                return redirect(url_for("collector_movie_collection", collection_id=collection_id, _anchor=f"part-{part_id}"))
            # A physical box may cover any number of parts; only duplicate same part->box is collapsed.
            box_links[part_id] = int(box.id)
            statuses[part_id] = "covered"
            _set_movie_box_links(uid, collection_id, box_links)
            _set_movie_collection_statuses(uid, collection_id, statuses)
            db.session.commit()
            flash(f"{box.title} deckt diesen Film jetzt ab.", "success")
            return redirect(url_for("collector_movie_collection", collection_id=collection_id))
        if action == "box_unlink":
            # Zero/unknown are intentional tombstones. They also override an old
            # link or status inherited from a sibling TMDB collection view.
            box_links[part_id] = 0
            statuses[part_id] = "unknown"
            _set_movie_box_links(uid, collection_id, box_links)
            _set_movie_collection_statuses(uid, collection_id, statuses)
            db.session.commit()
            flash("Box-Zuordnung entfernt.", "success")
            return redirect(url_for("collector_movie_collection", collection_id=collection_id))
        status = str(request.form.get("status") or "unknown").strip().lower()
        if status not in {"physical", "digital", "never_physical_de", "covered", "unknown", "not_owned", "auto"}: abort(400)
        if status == "auto":
            statuses.pop(part_id, None)
        else:
            statuses[part_id] = status
        _set_movie_collection_statuses(uid, collection_id, statuses)
        db.session.commit()
        flash("Status der Filmreihen-Ausgabe gespeichert.", "success")
        return redirect(url_for("collector_movie_collection", collection_id=collection_id))

    details = tmdb_json(f"collection/{quote(str(collection_id), safe='')}", {"language": "de-DE"}) or {}
    family = _tmdb_movie_collection_family(collection_id, details)
    family_ids = {str(x.get("id")) for x in family.get("collections", []) if x.get("id")}
    collection_name = str(family.get("title") or details.get("name") or collection_name)
    tmdb_parts = list(family.get("parts") or [])

    # Inventory assigned to a sibling TMDB collection belongs on the same
    # family page as well. Keep every physical row and deduplicate only by DB id.
    related_ids = {row.id for row, _meta in related}
    family_aliases = set(aliases)
    for family_collection in family.get("collections", []):
        family_aliases.add(_match_key(family_collection.get("name") or ""))
    for row in all_rows:
        if row.id in related_ids:
            continue
        meta = collector_metadata(row)
        coll = meta.get("tmdb_collection") or {}
        cid = str(coll.get("id") or "") if isinstance(coll, dict) else ""
        alias = _match_key(meta.get("collection_name") or meta.get("series_name") or "")
        if cid in family_ids or (not cid and alias and alias in family_aliases):
            related.append((row, meta))
            related_ids.add(row.id)

    # Preserve manual work done from any sibling collection detail. Values on
    # the currently opened canonical route win if the same movie was edited in
    # more than one former view.
    current_statuses = dict(statuses)
    current_box_links = dict(box_links)
    merged_statuses = {}
    merged_box_links = {}
    for family_id in sorted(family_ids):
        if family_id == str(collection_id):
            continue
        merged_statuses.update(_movie_collection_statuses(uid, family_id))
        merged_box_links.update(_movie_box_links(uid, family_id))
    merged_statuses.update(current_statuses)
    merged_box_links.update(current_box_links)
    statuses = merged_statuses
    box_links = merged_box_links

    owned_by_tmdb = {}
    covered_ids = set()
    # Assignment must show every recorded physical movie copy, even when a
    # legacy row has no country metadata yet. Strict DE evidence is evaluated
    # separately for automatic completion below.
    physical_candidates = [r for r in all_rows if _is_physical_video_media(r)]
    physical_candidates.sort(key=lambda r: ((r.title or "").casefold(), (r.edition or "").casefold(), r.id))
    box_by_id = {r.id: r for r in physical_candidates}
    used_single_ids = _movie_used_single_item_ids(uid)
    for row, meta in related:
        rid = str(meta.get("tmdb_id") or row.external_id or "").strip()
        is_de_disc = _is_de_physical_media(row)
        if rid and is_de_disc:
            owned_by_tmdb.setdefault(rid, []).append(row)
        included = meta.get("included_tmdb_ids") or []
        if isinstance(included, list) and is_de_disc:
            covered_ids.update(str(x) for x in included if str(x).isdigit())

    parts = []
    for part in sorted(tmdb_parts, key=lambda x: (str(x.get("release_date") or "9999"), str(x.get("title") or "").casefold())):
        pid = str(part.get("id"))
        owned_rows = owned_by_tmdb.get(pid, [])
        if not owned_rows:
            # Legacy/imported copies can have a wrong/missing TMDB id while the physical title is clearly the same work.
            # Conservative alias fallback: require a German physical copy and a strong normalized-title containment match.
            target_key = _match_key(part.get("title") or part.get("original_title") or "")
            if target_key:
                aliases=[]
                for candidate in physical_candidates:
                    ck=_match_key(candidate.title or "")
                    if ck and (ck == target_key or (len(target_key) >= 8 and target_key in ck) or (len(ck) >= 8 and ck in target_key)):
                        aliases.append(candidate)
                if len(aliases) == 1:
                    owned_rows = aliases
        manual = statuses.get(pid)
        recognized_rows = list(owned_rows)
        if manual == "not_owned":
            status = "not_owned"
            owned_rows = []
        elif owned_rows:
            status = "owned"
        elif pid in covered_ids or manual == "covered" or (pid in box_links and str(box_links.get(pid) or "").isdigit() and int(box_links.get(pid) or 0) > 0):
            status = "covered"
        elif manual:
            status = manual
        else:
            # TMDB release type 5 = physical release. Only positive German evidence is
            # promoted automatically; absence remains unknown (never guessed as "no DE disc").
            status = "unknown"
            de_physical_evidence = False
            de_release_data_checked = False
            try:
                release_info = tmdb_json(f"movie/{pid}/release_dates", {}) or {}
                de_entries = next((x.get("release_dates") or [] for x in (release_info.get("results") or []) if x.get("iso_3166_1") == "DE"), [])
                de_release_data_checked = True
                if any(int(x.get("type") or 0) == 5 for x in de_entries):
                    status = "physical"
                    de_physical_evidence = True
                elif de_entries and all(int(x.get("type") or 0) == 4 for x in de_entries if x.get("type")):
                    status = "digital"
            except Exception:
                status = "unknown"
                de_release_data_checked = False
        if manual or owned_rows or pid in covered_ids or (pid in box_links and str(box_links.get(pid) or "").isdigit() and int(box_links.get(pid) or 0) > 0):
            # A manual/inventory decision outranks provider metadata. The two
            # flags are informational only and must never silently create a
            # negative physical-release assertion.
            de_physical_evidence = status in {"owned", "covered", "physical"}
            de_release_data_checked = False
        part_value = sum((collector_effective_value(r) or 0) * max(r.quantity or 1, 1) for r in owned_rows)
        linked_box = box_by_id.get(int(box_links[pid])) if pid in box_links and str(box_links[pid]).isdigit() else None
        assignment_candidates = [
            row for row in physical_candidates
            if row.id not in used_single_ids or _collector_multi_part_copy(row) or (linked_box and row.id == linked_box.id)
        ]
        parts.append({
            "id": pid, "title": part.get("title") or part.get("original_title") or f"Film {pid}",
            "year": int(str(part.get("release_date") or "")[:4]) if str(part.get("release_date") or "")[:4].isdigit() else None,
            "release_date": part.get("release_date"), "cover": tmdb_poster_url(part.get("poster_path")),
            "status": status, "owned_rows": owned_rows, "recognized_rows": recognized_rows, "value": part_value,
            "box_item": linked_box,
            "box_value": ((collector_effective_value(linked_box) or 0) * max(linked_box.quantity or 1, 1)) if linked_box else 0,
            "assignment_candidates": assignment_candidates,
            "de_physical_evidence": de_physical_evidence,
            "de_release_data_checked": de_release_data_checked,
        })

    relevant = [x for x in parts if x["status"] in {"owned", "covered", "physical", "not_owned"}]
    owned_count = sum(1 for x in relevant if x["status"] in {"owned", "covered"})
    physical_total = len(relevant)
    missing_count = sum(1 for x in relevant if x["status"] in {"physical", "not_owned"})
    digital_count = sum(1 for x in parts if x["status"] == "digital")
    never_physical_de_count = sum(1 for x in parts if x["status"] == "never_physical_de")
    unknown_count = sum(1 for x in parts if x["status"] == "unknown")
    pct = round(owned_count * 100 / physical_total) if physical_total else None
    # Count each physical inventory row once. A box may cover several films, but
    # its value must never be repeated for every covered part.
    value_rows = {}
    for part in parts:
        if part["status"] == "owned":
            for row in part["owned_rows"]:
                value_rows[row.id] = row
    for part_id, item_id in box_links.items():
        if not any(part["id"] == str(part_id) and part["status"] == "covered" for part in parts):
            continue
        try:
            linked_box = box_by_id.get(int(item_id))
        except (TypeError, ValueError):
            linked_box = None
        if linked_box:
            value_rows[linked_box.id] = linked_box
    total_value = sum((collector_effective_value(r) or 0) * max(r.quantity or 1, 1) for r in value_rows.values())
    return render_template("collector_movie_collection.html", title=collection_name, collection_id=collection_id,
                           parts=parts, owned_count=owned_count, physical_total=physical_total, missing_count=missing_count,
                           digital_count=digital_count, never_physical_de_count=never_physical_de_count,
                           unknown_count=unknown_count, pct=pct, total_value=total_value,
                           family_collections=family.get("collections", []),
                           family_scope=family.get("scope"))


def _series_ownership_override_key(user_id, franchise):
    digest = hashlib.sha1(_search_text(franchise).encode("utf-8")).hexdigest()[:20]
    return f"series_owned_override:{int(user_id)}:{digest}"


def _series_ownership_exclusions(user_id, franchise):
    raw = app_setting_get(_series_ownership_override_key(user_id, franchise), "")
    try:
        data = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        data = []
    return {str(x) for x in data if str(x).strip()}


def _set_series_ownership_exclusions(user_id, franchise, values):
    app_setting_set(_series_ownership_override_key(user_id, franchise), json.dumps(sorted(set(values)), ensure_ascii=False))


@app.route("/franchises/<path:name>/ownership", methods=["POST"])
@login_required
def franchise_ownership_override(name):
    canonical_key = str(request.form.get("canonical_key") or "").strip()
    action = str(request.form.get("action") or "exclude").strip().lower()
    if not canonical_key or action not in {"exclude", "auto"}:
        abort(400)
    excluded = _series_ownership_exclusions(active_collection_user_id(), name)
    if action == "exclude":
        excluded.add(canonical_key)
        flash("Titel wird in dieser Reihe jetzt als nicht im Besitz geführt. Das Exemplar selbst bleibt erhalten.", "success")
    else:
        excluded.discard(canonical_key)
        flash("Für diesen Titel gilt wieder die automatische Besitzerkennung.", "success")
    _set_series_ownership_exclusions(active_collection_user_id(), name, excluded)
    db.session.commit()
    return redirect(url_for("franchise_detail", name=name) + f"#series-{hashlib.sha1(canonical_key.encode('utf-8')).hexdigest()[:10]}")


def _game_franchise_overview_rows(user_id):
    """Canonical game-series cards visible only in the selected collection."""
    all_games = [g for g in Game.query.filter(Game.franchise.isnot(None), Game.franchise != "").order_by(Game.id).all() if game_is_physical_candidate(g)]
    all_entries = SeriesEntry.query.order_by(SeriesEntry.id).all()
    owned_by_game = {}
    owned_items = CollectionItem.query.filter_by(user_id=user_id, status="owned").filter(CollectionItem.ownership_format != "digital").all()
    for item in owned_items:
        owned_by_game.setdefault(item.game_id, []).append(item)
    # A collection only gets series cards for franchises it actually owns.
    # SeriesEntry is global catalogue metadata and must never make a fresh or
    # unrelated collection look as if it already had another collection's
    # series progress (the old 0/1-style ghost cards).
    owned_game_ids = set(owned_by_game)
    names = {canonical_franchise_name(g.franchise) for g in all_games if g.id in owned_game_ids}
    rows = []
    for name in sorted((x for x in names if x), key=_search_text):
        excluded_keys = _series_ownership_exclusions(user_id, name)
        franchise_games = [g for g in all_games if canonical_franchise_name(g.franchise) == name]
        if name == "FIFA":
            franchise_games.extend(g for g in Game.query.filter(db.or_(Game.title.ilike("FIFA%"), Game.title.ilike("EA SPORTS FC%"), Game.title.ilike("%FIFA World Cup%"), Game.title.ilike("UEFA Euro%"))).all() if g not in franchise_games and game_is_physical_candidate(g))
        entries = [e for e in all_entries if canonical_franchise_name(e.franchise) == name]
        if name in CURATED_SERIES:
            entries = [e for e in entries if e.external_source == "GameCollector"]
        catalog_keys = {canonical_series_item_key(name, g.title) for g in franchise_games}
        catalog_keys.update(canonical_series_item_key(name, e.title) for e in entries if external_is_physical_candidate(e))
        owned_keys = set()
        value = 0.0
        copy_count = valued_count = 0
        last_valued_at = None
        covers = []
        for game in franchise_games:
            series_key = canonical_series_item_key(name, game.title)
            if series_key in excluded_keys:
                continue
            copies = owned_by_game.get(game.id, [])
            if copies:
                owned_keys.add(series_key)
                if game.cover_url:
                    covers.append((game.release_year or 9999, game.console.name if game.console else "", game.cover_url))
            for item in copies:
                copy_count += 1
                item_value = effective_value(item)
                if item_value is None:
                    continue
                valued_count += 1
                value += float(item_value)
                if item.auto_value_updated_at and (last_valued_at is None or item.auto_value_updated_at > last_valued_at):
                    last_valued_at = item.auto_value_updated_at
        total = len(catalog_keys)
        owned = len(owned_keys & catalog_keys)
        # Series metadata belongs to the shared catalog, but a series card is
        # collection inventory.  Never leak a series from another logical
        # collection as 0/x into a newly created or empty collection.
        if owned == 0:
            continue
        pct = 100 if total and owned == total else min(99, round(owned * 100 / total)) if total else 0
        cover = sorted(covers, key=lambda x: (x[0], _search_text(x[1])))[0][2] if covers else None
        rows.append({"name": name, "total": total, "owned": owned, "missing": max(0, total-owned), "pct": pct,
                     "value": round(value, 2), "copy_count": copy_count, "valued_count": valued_count,
                     "last_valued_at": last_valued_at, "cover": cover})
    return rows


def _console_family_name(console_name, manufacturer=""):
    """Return a stable, user-facing hardware series for a console generation."""
    name = _search_text(console_name)
    maker = _search_text(manufacturer)
    if "playstation" in name or name in {"psp", "ps vita"}:
        return "PlayStation"
    if "xbox" in name:
        return "Xbox"
    if (name.startswith("nintendo ") or name.startswith("game boy") or name in {
        "nintendo entertainment system nes", "super nintendo snes", "wii", "wii u",
    }):
        return "Nintendo"
    if any(token in name for token in ("master system", "mega drive", "genesis", "game gear", "saturn", "dreamcast")) or "sega" in maker:
        return "Sega"
    if "atari" in name or "atari" in maker:
        return "Atari"
    if "neo geo" in name or "snk" in maker:
        return "SNK / Neo Geo"
    return (manufacturer or console_name or "Weitere Konsolen").strip()


def _console_family_rows():
    """Build real console-series progress from catalog generations, not copies."""
    families = {}
    year_catalog = {
        "Nintendo Entertainment System (NES)": 1986, "Super Nintendo (SNES)": 1992,
        "Nintendo 64": 1997, "Nintendo GameCube": 2002, "Wii": 2006, "Wii U": 2012,
        "Nintendo Switch": 2017, "Nintendo Switch 2": 2025, "Game Boy": 1990,
        "Game Boy Color": 1998, "Game Boy Advance": 2001, "Nintendo DS": 2005,
        "Nintendo 3DS": 2011, "PlayStation": 1995, "PlayStation 2": 2000,
        "PlayStation 3": 2007, "PlayStation 4": 2013, "PlayStation 5": 2020,
        "PSP": 2005, "PS Vita": 2012, "Xbox": 2002, "Xbox 360": 2005,
        "Xbox One": 2013, "Xbox Series X|S": 2020, "Master System": 1987,
        "Mega Drive / Genesis": 1990, "Game Gear": 1991, "Saturn": 1995,
        "Dreamcast": 1999, "Atari 2600": 1980, "Atari 7800": 1987,
        "Atari Jaguar": 1994, "Neo Geo": 1990,
    }
    consoles = Console.query.order_by(Console.name).all()
    by_name = {_match_key(console.name): console for console in consoles}
    catalog_names = [name for name in HARDWARE_MODEL_PRESETS if name != "PC"]
    catalog_names.extend(console.name for console in consoles if console.name not in HARDWARE_MODEL_PRESETS and _search_text(console.name) != "pc")
    for catalog_name in dict.fromkeys(catalog_names):
        console = by_name.get(_match_key(catalog_name))
        models = list(console.hardware_models or []) if console else []
        manufacturer = console.manufacturer if console else ("Nintendo" if _console_family_name(catalog_name) == "Nintendo" else "")
        family = _console_family_name(catalog_name, manufacturer)
        bucket = families.setdefault(family, {"name": family, "type": "consoles", "label": "Konsolenreihen", "icon": "🕹️", "items": [], "value": 0.0})
        owned_items = [item for model in models for item in model.items if item.status == "owned" and item.user_id == active_collection_user_id()]
        value = sum(float(effective_hardware_value(item) or 0) for item in owned_items)
        years = [model.release_year for model in models if model.release_year]
        if catalog_name in year_catalog:
            years.append(year_catalog[catalog_name])
        cover = next((model.reference_image for model in models if model.reference_image and any(item.status == "owned" and item.user_id == active_collection_user_id() for item in model.items)), None)
        cover = cover or next((model.reference_image for model in models if model.reference_image), None)
        model = models[0] if models else None
        bucket["items"].append({
            "order": min(years) if years else None,
            "title": catalog_name,
            "subtitle": f"{len(models)} Modelle · {len(owned_items)} Exemplare",
            "cover": cover,
            "url": url_for("hardware_detail", model_id=model.id) if model else url_for("hardware", q=catalog_name),
            "value": value,
            "owned": bool(owned_items),
            "console_id": console.id if console else None,
            "models": models,
            "owned_items": owned_items,
        })
        bucket["value"] += value
    rows = []
    for bucket in families.values():
        bucket["items"].sort(key=lambda item: ((item["order"] is None), item["order"] or 9999, item["title"].casefold()))
        bucket["total"] = len(bucket["items"])
        bucket["owned"] = sum(1 for item in bucket["items"] if item["owned"])
        bucket["missing"] = bucket["total"] - bucket["owned"]
        bucket["pct"] = round(bucket["owned"] * 100 / bucket["total"]) if bucket["total"] else 0
        bucket["cover"] = next((item["cover"] for item in bucket["items"] if item.get("owned") and item.get("cover")), None) or next((item["cover"] for item in bucket["items"] if item.get("cover")), None)
        bucket["copy_count"] = sum(len(item["owned_items"]) for item in bucket["items"])
        bucket["valued_count"] = sum(1 for item in bucket["items"] for copy in item["owned_items"] if effective_hardware_value(copy) is not None)
        updated = [copy.auto_value_updated_at for item in bucket["items"] for copy in item["owned_items"] if copy.auto_value_updated_at]
        bucket["last_valued_at"] = max(updated) if updated else None
        # Use this bucket's own name. The outer catalog loop's ``family``
        # variable otherwise makes every card point to the same last family.
        bucket["detail_url"] = url_for("collector_console_family", family=bucket["name"])
        # A manufacturer family becomes a collection only after the user owns
        # at least one physical console from it.  Once visible, the complete
        # curated German target list remains available for completion tracking.
        if bucket["owned"] > 0:
            rows.append(bucket)
    return rows


@app.route("/collector/consoles/family/<path:family>")
@login_required
def collector_console_family(family):
    row = next((entry for entry in _console_family_rows() if _search_text(entry["name"]) == _search_text(family)), None)
    if not row:
        abort(404)
    return render_template("collector_console_family.html", family=row)


@app.route("/collector/collections")
@login_required
def collector_collections():
    """Universal tile overview for series and collection families."""
    kind = (request.args.get("type") or "all").strip().lower()
    allowed = {"all", "games", "books", "tv", "movies", "consoles"}
    if kind not in allowed:
        kind = "all"
    query_text = (request.args.get("q") or "").strip()
    status_filter = (request.args.get("status") or "all").strip().lower()
    if status_filter not in {"all", "complete", "incomplete", "started", "not_started", "unresolved"}:
        status_filter = "all"
    valuation_filter = (request.args.get("valuation") or "all").strip().lower()
    if valuation_filter not in {"all", "valued", "unvalued", "partial"}:
        valuation_filter = "all"
    sort = (request.args.get("sort") or "name").strip().lower()
    if sort not in {"name", "name_desc", "value_desc", "value_asc", "progress_desc", "progress_asc", "missing_desc", "updated_desc", "owned_desc"}:
        sort = "name"
    user_id = active_collection_user_id()
    groups = []

    if kind in {"all", "games"}:
        for row in _game_franchise_overview_rows(user_id):
            groups.append({**row, "type": "games", "label": "Spielreihen", "icon": "🎮", "items": [],
                           "detail_url": url_for("franchise_detail", name=row["name"])})

    if kind in {"all", "books", "tv", "movies"}:
        labels = {"books": "Buchreihen", "tv": "TV-Serien", "movies": "Filmreihen"}
        icons = {"books": "📚", "tv": "📺", "movies": "🎬"}
        query = CollectorItem.query.filter(CollectorItem.user_id == user_id, CollectorItem.category.in_(["books", "tv", "movies"]))
        source_rows = [r for r in query.all() if kind == "all" or r.category == kind]
        inferred_added = sum(sync_inferred_release_coverages(row) for row in source_rows)
        if inferred_added:
            db.session.commit()

        # v2.14.3: build canonical aliases first.  A physical copy is inventory, not a
        # series.  External work/series ids win; names are only aliases/fallbacks.
        alias_to_canonical = {"movies": {}, "tv": {}, "books": {}}
        resolved = []
        for row in source_rows:
            meta = collector_metadata(row)
            name, order = infer_collector_group(row)
            canonical_id = ""
            aliases = set()
            if name:
                aliases.add(_match_key(name))
            if row.category == "movies":
                coll = meta.get("tmdb_collection") or {}
                if isinstance(coll, dict):
                    canonical_id = str(coll.get("id") or "").strip()
                    if coll.get("name"): aliases.add(_match_key(coll.get("name")))
                if meta.get("collection_name"): aliases.add(_match_key(meta.get("collection_name")))
                # Resolve a known TMDB movie to its canonical collection. This also repairs
                # old imports that only stored collection_name.
                if not canonical_id:
                    mid = str(meta.get("tmdb_id") or (row.external_id if str(row.external_source or '').upper() == 'TMDB' else '') or "").strip()
                    if mid.isdigit():
                        md = tmdb_json(f"movie/{mid}", {"language":"de-DE"}) or {}
                        rc = md.get("belongs_to_collection") or {}
                        if isinstance(rc, dict) and rc.get("id"):
                            canonical_id = str(rc.get("id"))
                            if rc.get("name"): aliases.add(_match_key(rc.get("name")))
                # Legacy film copies may have only a translated series/title hint.
                # Curated families still get their stable detail route and catalog.
                if not canonical_id:
                    _text_key, _text_family = _curated_movie_collection_family_from_text(
                        row.title, row.edition, name, meta.get("collection_name"), meta.get("series_name")
                    )
                    if _text_family:
                        canonical_id = str(_text_family.get("collection_ids", ("",))[0])
                        name = str(_text_family.get("title") or name)
                        aliases.add(_match_key(name))
                # Provider-split members of a curated family share one overview row.
                _family_key, _family = _curated_movie_collection_family(canonical_id)
                if _family:
                    canonical_id = str(_family.get("collection_ids", (canonical_id,))[0])
                    name = str(_family.get("title") or name)
                    aliases.add(_match_key(name))
            elif row.category == "tv":
                tid = str(meta.get("tmdb_id") or (row.external_id if str(row.external_source or '').upper() == 'TMDB' else '') or "").strip()
                if tid.isdigit(): canonical_id = tid
                name = _canonical_tv_series_name(row)
                if name: aliases.add(_match_key(name))
                if meta.get("collection_name"): aliases.add(_match_key(meta.get("collection_name")))
                if meta.get("original_title"): aliases.add(_match_key(meta.get("original_title")))
            elif row.category == "books":
                # Prefer provider series ids when present; otherwise one normalized series name.
                canonical_id = str(meta.get("series_id") or meta.get("book_series_id") or "").strip()
                if meta.get("book_series"): aliases.add(_match_key(meta.get("book_series")))
                if meta.get("series_name"): aliases.add(_match_key(meta.get("series_name")))
            resolved.append((row, meta, name, order, canonical_id, aliases))
            if canonical_id:
                for alias in aliases:
                    if alias:
                        alias_to_canonical[row.category].setdefault(alias, canonical_id)

        buckets = {}
        for row, meta, name, order, canonical_id, aliases in resolved:
            # Attach legacy/provider-only inventory to an already known canonical group when
            # an unambiguous normalized alias exists (e.g. Family Guy / Fluch der Karibik).
            if not canonical_id:
                matches = {alias_to_canonical[row.category].get(a) for a in aliases if alias_to_canonical[row.category].get(a)}
                if len(matches) == 1:
                    canonical_id = matches.pop()
            if not name:
                continue
            if canonical_id:
                key = (row.category, "id:" + canonical_id)
            else:
                # No external identity: keep one conservative normalized-name group. Do not
                # invent a second collection from edition/season suffixes.
                fallback = next((a for a in aliases if a), _match_key(name))
                key = (row.category, "name:" + fallback)
            b = buckets.setdefault(key, {"name": name.removesuffix(" Filmreihe").strip(), "type": row.category, "label": labels[row.category], "icon": icons[row.category], "items": [], "value": 0.0, "_orders": set(), "_logical_units": set(), "_owned_work_ids": set(), "_total_candidates": [], "_canonical_id": canonical_id, "_canonical_score": 0, "_aliases": set()})
            b["_aliases"].update(aliases)
            if canonical_id and not b.get("_canonical_id"):
                b["_canonical_id"] = canonical_id
            # Prefer the clean collection/series name from canonical metadata.
            work_id = ""
            if row.category == "movies":
                coll = meta.get("tmdb_collection") or {}
                _family_key, _family = _curated_movie_collection_family(canonical_id)
                if _family:
                    b["name"] = str(_family.get("title") or b["name"])
                elif isinstance(coll, dict) and coll.get("name"):
                    b["name"] = str(coll.get("name")).removesuffix(" Filmreihe").strip()
                work_id = str(meta.get("tmdb_id") or (row.external_id if str(row.external_source or "").upper() == "TMDB" else "") or "").strip()
                if work_id.isdigit():
                    b["_owned_work_ids"].add(work_id)
                included = meta.get("included_tmdb_ids") or []
                if isinstance(included, list):
                    b["_owned_work_ids"].update(str(x) for x in included if str(x).isdigit())
            elif row.category == "tv" and meta.get("original_title") and not b.get("name"):
                b["name"] = str(meta.get("original_title"))
            qty = max(row.quantity or 1, 1)
            value = (collector_effective_value(row) or 0) * qty
            b["items"].append({"id": row.id, "order": order, "title": row.title, "subtitle": row.edition or row.media_type or labels[row.category], "cover": row.cover_url, "url": url_for("collector_item_detail", item_id=row.id), "value": value, "work_id": work_id})
            b["value"] += value
            b["_logical_units"].add(logical_collection_unit_key(row, meta, order))
            if order not in (None, ""):
                # A season split across 1.1/1.2 is one owned season, while the
                # physical copies and their values remain separate inventory.
                normalized_order = _tv_season_number(row, meta) if row.category == "tv" else order
                b["_orders"].add(str(normalized_order if normalized_order is not None else order))
            if row.category == "tv":
                total = meta.get("season_count") or meta.get("number_of_seasons")
                try:
                    if total is not None and int(total) > 0:
                        b["_total_candidates"].append(int(total))
                except (TypeError, ValueError):
                    pass

        # Second merge pass: if a legacy name-only bucket aliases exactly one canonical bucket,
        # fold it in. This prevents old physical editions from resurfacing as duplicate rows.
        canonical_aliases = {}
        for key, b in buckets.items():
            if key[1].startswith("id:"):
                for alias in b.get("_aliases", set()):
                    if alias:
                        canonical_aliases.setdefault((b["type"], alias), []).append(key)
        for key in list(buckets):
            if key not in buckets or key[1].startswith("id:"):
                continue
            b = buckets[key]
            targets = set()
            for alias in b.get("_aliases", set()):
                ks = canonical_aliases.get((b["type"], alias), [])
                if len(ks) == 1: targets.add(ks[0])
            if len(targets) != 1:
                continue
            target_key = targets.pop(); target = buckets[target_key]
            target["items"].extend(b["items"]); target["value"] += b["value"]
            target["_orders"].update(b["_orders"]); target["_logical_units"].update(b["_logical_units"]); target["_owned_work_ids"].update(b["_owned_work_ids"]); target["_total_candidates"].extend(b["_total_candidates"])
            del buckets[key]

        for b in buckets.values():
            b["items"].sort(key=lambda x: ((x["order"] is None), str(x["order"] or ""), x["title"].casefold()))
            b["owned"] = len(b["_logical_units"])
            b["total"] = max(b["_total_candidates"], default=None)
            canonical_id = str(b.get("_canonical_id") or "").strip()
            if b["type"] == "movies" and canonical_id:
                details = tmdb_json(f"collection/{quote(canonical_id, safe='')}", {"language": "de-DE"}) or {}
                _family_key, _family = _curated_movie_collection_family(canonical_id)
                if _family:
                    family = _tmdb_movie_collection_family(canonical_id, details)
                    collection_ids = {str(x.get("id")) for x in family.get("collections", []) if x.get("id")}
                    known_parts = list(family.get("parts") or [])
                    b["name"] = str(family.get("title") or b["name"])
                else:
                    collection_ids = {canonical_id}
                    known_parts = [x for x in (details.get("parts") or []) if isinstance(x, dict) and x.get("id")]
                known_ids = {str(x.get("id")) for x in known_parts}
                covered_ids = set()
                excluded_ids = set()
                never_physical_de_ids = set()
                digital_only_ids = set()
                for family_id in collection_ids:
                    links = _movie_box_links(user_id, family_id)
                    covered_ids.update(str(pid) for pid, item_id in links.items() if str(item_id or "").isdigit() and int(item_id or 0) > 0)
                    statuses = _movie_collection_statuses(user_id, family_id)
                    covered_ids.update(str(pid) for pid, status in statuses.items() if status == "covered")
                    excluded_ids.update(str(pid) for pid, status in statuses.items() if status == "not_owned")
                    never_physical_de_ids.update(str(pid) for pid, status in statuses.items() if status == "never_physical_de")
                    digital_only_ids.update(str(pid) for pid, status in statuses.items() if status == "digital")
                source_ids = [str(item["id"]) for item in b["items"]]
                if source_ids:
                    explicit = ReleaseCoverage.query.filter(ReleaseCoverage.owner_id == user_id, ReleaseCoverage.source_kind == "collector",
                        ReleaseCoverage.source_id.in_(source_ids), ReleaseCoverage.target_kind == "movies").all()
                    covered_ids.update(entry.target_key.rsplit(":", 1)[-1] for entry in explicit if entry.target_key.rsplit(":", 1)[-1].isdigit())
                nonphysical_de_ids = never_physical_de_ids | digital_only_ids
                target_ids = known_ids - nonphysical_de_ids
                recognized_owned = ((set(b["_owned_work_ids"]) | covered_ids) - excluded_ids) & target_ids
                if target_ids or known_ids:
                    b["total"] = len(target_ids)
                    b["owned"] = len(recognized_owned) if (recognized_owned or excluded_ids or nonphysical_de_ids) else min(b["owned"], b["total"])
                    b["never_physical_de_count"] = len(never_physical_de_ids & known_ids)
                    b["digital_only_count"] = len(digital_only_ids & known_ids)
                if excluded_ids:
                    b["value"] = max(0.0, b["value"] - sum(float(item.get("value") or 0) for item in b["items"] if str(item.get("work_id") or "") in excluded_ids))
            elif b["type"] == "tv" and canonical_id and b["total"] is not None:
                provider_total = int(b["total"] or 0)
                owned_seasons = {int(x) for x in b["_orders"] if str(x).isdigit() and 1 <= int(x) <= provider_total}
                statuses = _tv_disc_statuses(user_id, canonical_id)
                source_ids = [str(item["id"]) for item in b["items"]]
                if source_ids:
                    explicit = ReleaseCoverage.query.filter(ReleaseCoverage.owner_id == user_id, ReleaseCoverage.source_kind == "collector",
                        ReleaseCoverage.source_id.in_(source_ids), ReleaseCoverage.target_kind == "tv").all()
                    for entry in explicit:
                        match = re.search(r":season:(\d+)$", entry.target_key)
                        if match: owned_seasons.add(int(match.group(1)))
                never_physical = {int(season) for season, status in statuses.items() if str(season).isdigit() and 1 <= int(season) <= provider_total and status == "never_physical_de"}
                digital_only = {int(season) for season, status in statuses.items() if str(season).isdigit() and 1 <= int(season) <= provider_total and status == "digital"}
                excluded_seasons = (never_physical | digital_only) - owned_seasons
                target_seasons = set(range(1, provider_total + 1)) - excluded_seasons
                b["total"] = len(target_seasons)
                b["owned"] = len(owned_seasons & target_seasons)
                b["never_physical_de_count"] = len(never_physical - owned_seasons)
                b["digital_only_count"] = len(digital_only - owned_seasons)
            elif b["type"] == "books":
                catalog = _book_series_catalog(user_id, b["name"])
                if catalog:
                    known = {str(item.get("id") or "").strip() or _match_key(item.get("title")) for item in catalog}
                    b["total"] = max(len({item for item in known if item}), b["owned"])
            if b["total"] is not None:
                b["total"] = max(b["total"], b["owned"])
            b["pct"] = round(b["owned"] * 100 / b["total"]) if b["total"] else None
            b["cover"] = next((x["cover"] for x in b["items"] if x.get("cover")), None)
            b["copy_count"] = len(b["items"])
            b["valued_count"] = sum(1 for x in b["items"] if x.get("value") is not None and float(x.get("value") or 0) > 0)
            b["last_valued_at"] = None
            b["missing"] = max(0, int(b["total"] or 0) - int(b["owned"] or 0)) if b["total"] else 0
            if b["type"] == "tv":
                b["detail_url"] = url_for("collector_tv_collection", tmdb_id=canonical_id) if canonical_id else None
            elif b["type"] == "movies":
                b["detail_url"] = url_for("collector_movie_collection", collection_id=canonical_id) if canonical_id else None
            elif b["type"] == "books" and b["items"]:
                b["detail_url"] = url_for("collector_book_collection", item_id=b["items"][0]["id"])
            b.pop("_orders", None); b.pop("_logical_units", None); b.pop("_owned_work_ids", None); b.pop("_total_candidates", None); b.pop("_canonical_id", None); b.pop("_canonical_score", None); b.pop("_aliases", None)
            groups.append(b)

    if kind in {"all", "consoles"}:
        groups.extend(_console_family_rows())

    all_groups = list(groups)
    overview = {
        "groups": len(all_groups),
        "owned": sum(int(b.get("owned") or 0) for b in all_groups),
        "value": sum(float(b.get("value") or 0) for b in all_groups),
        "complete": sum(1 for b in all_groups if b.get("total") and int(b.get("owned") or 0) >= int(b["total"])),
        "unresolved": sum(1 for b in all_groups if not b.get("total")),
    }
    if query_text:
        needle = _search_text(query_text)
        groups = [b for b in groups if needle in _search_text(b.get("name")) or any(needle in _search_text(x.get("title")) for x in b.get("items", []))]
    if status_filter == "complete":
        groups = [b for b in groups if b.get("total") and int(b.get("owned") or 0) >= int(b["total"])]
    elif status_filter == "incomplete":
        groups = [b for b in groups if b.get("total") and 0 < int(b.get("owned") or 0) < int(b["total"])]
    elif status_filter == "started":
        groups = [b for b in groups if int(b.get("owned") or 0) > 0]
    elif status_filter == "not_started":
        groups = [b for b in groups if b.get("total") and int(b.get("owned") or 0) == 0]
    elif status_filter == "unresolved":
        groups = [b for b in groups if not b.get("total")]
    if valuation_filter == "valued":
        groups = [b for b in groups if int(b.get("copy_count") or 0) > 0 and int(b.get("valued_count") or 0) >= int(b.get("copy_count") or 0)]
    elif valuation_filter == "unvalued":
        groups = [b for b in groups if int(b.get("copy_count") or 0) > 0 and int(b.get("valued_count") or 0) == 0]
    elif valuation_filter == "partial":
        groups = [b for b in groups if 0 < int(b.get("valued_count") or 0) < int(b.get("copy_count") or 0)]
    if sort == "value_desc":
        groups.sort(key=lambda b: (float(b.get("value") or 0), b.get("name", "").casefold()), reverse=True)
    elif sort == "value_asc":
        groups.sort(key=lambda b: (float(b.get("value") or 0) <= 0, float(b.get("value") or 0), b.get("name", "").casefold()))
    elif sort == "progress_desc":
        groups.sort(key=lambda b: (b.get("pct") is not None, int(b.get("pct") or -1), int(b.get("owned") or 0), b.get("name", "").casefold()), reverse=True)
    elif sort == "progress_asc":
        groups.sort(key=lambda b: (b.get("pct") is None, int(b.get("pct") or 0), b.get("name", "").casefold()))
    elif sort == "missing_desc":
        groups.sort(key=lambda b: (int(b.get("missing") or 0), int(b.get("total") or 0)), reverse=True)
    elif sort == "updated_desc":
        groups.sort(key=lambda b: b.get("last_valued_at") or datetime.min, reverse=True)
    elif sort == "owned_desc":
        groups.sort(key=lambda b: (int(b.get("owned") or 0), float(b.get("value") or 0), b.get("name", "").casefold()), reverse=True)
    elif sort == "name_desc":
        groups.sort(key=lambda b: (b["label"], b["name"].casefold()), reverse=True)
    else:
        groups.sort(key=lambda b: (b["label"], b["name"].casefold()))
    return render_template("collector_collections.html", groups=groups, selected_type=kind, query_text=query_text, selected_status=status_filter, selected_valuation=valuation_filter, selected_sort=sort, overview=overview)


@app.route("/collector/<section>")
@login_required
def collector_section(section):
    config = dict(COLLECTOR_SECTIONS.get(section) or {})
    if not config:
        abort(404)
    rows = CollectorItem.query.filter_by(user_id=active_collection_user_id(), category=section).all()
    custom_categories = custom_collection_categories(active_collection_user_id()) if section == "custom" else []
    selected_custom_category = (request.args.get("custom_category") or "").strip() if section == "custom" else ""
    selected_custom_config = _custom_collection_category(active_collection_user_id(), selected_custom_category) if selected_custom_category else None
    if selected_custom_category and not selected_custom_config:
        abort(404)
    if selected_custom_config:
        rows = [row for row in rows if collector_metadata(row).get("custom_category") == selected_custom_category]
        config.update({"title": selected_custom_config["title"], "singular": "Objekt", "icon": selected_custom_config["icon"],
                       "description": selected_custom_config["description"] or "Eigene Sammlungskategorie."})
    tcg_filter = (request.args.get("tcg") or "").strip() if section == "cards" else ""
    if tcg_filter:
        rows = [row for row in rows if (row.tcg_game or "").casefold() == tcg_filter.casefold()]
    query_text = (request.args.get("q") or "").strip()
    if query_text:
        needle = _search_text(query_text)
        rows = [row for row in rows if any(needle in _search_text(value) for value in (row.title, row.edition, row.media_type, row.barcode))]
    allowed_sorts = {"name_asc", "name_desc", "value_unit_desc", "value_unit_asc", "value_total_desc", "value_total_asc", "newest"}
    sort_key = f"collector_sort_{section}"
    requested_sort = (request.args.get("sort") or "").strip()
    if requested_sort in allowed_sorts:
        session[sort_key] = requested_sort
    sort = requested_sort if requested_sort in allowed_sorts else session.get(sort_key, "newest")
    if sort not in allowed_sorts:
        sort = "newest"
    view_key = f"collector_view_{section}"
    requested_view = (request.args.get("view") or "").strip()
    if requested_view in {"list", "grid"}:
        session[view_key] = requested_view
    view = requested_view if requested_view in {"list", "grid"} else session.get(view_key, "list")
    def _unit_value(row):
        value = collector_effective_value(row)
        return float(value) if value is not None else -1.0
    def _total_value(row):
        return _unit_value(row) * max(row.quantity or 1, 1) if _unit_value(row) >= 0 else -1.0
    if sort == "name_asc": rows.sort(key=lambda row: (row.title or "").casefold())
    elif sort == "name_desc": rows.sort(key=lambda row: (row.title or "").casefold(), reverse=True)
    elif sort == "value_unit_desc": rows.sort(key=lambda row: (_unit_value(row), (row.title or "").casefold()), reverse=True)
    elif sort == "value_unit_asc": rows.sort(key=lambda row: (_unit_value(row) < 0, _unit_value(row), (row.title or "").casefold()))
    elif sort == "value_total_desc": rows.sort(key=lambda row: (_total_value(row), (row.title or "").casefold()), reverse=True)
    elif sort == "value_total_asc": rows.sort(key=lambda row: (_total_value(row) < 0, _total_value(row), (row.title or "").casefold()))
    else: rows.sort(key=lambda row: row.added_at or datetime.min, reverse=True)
    count = sum(max(row.quantity or 1, 1) for row in rows)
    value = collector_rows_total_value(rows, authoritative_pokemon=(section == "cards"))
    active_tcgs = []
    if section == "cards":
        tcg_rows = CollectorItem.query.filter_by(user_id=active_collection_user_id(), category="cards").all()
        counts = {}
        for card in tcg_rows:
            name = (card.tcg_game or "").strip()
            if name:
                counts[name] = counts.get(name, 0) + max(card.quantity or 1, 1)
        active_tcgs = sorted(counts.items(), key=lambda x: x[0].casefold())
    return render_template("collector_section.html", section=section, config=config, rows=rows, item_count=count, section_value=value, tcg_filter=tcg_filter, active_tcgs=active_tcgs, selected_sort=sort, query_text=query_text, view=view,
                           custom_categories=custom_categories, selected_custom_category=selected_custom_category,
                           category_move_token=custom_category_form_token("move-items") if section == "custom" and collection_capability("edit_items") else None)


def collector_effective_value(row):
    if getattr(row, "fixed_value_eur", None) is not None:
        return row.fixed_value_eur
    return row.auto_value_eur if row.auto_value_eur is not None else row.estimated_value_eur


def collector_card_tcg_name(row):
    """Return one stable TCG label, including historical PokéCollector imports."""
    tcg_name = (getattr(row, "tcg_game", None) or "").strip()
    source = (getattr(row, "external_source", None) or "").casefold()
    meta_blob = (getattr(row, "metadata_json", None) or "").casefold()
    probe = tcg_name.casefold()
    if ("pokemon" in probe or "pokémon" in probe
            or "pokecollector" in source or "pokécollector" in source
            or "pokecollector" in meta_blob or "pokécollector" in meta_blob
            or '"tcg": "pokemon"' in meta_blob
            or '"tcg":"pokemon"' in meta_blob):
        return "Pokémon"
    if "magic" in probe or probe == "mtg":
        return "Magic: The Gathering"
    if "yu-gi" in probe or "yugioh" in probe:
        return "Yu-Gi-Oh!"
    return tcg_name or "Sonstige"


def is_pokemon_card(row):
    """Identify Pokémon cards consistently across imports and legacy labels."""
    return bool(row and getattr(row, "category", None) == "cards" and collector_card_tcg_name(row) == "Pokémon")


def repair_pokemon_card_valuation_artifacts():
    """Remove invalid marketplace valuations from Pokémon cards."""
    changed = 0
    rows = CollectorItem.query.filter_by(category="cards").all()
    for row in rows:
        if not is_pokemon_card(row):
            continue
        for activity in list(row.collector_price_activity):
            if "ebay" in str(activity.source or "").casefold():
                db.session.delete(activity)
                changed += 1
        for history in list(row.collector_price_history):
            if "ebay" in str(history.source or "").casefold():
                db.session.delete(history)
                changed += 1
        if row.auto_value_low_eur is not None or row.auto_value_high_eur is not None:
            row.auto_value_low_eur = None
            row.auto_value_high_eur = None
            changed += 1
        if "ebay" in str(row.auto_value_source or "").casefold():
            row.auto_value_eur = None
            row.auto_value_source = None
            row.auto_value_status = "pokecollector_sync_required"
            row.auto_value_updated_at = None
            changed += 1
    if changed:
        db.session.commit()
        app.logger.info("v3.0.6 removed %d invalid Pokémon marketplace valuation artifacts", changed)
    return changed


def pokecollector_portfolio_value():
    """Return PokéCollector's authoritative portfolio total, if one was synced."""
    try:
        return _pc_float(app_setting_get("pokecollector_portfolio_value_eur"))
    except Exception:
        return None


def collector_rows_total_value(rows, authoritative_pokemon=False):
    """Sum Collector rows without counting PokéCollector's portfolio twice.

    Individual Pokémon values remain available for details and sorting. For full
    collection/module totals, PokéCollector's synced portfolio total replaces the
    sum of those individual Pokémon rows.
    """
    rows = list(rows)
    if not authoritative_pokemon:
        return sum((collector_effective_value(row) or 0) * max(row.quantity or 1, 1) for row in rows)
    pokemon_rows = [row for row in rows if row.category == "cards" and collector_card_tcg_name(row) == "Pokémon"]
    pc_total = pokecollector_portfolio_value() if pokemon_rows else None
    if pc_total is None:
        return sum((collector_effective_value(row) or 0) * max(row.quantity or 1, 1) for row in rows)
    other_value = sum(
        (collector_effective_value(row) or 0) * max(row.quantity or 1, 1)
        for row in rows if row not in pokemon_rows
    )
    return float(pc_total) + other_value


def record_collector_price(row, previous_value, value, low, high, source):
    """Persist a successful Collector-module valuation and its activity."""
    if is_pokemon_card(row):
        return
    now = utc_now()
    previous = float(previous_value) if previous_value is not None else None
    current = float(value)
    delta = round(current - previous, 2) if previous is not None else 0.0
    change = "new" if previous is None else ("up" if delta > 0.004 else ("down" if delta < -0.004 else "same"))
    db.session.add(CollectorPriceHistory(collector_item_id=row.id, value_eur=current, low_eur=low, high_eur=high, source=source or "Automatischer Marktwert", recorded_at=now))
    db.session.add(CollectorPriceActivity(collector_item_id=row.id, previous_value_eur=previous, value_eur=current, delta_eur=delta, change_type=change, source=source or "Automatischer Marktwert", recorded_at=now))


def collector_total_value_snapshot(user_id=None):
    """Store one total-value point for games, hardware, accessories and all Collector modules."""
    uid = user_id or active_collection_user_id()
    games = [i for i in CollectionItem.query.filter_by(user_id=uid, status="owned").filter(CollectionItem.ownership_format != "digital").all() if game_is_physical_candidate(i.game)]
    hardware = scoped_hardware_query().filter_by(status="owned").all()
    accessories = scoped_accessory_query().filter_by(status="owned").all()
    generic = CollectorItem.query.filter_by(user_id=uid).all()
    values=[]
    values += [effective_value(i) for i in games]
    values += [effective_hardware_value(i) for i in hardware]
    values += [(effective_accessory_value(i) * max(i.quantity or 1,1)) if effective_accessory_value(i) is not None and accessory_counts_in_total(i) else None for i in accessories]
    pokemon_rows = [i for i in generic if i.category == "cards" and collector_card_tcg_name(i) == "Pokémon"]
    pc_total = pokecollector_portfolio_value() if pokemon_rows else None
    if pc_total is None:
        values += [(collector_effective_value(i) * max(i.quantity or 1,1)) if collector_effective_value(i) is not None else None for i in generic]
    else:
        values += [(collector_effective_value(i) * max(i.quantity or 1,1)) if collector_effective_value(i) is not None else None for i in generic if i not in pokemon_rows]
        values.append(float(pc_total))
    valued=[v for v in values if v is not None]
    owned_count=len(games)+len(hardware)+sum(max(i.quantity or 1,1) for i in accessories if accessory_counts_in_total(i))+sum(max(i.quantity or 1,1) for i in generic)
    snap=CollectorValueSnapshot(collection_user_id=uid, total_value_eur=round(sum(float(v) for v in valued),2), owned_count=owned_count, valued_count=len(valued), recorded_at=utc_now())
    db.session.add(snap)
    return snap


def collector_owned_row(item_id):
    row = CollectorItem.query.filter_by(id=item_id, user_id=active_collection_user_id()).first_or_404()
    if row.category not in COLLECTOR_SECTIONS:
        abort(404)
    return row


def _collector_media_copy_key(row):
    if row.category not in {"movies", "tv"}:
        return None
    meta = collector_metadata(row)
    tmdb_id = str(meta.get("tmdb_id") or (row.external_id if str(row.external_source or "").upper() == "TMDB" else "") or "").strip()
    if tmdb_id:
        return "tmdb", tmdb_id
    return "title", _match_key(row.title or "")


def _collector_media_copies(row):
    key = _collector_media_copy_key(row)
    if not key:
        return [row]
    candidates = CollectorItem.query.filter_by(user_id=row.user_id, category=row.category).order_by(CollectorItem.id).all()
    return [candidate for candidate in candidates if _collector_media_copy_key(candidate) == key]


REVIEW_DIMENSIONS = {
    "games": ("Gameplay", "Handlung", "Grafik & Präsentation", "Sound & Musik", "Wiederspielwert"),
    "movies": ("Handlung", "Figuren & Schauspiel", "Bild & Inszenierung", "Ton & Musik", "Wiederschauwert"),
    "tv": ("Handlung", "Figuren", "Inszenierung", "Ton & Musik", "Langzeitqualität"),
    "books": ("Handlung & Inhalt", "Schreibstil", "Figuren", "Welt & Atmosphäre", "Wiederlesewert"),
    "music": ("Komposition", "Produktion", "Gesang & Text", "Abwechslung", "Wiederhörwert"),
    "cards": ("Artwork", "Design", "Druckqualität", "Spielbarkeit", "Persönlicher Sammelreiz"),
    "custom": ("Inhalt", "Gestaltung", "Qualität", "Unterhaltungswert", "Langzeitwert"),
}


def _personal_review_target(source_kind, source_id):
    owner_id = active_collection_user_id()
    if source_kind == "game":
        game = db.get_or_404(Game, source_id)
        owned = CollectionItem.query.filter_by(user_id=owner_id, game_id=game.id, status="owned").first()
        if not owned:
            abort(404)
        return {"media_kind": "games", "title": game.title, "cover_url": game.cover_url,
                "back_url": url_for("game_detail", game_id=game.id)}
    if source_kind == "collector":
        row = collector_owned_row(source_id)
        return {"media_kind": row.category, "title": row.title, "cover_url": row.cover_url,
                "back_url": url_for("collector_item_detail", item_id=row.id)}
    abort(404)


def _personal_review(source_kind, source_id):
    return PersonalReview.query.filter_by(user_id=current_user.id, source_kind=source_kind, source_id=str(source_id)).first()


@app.route("/review/<source_kind>/<int:source_id>", methods=["GET", "POST"])
@login_required
def personal_review_edit(source_kind, source_id):
    target = _personal_review_target(source_kind, source_id)
    review = _personal_review(source_kind, source_id)
    dimensions = REVIEW_DIMENSIONS.get(target["media_kind"], REVIEW_DIMENSIONS["custom"])
    if request.method == "POST":
        if request.form.get("action") == "delete":
            if review:
                db.session.delete(review); db.session.commit()
                flash("Deine persönliche Bewertung wurde entfernt.", "success")
            return redirect(target["back_url"])
        overall = request.form.get("overall_rating", type=int)
        if overall is None or not 1 <= overall <= 10:
            flash("Bitte gib eine Gesamtbewertung von 1 bis 10 an.", "warning")
            return redirect(url_for("personal_review_edit", source_kind=source_kind, source_id=source_id))
        if not review:
            review = PersonalReview(user_id=current_user.id, source_kind=source_kind, source_id=str(source_id),
                                    media_kind=target["media_kind"], title_snapshot=target["title"], overall_rating=overall)
            db.session.add(review)
        review.media_kind = target["media_kind"]
        review.title_snapshot = target["title"][:255]
        review.overall_rating = overall
        for index in range(1, 6):
            value = request.form.get(f"dimension_{index}", type=int)
            setattr(review, f"dimension_{index}", value if value is not None and 1 <= value <= 10 else None)
        review.review_title = (request.form.get("review_title") or "").strip()[:180] or None
        review.review_text = (request.form.get("review_text") or "").strip()[:12000] or None
        review.pros = (request.form.get("pros") or "").strip()[:4000] or None
        review.cons = (request.form.get("cons") or "").strip()[:4000] or None
        recommendation = (request.form.get("recommendation") or "").strip()
        review.recommendation = recommendation if recommendation in {"yes", "maybe", "no"} else None
        review.favorite = request.form.get("favorite") == "1"
        review.spoiler = request.form.get("spoiler") == "1"
        try:
            review.consumed_at = date.fromisoformat(request.form.get("consumed_at")) if request.form.get("consumed_at") else None
        except ValueError:
            review.consumed_at = None
        db.session.commit()
        flash("Deine persönliche Bewertung wurde gespeichert.", "success")
        return redirect(target["back_url"])
    return render_template("personal_review_edit.html", target=target, review=review, dimensions=dimensions,
                           source_kind=source_kind, source_id=source_id)


@app.route("/collector/item/<int:item_id>")
@login_required
def collector_item_detail(item_id):
    row = collector_owned_row(item_id)
    sync_inferred_release_coverages(row); db.session.commit()
    media_copies = _collector_media_copies(row) if row.category in {"movies", "tv"} else []
    copy_position = next((index for index, copy in enumerate(media_copies, 1) if copy.id == row.id), 1)
    coverages = ReleaseCoverage.query.filter_by(owner_id=row.user_id, source_kind="collector", source_id=str(row.id)).order_by(ReleaseCoverage.target_kind, ReleaseCoverage.sequence_label, ReleaseCoverage.target_title).all()
    return render_template("collector_item_detail.html", row=row, config=COLLECTOR_SECTIONS[row.category],
                           effective_value=collector_effective_value(row), metadata=collector_metadata(row),
                           media_copies=media_copies, copy_position=copy_position, coverages=coverages,
                           personal_review=_personal_review("collector", row.id),
                           review_dimensions=REVIEW_DIMENSIONS.get(row.category, REVIEW_DIMENSIONS["custom"]),
                           review_source_kind="collector", review_source_id=row.id)


@app.route("/collector/item/<int:item_id>/coverage", methods=["GET", "POST"])
@login_required
def collector_item_coverage(item_id):
    row = collector_owned_row(item_id)
    if row.category not in {"movies", "tv", "books"}: abort(400)
    sync_inferred_release_coverages(row)
    if request.method == "POST":
        if row.category == "movies" and request.form.get("action") == "tmdb_add":
            movie_ids = []
            for raw in (request.form.get("tmdb_links") or "").splitlines():
                value = raw.strip()
                match = re.search(r"(?:themoviedb\.org)?/movie/(\d+)", value, flags=re.I)
                if not match:
                    match = re.fullmatch(r"(?:tmdb\s*[:#]\s*)?(\d+)", value, flags=re.I)
                if match and match.group(1) not in movie_ids:
                    movie_ids.append(match.group(1))
            added, unresolved = 0, []
            meta = collector_metadata(row)
            included_ids = {str(value) for value in (meta.get("included_tmdb_ids") or []) if str(value).isdigit()}
            for movie_id in movie_ids[:100]:
                details = tmdb_json(f"movie/{quote(movie_id, safe='')}", {"language": "de-DE"}) or {}
                title = str(details.get("title") or details.get("original_title") or "").strip() if isinstance(details, dict) else ""
                if not title or str(details.get("id") or "") != movie_id:
                    unresolved.append(movie_id)
                    continue
                key = f"movie:tmdb:{movie_id}"
                existing = ReleaseCoverage.query.filter_by(owner_id=row.user_id, source_kind="collector", source_id=str(row.id), target_kind="movies", target_key=key).first()
                if not existing:
                    db.session.add(ReleaseCoverage(owner_id=row.user_id, source_kind="collector", source_id=str(row.id), target_kind="movies",
                                   target_key=key, target_title=title[:255], sequence_label=str(details.get("release_date") or "")[:4] or None, origin="tmdb"))
                    added += 1
                included_ids.add(movie_id)
            if included_ids:
                meta["included_tmdb_ids"] = sorted(included_ids, key=lambda value: int(value))
                row.metadata_json = json.dumps(meta, ensure_ascii=False)
            db.session.commit()
            if added:
                flash(f"{added} Film{'e' if added != 1 else ''} über TMDB hinzugefügt. Der Boxpreis wird weiterhin nur einmal gezählt.", "success")
            elif movie_ids and not unresolved:
                flash("Diese TMDB-Filme sind der Ausgabe bereits zugeordnet.", "success")
            else:
                flash("Kein gültiger TMDB-Film-Link gefunden. Verwende pro Zeile einen /movie/-Link oder eine Film-ID.", "warning")
            if unresolved:
                flash("Nicht bei TMDB auflösbar: " + ", ".join(unresolved), "warning")
            return redirect(url_for("collector_item_coverage", item_id=row.id))
        ReleaseCoverage.query.filter_by(owner_id=row.user_id, source_kind="collector", source_id=str(row.id)).delete(synchronize_session=False)
        seen = set()
        for raw in (request.form.get("coverage_lines") or "").splitlines():
            parts = [part.strip() for part in raw.split("|", 2)]
            if len(parts) != 3: continue
            kind, key, title = parts
            if kind not in {"movies", "tv", "books"} or not key or not title or (kind, key) in seen: continue
            seen.add((kind, key))
            db.session.add(ReleaseCoverage(owner_id=row.user_id, source_kind="collector", source_id=str(row.id), target_kind=kind,
                           target_key=key[:320], target_title=title[:255], origin="manual"))
        if row.category == "movies":
            meta = collector_metadata(row)
            selected_tmdb_ids = sorted({key.rsplit(":", 1)[-1] for kind, key in seen
                                        if kind == "movies" and key.startswith("movie:tmdb:") and key.rsplit(":", 1)[-1].isdigit()},
                                       key=lambda value: int(value))
            if selected_tmdb_ids:
                meta["included_tmdb_ids"] = selected_tmdb_ids
            else:
                meta.pop("included_tmdb_ids", None)
            row.metadata_json = json.dumps(meta, ensure_ascii=False)
        db.session.commit(); flash("Abgedeckte Werke gespeichert. Der Boxpreis wird weiterhin nur einmal gezählt.", "success")
        return redirect(url_for("collector_item_detail", item_id=row.id))
    db.session.commit()
    entries = ReleaseCoverage.query.filter_by(owner_id=row.user_id, source_kind="collector", source_id=str(row.id)).order_by(ReleaseCoverage.target_kind, ReleaseCoverage.sequence_label, ReleaseCoverage.target_title).all()
    coverage_lines = "\n".join(f"{entry.target_kind}|{entry.target_key}|{entry.target_title}" for entry in entries)
    return render_template("collector_item_coverage.html", row=row, entries=entries, coverage_lines=coverage_lines)


@app.route("/collector/item/<int:item_id>/duplicate-copy", methods=["POST"])
@login_required
def collector_item_duplicate_copy(item_id):
    row = collector_owned_row(item_id)
    if row.category not in {"movies", "tv"}:
        abort(400)
    copies = _collector_media_copies(row)
    meta = collector_metadata(row)
    try:
        origin_id = int(meta.get("copy_origin_id") or row.id)
    except (TypeError, ValueError):
        origin_id = row.id
    meta["copy_origin_id"] = origin_id
    row.metadata_json = json.dumps(meta, ensure_ascii=False)
    clone = _clone_collector_item_copy(row, origin_id=origin_id, sequence=len(copies) + 1)
    db.session.add(clone)
    db.session.commit()
    flash(f"Weiteres Exemplar von {row.title} wurde separat angelegt.", "success")
    return redirect(url_for("collector_item_edit", item_id=clone.id))


@app.route("/collector/item/<int:item_id>/new-copy")
@login_required
def collector_item_new_copy(item_id):
    """Reuse catalog metadata, but collect the new physical copy separately."""
    row = collector_owned_row(item_id)
    meta = collector_metadata(row)
    prefill = {
        "category": row.category,
        "title": row.title or "",
        "barcode": row.barcode or "",
        "release_year": row.release_year or "",
        "cover_url": row.cover_url or "",
        "media_type": row.media_type or "",
        "edition": row.edition or "",
        "source": row.external_source or "",
        "source_id": row.external_id or "",
        "country": meta.get("physical_country") or "DE",
        "series_name": meta.get("collection_name") or meta.get("series_name") or "",
        "series_order": meta.get("collection_order") or "",
        "tmdb_id": meta.get("tmdb_id") or (row.external_id if str(row.external_source or "").upper() == "TMDB" else ""),
        "author": meta.get("author") or "",
        "publisher": meta.get("publisher") or "",
        "artist": meta.get("artist") or "",
        "label": meta.get("label") or "",
        "catalog_number": meta.get("catalog_number") or "",
        "ownership_format": meta.get("ownership_format") or "physical",
        "de_physical_release_status": meta.get("de_physical_release_status") or "unknown",
        "release_kind": meta.get("edition_type") or "single",
        "tcg_game": row.tcg_game or "",
        "card_set": row.card_set or "",
        "card_number": row.card_number or "",
        "card_language": row.card_language or "",
        "card_variant": row.card_variant or "",
        "card_rarity": row.card_rarity or "",
        "from_provider": True,
        "from_existing": True,
        "existing_item_id": row.id,
    }
    if row.category in {"movies", "tv"}:
        try:
            prefill["copy_origin_id"] = int(meta.get("copy_origin_id") or row.id)
        except (TypeError, ValueError):
            prefill["copy_origin_id"] = row.id
    entries = (ReleaseCoverage.query
               .filter_by(owner_id=row.user_id, source_kind="collector", source_id=str(row.id))
               .order_by(ReleaseCoverage.sequence_label, ReleaseCoverage.id).all())
    if row.category == "tv":
        seasons = []
        for entry in entries:
            match = re.search(r":season:(\d+)$", entry.target_key or "")
            if match:
                seasons.append(int(match.group(1)))
        if not seasons:
            seasons = _parse_number_selection(meta.get("included_seasons"), maximum=200)
        if seasons:
            prefill["included_seasons"] = ", ".join(str(value) for value in sorted(set(seasons)))
            prefill["season_count"] = meta.get("season_count") or max(seasons)
        elif meta.get("season_count"):
            prefill["season_count"] = meta.get("season_count")
    elif row.category == "movies":
        prefill["included_titles"] = "\n".join(entry.target_title for entry in entries if entry.target_kind == "movies")
    elif row.category == "books":
        prefill["included_books"] = "\n".join(entry.target_title for entry in entries if entry.target_kind == "books")
    session["media_questionnaire_prefill"] = prefill
    return redirect(url_for("collector_media_questionnaire"))


def _repoint_deleted_media_copy_links(row):
    """Prevent stale TV/box links when one independently managed copy is deleted."""
    if row.category not in {"movies", "tv"}:
        return
    siblings = [copy for copy in _collector_media_copies(row) if copy.id != row.id]
    if row.category == "movies":
        replacement = next((copy for copy in siblings if _collector_multi_part_copy(copy)), None)
        prefix = f"movie_box_links:{int(row.user_id)}:"
    else:
        replacement = siblings[0] if siblings else None
        prefix = f"tv_season_links:{int(row.user_id)}:"
    for setting in AppSetting.query.filter(AppSetting.key.like(prefix + "%")).all():
        try:
            links = json.loads(setting.value or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(links, dict):
            continue
        affected = [key for key, item_id in links.items() if str(item_id) == str(row.id)]
        if not affected:
            continue
        for key in affected:
            if replacement:
                links[key] = replacement.id
            else:
                links.pop(key, None)
        setting.value = json.dumps(links, ensure_ascii=False, sort_keys=True)
        if row.category == "movies" and not replacement:
            collection_id = setting.key[len(prefix):]
            status_setting = db.session.get(AppSetting, _movie_collection_status_key(row.user_id, collection_id))
            if status_setting:
                try:
                    statuses = json.loads(status_setting.value or "{}")
                except (TypeError, ValueError):
                    statuses = {}
                if isinstance(statuses, dict):
                    for key in affected:
                        if statuses.get(key) == "covered":
                            statuses.pop(key, None)
                    status_setting.value = json.dumps(statuses, ensure_ascii=False, sort_keys=True)


COLLECTOR_VIDEO_MEDIA_TYPES = ("DVD", "Blu-ray", "Blu-ray 3D", "4K UHD Blu-ray", "HD DVD", "VHS", "Video-CD", "Sonstiges")
COLLECTOR_VIDEO_EDITION_TYPES = ("Standard", "Steelbook", "Mediabook", "Collector's Edition", "Limited Edition", "Komplettbox", "Teilbox", "Sonstiges")
COLLECTOR_VIDEO_CONDITIONS = ("Neu", "Sehr gut", "Gut", "Akzeptabel", "Defekt")
COLLECTOR_VIDEO_COMPLETENESS = ("Sealed", "Komplett / CIB", "OVP vorhanden", "Ohne OVP", "Unvollständig", "Nur Disc")
COLLECTOR_BOOK_CONDITIONS = ("Neu", "Wie neu", "Sehr gut", "Gut", "Akzeptabel", "Mangelhaft")

def collector_video_copy_factor(row):
    """Game-like copy factor for movies/TV; market sample remains separate."""
    if row.category not in {"movies", "tv"}:
        return 1.0
    meta = collector_metadata(row)
    completeness = (row.completeness or "").strip()
    factor = {
        "Sealed": 1.20, "Komplett / CIB": 1.00, "OVP vorhanden": .96,
        "Ohne OVP": .82, "Unvollständig": .72, "Nur Disc": .58,
        # compatibility with older Collector values
        "Komplett": 1.00, "Nur Medium": .58,
    }.get(completeness, 1.0)
    cond = (row.condition or "").strip()
    factor *= {"Neu":1.08, "Sehr gut":1.00, "Gut":.90, "Akzeptabel":.75, "Defekt":.40}.get(cond, 1.0)
    if meta.get("sealed") is True: factor = max(factor, 1.20)
    elif meta.get("has_original_packaging") is False: factor *= .90
    if meta.get("disc_present") is False: factor *= .20
    return max(.10, min(1.35, factor))

@app.route("/collector/item/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def collector_item_edit(item_id):
    row = collector_owned_row(item_id)
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Ein Titel wird benötigt.", "danger")
            return redirect(url_for("collector_item_edit", item_id=row.id))
        row.title = title[:255]
        row.barcode = clean_barcode(request.form.get("barcode")) or None
        requested_media = (request.form.get("media_type") or "").strip()[:120] or None
        if row.category in {"movies", "tv"} and requested_media not in COLLECTOR_VIDEO_MEDIA_TYPES:
            requested_media = row.media_type if row.media_type in COLLECTOR_VIDEO_MEDIA_TYPES else "DVD"
        row.media_type = requested_media
        row.edition = (request.form.get("edition") or "").strip()[:160] or None
        if row.category == "cards":
            row.tcg_game = (request.form.get("tcg_game") or "").strip()[:80] or None
            row.card_set = (request.form.get("card_set") or "").strip()[:160] or None
            row.card_number = (request.form.get("card_number") or "").strip()[:80] or None
            row.card_language = (request.form.get("card_language") or "").strip()[:32] or None
            row.card_variant = (request.form.get("card_variant") or "").strip()[:80] or None
            row.card_rarity = (request.form.get("card_rarity") or "").strip()[:120] or None
            row.card_grade = (request.form.get("card_grade") or "").strip()[:80] or None
        year = (request.form.get("release_year") or "").strip()
        row.release_year = int(year) if year.isdigit() and 1800 <= int(year) <= 2200 else None
        row.condition = (request.form.get("condition") or "").strip()[:40] or None
        # A book is the object itself. Game/media concepts such as OVP, CIB or
        # "Nur Medium" do not describe book completeness and must not be stored.
        row.completeness = None if row.category == "books" else (request.form.get("completeness") or "").strip()[:40] or None
        row.quantity = 1 if row.category in {"movies", "tv"} else max(1, int(request.form.get("quantity") or 1))
        row.purchase_price_eur = parse_money_input(request.form.get("purchase_price_eur"))
        purchase_date_raw = (request.form.get("purchase_date") or "").strip()
        try:
            row.purchase_date = date.fromisoformat(purchase_date_raw) if purchase_date_raw else None
        except ValueError:
            row.purchase_date = None
        row.storage_location = (request.form.get("storage_location") or "").strip()[:160] or None
        row.estimated_value_eur = parse_money_input(request.form.get("estimated_value_eur"))
        row.cover_url = archived_or_original_image(request.form.get("cover_url"))
        row.notes = (request.form.get("notes") or "").strip() or None
        meta = collector_metadata(row)
        if row.category == "custom" and "custom_category" in request.form:
            custom_category = (request.form.get("custom_category") or "").strip()
            if custom_category and _custom_collection_category(row.user_id, custom_category):
                meta["custom_category"] = custom_category
            else:
                meta.pop("custom_category", None)
        if row.category == "books":
            for key, maxlen in (("subtitle",255),("author",255),("publisher",255),("language",40),("publish_date",80),("page_count",12)):
                value = (request.form.get(key) or "").strip()
                if value: meta[key] = value[:maxlen]
                else: meta.pop(key, None)
            meta["isbn"] = row.barcode
        if row.category in {"books", "tv", "movies"}:
            collection_name = (request.form.get("collection_name") or "").strip()
            collection_order = (request.form.get("collection_order") or "").strip()
            if collection_name: meta["collection_name"] = collection_name[:200]
            else: meta.pop("collection_name", None)
            if collection_order: meta["collection_order"] = collection_order[:40]
            else: meta.pop("collection_order", None)
        if row.category == "music":
            meta.update(music_metadata_from_form(request.form))
        elif row.category in {"movies", "tv"}:
            for key, maxlen in (("physical_language",80),("physical_country",80),("region",80),("studio",160),("edition_type",80)):
                value = (request.form.get(key) or "").strip()
                if value: meta[key] = value[:maxlen]
                elif key in meta: meta.pop(key, None)
            for key in ("has_original_packaging", "disc_present", "booklet_present", "slipcover_present", "bonus_disc_present", "sealed"):
                meta[key] = request.form.get(key) == "1"
            disc_count = (request.form.get("physical_disc_count") or "").strip()
            meta["physical_disc_count"] = int(disc_count) if disc_count.isdigit() and int(disc_count) >= 0 else None
            if row.category == "tv":
                season = (request.form.get("season_number") or "").strip()
                episodes = (request.form.get("physical_episode_count") or "").strip()
                meta["season_number"] = int(season) if season.isdigit() else None
                meta["physical_episode_count"] = int(episodes) if episodes.isdigit() else None
        row.metadata_json = json.dumps(meta, ensure_ascii=False)
        db.session.commit()
        flash(f"{row.title} wurde gespeichert.", "success")
        return redirect(url_for("collector_item_detail", item_id=row.id))
    if row.category == "books":
        return render_template("collector_book_edit.html", row=row, config=COLLECTOR_SECTIONS[row.category], metadata=collector_metadata(row), book_conditions=COLLECTOR_BOOK_CONDITIONS)
    return render_template("collector_item_edit.html", row=row, config=COLLECTOR_SECTIONS[row.category], metadata=collector_metadata(row),
                           video_media_types=COLLECTOR_VIDEO_MEDIA_TYPES, video_edition_types=COLLECTOR_VIDEO_EDITION_TYPES,
                           video_conditions=COLLECTOR_VIDEO_CONDITIONS, video_completeness=COLLECTOR_VIDEO_COMPLETENESS,
                           book_conditions=COLLECTOR_BOOK_CONDITIONS,
                           custom_categories=custom_collection_categories(row.user_id) if row.category == "custom" else [])


@app.route("/collector/item/<int:item_id>/delete", methods=["POST"])
@login_required
def collector_item_delete(item_id):
    row = collector_owned_row(item_id)
    section, title = row.category, row.title
    _repoint_deleted_media_copy_links(row)
    ReleaseCoverage.query.filter_by(owner_id=row.user_id, source_kind="collector", source_id=str(row.id)).delete(synchronize_session=False)
    db.session.delete(row); db.session.commit()
    flash(f"Das ausgewählte Exemplar von {title} wurde gelöscht.", "success")
    return redirect(url_for("collector_section", section=section))


def collector_ebay_valuation(row):
    if is_pokemon_card(row):
        return None, None, None, "pokecollector_only"
    if row.category not in {"movies", "tv", "books", "music", "cards", "custom"}:
        return None, None, None, "unsupported"
    queries = []
    if row.barcode:
        queries.append(row.barcode)
    descriptive = " ".join(x for x in (row.title, row.media_type, row.edition) if x)
    if descriptive and descriptive not in queries:
        queries.append(descriptive)
    found, last_status = [], "ebay_no_results"
    for query in queries:
        rows, last_status = ebay_search_items(query, limit=50)
        found.extend(rows)
        if len(found) >= 8: break
    if not found:
        return None, None, None, last_status
    wanted = {_match_key(x) for x in (row.title, row.media_type) if x}
    unwanted = ("player", "recorder", "leerhülle", "empty case", "case only", "download", "digital", "lot", "konvolut", "sammlung")
    values=[]
    for hit in found:
        if hit.get("currency") != "EUR" or hit.get("price") is None: continue
        key=_match_key(hit.get("name"))
        if any(x in key for x in unwanted): continue
        # Barcode queries are already precise; text queries require title overlap.
        if not row.barcode and wanted and not any(w and w in key for w in wanted): continue
        total=float(hit["price"])+float(hit.get("shipping") or 0)
        if .25 <= total <= 5000: values.append(total)
    if len(values) < 2:
        return None, None, None, "ebay_too_few_results"
    center=statistics.median(values)
    values=[v for v in values if center*.35 <= v <= center*2.5]
    if len(values) < 2:
        return None, None, None, "ebay_too_few_results"
    factor = collector_video_copy_factor(row)
    return round(statistics.median(values)*factor,2), round(min(values)*factor,2), round(max(values)*factor,2), "ok"


def _scryfall_price_from_card(data, foil=False):
    """Extract a usable EUR price from one Scryfall card object."""
    if not isinstance(data, dict):
        return None, None
    prices = data.get("prices") or {}
    eur = _tcg_float(prices.get("eur_foil") if foil else prices.get("eur"))
    source = "Scryfall EUR Foil" if foil else "Scryfall EUR"
    if eur is None:
        usd = _tcg_float(prices.get("usd_foil") if foil else prices.get("usd"))
        rate = _usd_to_eur_rate() if usd is not None else None
        if usd is not None and rate is not None:
            eur = round(usd * rate, 2)
            source = "Scryfall USD Foil → EUR" if foil else "Scryfall USD → EUR"
    return (round(float(eur), 2), source) if eur is not None else (None, None)


def collector_scryfall_valuation(row):
    """Value a Magic printing, using an English same-print reference when localized prices are empty."""
    if row.category != "cards" or (row.tcg_game or "").strip().casefold() != "magic: the gathering":
        return None, None, None, None
    meta = collector_metadata(row)
    scryfall_id = str(meta.get("scryfall_id") or (row.external_id if (row.external_source or "").casefold() == "scryfall" else "") or "").strip()
    if not scryfall_id:
        return None, None, None, "scryfall_id_missing"
    data = _tcg_json_url("https://api.scryfall.com/cards/" + quote(scryfall_id, safe=""))
    if not isinstance(data, dict):
        return None, None, None, "scryfall_unavailable"
    variant = (row.card_variant or meta.get("finish") or "normal").casefold()
    foil = "foil" in variant
    eur, source = _scryfall_price_from_card(data, foil)
    reference = None

    # Localized Scryfall printings often have no market fields.  The English
    # printing with the same set + collector number is the closest market proxy.
    if eur is None:
        set_code = str(meta.get("set_code") or data.get("set") or "").strip().lower()
        number = str(row.card_number or data.get("collector_number") or "").strip()
        if set_code and number:
            ref = _tcg_json_url("https://api.scryfall.com/cards/%s/%s/en" % (quote(set_code, safe=""), quote(number, safe="")))
            if isinstance(ref, dict) and ref.get("object") == "card":
                eur, source = _scryfall_price_from_card(ref, foil)
                if eur is not None:
                    reference = ref
                    source += " · EN-Referenz"

    # Last Scryfall-native fallback: same Oracle card in the same set.  This
    # covers unusual localized records where the collector-number endpoint differs.
    if eur is None:
        oracle_id = str(meta.get("oracle_id") or data.get("oracle_id") or "").strip()
        set_code = str(meta.get("set_code") or data.get("set") or "").strip().lower()
        if oracle_id and set_code:
            search = _tcg_json_url("https://api.scryfall.com/cards/search", {"q": f"oracleid:{oracle_id} set:{set_code}", "unique": "prints", "include_multilingual": "true"})
            candidates = (search or {}).get("data") if isinstance(search, dict) else []
            candidates = sorted((c for c in (candidates or []) if isinstance(c, dict)), key=lambda c: 0 if c.get("lang") == "en" else 1)
            for ref in candidates:
                eur, source = _scryfall_price_from_card(ref, foil)
                if eur is not None:
                    reference = ref
                    source += " · Set-Referenz"
                    break

    meta["prices"] = data.get("prices") or {}
    meta["price_checked_at"] = utc_now().isoformat()
    if reference:
        meta["price_reference_scryfall_id"] = reference.get("id")
        meta["price_reference_language"] = reference.get("lang")
        meta["price_reference_prices"] = reference.get("prices") or {}
    row.metadata_json = json.dumps(meta, ensure_ascii=False)
    if eur is None:
        return None, None, None, "scryfall_no_price"
    return eur, eur, eur, source


@app.route("/collector/item/<int:item_id>/value", methods=["POST"])
@login_required
def collector_item_value(item_id):
    row=collector_owned_row(item_id)
    if is_pokemon_card(row):
        flash("Pokémon-Marktwerte werden ausschließlich aus PokéCollector übernommen. Bitte PokéCollector synchronisieren.", "info")
        return redirect_back("collector_item_detail", item_id=row.id)
    # Trading cards have provider-native market data.  For Magic, Scryfall is
    # authoritative for the concrete printing and variant; eBay is fallback only.
    if row.category == "cards" and (row.tcg_game or "").strip().casefold() == "magic: the gathering":
        value, low, high, source = collector_scryfall_valuation(row)
        if value is not None:
            row.auto_value_eur=value; row.auto_value_low_eur=low; row.auto_value_high_eur=high
            row.auto_value_source=source; row.auto_value_status="ok"; row.auto_value_updated_at=utc_now()
            record_collector_price(row, None if not row.collector_price_activity else row.collector_price_activity[-1].value_eur, value, low, high, source)
            db.session.commit()
            flash(f"Scryfall-Marktwert: {format_eur(value)} ({source})", "success")
            return redirect_back("collector_item_detail", item_id=row.id)
        # Only if Scryfall has no usable price do we try the generic marketplace path.
    value, low, high, status=collector_ebay_valuation(row)
    row.auto_value_status=status
    row.auto_value_updated_at=utc_now()
    if value is not None:
        previous = row.auto_value_eur
        row.auto_value_eur=value; row.auto_value_low_eur=low; row.auto_value_high_eur=high; row.auto_value_source="eBay-Angebote"
        record_collector_price(row, previous, value, low, high, "eBay-Angebote")
        flash(f"Automatischer Marktwert: {format_eur(value)}", "success")
    else:
        flash(VALUATION_STATUS_MESSAGES.get(status, "Für diesen Eintrag konnte noch kein belastbarer Marktwert ermittelt werden."), "warning")
    db.session.commit()
    return redirect_back("collector_item_detail", item_id=row.id)



VALUATION_JOB_DIR=Path("/tmp/collector-valuation-jobs")
VALUATION_JOB_DIR.mkdir(parents=True, exist_ok=True)

def _valuation_job_path(job_id): return VALUATION_JOB_DIR/(re.sub(r"[^A-Za-z0-9_-]","",job_id)+".json")
def _valuation_job_write(job_id,data):
    path=_valuation_job_path(job_id); tmp=path.with_suffix(".tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8"); tmp.replace(path)

def _valuation_worker(job_id,user_id,section,tcg):
    with app.app_context():
        rows=CollectorItem.query.filter_by(user_id=user_id,category=section).order_by(CollectorItem.id).all()
        if section=="cards" and tcg: rows=[r for r in rows if (r.tcg_game or "").casefold()==tcg.casefold()]
        st={"id":job_id,"status":"running","section":section,"total":len(rows),"checked":0,"updated":0,"unchanged":0,"missing":0,"failed":0,"current":"Start","message":"Bewertung läuft"}; _valuation_job_write(job_id,st)
        for row in rows:
            st["current"]=row.title; _valuation_job_write(job_id,st)
            if is_pokemon_card(row): st["checked"]+=1; st["unchanged"]+=1; _valuation_job_write(job_id,st); continue
            old=row.auto_value_eur
            try:
                value=low=high=None; source=None; status=None
                if row.category=="cards" and (row.tcg_game or "").strip().casefold()=="magic: the gathering":
                    value,low,high,source=collector_scryfall_valuation(row); status="ok" if value is not None else None
                if value is None: value,low,high,status=collector_ebay_valuation(row); source="eBay-Angebote" if value is not None else None
                row.auto_value_status=status or "no_price"; row.auto_value_updated_at=utc_now()
                if value is not None:
                    row.auto_value_eur=value; row.auto_value_low_eur=low; row.auto_value_high_eur=high; row.auto_value_source=source; record_collector_price(row,old,value,low,high,source)
                    st["updated" if old is None or abs(float(old)-float(value))>0.004 else "unchanged"]+=1
                else: st["missing"]+=1
                db.session.commit()
            except Exception as exc: db.session.rollback(); st["failed"]+=1; current_app.logger.exception("Collector background valuation failed for item %s: %s",row.id,exc)
            st["checked"]+=1; _valuation_job_write(job_id,st)
        st.update(status="done",current="Fertig",message="Bewertung abgeschlossen"); _valuation_job_write(job_id,st); db.session.remove()

@app.route("/collector/<section>/revalue",methods=["POST"])
@login_required
def collector_section_revalue(section):
    if section not in COLLECTOR_SECTIONS: abort(404)
    tcg=(request.form.get("tcg") or "").strip(); job_id=secrets.token_urlsafe(18)
    _valuation_job_write(job_id,{"id":job_id,"status":"queued","section":section,"total":0,"checked":0,"updated":0,"unchanged":0,"missing":0,"failed":0,"current":"Warteschlange","message":"Bewertung wird gestartet"})
    threading.Thread(target=_valuation_worker,args=(job_id,active_collection_user_id(),section,tcg),daemon=True).start()
    return redirect(url_for("collector_valuation_job",job_id=job_id))

@app.route("/collector/valuation/<job_id>")
@login_required
def collector_valuation_job(job_id):
    if not _valuation_job_path(job_id).exists(): abort(404)
    return render_template("collector_valuation_job.html",job_id=job_id)

@app.route("/collector/valuation/<job_id>/status")
@login_required
def collector_valuation_job_status(job_id):
    path=_valuation_job_path(job_id)
    if not path.exists(): return jsonify({"status":"missing"}),404
    try: return jsonify(json.loads(path.read_text(encoding="utf-8")))
    except Exception: return jsonify({"status":"error","message":"Status konnte nicht gelesen werden."}),500


def _collector_media_ean_terms(code):
    """Resolve a physical video EAN through barcode providers and eBay GTIN.

    v2.10.7 deliberately uses Browse's dedicated ``gtin`` parameter first.
    Searching the numeric EAN as a keyword misses many DVD/Blu-ray products.
    """
    products = list(lookup_barcode_external(code) or [])

    ebay_rows, ebay_status = ebay_search_gtin(code, limit=20)
    # Keep the old keyword query only as a secondary compatibility fallback.
    if not ebay_rows:
        keyword_rows, keyword_status = ebay_search_items(code, limit=12)
        if keyword_rows:
            ebay_rows, ebay_status = keyword_rows, keyword_status
        elif ebay_status == "ok":
            ebay_status = keyword_status
    for row in ebay_rows if ebay_status == "ok" else []:
        products.append({
            "name": row.get("name") or "", "cover_url": row.get("cover_url") or "",
            "source": row.get("source") or "eBay GTIN",
            "source_id": row.get("source_id") or row.get("id") or "",
            "category": "DVD / Blu-ray", "barcode": code,
        })

    # Regression references are intentionally tiny and only cover EANs that were
    # reported by users and independently verified.  They are a final fallback,
    # never preferred over live provider data.
    verified_media = {
        "4010232072504": {
            "name": "Family Guy - Season 16 [3 DVDs]", "cover_url": "",
            "source": "Collector-Verifizierung", "source_id": "4010232072504",
            "category": "TV-Serie DVD", "barcode": "4010232072504",
        },
    }
    if not products and code in verified_media:
        products.append(verified_media[code])
        ebay_status = "verified_fallback"

    seen, out = set(), []
    for product in products:
        raw = clean_collector_provider_title(product.get("name") or "")
        if not raw:
            continue
        key = raw.casefold()
        if key in seen:
            continue
        seen.add(key)
        season_match = re.search(r"(?i)\b(?:staffel|season)\s*(?:sixteen|16)\b", raw)
        generic_season = re.search(r"(?i)\b(?:staffel|season)\s*(\d{1,3})\b", raw)
        season_number = int(generic_season.group(1)) if generic_season else (16 if season_match else None)
        is_tv = bool(season_number is not None or re.search(r"(?i)\b(series\s+\d+|complete\s+series|komplettbox)\b", raw))
        tmdb_term = raw
        if is_tv:
            tmdb_term = re.split(r"(?i)\s*[-–:]?\s*\b(?:staffel|season)\b", tmdb_term, maxsplit=1)[0].strip()
        tmdb_term = re.sub(r"(?i)\s*\[[^\]]*(?:dvd|blu.?ray|disc)[^\]]*\]\s*$", "", tmdb_term).strip()
        product = dict(product)
        if season_number:
            product["season_number"] = season_number
            product["edition"] = f"Staffel {season_number}"
        out.append((tmdb_term or raw, product, "tv" if is_tv else None))
    return out, ebay_status


def collector_media_ean_results(code, limit=12):
    terms, ebay_status = _collector_media_ean_terms(code)
    results, seen = [], set()
    # Strong TV hints search TV first; otherwise allow both media types.
    for term, product, hint in terms[:10]:
        kinds = [hint] if hint else ["movie", "tv"]
        for kind in kinds:
            endpoint = "search/tv" if kind == "tv" else "search/movie"
            data = tmdb_json(endpoint, {"query": term, "language": "de-DE", "include_adult": "false"})
            for hit in ((data or {}).get("results") or [])[:5] if isinstance(data, dict) else []:
                hid = str(hit.get("id") or "")
                key = (kind, hid)
                if not hid or key in seen: continue
                seen.add(key)
                date_value = hit.get("first_air_date") if kind == "tv" else hit.get("release_date")
                results.append({
                    "section": "tv" if kind == "tv" else "movies", "id": hid,
                    "title": hit.get("name") if kind == "tv" else hit.get("title"),
                    "original_title": hit.get("original_name") if kind == "tv" else hit.get("original_title"),
                    "year": int(str(date_value or "")[:4]) if str(date_value or "")[:4].isdigit() else None,
                    "overview": hit.get("overview"), "cover_url": tmdb_poster_url(hit.get("poster_path")),
                    "barcode": code, "provider_title": product.get("name") or "", "source": product.get("source") or "Barcode",
                    "media_type": "DVD" if "dvd" in str(product.get("name") or product.get("category") or "").casefold() else "Blu-ray" if "blu" in str(product.get("name") or product.get("category") or "").casefold() else ("DVD" if kind == "tv" else "Blu-ray"),
                    "edition": product.get("edition") or "", "season_number": product.get("season_number"),
                })
                if len(results) >= limit: return results, terms, ebay_status
            if hint and results: break
    return results, terms, ebay_status

def tmdb_credentials():
    """TMDB can be configured through AppSetting or .env without hard-coding secrets."""
    return {
        "api_key": app_setting_get("tmdb_api_key", os.environ.get("TMDB_API_KEY", "")).strip(),
        "token": app_setting_get("tmdb_read_token", os.environ.get("TMDB_READ_ACCESS_TOKEN", os.environ.get("TMDB_READ_TOKEN", ""))).strip(),
    }


def tmdb_json(path, params=None):
    credentials = tmdb_credentials()
    params = dict(params or {})
    headers = {"User-Agent": f"Collector/{APP_VERSION}", "Accept": "application/json"}
    if credentials["token"]:
        headers["Authorization"] = "Bearer " + credentials["token"]
    elif credentials["api_key"]:
        params["api_key"] = credentials["api_key"]
    else:
        return None
    url = "https://api.themoviedb.org/3/" + path.lstrip("/")
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        current_app.logger.exception("TMDB request failed: %s", path)
        return None


def tmdb_connection_test():
    credentials = tmdb_credentials()
    if not credentials["token"] and not credentials["api_key"]:
        return False, "Bitte API-Schlüssel oder Read Access Token eintragen."
    data = tmdb_json("configuration")
    if isinstance(data, dict) and data.get("images"):
        return True, "TMDB-Verbindung erfolgreich."
    return False, "TMDB-Verbindung fehlgeschlagen. Bitte Zugangsdaten prüfen."


def tmdb_poster_url(path, size="w500"):
    path = str(path or "").strip()
    if not path:
        return None
    if not path.startswith("/"):
        path = "/" + path
    return f"https://image.tmdb.org/t/p/{size}{path}"


def collector_metadata(row):
    try:
        data = json.loads(row.metadata_json or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def tmdb_apply_metadata(row):
    """Enrich a movie/TV Collector item while preserving physical-copy fields."""
    if row.category not in {"movies", "tv"}:
        return False, "TMDB-Metadaten sind nur für Filme und Serien verfügbar."
    meta = collector_metadata(row)
    tmdb_id = str(meta.get("tmdb_id") or "").strip()
    media = "movie" if row.category == "movies" else "tv"
    if not tmdb_id:
        endpoint = "search/movie" if media == "movie" else "search/tv"
        data = tmdb_json(endpoint, {"query": row.title, "language": "de-DE", "include_adult": "false"})
        hits = (data or {}).get("results") or [] if isinstance(data, dict) else []
        if not hits:
            return False, "Bei TMDB wurde kein passender Titel gefunden. Bitte zuerst über ‚Cover suchen‘ einen TMDB-Treffer auswählen."
        # Prefer the same release year when known; otherwise TMDB relevance order.
        if row.release_year:
            dated = []
            for hit in hits:
                date = hit.get("release_date") or hit.get("first_air_date") or ""
                if str(date).startswith(str(row.release_year)):
                    dated.append(hit)
            hit = (dated or hits)[0]
        else:
            hit = hits[0]
        tmdb_id = str(hit.get("id") or "")
        if not tmdb_id:
            return False, "TMDB-Treffer enthält keine gültige ID."

    details = tmdb_json(f"{media}/{tmdb_id}", {"language": "de-DE", "append_to_response": "credits"})
    if not isinstance(details, dict) or not details.get("id"):
        return False, "TMDB-Metadaten konnten nicht geladen werden."

    credits = details.get("credits") or {}
    crew = credits.get("crew") or [] if isinstance(credits, dict) else []
    directors = [x.get("name") for x in crew if x.get("job") == "Director" and x.get("name")]
    creators = [x.get("name") for x in (details.get("created_by") or []) if x.get("name")]
    genres = [x.get("name") for x in (details.get("genres") or []) if x.get("name")]
    date = details.get("release_date") or details.get("first_air_date") or ""
    runtime = details.get("runtime")
    if runtime is None:
        runtimes = details.get("episode_run_time") or []
        runtime = runtimes[0] if runtimes else None

    meta.update({
        "tmdb_id": str(details.get("id")),
        "tmdb_media_type": media,
        "original_title": details.get("original_title") or details.get("original_name"),
        "overview": details.get("overview"),
        "genres": genres,
        "runtime_minutes": runtime,
        "director": ", ".join(directors) if directors else None,
        "creators": creators,
        "original_language": details.get("original_language"),
        "season_count": details.get("number_of_seasons") if media == "tv" else None,
        "episode_count": details.get("number_of_episodes") if media == "tv" else None,
        "status": details.get("status"),
        "networks": [x.get("name") for x in (details.get("networks") or []) if x.get("name")] if media == "tv" else [],
        "tmdb_updated_at": utc_now().isoformat(),
        "tmdb_collection": details.get("belongs_to_collection") if media == "movie" else None,
    })
    row.metadata_json = json.dumps(meta, ensure_ascii=False)
    if date and str(date)[:4].isdigit():
        row.release_year = int(str(date)[:4])
    poster = tmdb_poster_url(details.get("poster_path"))
    if poster:
        row.cover_url = archived_or_original_image(poster)
    row.external_source = "TMDB"
    row.external_id = str(details.get("id"))
    return True, "TMDB-Metadaten wurden aktualisiert."


@app.route("/collector/item/<int:item_id>/metadata/tmdb", methods=["POST"])
@login_required
def collector_item_tmdb_metadata(item_id):
    row = collector_owned_row(item_id)
    ok, message = tmdb_apply_metadata(row)
    if ok:
        db.session.commit()
        flash(message, "success")
    else:
        db.session.rollback()
        flash(message, "warning")
    return redirect(url_for("collector_item_detail", item_id=row.id))


def collector_cover_candidates(row):
    results = []
    seen = set()
    def add(url, title, source, external_id=None, subtitle=None):
        url = str(url or "").strip()
        if not url or url in seen:
            return
        seen.add(url)
        results.append({"url": url, "title": title, "source": source, "external_id": external_id, "subtitle": subtitle})

    # Existing product/EAN providers can sometimes provide the exact physical-release artwork.
    if row.barcode:
        for hit in lookup_barcode_external(row.barcode) or []:
            add(hit.get("cover_url"), hit.get("name") or row.title, hit.get("source") or "EAN", hit.get("source_id"), hit.get("category"))

    if row.category in {"movies", "tv"}:
        endpoint = "search/movie" if row.category == "movies" else "search/tv"
        data = tmdb_json(endpoint, {"query": row.title, "language": "de-DE", "include_adult": "false"})
        if isinstance(data, dict):
            for hit in (data.get("results") or [])[:12]:
                title = hit.get("title") or hit.get("name") or row.title
                date = hit.get("release_date") or hit.get("first_air_date") or ""
                add(tmdb_poster_url(hit.get("poster_path")), title, "TMDB", str(hit.get("id") or ""), date[:4] or None)
    return results


@app.route("/collector/item/<int:item_id>/cover", methods=["GET", "POST"])
@login_required
def collector_item_cover(item_id):
    row = collector_owned_row(item_id)
    if request.method == "POST":
        url = (request.form.get("cover_url") or "").strip()
        if not url.startswith(("https://", "http://")):
            flash("Bitte ein gültiges Cover auswählen.", "danger")
            return redirect(url_for("collector_item_cover", item_id=row.id))
        row.cover_url = archived_or_original_image(url)
        source = (request.form.get("source") or "").strip()
        source_id = (request.form.get("source_id") or "").strip()
        if source == "TMDB" and source_id:
            meta = {}
            try:
                meta = json.loads(row.metadata_json or "{}")
            except (TypeError, ValueError):
                meta = {}
            meta["tmdb_id"] = source_id
            row.metadata_json = json.dumps(meta, ensure_ascii=False)
        db.session.commit()
        flash("Cover wurde übernommen.", "success")
        return redirect(url_for("collector_item_detail", item_id=row.id))
    candidates = collector_cover_candidates(row)
    tmdb_configured = bool(tmdb_credentials()["api_key"] or tmdb_credentials()["token"])
    return render_template("collector_item_cover.html", row=row, config=COLLECTOR_SECTIONS[row.category], candidates=candidates, tmdb_configured=tmdb_configured)


@app.route("/collector/item/<int:item_id>/cover/refresh", methods=["POST"])
@login_required
def collector_item_cover_refresh(item_id):
    row = collector_owned_row(item_id)
    if row.category == "cards" and row.external_source == "TCGdex" and row.external_id:
        data = tcgdex_json("cards/" + quote(row.external_id, safe=""))
        image = data.get("image") if isinstance(data, dict) else None
        if image:
            image = str(image).rstrip("/")
            if not image.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                image += "/high.webp"
            row.cover_url = archived_or_original_image(image)
            db.session.commit()
            flash("Kartenbild wurde von TCGdex aktualisiert.", "success")
            return redirect(url_for("collector_item_detail", item_id=row.id))
        flash("TCGdex hat für diese Karte kein Bild geliefert.", "warning")
        return redirect(url_for("collector_item_detail", item_id=row.id))
    return redirect(url_for("collector_item_cover", item_id=row.id))



def pokecollector_credentials():
    return {
        "base_url": (app_setting_get("pokecollector_base_url", "http://pokemon-backend:8000") or "http://pokemon-backend:8000").strip().rstrip("/"),
        "username": app_setting_get("pokecollector_username", "").strip(),
        "password": app_setting_get("pokecollector_password", "").strip(),
    }


def pokecollector_request(path, method="GET", payload=None, token=None, timeout=15, form=False):
    cfg = pokecollector_credentials()
    url = cfg["base_url"] + "/" + path.lstrip("/")
    headers = {"Accept":"application/json", "User-Agent":f"Collector/{APP_VERSION}"}
    data = None
    if payload is not None:
        if form:
            data = urlencode(payload).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=timeout) as response:
        raw=response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def pokecollector_session():
    cfg=pokecollector_credentials()
    try:
        mode=pokecollector_request("api/auth/mode")
    except Exception as exc:
        return None, None, f"PokéCollector ist unter {cfg['base_url']} nicht erreichbar: {exc}"
    multi=bool((mode or {}).get("multi_user")) if isinstance(mode,dict) else False
    if not multi:
        return None, mode, None
    if not cfg["username"] or not cfg["password"]:
        return None, mode, "PokéCollector läuft im Multi-User-Modus. Benutzername und Passwort fehlen."
    try:
        login=pokecollector_request("api/auth/login", "POST", {
            "grant_type":"password", "username":cfg["username"], "password":cfg["password"], "scope":""
        }, form=True)
        token=(login or {}).get("access_token") or (login or {}).get("token") or (login or {}).get("jwt")
        if not token:
            return None, mode, "PokéCollector-Anmeldung lieferte kein Zugriffstoken."
        return str(token), mode, None
    except HTTPError as exc:
        detail = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
            value = parsed.get("detail") if isinstance(parsed, dict) else None
            if isinstance(value, str): detail = value
            elif value: detail = json.dumps(value, ensure_ascii=False)
        except Exception:
            detail = ""
        if exc.code in (401, 403):
            return None, mode, "PokéCollector-Anmeldung abgelehnt. Bitte Benutzername und Passwort prüfen."
        suffix = f" · {detail[:300]}" if detail else ""
        return None, mode, f"PokéCollector-Anmeldung fehlgeschlagen (HTTP {exc.code}){suffix}."
    except Exception as exc:
        return None, mode, f"PokéCollector-Anmeldung fehlgeschlagen: {exc}"


def pokecollector_connection_test():
    token, mode, error=pokecollector_session()
    if error: return False, error
    try:
        data=pokecollector_request("api/collection/", token=token)
        rows=data if isinstance(data,list) else ((data or {}).get("items") or (data or {}).get("collection") or [])
        return True, f"PokéCollector verbunden · {'Multi-User' if (mode or {}).get('multi_user') else 'Single-User'} · {len(rows)} Sammlungspositionen gefunden."
    except Exception as exc:
        return False, f"Verbindung steht, Sammlung konnte aber nicht gelesen werden: {exc}"


def _pc_pick(obj, *names):
    if not isinstance(obj,dict): return None
    for name in names:
        value=obj.get(name)
        if value not in (None, "", []): return value
    return None


def _pc_float(value):
    try: return float(value) if value not in (None,"") else None
    except (TypeError,ValueError): return None


def _pc_card_image(card, card_id):
    image=_pc_pick(card,"image","image_url","imageUrl","image_high","image_large")
    if isinstance(image,dict): image=_pc_pick(image,"high","large","url")
    if image: return str(image)
    tcg=str(_pc_pick(card,"tcg_card_id","tcgdex_id") or card_id or "").rsplit("_",1)[0]
    return f"https://assets.tcgdex.net/en/{tcg}/high.webp" if tcg else None


def _pc_card_details(card_id, token):
    """Load the canonical PokéCollector card record, which contains current prices."""
    if not card_id:
        return {}
    try:
        data = pokecollector_request("api/cards/" + quote(str(card_id), safe=""), token=token, timeout=20)
        return data if isinstance(data, dict) else {}
    except HTTPError as exc:
        app.logger.warning("PokéCollector card detail %s returned HTTP %s", card_id, exc.code)
    except Exception as exc:
        app.logger.warning("PokéCollector card detail %s failed: %s", card_id, exc)
    return {}


def _pc_collection_row_price(src):
    """Prefer the value PokéCollector itself exposes for the owned collection row.

    This keeps Collector aligned with PokéCollector's portfolio instead of
    independently choosing another market column from the card detail record.
    """
    if not isinstance(src, dict):
        return None, None
    for key in ("current_value_eur", "market_value_eur", "value_eur", "current_value",
                "market_value", "card_value", "price_eur", "price"):
        value = _pc_float(src.get(key))
        if value is not None and value >= 0:
            return value, key
    return None, None


def _pc_portfolio_total(data):
    """Read an authoritative portfolio total when the PokéCollector API returns one."""
    if not isinstance(data, dict):
        return None
    candidates=[data]
    for key in ("summary","stats","portfolio","totals"):
        if isinstance(data.get(key), dict): candidates.append(data[key])
    for obj in candidates:
        for key in ("portfolio_value_eur","portfolio_value","total_value_eur","total_value","collection_value_eur","collection_value","value_eur","value"):
            value=_pc_float(obj.get(key))
            if value is not None and value >= 0: return value
    return None


def _pc_primary_price_name(value, default=None):
    """Normalize PokéCollector UI/API price names to dashboard query values."""
    selected = str(value or "").strip().casefold().replace("price_", "")
    selected = selected.replace("-", "").replace("_", "")
    aliases = {"average": "avg", "market": "avg"}
    selected = aliases.get(selected, selected)
    return selected if selected in {"trend", "avg", "avg1", "avg7", "avg30", "low"} else default


def _pc_settings_primary_price(data):
    """Read the per-user primary price from compatible PokéCollector settings."""
    if not isinstance(data, dict):
        return None
    preferred = (
        "primary_price", "primary_price_field", "price_field",
        "price_type", "price_source", "card_price_field",
    )
    for key in preferred:
        selected = _pc_primary_price_name(data.get(key))
        if selected:
            return selected
    for key, value in data.items():
        if "price" in str(key).casefold():
            selected = _pc_primary_price_name(value)
            if selected:
                return selected
    for value in data.values():
        selected = _pc_settings_primary_price(value)
        if selected:
            return selected
    return None


def _pc_variant_price(card, variant, primary_price="avg7"):
    """Apply PokéCollector's selected Cardmarket price field and fallbacks."""
    v = str(variant or "Normal").casefold()
    selected = _pc_primary_price_name(primary_price, "avg7")
    base_by_setting = {
        "trend": "price_trend",
        "avg": "price_market",
        "average": "price_market",
        "market": "price_market",
        "avg1": "price_avg1",
        "avg7": "price_avg7",
        "avg30": "price_avg30",
        "low": "price_low",
    }
    base = base_by_setting.get(selected, "price_avg7")
    candidates = []
    # PokéCollector treats Holo and Reverse Holo alike: selected holo field,
    # then selected non-holo field, then Cardmarket's average fallback.
    if "holo" in v:
        candidates.extend((base + "_holo", base, "price_market"))
    else:
        candidates.extend((base, "price_market"))
    candidates = tuple(dict.fromkeys(candidates))
    for key in candidates:
        value = _pc_float(card.get(key)) if isinstance(card, dict) else None
        if value is not None and value > 0:
            return value, key
    # Fallback to TCGPlayer market fields when Cardmarket has no usable value.
    if "reverse" in v:
        keys=("price_tcg_reverse_market","price_tcg_reverse_mid","price_tcg_reverse_low")
    elif "holo" in v:
        keys=("price_tcg_holo_market","price_tcg_holo_mid","price_tcg_holo_low")
    else:
        keys=("price_tcg_normal_market","price_tcg_normal_mid","price_tcg_normal_low")
    for key in keys:
        value=_pc_float(card.get(key)) if isinstance(card,dict) else None
        if value is not None and value > 0:
            return value, key
    return None, None


def pokecollector_sync_collection(user_id=None):
    token, mode, error=pokecollector_session()
    if error: return None, error
    try:
        data=pokecollector_request("api/collection/", token=token, timeout=30)
    except Exception as exc:
        return None, f"PokéCollector-Sammlung konnte nicht geladen werden: {exc}"
    authoritative_total = _pc_portfolio_total(data)
    primary_price = "avg7"
    try:
        settings = pokecollector_request("api/settings/", token=token, timeout=20)
        primary_price = _pc_settings_primary_price(settings) or primary_price
    except Exception as exc:
        app.logger.warning("PokéCollector price setting failed: %s", exc)
    # /api/collection/ is intentionally row-oriented. PokéCollector exposes
    # its own selected price field and authoritative portfolio total through
    # the dashboard endpoint. The endpoint defaults to trend unless the same
    # price_field query used by the frontend is supplied.
    try:
        dashboard = pokecollector_request(
            "api/dashboard/?price_field=" + quote(primary_price, safe=""),
            token=token,
            timeout=30,
        )
        if isinstance(dashboard, dict):
            primary_price = _pc_primary_price_name(dashboard.get("price_field"), primary_price)
            dashboard_total = _pc_float(dashboard.get("total_value"))
            if dashboard_total is not None and dashboard_total >= 0:
                authoritative_total = dashboard_total
    except Exception as exc:
        app.logger.warning("PokéCollector dashboard summary failed: %s", exc)
    rows=data if isinstance(data,list) else ((data or {}).get("items") or (data or {}).get("collection") or (data or {}).get("results") or [])
    if not isinstance(rows,list): return None, "PokéCollector lieferte ein unbekanntes Sammlungsformat."
    uid=user_id or active_collection_user_id(); stats={"new":0,"updated":0,"unchanged":0,"errors":0,"priced":0,"unpriced":0,"total":len(rows),"price_field":primary_price}
    computed_portfolio_total = 0.0
    detail_cache={}
    for src in rows:
        try:
            if not isinstance(src,dict): raise ValueError("Ungültiger Datensatz")
            embedded=src.get("card") if isinstance(src.get("card"),dict) else {}
            pc_id=_pc_pick(src,"id","collection_item_id","collection_id")
            card_id=_pc_pick(src,"card_id") or _pc_pick(embedded,"id","card_id")
            # /api/collection/ does not expose all price columns in every PokéCollector version.
            # Enrich each unique card once via /api/cards/{card_id}.
            if card_id not in detail_cache:
                detail_cache[card_id]=_pc_card_details(card_id, token)
            details=detail_cache.get(card_id) or {}
            card=dict(embedded)
            card.update({k:v for k,v in details.items() if v not in (None,"")})
            tcg_id=_pc_pick(card,"tcg_card_id","tcgdex_id") or card_id
            if not pc_id: pc_id=f"{card_id}:{_pc_pick(src,'variant') or 'Normal'}:{_pc_pick(src,'lang','language') or 'de'}:{_pc_pick(src,'condition') or ''}:{_pc_pick(src,'purchase_price') or ''}"
            ext=f"pokecollector:{pc_id}"
            row=CollectorItem.query.filter_by(user_id=uid,category="cards",external_source="PokéCollector",external_id=ext).first()
            created=row is None
            if created: row=CollectorItem(user_id=uid,category="cards",external_source="PokéCollector",external_id=ext,title="Pokémon-Karte")
            before=(row.title,row.quantity,row.purchase_price_eur,row.condition,row.edition,row.cover_url,row.metadata_json,row.auto_value_eur,row.auto_value_source,row.tcg_game,row.card_set,row.card_number,row.card_language,row.card_variant,row.card_rarity,row.card_grade)
            title=str(_pc_pick(card,"name","name_de","title") or _pc_pick(src,"name","title") or card_id or "Pokémon-Karte")[:255]
            set_obj=card.get("set") if isinstance(card.get("set"),dict) else {}
            set_name=_pc_pick(set_obj,"name") or _pc_pick(card,"set_name") or _pc_pick(src,"set_name") or _pc_pick(card,"set_id")
            lang=str(_pc_pick(src,"lang","language") or _pc_pick(card,"lang","language") or "de")
            variant=str(_pc_pick(src,"variant") or "Normal")
            condition=str(_pc_pick(src,"condition") or "") or None
            grade=str(_pc_pick(src,"grade") or "raw")
            qty=int(_pc_pick(src,"quantity") or 1)
            purchase=_pc_float(_pc_pick(src,"purchase_price","purchase_price_eur"))
            rarity=_pc_pick(card,"rarity"); local_id=_pc_pick(card,"local_id","localId","number")
            # The owned collection row is authoritative. Only older PokéCollector
            # APIs without a row value fall back to the provider price columns.
            market, price_field=_pc_collection_row_price(src)
            if market is None:
                market, price_field=_pc_variant_price(card, variant, primary_price)
            price_source="PokéCollector" if price_field and not str(price_field).startswith("price_") else ("PokéCollector / Cardmarket" if price_field and not price_field.startswith("price_tcg_") else ("PokéCollector / TCGPlayer" if price_field else None))
            meta={"tcg":"pokemon","provider":"PokéCollector","pokecollector_id":pc_id,"card_id":card_id,"tcgdex_id":tcg_id,"set":set_obj or set_name,"set_id":_pc_pick(card,"set_id"),"set_name":set_name,"card_number":local_id,"rarity":rarity,"language":lang,"variant":variant,"grade":grade,"artist":_pc_pick(card,"artist"),"price_field":price_field,"price_source_lang":_pc_pick(card,"price_source_lang"),"printing_detail_tags":_pc_pick(src,"printing_detail_tags") or []}
            row.title=title; row.quantity=max(qty,1); row.purchase_price_eur=purchase; row.condition=condition
            row.media_type="Pokémon TCG"; row.edition=str(set_name)[:160] if set_name else row.edition
            row.cover_url=_pc_card_image(card,tcg_id) or row.cover_url
            row.metadata_json=json.dumps(meta,ensure_ascii=False)
            row.tcg_game="Pokémon"; row.card_set=str(set_name)[:160] if set_name else None; row.card_number=str(local_id)[:80] if local_id else None
            row.card_language=lang[:32]; row.card_variant=variant[:80]; row.card_rarity=str(rarity)[:120] if rarity else None; row.card_grade=grade[:80]
            if market is not None:
                row.auto_value_eur=market; row.auto_value_low_eur=None; row.auto_value_high_eur=None
                row.auto_value_source=price_source; row.auto_value_status="ok"; row.auto_value_updated_at=utc_now(); stats["priced"]+=1
                computed_portfolio_total += float(market) * max(qty, 1)
            else:
                stats["unpriced"]+=1
            after=(row.title,row.quantity,row.purchase_price_eur,row.condition,row.edition,row.cover_url,row.metadata_json,row.auto_value_eur,row.auto_value_source,row.tcg_game,row.card_set,row.card_number,row.card_language,row.card_variant,row.card_rarity,row.card_grade)
            if created: db.session.add(row); stats["new"]+=1
            elif before != after: stats["updated"]+=1
            else: stats["unchanged"]+=1
        except Exception:
            stats["errors"]+=1
            app.logger.exception("PokéCollector sync row failed")
    db.session.commit()
    app_setting_set("pokecollector_last_sync", utc_now().isoformat())
    app_setting_set("pokecollector_last_sync_stats", json.dumps(stats))
    portfolio_total = authoritative_total
    if portfolio_total is None and stats["errors"] == 0:
        # Older/current PokéCollector APIs return a bare collection list without
        # a portfolio summary. Rebuild the same dashboard total from the exact
        # per-card values selected above instead of leaving a stale/empty total.
        portfolio_total = round(computed_portfolio_total, 2)
    if portfolio_total is not None:
        stats["portfolio_value_eur"] = float(portfolio_total)
        app_setting_set("pokecollector_portfolio_value_eur", str(portfolio_total))
    db.session.commit()
    return stats, None


@app.route("/admin/integrations/pokecollector", methods=["POST"])
@login_required
def admin_pokecollector_settings():
    if not current_user.is_admin: abort(403)
    if request.form.get("remove") == "1":
        for key in ("pokecollector_base_url","pokecollector_username","pokecollector_password"):
            row=db.session.get(AppSetting,key)
            if row: db.session.delete(row)
        db.session.commit(); flash("PokéCollector-Verbindung entfernt.","success")
        return redirect(url_for("account")+"#pokecollector-integration")
    current=pokecollector_credentials()
    base=(request.form.get("base_url") or current["base_url"] or "http://pokemon-backend:8000").strip().rstrip("/")
    username=(request.form.get("username") or current["username"]).strip()
    password=request.form.get("password") or current["password"]
    app_setting_set("pokecollector_base_url",base); app_setting_set("pokecollector_username",username); app_setting_set("pokecollector_password",password,secret=True); db.session.commit()
    action=request.form.get("action") or "save"
    if action in {"test","sync"}:
        ok,msg=pokecollector_connection_test(); flash(msg,"success" if ok else "danger")
        if not ok: return redirect(url_for("account")+"#pokecollector-integration")
    if action=="sync":
        stats,error=pokecollector_sync_collection()
        if error: flash(error,"danger")
        else: flash(f"PokéCollector synchronisiert: {stats['new']} neu · {stats['updated']} aktualisiert · {stats['unchanged']} unverändert · {stats.get('priced',0)} mit Preis · {stats.get('unpriced',0)} ohne Preis · {stats['errors']} Fehler.","success" if not stats['errors'] else "warning")
    elif action=="save": flash("PokéCollector-Einstellungen gespeichert.","success")
    return redirect(url_for("account")+"#pokecollector-integration")


@app.route("/collector/cards/pokecollector/sync", methods=["POST"])
@login_required
def collector_cards_pokecollector_sync():
    if not current_user.is_admin: abort(403)
    stats,error=pokecollector_sync_collection()
    if error: flash(error,"danger")
    else: flash(f"PokéCollector synchronisiert: {stats['new']} neu · {stats['updated']} aktualisiert · {stats['unchanged']} unverändert · {stats.get('priced',0)} mit Preis · {stats.get('unpriced',0)} ohne Preis · {stats['errors']} Fehler.","success" if not stats['errors'] else "warning")
    return redirect(url_for("collector_section",section="cards"))


def tcgdex_json(path, params=None, language="de"):
    url=f"https://api.tcgdex.net/v2/{quote(language)}/{path.lstrip('/')}"
    if params: url += "?" + urlencode(params)
    req=Request(url, headers={"User-Agent":f"Collector/{APP_VERSION}", "Accept":"application/json"})
    try:
        with urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None


@app.route("/collector/cards/pokemon")
@login_required
def collector_cards_pokemon():
    # Compatibility URL from v2.4-v2.6; the UI is TCG-neutral since v2.7.0.
    q=(request.args.get("q") or "").strip()
    return redirect(url_for("collector_cards_search", q=q, tcg="pokemon"))


def _tcg_float(value):
    try:
        return float(str(value).replace(",", ".")) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _tcg_json_url(url, params=None, timeout=15):
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    req=Request(url, headers={"User-Agent":f"Collector/{APP_VERSION} (self-hosted collection manager)", "Accept":"application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        app.logger.warning("TCG provider request failed for %s: %s", url.split("?")[0], exc)
        return None


def _magic_search_query(query):
    """Translate collector shorthand such as '030/269 M15' into Scryfall syntax."""
    raw=(query or "").strip()
    # Common collector formats: 030/269 M15, 30 M15, M15 030, M15 30.
    m=re.fullmatch(r"0*(\d+)\s*/\s*\d+\s+([A-Za-z0-9_-]+)", raw, re.I)
    if m:
        return f"set:{m.group(2).lower()} cn:{int(m.group(1))}"
    m=re.fullmatch(r"0*(\d+)\s+([A-Za-z][A-Za-z0-9_-]{1,11})", raw, re.I)
    if m:
        return f"set:{m.group(2).lower()} cn:{int(m.group(1))}"
    m=re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]{1,11})\s+0*(\d+)(?:\s*/\s*\d+)?", raw, re.I)
    if m:
        return f"set:{m.group(1).lower()} cn:{int(m.group(2))}"
    return raw


def _magic_language_code(value):
    value=(value or "de").strip().lower()
    return value if value in {"de","en","fr","it","es","pt","ja","ko","ru","zhs","zht","all"} else "de"


def _magic_search_parts(query):
    """Split a human Magic query into name/artist hints without making artist mandatory."""
    raw=" ".join((query or "").strip().split())
    basic_aliases={"ebene":"Plains","insel":"Island","sumpf":"Swamp","gebirge":"Mountain","wald":"Forest"}
    lower=raw.casefold()
    for de_name,en_name in basic_aliases.items():
        if lower == de_name:
            return en_name, None, de_name
        prefix=de_name+" "
        if lower.startswith(prefix):
            return en_name, raw[len(prefix):].strip() or None, de_name
    aliases={"ende der reise":"Voyage's End"}
    if lower in aliases:
        return aliases[lower], None, lower
    return raw, None, None


def scryfall_search(query, language="de", artist_filter="", set_filter=""):
    raw=(query or "").strip()
    magic_query=_magic_search_query(raw)
    lang=_magic_language_code(language)
    name_hint, artist_hint, localized_alias=_magic_search_parts(raw)
    artist_filter=" ".join((artist_filter or artist_hint or "").split()).strip()
    set_filter=(set_filter or "").strip().lower()

    # Concrete printing search. For known localized names we search the English
    # Oracle identity and ask Scryfall for multilingual printings. Artist/set are
    # printing attributes and therefore belong in the provider query itself.
    attempts=[]
    if localized_alias:
        base=f'!"{name_hint.replace(chr(34), "")}"'
        if artist_filter: base += f' artist:"{artist_filter.replace(chr(34), "")}"'
        if set_filter: base += f' set:{set_filter}'
        attempts.append(base)
        # Artist spelling is a common source of zero results. A surname retry is
        # intentionally less strict but still keeps the card identity exact.
        if artist_filter and len(artist_filter.split()) > 1:
            attempts.append(f'!"{name_hint.replace(chr(34), "")}" artist:{artist_filter.split()[-1]}'+(f' set:{set_filter}' if set_filter else ''))
    else:
        base=magic_query
        if artist_filter: base += f' artist:"{artist_filter.replace(chr(34), "")}"'
        if set_filter and not re.search(r"(?:^|\\s)set:", base, re.I): base += f' set:{set_filter}'
        attempts.append(base)
        if raw and not re.search(r"(?:set:|cn:|oracleid:|lang:|artist:)", magic_query, re.I):
            attempts.append(f'!"{raw.replace(chr(34), "")}"'+(f' artist:"{artist_filter.replace(chr(34), "")}"' if artist_filter else '')+(f' set:{set_filter}' if set_filter else ''))

    data=None
    for candidate in dict.fromkeys(attempts):
        candidate_q=candidate if lang == "all" else f"({candidate}) lang:{lang}"
        data=_tcg_json_url("https://api.scryfall.com/cards/search", {"q":candidate_q,"unique":"prints","order":"released","dir":"desc","include_multilingual":"true"})
        if isinstance(data,dict) and data.get("data"):
            break
    if not isinstance(data,dict): return []
    rows=[]
    for card in (data.get("data") or [])[:80]:
        prices=card.get("prices") or {}; images=card.get("image_uris") or {}
        if not images and card.get("card_faces"):
            images=(card["card_faces"][0] or {}).get("image_uris") or {}
        finishes=card.get("finishes") or []
        rows.append({"provider":"scryfall","tcg":"Magic: The Gathering","id":str(card.get("id") or ""),"name":card.get("printed_name") or card.get("name"),
            "oracle_name":card.get("name"),"set_name":card.get("set_name"),"set_code":str(card.get("set") or "").upper(),"number":card.get("collector_number"),"rarity":str(card.get("rarity") or "").replace("_"," ").title(),
            "artist":card.get("artist"),"released_at":card.get("released_at"),"language":card.get("lang"),"finishes":finishes,
            "image":images.get("normal") or images.get("large") or images.get("small"),"price":_tcg_float(prices.get("eur")),"foil_price":_tcg_float(prices.get("eur_foil"))})
    return rows


def _ygo_language_code(value):
    raw=(value or "").strip().casefold()
    aliases={"de":"de","deutsch":"de","german":"de","en":"en","englisch":"en","english":"en","fr":"fr","französisch":"fr","francais":"fr","it":"it","italienisch":"it","pt":"pt","portugiesisch":"pt"}
    return aliases.get(raw, "de" if raw in {"", "all"} else raw)


def _ygo_language_label(code):
    return {"de":"Deutsch","en":"Englisch","fr":"Französisch","it":"Italienisch","pt":"Portugiesisch"}.get(_ygo_language_code(code), str(code or ""))


def _ygo_reference_setcode(code):
    """Return the EN reference printing code used by YGOPRODeck for EU printings.

    The entered/localized physical code remains the inventory identity. This helper
    is lookup-only, e.g. YGLD-DEC04 -> YGLD-ENC04.
    """
    raw=(code or "").strip().upper()
    m=re.fullmatch(r"(.+)-([A-Z]{2})([A-Z0-9]+)", raw)
    if m and m.group(2) in {"DE","FR","IT","PT","SP","ES"}:
        return f"{m.group(1)}-EN{m.group(3)}"
    return raw


def _ygo_code_language(code):
    raw=(code or "").strip().upper()
    m=re.fullmatch(r".+-([A-Z]{2})[A-Z0-9]+", raw)
    return {"DE":"de","EN":"en","FR":"fr","IT":"it","PT":"pt","SP":"es","ES":"es"}.get(m.group(1) if m else "")


def _ygo_localized_setcode(code, language_code):
    """Render an EN reference code as the requested physical EU language code.

    YGOPRODeck's card_sets list is primarily the English/reference printing list.
    Modern European printings use the same prefix/number with a language marker.
    Codes without an explicit EN marker (especially older sets) are left untouched
    rather than guessing a physical code that may never have existed.
    """
    raw=(code or "").strip().upper()
    lang=_ygo_language_code(language_code)
    marker={"de":"DE","fr":"FR","it":"IT","pt":"PT","es":"SP"}.get(lang)
    if not marker:
        return raw
    m=re.fullmatch(r"(.+)-EN([A-Z0-9]+)", raw)
    return f"{m.group(1)}-{marker}{m.group(2)}" if m else raw


def _ygo_card_row(card, language_code=None, physical_setcode=None, reference_setcode=None):
    images=card.get("card_images") or []
    image=(images[0].get("image_url_small") if images else None)
    sets=card.get("card_sets") or []
    prices=card.get("card_prices") or []
    cardmarket=_tcg_float((prices[0] if prices else {}).get("cardmarket_price"))
    lang=_ygo_language_code(language_code or "en")
    set_rows=[]
    seen_sets=set()
    for x in sets:
        reference=str(x.get("set_code") or "").upper()
        shown=reference
        if physical_setcode and reference_setcode and reference==reference_setcode:
            shown=physical_setcode
        elif lang != "en":
            shown=_ygo_localized_setcode(reference, lang)
        key=(shown, str(x.get("set_name") or ""), str(x.get("set_rarity") or ""))
        if key in seen_sets:
            continue
        seen_sets.add(key)
        set_rows.append({"name":x.get("set_name"),"code":shown,"reference_code":reference,"rarity":x.get("set_rarity"),"price":cardmarket})
    return {"provider":"ygoprodeck","tcg":"Yu-Gi-Oh!","id":str(card.get("id") or ""),"name":card.get("name"),
        "set_name":None,"set_code":physical_setcode,"reference_setcode":reference_setcode,"number":physical_setcode or str(card.get("id") or ""),
        "rarity":None,"language":lang,"image":image,"price":cardmarket,"sets":set_rows}


def _ygo_localized_card(card_id, language_code):
    """Fetch one identified card in the requested YGOPRODeck language.

    English is the provider default and must not be sent as language=en.  For
    translated datasets we query by the already-known card id; this avoids the
    invalid combination of an English name with language=de.
    """
    lang=_ygo_language_code(language_code)
    params={"id":str(card_id)}
    if lang in {"de","fr","it","pt"}:
        params["language"]=lang
    data=_tcg_json_url("https://db.ygoprodeck.com/api/v7/cardinfo.php", params)
    cards=(data or {}).get("data") if isinstance(data,dict) else None
    return cards[0] if cards else None


def _ygo_wiki_printing_identity(reference, set_names):
    """Resolve an omitted YGO printing from an exact row in a rendered Wiki set list.

    Fandom's revision source for set pages is largely template/transclusion based, so
    the literal print code is often absent there even though it is visible in the
    rendered list.  Use MediaWiki action=parse and inspect only the table row that
    contains the exact requested print code.  Never use a search-result title as a
    card identity.
    """
    from html import unescape

    wiki=_tcg_json_url("https://yugioh.fandom.com/api.php", {
        "action":"query","list":"search","srsearch":f'"{reference}"',"srlimit":10,"format":"json"
    })
    hits=((wiki or {}).get("query") or {}).get("search") if isinstance(wiki,dict) else None
    if not hits:
        return None

    preferred={str(x or "").strip().casefold() for x in (set_names or []) if str(x or "").strip()}
    ordered=sorted(hits, key=lambda h: 0 if str((h or {}).get("title") or "").strip().casefold() in preferred else 1)
    code_re=re.compile(r"(?<![A-Z0-9])"+re.escape(reference)+r"(?![A-Z0-9])", re.I)

    def plain(fragment):
        fragment=re.sub(r"<script\b[^>]*>.*?</script>", " ", fragment, flags=re.I|re.S)
        fragment=re.sub(r"<style\b[^>]*>.*?</style>", " ", fragment, flags=re.I|re.S)
        fragment=re.sub(r"<[^>]+>", " ", fragment)
        return re.sub(r"\s+", " ", unescape(fragment)).strip()

    for hit in ordered:
        title=str((hit or {}).get("title") or "").strip()
        if not title:
            continue
        parsed=_tcg_json_url("https://yugioh.fandom.com/api.php", {
            "action":"parse","page":title,"prop":"text","format":"json","formatversion":2
        })
        html=((parsed or {}).get("parse") or {}).get("text") if isinstance(parsed,dict) else None
        if not isinstance(html,str) or not code_re.search(plain(html)):
            continue

        # The exact code must occur in the same rendered table row as the card.
        rows=re.findall(r"<tr\b[^>]*>.*?</tr>", html, flags=re.I|re.S)
        for row in rows:
            row_text=plain(row)
            if not code_re.search(row_text):
                continue

            # Links after the print-code cell contain the card name, rarity, etc.
            # Ask YGOPRODeck to validate each linked title and accept the first exact
            # card name it recognizes.  Namespace/category links are ignored.
            links=[]
            for href,label in re.findall(r'<a\b[^>]*href="[^"]*"[^>]*title="([^"]+)"[^>]*>(.*?)</a>', row, flags=re.I|re.S):
                candidate=plain(label) or unescape(href)
                candidate=re.sub(r"\s+\((?:original|card|anime|manga)\)\s*$", "", candidate, flags=re.I).strip().strip('"')
                if not candidate or ':' in candidate or candidate.upper()==reference or candidate in links:
                    continue
                links.append(candidate)

            for candidate in links:
                data=_tcg_json_url("https://db.ygoprodeck.com/api/v7/cardinfo.php", {"name":candidate})
                cards=(data or {}).get("data") if isinstance(data,dict) else None
                if cards and str(cards[0].get("name") or "").strip().casefold()==candidate.casefold():
                    card=cards[0]
                    rarity=None
                    for known in ("Starlight Rare","Quarter Century Secret Rare","Prismatic Secret Rare","Secret Rare","Ultra Rare","Super Rare","Rare","Common"):
                        if known.casefold() in row_text.casefold():
                            rarity=known; break
                    return {"id":card.get("id"),"name":card.get("name"),
                            "set_name":title if title.casefold() in preferred else ((set_names or [title])[0]),
                            "set_code":reference,"set_rarity":rarity,"set_price":None}
    return None

def _ygo_printing_info(reference_setcode):
    """Resolve a YGO printing code, accepting only evidence tied to the exact code."""
    reference=(reference_setcode or "").strip().upper()
    if not reference:
        return None

    info=_tcg_json_url("https://db.ygoprodeck.com/api/v7/cardsetsinfo.php", {"setcode":reference})
    if isinstance(info,dict) and info.get("id"):
        return info

    prefix=reference.split("-",1)[0]
    sets=_tcg_json_url("https://db.ygoprodeck.com/api/v7/cardsets.php")
    if not isinstance(sets,list):
        return None

    set_names=[]
    for entry in sets:
        entry=entry or {}
        if str(entry.get("set_code") or "").strip().upper()==prefix:
            name=str(entry.get("set_name") or "").strip()
            if name and name not in set_names:
                set_names.append(name)

    # First trust exact YGOPRODeck printing data.  A suffix match is retained only
    # when it produces one unique candidate inside the already identified set.
    wanted_suffix=reference.split("-",1)[1] if "-" in reference else ""
    exact=[]
    suffix_candidates=[]
    for set_name in set_names:
        data=_tcg_json_url("https://db.ygoprodeck.com/api/v7/cardinfo.php", {"cardset":set_name})
        cards=(data or {}).get("data") if isinstance(data,dict) else None
        for card in cards or []:
            matched=False
            for printing in card.get("card_sets") or []:
                code=str(printing.get("set_code") or "").strip().upper()
                if code==reference:
                    resolved=dict(printing); resolved["id"]=card.get("id"); resolved["name"]=card.get("name")
                    exact.append(resolved); matched=True
            if matched:
                continue
            for printing in card.get("card_sets") or []:
                code=str(printing.get("set_code") or "").strip().upper()
                suffix=code.split("-",1)[1] if "-" in code else ""
                if wanted_suffix and suffix==wanted_suffix:
                    suffix_candidates.append({"id":card.get("id"),"name":card.get("name"),
                        "set_name":set_name,"set_code":reference,
                        "set_rarity":printing.get("set_rarity"),"set_price":printing.get("set_price")})
                    break
    if exact:
        return exact[0]
    if len(suffix_candidates)==1:
        return suffix_candidates[0]

    # For provider omissions, never use a Wiki search-result title as the card.
    # Resolve only from page source that contains this exact physical print code.
    return _ygo_wiki_printing_identity(reference, set_names)


def _ygo_deck_rows(prefix):
    """Discover physical Yu-Gi-Oh! printings for a deck/set prefix.

    Example: YGLD-DE discovers the German A/B/C/G... printings while using the
    English reference codes only for provider lookup.  Discovery is based on
    exact print codes in the rendered set list; no fuzzy card identity matching.
    """
    from html import unescape
    raw=(prefix or "").strip().upper().rstrip("-")
    m=re.fullmatch(r"([A-Z0-9]{2,16})-([A-Z]{2})", raw)
    if not m:
        return []
    set_prefix, marker=m.groups()
    lang={"DE":"de","EN":"en","FR":"fr","IT":"it","PT":"pt","SP":"es","ES":"es"}.get(marker)
    if not lang:
        return []
    reference_prefix=f"{set_prefix}-EN"

    sets=_tcg_json_url("https://db.ygoprodeck.com/api/v7/cardsets.php")
    set_names=[]
    for entry in sets if isinstance(sets,list) else []:
        if str((entry or {}).get("set_code") or "").strip().upper()==set_prefix:
            name=str((entry or {}).get("set_name") or "").strip()
            if name and name not in set_names:
                set_names.append(name)
    if not set_names:
        return []

    def plain(fragment):
        fragment=re.sub(r"<script\b[^>]*>.*?</script>"," ",fragment,flags=re.I|re.S)
        fragment=re.sub(r"<style\b[^>]*>.*?</style>"," ",fragment,flags=re.I|re.S)
        fragment=re.sub(r"<[^>]+>"," ",fragment)
        return re.sub(r"\s+"," ",unescape(fragment)).strip()

    # Parse the set page once. This is intentionally much cheaper than resolving
    # every card through the provider while merely showing the checklist.
    parsed=_tcg_json_url("https://yugioh.fandom.com/api.php", {
        "action":"parse","page":set_names[0],"prop":"text","format":"json","formatversion":2
    })
    html=((parsed or {}).get("parse") or {}).get("text") if isinstance(parsed,dict) else None
    if not isinstance(html,str):
        return []

    code_re=re.compile(r"(?<![A-Z0-9])("+re.escape(reference_prefix)+r"[A-Z0-9]+)(?![A-Z0-9])",re.I)
    rows=[]; seen=set()
    for tr in re.findall(r"<tr\b[^>]*>.*?</tr>",html,flags=re.I|re.S):
        text=plain(tr)
        match=code_re.search(text)
        if not match:
            continue
        reference=match.group(1).upper()
        physical=_ygo_localized_setcode(reference,lang)
        if physical in seen:
            continue
        links=[]
        for title,label in re.findall(r'<a\b[^>]*href="[^"]*"[^>]*title="([^"]+)"[^>]*>(.*?)</a>',tr,flags=re.I|re.S):
            candidate=plain(label) or unescape(title)
            candidate=re.sub(r"\s+\((?:original|card|anime|manga)\)\s*$","",candidate,flags=re.I).strip().strip('"')
            if not candidate or ':' in candidate or candidate.upper() in {reference,physical} or candidate in links:
                continue
            links.append(candidate)
        name=links[0] if links else "Unbekannte Karte"
        rarity=None
        for known in ("Starlight Rare","Quarter Century Secret Rare","Prismatic Secret Rare","Secret Rare","Ultra Rare","Super Rare","Rare","Common"):
            if known.casefold() in text.casefold(): rarity=known; break
        section=""
        suffix=reference[len(reference_prefix):]
        if suffix and suffix[0].isalpha(): section=suffix[0]
        rows.append({"code":physical,"reference_code":reference,"name":name,"rarity":rarity,"section":section})
        seen.add(physical)
    return sorted(rows,key=lambda x:x["code"])


@app.route("/collector/cards/yugioh/deck")
@login_required
def collector_cards_yugioh_deck():
    prefix=(request.args.get("prefix") or "YGLD-DE").strip().upper()
    rows=[]; error=None
    if request.args.get("prefix") is not None:
        try:
            rows=_ygo_deck_rows(prefix)
            if not rows: error="Für diesen Set-/Deck-Präfix wurden keine Karten gefunden."
        except Exception:
            current_app.logger.exception("Yu-Gi-Oh deck discovery failed")
            error="Die Set-/Deck-Liste konnte nicht geladen werden."
    uid=active_collection_user_id()
    existing_codes={}
    if rows:
        for item in CollectorItem.query.filter_by(user_id=uid,category="cards").all():
            if (item.tcg_game or "").casefold()!="yu-gi-oh!": continue
            code=(item.card_number or "").strip().upper()
            if code: existing_codes[code]=existing_codes.get(code,0)+max(item.quantity or 1,1)
    return render_template("collector_cards_yugioh_deck.html",prefix=prefix,rows=rows,error=error,existing_codes=existing_codes)


def _ygo_add_by_physical_code(uid, physical_code):
    physical=(physical_code or "").strip().upper()
    lang=_ygo_code_language(physical) or "de"
    reference=_ygo_reference_setcode(physical)
    info=_ygo_printing_info(reference)
    if not isinstance(info,dict) or not info.get("id"):
        raise ValueError("Ausgabe konnte nicht eindeutig aufgelöst werden")
    card_id=str(info.get("id"))
    card=_ygo_localized_card(card_id,lang) or _ygo_localized_card(card_id,"en")
    if not isinstance(card,dict):
        raise ValueError("Kartendaten konnten nicht geladen werden")
    title=card.get("name") or info.get("name") or physical
    set_name=info.get("set_name")
    rarity=info.get("set_rarity")
    prices=card.get("card_prices") or []
    cardmarket=_tcg_float((prices[0] if prices else {}).get("cardmarket_price"))
    value=cardmarket
    if value is None:
        usd=_tcg_float(info.get("set_price")); rate=_usd_to_eur_rate() if usd is not None else None
        if usd is not None and rate is not None: value=round(usd*rate,2)
    images=card.get("card_images") or []; remote=images[0].get("image_url") if images else None
    image=_cache_tcg_image(remote,"ygoprodeck",f"{card_id}-{physical}")
    external_id=f"{card_id}:{physical}"
    language=_ygo_language_label(lang)
    existing=CollectorItem.query.filter_by(user_id=uid,category="cards",external_source="YGOPRODeck",external_id=external_id).all()
    duplicate=next((x for x in existing if (x.card_language or "").strip().casefold()==language.casefold() and (x.card_variant or "Normal").strip().casefold()=="normal" and (x.card_grade or "raw").strip().casefold()=="raw" and (x.condition or "").strip().casefold() in {"","unknown","unbekannt"}),None)
    if duplicate:
        duplicate.quantity=max(duplicate.quantity or 1,1)+1
        db.session.commit()
        return duplicate,False
    meta={"provider":"ygoprodeck","ygoprodeck_id":card_id,"set_code":physical,"reference_set_code":reference,"set_name":set_name,"rarity":rarity,"language":lang,"cardmarket_reference_eur":cardmarket,"api_price":value}
    row=CollectorItem(user_id=uid,category="cards",title=str(title)[:255],quantity=1,media_type="Yu-Gi-Oh! TCG",edition=str(set_name or "")[:160] or None,cover_url=image,external_source="YGOPRODeck",external_id=external_id,metadata_json=json.dumps(meta,ensure_ascii=False),tcg_game="Yu-Gi-Oh!",card_set=str(set_name or "")[:160] or None,card_number=physical,card_language=language,card_variant="Normal",card_rarity=str(rarity or "")[:120] or None,card_grade="raw",auto_value_eur=value,auto_value_source="YGOPRODeck" if value is not None else None,auto_value_status="ok" if value is not None else None,auto_value_updated_at=utc_now() if value is not None else None)
    db.session.add(row); db.session.commit()
    return row,True


@app.route("/collector/cards/yugioh/deck/add",methods=["POST"])
@login_required
def collector_cards_yugioh_deck_add():
    code=(request.form.get("code") or "").strip().upper()
    if not code:
        return jsonify({"ok":False,"error":"Setcode fehlt"}),400
    try:
        row,created=_ygo_add_by_physical_code(active_collection_user_id(),code)
        return jsonify({"ok":True,"created":created,"id":row.id,"title":row.title,"quantity":row.quantity})
    except Exception as exc:
        current_app.logger.warning("YGO quick add failed for %s: %s",code,exc)
        return jsonify({"ok":False,"error":str(exc)}),422


def ygopro_search(query, language="all"):
    raw=(query or "").strip()
    if not raw:
        return []

    requested=(language or "all").strip().casefold()
    preferred="de" if requested in {"", "all"} else _ygo_language_code(requested)

    # Physical printing code: resolve the provider's EN reference code but keep the
    # entered DE/FR/IT/PT code as the physical inventory identity.
    if re.fullmatch(r"[A-Za-z0-9]{2,16}-[A-Za-z0-9]{2,16}", raw):
        physical=raw.upper()
        lang=_ygo_code_language(physical) or preferred
        reference=_ygo_reference_setcode(physical)
        info=_ygo_printing_info(reference)
        if isinstance(info,dict) and info.get("id"):
            card=_ygo_localized_card(info.get("id"), lang)
            if not card:
                # Localization gaps must not make a valid physical printing vanish.
                card=_ygo_localized_card(info.get("id"), "en")
            if not card:
                card={"id":info.get("id"),"name":info.get("name"),"card_sets":[info],"card_images":[],"card_prices":[]}
            row=_ygo_card_row(card, lang, physical, reference)
            matching=[x for x in row["sets"] if x.get("reference_code")==reference]
            if not matching:
                matching=[{"name":info.get("set_name"),"code":physical,"reference_code":reference,"rarity":info.get("set_rarity"),"price":row.get("price")}]
            row["sets"]=matching
            row["set_name"]=matching[0].get("name")
            row["set_code"]=physical
            row["rarity"]=matching[0].get("rarity")
            return [row]
        return []

    # Passcodes are language-independent. Names are searched in the requested
    # language first. In "all" mode German is preferred and English is only a
    # fallback. Once identity is known we fetch the preferred localization by ID.
    is_passcode=bool(re.fullmatch(r"\d{8}", raw))
    search_langs=[preferred]
    if preferred != "en":
        search_langs.append("en")

    identified=[]
    seen_ids=set()
    for search_lang in search_langs:
        params={"id":raw} if is_passcode else {"fname":raw,"num":40,"offset":0}
        if search_lang in {"de","fr","it","pt"}:
            params["language"]=search_lang
        data=_tcg_json_url("https://db.ygoprodeck.com/api/v7/cardinfo.php", params)
        if not isinstance(data,dict):
            continue
        for card in (data.get("data") or [])[:40]:
            cid=str(card.get("id") or "")
            if not cid or cid in seen_ids:
                continue
            seen_ids.add(cid)
            # A fallback English match is reloaded in the preferred language so a
            # German search never turns into an English collection entry merely
            # because identity resolution needed the English database.
            localized=card if search_lang==preferred else (_ygo_localized_card(cid, preferred) or card)
            identified.append(_ygo_card_row(localized, preferred))
        if identified and (requested not in {"", "all"} or search_lang==preferred):
            # An explicit language, or a successful preferred-language search, is
            # authoritative. Do not append duplicate English copies of the card.
            break
    return identified

def tcgdex_search(query):
    data=tcgdex_json("cards", {"name":query})
    rows=[]
    if not isinstance(data,list): return rows
    for card in data[:40]:
        image=card.get("image")
        if image and not str(image).lower().endswith((".png",".jpg",".jpeg",".webp")): image=str(image)+"/high.webp"
        set_obj=card.get("set") if isinstance(card.get("set"),dict) else {}
        rows.append({"provider":"tcgdex","tcg":"Pokémon","id":str(card.get("id") or ""),"name":card.get("name"),"set_name":set_obj.get("name") or card.get("setName"),"set_code":set_obj.get("id") or card.get("setId"),"number":card.get("localId"),"rarity":card.get("rarity"),"language":card.get("language") or "de","artist":card.get("illustrator") or card.get("artist"),"illustrator":card.get("illustrator"),"image":image,"price":None})
    return rows


def _scan_temp_dir():
    path=Path(app.root_path)/"static"/"uploads"/"tcg"/".scan-temp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_card_scan_temp(max_age_seconds=3600):
    now=time.time()
    try:
        for item in _scan_temp_dir().iterdir():
            if item.is_file() and now-item.stat().st_mtime > max_age_seconds:
                item.unlink(missing_ok=True)
    except OSError:
        app.logger.warning("Could not clean temporary card scans", exc_info=True)


def _scan_token_path(token):
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token or ""):
        return None
    matches=list(_scan_temp_dir().glob(token+".*"))
    return matches[0] if matches else None


@app.route("/collector/cards/scan")
@login_required
def collector_cards_scan():
    flash("Der Kartenscanner wurde entfernt. Nutze bitte die Kartensuche.", "info")
    return redirect(url_for("collector_cards_search"))


def _multipart_file_body(field_name, filename, mime, body):
    boundary = "----CollectorBoundary" + secrets.token_hex(16)
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return boundary, head + body + tail


@app.route("/collector/cards/scan/recognize-pokemon", methods=["POST"])
@login_required
def collector_cards_scan_recognize_pokemon():
    """Proxy one scan photo to PokéCollector's configured visual recognizer.

    Collector never stores the photo here. PokéCollector sanitizes the upload and applies its
    configured vision provider, candidate ranking and optional visual verification.
    """
    upload = request.files.get("photo")
    if not upload or not upload.filename:
        return {"ok": False, "error": "Kein Foto empfangen."}, 400
    body = upload.read(10 * 1024 * 1024 + 1)
    if not body or len(body) > 10 * 1024 * 1024:
        return {"ok": False, "error": "Das Foto ist leer oder größer als 10 MB."}, 400
    mime = (upload.mimetype or "image/jpeg").lower()
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        return {"ok": False, "error": "Bitte JPG, PNG oder WebP verwenden."}, 400
    token, mode, error = pokecollector_session()
    if error:
        return {"ok": False, "error": error}, 502
    cfg = pokecollector_credentials()
    boundary, payload = _multipart_file_body("file", secure_filename(upload.filename) or "card.jpg", mime, body)
    headers = {
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": f"Collector/{APP_VERSION}",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(cfg["base_url"] + "/api/cards/recognize", data=payload, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=55) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
            detail = parsed.get("detail") if isinstance(parsed, dict) else None
        except Exception:
            detail = None
        return {"ok": False, "error": str(detail or f"PokéCollector-Scanner HTTP {exc.code}")}, 502
    except Exception as exc:
        return {"ok": False, "error": f"PokéCollector-Scanner nicht erreichbar: {exc}"}, 502
    recognized = data.get("recognized") if isinstance(data, dict) else {}
    matches = data.get("matches") if isinstance(data, dict) else []
    recognized = recognized if isinstance(recognized, dict) else {}
    matches = matches if isinstance(matches, list) else []
    return {
        "ok": True,
        "recognized": recognized,
        "matches": matches[:8],
        "confident": bool(data.get("_identity_confident")) if isinstance(data, dict) else False,
        "decision": data.get("_identity_decision") if isinstance(data, dict) else None,
    }


@app.route("/collector/cards/scan/photo", methods=["POST"])
@login_required
def collector_cards_scan_photo():
    """Store a scan only when the user explicitly chose to keep their own photo."""
    _cleanup_card_scan_temp()
    upload=request.files.get("photo")
    if not upload or not upload.filename:
        return {"ok":False,"error":"Kein Foto empfangen."},400
    body=upload.read(10*1024*1024+1)
    if not body or len(body)>10*1024*1024:
        return {"ok":False,"error":"Das Foto ist leer oder größer als 10 MB."},400
    mime=(upload.mimetype or "").lower()
    ext={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}.get(mime)
    if not ext:
        return {"ok":False,"error":"Bitte JPG, PNG oder WebP verwenden."},400
    token=secrets.token_urlsafe(24)
    (_scan_temp_dir()/(token+ext)).write_bytes(body)
    return {"ok":True,"token":token}


def _consume_scan_photo(token, item_id):
    src=_scan_token_path(token)
    if not src: return None
    try:
        dest_dir=Path(app.root_path)/"static"/"uploads"/"tcg"/"user-photos"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest=dest_dir/f"card-{item_id}-{secrets.token_hex(5)}{src.suffix.lower()}"
        src.replace(dest)
        return "/static/uploads/tcg/user-photos/"+dest.name
    except OSError:
        app.logger.exception("Could not preserve card scan photo")
        return None


def pokecollector_local_card_search(query):
    """Use already-synchronised PokéCollector cards as an additional Pokémon scan/search source.

    This intentionally searches by card name. Card number/set hints are verification data, not a
    replacement for the name query produced by the scanner.
    """
    q=(query or "").strip().casefold()
    if not q:
        return []
    rows=[]
    owned=CollectorItem.query.filter_by(user_id=active_collection_user_id(), category="cards", external_source="PokéCollector").all()
    for item in owned:
        if q not in (item.title or "").casefold():
            continue
        meta=collector_metadata(item)
        rows.append({
            "provider":"pokecollector_local", "tcg":"Pokémon", "id":str(item.id),
            "name":item.title, "set_name":item.card_set or item.edition,
            "set_code":meta.get("set_id"), "number":item.card_number,
            "rarity":item.card_rarity, "language":item.card_language,
            "image":item.cover_url, "price":item.auto_value_eur,
            "existing_item_id":item.id,
        })
    return rows[:40]


@app.route("/collector/cards/search")
@login_required
def collector_cards_search():
    q=(request.args.get("q") or "").strip(); tcg=(request.args.get("tcg") or "auto").strip().lower()
    language_filter=(request.args.get("language") or request.args.get("magic_lang") or "all").strip().lower(); artist_filter=(request.args.get("artist") or "").strip(); set_filter=(request.args.get("set") or "").strip(); number_filter=(request.args.get("number") or "").strip(); variant_filter=(request.args.get("variant") or "").strip()
    rows=[]; provider_errors=[]
    if q:
        providers=[]
        if tcg in {"auto","pokemon"}: providers += [("PokéCollector",pokecollector_local_card_search),("Pokémon",tcgdex_search)]
        if tcg in {"auto","magic"}: providers.append(("Magic",lambda query:scryfall_search(query,language_filter,artist_filter,set_filter)))
        if tcg in {"auto","yugioh"}: providers.append(("Yu-Gi-Oh!",lambda query:ygopro_search(query,language_filter)))
        for label,fn in providers:
            try: rows.extend(fn(q))
            except Exception: current_app.logger.exception("TCG search failed: %s",label); provider_errors.append(label)
        if set_filter:
            for row in rows:
                if row.get("provider")=="ygoprodeck" and row.get("sets"):
                    row["sets"]=[x for x in row["sets"] if set_filter.casefold() in (str(x.get("name") or "")+" "+str(x.get("code") or "")).casefold()]
            rows=[r for r in rows if r.get("provider")!="ygoprodeck" or r.get("sets")]
        def matches(row):
            lang=str(row.get("language") or "").casefold(); artist=str(row.get("artist") or row.get("illustrator") or "").casefold(); set_blob=(str(row.get("set_name") or "")+" "+str(row.get("set_code") or "")).casefold(); number=str(row.get("number") or "").casefold(); finishes=[str(x).casefold() for x in (row.get("finishes") or [])]
            if language_filter not in {"","all"} and lang and lang!=language_filter.casefold(): return False
            if artist_filter and artist and artist_filter.casefold() not in artist: return False
            if set_filter and set_blob and set_filter.casefold() not in set_blob: return False
            if number_filter and number and number_filter.casefold() not in number: return False
            if variant_filter and finishes and variant_filter.casefold() not in finishes: return False
            return True
        rows=[r for r in rows if matches(r)]
    artists=sorted({str(r.get("artist") or r.get("illustrator") or "").strip() for r in rows if r.get("artist") or r.get("illustrator")}); sets=sorted({(str(r.get("set_code") or ""),str(r.get("set_name") or "")) for r in rows if r.get("set_code") or r.get("set_name")})
    return render_template("collector_cards_search.html",q=q,tcg=tcg,language_filter=language_filter,magic_lang=language_filter,rows=rows,provider_errors=provider_errors,artist_filter=artist_filter,set_filter=set_filter,number_filter=number_filter,variant_filter=variant_filter,artists=artists,card_sets=sets,magic_sets=sets)


def _cache_tcg_image(url, provider, external_id):
    if not url: return None
    try:
        suffix=Path(urlsplit(url).path).suffix.lower()
        if suffix not in {".jpg",".jpeg",".png",".webp"}: suffix=".jpg"
        safe=re.sub(r"[^A-Za-z0-9_.-]+","-",str(external_id))[:120]
        rel=Path("tcg")/provider/f"{safe}{suffix}"
        target=Path(app.root_path)/"static"/"uploads"/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            req=Request(url,headers={"User-Agent":f"Collector/{APP_VERSION}"})
            with urlopen(req,timeout=20) as response:
                body=response.read(8*1024*1024)
            target.write_bytes(body)
        return "/static/uploads/"+str(rel).replace(os.sep,"/")
    except Exception:
        app.logger.exception("Could not cache TCG image")
        return None


@app.route("/collector/cards/add/<provider>/<path:card_id>", methods=["POST"])
@login_required
def collector_cards_add(provider, card_id):
    uid=active_collection_user_id(); provider=provider.lower(); set_code=(request.form.get("set_code") or "").strip(); scan_token=(request.form.get("scan_token") or "").strip()
    variant=(request.form.get("variant") or "Normal").strip()[:80]; language=(request.form.get("language") or "").strip()[:32] or None
    title=set_name=number=rarity=image=None; value=None; source=None; external_id=str(card_id); meta={"provider":provider}
    if provider=="tcgdex":
        data=tcgdex_json("cards/"+quote(card_id,safe=""))
        if not isinstance(data,dict): flash("TCGdex konnte die Karte nicht laden.","danger"); return redirect(url_for("collector_cards_search"))
        sd=data.get("set") or {}; title=data.get("name"); set_name=sd.get("name"); number=data.get("localId"); rarity=data.get("rarity"); image=data.get("image")
        if image and not str(image).lower().endswith((".png",".jpg",".jpeg",".webp")): image=str(image)+"/high.webp"
        tcg_name="Pokémon"; media="Pokémon TCG"; source="TCGdex"; meta.update({"tcgdex_id":card_id,"set":sd,"localId":number,"rarity":rarity})
    elif provider=="scryfall":
        data=_tcg_json_url("https://api.scryfall.com/cards/"+quote(card_id,safe=""))
        if not isinstance(data,dict): flash("Scryfall konnte die Karte nicht laden.","danger"); return redirect(url_for("collector_cards_search"))
        prices=data.get("prices") or {}; images=data.get("image_uris") or {}
        if not images and data.get("card_faces"): images=(data["card_faces"][0] or {}).get("image_uris") or {}
        title=data.get("printed_name") or data.get("name"); set_name=data.get("set_name"); set_code=str(data.get("set") or "").upper(); number=data.get("collector_number"); rarity=str(data.get("rarity") or "").replace("_"," ").title(); image=images.get("normal") or images.get("large")
        is_foil="foil" in variant.casefold(); value=_tcg_float(prices.get("eur_foil") if is_foil else prices.get("eur")); tcg_name="Magic: The Gathering"; media="Magic: The Gathering"; source="Scryfall"
        if value is None:
            usd=_tcg_float(prices.get("usd_foil") if is_foil else prices.get("usd")); rate=_usd_to_eur_rate() if usd is not None else None
            if usd is not None and rate is not None: value=round(usd*rate,2)
        meta.update({"scryfall_id":card_id,"oracle_id":data.get("oracle_id"),"set_code":set_code,"finish":variant,"prices":prices,"artist":data.get("artist"),"released_at":data.get("released_at"),"collector_number":number})
    elif provider=="ygoprodeck":
        ygo_lang=_ygo_language_code(language or _ygo_code_language(set_code) or "de")
        reference_code=_ygo_reference_setcode(set_code)
        data=_tcg_json_url("https://db.ygoprodeck.com/api/v7/cardinfo.php", {"id":card_id,"language":ygo_lang})
        cards=(data or {}).get("data") if isinstance(data,dict) else None
        if not cards: flash("YGOPRODeck konnte die Karte nicht laden.","danger"); return redirect(url_for("collector_cards_search"))
        data=cards[0]
        selected=next((x for x in (data.get("card_sets") or []) if str(x.get("set_code") or "").upper()==reference_code),None)
        if not selected and set_code==reference_code:
            selected=next((x for x in (data.get("card_sets") or []) if str(x.get("set_code") or "").upper()==set_code.upper()),None)
        # Some legitimate physical printings (for example YGLD-ENG01 /
        # YGLD-DEG01) are missing from YGOPRODeck's card_sets.  Reuse the
        # exact printing resolver used by search, but only accept it when it
        # resolves to the very same provider card id.  This prevents a
        # fallback from ever changing the card identity during import.
        if not selected:
            resolved=_ygo_printing_info(reference_code)
            if (isinstance(resolved,dict) and
                    str(resolved.get("id") or "")==str(card_id) and
                    str(resolved.get("set_code") or "").strip().upper()==reference_code):
                selected=resolved
        if not selected: flash("Bitte eine konkrete Yu-Gi-Oh!-Ausgabe auswählen.","warning"); return redirect(url_for("collector_cards_search",q=data.get("name"),tcg="yugioh",language=ygo_lang))
        title=data.get("name"); set_name=selected.get("set_name"); number=set_code; rarity=selected.get("set_rarity")
        prices=data.get("card_prices") or []; cardmarket=_tcg_float((prices[0] if prices else {}).get("cardmarket_price"))
        value=cardmarket
        if value is None:
            usd=_tcg_float(selected.get("set_price")); rate=_usd_to_eur_rate() if usd is not None else None
            if usd is not None and rate is not None: value=round(usd*rate,2)
        images=data.get("card_images") or []; remote=images[0].get("image_url") if images else None
        image=_cache_tcg_image(remote,"ygoprodeck",f"{card_id}-{set_code}"); tcg_name="Yu-Gi-Oh!"; media="Yu-Gi-Oh! TCG"; source="YGOPRODeck"; external_id=f"{card_id}:{set_code.upper()}"
        language=_ygo_language_label(ygo_lang)
        meta.update({"ygoprodeck_id":card_id,"set_code":set_code.upper(),"reference_set_code":reference_code,"set_name":set_name,"rarity":rarity,"language":ygo_lang,"cardmarket_reference_eur":cardmarket,"api_price":value})
    else: abort(404)
    # Same printing/copy characteristics are one inventory row. Different language,
    # finish, condition or grading remain separate collectible copies.
    existing=CollectorItem.query.filter_by(user_id=uid,category="cards",external_source=source,external_id=external_id).all()
    language_norm=(language or ("Deutsch" if provider in {"tcgdex","ygoprodeck"} else "")).strip().casefold()
    duplicate=next((x for x in existing if
        (x.card_language or "").strip().casefold()==language_norm and
        (x.card_variant or "Normal").strip().casefold()==variant.casefold() and
        (x.card_grade or "raw").strip().casefold()=="raw" and
        (x.condition or "").strip().casefold() in {"", "unknown", "unbekannt"}), None)
    if duplicate:
        duplicate.quantity=max(duplicate.quantity or 1,1)+1
        db.session.commit()
        flash(f"{duplicate.title} ist bereits vorhanden – Menge wurde auf {duplicate.quantity} erhöht.","success")
        return redirect(url_for("collector_item_detail",item_id=duplicate.id, return_to=url_for("collector_cards_search", q=(request.form.get("search_q") or ""), tcg=(request.form.get("search_tcg") or "auto"), language=(request.form.get("search_magic_lang") or "all"), artist=(request.form.get("search_artist") or ""), set=(request.form.get("search_set") or ""), number=(request.form.get("search_number") or ""), variant=(request.form.get("search_variant") or ""))))
    row=CollectorItem(user_id=uid,category="cards",title=str(title or external_id)[:255],quantity=1,media_type=media,edition=str(set_name or "")[:160] or None,cover_url=image,
        external_source=source,external_id=external_id,metadata_json=json.dumps(meta,ensure_ascii=False),tcg_game=tcg_name,card_set=str(set_name or "")[:160] or None,card_number=str(number or "")[:80] or None,
        card_language=language or ("Deutsch" if provider in {"tcgdex","ygoprodeck"} else None),card_variant=variant,card_rarity=str(rarity or "")[:120] or None,card_grade="raw",auto_value_eur=value,auto_value_source=source if value is not None else None,auto_value_status="ok" if value is not None else None,auto_value_updated_at=utc_now() if value is not None else None)
    db.session.add(row); db.session.flush()
    own_photo=_consume_scan_photo(scan_token,row.id) if scan_token else None
    if own_photo:
        meta["own_photo"]=own_photo
        meta["own_photo_source"]="card_scanner"
        row.metadata_json=json.dumps(meta,ensure_ascii=False)
    db.session.commit(); flash(f"{row.title} wurde zu Sammelkarten hinzugefügt." + (" Eigenes Scan-Foto wurde gespeichert." if own_photo else ""),"success")
    return redirect(url_for("collector_item_detail",item_id=row.id, return_to=url_for("collector_cards_search", q=(request.form.get("search_q") or ""), tcg=(request.form.get("search_tcg") or "auto"), language=(request.form.get("search_magic_lang") or "all"), artist=(request.form.get("search_artist") or ""), set=(request.form.get("search_set") or ""), number=(request.form.get("search_number") or ""), variant=(request.form.get("search_variant") or ""))))


DASHBOARD_WIDGET_IDS = (
    "category_values", "collector_values", "market_movement", "market_ranks",
    "insights", "valuation_health", "top_inventory", "top_collector", "recent_items",
)


def dashboard_layout_for(user_id):
    raw = app_setting_get(f"dashboard_layout_user_{int(user_id)}", "")
    try:
        payload = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        payload = {}
    order = [str(x) for x in payload.get("order", []) if str(x) in DASHBOARD_WIDGET_IDS]
    order.extend(x for x in DASHBOARD_WIDGET_IDS if x not in order)
    hidden = [str(x) for x in payload.get("hidden", []) if str(x) in DASHBOARD_WIDGET_IDS]
    return {"order": order, "hidden": hidden}


@app.route("/games/dashboard-layout", methods=["POST"])
@login_required
def dashboard_layout_save():
    payload = request.get_json(silent=True) or {}
    order = [str(x) for x in payload.get("order", []) if str(x) in DASHBOARD_WIDGET_IDS]
    order.extend(x for x in DASHBOARD_WIDGET_IDS if x not in order)
    hidden = [str(x) for x in payload.get("hidden", []) if str(x) in DASHBOARD_WIDGET_IDS]
    layout = {"order": order, "hidden": hidden}
    app_setting_set(f"dashboard_layout_user_{int(current_user.id)}", json.dumps(layout))
    db.session.commit()
    return {"ok": True, "layout": layout}


def dashboard_watermarks(owned_items, hardware_items, accessory_items, collector_rows, wishlist_items):
    """Choose recognizable images from the active collection, never stock art."""
    def first(values):
        return next((str(value) for value in values if str(value or "").strip()), None)
    images = {
        "games": first(item.game.cover_url for item in sorted(owned_items, key=lambda x: x.added_at or datetime.min, reverse=True)),
        "hardware": first(item.model.reference_image for item in hardware_items if item.model),
        "accessories": first((item.reference_image or item.photo) for item in accessory_items),
        "wishlist": first(item.game.cover_url for item in wishlist_items),
    }
    for category in ("movies", "tv", "books", "music", "cards", "custom"):
        rows = sorted((row for row in collector_rows if row.category == category), key=lambda x: x.added_at or datetime.min, reverse=True)
        images[category] = first(row.cover_url for row in rows)
    return images


def review_inbox_rows():
    """One actionable, grouped inbox across data, pricing and application health."""
    owner_id = active_collection_user_id()
    issue_labels = {
        "cover": "Spiele ohne Cover", "identifier": "Spiele ohne EAN oder Produktcode",
        "external": "Spiele ohne Metadatenquelle", "series_review": "Ungeklärte Spielreihen",
        "series_mismatch": "Widersprüchliche Reihenzuordnungen", "value": "Spiele ohne Wert",
        "collector_cover": "Collector-Einträge ohne Cover", "collector_external": "Collector-Einträge ohne Metadatenquelle",
        "collector_value": "Collector-Einträge ohne Wert", "edition_review": "Ausgabe ungeklärt",
        "de_release_review": "Deutsche physische Veröffentlichung ungeklärt", "physical_medium": "Medium ungeklärt",
        "barcode_duplicate": "Mögliche Dubletten", "external_shared": "Mehrfach verwendete externe IDs",
    }
    counts = {}
    for issue in quality_issues():
        for key in issue.get("missing", []):
            counts[key] = counts.get(key, 0) + 1
    tasks = []
    for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if count and key in issue_labels:
            tasks.append({"key": f"quality:{key}:{count}", "kind": "Daten", "icon": "🧹", "title": issue_labels[key], "count": count,
                          "description": "Einträge gesammelt prüfen und ergänzen.", "url": url_for("quality", issue=key), "priority": 2})
    price_rows = _price_center_rows()
    price_states = {
        "error": ("Preisquellen mit Fehlern", "Quelle oder Zuordnung kontrollieren.", 0),
        "outlier": ("Auffällige Preissprünge", "Wert vor Übernahme prüfen oder fixieren.", 0),
        "missing": ("Einträge ohne Marktwert", "Preisquelle ergänzen oder eigene Schätzung setzen.", 3),
        "stale": ("Veraltete Marktwerte", "Bewertung erneut ausführen.", 4),
    }
    for state, (title, description, priority) in price_states.items():
        count = sum(1 for row in price_rows if row["state"] == state)
        if count:
            tasks.append({"key": f"price:{state}:{count}", "kind": "Preise", "icon": "💶", "title": title, "count": count,
                          "description": description, "url": url_for("price_center", status=state), "priority": priority})
    incident_count = ApplicationError.query.filter_by(collection_user_id=owner_id).count()
    if incident_count:
        tasks.append({"key": f"errors:all:{incident_count}", "kind": "Technik", "icon": "🛠️", "title": "Protokollierte Anwendungsfehler", "count": incident_count,
                      "description": "Fehlerkennungen und betroffene Seiten kontrollieren.", "url": url_for("error_center"), "priority": 1})
    dismissed_raw = app_setting_get(f"review_inbox_dismissed_{owner_id}", "[]") or "[]"
    try:
        dismissed = set(json.loads(dismissed_raw))
    except (TypeError, ValueError):
        dismissed = set()
    tasks = [task for task in tasks if task["key"] not in dismissed]
    tasks.sort(key=lambda task: (task["priority"], -task["count"], task["title"].casefold()))
    return tasks


def collection_insights():
    """Explain the next useful collection actions instead of showing raw KPIs only."""
    uid = active_collection_user_id(); rows = []
    for series in _game_franchise_overview_rows(uid):
        missing = int(series.get("missing") or 0)
        owned = int(series.get("owned") or 0)
        total = int(series.get("total") or 0)
        if owned and 1 <= missing <= 3 and total:
            rows.append({"score": 100 - missing * 5, "icon": "🏁", "kind": "Reihe fast vollständig", "title": series["name"],
                         "description": f"Noch {missing} von {total} Spielen fehlen.", "url": series.get("detail_url") or url_for("collector_collections", type="games")})
    open_batches = CaptureBatch.query.filter_by(collection_user_id=uid, state="open").count()
    if open_batches:
        rows.append({"score": 88, "icon": "📷", "kind": "Erfassung fortsetzen", "title": f"{open_batches} offene Scan-Stapel",
                     "description": "Barcodes fertig erfassen und anschließend zuordnen.", "url": url_for("capture_batches")})
    uncovered_boxes = 0
    for item in CollectorItem.query.filter(CollectorItem.user_id == uid, CollectorItem.category.in_(["movies", "tv", "books"])).all():
        if _collector_multi_part_copy(item) and not ReleaseCoverage.query.filter_by(owner_id=uid, source_kind="collector", source_id=str(item.id)).first():
            uncovered_boxes += 1
    if uncovered_boxes:
        rows.append({"score": 92, "icon": "📦", "kind": "Boxinhalt ungeklärt", "title": f"{uncovered_boxes} Sammelausgaben prüfen",
                     "description": "Enthaltene Filme, Staffeln oder Bände zuordnen, damit der Fortschritt stimmt.", "url": url_for("review_inbox")})
    price_rows = _price_center_rows()
    outliers = sum(1 for row in price_rows if row["state"] == "outlier")
    missing_values = sum(1 for row in price_rows if row["state"] == "missing")
    if outliers:
        rows.append({"score": 98, "icon": "⚠️", "kind": "Preis prüfen", "title": f"{outliers} auffällige Preisänderungen",
                     "description": "Sprünge kontrollieren, bevor sie als verlässlich gelten.", "url": url_for("price_center", status="outlier")})
    if missing_values:
        rows.append({"score": 70, "icon": "💶", "kind": "Bewertung vervollständigen", "title": f"{missing_values} Einträge ohne Marktwert",
                     "description": "Automatische Quelle prüfen oder eine eigene Schätzung hinterlegen.", "url": url_for("price_center", status="missing")})
    wishlist_count = CollectionItem.query.filter_by(user_id=uid, status="wishlist", wishlist_priority=3).count()
    if wishlist_count:
        rows.append({"score": 72, "icon": "⭐", "kind": "Wunschliste", "title": f"{wishlist_count} Wünsche mit hoher Priorität",
                     "description": "Zielpreise und Kaufreihenfolge kontrollieren.", "url": url_for("wishlist")})
    issue_count = len(quality_issues())
    if issue_count:
        rows.append({"score": 60, "icon": "🧹", "kind": "Datenqualität", "title": f"{issue_count} Datenhinweise",
                     "description": "Fehlende Cover, IDs und Reihenzuordnungen verbessern.", "url": url_for("quality")})
    rows.sort(key=lambda row: (-row["score"], row["title"].casefold()))
    return rows


@app.route("/insights")
@login_required
def insights():
    rows = collection_insights()
    return render_template("insights.html", rows=rows)


@app.route("/inbox")
@login_required
def review_inbox():
    rows = review_inbox_rows()
    return render_template("review_inbox.html", rows=rows, total=sum(row["count"] for row in rows))


@app.route("/inbox/dismiss", methods=["POST"])
@login_required
def review_inbox_dismiss():
    key = (request.form.get("key") or "")[:240]
    valid = {row["key"] for row in review_inbox_rows()}
    if key not in valid:
        abort(400)
    owner_id = active_collection_user_id()
    setting_key = f"review_inbox_dismissed_{owner_id}"
    try:
        dismissed = set(json.loads(app_setting_get(setting_key, "[]") or "[]"))
    except (TypeError, ValueError):
        dismissed = set()
    dismissed.add(key)
    app_setting_set(setting_key, json.dumps(sorted(dismissed)))
    db.session.commit()
    flash("Hinweis ausgeblendet. Wenn sich die Anzahl ändert, erscheint er erneut.", "success")
    return redirect(url_for("review_inbox"))


@app.route("/bewertungen")
@login_required
def dashboard():
    owned_items = [i for i in CollectionItem.query.filter_by(status="owned", user_id=active_collection_user_id()).all() if game_is_physical_candidate(i.game)]
    physical_owned_items = [i for i in owned_items if (i.ownership_format or "physical") != "digital"]
    wishlist_items = [i for i in CollectionItem.query.filter_by(status="wishlist", user_id=active_collection_user_id()).all() if game_is_physical_candidate(i.game)]
    owned = len(owned_items)
    digital_owned = sum(1 for i in owned_items if i.ownership_format == "digital")
    physical_owned = owned - digital_owned
    wishlist = len(wishlist_items)
    total_value = sum((effective_value(i) or 0) for i in owned_items)
    valued_count = sum(1 for i in physical_owned_items if effective_value(i) is not None)
    auto_valued_count = sum(1 for i in physical_owned_items if i.auto_value_eur is not None)
    purchase_total = sum((i.purchase_price or 0) for i in owned_items)
    console_count = Console.query.count()
    catalog_count = Game.query.count()
    recent = sorted(owned_items, key=lambda i:i.added_at or datetime.min, reverse=True)[:8]
    valuation_status_counts = {}
    for item in physical_owned_items:
        key = item.auto_value_status or ("ok" if item.auto_value_eur is not None else "not_checked")
        valuation_status_counts[key] = valuation_status_counts.get(key, 0) + 1
    auto_missing_count = sum(1 for i in physical_owned_items if i.auto_value_eur is None)
    no_value_count = sum(1 for i in physical_owned_items if effective_value(i) is None)

    # v0.4.0 dashboard analytics
    by_console = {}
    for item in owned_items:
        name = item.game.console.name
        slot = by_console.setdefault(name, {"count": 0, "value": 0.0})
        slot["count"] += 1
        slot["value"] += effective_value(item) or 0
    console_stats = [dict(name=name, **values) for name, values in by_console.items()]
    console_stats.sort(key=lambda x: (x["value"], x["count"]), reverse=True)
    max_console_value = max([x["value"] for x in console_stats] or [0])
    for row in console_stats:
        row["pct"] = round((row["value"] / max_console_value) * 100) if max_console_value else 0

    top_value_items = sorted(
        [i for i in physical_owned_items if effective_value(i) is not None],
        key=lambda i: effective_value(i) or 0,
        reverse=True,
    )[:10]

    price_changes = []
    for item in physical_owned_items:
        history = sorted(item.price_history, key=lambda h: h.recorded_at or datetime.min, reverse=True)
        if len(history) >= 2:
            latest, previous = history[0], history[1]
            delta = latest.value_eur - previous.value_eur
            pct = (delta / previous.value_eur * 100) if previous.value_eur else 0
            price_changes.append({"item": item, "current": latest.value_eur, "previous": previous.value_eur, "delta": delta, "pct": pct})
    price_changes.sort(key=lambda x: abs(x["delta"]), reverse=True)
    change_total = sum(x["delta"] for x in price_changes)

    series_stats = _game_franchise_overview_rows(active_collection_user_id())
    series_stats.sort(key=lambda x: (x["owned"], x["total"]), reverse=True)

    missing_cover_count = sum(1 for i in owned_items if not i.game.cover_url)
    incomplete_data_count = len(quality_issues())
    high_priority_wishlist = CollectionItem.query.filter_by(user_id=active_collection_user_id(), status="wishlist", wishlist_priority=3).count()
    recent_activity = ActivityLog.query.filter_by(collection_user_id=active_collection_user_id()).order_by(ActivityLog.created_at.desc()).limit(6).all()

    # v0.7.9 valuation health: only successfully completed runs count as fresh.
    latest_auto_run = RevaluationRun.query.filter_by(collection_user_id=active_collection_user_id(), source="automatic", success=True).order_by(RevaluationRun.finished_at.desc()).first()
    latest_manual_run = RevaluationRun.query.filter_by(collection_user_id=active_collection_user_id(), source="manual", success=True).order_by(RevaluationRun.finished_at.desc()).first()
    valuation_health = {"state": "unknown", "label": "Noch kein automatischer Lauf protokolliert", "last_auto": None, "last_manual": None, "next_auto": None}
    try:
        tz = DISPLAY_TIMEZONE
        now_local = datetime.now(tz)
        def local_dt(value):
            if not value:
                return None
            aware = value.replace(tzinfo=ZoneInfo("UTC")) if value.tzinfo is None else value
            return aware.astimezone(tz)
        last_auto_local = local_dt(latest_auto_run.finished_at) if latest_auto_run else None
        last_manual_local = local_dt(latest_manual_run.finished_at) if latest_manual_run else None
        hour = int(os.environ.get("AUTOMATIC_REVALUE_HOUR", "3"))
        next_auto = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
        if next_auto <= now_local:
            from datetime import timedelta
            next_auto += timedelta(days=1)
        valuation_health["last_auto"] = last_auto_local
        valuation_health["last_manual"] = last_manual_local
        valuation_health["next_auto"] = next_auto
        if last_auto_local:
            age_h = (now_local - last_auto_local).total_seconds() / 3600
            if age_h <= 36:
                valuation_health.update(state="ok", label="Bewertung aktuell")
            else:
                valuation_health.update(state="warning", label="Bewertung möglicherweise veraltet")
    except Exception:
        app.logger.exception("Could not calculate valuation health")

    recent_price_activity = PriceActivity.query.join(CollectionItem).filter(
        CollectionItem.user_id == active_collection_user_id()
    ).order_by(PriceActivity.recorded_at.desc()).limit(10).all()
    hardware_owned = scoped_hardware_query().filter_by(status="owned").count()
    accessory_owned = scoped_accessory_query().with_entities(db.func.coalesce(db.func.sum(AccessoryItem.quantity), 0)).filter(AccessoryItem.status == "owned").scalar() or 0
    hardware_items_owned = scoped_hardware_query().filter_by(status="owned").all()
    hardware_value = sum((effective_hardware_value(x) or 0) for x in hardware_items_owned)
    hardware_valued_count = sum(1 for x in hardware_items_owned if effective_hardware_value(x) is not None)
    top_hardware_items = sorted([x for x in scoped_hardware_query().filter_by(status="owned").all() if effective_hardware_value(x) is not None], key=lambda x: effective_hardware_value(x) or 0, reverse=True)[:10]
    accessory_items_owned = scoped_accessory_query().filter_by(status="owned").all()
    accessory_value = sum(((effective_accessory_value(x) or 0) * (x.quantity or 1)) for x in accessory_items_owned if accessory_counts_in_total(x))
    accessory_valued_count = sum((x.quantity or 1) for x in accessory_items_owned if effective_accessory_value(x) is not None)
    top_accessory_items = sorted([x for x in accessory_items_owned if effective_accessory_value(x) is not None], key=lambda x: (effective_accessory_value(x) or 0) * (x.quantity or 1), reverse=True)[:10]
    complete_collection_value = total_value + hardware_value + accessory_value
    collector_rows = CollectorItem.query.filter_by(user_id=active_collection_user_id()).all()
    movement_period = request.args.get("movement", "latest")
    market_movement = collection_market_movement(
        movement_period, physical_owned_items, hardware_items_owned, accessory_items_owned, collector_rows,
    )
    # The complete Collector snapshot carries the logical collection owner.
    # CollectionValueSnapshot is the obsolete game-only history and has no
    # collection_user_id; filtering it caused /bewertungen to return HTTP 500.
    snapshots = CollectorValueSnapshot.query.filter_by(collection_user_id=active_collection_user_id()).order_by(CollectorValueSnapshot.recorded_at).all()
    total_change = None
    total_change_pct = None
    inventory_change = None
    comparison_value = None
    if movement_period == "latest":
        if len(snapshots) >= 2:
            comparison_value = float(snapshots[-2].total_value_eur)
            compared_total = float(snapshots[-1].total_value_eur)
            total_change = round(compared_total - comparison_value, 2)
    else:
        days = MARKET_MOVEMENT_PERIODS.get(movement_period, MARKET_MOVEMENT_PERIODS["latest"])["days"]
        cutoff = utc_now() - timedelta(days=days) if days else None
        baseline = next((row for row in reversed(snapshots) if row.recorded_at and row.recorded_at <= cutoff), None)
        if baseline:
            comparison_value = float(baseline.total_value_eur)
            total_change = round(float(complete_collection_value) - comparison_value, 2)
    if total_change is not None:
        total_change_pct = round(total_change / comparison_value * 100, 2) if comparison_value else 0.0
        inventory_change = round(total_change - market_movement["market_delta"], 2)
    standalone_count = Game.query.filter(Game.series_status == "standalone").count()
    unreviewed_series_count = Game.query.filter(Game.series_status == "unreviewed").count()
    series_mismatch_count = Game.query.filter(Game.franchise.isnot(None), Game.franchise != "", Game.series_status != "series").count()
    latest_run_summary = None
    latest_run = RevaluationRun.query.filter_by(collection_user_id=active_collection_user_id()).order_by(RevaluationRun.started_at.desc()).first()
    if latest_run:
        rows = PriceActivity.query.filter_by(revaluation_run_id=latest_run.id).all()
        latest_run_summary = {
            "run": latest_run,
            "up": sum(1 for r in rows if r.change_type == "up"),
            "down": sum(1 for r in rows if r.change_type == "down"),
            "same": sum(1 for r in rows if r.change_type == "same"),
            "new": sum(1 for r in rows if r.change_type == "new"),
        }

    # v0.9.3 documentation score: core catalog fields only, so it stays understandable.
    owned_games = [i.game for i in owned_items]
    quality_fields = 0; quality_have = 0
    for g in owned_games:
        checks = [g.cover_url, g.barcode, g.region, g.release_year, g.publisher, g.series_status and g.series_status != "unreviewed"]
        quality_fields += len(checks); quality_have += sum(1 for x in checks if x)
    data_quality_score = round(quality_have * 100 / max(quality_fields, 1))

    # v2.10.10: Games is the central valuation overview for the complete Collector.
    collector_module_labels = {"movies":"Filme", "tv":"TV-Serien", "books":"Bücher", "music":"Musik", "cards":"Sammelkarten"}
    collector_valuation_stats = []
    collector_modules_value = 0.0
    for key, label in collector_module_labels.items():
        rows = [row for row in collector_rows if row.category == key]
        count = sum(max(row.quantity or 1, 1) for row in rows)
        valued = sum(max(row.quantity or 1, 1) for row in rows if collector_effective_value(row) is not None)
        value = collector_rows_total_value(rows, authoritative_pokemon=(key == "cards"))
        collector_modules_value += value
        collector_valuation_stats.append({"key":key, "label":label, "count":count, "valued":valued, "value":value,
                                          "icon":{"movies":"🎬","tv":"📺","books":"📚","music":"💿","cards":"🃏"}[key],
                                          "url":url_for("collector_section", section=key),
                                          "image":next((row.cover_url for row in sorted(rows, key=lambda item:item.added_at or datetime.min, reverse=True) if row.cover_url), None)})
    configured_custom = custom_collection_categories(active_collection_user_id())
    configured_ids = {category["id"] for category in configured_custom}
    for category in configured_custom:
        rows = [row for row in collector_rows if row.category == "custom" and collector_metadata(row).get("custom_category") == category["id"]]
        count = sum(max(row.quantity or 1, 1) for row in rows)
        valued = sum(max(row.quantity or 1, 1) for row in rows if collector_effective_value(row) is not None)
        value = collector_rows_total_value(rows)
        collector_modules_value += value
        collector_valuation_stats.append({"key":f"custom-{category['id']}", "label":category["title"], "count":count, "valued":valued, "value":value,
                                          "icon":category["icon"], "url":url_for("collector_section", section="custom", custom_category=category["id"]),
                                          "image":next((row.cover_url for row in sorted(rows, key=lambda item:item.added_at or datetime.min, reverse=True) if row.cover_url), None)})
    unassigned_custom = [row for row in collector_rows if row.category == "custom" and collector_metadata(row).get("custom_category") not in configured_ids]
    if unassigned_custom or not configured_custom:
        count = sum(max(row.quantity or 1, 1) for row in unassigned_custom)
        valued = sum(max(row.quantity or 1, 1) for row in unassigned_custom if collector_effective_value(row) is not None)
        value = collector_rows_total_value(unassigned_custom)
        collector_modules_value += value
        collector_valuation_stats.append({"key":"custom", "label":"Weitere", "count":count, "valued":valued, "value":value,
                                          "icon":"📦", "url":url_for("collector_section", section="custom"),
                                          "image":next((row.cover_url for row in sorted(unassigned_custom, key=lambda item:item.added_at or datetime.min, reverse=True) if row.cover_url), None)})
    collector_complete_value = complete_collection_value + collector_modules_value

    # v2.10.11-r2: top-valued lists for every Collector module. Quantity is
    # included so the ranking reflects the actual collection value. TV rows are
    # aggregated by series where grouping metadata is available.
    top_collector_values = {}
    for key in ("movies", "books", "music", "cards"):
        ranked = []
        for row in collector_rows:
            if row.category != key or collector_effective_value(row) is None:
                continue
            qty = max(row.quantity or 1, 1)
            ranked.append({
                "title": row.title,
                "subtitle": row.edition or row.media_type or collector_module_labels.get(key, "Objekt"),
                "cover": row.cover_url,
                "url": url_for("collector_item_detail", item_id=row.id),
                "value": (collector_effective_value(row) or 0) * qty,
                "quantity": qty,
            })
        ranked.sort(key=lambda x: x["value"], reverse=True)
        top_collector_values[key] = ranked[:10]

    tv_groups = {}
    for row in collector_rows:
        if row.category != "tv" or collector_effective_value(row) is None:
            continue
        group_name, _ = infer_collector_group(row)
        group_name = group_name or row.title
        key = group_name.casefold()
        qty = max(row.quantity or 1, 1)
        slot = tv_groups.setdefault(key, {
            "title": group_name, "subtitle": "TV-Serie", "cover": row.cover_url,
            "url": url_for("collector_item_detail", item_id=row.id), "value": 0.0,
            "quantity": 0, "parts": 0,
        })
        slot["value"] += (collector_effective_value(row) or 0) * qty
        slot["quantity"] += qty
        slot["parts"] += 1
        if not slot.get("cover") and row.cover_url:
            slot["cover"] = row.cover_url
    top_tv_values = sorted(tv_groups.values(), key=lambda x: x["value"], reverse=True)[:10]
    for row in top_tv_values:
        row["subtitle"] = f"TV-Serie · {row['parts']} Eintrag" + ("e" if row["parts"] != 1 else "")

    # v2.10.11: newest entries across Games and every generic Collector module.
    recent_entries = []
    for item in owned_items:
        recent_entries.append({
            "added_at": item.added_at, "title": item.game.title,
            "subtitle": item.game.console.name if item.game.console else "Spiel",
            "kind": "Spiel", "icon": "🎮", "cover": item.game.cover_url,
            "url": url_for("game_detail", game_id=item.game.id),
            "value": effective_value(item),
        })
    recent_labels = {
        "movies": ("Film", "🎬"), "tv": ("Serie", "📺"), "books": ("Buch", "📚"),
        "music": ("Musik", "💿"), "cards": ("Sammelkarte", "🃏"), "custom": ("Sammlung", "📦"),
    }
    for row in collector_rows:
        label, icon = recent_labels.get(row.category, ("Objekt", "📦"))
        recent_entries.append({
            "added_at": row.added_at, "title": row.title,
            "subtitle": row.edition or row.media_type or label,
            "kind": label, "icon": icon, "cover": row.cover_url,
            "url": url_for("collector_item_detail", item_id=row.id),
            "value": collector_effective_value(row),
        })
    recent_entries.sort(key=lambda row: row["added_at"] or datetime.min, reverse=True)
    recent_entries = recent_entries[:8]

    dashboard_layout = dashboard_layout_for(current_user.id)
    dashboard_images = dashboard_watermarks(owned_items, hardware_items_owned, accessory_items_owned, collector_rows, wishlist_items)
    review_task_count = len(review_inbox_rows())
    insight_rows = collection_insights()[:6]
    return render_template("dashboard.html", owned=owned, physical_owned=physical_owned, digital_owned=digital_owned, wishlist=wishlist, total_value=total_value,
                           valued_count=valued_count, auto_valued_count=auto_valued_count, purchase_total=purchase_total,
                           console_count=console_count, catalog_count=catalog_count, recent=recent,
                           valuation_status_counts=valuation_status_counts, auto_missing_count=auto_missing_count,
                           no_value_count=no_value_count, console_stats=console_stats[:8],
                           top_value_items=top_value_items, price_changes=price_changes[:6], change_total=change_total,
                           series_stats=series_stats[:6], missing_cover_count=missing_cover_count,
                           incomplete_data_count=incomplete_data_count, high_priority_wishlist=high_priority_wishlist,
                           recent_activity=recent_activity, valuation_health=valuation_health,
                           recent_price_activity=recent_price_activity, latest_run_summary=latest_run_summary,
                           hardware_owned=hardware_owned, accessory_owned=accessory_owned, hardware_value=hardware_value,
                           top_hardware_items=top_hardware_items, hardware_valued_count=hardware_valued_count,
                           accessory_value=accessory_value, complete_collection_value=complete_collection_value,
                           accessory_valued_count=accessory_valued_count, top_accessory_items=top_accessory_items,
                           market_movement=market_movement, movement_periods=MARKET_MOVEMENT_PERIODS,
                           total_change=total_change, total_change_pct=total_change_pct,
                           inventory_change=inventory_change,
                           standalone_count=standalone_count, unreviewed_series_count=unreviewed_series_count,
                           series_mismatch_count=series_mismatch_count, data_quality_score=data_quality_score,
                           collector_valuation_stats=collector_valuation_stats, collector_complete_value=collector_complete_value,
                           top_collector_values=top_collector_values, top_tv_values=top_tv_values,
                           recent_entries=recent_entries, dashboard_layout=dashboard_layout,
                           dashboard_images=dashboard_images, review_task_count=review_task_count,
                           insight_rows=insight_rows)


@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) < 2 or len(password) < 8:
            flash("Benutzername mindestens 2 Zeichen, Passwort mindestens 8 Zeichen.", "danger")
        elif User.query.filter(db.func.lower(User.username) == username.lower()).first():
            flash("Dieser Benutzername ist bereits vergeben.", "warning")
        else:
            role = request.form.get("role", "editor") if request.form.get("role") in {"admin", "editor", "viewer"} else "editor"
            user = User(username=username, display_name=request.form.get("display_name", "").strip() or None, password_hash=generate_password_hash(password), is_admin=(role == "admin"), role=role, is_system=False)
            db.session.add(user); db.session.flush()
            initial_collection_id = request.form.get("collection_id", type=int)
            initial_space = db.session.get(CollectionSpace, initial_collection_id) if initial_collection_id else None
            if initial_space:
                initial_role = request.form.get("collection_role", "viewer")
                if initial_role not in {"viewer", "editor", "manager"}:
                    initial_role = "viewer"
                db.session.add(CollectionPermission(collection_id=initial_space.id, user_id=user.id, role=initial_role))
            log_activity("user_created", "user", user.id, f"Benutzer {username} wurde angelegt."); db.session.commit()
            flash(f"Benutzer {username} wurde angelegt.", "success")
        return redirect(url_for("admin_users"))
    users = User.query.filter_by(is_system=False).order_by(User.username).all()
    collection_spaces = CollectionSpace.query.order_by(CollectionSpace.name).all()
    permission_map = {(p.collection_id, p.user_id): p.role for p in CollectionPermission.query.all()}
    ebay = ebay_credentials()
    return render_template(
        "users.html", users=users, collection_spaces=collection_spaces, permission_map=permission_map,
        ebay_configured=bool(ebay["client_id"] and ebay["client_secret"]),
        ebay_client_id=ebay["client_id"], ebay_dev_id=ebay["dev_id"],
        ebay_marketplace=ebay["marketplace"], ebay_environment=ebay["environment"],
    )


@app.route("/admin/collections/create", methods=["POST"])
@admin_required
def admin_collection_create():
    name = " ".join((request.form.get("name") or "").split()).strip()
    if len(name) < 2:
        flash("Der Sammlungsname muss mindestens zwei Zeichen enthalten.", "danger")
        return redirect(url_for("admin_users") + "#collection-access")
    base_slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()).strip("-") or "sammlung"
    slug, suffix = base_slug[:100], 2
    while CollectionSpace.query.filter_by(slug=slug).first():
        slug = f"{base_slug[:94]}-{suffix}"
        suffix += 1
    owner = User(username=f"__bibo_collection_{secrets.token_hex(8)}", display_name=name,
                 password_hash=generate_password_hash(os.urandom(32).hex()), is_admin=False, role="viewer", is_system=True)
    db.session.add(owner); db.session.flush()
    space = CollectionSpace(name=name[:120], slug=slug, owner_user_id=owner.id)
    db.session.add(space); db.session.flush()
    db.session.add(CollectionPermission(collection_id=space.id, user_id=current_user.id, role="manager"))
    log_activity("collection_created", "collection_space", space.id, f"Sammlung {space.name} wurde angelegt.")
    db.session.commit()
    flash(f"Sammlung „{space.name}“ wurde angelegt.", "success")
    return redirect(url_for("admin_users") + "#collection-access")


@app.route("/admin/collections/<int:collection_id>/permissions", methods=["POST"])
@admin_required
def admin_collection_permissions(collection_id):
    space = db.get_or_404(CollectionSpace, collection_id)
    users = User.query.filter_by(is_system=False).all()
    allowed_roles = {"viewer", "editor", "manager"}
    for user in users:
        requested = (request.form.get(f"access_{user.id}") or "none").strip()
        permission = CollectionPermission.query.filter_by(collection_id=space.id, user_id=user.id).first()
        if requested in allowed_roles:
            if not permission:
                permission = CollectionPermission(collection_id=space.id, user_id=user.id)
                db.session.add(permission)
            permission.role = requested
        elif permission:
            db.session.delete(permission)
    if not CollectionPermission.query.filter_by(collection_id=space.id, role="manager").first() and not current_user.is_admin:
        db.session.rollback()
        flash("Mindestens ein Verwalter muss Zugriff auf die Sammlung behalten.", "danger")
        return redirect(url_for("admin_users") + "#collection-access")
    log_activity("collection_permissions_updated", "collection_space", space.id, f"Zugriffe für {space.name} aktualisiert.")
    db.session.commit()
    flash(f"Zugriffe für „{space.name}“ wurden gespeichert.", "success")
    return redirect(url_for("admin_users") + "#collection-access")


@app.route("/collection/access", methods=["GET", "POST"])
@collection_manager_required
def collection_access():
    space = active_collection_space()
    if not space:
        abort(404)
    # Privacy boundary: collection managers only see accounts that already have
    # access to this collection. New users enter this view only through a
    # collection-specific access request. System admins retain the global user
    # directory in /admin/users.
    permission_rows = (CollectionPermission.query
                       .filter_by(collection_id=space.id)
                       .order_by(CollectionPermission.id)
                       .all())
    users = [row.user for row in permission_rows if row.user and not row.user.is_system]
    permissions = {row.user_id: row for row in permission_rows}
    if request.method == "POST":
        for user in users:
            requested = (request.form.get(f"access_{user.id}") or "none").strip()
            permission = permissions.get(user.id)
            if requested in {"viewer", "editor", "manager"}:
                if not permission:
                    permission = CollectionPermission(collection_id=space.id, user_id=user.id)
                    db.session.add(permission)
                permission.role = requested
                permission.can_edit_items = request.form.get(f"edit_items_{user.id}") == "1"
                permission.can_manage_prices = request.form.get(f"manage_prices_{user.id}") == "1"
                permission.can_run_imports = request.form.get(f"run_imports_{user.id}") == "1"
                permission.can_manage_users = request.form.get(f"manage_users_{user.id}") == "1"
            elif permission and user.id != current_user.id:
                db.session.delete(permission)
        db.session.flush()
        managers = CollectionPermission.query.filter_by(collection_id=space.id, role="manager").all()
        if not managers or not any(row.can_manage_users is not False for row in managers):
            db.session.rollback()
            flash("Mindestens ein Verwalter muss die Rechteverwaltung behalten.", "danger")
            return redirect(url_for("collection_access"))
        log_activity("collection_permissions_updated", "collection_space", space.id, f"Feinrechte für {space.name} aktualisiert.")
        db.session.commit()
        flash("Benutzerrechte wurden gespeichert.", "success")
        return redirect(url_for("collection_access"))
    requests = (CollectionAccessRequest.query
                .filter_by(collection_id=space.id, status="pending")
                .order_by(CollectionAccessRequest.created_at.asc())
                .all())
    return render_template("collection_access.html", space=space, users=users, permissions=permissions, access_requests=requests)


@app.route("/collections/request-access", methods=["GET", "POST"])
@login_required
def collection_access_request():
    accessible_ids = {space.id for space in accessible_collection_spaces(current_user)}
    spaces = CollectionSpace.query.order_by(CollectionSpace.name).all()
    requestable = [space for space in spaces if space.id not in accessible_ids]
    existing = {row.collection_id: row for row in CollectionAccessRequest.query.filter_by(user_id=current_user.id).all()}
    if request.method == "POST":
        collection_id = request.form.get("collection_id", type=int)
        space = db.session.get(CollectionSpace, collection_id) if collection_id else None
        if not space or space.id in accessible_ids:
            flash("Für diese Sammlung ist keine Zugriffsanfrage erforderlich.", "warning")
            return redirect(url_for("collection_access_request"))
        role = (request.form.get("requested_role") or "viewer").strip()
        if role not in {"viewer", "editor"}:
            role = "viewer"
        row = CollectionAccessRequest.query.filter_by(collection_id=space.id, user_id=current_user.id).first()
        if not row:
            row = CollectionAccessRequest(collection_id=space.id, user_id=current_user.id)
            db.session.add(row)
        row.requested_role = role
        row.message = " ".join((request.form.get("message") or "").split())[:500] or None
        row.status = "pending"
        row.created_at = utc_now()
        row.decided_at = None
        row.decided_by_user_id = None
        db.session.commit()
        flash(f"Zugriff auf „{space.name}“ wurde angefragt.", "success")
        return redirect(url_for("collection_access_request"))
    return render_template("collection_access_request.html", spaces=requestable, requests=existing)


@app.route("/collection/access/requests/<int:request_id>/<decision>", methods=["POST"])
@collection_manager_required
def collection_access_request_decide(request_id, decision):
    space = active_collection_space()
    row = db.get_or_404(CollectionAccessRequest, request_id)
    if not space or row.collection_id != space.id or row.status != "pending":
        abort(404)
    if decision not in {"approve", "reject"}:
        abort(404)
    if decision == "approve":
        permission = CollectionPermission.query.filter_by(collection_id=space.id, user_id=row.user_id).first()
        if not permission:
            permission = CollectionPermission(collection_id=space.id, user_id=row.user_id)
            db.session.add(permission)
        permission.role = row.requested_role if row.requested_role in {"viewer", "editor"} else "viewer"
        row.status = "approved"
        flash(f"Zugriff für {row.user.display_name or row.user.username} wurde freigegeben.", "success")
    else:
        row.status = "rejected"
        flash("Zugriffsanfrage wurde abgelehnt.", "success")
    row.decided_at = utc_now()
    row.decided_by_user_id = current_user.id
    db.session.commit()
    return redirect(url_for("collection_access"))


@app.route("/admin/integrations/ebay", methods=["POST"])
@admin_required
def admin_ebay_settings():
    client_id = request.form.get("client_id", "").strip()
    client_secret = request.form.get("client_secret", "").strip()
    dev_id = request.form.get("dev_id", "").strip()
    marketplace = request.form.get("marketplace", "EBAY_DE").strip()
    environment = request.form.get("environment", "production").strip()
    if marketplace not in {"EBAY_DE", "EBAY_AT", "EBAY_CH"}:
        marketplace = "EBAY_DE"
    if environment not in {"production", "sandbox"}:
        environment = "production"
    return_endpoint = "account" if request.form.get("return_to") == "account" else "admin_users"

    if request.form.get("remove") == "1":
        for key in ("ebay_client_id", "ebay_client_secret", "ebay_dev_id", "ebay_marketplace", "ebay_environment"):
            row = db.session.get(AppSetting, key)
            if row:
                db.session.delete(row)
        log_activity("integration_removed", "integration", None, "eBay-Zugangsdaten wurden entfernt.")
        db.session.commit()
        flash("eBay-Zugangsdaten wurden entfernt.", "success")
        return redirect(url_for(return_endpoint) + "#ebay-integration")

    current = ebay_credentials()
    client_id = client_id or current["client_id"]
    client_secret = client_secret or current["client_secret"]
    if not client_id or not client_secret:
        flash("Bitte Client-ID und Client-Secret vollständig eintragen.", "danger")
        return redirect(url_for(return_endpoint) + "#ebay-integration")

    app_setting_set("ebay_client_id", client_id)
    app_setting_set("ebay_client_secret", client_secret, secret=True)
    app_setting_set("ebay_dev_id", dev_id)
    app_setting_set("ebay_marketplace", marketplace)
    app_setting_set("ebay_environment", environment)
    _EBAY_TOKEN_CACHE.update(token=None, expires_at=0.0, client_id=None)
    log_activity("integration_updated", "integration", None, "eBay-Zugangsdaten wurden aktualisiert.")
    db.session.commit()

    if request.form.get("action") == "test":
        ok, message = ebay_connection_test()
        flash(message, "success" if ok else "danger")
    else:
        flash("eBay-Zugangsdaten wurden sicher gespeichert.", "success")
    return redirect(url_for(return_endpoint) + "#ebay-integration")


@app.route("/admin/integrations/tmdb", methods=["POST"])
@admin_required
def admin_tmdb_settings():
    return_endpoint = "account"
    if request.form.get("remove") == "1":
        for key in ("tmdb_api_key", "tmdb_read_token"):
            row = db.session.get(AppSetting, key)
            if row:
                db.session.delete(row)
        log_activity("integration_removed", "integration", None, "TMDB-Zugangsdaten wurden entfernt.")
        db.session.commit()
        flash("TMDB-Zugangsdaten wurden entfernt.", "success")
        return redirect(url_for(return_endpoint) + "#tmdb-integration")

    current = tmdb_credentials()
    api_key = request.form.get("api_key", "").strip() or current["api_key"]
    token = request.form.get("read_token", "").strip() or current["token"]
    if not api_key and not token:
        flash("Bitte mindestens API-Schlüssel oder Read Access Token eintragen.", "danger")
        return redirect(url_for(return_endpoint) + "#tmdb-integration")

    if api_key:
        app_setting_set("tmdb_api_key", api_key, secret=True)
    if token:
        app_setting_set("tmdb_read_token", token, secret=True)
    log_activity("integration_updated", "integration", None, "TMDB-Zugangsdaten wurden aktualisiert.")
    db.session.commit()

    if request.form.get("action") == "test":
        ok, message = tmdb_connection_test()
        flash(message, "success" if ok else "danger")
    else:
        flash("TMDB-Zugangsdaten wurden sicher gespeichert.", "success")
    return redirect(url_for(return_endpoint) + "#tmdb-integration")


@app.route("/admin/users/<int:user_id>/profile", methods=["POST"])
@admin_required
def admin_user_profile(user_id):
    user = db.get_or_404(User, user_id)
    if user.is_system:
        abort(404)
    user.display_name = request.form.get("display_name", "").strip() or None
    role = request.form.get("role", "editor")
    if role not in {"admin", "editor", "viewer"}:
        role = "editor"
    if user.id == current_user.id:
        role = "admin"
    user.role = role
    user.is_admin = role == "admin"
    log_activity("user_updated", "user", user.id, f"Profil für {user.username} aktualisiert.")
    db.session.commit()
    flash(f"Profil für {user.username} aktualisiert.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/password", methods=["POST"])
@admin_required
def admin_user_password(user_id):
    user = db.get_or_404(User, user_id)
    if user.is_system:
        abort(404)
    password = request.form.get("password", "")
    if len(password) < 8:
        flash("Das neue Passwort muss mindestens 8 Zeichen lang sein.", "danger")
    else:
        user.password_hash = generate_password_hash(password); db.session.commit(); flash(f"Passwort für {user.username} geändert.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_user_delete(user_id):
    user = db.get_or_404(User, user_id)
    if user.is_system:
        abort(404)
    if user.id == current_user.id:
        flash("Du kannst dein eigenes angemeldetes Konto nicht löschen.", "danger")
    else:
        copies = CollectionItem.query.filter_by(user_id=user.id).count()
        if copies and request.form.get("confirm") != "DELETE":
            flash(f"{user.username} besitzt {copies} Sammlungseinträge. Gib DELETE zur Bestätigung ein.", "danger")
        else:
            for item in CollectionItem.query.filter_by(user_id=user.id).all():
                db.session.delete(item)
            db.session.flush()
            db.session.delete(user); db.session.commit(); flash(f"Benutzer {user.username} wurde gelöscht.", "success")
    return redirect(url_for("admin_users"))


@app.route("/consoles", methods=["GET", "POST"])
@login_required
def consoles():
    if request.method == "POST":
        raw_name = request.form.get("name", "").strip()
        name = canonical_console_name(raw_name) if raw_name else ""
        if not name:
            flash("Bitte einen Konsolennamen eingeben.", "danger")
        elif Console.query.filter(db.func.lower(Console.name) == name.lower()).first():
            if raw_name and raw_name != name:
                flash(f"{raw_name} wird als {name} geführt; diese Plattform existiert bereits.", "warning")
            else:
                flash("Diese Konsole existiert bereits.", "warning")
        else:
            db.session.add(Console(name=name, manufacturer=request.form.get("manufacturer", "").strip(), generation=request.form.get("generation", "").strip()))
            db.session.commit()
            flash("Konsole hinzugefügt.", "success")
        return redirect(url_for("consoles"))
    all_consoles = Console.query.order_by(Console.manufacturer, Console.name).all()
    alias_rows = []
    for c in all_consoles:
        canonical = canonical_console_name(c.name)
        if canonical.casefold() != c.name.casefold():
            alias_rows.append((c, canonical))
    return render_template("consoles.html", consoles=all_consoles, alias_rows=alias_rows)


@app.route("/consoles/<int:console_id>/edit", methods=["GET", "POST"])
@admin_required
def console_edit(console_id):
    console = db.get_or_404(Console, console_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Bitte einen Konsolennamen eingeben.", "danger")
        else:
            console.name = name
            console.manufacturer = request.form.get("manufacturer", "").strip() or None
            console.generation = request.form.get("generation", "").strip() or None
            try:
                db.session.commit()
                flash("Konsole aktualisiert. Zugeordnete Spiele bleiben erhalten.", "success")
                return redirect(url_for("consoles"))
            except Exception:
                db.session.rollback()
                flash("Der Konsolenname ist bereits vergeben.", "danger")
    targets = Console.query.filter(Console.id != console.id).order_by(Console.name).all()
    return render_template("console_edit.html", console=console, targets=targets)


@app.route("/consoles/<int:console_id>/merge", methods=["POST"])
@admin_required
def console_merge(console_id):
    source = db.get_or_404(Console, console_id)
    target_id = request.form.get("target_console_id", type=int)
    if not target_id:
        flash("Bitte eine Zielkonsole auswählen.", "danger")
        return redirect(url_for("console_edit", console_id=source.id))
    target = db.get_or_404(Console, target_id)
    if target.id == source.id:
        flash("Quell- und Zielkonsole dürfen nicht identisch sein.", "danger")
        return redirect(url_for("console_edit", console_id=source.id))
    conflicts = _console_merge_conflicts(source, target)
    if conflicts:
        preview = ", ".join(g.title for g, _ in conflicts[:5])
        more = f" (+{len(conflicts)-5} weitere)" if len(conflicts) > 5 else ""
        flash(
            f"Zusammenführen abgebrochen: {len(conflicts)} Katalogvarianten existieren bereits auf {target.name}: {preview}{more}. "
            "Bitte diese Spiele zuerst einzeln prüfen.",
            "danger",
        )
        return redirect(url_for("console_edit", console_id=source.id))
    moved = Game.query.filter_by(console_id=source.id).count()
    source_name, target_name = source.name, target.name
    ok, _ = merge_console_into(source, target)
    if not ok:
        db.session.rollback()
        flash("Die Plattformen konnten wegen Katalogkonflikten nicht zusammengeführt werden.", "danger")
        return redirect(url_for("console_edit", console_id=console_id))
    log_activity("console_merged", "console", target.id, f"{source_name} -> {target_name}; {moved} Spiele verschoben.")
    db.session.commit()
    flash(f"{source_name} wurde mit {target_name} zusammengeführt. {moved} Spiele wurden verschoben.", "success")
    return redirect(url_for("consoles"))


@app.route("/consoles/<int:console_id>/delete", methods=["POST"])
@admin_required
def console_delete(console_id):
    console = db.get_or_404(Console, console_id)
    game_count = Game.query.filter_by(console_id=console.id).count()
    target_id = request.form.get("target_console_id", type=int)
    if game_count and not target_id:
        flash(f"{game_count} Spiele sind dieser Konsole zugeordnet. Wähle zuerst eine Zielkonsole zum Verschieben.", "danger")
        return redirect(url_for("console_edit", console_id=console.id))
    if target_id:
        target = db.get_or_404(Console, target_id)
        if target.id == console.id:
            flash("Zielkonsole darf nicht identisch sein.", "danger")
            return redirect(url_for("console_edit", console_id=console.id))
        Game.query.filter_by(console_id=console.id).update({Game.console_id: target.id}, synchronize_session=False)
    name = console.name
    db.session.delete(console)
    db.session.commit()
    flash(f"Konsole {name} gelöscht" + ("; Spiele wurden verschoben." if game_count else "."), "success")
    return redirect(url_for("consoles"))


@app.route("/games", methods=["GET", "POST"])
@login_required
def games():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        console_id = request.form.get("console_id", type=int)
        if not title or not console_id:
            flash("Titel und Konsole sind Pflichtfelder.", "danger")
        else:
            selected_console = db.session.get(Console, console_id)
            if normalized_platform(selected_console.name if selected_console else "") in NON_PHYSICAL_ONLY or normalize_series_title(title) in NON_PHYSICAL_TITLES:
                flash("Bibo nimmt ausschließlich physisch veröffentlichte Spiele auf. Mobile- und reine Online-Titel sind ausgeschlossen.", "warning")
                return redirect(url_for("games"))
            incoming_barcode = clean_barcode(request.form.get("barcode"))
            conflicts = barcode_conflicts(incoming_barcode)
            if conflicts and request.form.get("confirm_barcode_duplicate") != "1":
                flash(f"EAN/UPC {incoming_barcode} ist bereits bei „{conflicts[0].title}“ hinterlegt. Nutze bei derselben Ausgabe „Weiteres Exemplar“.", "warning")
                return redirect(url_for("barcode_lookup", barcode=incoming_barcode))
            year_raw = request.form.get("release_year", "").strip()
            game = Game(
                title=title, console_id=console_id,
                region=request.form.get("region", "PAL").strip() or "PAL",
                release_year=int(year_raw) if year_raw.isdigit() else None,
                publisher=request.form.get("publisher", "").strip(),
                developer=request.form.get("developer", "").strip(),
                genre=request.form.get("genre", "").strip(),
                edition=request.form.get("edition", "Standard").strip() or "Standard",
                franchise=request.form.get("franchise", "").strip() or None,
                franchise_source="manual" if request.form.get("franchise", "").strip() else None,
                barcode=incoming_barcode,
                product_code=normalize_product_code(request.form.get("product_code")),
                cover_url=archived_or_original_image(request.form.get("cover_url")),
                physical_status="physical_addon" if title_requires_physical_addon_proof(title) else "physical",
            )
            if not game.franchise:
                detected = infer_franchise_name(game.title)
                if detected:
                    game.franchise = detected
                    game.franchise_source = "auto-rule"
            game.series_status = "series" if game.franchise else "unreviewed"
            db.session.add(game)
            try:
                db.session.flush()
                log_activity("game_created", "game", game.id, f"Katalogtitel „{game.title}“ angelegt.")
                db.session.commit()
                flash("Spiel zum Katalog hinzugefügt.", "success")
            except Exception:
                db.session.rollback()
                flash("Diese Spielvariante ist bereits vorhanden.", "warning")
        return redirect(url_for("games"))

    q = request.args.get("q", "").strip()
    console_id = request.args.get("console_id", type=int)
    franchise = request.args.get("franchise", "").strip()
    owned_filter = request.args.get("owned", "").strip()
    query = Game.query.filter(Game.physical_status != "excluded")
    if q:
        query = query.filter(db.or_(Game.title.ilike(f"%{q}%"), Game.barcode.ilike(f"%{q}%"), Game.product_code.ilike(f"%{q}%")))
    if console_id:
        query = query.filter_by(console_id=console_id)
    if franchise:
        query = query.filter(Game.franchise == franchise)
    owner_id = active_collection_user_id()
    if owned_filter == "owned":
        query = query.filter(Game.collections.any(db.and_(CollectionItem.user_id == owner_id, CollectionItem.status == "owned")))
    elif owned_filter == "missing":
        query = query.filter(~Game.collections.any(db.and_(CollectionItem.user_id == owner_id, CollectionItem.status == "owned")))
    franchises = [r[0] for r in db.session.query(Game.franchise).filter(Game.franchise.isnot(None), Game.franchise != "").distinct().order_by(Game.franchise).all()]
    return render_template("games.html", games=query.order_by(Game.title).all(), consoles=Console.query.order_by(Console.name).all(),
                           q=q, selected_console=console_id, selected_franchise=franchise, selected_owned=owned_filter, franchises=franchises)


@app.route("/games/search", methods=["GET"])
@login_required
def game_catalog_search():
    """Search the local catalog first, then external metadata without requiring an EAN/UPC."""
    source_ean = clean_barcode(request.args.get("source_ean"))
    q = request.args.get("q", "").strip()
    console_id = request.args.get("console_id", type=int)
    consoles = Console.query.order_by(Console.name).all()
    selected_console = db.session.get(Console, console_id) if console_id else None
    local_results = []
    external_results = []
    rawg_status = None
    if q:
        local_query = Game.query.filter(
            db.or_(Game.title.ilike(f"%{q}%"), Game.product_code.ilike(f"%{q}%"), Game.barcode.ilike(f"%{q}%"))
        )
        if console_id:
            local_query = local_query.filter(Game.console_id == console_id)
        local_results = [g for g in local_query.order_by(Game.title).limit(30).all() if game_is_physical_candidate(g)]
        # External lookup is supplemental. It remains useful even when local matches exist,
        # because the user may be looking for a different edition/platform variant.
        external_results, rawg_status = _metadata_candidates(q, selected_console.name if selected_console else None, limit=18)
        local_keys = {(g.title.casefold(), g.console_id, (g.region or "PAL").casefold(), (g.edition or "Standard").casefold()) for g in local_results}
        filtered = []
        for row in external_results:
            row_platforms = row.get("platforms") or [row.get("platform")]
            row_platforms = {normalized_platform(p) for p in row_platforms if p}
            if (row_platforms and row_platforms.issubset(NON_PHYSICAL_ONLY)) or normalize_series_title(row.get("name")) in NON_PHYSICAL_TITLES or title_requires_physical_addon_proof(row.get("name")):
                continue
            row["already_local"] = any(
                g.title.casefold() == str(row.get("name") or "").casefold()
                and (not row.get("platform") or canonical_console_name(row.get("platform")) == canonical_console_name(g.console.name))
                for g in local_results
            )
            filtered.append(row)
        external_results = filtered
    return render_template(
        "game_catalog_search.html",
        q=q,
        consoles=consoles,
        selected_console=selected_console,
        local_results=local_results,
        external_results=external_results,
        rawg_status=rawg_status,
        source_ean=source_ean,
    )


@app.route("/games/<int:game_id>/edit", methods=["GET", "POST"])
@login_required
def game_edit(game_id):
    game = db.get_or_404(Game, game_id)
    return_to = safe_collection_return_to(request.values.get("return_to", "")) or safe_collection_return_to(session.get("collection_return_to", ""))
    ean_flow = request.values.get("ean_flow") == "1"
    retro_flow = request.values.get("retro_flow") == "1"
    if request.method == "POST":
        if not request.form.get("title", "").strip() or not request.form.get("console_id", type=int):
            flash("Titel und Konsole sind Pflichtfelder.", "danger")
        else:
            proposed_barcode = clean_barcode(request.form.get("barcode"))
            conflicts = barcode_conflicts(proposed_barcode, game.id)
            if conflicts and request.form.get("confirm_barcode_duplicate") != "1":
                flash("EAN/UPC ist bereits einem anderen Katalogtitel zugeordnet. Bitte Konflikt prüfen oder bewusst bestätigen.", "warning")
                return render_template("game_edit.html", game=game, consoles=Console.query.order_by(Console.name).all(), barcode_conflicts=conflicts, return_to=return_to, ean_flow=ean_flow, retro_flow=retro_flow)
            apply_game_form(game)
            try:
                log_activity("game_updated", "game", game.id, f"Katalogtitel „{game.title}“ bearbeitet.")
                db.session.commit()
                if request.form.get("save_action") == "identify":
                    flash("Katalogeintrag gespeichert. Du kannst das Spiel jetzt identifizieren.", "success")
                    return redirect(url_for("game_identify", game_id=game.id, return_edit=1, return_to=return_to))
                flash("Katalogeintrag aktualisiert.", "success")
                if return_to:
                    return redirect(return_to)
                return redirect(url_for("game_detail", game_id=game.id))
            except Exception as exc:
                db.session.rollback()
                app.logger.warning("Game edit failed: %s", exc)
                flash("Änderung konnte nicht gespeichert werden. Prüfe, ob diese Variante bereits existiert.", "danger")
    return render_template("game_edit.html", game=game, consoles=Console.query.order_by(Console.name).all(), return_to=return_to, ean_flow=ean_flow, retro_flow=retro_flow)



def _metadata_candidates(query, console_name=None, limit=18):
    """Combine the configured metadata source with the keyless product fallback."""
    rows = []
    rawg_rows, rawg_status = rawg_game_search(query, console_name, limit=12)
    rows.extend(rawg_rows)
    for row in upcitemdb_title_search(f"{query} {console_name or ''}".strip(), limit=8):
        # Product search is especially useful for actual box-art photos.
        rows.append(row)
    seen = set()
    unique = []
    for row in rows:
        key = (str(row.get("source") or ""), str(row.get("source_id") or ""), str(row.get("cover_url") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
        if len(unique) >= limit:
            break
    return unique, rawg_status


def _provider_candidate(source, source_id):
    source = (source or "").strip()
    source_id = (source_id or "").strip()
    if source == "eBay":
        return ebay_item(source_id)
    if source == "RAWG":
        detail = rawg_game_detail(source_id)
        if not detail:
            return None
        return {
            "name": detail.get("name") or "",
            "year": detail.get("release_year") or "",
            "publisher": detail.get("publisher") or "",
            "developer": detail.get("developer") or "",
            "genre": detail.get("genre") or "",
            "cover_url": detail.get("cover_url") or "",
            "source": "RAWG", "source_id": source_id,
        }
    if source in {"UPCitemdb Search", "UPCitemdb"} and source_id:
        rows = lookup_upcitemdb(source_id)
        if rows:
            row = rows[0]
            return {
                "name": row.get("name") or "", "year": "",
                "publisher": row.get("publisher") or "", "developer": "",
                "genre": row.get("category") or "", "cover_url": row.get("cover_url") or "",
                "source": "UPCitemdb", "source_id": source_id,
            }
    return None


def _download_catalog_cover(url, game_id):
    """Persist a provider-selected image locally so catalog covers do not depend on hotlinks."""
    url = str(url or "").strip()
    if not url.startswith("https://"):
        return None
    req = Request(url, headers={"User-Agent": f"GameCollector/{APP_VERSION}"})
    try:
        with urlopen(req, timeout=10) as response:
            ctype = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
            ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(ctype)
            if not ext:
                return None
            data = response.read(8 * 1024 * 1024 + 1)
            if not data or len(data) > 8 * 1024 * 1024:
                return None
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    upload_dir = Path(app.root_path) / "static" / "uploads" / "covers"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"game-{game_id}-{int(utc_now().timestamp())}{ext}"
    (upload_dir / filename).write_bytes(data)
    return f"/static/uploads/covers/{filename}"


@app.route("/games/<int:game_id>/identify", methods=["GET", "POST"])
@login_required
def game_identify(game_id):
    game = db.get_or_404(Game, game_id)
    return_edit = request.values.get("return_edit") == "1"
    return_to = safe_collection_return_to(request.values.get("return_to", ""))
    if request.method == "POST":
        candidate = _provider_candidate(request.form.get("source"), request.form.get("source_id"))
        if not candidate:
            flash("Der gewählte Metadaten-Treffer konnte nicht mehr geladen werden.", "danger")
            return redirect(url_for("game_identify", game_id=game.id, return_edit=1 if return_edit else None, return_to=return_to))
        fields = set(request.form.getlist("fields"))
        # Keep the local/display title independent from the provider title.
        # RAWG often exposes only the English title, while collectors may want
        # the German/regional title in their catalog.  The identify dialog can
        # therefore explicitly provide a preferred local title.
        if "title" in fields:
            preferred_title = request.form.get("preferred_title", "").strip()
            if preferred_title:
                game.title = preferred_title
            elif candidate.get("name"):
                game.title = candidate["name"]
        if "release_year" in fields and str(candidate.get("year") or "").isdigit():
            game.release_year = int(candidate["year"])
        for field in ("publisher", "developer", "genre"):
            if field in fields and candidate.get(field):
                setattr(game, field, candidate[field])
        if "cover" in fields and candidate.get("cover_url"):
            local_cover = _download_catalog_cover(candidate["cover_url"], game.id)
            game.cover_url = local_cover or archived_or_original_image(candidate["cover_url"])
        if "external" in fields:
            # Provider IDs are metadata references, not physical-edition identifiers.
            # RAWG may intentionally group Diamond/Pearl, X/Y etc. into one record.
            game.external_source = candidate.get("source") or None
            game.external_id = candidate.get("source_id") or None
        if "franchise" in fields:
            detected = infer_franchise_name(game.title)
            if detected:
                game.franchise = detected
                game.franchise_source = "auto-rule"
                game.series_status = "series"
        try:
            log_activity("game_identified", "game", game.id, f"Katalogtitel „{game.title}“ identifiziert ({candidate.get('source')}).")
            db.session.commit()
            flash("Metadaten übernommen. Deine Exemplar-, Kauf- und Sammlungsdaten wurden nicht verändert.", "success")
            if return_edit:
                return redirect(url_for("game_edit", game_id=game.id, return_to=return_to))
            return redirect(url_for("game_detail", game_id=game.id, return_to=return_to))
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Identify apply failed: %s", exc)
            flash("Die Metadaten konnten nicht übernommen werden. Möglicherweise würde dadurch eine bereits vorhandene Spielvariante entstehen.", "danger")
            return redirect(url_for("game_identify", game_id=game.id, return_edit=1 if return_edit else None, return_to=return_to))

    q = request.args.get("q", "").strip() or game.title
    results, rawg_status = _metadata_candidates(q, game.console.name)
    for row in results:
        source = str(row.get("source") or "")
        source_id = str(row.get("source_id") or "")
        row["existing_game"] = Game.query.filter(Game.id != game.id, Game.console_id == game.console_id, Game.external_source == source, Game.external_id == source_id).first() if source_id else None
        if row.get("source") == "RAWG" and "platform_match" in row:
            row["platform_exact"] = bool(row.get("platform_match"))
        else:
            row["platform_exact"] = not row.get("platform") or canonical_console_name(row.get("platform")) == canonical_console_name(game.console.name)
    return render_template("game_identify.html", game=game, q=q, results=results, rawg_status=rawg_status,
                           return_edit=return_edit, return_to=return_to)


@app.route("/games/<int:game_id>/cover-search", methods=["GET", "POST"])
@login_required
def game_cover_search(game_id):
    game = db.get_or_404(Game, game_id)
    if request.method == "POST":
        if game.cover_url and request.form.get("confirm_replace") != "1":
            flash("Bitte bestätige, dass das vorhandene Cover ersetzt werden soll.", "warning")
            return redirect(url_for("game_cover_search", game_id=game.id, q=request.form.get("q"), region=request.form.get("region")))
        candidate = _provider_candidate(request.form.get("source"), request.form.get("source_id"))
        if not candidate or not candidate.get("cover_url"):
            flash("Dieses Cover konnte nicht geladen werden.", "danger")
            return redirect(url_for("game_cover_search", game_id=game.id))
        local_cover = _download_catalog_cover(candidate["cover_url"], game.id)
        if not local_cover:
            flash("Das Bild konnte nicht lokal gespeichert werden.", "danger")
            return redirect(url_for("game_cover_search", game_id=game.id))
        game.cover_url = local_cover
        log_activity("cover_changed", "game", game.id, f"Cover für „{game.title}“ über {candidate.get('source')} ausgewählt.")
        db.session.commit()
        flash("Cover ausgewählt und lokal gespeichert.", "success")
        return redirect(url_for("game_detail", game_id=game.id))

    q = request.args.get("q", "").strip() or game.title
    region_hint = request.args.get("region", "").strip()
    search_q = f"{q} {region_hint}".strip() if region_hint else q
    results, rawg_status = _metadata_candidates(search_q, game.console.name, limit=20)
    ebay_cfg = ebay_credentials()
    if ebay_cfg.get("client_id") and ebay_cfg.get("client_secret"):
        ebay_rows, _ = ebay_search_items(f"{search_q} {game.console.name}", limit=24)
        for row in ebay_rows:
            if row.get("cover_url"):
                results.append(row)
    results = [row for row in results if row.get("cover_url")]
    seen_urls = set()
    results = [row for row in results if not (row["cover_url"] in seen_urls or seen_urls.add(row["cover_url"]))]
    return render_template("cover_search.html", game=game, q=q, region_hint=region_hint, results=results, rawg_status=rawg_status)


@app.route("/games/<int:game_id>/delete", methods=["POST"])
@admin_required
def game_delete(game_id):
    game = db.get_or_404(Game, game_id)
    if game.collections and request.form.get("delete_collection") != "1":
        flash("Dieses Spiel ist in deiner Sammlung. Bestätige ausdrücklich, dass auch die Kopie gelöscht werden soll.", "danger")
        return redirect(url_for("game_edit", game_id=game.id, confirm_delete=1))
    title = game.title
    game_id_value = game.id
    log_activity("game_deleted", "game", game_id_value, f"Katalogtitel „{title}“ gelöscht.")
    db.session.delete(game)
    db.session.commit()
    flash(f"{title} wurde aus dem Katalog gelöscht.", "success")
    return redirect(url_for("games"))


@app.route("/games/<int:game_id>")
@login_required
def game_detail(game_id):
    game = db.get_or_404(Game, game_id)
    reviewable = CollectionItem.query.filter_by(user_id=active_collection_user_id(), game_id=game.id, status="owned").first() is not None
    return_to = safe_collection_return_to(request.args.get("return_to", "")) or safe_collection_return_to(session.get("collection_return_to", ""))
    historical = None; historical_status = None
    if request.args.get("historical") == "1":
        historical, historical_status = retrovideospiele_historical_lookup(game)
        if historical:
            owned_copy = collection_for(game)
            current_value = effective_value(owned_copy) if owned_copy else None
            reference = historical.get("boxed") if owned_copy and owned_copy.box_present else historical.get("loose")
            historical["current_value"] = current_value
            historical["reference_value"] = reference
            historical["delta"] = round(current_value - reference, 2) if current_value is not None and reference is not None else None
    return render_template("game_detail.html", game=game, barcode_state=barcode_status(game), return_to=return_to,
                           historical=historical, historical_status=historical_status,
                           personal_review=_personal_review("game", game.id),
                           review_dimensions=REVIEW_DIMENSIONS["games"], review_source_kind="game", review_source_id=game.id,
                           reviewable=reviewable)


@app.route("/games/<int:game_id>/cover-asset")
@login_required
def game_cover_asset(game_id):
    """Authenticated cover target for the blurred collection-list backdrop."""
    game = db.get_or_404(Game, game_id)
    if not game.cover_url:
        abort(404)
    return redirect(game.cover_url)


def safe_collection_return_to(value):
    """Accept only internal collection/catalog URLs as post-edit return targets."""
    value = str(value or "").strip()
    if not value:
        return None
    target = urlsplit(value)
    allowed = {url_for("collection"), url_for("games")}
    if target.scheme or target.netloc or target.path not in allowed:
        return None
    return target.path + (f"?{target.query}" if target.query else "")


@app.route("/collection/configure/<int:game_id>", methods=["GET", "POST"])
@login_required
def collection_configure(game_id):
    game = db.get_or_404(Game, game_id)
    return_to = safe_collection_return_to(request.values.get("return_to", "")) or safe_collection_return_to(session.get("collection_return_to", ""))
    ean_flow = request.values.get("ean_flow") == "1"
    retro_flow = request.values.get("retro_flow") == "1"
    item_id = request.args.get("item_id", type=int) or request.form.get("item_id", type=int)
    new_copy = request.args.get("new_copy") == "1"
    item = None
    if item_id:
        item = db.get_or_404(CollectionItem, item_id)
        if item.game_id != game.id or item.user_id != active_collection_user_id():
            abort(403)
    elif not new_copy:
        item = collection_for(game)
    if request.method == "POST":
        is_new = item is None
        item = item or CollectionItem(game_id=game.id, user_id=active_collection_user_id())

        # Hotfix1: keep manual estimates reliable when an existing copy is edited.
        # Capture the raw value before applying the rest of the form and explicitly
        # write the parsed value back to the persistent object. This also makes the
        # edit path behave exactly like creation for German decimal notation.
        errors = apply_collection_form(item)
        if errors:
            db.session.rollback()
            for error in errors:
                flash(error, "danger")
            return render_template(
                "collection_configure.html", game=game, item=item, copies=collection_items_for(game),
                pricecharting_enabled=bool(os.environ.get("PRICECHARTING_TOKEN", "").strip()),
                new_import=request.args.get("new") == "1", new_copy=new_copy, return_to=return_to, ean_flow=ean_flow, retro_flow=retro_flow,
            ), 400

        if is_new:
            db.session.add(item)
            db.session.flush()
        for slot, field in (("front", "photo_front"), ("back", "photo_back"), ("media", "photo_media")):
            saved = _save_copy_photo(request.files.get(f"photo_{slot}"), item, slot)
            if saved:
                setattr(item, field, saved)
        if is_new:
            log_activity("copy_added", "collection_item", item.id, f"{game.title}: weiteres Exemplar zur Sammlung hinzugefügt.", {"game_id": game.id})
        else:
            log_activity("copy_updated", "collection_item", item.id, f"{game.title}: Exemplar #{item.id} bearbeitet.", {"game_id": game.id})
        # Flush the edited copy first; the collection snapshot must see the new
        # manual estimate instead of the previous database value.
        db.session.flush()
        if item.status == "owned":
            collection_total_value_snapshot()
        db.session.commit()
        if item.ownership_format == "digital":
            flash("Digitales Exemplar gespeichert. Physische Zustands- und Marktwertangaben werden nicht berücksichtigt.", "success")
        elif item.estimated_value is not None:
            flash(f"Exemplar gespeichert · eigener Schätzwert: {item.estimated_value:.2f} €", "success")
        else:
            flash("Exemplar in der gemeinsamen Sammlung gespeichert.", "success")
        if request.form.get("save_action") == "stay":
            return redirect(url_for("collection_configure", game_id=game.id, item_id=item.id, return_to=return_to, ean_flow=1 if ean_flow else None, retro_flow=1 if retro_flow else None))
        if ean_flow or retro_flow:
            flash("Exemplar erfasst. Prüfe jetzt die Spieldaten.", "success")
            return redirect(url_for("game_edit", game_id=game.id, return_to=return_to, ean_flow=1 if ean_flow else None, retro_flow=1 if retro_flow else None))
        return redirect(return_to or url_for("game_detail", game_id=game.id))
    return render_template(
        "collection_configure.html", game=game, item=item, copies=collection_items_for(game),
        pricecharting_enabled=bool(os.environ.get("PRICECHARTING_TOKEN", "").strip()),
        new_import=request.args.get("new") == "1", new_copy=new_copy, return_to=return_to, ean_flow=ean_flow, retro_flow=retro_flow,
    )


@app.route("/collection/market-value/<int:game_id>", methods=["POST"])
@login_required
def collection_market_value(game_id):
    game = db.get_or_404(Game, game_id)
    prices, status = pricecharting_lookup(game)
    if status == "missing_token":
        flash("PriceCharting ist noch nicht konfiguriert. Hinterlege PRICECHARTING_TOKEN in der .env.", "warning")
        return redirect(url_for("collection_configure", game_id=game.id))
    if not prices:
        flash("PriceCharting hat für diese Variante keinen eindeutigen Treffer geliefert.", "warning")
        return redirect(url_for("collection_configure", game_id=game.id))
    price_kind = request.form.get("price_kind", "loose")
    selected_market_value = prices.get(price_kind)
    item_id = request.form.get("item_id", type=int)
    item = db.session.get(CollectionItem, item_id) if item_id else collection_for(game)
    if item and item.ownership_format == "digital":
        flash("Digitale Exemplare werden nicht mit physischen PriceCharting-Angeboten bewertet.", "warning")
        return redirect(url_for("collection_configure", game_id=game.id, item_id=item.id))
    return render_template(
        "collection_configure.html", game=game, item=item, copies=collection_items_for(game), prices=prices,
        selected_market_value=selected_market_value, selected_price_kind=price_kind,
        pricecharting_enabled=True, new_import=False, market_lookup_done=True,
    )


@app.route("/collection/add/<int:game_id>", methods=["POST"])
@login_required
def collection_add(game_id):
    game = db.get_or_404(Game, game_id)
    item_id = request.form.get("item_id", type=int)
    item = db.session.get(CollectionItem, item_id) if item_id else None
    if item and (item.game_id != game.id or item.user_id != active_collection_user_id()):
        abort(403)
    is_new = item is None
    item = item or CollectionItem(game_id=game.id, user_id=active_collection_user_id())
    errors = apply_collection_form(item)
    if errors:
        db.session.rollback()
        for error in errors:
            flash(error, "danger")
        return redirect(request.referrer or url_for("collection_configure", game_id=game.id, item_id=item_id))
    if is_new:
        db.session.add(item); db.session.flush()
        log_activity("copy_added", "collection_item", item.id, f"{game.title}: Exemplar zur Sammlung hinzugefügt.")
    else:
        log_activity("copy_updated", "collection_item", item.id, f"{game.title}: Exemplar #{item.id} aktualisiert.")
    db.session.commit()
    flash("Sammlung aktualisiert.", "success")
    return redirect(request.referrer or url_for("collection"))


@app.route("/collection/items/<int:item_id>/delete", methods=["POST"])
@login_required
def collection_item_delete(item_id):
    item = db.get_or_404(CollectionItem, item_id)
    if item.user_id != active_collection_user_id():
        abort(403)
    game_id = item.game_id
    title = item.game.title
    return_to = safe_collection_return_to(request.form.get("return_to", ""))
    # Preserve historical run summaries while detaching their optional item link.
    RevaluationLog.query.filter_by(collection_item_id=item.id).update({"collection_item_id": None})
    log_activity("copy_deleted", "collection_item", item.id, f"{title}: Exemplar #{item.id} gelöscht.", {"game_id": game_id})
    db.session.delete(item)
    db.session.flush()
    collection_total_value_snapshot()
    db.session.commit()
    flash(f"Exemplar #{item_id} wurde gelöscht. Der Katalogeintrag bleibt erhalten.", "success")
    return redirect(return_to or url_for("game_detail", game_id=game_id))


@app.route("/collection/auto-value/<int:game_id>", methods=["POST"])
@login_required
def collection_auto_value(game_id):
    game = db.get_or_404(Game, game_id)
    item_id = request.form.get("item_id", type=int)
    item = db.session.get(CollectionItem, item_id) if item_id else collection_for(game)
    if item and (item.game_id != game.id or item.user_id != active_collection_user_id()):
        abort(403)
    if not item:
        flash("Speichere zuerst ein Exemplar, damit der passende Zustand bewertet werden kann.", "warning")
        return redirect(url_for("collection_configure", game_id=game.id))
    if item.ownership_format == "digital":
        flash("Digitale Exemplare werden nicht mit physischen Marktangeboten bewertet.", "warning")
        return redirect(url_for("collection_configure", game_id=game.id, item_id=item.id))
    ok, status = auto_value_item(item)
    if ok:
        db.session.commit()
        flash(f"Automatischer Marktwert aktualisiert: {item.auto_value_eur:.2f} € ({item.auto_value_source}).", "success")
    else:
        db.session.rollback()
        if status in ("unsupported_platform", "no_automatic_price_source"):
            flash("Für diese Plattform ist derzeit keine automatische Preisquelle verfügbar. Dein manueller Schätzwert bleibt erhalten.", "warning")
        else:
            flash("Für diese Spielvariante konnte die kostenlose Preisquelle keinen sicheren Treffer liefern.", "warning")
    return redirect(url_for("collection_configure", game_id=game.id, item_id=item.id))


def recover_stale_revaluation_runs(force=False, collection_user_id=None):
    """Recover orphaned valuation runs. At app startup no old daemon worker survives."""
    from datetime import timedelta
    cutoff = utc_now() - timedelta(minutes=20)
    query = RevaluationRun.query.filter(RevaluationRun.state.in_(["queued", "running", "cancel_requested"]))
    if collection_user_id is not None:
        query = query.filter(RevaluationRun.collection_user_id == collection_user_id)
    runs = query.all()
    changed = False
    for run in runs:
        last = run.heartbeat_at or run.started_at
        if force or (last and last < cutoff):
            run.state = "failed"
            run.success = False
            run.finished_at = utc_now()
            run.current_title = None
            run.message = "Neubewertung wegen fehlendem Lebenszeichen beendet (z. B. nach Container-Neustart)."
            changed = True
    if changed:
        db.session.commit()


@app.route("/collection/revalue", methods=["POST"])
@login_required
def collection_revalue():
    owner_id = active_collection_user_id()
    recover_stale_revaluation_runs(collection_user_id=owner_id)
    active = RevaluationRun.query.filter(RevaluationRun.collection_user_id == owner_id, RevaluationRun.state.in_(["queued", "running", "cancel_requested"])).order_by(RevaluationRun.started_at.desc()).first()
    if active:
        flash("Eine Neubewertung läuft bereits.", "warning")
        if request.form.get("return_to") == "dashboard":
            return redirect(url_for("dashboard"))
        return redirect(url_for("valuation_detail", run_id=active.id))
    total = CollectionItem.query.join(Game).filter(CollectionItem.status=="owned", CollectionItem.user_id==owner_id, CollectionItem.ownership_format!="digital", CollectionItem.auto_value_eur.is_(None), Game.physical_status!="excluded").count()
    run = RevaluationRun(collection_user_id=owner_id, source="manual", started_at=utc_now(), total_count=total, state="queued", heartbeat_at=utc_now(), message="Neubewertung wartet auf Start")
    db.session.add(run); db.session.commit(); run_id = run.id

    def worker(app_obj, rid, uid):
        with app_obj.app_context():
            run = db.session.get(RevaluationRun, rid)
            try:
                run.state = "running"; run.message = "Neubewertung läuft"; run.heartbeat_at = utc_now(); db.session.commit()
                items = [i for i in CollectionItem.query.filter_by(status="owned", user_id=uid).filter(CollectionItem.ownership_format!="digital", CollectionItem.auto_value_eur.is_(None)).order_by(CollectionItem.id).all() if game_is_physical_candidate(i.game)]
                # Recalculate inside the worker as a durable guard against stale/legacy runs.
                run = db.session.get(RevaluationRun, rid)
                run.total_count = len(items)
                db.session.commit()
                updated=unsupported=failed=0
                for pos, item in enumerate(items, 1):
                    run = db.session.get(RevaluationRun, rid)
                    run.current_index=pos; run.current_title=item.game.title; run.heartbeat_at=utc_now(); db.session.commit()
                    if run.state == "cancel_requested":
                        run.state = "cancelled"; run.success = False; run.finished_at = utc_now(); run.current_title = None; run.message = "Neubewertung wurde abgebrochen."; db.session.commit(); return
                    try:
                        ok, status = auto_value_item(item, run=run)
                        if ok: updated += 1
                        elif status in ("unsupported_platform", "no_automatic_price_source", "no_match", "empty", "not_found"):
                            unsupported += 1
                        else: failed += 1
                        msg = item.auto_value_message or (f"{item.auto_value_eur:.2f} € · {item.auto_value_source}" if ok and item.auto_value_eur is not None else status)
                        db.session.add(RevaluationLog(revaluation_run_id=rid, collection_item_id=item.id, position=pos, title=item.game.title, status="Bewertet" if ok else ("Ohne Quelle" if status in ("unsupported_platform", "no_automatic_price_source", "no_match", "empty", "not_found") else "Fehler"), message=msg))
                        run.checked_count=pos; run.valued_count=updated; run.unsupported_count=unsupported; run.failed_count=failed
                        db.session.commit()
                    except Exception as exc:
                        db.session.rollback(); run=db.session.get(RevaluationRun,rid); failed += 1
                        run.checked_count=pos; run.failed_count=failed
                        db.session.add(RevaluationLog(revaluation_run_id=rid, collection_item_id=item.id, position=pos, title=item.game.title, status="Fehler", message=str(exc)[:300])); db.session.commit()
                collection_total_value_snapshot()
                run=db.session.get(RevaluationRun,rid); run.finished_at=utc_now(); run.success=True; run.state="finished"; run.current_title=None; run.heartbeat_at=utc_now(); run.message="Neubewertung abgeschlossen"; db.session.commit()
            except Exception as exc:
                db.session.rollback(); run=db.session.get(RevaluationRun,rid)
                if run:
                    run.finished_at=utc_now(); run.success=False; run.state="failed"; run.heartbeat_at=utc_now(); run.message=f"Neubewertung abgebrochen: {exc}"; db.session.commit()
                app_obj.logger.exception("background revaluation failed")
    threading.Thread(target=worker, args=(app, run_id, owner_id), daemon=True, name=f"valuation-{run_id}").start()
    if request.form.get("return_to") == "dashboard":
        flash("Bewertung unbewerteter Spiele gestartet; bereits bewertete werden bis zum nächsten automatischen Lauf übersprungen.", "success")
        return redirect(url_for("dashboard"))
    return redirect(url_for("valuation_detail", run_id=run_id))

@app.route("/collection/revalue/<int:run_id>/cancel", methods=["POST"])
@login_required
def collection_revalue_cancel(run_id):
    run = db.session.get(RevaluationRun, run_id) or abort(404)
    if run.collection_user_id not in (None, active_collection_user_id()): abort(403)
    if run.state in ("queued", "running"):
        run.state = "cancel_requested"
        run.message = "Abbruch angefordert …"
        run.heartbeat_at = utc_now()
        db.session.commit()
        flash("Abbruch der Neubewertung wurde angefordert.", "warning")
    elif run.state == "cancel_requested":
        flash("Der Abbruch wurde bereits angefordert.", "warning")
    else:
        flash("Diese Neubewertung läuft nicht mehr.", "info")
    return redirect(url_for("valuation_detail", run_id=run.id))


@app.route("/valuation")
@login_required
def valuation_overview():
    owner_id = active_collection_user_id()
    recover_stale_revaluation_runs(collection_user_id=owner_id)
    run = RevaluationRun.query.filter_by(collection_user_id=owner_id).order_by(RevaluationRun.started_at.desc()).first()
    return redirect(url_for("valuation_detail", run_id=run.id)) if run else render_template("valuation.html", run=None, logs=[])

@app.route("/valuation/<int:run_id>")
@login_required
def valuation_detail(run_id):
    recover_stale_revaluation_runs(collection_user_id=active_collection_user_id())
    run = db.session.get(RevaluationRun, run_id) or abort(404)
    if run.collection_user_id not in (None, active_collection_user_id()): abort(403)
    logs = RevaluationLog.query.filter_by(revaluation_run_id=run.id).order_by(RevaluationLog.position.desc()).limit(250).all()
    return render_template("valuation.html", run=run, logs=logs)


PRICE_CENTER_STALE_DAYS = 45


def _price_center_target(kind, item_id):
    models = {
        "game": CollectionItem,
        "hardware": HardwareItem,
        "accessory": AccessoryItem,
        "collector": CollectorItem,
    }
    model = models.get(kind)
    if not model:
        abort(404)
    item = db.get_or_404(model, item_id)
    if kind in {"game", "collector"} and item.user_id != active_collection_user_id():
        abort(403)
    if kind in {"hardware", "accessory"} and item.user_id != active_collection_user_id():
        abort(403)
    return item


def _price_center_return():
    target = (request.form.get("return_to") or "").strip()
    if target.startswith("/price-center"):
        return target
    return url_for("price_center")


def _price_center_history_values(item, kind):
    if kind == "game":
        history = item.price_history
    elif kind == "hardware":
        history = item.price_history
    elif kind == "accessory":
        history = item.price_history
    else:
        history = item.collector_price_history
    rows = sorted(history, key=lambda row: row.recorded_at or datetime.min, reverse=True)
    values = [float(row.value_eur) for row in rows[:2] if row.value_eur is not None]
    latest = values[0] if values else None
    previous = values[1] if len(values) > 1 else None
    delta = round(latest - previous, 2) if latest is not None and previous is not None else None
    return latest, previous, delta


def _price_center_outlier(item, automatic, purchase, history_previous):
    if automatic is None:
        return None
    automatic = float(automatic)
    low = getattr(item, "auto_value_low_eur", None)
    high = getattr(item, "auto_value_high_eur", None)
    if low is not None and high is not None and float(low) > 0:
        if float(high) / float(low) >= 8 and float(high) - float(low) >= 20:
            return "Sehr große Preisspanne der Quelle"
    if history_previous is not None and float(history_previous) > 0:
        ratio = automatic / float(history_previous)
        if (ratio >= 2.5 or ratio <= 0.4) and abs(automatic - float(history_previous)) >= 10:
            return "Sprunghafte Änderung gegenüber dem vorherigen Marktwert"
    if purchase is not None and float(purchase) > 0:
        if automatic / float(purchase) >= 10 and automatic - float(purchase) >= 50:
            return "Marktwert liegt ungewöhnlich weit über dem Kaufpreis"
    return None


def _price_center_row(item, kind):
    now = utc_now()
    if kind == "game":
        title = item.game.title
        category = "games"
        category_label = "Games"
        subtitle = f"{item.game.console.name} · {item.game.region or 'Region offen'} · {item.game.edition or 'Standard'}"
        variant = f"Exemplar #{item.id} · {item.completeness or 'Loose'} · Zustand {item.auto_value_condition or item.media_condition or 'offen'}"
        purchase = item.purchase_price
        estimate = item.estimated_value
        detail_url = url_for("game_detail", game_id=item.game_id)
        source_url = item.auto_value_url
        status_raw = item.auto_value_status
        message = item.auto_value_message
        lockable = item.ownership_format != "digital"
        quantity = 1
    elif kind == "hardware":
        title = item.model.name
        category = "hardware"
        category_label = "Hardware"
        subtitle = f"{item.model.console.name} · {item.model.edition or item.model.model_number or 'Variante offen'}"
        variant = f"Exemplar #{item.id} · {item.completeness or 'Loose'} · {item.set_condition_label or ('Zustand ' + str(item.condition or 'offen'))}"
        purchase = item.purchase_price
        estimate = item.estimated_value
        detail_url = url_for("hardware_detail", model_id=item.hardware_model_id)
        source_url = item.auto_value_url
        status_raw = "ok" if item.auto_value_eur is not None else None
        message = item.auto_value_message
        lockable = True
        quantity = 1
    elif kind == "accessory":
        title = item.name
        category = "accessories"
        category_label = "Zubehör"
        subtitle = f"{item.console.name if item.console else 'Plattformübergreifend'} · {accessory_category_label(item.category)}"
        variant = f"Eintrag #{item.id} · {'Original' if item.original_product else 'Drittanbieter'} · Zustand {item.condition or 'offen'}"
        purchase = item.purchase_price
        estimate = item.estimated_value
        detail_url = url_for("accessories")
        source_url = item.auto_value_url
        status_raw = item.auto_value_status
        message = item.auto_value_message
        lockable = True
        quantity = max(1, int(item.quantity or 1))
    else:
        title = item.title
        category = item.category
        category_label = COLLECTOR_SECTIONS.get(item.category, {}).get("title", item.category.title())
        subtitle = " · ".join(value for value in (item.media_type, item.edition, item.card_variant) if value) or category_label
        variant = f"Exemplar #{item.id} · {item.completeness or item.condition or 'Variante offen'}"
        purchase = item.purchase_price_eur
        estimate = item.estimated_value_eur
        detail_url = url_for("collector_item_detail", item_id=item.id)
        source_url = None
        status_raw = item.auto_value_status
        message = None
        lockable = not is_pokemon_card(item)
        quantity = max(1, int(item.quantity or 1))

    automatic = getattr(item, "auto_value_eur", None)
    fixed = getattr(item, "fixed_value_eur", None)
    updated = getattr(item, "auto_value_updated_at", None)
    latest_history, previous_history, history_delta = _price_center_history_values(item, kind)
    outlier_reason = (message if status_raw == "price_jump_pending" else
                      _price_center_outlier(item, automatic, purchase, previous_history))
    failure = bool(status_raw and str(status_raw).casefold() not in {
        "ok", "success", "synced", "digital_excluded", "non_physical_excluded", "not_checked"
    })
    if fixed is not None:
        state = "fixed"
    elif automatic is None and failure:
        state = "error"
    elif automatic is None:
        state = "missing"
    elif outlier_reason:
        state = "outlier"
    elif updated is None or updated < now - timedelta(days=PRICE_CENTER_STALE_DAYS):
        state = "stale"
    else:
        state = "current"
    effective = (float(fixed) if fixed is not None else
                 float(automatic) if automatic is not None else
                 float(estimate) if estimate is not None else None)
    purchase_delta = round(effective - float(purchase), 2) if effective is not None and purchase is not None else None
    purchase_pct = round(purchase_delta / float(purchase) * 100, 1) if purchase_delta is not None and float(purchase) else None
    source = ("Manuell fixiert" if fixed is not None else
              getattr(item, "auto_value_source", None) if automatic is not None else
              "Eigene Schätzung" if estimate is not None else None)
    if kind == "collector" and is_pokemon_card(item):
        source = "PokéCollector-Synchronwert (keine automatische Bibo-Bewertung)" if automatic is not None else "PokéCollector-Synchronisierung erforderlich"
    return {
        "kind": kind, "id": item.id, "item": item, "title": title, "category": category,
        "category_label": category_label, "subtitle": subtitle, "variant": variant,
        "purchase": purchase, "estimate": estimate, "automatic": automatic, "effective": effective,
        "fixed": fixed, "fixed_reason": getattr(item, "fixed_value_reason", None),
        "fixed_at": getattr(item, "fixed_value_at", None), "updated": updated, "source": source,
        "source_url": source_url, "status_raw": status_raw, "message": message,
        "state": state, "outlier_reason": outlier_reason, "detail_url": detail_url,
        "history_latest": latest_history, "history_previous": previous_history,
        "history_delta": history_delta, "purchase_delta": purchase_delta,
        "purchase_pct": purchase_pct, "quantity": quantity, "lockable": lockable,
        "search": _search_text(" ".join(str(value or "") for value in (title, subtitle, variant, source, status_raw, message))),
    }


@app.route("/price-center/<kind>/<int:item_id>/trace")
@login_required
def price_center_trace(kind, item_id):
    item = _price_center_target(kind, item_id)
    row = _price_center_row(item, kind)
    if kind in {"game", "hardware", "accessory"}:
        history = list(item.price_history)
    else:
        history = list(item.collector_price_history)
    history.sort(key=lambda entry: entry.recorded_at or datetime.min, reverse=True)
    return render_template("price_trace.html", row=row, history=history[:100], pokemon=(kind == "collector" and is_pokemon_card(item)))


def _price_center_rows():
    uid = active_collection_user_id()
    rows = []
    games = (CollectionItem.query.join(Game).options(
        joinedload(CollectionItem.game).joinedload(Game.console),
        selectinload(CollectionItem.price_history),
    ).filter(
        CollectionItem.user_id == uid, CollectionItem.status == "owned",
        CollectionItem.ownership_format != "digital", Game.physical_status != "excluded",
    ).all())
    rows.extend(_price_center_row(item, "game") for item in games)
    hardware = scoped_hardware_query().options(
        joinedload(HardwareItem.model).joinedload(HardwareModel.console),
        selectinload(HardwareItem.price_history),
    ).filter_by(status="owned").all()
    rows.extend(_price_center_row(item, "hardware") for item in hardware)
    accessories = scoped_accessory_query().options(
        joinedload(AccessoryItem.console), selectinload(AccessoryItem.price_history),
    ).filter_by(status="owned").all()
    rows.extend(_price_center_row(item, "accessory") for item in accessories)
    collector = CollectorItem.query.options(
        selectinload(CollectorItem.collector_price_history),
    ).filter_by(user_id=uid).all()
    rows.extend(_price_center_row(item, "collector") for item in collector)
    return rows


@app.route("/price-center")
@login_required
def price_center():
    status = (request.args.get("status") or "queue").strip()
    category = (request.args.get("category") or "all").strip()
    query_text = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "priority").strip()
    page = max(1, request.args.get("page", type=int) or 1)
    all_rows = _price_center_rows()
    counts = {key: sum(1 for row in all_rows if row["state"] == key) for key in ("missing", "stale", "error", "outlier", "fixed", "current")}
    queue_states = {"missing", "stale", "error", "outlier"}
    rows = all_rows
    if status == "queue":
        rows = [row for row in rows if row["state"] in queue_states]
    elif status in counts:
        rows = [row for row in rows if row["state"] == status]
    else:
        status = "all"
    if category != "all":
        rows = [row for row in rows if row["category"] == category]
    if query_text:
        needle = _search_text(query_text)
        rows = [row for row in rows if needle in row["search"]]
    priorities = {"error": 0, "outlier": 1, "missing": 2, "stale": 3, "fixed": 4, "current": 5}
    if sort == "name":
        rows.sort(key=lambda row: _search_text(row["title"]))
    elif sort == "value_desc":
        rows.sort(key=lambda row: (row["effective"] is not None, row["effective"] or 0), reverse=True)
    elif sort == "oldest":
        rows.sort(key=lambda row: row["updated"] or datetime.min)
    else:
        sort = "priority"
        rows.sort(key=lambda row: (priorities.get(row["state"], 9), row["updated"] or datetime.min, _search_text(row["title"])))
    per_page = 100
    total_filtered = len(rows)
    pages = max(1, (total_filtered + per_page - 1) // per_page)
    page = min(page, pages)
    rows = rows[(page - 1) * per_page:page * per_page]
    categories = [
        ("all", "Alle"), ("games", "Games"), ("hardware", "Hardware"),
        ("accessories", "Zubehör"), ("movies", "Filme"), ("tv", "Serien"),
        ("books", "Bücher"), ("music", "Musik"), ("cards", "Karten"),
    ]
    return render_template("price_center.html", rows=rows, counts=counts, status=status,
                           category=category, categories=categories, q=query_text, sort=sort,
                           page=page, pages=pages, total_filtered=total_filtered,
                           queue_count=sum(counts[key] for key in queue_states),
                           stale_days=PRICE_CENTER_STALE_DAYS)


@app.route("/price-center/<kind>/<int:item_id>/fix", methods=["POST"])
@login_required
def price_center_fix(kind, item_id):
    item = _price_center_target(kind, item_id)
    value = parse_money_input(request.form.get("value"))
    if value is None or value < 0:
        flash("Bitte einen gültigen fixierten Preis eingeben.", "danger")
        return redirect(_price_center_return())
    reason = (request.form.get("reason") or "").strip()[:255]
    item.fixed_value_eur = round(float(value), 2)
    item.fixed_value_reason = reason or "Manuell im Preiszentrum geprüft"
    item.fixed_value_at = utc_now()
    log_activity("price_fixed", kind, item.id, f"Preis auf {item.fixed_value_eur:.2f} € fixiert: {item.fixed_value_reason}")
    collector_total_value_snapshot()
    db.session.commit()
    flash(f"Preis wurde auf {format_eur(item.fixed_value_eur)} fixiert. Der automatische Marktwert bleibt erhalten.", "success")
    return redirect(_price_center_return())


@app.route("/price-center/<kind>/<int:item_id>/unfix", methods=["POST"])
@login_required
def price_center_unfix(kind, item_id):
    item = _price_center_target(kind, item_id)
    old = item.fixed_value_eur
    item.fixed_value_eur = None
    item.fixed_value_reason = None
    item.fixed_value_at = None
    log_activity("price_unfixed", kind, item.id, f"Preisfixierung {format_eur(old)} aufgehoben.")
    collector_total_value_snapshot()
    db.session.commit()
    flash("Preisfixierung aufgehoben. Es gilt wieder der automatische Marktwert beziehungsweise die eigene Schätzung.", "success")
    return redirect(_price_center_return())


@app.route("/price-center/<kind>/<int:item_id>/revalue", methods=["POST"])
@login_required
def price_center_revalue(kind, item_id):
    item = _price_center_target(kind, item_id)
    ok = False
    status = "no_price"
    if kind == "game":
        ok, status = auto_value_item(item)
    elif kind == "hardware":
        ok, status = hardware_auto_value(item)
    elif kind == "accessory":
        ok, status = accessory_auto_value(item)
    elif is_pokemon_card(item):
        flash("Pokémon-Preise werden über die PokéCollector-Synchronisierung aktualisiert.", "info")
        return redirect(_price_center_return())
    elif item.category == "cards" and (item.tcg_game or "").strip().casefold() == "magic: the gathering":
        value, low, high, source = collector_scryfall_valuation(item)
        if value is not None:
            previous = item.auto_value_eur
            item.auto_value_eur = value; item.auto_value_low_eur = low; item.auto_value_high_eur = high
            item.auto_value_source = source; item.auto_value_status = "ok"; item.auto_value_updated_at = utc_now()
            record_collector_price(item, previous, value, low, high, source); ok = True; status = "ok"
    else:
        value, low, high, status = collector_ebay_valuation(item)
        item.auto_value_status = status; item.auto_value_updated_at = utc_now()
        if value is not None:
            previous = item.auto_value_eur
            item.auto_value_eur = value; item.auto_value_low_eur = low; item.auto_value_high_eur = high
            item.auto_value_source = "eBay-Angebote"; record_collector_price(item, previous, value, low, high, "eBay-Angebote"); ok = True
    collector_total_value_snapshot()
    db.session.commit()
    if ok:
        flash(f"Marktwert aktualisiert: {format_eur(item.auto_value_eur)}. Eine vorhandene Fixierung bleibt wirksam.", "success")
    else:
        flash(VALUATION_STATUS_MESSAGES.get(status, "Kein ausreichend sicherer Marktpreis gefunden."), "warning")
    return redirect(_price_center_return())

@app.route("/api/valuation/<int:run_id>")
@login_required
def valuation_status_api(run_id):
    owner_id = active_collection_user_id()
    recover_stale_revaluation_runs(collection_user_id=owner_id)
    run = db.session.get(RevaluationRun, run_id) or abort(404)
    if run.collection_user_id not in (None, owner_id): abort(403)
    logs = RevaluationLog.query.filter_by(revaluation_run_id=run.id).order_by(RevaluationLog.position.desc()).limit(40).all()
    total = run.total_count or 0
    checked = run.checked_count or 0
    pct = min(100, round(checked * 100 / total)) if total else (100 if run.state == "finished" and checked else 0)
    end = run.finished_at or utc_now()
    duration = max(0, int((end - run.started_at).total_seconds())) if run.started_at else 0
    return jsonify({"id":run.id,"state":run.state,"success":run.success,"checked":checked,"total":total,"pct":pct,"current":run.current_title or "","valued":run.valued_count,"unsupported":run.unsupported_count,"failed":run.failed_count,"message":run.message or "","started_at":run.started_at.isoformat() if run.started_at else None,"finished_at":run.finished_at.isoformat() if run.finished_at else None,"duration_seconds":duration,"logs":[{"position":x.position,"title":x.title,"status":x.status,"message":x.message or ""} for x in logs]})

@app.route("/price-activity")
@login_required
def price_activity():
    change = request.args.get("change", "").strip()
    category = request.args.get("category", "all").strip()
    rows=[]
    q=PriceActivity.query.join(CollectionItem).filter(CollectionItem.user_id == active_collection_user_id())
    if change in {"up","down","same","new"}: q=q.filter(PriceActivity.change_type==change)
    for r in q.order_by(PriceActivity.recorded_at.desc()).limit(500).all():
        rows.append({"recorded_at":r.recorded_at,"change_type":r.change_type,"previous":r.previous_value_eur,"value":r.value_eur,"delta":r.delta_eur,"source":r.source,"category":"games","category_label":"Games","title":r.collection_item.game.title,"subtitle":r.collection_item.game.console.name,"url":url_for("game_detail",game_id=r.collection_item.game.id)})
    pokemon_ids = [row.id for row in CollectorItem.query.filter_by(user_id=active_collection_user_id(), category="cards").all() if is_pokemon_card(row)]
    cq=CollectorPriceActivity.query.join(CollectorItem).filter(CollectorItem.user_id==active_collection_user_id())
    if pokemon_ids: cq=cq.filter(~CollectorItem.id.in_(pokemon_ids))
    if change in {"up","down","same","new"}: cq=cq.filter(CollectorPriceActivity.change_type==change)
    if category not in {"all","games"}: cq=cq.filter(CollectorItem.category==category)
    if category != "games":
        for r in cq.order_by(CollectorPriceActivity.recorded_at.desc()).limit(500).all():
            label=COLLECTOR_SECTIONS.get(r.item.category,{}).get("title",r.item.category)
            rows.append({"recorded_at":r.recorded_at,"change_type":r.change_type,"previous":r.previous_value_eur,"value":r.value_eur,"delta":r.delta_eur,"source":r.source,"category":r.item.category,"category_label":label,"title":r.item.title,"subtitle":r.item.media_type or label,"url":url_for("collector_item_detail",item_id=r.item.id)})
    if category in {"all","hardware"}:
        for item in scoped_hardware_query().filter_by(status="owned").all():
            hist=sorted(item.price_history,key=lambda x:x.recorded_at or datetime.min)
            for idx,r in enumerate(hist):
                prev=hist[idx-1].value_eur if idx else None; delta=round(float(r.value_eur)-(float(prev) if prev is not None else float(r.value_eur)),2); ch="new" if prev is None else ("up" if delta>0.004 else ("down" if delta<-0.004 else "same"))
                if change and ch!=change: continue
                rows.append({"recorded_at":r.recorded_at,"change_type":ch,"previous":prev,"value":r.value_eur,"delta":delta,"source":r.source,"category":"hardware","category_label":"Hardware","title":item.model.name,"subtitle":item.model.console.name if item.model and item.model.console else "Hardware","url":url_for("hardware_detail",model_id=item.hardware_model_id)})
    if category in {"all","accessories"}:
        for item in scoped_accessory_query().filter_by(status="owned").all():
            hist=sorted(item.price_history,key=lambda x:x.recorded_at or datetime.min)
            for idx,r in enumerate(hist):
                prev=hist[idx-1].value_eur if idx else None; delta=round(float(r.value_eur)-(float(prev) if prev is not None else float(r.value_eur)),2); ch="new" if prev is None else ("up" if delta>0.004 else ("down" if delta<-0.004 else "same"))
                if change and ch!=change: continue
                rows.append({"recorded_at":r.recorded_at,"change_type":ch,"previous":prev,"value":r.value_eur,"delta":delta,"source":r.source,"category":"accessories","category_label":"Zubehör","title":item.name,"subtitle":item.console.name if item.console else "Zubehör","url":url_for("accessories")})
    if category not in {"all","games","hardware","accessories"}: rows=[r for r in rows if r["category"]==category]
    rows.sort(key=lambda r:r["recorded_at"] or datetime.min, reverse=True)
    return render_template("price_activity.html", rows=rows[:500], change=change, category=category)


@app.route("/collection")
@login_required
def collection():
    status = request.args.get("status", "owned")
    q = request.args.get("q", "").strip()
    console_id = request.args.get("console_id", type=int)
    valuation = request.args.get("valuation", "").strip()
    completeness = request.args.get("completeness", "").strip()
    franchise = request.args.get("franchise", "").strip()
    region = request.args.get("region", "").strip()
    ownership_format = request.args.get("format", "").strip().lower()
    if ownership_format not in {"", "physical", "digital"}:
        ownership_format = ""
    sort = request.args.get("sort", "title").strip()
    view = request.args.get("view", "grid").strip()
    if view not in {"grid", "list"}:
        view = "grid"
    session["collection_return_to"] = request.full_path.rstrip("?")
    query = CollectionItem.query.join(Game).filter(CollectionItem.status == status, CollectionItem.user_id == active_collection_user_id(), Game.physical_status != "excluded")
    if q:
        query = query.filter(db.or_(Game.title.ilike(f"%{q}%"), Game.barcode.ilike(f"%{q}%"), Game.product_code.ilike(f"%{q}%")))
    if console_id:
        query = query.filter(Game.console_id == console_id)
    if completeness:
        query = query.filter(CollectionItem.completeness == completeness)
    if franchise:
        query = query.filter(Game.franchise == franchise)
    if region:
        query = query.filter(Game.region == region)
    if ownership_format:
        query = query.filter(CollectionItem.ownership_format == ownership_format)
    if valuation == "auto":
        query = query.filter(CollectionItem.auto_value_eur.isnot(None))
    elif valuation == "valued":
        query = query.filter(db.or_(CollectionItem.fixed_value_eur.isnot(None), CollectionItem.auto_value_eur.isnot(None), CollectionItem.estimated_value.isnot(None)))
    elif valuation == "no_value":
        query = query.filter(CollectionItem.fixed_value_eur.is_(None), CollectionItem.auto_value_eur.is_(None), CollectionItem.estimated_value.is_(None))
    elif valuation == "auto_missing":
        query = query.filter(CollectionItem.auto_value_eur.is_(None))
    elif valuation == "unsupported":
        query = query.filter(CollectionItem.auto_value_status.in_(("unsupported_platform", "no_automatic_price_source")))
    elif valuation == "failed":
        query = query.filter(
            CollectionItem.auto_value_eur.is_(None),
            CollectionItem.auto_value_status.isnot(None),
            ~CollectionItem.auto_value_status.in_(("unsupported_platform", "no_automatic_price_source")),
        )
    elif valuation == "purchased":
        query = query.filter(CollectionItem.purchase_price.isnot(None))

    items = [i for i in query.all() if game_is_physical_candidate(i.game)]
    value_of = lambda i: effective_value(i) if effective_value(i) is not None else -1
    if sort == "value_desc":
        items.sort(key=value_of, reverse=True)
    elif sort == "value_asc":
        items.sort(key=value_of)
    elif sort == "added_desc":
        items.sort(key=lambda i: i.added_at or datetime.min, reverse=True)
    elif sort == "purchase_desc":
        items.sort(key=lambda i: i.purchase_price if i.purchase_price is not None else -1, reverse=True)
    elif sort == "year":
        items.sort(key=lambda i: (i.game.release_year or 9999, i.game.title.lower()))
    else:
        items.sort(key=lambda i: i.game.title.lower())

    franchises = [r[0] for r in db.session.query(Game.franchise).join(CollectionItem, CollectionItem.game_id == Game.id).filter(
        CollectionItem.status == status, CollectionItem.user_id == active_collection_user_id(), Game.franchise.isnot(None), Game.franchise != ""
    ).distinct().order_by(Game.franchise).all()]
    regions = [r[0] for r in db.session.query(Game.region).join(CollectionItem, CollectionItem.game_id == Game.id).filter(
        CollectionItem.status == status, CollectionItem.user_id == active_collection_user_id(), Game.region.isnot(None), Game.region != ""
    ).distinct().order_by(Game.region).all()]
    completeness_options = [r[0] for r in db.session.query(CollectionItem.completeness).filter(
        CollectionItem.status == status, CollectionItem.user_id == active_collection_user_id(), CollectionItem.completeness.isnot(None)
    ).distinct().order_by(CollectionItem.completeness).all()]
    format_rows = CollectionItem.query.join(Game).filter(
        CollectionItem.status == status, CollectionItem.user_id == active_collection_user_id(), Game.physical_status != "excluded"
    ).all()
    format_counts = {
        "all": len(format_rows),
        "physical": sum(1 for row in format_rows if (row.ownership_format or "physical") != "digital"),
        "digital": sum(1 for row in format_rows if row.ownership_format == "digital"),
    }
    return render_template("collection.html", items=items, status=status, q=q, consoles=Console.query.order_by(Console.name).all(),
                           selected_console=console_id, valuation=valuation, completeness=completeness, selected_franchise=franchise,
                           region=region, sort=sort, view=view, franchises=franchises, regions=regions,
                           completeness_options=completeness_options, selected_format=ownership_format, format_counts=format_counts,
                           selected_console_label=(db.session.get(Console, console_id).name if console_id and db.session.get(Console, console_id) else ""))


@app.route("/collection/remove/<int:item_id>", methods=["POST"])
@login_required
def collection_remove(item_id):
    item = db.get_or_404(CollectionItem, item_id)
    if item.user_id != active_collection_user_id():
        abort(403)
    title = item.game.title
    item_id_value = item.id
    log_activity("copy_removed", "collection_item", item_id_value, f"{title}: Exemplar #{item_id_value} aus der Sammlung entfernt.")
    db.session.delete(item)
    db.session.commit()
    flash("Exemplar aus der Sammlung entfernt.", "success")
    return redirect(request.referrer or url_for("collection"))


@app.route("/activity")
@login_required
def activity():
    page = max(1, request.args.get("page", type=int) or 1)
    per_page = 60
    q = ActivityLog.query.filter_by(collection_user_id=active_collection_user_id()).order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    rows = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(rows) > per_page
    return render_template("activity.html", rows=rows[:per_page], page=page, has_next=has_next)


@app.route("/activity/export.csv")
@login_required
def activity_export():
    rows = ActivityLog.query.filter_by(collection_user_id=active_collection_user_id()).order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Zeitpunkt", "Benutzer", "Aktion", "Objekttyp", "Objekt-ID", "Beschreibung", "Details"])
    for row in rows:
        writer.writerow([
            local_datetime(row.created_at).isoformat(timespec="seconds") if row.created_at else "",
            (row.actor.display_name or row.actor.username) if row.actor else "System",
            row.action, row.entity_type, row.entity_id or "", row.message, row.details_json or "",
        ])
    data = "\ufeff" + output.getvalue()
    return Response(data, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="bibo-aenderungsnachweis-{date.today().isoformat()}.csv"'})


def barcode_conflicts(barcode, exclude_game_id=None):
    code = clean_barcode(barcode)
    if not code:
        return []
    q = Game.query.filter(Game.barcode == code)
    if exclude_game_id:
        q = q.filter(Game.id != exclude_game_id)
    return q.order_by(Game.title).all()


def barcode_status(game):
    if not game.barcode:
        return {"state": "missing", "label": "Keine EAN/UPC hinterlegt", "count": 0}
    matches = barcode_conflicts(game.barcode, game.id)
    if matches:
        return {"state": "conflict", "label": f"EAN/UPC bei {len(matches)+1} Katalogtiteln", "count": len(matches)+1}
    return {"state": "unique", "label": "EAN/UPC eindeutig", "count": 1}


def _dup_pair(a, b):
    return (min(int(a), int(b)), max(int(a), int(b)))


def ignored_duplicate_pairs():
    return {(r.game_a_id, r.game_b_id) for r in DuplicateIgnore.query.all()}


def duplicate_candidates():
    """Conservative duplicate detector: barcode first, same-platform external id second."""
    rows = []
    ignored = ignored_duplicate_pairs()
    games = Game.query.order_by(Game.console_id, Game.title).all()
    by_barcode = {}
    for g in games:
        if g.barcode:
            by_barcode.setdefault(clean_barcode(g.barcode), []).append(g)
    for code, matches in by_barcode.items():
        if code and len(matches) > 1:
            for i in range(len(matches)):
                for j in range(i + 1, len(matches)):
                    a,b=matches[i],matches[j]; pair=_dup_pair(a.id,b.id)
                    if pair not in ignored:
                        rows.append({"reason":"barcode_duplicate","strength":"high","a":a,"b":b,"detail":code})
    by_external = {}
    for g in games:
        if g.external_source and g.external_id:
            key=(g.console_id, g.external_source.strip().casefold(), str(g.external_id).strip())
            by_external.setdefault(key, []).append(g)
    seen={(r['a'].id,r['b'].id) for r in rows}
    for key,matches in by_external.items():
        if len(matches)>1:
            for i in range(len(matches)):
                for j in range(i+1,len(matches)):
                    a,b=matches[i],matches[j]; pair=_dup_pair(a.id,b.id)
                    if pair not in ignored and pair not in seen:
                        rows.append({"reason":"external_shared","strength":"medium","a":a,"b":b,"detail":f"{a.external_source}: {a.external_id}"})
    return rows


def quality_issues():
    issues = []
    games = Game.query.order_by(Game.title).all()
    items = CollectionItem.query.filter_by(user_id=active_collection_user_id()).all()
    for g in games:
        missing = []
        if not g.cover_url: missing.append("cover")
        if not g.release_year: missing.append("year")
        if g.franchise and (g.series_status or "unreviewed") != "series":
            missing.append("series_mismatch")
        elif (g.series_status or "unreviewed") == "unreviewed":
            missing.append("series_review")
        elif g.series_status == "series" and not g.franchise:
            missing.append("franchise")
        if not g.barcode and not g.product_code: missing.append("identifier")
        if not g.external_source or not g.external_id: missing.append("external")
        if not g.publisher: missing.append("publisher")
        if missing:
            issues.append({"kind": "game", "game": g, "item": None, "missing": missing})
    for dup in duplicate_candidates():
        issues.append({"kind": "duplicate", "game": dup["a"], "other_game": dup["b"], "item": None, "missing": [dup["reason"]], "duplicate": dup})
    for i in items:
        missing = []
        if i.status == "owned" and i.auto_value_eur is None and i.estimated_value is None: missing.append("value")
        if i.status == "owned" and not i.notes and i.media_condition == 8 and i.box_condition == 8: missing.append("copy_details")
        if missing:
            issues.append({"kind": "copy", "game": i.game, "item": i, "missing": missing})
    # Collector-wide quality checks for movies, TV, books, music and cards.
    for c in CollectorItem.query.filter_by(user_id=active_collection_user_id()).all():
        missing=[]
        if not c.cover_url: missing.append("collector_cover")
        if not c.external_source or not c.external_id: missing.append("collector_external")
        if c.auto_value_eur is None and c.estimated_value_eur is None: missing.append("collector_value")
        if c.category in {"movies", "tv"}:
            cm = collector_metadata(c)
            if not c.media_type: missing.append("physical_medium")
            if not c.edition: missing.append("edition_review")
            if not str(cm.get("physical_country") or "").strip(): missing.append("de_release_review")
        if c.category == "cards":
            if not c.card_set: missing.append("card_set")
            if not c.card_number: missing.append("card_number")
            if not c.tcg_game: missing.append("card_tcg")
        if missing:
            issues.append({"kind":"collector","game":None,"item":c,"missing":missing})
    return issues


@app.route("/quality/export.csv")
@login_required
def quality_export_csv():
    rows = [["Typ","ID","Spiel-ID","Titel","Konsole/Kategorie","Fehler","Jahr","Publisher","Serie","Serienstatus","EAN/UPC","Produktcode","Cover-URL","Externe Quelle","Externe ID","Schätzwert EUR","Notizen"]]
    for row in quality_issues():
        if row["kind"] == "collector":
            c=row["item"]
            rows.append(["collector",c.id,"",c.title,c.category,",".join(row["missing"]),c.release_year or "","","","",c.barcode or "","",c.cover_url or "",c.external_source or "",c.external_id or "",c.estimated_value_eur if c.estimated_value_eur is not None else "",c.notes or ""])
            continue
        g = row["game"]; item = row.get("item")
        rows.append([row["kind"], item.id if item else g.id, g.id, g.title, g.console.name, ",".join(row["missing"]), g.release_year or "", g.publisher or "", g.franchise or "", g.series_status or "unreviewed", g.barcode or "", g.product_code or "", g.cover_url or "", g.external_source or "", g.external_id or "", item.estimated_value if item and item.estimated_value is not None else "", item.notes if item else ""])
    return _csv_response(rows, f"gamecollector-fehler-{date.today().isoformat()}.csv")


@app.route("/quality/import.csv", methods=["POST"])
@login_required
def quality_import_csv():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Bitte eine bearbeitete Fehler-CSV auswählen.", "warning")
        return redirect(url_for("quality"))
    try:
        text_data = upload.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text_data), delimiter=';')
        changed = 0
        for row in reader:
            game_id = int((row.get("Spiel-ID") or "0").strip() or 0)
            if not game_id:
                continue
            g = db.session.get(Game, game_id)
            if not g:
                continue
            year = (row.get("Jahr") or "").strip()
            g.release_year = int(year) if year.isdigit() else None
            g.publisher = (row.get("Publisher") or "").strip() or None
            g.franchise = (row.get("Serie") or "").strip() or None
            status = (row.get("Serienstatus") or "").strip()
            if status in {"series","standalone","unreviewed"}: g.series_status = status
            g.barcode = clean_barcode(row.get("EAN/UPC"))
            g.product_code = normalize_product_code(row.get("Produktcode"))
            g.cover_url = archived_or_original_image(row.get("Cover-URL"))
            g.external_source = (row.get("Externe Quelle") or "").strip() or None
            g.external_id = (row.get("Externe ID") or "").strip() or None
            if (row.get("Typ") or "").strip() == "copy":
                try: item_id = int((row.get("ID") or "0").strip() or 0)
                except ValueError: item_id = 0
                item = db.session.get(CollectionItem, item_id) if item_id else None
                if item and item.game_id == g.id and item.user_id == active_collection_user_id():
                    item.estimated_value = parse_money_input(row.get("Schätzwert EUR"))
                    item.notes = (row.get("Notizen") or "").strip() or None
            changed += 1
        db.session.commit()
        flash(f"Fehler-CSV importiert: {changed} Datensätze aktualisiert.", "success")
    except Exception as exc:
        db.session.rollback(); app.logger.exception("quality CSV import failed")
        flash(f"Fehler-CSV konnte nicht importiert werden: {exc}", "danger")
    return redirect(url_for("quality"))


@app.route("/quality")
@login_required
def quality():
    wanted = request.args.get("issue", "").strip()
    issues = quality_issues()
    counts = {}
    for row in issues:
        for key in row["missing"]:
            counts[key] = counts.get(key, 0) + 1
    priority = {"barcode_duplicate": 0, "external_shared": 1, "series_mismatch": 2, "cover": 3, "external": 4, "identifier": 5, "series_review": 6, "franchise": 7, "year": 8, "publisher": 8, "value": 9, "copy_details": 10, "collector_cover": 11, "collector_external": 12, "collector_value": 13, "edition_review": 14, "de_release_review": 14, "physical_medium": 14, "card_set": 15, "card_number": 14, "card_tcg": 14}
    issues.sort(key=lambda row: min((priority.get(k, 50) for k in row["missing"]), default=50))
    if wanted:
        issues = [row for row in issues if wanted in row["missing"]]
    series_status_stats = {
        "series": Game.query.filter(Game.series_status == "series", Game.franchise.isnot(None), Game.franchise != "").count(),
        "standalone": Game.query.filter(Game.series_status == "standalone").count(),
        "unreviewed": Game.query.filter(Game.series_status == "unreviewed").count(),
        "mismatch": Game.query.filter(Game.franchise.isnot(None), Game.franchise != "", Game.series_status != "series").count(),
        "missing_franchise": Game.query.filter(Game.series_status == "series", db.or_(Game.franchise.is_(None), Game.franchise == "")).count(),
    }
    return render_template("quality.html", issues=issues, counts=counts, selected_issue=wanted, series_status_stats=series_status_stats)


@app.route("/quality/series-status/fix", methods=["POST"])
@login_required
def quality_series_status_fix():
    games = Game.query.filter(Game.franchise.isnot(None), Game.franchise != "", Game.series_status != "series").all()
    changed = 0
    for game in games:
        game.series_status = "series"
        changed += 1
    if changed:
        log_activity("series_status_fixed", "game", None, f"{changed} eindeutige Serienstatus-Zuordnungen automatisch korrigiert.")
        db.session.commit()
        flash(f"{changed} eindeutige Serienzuordnungen wurden auf „Teil einer Spielreihe“ gesetzt.", "success")
    else:
        flash("Keine eindeutigen Serienstatus-Fälle zu korrigieren.", "success")
    return redirect(url_for("quality", issue="series_review"))


def goal_progress(goal):
    q = db.session.query(Game.id).join(CollectionItem, CollectionItem.game_id == Game.id).filter(
        CollectionItem.user_id == active_collection_user_id(), CollectionItem.status == "owned"
    )
    if goal.franchise:
        q = q.filter(Game.franchise == goal.franchise)
    if goal.series_group:
        q = q.filter(Game.series_group == goal.series_group)
    if goal.console_id:
        q = q.filter(Game.console_id == goal.console_id)
    current = len({r[0] for r in q.all()})
    target = goal.target_count or 0
    if target <= 0:
        tq = Game.query
        if goal.franchise: tq = tq.filter(Game.franchise == goal.franchise)
        if goal.series_group: tq = tq.filter(Game.series_group == goal.series_group)
        if goal.console_id: tq = tq.filter(Game.console_id == goal.console_id)
        target = tq.count()
        if goal.franchise:
            target = max(target, SeriesEntry.query.filter_by(franchise=goal.franchise, series_group=goal.series_group).count() if goal.series_group else SeriesEntry.query.filter_by(franchise=goal.franchise).count())
    target = max(1, target)
    return current, target, min(100, round(current / target * 100))


@app.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        target = max(0, request.form.get("target_count", type=int) or 0)
        if not name:
            flash("Bitte einen Namen für das Sammlungsziel angeben.", "danger")
        else:
            try:
                target_date = date.fromisoformat(request.form.get("target_date")) if request.form.get("target_date") else None
            except ValueError:
                target_date = None
            goal = CollectionGoal(
                collection_user_id=active_collection_user_id(),
                name=name, description=request.form.get("description", "").strip() or None,
                goal_type=request.form.get("goal_type", "manual"), target_count=target,
                franchise=request.form.get("franchise", "").strip() or None,
                series_group=request.form.get("series_group", "").strip() or None,
                console_id=request.form.get("console_id", type=int), created_by_user_id=current_user.id,
                priority=max(1, min(3, request.form.get("priority", type=int) or 2)),
                target_budget_eur=parse_money_input(request.form.get("target_budget_eur")),
                target_date=target_date,
            )
            db.session.add(goal); db.session.flush()
            log_activity("goal_created", "collection_goal", goal.id, f"Sammlungsziel „{goal.name}“ angelegt.")
            db.session.commit(); flash("Sammlungsziel angelegt.", "success")
        return redirect(url_for("goals"))
    rows = CollectionGoal.query.filter_by(collection_user_id=active_collection_user_id()).order_by(CollectionGoal.created_at.desc()).all()
    rendered = [{"goal": g, "progress": goal_progress(g)} for g in rows]
    franchises = [r[0] for r in db.session.query(Game.franchise).filter(Game.franchise.isnot(None), Game.franchise != "").distinct().order_by(Game.franchise).all()]
    series_groups = [r[0] for r in db.session.query(Game.series_group).filter(Game.series_group.isnot(None), Game.series_group != "").distinct().order_by(Game.series_group).all()]
    return render_template("goals.html", rows=rendered, consoles=Console.query.order_by(Console.name).all(), franchises=franchises, series_groups=series_groups)


@app.route("/planner", methods=["GET", "POST"])
@login_required
def collection_planner():
    owner_id = active_collection_user_id()
    budget_key = f"monthly_budget_collection_{owner_id}"
    if request.method == "POST":
        if effective_role() == "viewer": abort(403)
        budget = parse_money_input(request.form.get("monthly_budget"))
        app_setting_set(budget_key, str(budget or 0))
        log_activity("budget_updated", "collection_budget", None, f"Monatsbudget auf {format_eur(budget or 0)} gesetzt.")
        db.session.commit(); flash("Monatsbudget gespeichert.", "success")
        return redirect(url_for("collection_planner"))
    try: monthly_budget = float(app_setting_get(budget_key, "0") or 0)
    except (TypeError, ValueError): monthly_budget = 0.0
    today = local_datetime(utc_now()).date(); month_start = today.replace(day=1)
    game_spend = sum(item.purchase_price or 0 for item in CollectionItem.query.filter(CollectionItem.user_id == owner_id, CollectionItem.purchase_date >= month_start).all())
    collector_spend = sum((item.purchase_price_eur or 0) * max(item.quantity or 1, 1) for item in CollectorItem.query.filter(CollectorItem.user_id == owner_id, CollectorItem.purchase_date >= month_start).all())
    hardware_spend = sum(item.purchase_price or 0 for item in HardwareItem.query.filter(HardwareItem.user_id == owner_id, HardwareItem.purchase_date >= month_start).all())
    spent = round(game_spend + collector_spend + hardware_spend, 2)
    refresh_bibo_registry()
    wishlist_copies = BiboCopy.query.options(joinedload(BiboCopy.edition).joinedload(BiboEdition.work)).filter_by(owner_id=owner_id, active=True, status="wishlist").all()
    wishlist_rows = []
    for copy in wishlist_copies:
        target = None
        if copy.source_kind == "game":
            source = db.session.get(CollectionItem, int(copy.source_id)); target = source.wishlist_target_price if source else None
        wishlist_rows.append({"copy":copy, "work":copy.edition.work, "target":target, "url":url_for("bibo_work_detail", work_id=copy.edition.work_id)})
    wishlist_rows.sort(key=lambda row: (row["target"] is None, row["target"] or 0, row["work"].sort_title))
    goals_rows = [{"goal": goal, "progress": goal_progress(goal)} for goal in CollectionGoal.query.filter_by(collection_user_id=owner_id).order_by(CollectionGoal.priority.desc(), CollectionGoal.target_date, CollectionGoal.created_at.desc()).all()]
    availability = {status: BiboWork.query.join(BiboEdition).join(BiboCopy).filter(BiboCopy.owner_id == owner_id, BiboCopy.active.is_(True), BiboWork.availability_de == status).distinct().count() for status in ("physical", "never_physical_de", "digital", "unknown")}
    return render_template("planner.html", monthly_budget=monthly_budget, spent=spent, remaining=round(monthly_budget-spent,2), wishlist_rows=wishlist_rows, goals_rows=goals_rows, availability=availability)


@app.route("/locations", methods=["GET", "POST"])
@login_required
def storage_locations():
    owner_id = active_collection_user_id()
    if request.method == "POST":
        if effective_role() == "viewer": abort(403)
        name = " ".join((request.form.get("name") or "").split())[:160]
        parent_id = request.form.get("parent_id", type=int)
        parent = StorageLocation.query.filter_by(id=parent_id, owner_id=owner_id).first() if parent_id else None
        if not name:
            flash("Bitte einen Namen für den Lagerort angeben.", "danger")
        else:
            location = StorageLocation(owner_id=owner_id, parent_id=parent.id if parent else None, name=name, token=secrets.token_urlsafe(24))
            db.session.add(location); db.session.flush(); log_activity("location_created", "storage_location", location.id, f"Lagerort „{name}“ angelegt."); db.session.commit()
        return redirect(url_for("storage_locations"))
    refresh_bibo_registry()
    rows = StorageLocation.query.filter_by(owner_id=owner_id).order_by(StorageLocation.parent_id, StorageLocation.name).all()
    return render_template("storage_locations.html", rows=rows)


@app.route("/locations/<string:token>", methods=["GET", "POST"])
@login_required
def storage_location_detail(token):
    owner_id = active_collection_user_id()
    location = StorageLocation.query.filter_by(token=token, owner_id=owner_id).first_or_404()
    refresh_bibo_registry()
    if request.method == "POST":
        if effective_role() == "viewer": abort(403)
        copy = BiboCopy.query.filter_by(id=request.form.get("copy_id", type=int), owner_id=owner_id, active=True).first_or_404()
        copy.location_id = location.id
        log_activity("copy_moved", "bibo_copy", copy.id, f"{copy.edition.work.title} nach „{location.name}“ verschoben.")
        db.session.commit(); flash("Exemplar dem Lagerort zugeordnet.", "success")
        return redirect(url_for("storage_location_detail", token=token))
    copies = BiboCopy.query.options(joinedload(BiboCopy.edition).joinedload(BiboEdition.work)).filter_by(owner_id=owner_id, active=True, location_id=location.id).order_by(BiboCopy.id).all()
    available = BiboCopy.query.options(joinedload(BiboCopy.edition).joinedload(BiboEdition.work)).filter_by(owner_id=owner_id, active=True, location_id=None).order_by(BiboCopy.id).limit(250).all()
    return render_template("storage_location_detail.html", location=location, copies=copies, available=available)


@app.route("/locations/<string:token>/qr.png")
@login_required
def storage_location_qr(token):
    location = StorageLocation.query.filter_by(token=token, owner_id=active_collection_user_id()).first_or_404()
    try:
        import qrcode
    except ImportError:
        abort(503)
    image = qrcode.make(url_for("storage_location_detail", token=location.token, _external=True))
    output = io.BytesIO(); image.save(output, format="PNG"); output.seek(0)
    return send_file(output, mimetype="image/png", download_name=f"bibo-lagerort-{location.id}.png")


@app.route("/locations/<string:token>/inventory", methods=["GET", "POST"])
@login_required
def storage_inventory(token):
    owner_id = active_collection_user_id(); location = StorageLocation.query.filter_by(token=token, owner_id=owner_id).first_or_404()
    copies = BiboCopy.query.options(joinedload(BiboCopy.edition).joinedload(BiboEdition.work)).filter_by(owner_id=owner_id, active=True, location_id=location.id).order_by(BiboCopy.id).all()
    if request.method == "POST":
        if effective_role() == "viewer": abort(403)
        found_ids = {int(value) for value in request.form.getlist("found") if value.isdigit()}
        session_row = InventorySession(owner_id=owner_id, location_id=location.id, expected_count=len(copies), found_count=sum(1 for copy in copies if copy.id in found_ids), state="finished", finished_at=utc_now())
        db.session.add(session_row); db.session.flush(); log_activity("inventory_finished", "inventory_session", session_row.id, f"Inventur „{location.name}“: {session_row.found_count}/{session_row.expected_count} gefunden."); db.session.commit()
        flash(f"Inventur abgeschlossen: {session_row.found_count} von {session_row.expected_count} Exemplaren gefunden.", "success")
        return redirect(url_for("storage_location_detail", token=token))
    return render_template("storage_inventory.html", location=location, copies=copies)


@app.route("/loans", methods=["GET", "POST"])
@login_required
def loans():
    owner_id = active_collection_user_id(); refresh_bibo_registry()
    if request.method == "POST":
        if effective_role() == "viewer": abort(403)
        copy = BiboCopy.query.filter_by(id=request.form.get("copy_id", type=int), owner_id=owner_id, active=True).first_or_404()
        borrower = " ".join((request.form.get("borrower") or "").split())[:160]
        if not borrower:
            flash("Bitte eine Person angeben.", "danger")
        else:
            try: due_at = date.fromisoformat(request.form.get("due_at")) if request.form.get("due_at") else None
            except ValueError: due_at = None
            loan = LoanRecord(owner_id=owner_id, copy_id=copy.id, borrower=borrower, due_at=due_at, notes=(request.form.get("notes") or "").strip() or None)
            db.session.add(loan); db.session.flush(); log_activity("loan_created", "loan", loan.id, f"{copy.edition.work.title} an {borrower} verliehen."); db.session.commit(); flash("Ausleihe gespeichert.", "success")
        return redirect(url_for("loans"))
    active = LoanRecord.query.options(joinedload(LoanRecord.copy).joinedload(BiboCopy.edition).joinedload(BiboEdition.work)).filter_by(owner_id=owner_id, returned_at=None).order_by(LoanRecord.due_at, LoanRecord.lent_at).all()
    copies = BiboCopy.query.options(joinedload(BiboCopy.edition).joinedload(BiboEdition.work)).filter_by(owner_id=owner_id, active=True, status="owned").order_by(BiboCopy.id).limit(500).all()
    return render_template("loans.html", active=active, copies=copies, today=local_datetime(utc_now()).date())


@app.route("/loans/<int:loan_id>/return", methods=["POST"])
@login_required
def loan_return(loan_id):
    if effective_role() == "viewer": abort(403)
    loan = LoanRecord.query.filter_by(id=loan_id, owner_id=active_collection_user_id(), returned_at=None).first_or_404()
    loan.returned_at = local_datetime(utc_now()).date(); log_activity("loan_returned", "loan", loan.id, f"{loan.copy.edition.work.title} zurückgegeben."); db.session.commit(); flash("Rückgabe gespeichert.", "success")
    return redirect(url_for("loans"))


@app.route("/goals/<int:goal_id>/delete", methods=["POST"])
@login_required
def goal_delete(goal_id):
    goal = CollectionGoal.query.filter_by(id=goal_id, collection_user_id=active_collection_user_id()).first_or_404()
    name = goal.name
    log_activity("goal_deleted", "collection_goal", goal.id, f"Sammlungsziel „{name}“ gelöscht.")
    db.session.delete(goal); db.session.commit(); flash("Sammlungsziel gelöscht.", "success")
    return redirect(url_for("goals"))


@app.route("/price-history")
@login_required
def price_history_page():
    snapshots = CollectorValueSnapshot.query.filter_by(collection_user_id=active_collection_user_id()).order_by(CollectorValueSnapshot.recorded_at).all()
    if not snapshots:
        snap=collector_total_value_snapshot(); db.session.commit(); snapshots=[snap] if snap else []
    collection_points=[{"date":h.recorded_at.strftime("%Y-%m-%dT%H:%M:%S"),"value":round(h.total_value_eur,2),"owned":h.owned_count,"valued":h.valued_count} for h in snapshots]
    return render_template("price_history.html", collection_points=collection_points)


@app.route("/franchises")
@login_required
def franchises():
    # One canonical overview prevents the historical Spielreihen page from
    # drifting away from Sammlung → Reihen & Sammlungen. Keep this route as a
    # bookmark-compatible redirect; franchise detail URLs remain unchanged.
    return redirect(url_for(
        "collector_collections", type="games",
        q=(request.args.get("q") or "").strip(),
        status=(request.args.get("status") or "all").strip(),
        valuation=(request.args.get("valuation") or "all").strip(),
        sort=(request.args.get("sort") or "name").strip(),
    ))
    query_text = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all").strip()
    valuation_filter = request.args.get("valuation", "all").strip()
    sort = request.args.get("sort", "name").strip()
    all_games = [g for g in Game.query.filter(Game.franchise.isnot(None), Game.franchise != "").order_by(Game.id).all() if game_is_physical_candidate(g)]
    all_entries = SeriesEntry.query.order_by(SeriesEntry.id).all()
    names = {canonical_franchise_name(g.franchise) for g in all_games}
    names.update(canonical_franchise_name(e.franchise) for e in all_entries)
    data = []
    for name in sorted(names, key=lambda value: _search_text(value)):
        franchise_games = [g for g in all_games if canonical_franchise_name(g.franchise) == name]
        if name == "FIFA":
            franchise_games.extend(g for g in Game.query.filter(db.or_(Game.title.ilike("FIFA%"), Game.title.ilike("EA SPORTS FC%"), Game.title.ilike("%FIFA World Cup%"), Game.title.ilike("UEFA Euro%"))).all() if g not in franchise_games and game_is_physical_candidate(g))
        entries = [e for e in all_entries if canonical_franchise_name(e.franchise) == name]
        if name in CURATED_SERIES:
            entries = [e for e in entries if e.external_source == "GameCollector"]
        catalog_keys = {canonical_series_item_key(name, g.title) for g in franchise_games}
        catalog_keys.update(canonical_series_item_key(name, e.title) for e in entries if external_is_physical_candidate(e))
        owned_keys = set()
        value = automatic_value = estimated_value = 0.0
        copy_count = valued_count = 0
        last_valued_at = None
        for game in franchise_games:
            owned_copies = [item for item in collection_items_for(game) if item.status == "owned"]
            if owned_copies:
                owned_keys.add(canonical_series_item_key(name, game.title))
            for item in owned_copies:
                copy_count += 1
                item_value = effective_value(item)
                if item_value is None:
                    continue
                item_value = float(item_value)
                valued_count += 1
                value += item_value
                if item.auto_value_eur is not None:
                    automatic_value += item_value
                    if item.auto_value_updated_at and (last_valued_at is None or item.auto_value_updated_at > last_valued_at):
                        last_valued_at = item.auto_value_updated_at
                else:
                    estimated_value += item_value
        total = len(catalog_keys)
        owned = len(owned_keys & catalog_keys)
        pct = 100 if total and owned == total else min(99, round(owned * 100 / total)) if total else 0
        data.append({"name":name, "total":total, "owned":owned, "missing":max(0,total-owned), "pct":pct,
                     "value":round(value,2), "automatic_value":round(automatic_value,2), "estimated_value":round(estimated_value,2),
                     "copy_count":copy_count, "valued_count":valued_count, "last_valued_at":last_valued_at,
                     "synced":len(entries), "auto_count":sum(1 for g in franchise_games if g.franchise_source and g.franchise_source != "manual")})
    if query_text:
        needle = _search_text(query_text)
        data = [row for row in data if needle in _search_text(row["name"])]
    if status_filter == "complete": data = [row for row in data if row["total"] and row["owned"] == row["total"]]
    elif status_filter == "incomplete": data = [row for row in data if 0 < row["owned"] < row["total"]]
    elif status_filter == "not_started": data = [row for row in data if row["owned"] == 0]
    elif status_filter == "started": data = [row for row in data if row["owned"] > 0]
    if valuation_filter == "valued": data = [row for row in data if row["value"] > 0]
    elif valuation_filter == "unvalued": data = [row for row in data if row["copy_count"] and row["valued_count"] == 0]
    elif valuation_filter == "partial": data = [row for row in data if row["valued_count"] < row["copy_count"]]
    if sort == "name_desc": data.sort(key=lambda row:_search_text(row["name"]),reverse=True)
    elif sort == "value_desc": data.sort(key=lambda row:(row["value"],_search_text(row["name"])),reverse=True)
    elif sort == "value_asc": data.sort(key=lambda row:(row["value"] <= 0,row["value"],_search_text(row["name"])))
    elif sort == "progress_desc": data.sort(key=lambda row:(row["pct"],row["owned"]),reverse=True)
    elif sort == "progress_asc": data.sort(key=lambda row:(row["pct"],_search_text(row["name"])))
    elif sort == "missing_desc": data.sort(key=lambda row:(row["missing"],row["total"]),reverse=True)
    elif sort == "updated_desc": data.sort(key=lambda row:row["last_valued_at"] or datetime.min,reverse=True)
    else: data.sort(key=lambda row:_search_text(row["name"]))
    summary = {"count":len(data), "complete":sum(1 for row in data if row["total"] and row["owned"]==row["total"]),
               "incomplete":sum(1 for row in data if 0<row["owned"]<row["total"]), "not_started":sum(1 for row in data if row["owned"]==0),
               "value":round(sum(row["value"] for row in data),2)}
    unassigned = Game.query.filter(Game.series_status == "unreviewed").count()
    standalone = Game.query.filter(Game.series_status == "standalone").count()
    latest_series_scan = SeriesScanRun.query.filter_by(collection_user_id=active_collection_user_id()).order_by(SeriesScanRun.started_at.desc()).first()
    return render_template("franchises.html", franchises=data, unassigned=unassigned, standalone=standalone,
                           latest_series_scan=latest_series_scan, summary=summary, q=query_text,
                           status_filter=status_filter, valuation_filter=valuation_filter, sort=sort)

    # Legacy implementation retained below for database compatibility reference.
    rows = db.session.query(
        Game.franchise,
        db.func.count(db.distinct(Game.id)).label("total"),
        db.func.count(db.distinct(db.case((db.and_(CollectionItem.status == "owned", CollectionItem.user_id == active_collection_user_id()), Game.id)))).label("owned")
    ).outerjoin(CollectionItem, CollectionItem.game_id == Game.id).filter(
        Game.franchise.isnot(None), Game.franchise != ""
    ).group_by(Game.franchise).order_by(Game.franchise).all()
    data = []
    for name, local_total, owned in rows:
        external_total = SeriesEntry.query.filter_by(franchise=name).count()
        total = max(local_total, external_total)
        pct = round((owned / total) * 100) if total else 0
        auto_count = Game.query.filter(Game.franchise == name, Game.franchise_source.isnot(None), Game.franchise_source != "manual").count()
        synced = SeriesEntry.query.filter_by(franchise=name).count()
        data.append({"name": name, "total": total, "local_total": local_total, "owned": owned, "pct": pct, "auto_count": auto_count, "synced": synced})

    # v1.0.1: LEGO is an umbrella series. Include every catalog title beginning
    # with LEGO even if older/manual metadata stored a sub-series as franchise.
    lego_games = Game.query.filter(Game.title.ilike("LEGO %")).all()
    if lego_games:
        lego_ids = {g.id for g in lego_games}
        lego_owned_ids = {row.game_id for row in CollectionItem.query.filter(
            CollectionItem.user_id == active_collection_user_id(),
            CollectionItem.status == "owned",
            CollectionItem.game_id.in_(lego_ids)
        ).all()}
        lego_external = SeriesEntry.query.filter_by(franchise="LEGO", external_source="GameCollector").count()
        lego_local_total = len(lego_ids)
        lego_owned = len(lego_owned_ids)
        lego_total = max(lego_local_total, lego_external)
        lego_row = next((row for row in data if row["name"] == "LEGO"), None)
        lego_payload = {
            "name":"LEGO", "total":lego_total, "local_total":lego_local_total,
            "owned":lego_owned, "pct":round(lego_owned * 100 / lego_total) if lego_total else 0,
            "auto_count":sum(1 for g in lego_games if g.franchise_source and g.franchise_source != "manual"),
            "synced":lego_external
        }
        if lego_row:
            lego_row.update(lego_payload)
        else:
            data.append(lego_payload)
            data.sort(key=lambda row: row["name"].casefold())
    # v1.0.2 Formula 1 umbrella row (F1 / Formula 1 / Formula One).
    f1_games = [g for g in Game.query.order_by(Game.id).all() if infer_franchise_name(g.title) == "Formula 1 / F1" or g.franchise == "Formula 1 / F1"]
    if f1_games:
        f1_ids = {g.id for g in f1_games}
        f1_owned = db.session.query(CollectionItem.game_id).filter(CollectionItem.user_id == active_collection_user_id(), CollectionItem.status == "owned", CollectionItem.game_id.in_(f1_ids)).distinct().count()
        f1_external = SeriesEntry.query.filter_by(franchise="Formula 1 / F1", external_source="GameCollector").count()
        payload = {"name":"Formula 1 / F1", "total":max(len(f1_ids), f1_external), "local_total":len(f1_ids), "owned":f1_owned,
                   "pct":round(f1_owned*100/max(len(f1_ids),f1_external)) if max(len(f1_ids),f1_external) else 0, "auto_count":len(f1_ids), "synced":f1_external}
        row = next((x for x in data if x["name"] == "Formula 1 / F1"), None)
        if row: row.update(payload)
        else: data.append(payload); data.sort(key=lambda x: x["name"].casefold())

    unassigned = Game.query.filter(Game.series_status == "unreviewed").count()
    standalone = Game.query.filter(Game.series_status == "standalone").count()
    latest_series_scan = SeriesScanRun.query.filter_by(collection_user_id=active_collection_user_id()).order_by(SeriesScanRun.started_at.desc()).first()
    return render_template("franchises.html", franchises=data, unassigned=unassigned, standalone=standalone,
                           rawg_enabled=bool(os.environ.get("RAWG_API_KEY", "").strip()), latest_series_scan=latest_series_scan)


@app.route("/franchises/rebuild", methods=["POST"])
@login_required
def franchises_rebuild():
    overwrite_auto = request.form.get("refresh_auto") == "1"
    owner_id = active_collection_user_id()
    owned_game_ids = (db.session.query(CollectionItem.game_id)
                      .filter(CollectionItem.user_id == owner_id,
                              CollectionItem.status == "owned",
                              CollectionItem.ownership_format != "digital")
                      .distinct())
    games_to_check = Game.query.filter(Game.id.in_(owned_game_ids)).order_by(Game.id).all()
    assigned = 0
    unchanged = 0
    unresolved = 0
    for game in games_to_check:
        if game.franchise and (game.franchise_source == "manual" or not overwrite_auto):
            unchanged += 1
            continue
        detected, source_name = infer_franchise_from_rawg(game)
        if detected:
            game.franchise = detected
            game.franchise_source = source_name or "auto-rule"
            game.series_status = "series"
            if detected == "LEGO" and not game.series_group:
                game.series_group = infer_lego_series_group(game.title)
            assigned += 1
        else:
            if overwrite_auto and game.franchise_source != "manual":
                game.franchise = None
                game.franchise_source = None
            unresolved += 1
    db.session.commit()
    flash(f"Serienerkennung abgeschlossen: {assigned} automatisch zugeordnet, {unchanged} beibehalten, {unresolved} ohne sichere Serie.", "success" if assigned else "warning")
    return redirect(url_for("collector_collections", type="games"))


SERIES_SEARCH_ALIASES = {
    # FIFA wurde ab 2023 unter dem Namen EA Sports FC fortgeführt. Beide Suchbegriffe
    # werden angeboten, die lokale Kollektion bleibt aber unter dem vom Nutzer gewählten Namen.
    "FIFA": ["FIFA", "EA Sports FC"],
    "EA Sports FC": ["EA Sports FC", "FIFA"],
}


def rawg_series_seed_candidates(name, limit=16):
    queries = SERIES_SEARCH_ALIASES.get(name, [name])
    seen = set()
    candidates = []
    for query in queries:
        rows, status = rawg_game_search(query, limit=12)
        if status != "ok":
            continue
        for row in rows:
            source_id = str(row.get("source_id") or "").strip()
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            row = dict(row)
            row["search_query"] = query
            candidates.append(row)
    # Die RAWG-Suche ist bereits lokal gerankt. Exakte Serienpräfixe zusätzlich bevorzugen.
    n = _search_text(name)
    candidates.sort(key=lambda r: (
        0 if _search_text(r.get("name", "")) == n else 1,
        0 if _search_text(r.get("name", "")).startswith(n) else 1,
        -(int(r.get("year") or 0)),
        r.get("name", "")
    ))
    return candidates[:limit]


def sync_rawg_series_rows(name, seed_ids, local_seeds=None):
    discovered = {}
    for seed_id in seed_ids[:4]:
        for row in rawg_game_series_rows(seed_id):
            discovered[row["id"]] = row
    for seed in (local_seeds or []):
        if seed.external_id:
            discovered.setdefault(str(seed.external_id), {
                "id": str(seed.external_id), "name": seed.title,
                "release_year": seed.release_year, "cover_url": seed.cover_url,
                "platforms": [seed.console.name]
            })
    added = 0
    updated = 0
    for row in discovered.values():
        entry = SeriesEntry.query.filter_by(franchise=name, external_source="RAWG", external_id=row["id"]).first()
        if not entry:
            entry = SeriesEntry(franchise=name, external_source="RAWG", external_id=row["id"], title=row["name"])
            db.session.add(entry)
            added += 1
        else:
            updated += 1
        entry.title = row["name"]
        entry.release_year = row.get("release_year")
        entry.cover_url = archived_or_original_image(row.get("cover_url"))
        entry.platforms = ", ".join(row.get("platforms") or []) or None
        entry.series_group, entry.series_generation = classify_series_item(name, row["name"])
    db.session.commit()
    return added, updated, len(discovered)


@app.route("/franchises/scan-all", methods=["POST"])
@login_required
def franchises_scan_all():
    owner_id = active_collection_user_id()
    active = SeriesScanRun.query.filter(SeriesScanRun.collection_user_id == owner_id, SeriesScanRun.state.in_(["queued", "running"])).order_by(SeriesScanRun.started_at.desc()).first()
    if active:
        flash("Ein Serienabgleich läuft bereits.", "warning")
        return redirect(url_for("series_scan_detail", run_id=active.id))
    names = sorted({row["name"] for row in _game_franchise_overview_rows(owner_id)}, key=str.casefold)
    run = SeriesScanRun(collection_user_id=owner_id, state="queued", total_count=len(names), message="Serienabgleich wartet auf Start")
    db.session.add(run); db.session.commit(); rid = run.id

    def worker(app_obj, run_id, franchises_to_scan):
        with app_obj.app_context():
            run = db.session.get(SeriesScanRun, run_id)
            try:
                run.state = "running"; run.message = "Serienabgleich läuft"; db.session.commit()
                total_added = total_updated = failed = 0
                rawg_enabled = bool(os.environ.get("RAWG_API_KEY", "").strip())
                for pos, name in enumerate(franchises_to_scan, 1):
                    run = db.session.get(SeriesScanRun, run_id)
                    run.current_franchise = name; run.checked_count = pos - 1; db.session.commit()
                    added = updated = 0; notes = []
                    try:
                        ca, cu = ensure_curated_series_entries(name)
                        added += ca; updated += cu
                        if ca or cu:
                            notes.append(f"lokaler Serienkatalog: {ca} neu, {cu} aktualisiert")
                        # RAWG is enrichment only. Existing local RAWG seeds may discover additional siblings.
                        if name in CURATED_SERIES:
                            notes.append("lokaler Katalog ist maßgeblich")
                        elif rawg_enabled:
                            seeds = Game.query.filter(Game.franchise == name, Game.external_source == "RAWG", Game.external_id.isnot(None)).order_by(Game.id).limit(4).all()
                            seed_ids = [str(g.external_id) for g in seeds if g.external_id]
                            if seed_ids:
                                ra, ru, discovered = sync_rawg_series_rows(name, seed_ids, seeds)
                                added += ra; updated += ru
                                notes.append(f"RAWG: {discovered} Treffer")
                            else:
                                notes.append("kein RAWG-Ausgangspunkt")
                        else:
                            notes.append("RAWG nicht konfiguriert")
                        total_added += added; total_updated += updated
                        status = "Neue Titel" if added else "Geprüft"
                        db.session.add(SeriesScanLog(series_scan_run_id=run_id, position=pos, franchise=name, status=status, added_count=added, updated_count=updated, message=" · ".join(notes)))
                    except Exception as exc:
                        db.session.rollback(); failed += 1
                        run = db.session.get(SeriesScanRun, run_id)
                        db.session.add(SeriesScanLog(series_scan_run_id=run_id, position=pos, franchise=name, status="Fehler", message=str(exc)[:300]))
                    run = db.session.get(SeriesScanRun, run_id)
                    run.checked_count = pos; run.added_count = total_added; run.updated_count = total_updated; run.failed_count = failed
                    db.session.commit()
                run = db.session.get(SeriesScanRun, run_id)
                run.finished_at = utc_now(); run.state = "finished"; run.current_franchise = None; run.message = "Serienabgleich abgeschlossen"; db.session.commit()
            except Exception as exc:
                db.session.rollback(); run = db.session.get(SeriesScanRun, run_id)
                if run:
                    run.finished_at = utc_now(); run.state = "failed"; run.message = f"Serienabgleich abgebrochen: {exc}"; db.session.commit()
                app_obj.logger.exception("series scan failed")
    threading.Thread(target=worker, args=(app, rid, names), daemon=True, name=f"series-scan-{rid}").start()
    return redirect(url_for("series_scan_detail", run_id=rid))


@app.route("/franchises/scan/<int:run_id>")
@login_required
def series_scan_detail(run_id):
    run = db.session.get(SeriesScanRun, run_id) or abort(404)
    if run.collection_user_id not in (None, active_collection_user_id()): abort(403)
    logs = SeriesScanLog.query.filter_by(series_scan_run_id=run.id).order_by(SeriesScanLog.position.desc()).limit(300).all()
    return render_template("series_scan.html", run=run, logs=logs)


@app.route("/api/franchises/scan/<int:run_id>")
@login_required
def series_scan_status_api(run_id):
    run = db.session.get(SeriesScanRun, run_id) or abort(404)
    logs = SeriesScanLog.query.filter_by(series_scan_run_id=run.id).order_by(SeriesScanLog.position.desc()).limit(100).all()
    total = run.total_count or 0; checked = run.checked_count or 0
    pct = min(100, round(checked * 100 / total)) if total else 0
    return jsonify({"id":run.id,"state":run.state,"checked":checked,"total":total,"pct":pct,"current":run.current_franchise or "","added":run.added_count,"updated":run.updated_count,"failed":run.failed_count,"message":run.message or "","logs":[{"position":x.position,"franchise":x.franchise,"status":x.status,"added":x.added_count,"updated":x.updated_count,"message":x.message or ""} for x in logs]})


@app.route("/franchises/<path:name>/sync", methods=["POST"])
@login_required
def franchise_sync(name):
    if not os.environ.get("RAWG_API_KEY", "").strip():
        flash("RAWG_API_KEY ist nicht konfiguriert.", "warning")
        return redirect(url_for("franchise_detail", name=name))

    # Wenn der Nutzer im Fallback-Dialog einen RAWG-Ausgangspunkt gewählt hat,
    # synchronisieren wir direkt über diese RAWG-ID.
    selected_seed = request.form.get("seed_id", "").strip()
    if selected_seed:
        added, updated, discovered = sync_rawg_series_rows(name, [selected_seed])
        if not discovered:
            flash("RAWG hat zu diesem Ausgangstitel keine Reihenliste geliefert. Bitte einen anderen Treffer wählen.", "warning")
            return redirect(url_for("franchise_seed_select", name=name))
        flash(f"RAWG-Reihe synchronisiert: {added} neue Titel, {updated} aktualisiert.", "success")
        return redirect(url_for("franchise_detail", name=name))

    seeds = Game.query.filter(Game.franchise == name, Game.external_source == "RAWG", Game.external_id.isnot(None)).order_by(Game.id).all()
    if not seeds:
        # v0.4.1: Kein harter Abbruch mehr. Die Reihe wird anhand ihres Namens bei RAWG gesucht.
        return redirect(url_for("franchise_seed_select", name=name))

    seed_ids = [str(seed.external_id) for seed in seeds if seed.external_id]
    added, updated, discovered = sync_rawg_series_rows(name, seed_ids, seeds)
    if not discovered:
        return redirect(url_for("franchise_seed_select", name=name))
    flash(f"RAWG-Reihe synchronisiert: {added} neue Titel, {updated} aktualisiert.", "success")
    return redirect(url_for("franchise_detail", name=name))


@app.route("/franchises/<path:name>/rawg-seed")
@login_required
def franchise_seed_select(name):
    if not os.environ.get("RAWG_API_KEY", "").strip():
        flash("RAWG_API_KEY ist nicht konfiguriert.", "warning")
        return redirect(url_for("franchise_detail", name=name))
    candidates = rawg_series_seed_candidates(name)
    return render_template("franchise_seed_select.html", name=name, candidates=candidates,
                           aliases=SERIES_SEARCH_ALIASES.get(name, [name]))


@app.route("/franchises/<path:name>")
@login_required
def franchise_detail(name):
    name_key = _search_text(name)
    if name_key == "lego":
        games = Game.query.filter(db.or_(Game.franchise == "LEGO", Game.title.ilike("LEGO %"))).order_by(Game.release_year.asc().nullslast(), Game.title, Game.console_id).all()
    elif name_key in {"formula 1 f1", "formula 1", "f1", "formula one"}:
        games = Game.query.filter(db.or_(Game.franchise == "Formula 1 / F1", db.or_(Game.title.ilike("F1 %"), Game.title.ilike("Formula 1 %"), Game.title.ilike("Formula One %")))).order_by(Game.release_year.asc().nullslast(), Game.title, Game.console_id).all()
    elif name_key in {"the sims", "die sims"}:
        games = Game.query.filter(db.or_(Game.franchise == "The Sims", Game.title.ilike("The Sims%"), Game.title.ilike("Die Sims%"), Game.title.ilike("MySims%"))).order_by(Game.release_year.asc().nullslast(), Game.title, Game.console_id).all()
    elif name_key == "singstar":
        games = Game.query.filter(db.or_(Game.franchise == "SingStar", Game.title.ilike("SingStar%"))).order_by(Game.release_year.asc().nullslast(), Game.title, Game.console_id).all()
    elif name_key in {"donkey kong", "donkey kong country"}:
        name = "Donkey Kong"
        games = Game.query.filter(db.or_(Game.franchise.in_(["Donkey Kong", "Donkey Kong Country"]), Game.title.ilike("Donkey Kong%"), Game.title.ilike("DK:%"))).order_by(Game.release_year.asc().nullslast(), Game.title, Game.console_id).all()
    elif name_key in {"fussball manager", "fifa manager"}:
        name = "Fußball Manager"
        games = Game.query.filter(db.or_(
            Game.franchise.in_(["Fußball Manager", "Fussball Manager", "FIFA Manager"]),
            Game.title.ilike("Fußball Manager%"), Game.title.ilike("Fussball Manager%"), Game.title.ilike("FIFA Manager%"),
        )).order_by(Game.release_year.asc().nullslast(), Game.title, Game.console_id).all()
    else:
        games = Game.query.filter(Game.franchise == name).order_by(Game.release_year.asc().nullslast(), Game.title, Game.console_id).all()
    games = [g for g in games if game_is_physical_candidate(g)]
    external_query = SeriesEntry.query.filter_by(franchise=name)
    if name in CURATED_SERIES:
        external_query = external_query.filter_by(external_source="GameCollector")
    external = external_query.order_by(SeriesEntry.release_year.asc().nullslast(), SeriesEntry.title).all()

    def owned_game(g):
        return any(item.status == "owned" for item in collection_items_for(g))

    series_items = []
    # Pokémon is curated locally because RAWG frequently bundles physically
    # separate editions (Diamond/Pearl, X/Y, etc.) into one metadata record.
    if _search_text(name) == "pokemon":
        def local_matches(aliases):
            alias_keys = [_search_text(a) for a in aliases]
            matches = []
            for g in games:
                key = _search_text(g.title)
                if any(key == a or key.startswith(a + " edition") or key.startswith(a + " version") for a in alias_keys):
                    matches.append(g)
            return matches

        def external_visual(aliases):
            alias_keys = [_search_text(a) for a in aliases]
            for e in external:
                ek = _search_text(e.title)
                if any(a in ek or ek in a for a in alias_keys):
                    return e
            return None

        for row in POKEMON_CURATED_SERIES:
            matches = local_matches(row["aliases"])
            visual = external_visual(row["aliases"])
            cover = next((g.cover_url for g in matches if g.cover_url), None) or (visual.cover_url if visual else None)
            series_items.append({
                "title": row["title"], "release_year": row.get("year"), "cover_url": cover,
                "platforms": row.get("platforms"), "owned": any(owned_game(g) for g in matches),
                "owned_variants": sum(1 for g in matches if owned_game(g)), "local_games": matches,
                "external_id": None, "series_group": "Hauptreihe", "series_generation": row.get("generation")
            })
        for row in POKEMON_CURATED_SPINOFFS:
            matches = local_matches(row["aliases"])
            visual = external_visual(row["aliases"])
            cover = next((g.cover_url for g in matches if g.cover_url), None) or (visual.cover_url if visual else None)
            series_items.append({
                "title": row["title"], "release_year": row.get("year"), "cover_url": cover,
                "platforms": row.get("platforms"), "owned": any(owned_game(g) for g in matches),
                "owned_variants": sum(1 for g in matches if owned_game(g)), "local_games": matches,
                "external_id": None, "series_group": row["group"], "series_generation": None
            })
        # Keep locally catalogued Pokémon titles that the curated checklist does
        # not yet know, but never lose them from the series page.
        used_ids = {g.id for item in series_items for g in item["local_games"]}
        for g in games:
            if g.id in used_ids:
                continue
            group, generation = classify_series_item(name, g.title)
            series_items.append({"title": g.title, "release_year": g.release_year, "cover_url": g.cover_url,
                                 "platforms": g.console.name, "owned": owned_game(g), "owned_variants": 1 if owned_game(g) else 0,
                                 "local_games": [g], "external_id": None,
                                 "series_group": group, "series_generation": generation})
        total = len(series_items)
        owned_total = sum(1 for x in series_items if x["owned"])
        synced = bool(external)
    else:
        owned = sum(1 for g in games if owned_game(g))
        local_by_external = {}
        for g in games:
            if g.external_source and g.external_id:
                local_by_external.setdefault((str(g.external_source).strip().lower(), str(g.external_id).strip()), []).append(g)
        used_local_ids = set()
        # v2.0.1: the collector is physical-only for every franchise, not only
        # selected curated series.
        external_rows = [e for e in external if external_is_physical_candidate(e)]
        if external_rows:
            for e in external_rows:
                matches, match_method = local_series_match(e, games, local_by_external)
                used_local_ids.update(g.id for g in matches)
                is_owned = any(owned_game(g) for g in matches)
                group, generation = classify_series_item(name, e.title)
                series_items.append({"title": e.title, "release_year": e.release_year, "cover_url": e.cover_url, "platforms": e.platforms,
                                     "owned": is_owned, "owned_variants": sum(1 for g in matches if owned_game(g)), "local_games": matches,
                                     "external_id": e.external_id, "series_group": e.series_group or group,
                                     "series_generation": e.series_generation or generation, "match_method": match_method})
            # Critical v1.0.2 behavior: an owned/local title is never lost just because RAWG's
            # series endpoint omitted it or used another regional title. Append unmatched local
            # catalogue entries and expose them as local catalogue matches.
            for g in games:
                if g.id in used_local_ids:
                    continue
                group, generation = classify_series_item(name, g.title)
                series_items.append({"title": g.title, "release_year": g.release_year, "cover_url": g.cover_url, "platforms": g.console.name,
                                     "owned": owned_game(g), "owned_variants": 1 if owned_game(g) else 0, "local_games": [g], "external_id": None,
                                     "series_group": g.series_group or group, "series_generation": g.series_generation or generation,
                                     "match_method": "Lokaler Katalog"})
            total = len(series_items)
            owned_total = sum(1 for x in series_items if x["owned"])
        else:
            for g in games:
                group, generation = classify_series_item(name, g.title)
                series_items.append({"title": g.title, "release_year": g.release_year, "cover_url": g.cover_url, "platforms": g.console.name,
                                     "owned": owned_game(g), "owned_variants": 1 if owned_game(g) else 0, "local_games": [g], "external_id": None,
                                     "series_group": g.series_group or group, "series_generation": g.series_generation or generation,
                                     "match_method": "Lokaler Katalog"})
            total = len(series_items)
            owned_total = owned
        synced = bool(external)

    # v1.2.4: collapse regional aliases and platform-specific metadata rows before
    # calculating ownership. External IDs are useful hints, but never define a
    # separate series part when the canonical title is identical.
    merged_items = []
    by_key = {}
    for item in series_items:
        key = canonical_series_item_key(name, item.get("title"))
        target = by_key.get(key)
        if target is None:
            target = item
            target["canonical_key"] = key
            by_key[key] = target
            merged_items.append(target)
            continue
        combined = {g.id: g for g in (target.get("local_games") or []) + (item.get("local_games") or [])}
        target["local_games"] = list(combined.values())
        target["owned"] = bool(target.get("owned") or item.get("owned"))
        target["owned_variants"] = sum(1 for g in target["local_games"] if owned_game(g))
        if not target.get("cover_url") and item.get("cover_url"):
            target["cover_url"] = item["cover_url"]
        if not target.get("platforms") and item.get("platforms"):
            target["platforms"] = item["platforms"]
    series_items = merged_items

    # Manual corrections always win over title/provider matching. The physical
    # copy remains untouched in inventory and can be re-enabled at any time.
    ownership_exclusions = _series_ownership_exclusions(active_collection_user_id(), name)
    for item in series_items:
        item["override_anchor"] = hashlib.sha1(str(item.get("canonical_key") or "").encode("utf-8")).hexdigest()[:10]
        item["manual_not_owned"] = item.get("canonical_key") in ownership_exclusions
        if item["manual_not_owned"]:
            item["owned"] = False
            item["owned_variants"] = 0

    # Canonical display names for known regional FIFA titles.
    if _search_text(name) == "fifa":
        display_names = {"fifa 97": "FIFA 97", "fifa 2003": "FIFA 2003", "fifa 2004": "FIFA 2004", "fifa 2005": "FIFA 2005"}
        for item in series_items:
            item["title"] = display_names.get(item.get("canonical_key"), item.get("title"))

    total = len(series_items)
    owned_total = sum(1 for x in series_items if x.get("owned"))

    # Prefer the cover and primary link of the technically oldest local platform.
    for item in series_items:
        locals_ = list(item.get("local_games") or [])
        if locals_:
            locals_.sort(key=lambda g: (series_platform_age(g), g.release_year is None, g.release_year or 9999, g.id))
            item["local_games"] = locals_
            local_cover = next((g.cover_url for g in locals_ if g.cover_url), None)
            if local_cover:
                item["cover_url"] = local_cover

    # Series valuation: every owned physical copy contributes once. Automatic
    # market values win; the user's estimate is the fallback.
    series_value = series_auto_value = series_estimated_value = 0.0
    series_copy_count = series_valued_count = 0
    series_last_valued_at = None
    for item in series_items:
        if item.get("manual_not_owned"):
            item["market_value"] = 0.0
            item["price_rows"] = []
            continue
        platform_totals = {}
        item_value = 0.0
        for game in item.get("local_games") or []:
            for copy in collection_items_for(game):
                if copy.status != "owned" or copy.ownership_format == "digital":
                    continue
                series_copy_count += 1
                platform = game.console.name
                row = platform_totals.setdefault(platform, {"platform": platform, "copies": 0, "value": 0.0, "automatic": 0.0, "estimated": 0.0})
                row["copies"] += 1
                value = effective_value(copy)
                if value is None:
                    continue
                value = float(value)
                row["value"] += value
                item_value += value
                series_value += value
                series_valued_count += 1
                if copy.auto_value_eur is not None:
                    row["automatic"] += value
                    series_auto_value += value
                    if copy.auto_value_updated_at and (series_last_valued_at is None or copy.auto_value_updated_at > series_last_valued_at):
                        series_last_valued_at = copy.auto_value_updated_at
                else:
                    row["estimated"] += value
                    series_estimated_value += value
        item["market_value"] = round(item_value, 2)
        item["price_rows"] = sorted(platform_totals.values(), key=lambda row: (SERIES_PLATFORM_AGE.get(_search_text(row["platform"]), 9999), row["platform"]))
    completion_pct = 100 if total and owned_total == total else min(99, round(owned_total * 100 / total)) if total else 0

    grouped = {}
    for item in series_items:
        group = item.get("series_group") or "Hauptreihe"
        generation = item.get("series_generation")
        bucket = grouped.setdefault(group, {"name": group, "items": [], "owned": 0, "total": 0, "generations": {}})
        bucket["items"].append(item)
        bucket["total"] += 1
        bucket["owned"] += 1 if item["owned"] else 0
        if generation:
            gen = bucket["generations"].setdefault(generation, {"name": generation, "items": [], "owned": 0, "total": 0})
            gen["items"].append(item)
            gen["total"] += 1
            gen["owned"] += 1 if item["owned"] else 0
    group_order = {"Hauptreihe": 0, "Mystery Dungeon": 10, "Pokémon Ranger": 11, "Pokémon Snap": 12, "Pokémon Stadium": 13,
                   "Pokémon Colosseum / XD": 14, "Pokémon Pinball": 15, "Pokémon Rumble": 16, "PokéPark": 17, "Pokémon TCG": 18,
                   "Weitere Pokémon-Spiele": 90}
    series_groups = sorted(grouped.values(), key=lambda x: (group_order.get(x["name"], 50), x["name"]))
    roman_order = {"I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6,"VII":7,"VIII":8,"IX":9}
    for group in series_groups:
        group["generation_rows"] = sorted(group["generations"].values(), key=lambda x: roman_order.get(x["name"], 99))
        generation_ids = {id(item) for gen in group["generation_rows"] for item in gen["items"]}
        group["ungrouped_items"] = [item for item in group["items"] if id(item) not in generation_ids]
    only_missing = request.args.get("missing") == "1"
    return render_template("franchise_detail.html", name=name, games=games, series_items=series_items, series_groups=series_groups,
                           owned=owned_total, total=total, rawg_enabled=bool(os.environ.get("RAWG_API_KEY", "").strip()), synced=synced,
                           only_missing=only_missing, curated=(name in CURATED_SERIES), completion_pct=completion_pct,
                           series_value=round(series_value, 2), series_auto_value=round(series_auto_value, 2),
                           series_estimated_value=round(series_estimated_value, 2), series_copy_count=series_copy_count,
                           series_valued_count=series_valued_count, series_last_valued_at=series_last_valued_at)


@app.route("/franchises/<path:name>/manage", methods=["GET", "POST"])
@login_required
def franchise_manage(name):
    source_name = name.strip()
    if request.method == "POST":
        target_name = request.form.get("target_name", "").strip()
        if not target_name:
            flash("Bitte einen Seriennamen oder eine Zielserie eintragen.", "danger")
            return redirect(url_for("franchise_manage", name=source_name))
        if _search_text(target_name) == _search_text(source_name):
            flash("Quell- und Zielserie sind identisch.", "warning")
            return redirect(url_for("franchise_manage", name=source_name))
        games = Game.query.filter(Game.franchise == source_name).all()
        entries = SeriesEntry.query.filter(SeriesEntry.franchise == source_name).order_by(SeriesEntry.id).all()
        for game in games:
            game.franchise = target_name
            game.series_status = "series"
            if game.franchise_source != "manual": game.franchise_source = "manual"
        for entry in entries:
            duplicate = SeriesEntry.query.filter_by(franchise=target_name, external_source=entry.external_source, external_id=entry.external_id).first()
            if duplicate:
                for field in ("title", "release_year", "cover_url", "platforms", "series_group", "series_generation"):
                    if not getattr(duplicate, field, None) and getattr(entry, field, None): setattr(duplicate, field, getattr(entry, field))
                db.session.delete(entry)
            else:
                entry.franchise = target_name
        log_activity("franchise_merged", "franchise", None, f"Serie „{source_name}“ wurde nach „{target_name}“ verschoben.")
        db.session.commit()
        flash(f"Serie „{source_name}“ wurde mit „{target_name}“ zusammengeführt.", "success")
        return redirect(url_for("franchise_detail", name=target_name))
    targets = [row[0] for row in db.session.query(Game.franchise).filter(Game.franchise.isnot(None), Game.franchise != "", Game.franchise != source_name).distinct().order_by(Game.franchise).all()]
    return render_template("franchise_manage.html", name=source_name, targets=targets,
                           game_count=Game.query.filter(Game.franchise == source_name).count(),
                           entry_count=SeriesEntry.query.filter(SeriesEntry.franchise == source_name).count())


@app.route("/find")
@login_required
def universal_search():
    q=(request.args.get("q") or "").strip()

    # The dashboard search is the single entry point for the whole Collector.
    # Numeric product identifiers must use the central identify pipeline instead
    # of being treated as plain text that only searches the local inventory.
    # This keeps EAN/UPC/GTIN/ISBN behavior consistent for games, movies/TV,
    # books, music, hardware/accessories and future collection modules.
    barcode_candidate = clean_barcode(q)
    barcode_like = bool(re.fullmatch(r"[0-9\s-]+", q))
    if barcode_like and barcode_candidate and len(barcode_candidate) in {8, 10, 12, 13, 14}:
        return redirect(url_for("collector_identify", barcode=barcode_candidate))

    selected=(request.args.get("type") or "all").strip().lower()
    sort=(request.args.get("sort") or "relevance").strip().lower()
    if sort not in {"relevance","name","newest","value"}: sort="relevance"
    tcg_filter=(request.args.get("tcg") or "").strip()
    allowed={"all","series","games","tv","movies","books","music","cards","hardware","accessories"}
    if selected not in allowed: selected="all"
    if not q: return redirect(url_for("collector_home"))
    like=f"%{q}%"; uid=active_collection_user_id()
    games=(Game.query.outerjoin(CollectionItem, db.and_(CollectionItem.game_id==Game.id, CollectionItem.user_id==uid))
           .filter(db.or_(Game.title.ilike(like),Game.barcode.ilike(like),Game.product_code.ilike(like),Game.edition.ilike(like),Game.publisher.ilike(like),Game.developer.ilike(like),Game.franchise.ilike(like),CollectionItem.storage_location.ilike(like),CollectionItem.tags.ilike(like),CollectionItem.notes.ilike(like)))
           .distinct().order_by(Game.title).limit(60).all())
    collector=CollectorItem.query.filter(CollectorItem.user_id==uid, db.or_(CollectorItem.title.ilike(like),CollectorItem.barcode.ilike(like),CollectorItem.edition.ilike(like),CollectorItem.media_type.ilike(like),CollectorItem.card_set.ilike(like),CollectorItem.card_number.ilike(like),CollectorItem.tcg_game.ilike(like),CollectorItem.storage_location.ilike(like),CollectorItem.notes.ilike(like))).order_by(CollectorItem.added_at.desc()).limit(120).all()
    hardware=(HardwareModel.query.join(Console).outerjoin(HardwareItem, db.and_(HardwareItem.hardware_model_id==HardwareModel.id, HardwareItem.user_id==uid))
              .filter(db.or_(HardwareModel.name.ilike(like),HardwareModel.model_number.ilike(like),HardwareModel.revision.ilike(like),HardwareModel.color.ilike(like),Console.name.ilike(like),HardwareItem.serial_number.ilike(like),HardwareItem.storage_location.ilike(like),HardwareItem.notes.ilike(like)))
              .distinct().order_by(HardwareModel.name).limit(40).all())
    accessories=scoped_accessory_query().filter(db.or_(AccessoryItem.name.ilike(like),AccessoryItem.manufacturer.ilike(like),AccessoryItem.model_number.ilike(like),AccessoryItem.barcode.ilike(like),AccessoryItem.product_code.ilike(like),AccessoryItem.compatibility.ilike(like),AccessoryItem.storage_location.ilike(like),AccessoryItem.notes.ilike(like))).order_by(AccessoryItem.name).limit(40).all()
    needle = _search_text(q)
    series_results = [row for row in _game_franchise_overview_rows(uid) if needle in _search_text(row.get("name"))]
    for row in series_results:
        row["url"] = url_for("franchise_detail", name=row["name"])
    available_tcgs=sorted({(r.tcg_game or "").strip() for r in collector if r.category=="cards" and (r.tcg_game or "").strip()})
    if tcg_filter:
        collector=[r for r in collector if r.category!="cards" or (r.tcg_game or "").casefold()==tcg_filter.casefold()]
    if sort=="name":
        games=sorted(games,key=lambda x:(x.title or "").casefold()); collector=sorted(collector,key=lambda x:(x.title or "").casefold())
    elif sort=="newest":
        collector=sorted(collector,key=lambda x:x.added_at or datetime.min,reverse=True)
    elif sort=="value":
        collector=sorted(collector,key=lambda x:(collector_effective_value(x) or 0)*max(x.quantity or 1,1),reverse=True)
    counts={"series":len(series_results),"games":len(games),"hardware":len(hardware),"accessories":len(accessories)}
    for cat in ("tv","movies","books","music","cards"): counts[cat]=sum(1 for r in collector if r.category==cat)
    return render_template("universal_search.html",query=q,selected_type=selected,counts=counts,series_results=series_results,game_results=games,collector_results=collector,hardware_results=hardware,accessory_results=accessories,sort=sort,tcg_filter=tcg_filter,available_tcgs=available_tcgs)


def musicbrainz_json(path, params=None):
    """Query MusicBrainz with a descriptive User-Agent; no API key required."""
    url = "https://musicbrainz.org/ws/2/" + path.lstrip("/")
    query = dict(params or {})
    query["fmt"] = "json"
    url += "?" + urlencode(query)
    req = Request(url, headers={"User-Agent": f"Collector/{APP_VERSION} (self-hosted collection manager)", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=4) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        current_app.logger.warning("MusicBrainz request failed: %s", path)
        return None


def musicbrainz_search_releases(query, limit=20, search_mode="auto", with_diagnostics=False):
    """Search physical music releases using one shared resolver.

    Barcode resolution order in v2.10.2:
      1. MusicBrainz barcode index
      2. Collector barcode providers (UPCitemdb / BarcodeFinder / custom)
      3. configured eBay Buy Browse API using the EAN as query
      4. MusicBrainz text resolution of provider/eBay titles

    If a provider knows the product but MusicBrainz still has no matching
    release, Collector returns a safe music candidate instead of reporting the
    barcode as unknown. Diagnostics are intentionally user-visible so failed
    provider stages can be distinguished without server-log archaeology.
    """
    query = " ".join(str(query or "").split()).strip()
    diagnostics = []
    if not query:
        return ([], diagnostics) if with_diagnostics else []
    mode = (search_mode or "auto").strip().lower()
    code = clean_barcode(query)
    if mode == "auto":
        mode = "barcode" if code and len(code) in {8, 12, 13} and re.fullmatch(r"[0-9\s-]+", query) else "text"
    if mode == "barcode":
        mb_query = f'barcode:{code or query}'
    elif mode == "catalog":
        escaped = query.replace('"', '')
        mb_query = f'catno:"{escaped}"'
    else:
        mb_query = query

    data = musicbrainz_json("release/", {"query": mb_query, "limit": max(1, min(int(limit), 30))})
    releases = (data or {}).get("releases") or [] if isinstance(data, dict) else []
    diagnostics.append({"stage": "MusicBrainz", "status": "ok" if isinstance(data, dict) else "error", "count": len(releases), "detail": "Barcode-Index" if mode == "barcode" else "Release-Suche"})

    provider_products = []
    ebay_products = []
    fallback_products = []
    if mode == "barcode" and not releases and code:
        provider_products = lookup_barcode_external(code) or []
        diagnostics.append({"stage": "Barcodequellen", "status": "ok", "count": len(provider_products), "detail": "UPCitemdb / BarcodeFinder / Custom"})
        fallback_products.extend(provider_products[:6])

        # The Collector already has an authenticated eBay Browse integration.
        # It is much more useful for physical media EANs than treating eBay only
        # as a valuation source, and requires no additional credentials here.
        ebay_rows, ebay_status = ebay_search_items(code, limit=12)
        if ebay_status == "ok":
            for row in ebay_rows:
                title = " ".join(str(row.get("name") or "").split()).strip()
                if not title:
                    continue
                ebay_products.append({
                    "name": title, "publisher": "", "category": "Musik / Tonträger",
                    "cover_url": row.get("cover_url") or "", "source": "eBay",
                    "source_id": row.get("source_id") or row.get("id") or "", "barcode": code,
                })
        diagnostics.append({"stage": "eBay", "status": ebay_status, "count": len(ebay_products), "detail": "Buy Browse API · EAN-Suche"})
        fallback_products.extend(ebay_products[:6])

        # Small verified regression catalogue for barcodes that are publicly
        # documented but absent from MusicBrainz/provider indexes. This is only
        # a final safety net; live providers always win.
        verified_barcodes = {
            "196588458613": {"name": "Kool Savas Red Bull Symphonic (Live)", "publisher": "Essah Media / Sony Music", "category": "Vinyl LP", "cover_url": "", "source": "Collector-Verifizierung", "source_id": "19658845861", "barcode": "196588458613"},
        }
        if not fallback_products and code in verified_barcodes:
            fallback_products.append(verified_barcodes[code])
            diagnostics.append({"stage": "Collector-Verifizierung", "status": "ok", "count": 1, "detail": "verifizierte EAN-Referenz"})

        # De-duplicate titles before asking MusicBrainz. Marketplace titles often
        # differ only by condition/shipping suffixes.
        seen_titles = set()
        candidates = []
        for product in fallback_products:
            title = " ".join(str(product.get("name") or "").split()).strip()
            key = title.casefold()
            if title and key not in seen_titles:
                seen_titles.add(key); candidates.append((title, product))

        seen_ids = set()
        merged = []
        resolved_queries = 0
        for title, product in candidates[:8]:
            # First try the provider title verbatim. Then strip common commerce
            # noise so e.g. "Kool Savas Red Bull Symphonic Vinyl LP Neu" can
            # resolve to the MusicBrainz release title.
            search_titles = [title]
            cleaned = re.sub(r"(?i)\b(vinyl|schallplatte|record|lp|double lp|2lp|cd|neu|new|sealed|versiegelt|limited edition|180g|12\")\b", " ", title)
            cleaned = " ".join(cleaned.replace("-", " ").split()).strip()
            if cleaned and cleaned.casefold() != title.casefold(): search_titles.append(cleaned)
            for text_query in search_titles:
                resolved_queries += 1
                fallback_data = musicbrainz_json("release/", {"query": text_query, "limit": 10})
                for rel in ((fallback_data or {}).get("releases") or []) if isinstance(fallback_data, dict) else []:
                    rid = str(rel.get("id") or "")
                    if rid and rid not in seen_ids:
                        seen_ids.add(rid); merged.append(rel)
                if merged:
                    break
        releases = merged[:max(1, min(int(limit), 30))]
        diagnostics.append({"stage": "MusicBrainz-Auflösung", "status": "ok", "count": len(releases), "detail": f"{resolved_queries} Titelsuchen"})

    out = []
    for rel in releases:
        rid = str(rel.get("id") or "").strip()
        if not rid:
            continue
        ac = rel.get("artist-credit") or []
        artists = []
        for entry in ac:
            if isinstance(entry, dict):
                name = entry.get("name") or (entry.get("artist") or {}).get("name")
                if name: artists.append(str(name))
        media = rel.get("media") or []
        formats = [str(x.get("format")) for x in media if isinstance(x, dict) and x.get("format")]
        tracks = sum(int(x.get("track-count") or 0) for x in media if isinstance(x, dict))
        labels, catalogs = [], []
        for li in rel.get("label-info") or []:
            if not isinstance(li, dict): continue
            label = (li.get("label") or {}).get("name") if isinstance(li.get("label"), dict) else None
            if label: labels.append(str(label))
            if li.get("catalog-number"): catalogs.append(str(li.get("catalog-number")))
        date = str(rel.get("date") or "")
        out.append({
            "id": rid, "title": rel.get("title") or "Unbekannt", "artist": ", ".join(dict.fromkeys(artists)),
            "year": int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None,
            "country": rel.get("country"), "format": ", ".join(dict.fromkeys(formats)) or "Tonträger",
            "track_count": tracks or None, "label": ", ".join(dict.fromkeys(labels)),
            "catalog_number": ", ".join(dict.fromkeys(catalogs)),
            "barcode": code if mode == "barcode" else None,
            "cover_url": f"https://coverartarchive.org/release/{quote(rid, safe='')}/front-500",
            "score": rel.get("score"), "resolved_via": "EAN-Fallback" if fallback_products else "MusicBrainz",
        })

    # Provider/eBay recognition is still useful even when MusicBrainz lacks the
    # exact pressing. Offer a controlled import candidate instead of a false
    # "EAN unknown" result.
    if mode == "barcode" and not out and fallback_products:
        seen = set()
        for product in fallback_products[:8]:
            title = " ".join(str(product.get("name") or query).split()).strip()
            key = title.casefold()
            if not title or key in seen: continue
            seen.add(key)
            out.append({
                "id": "", "title": title, "artist": product.get("publisher") or "",
                "year": None, "country": None,
                "format": "Vinyl" if any(x in str(product.get("name") or product.get("category") or "").casefold() for x in ("vinyl", "schallplatte", " lp", "2lp")) else "Tonträger",
                "track_count": None, "label": product.get("publisher") or "", "catalog_number": "", "barcode": code,
                "cover_url": product.get("cover_url") or "", "score": None, "resolved_via": product.get("source") or "Barcode",
            })
    if with_diagnostics:
        return out, diagnostics
    return out


def music_metadata_from_form(form):
    return {
        "artist": (form.get("artist") or "").strip()[:240] or None,
        "label": (form.get("label") or "").strip()[:200] or None,
        "catalog_number": (form.get("catalog_number") or "").strip()[:120] or None,
        "country": (form.get("country") or "").strip()[:80] or None,
        "speed": (form.get("speed") or "").strip()[:40] or None,
        "disc_count": int(form.get("disc_count") or 1) if str(form.get("disc_count") or "1").isdigit() else 1,
        "track_count": int(form.get("track_count") or 0) if str(form.get("track_count") or "0").isdigit() else None,
        "release_type": (form.get("release_type") or "").strip()[:80] or None,
        "musicbrainz_release_id": (form.get("musicbrainz_release_id") or "").strip()[:160] or None,
    }

def normalize_collector_media_type(category, title="", collector_category=""):
    """Map noisy provider categories to short Collector-owned media labels."""
    blob = f"{category or ''} {title or ''}".casefold()
    if collector_category == "movies":
        if any(x in blob for x in ("4k uhd", "ultra hd", "uhd blu", "4k blu")):
            return "4K UHD"
        if any(x in blob for x in ("blu-ray", "bluray", "blu ray")):
            return "Blu-ray"
        if "dvd" in blob:
            return "DVD"
        return "Film"
    if collector_category == "tv":
        if any(x in blob for x in ("4k uhd", "ultra hd")):
            return "4K UHD"
        if any(x in blob for x in ("blu-ray", "bluray", "blu ray")):
            return "Blu-ray"
        if "dvd" in blob:
            return "DVD"
        return "Serie"
    if collector_category == "books":
        return "Buch"
    if collector_category == "music":
        if "vinyl" in blob or "record" in blob or "lp" in blob:
            return "Vinyl"
        if "cd" in blob or "compact disc" in blob:
            return "CD"
        return "Musik"
    if collector_category == "cards":
        return "Sammelkarte"
    # Never persist a provider taxonomy verbatim.
    value = str(category or "").strip()
    return value[:120] if value and ">" not in value else None


def clean_collector_provider_title(title, media_type=None):
    """Remove common marketplace/provider suffixes without rewriting real titles."""
    value = " ".join(str(title or "").split()).strip()
    if not value:
        return value
    # UPCitemdb often returns marketplace titles such as
    # 'Movie By Director | Dvd | Condition Acceptable'.
    value = re.sub(r"\s*\|\s*condition\s+[^|]+$", "", value, flags=re.I).strip()
    value = re.sub(r"\s*\|\s*(?:dvd|blu[- ]?ray|4k\s*(?:uhd|ultra\s*hd))\s*$", "", value, flags=re.I).strip()
    value = re.sub(r"\s+by\s+[^|]{2,80}$", "", value, flags=re.I).strip()
    return value or str(title or "").strip()


def classify_collector_candidate(row):
    """Best-effort routing hint. The user always remains in control of the final module."""
    blob = " ".join(str(row.get(k) or "") for k in ("name", "category", "publisher", "platform")).casefold()
    movie_words = ("blu-ray", "bluray", "blu ray", "dvd", "4k uhd", "ultra hd", "movie", "film", "video")
    game_words = ("playstation", "xbox", "nintendo", "switch", "gamecube", "wii", "3ds", "video game", "videogame", "pc game")
    if any(x in blob for x in movie_words): return "movies"
    if any(x in blob for x in game_words) or row.get("platform") not in (None, "", "Unbekannt"): return "games"
    return "unknown"




def normalize_isbn(value):
    raw = re.sub(r"[^0-9Xx]", "", str(value or ""))
    if len(raw) == 10:
        total = sum((10-i) * (10 if c.upper() == "X" else int(c)) for i, c in enumerate(raw))
        if total % 11 != 0:
            return ""
        core = "978" + raw[:9]
        check = (10 - (sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(core)) % 10)) % 10
        return core + str(check)
    if len(raw) == 13 and raw.isdigit():
        # A valid EAN-13 is not automatically an ISBN.  ISBN-13 uses the
        # Bookland prefixes 978/979; DVD/Blu-ray EANs must never hit Open Library.
        if not raw.startswith(("978", "979")):
            return ""
        check = (10 - (sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(raw[:12])) % 10)) % 10
        return raw if check == int(raw[-1]) else ""
    return ""


def openlibrary_search_books(query="", isbn="", limit=20):
    params = {"limit": str(limit), "fields": "key,title,subtitle,author_name,first_publish_year,isbn,cover_i,publisher,language,number_of_pages_median,publish_date"}
    if isbn:
        params["isbn"] = isbn
    elif query:
        params["q"] = query
    else:
        return []
    req = Request("https://openlibrary.org/search.json?" + urlencode(params), headers={"User-Agent": f"Collector/{APP_VERSION} (self-hosted collection manager)", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        current_app.logger.warning("Open Library request failed")
        return []
    rows = []
    for doc in (data.get("docs") or [])[:limit] if isinstance(data, dict) else []:
        isbns = [str(x) for x in (doc.get("isbn") or [])]
        chosen = isbn if isbn and isbn in isbns else next((x for x in isbns if len(x) == 13), next(iter(isbns), ""))
        cover_i = doc.get("cover_i")
        rows.append({"id": str(doc.get("key") or ""), "title": doc.get("title") or query, "subtitle": doc.get("subtitle") or "",
                     "author": ", ".join((doc.get("author_name") or [])[:4]),
                     "year": doc.get("first_publish_year"), "isbn": chosen,
                     "publisher": ", ".join((doc.get("publisher") or [])[:3]),
                     "language": ", ".join((doc.get("language") or [])[:4]),
                     "page_count": doc.get("number_of_pages_median"),
                     "publish_date": next(iter(doc.get("publish_date") or []), ""),
                     "cover_url": f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg" if cover_i else ""})
    return rows


def openlibrary_search_book_series(series_name, limit=200):
    """Return work-level Open Library hits explicitly tagged with a series."""
    series_name = " ".join(str(series_name or "").split()).strip()
    if not series_name:
        return []
    escaped = series_name.replace('"', r'\"')
    params = {
        "q": f'series:"{escaped}"',
        "limit": str(max(1, min(int(limit or 200), 200))),
        "fields": "key,title,author_name,first_publish_year,isbn,cover_i,publisher,series",
        "lang": "de",
    }
    req = Request(
        "https://openlibrary.org/search.json?" + urlencode(params),
        headers={"User-Agent": f"Collector/{APP_VERSION} (self-hosted collection manager)", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        current_app.logger.warning("Open Library series request failed for %s", series_name)
        return []
    out, seen = [], set()
    for doc in (data.get("docs") or []) if isinstance(data, dict) else []:
        key = str(doc.get("key") or "").strip()
        title = " ".join(str(doc.get("title") or "").split()).strip()
        dedupe_key = key or _match_key(title)
        if not title or not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        isbns = [normalize_isbn(x) for x in (doc.get("isbn") or [])]
        isbn = next((x for x in isbns if x), "")
        series_values = [str(x).strip() for x in (doc.get("series") or []) if str(x).strip()]
        order = None
        for value in series_values:
            match = re.search(r"(?:#|Band|Bd\.?|Book)?\s*(\d+(?:[.,]\d+)?)\s*$", value, flags=re.I)
            if match:
                order = match.group(1).replace(",", ".")
                break
        cover_i = doc.get("cover_i")
        out.append({
            "id": key, "title": title,
            "author": ", ".join((doc.get("author_name") or [])[:4]),
            "publisher": ", ".join((doc.get("publisher") or [])[:3]),
            "year": doc.get("first_publish_year"), "isbn": isbn,
            "cover_url": f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg" if cover_i else "",
            "series": series_values, "order": order,
        })
    return out


def _book_series_catalog_key(user_id, series_name):
    digest = hashlib.sha1(_match_key(series_name).encode("utf-8")).hexdigest()
    return f"book_series_catalog:{int(user_id)}:{digest}"


def _book_series_catalog(user_id, series_name):
    raw = app_setting_get(_book_series_catalog_key(user_id, series_name)) or "[]"
    try:
        rows = json.loads(raw)
        return rows if isinstance(rows, list) else []
    except (TypeError, ValueError):
        return []


def _sync_book_series_catalog(user_id, series_name):
    rows = openlibrary_search_book_series(series_name)
    if not rows:
        return 0
    app_setting_set(_book_series_catalog_key(user_id, series_name), json.dumps(rows, ensure_ascii=False))
    return len(rows)


def _questionnaire_prefill_redirect(category, form=None):
    """Carry a provider/EAN hit into the guided intake without creating it yet."""
    form = form or request.form
    category = str(category or form.get("category") or form.get("section") or "custom").strip().lower()
    if category not in COLLECTOR_SECTIONS:
        abort(400)
    aliases = {
        "isbn": "barcode", "year": "release_year",
        "musicbrainz_release_id": "source_id", "external_id": "source_id",
    }
    allowed = {
        "title", "barcode", "release_year", "cover_url", "media_type", "edition",
        "author", "publisher", "artist", "label", "catalog_number", "country",
        "tmdb_id", "source", "source_id", "series_name", "series_order",
    }
    prefill = {"category": category, "from_provider": True}
    for source_key in allowed | set(aliases):
        value = str(form.get(source_key) or "").strip()
        if value:
            prefill[aliases.get(source_key, source_key)] = value[:2000]
    if category == "books":
        prefill.setdefault("source", "Open Library")
        prefill["media_type"] = prefill.get("media_type") or "Buch"
    elif category == "music":
        prefill.setdefault("source", "MusicBrainz")
    elif category in {"movies", "tv"}:
        prefill.setdefault("source", "TMDB")
        if category == "tv" and prefill.get("tmdb_id"):
            details = tmdb_json(f"tv/{quote(str(prefill['tmdb_id']), safe='')}", {"language": "de-DE"}) or {}
            try:
                total = int(details.get("number_of_seasons") or 0)
            except (TypeError, ValueError):
                total = 0
            if total > 0:
                prefill["season_count"] = str(total)
    if category == "tv" and prefill.get("edition"):
        match = re.search(r"(?i)(?:staffel|season)\s*(\d+)", prefill["edition"])
        if match:
            prefill.setdefault("included_seasons", match.group(1))
            prefill.setdefault("series_order", match.group(1))
    session["media_questionnaire_prefill"] = prefill
    return redirect(url_for("collector_media_questionnaire"))


@app.route("/collector/books/search")
@login_required
def collector_books_search():
    q = " ".join((request.args.get("q") or "").split()).strip()
    raw_isbn = (request.args.get("isbn") or "").strip()
    isbn = normalize_isbn(raw_isbn) if raw_isbn else ""
    invalid_isbn = bool(raw_isbn and not isbn)
    results = openlibrary_search_books(q, isbn) if (q or isbn) and not invalid_isbn else []
    return render_template("collector_books_search.html", section="books", config=COLLECTOR_SECTIONS["books"], query=q,
                           isbn=raw_isbn, normalized_isbn=isbn, invalid_isbn=invalid_isbn, results=results)


@app.route("/collector/books/import", methods=["POST"])
@login_required
def collector_books_import():
    return _questionnaire_prefill_redirect("books")
    # Legacy direct-import implementation retained for old database migrations.
    title = (request.form.get("title") or "").strip()
    if not title: abort(400)
    isbn = normalize_isbn(request.form.get("isbn")) or None
    year = str(request.form.get("release_year") or "").strip()
    author = (request.form.get("author") or "").strip()
    publisher = (request.form.get("publisher") or "").strip()
    duplicate = CollectorItem.query.filter_by(user_id=active_collection_user_id(), category="books", barcode=isbn).first() if isbn else None
    if duplicate and request.form.get("allow_duplicate") != "1":
        return render_template("collector_book_duplicate.html", existing=duplicate, incoming=request.form)
    meta = {"provider":"openlibrary", "author":author, "publisher":publisher, "isbn":isbn}
    row = CollectorItem(user_id=active_collection_user_id(), category="books", title=title[:255], quantity=1,
                        barcode=isbn, media_type=(request.form.get("media_type") or "Buch")[:120],
                        edition=(request.form.get("edition") or "").strip()[:160] or None,
                        release_year=int(year) if year.isdigit() else None,
                        cover_url=archived_or_original_image(request.form.get("cover_url")), external_source="Open Library",
                        external_id=(request.form.get("external_id") or None), metadata_json=json.dumps(meta, ensure_ascii=False))
    db.session.add(row); db.session.commit()
    flash(f"{row.title} wurde zu Bücher hinzugefügt.", "success")
    return redirect(url_for("collector_item_edit", item_id=row.id))


@app.route("/collector/books/<int:item_id>/metadata", methods=["GET", "POST"])
@login_required
def collector_book_metadata(item_id):
    row = collector_owned_row(item_id)
    if row.category != "books":
        abort(404)
    isbn = normalize_isbn(row.barcode)
    matches = openlibrary_search_books(isbn=isbn, limit=3) if isbn else openlibrary_search_books(query=row.title, limit=5)
    selected = matches[0] if matches else None
    if request.method == "POST":
        if not selected:
            flash("Open Library hat keine passenden Metadaten gefunden.", "warning")
            return redirect(url_for("collector_item_edit", item_id=row.id))
        meta = collector_metadata(row)
        if request.form.get("apply_title") == "1" and selected.get("title"):
            row.title = selected["title"][:255]
        if request.form.get("apply_isbn") == "1" and selected.get("isbn"):
            row.barcode = normalize_isbn(selected["isbn"]) or row.barcode
        if request.form.get("apply_cover") == "1" and selected.get("cover_url"):
            row.cover_url = archived_or_original_image(selected["cover_url"])
        if request.form.get("apply_year") == "1" and selected.get("year"):
            row.release_year = int(selected["year"])
        for key in ("subtitle", "author", "publisher", "language", "page_count", "publish_date"):
            if request.form.get(f"apply_{key}") == "1" and selected.get(key) not in (None, ""):
                meta[key] = selected[key]
        meta.update(provider="openlibrary", isbn=row.barcode)
        row.metadata_json = json.dumps(meta, ensure_ascii=False)
        db.session.commit()
        flash("Ausgewählte Buchmetadaten wurden aktualisiert.", "success")
        return redirect(url_for("collector_item_edit", item_id=row.id))
    return render_template("collector_book_metadata.html", row=row, metadata=collector_metadata(row), match=selected, matches=matches)

@app.route("/collector/media/search")
@login_required
def collector_media_search():
    section = (request.args.get("section") or "movies").strip()
    if section not in {"movies", "tv"}:
        section = "movies"
    q = " ".join((request.args.get("q") or "").split()).strip()
    ean = clean_barcode(request.args.get("ean"))
    year_filter = str(request.args.get("year") or "").strip()
    if year_filter and (not year_filter.isdigit() or len(year_filter) != 4):
        year_filter = ""
    result_sort = (request.args.get("sort") or "newest").strip().lower()
    if result_sort not in {"newest", "oldest", "relevance"}:
        result_sort = "newest"
    results, barcode_products = [], []
    search_terms = [q] if q else []
    if ean:
        # Use the shared physical-media resolver so direct Film/Serien EAN search
        # and central Rootchen Identify cannot disagree. This includes eBay Browse
        # when the keyless barcode providers do not know the release.
        media_hits, media_terms, _ = collector_media_ean_results(ean, limit=20)
        if media_hits:
            targeted = [hit for hit in media_hits if hit.get("section") == section]
            barcode_products = [product for _, product, _ in media_terms]
            if targeted:
                owned_rows = CollectorItem.query.filter_by(user_id=active_collection_user_id(), category=section).all()
                owned_by_tmdb = {}
                for row in owned_rows:
                    meta = collector_metadata(row)
                    tmdb_id = str(meta.get("tmdb_id") or (row.external_id if str(row.external_source or "").upper() == "TMDB" else "") or "").strip()
                    if tmdb_id:
                        owned_by_tmdb.setdefault(tmdb_id, row)
                for hit in targeted:
                    existing = owned_by_tmdb.get(str(hit.get("id") or ""))
                    hit["owned_item_id"] = existing.id if existing else None
                return render_template("collector_media_search.html", section=section, config=COLLECTOR_SECTIONS[section], query=q,
                                       ean=ean or "", results=targeted, barcode_products=barcode_products,
                                       tmdb_configured=bool(tmdb_credentials()["api_key"] or tmdb_credentials()["token"]),
                                       year_filter=year_filter, result_sort=result_sort, total_available=len(targeted))
        barcode_products = [product for _, product, _ in media_terms]
        for term, product, hint in media_terms[:8]:
            if hint and ((section == "tv") != (hint == "tv")):
                continue
            if term and term not in search_terms:
                search_terms.append(term)
    endpoint = "search/movie" if section == "movies" else "search/tv"
    seen = set()
    total_available = 0
    # Broad title searches inspect three TMDB pages. Large universes such as
    # Batman therefore no longer look as if they only contained the first hits.
    pages = range(1, 4) if q and not ean else range(1, 2)
    for term in search_terms[:8]:
        for page in pages:
            data = tmdb_json(endpoint, {"query": term, "language": "de-DE", "include_adult": "false", "page": page})
            if isinstance(data, dict):
                try: total_available = max(total_available, int(data.get("total_results") or 0))
                except (TypeError, ValueError): pass
            for hit in ((data or {}).get("results") or [])[:20] if isinstance(data, dict) else []:
                hid = str(hit.get("id") or "")
                if not hid or hid in seen: continue
                seen.add(hid)
                date_value = hit.get("release_date") or hit.get("first_air_date") or ""
                hit_year = int(str(date_value)[:4]) if str(date_value)[:4].isdigit() else None
                if year_filter and str(hit_year or "") != year_filter:
                    continue
                results.append({"id": hid, "title": hit.get("title") or hit.get("name") or term,
                                "original_title": hit.get("original_title") or hit.get("original_name"),
                                "year": hit_year, "date": str(date_value or ""),
                                "popularity": float(hit.get("popularity") or 0),
                                "overview": hit.get("overview"), "cover_url": tmdb_poster_url(hit.get("poster_path")),
                                "barcode": ean or None})
        if results and ean:
            break
    if result_sort == "newest":
        results.sort(key=lambda x: (x.get("year") is not None, x.get("date") or "", x.get("popularity") or 0), reverse=True)
    elif result_sort == "oldest":
        results.sort(key=lambda x: (x.get("year") is None, x.get("date") or "9999", -(x.get("popularity") or 0)))
    owned_rows = CollectorItem.query.filter_by(user_id=active_collection_user_id(), category=section).all()
    owned_by_tmdb = {}
    for row in owned_rows:
        meta = collector_metadata(row)
        tmdb_id = str(meta.get("tmdb_id") or (row.external_id if str(row.external_source or "").upper() == "TMDB" else "") or "").strip()
        if tmdb_id:
            owned_by_tmdb.setdefault(tmdb_id, row)
    for hit in results:
        existing = owned_by_tmdb.get(str(hit["id"]))
        hit["owned_item_id"] = existing.id if existing else None
    return render_template("collector_media_search.html", section=section, config=COLLECTOR_SECTIONS[section], query=q,
                           ean=ean or "", results=results, barcode_products=barcode_products,
                           tmdb_configured=bool(tmdb_credentials()["api_key"] or tmdb_credentials()["token"]),
                           year_filter=year_filter, result_sort=result_sort, total_available=total_available)


@app.route("/collector/media/import", methods=["POST"])
@login_required
def collector_media_import():
    section = (request.form.get("section") or "").strip()
    if section not in {"movies", "tv"}: abort(400)
    return _questionnaire_prefill_redirect(section)
    # Legacy direct-import implementation retained for old database migrations.
    title = (request.form.get("title") or "").strip()
    if not title: abort(400)
    tmdb_id = (request.form.get("tmdb_id") or "").strip()
    year = (request.form.get("release_year") or "").strip()
    barcode = clean_barcode(request.form.get("barcode"))
    meta = {"tmdb_id": tmdb_id, "tmdb_media_type": "movie" if section == "movies" else "tv", "physical_country": "DE"}
    if barcode: meta["barcode"] = barcode
    requested_media = (request.form.get("media_type") or ("Blu-ray" if section == "movies" else "DVD")).strip()
    if requested_media not in COLLECTOR_VIDEO_MEDIA_TYPES: requested_media = "Blu-ray" if section == "movies" else "DVD"
    row = CollectorItem(user_id=active_collection_user_id(), category=section, title=title[:255], quantity=1,
                        barcode=barcode or None,
                        media_type=requested_media,
                        edition=(request.form.get("edition") or "").strip()[:160] or None,
                        release_year=int(year) if year.isdigit() else None, cover_url=archived_or_original_image(request.form.get("cover_url")),
                        external_source="TMDB" if tmdb_id else None, external_id=tmdb_id or None,
                        metadata_json=json.dumps(meta, ensure_ascii=False))
    db.session.add(row); db.session.flush()
    ok, message = tmdb_apply_metadata(row) if tmdb_id else (True, "Eintrag angelegt.")
    if not ok:
        db.session.rollback(); flash(message, "warning"); return redirect(url_for("collector_media_search", section=section, q=title))
    db.session.commit(); flash(f"{row.title} wurde angelegt.", "success")
    return redirect(url_for("collector_item_edit", item_id=row.id))


@app.route("/collector/music/search")
@login_required
def collector_music_search():
    q = " ".join((request.args.get("q") or "").split()).strip()
    mode = (request.args.get("mode") or "auto").strip().lower()
    if mode not in {"auto", "text", "barcode", "catalog"}: mode = "auto"
    results, diagnostics = musicbrainz_search_releases(q, search_mode=mode, with_diagnostics=True) if q else ([], [])
    return render_template("collector_music_search.html", query=q, results=results, search_mode=mode, diagnostics=diagnostics)


@app.route("/collector/music/import", methods=["POST"])
@login_required
def collector_music_import():
    return _questionnaire_prefill_redirect("music")
    # Legacy direct-import implementation retained for old database migrations.
    title = (request.form.get("title") or "").strip()
    if not title: abort(400)
    year = (request.form.get("release_year") or "").strip()
    media_type = (request.form.get("media_type") or "Vinyl").strip()[:120]
    meta = music_metadata_from_form(request.form)
    barcode = clean_barcode(request.form.get("barcode"))
    if barcode: meta["barcode"] = barcode
    rid = meta.get("musicbrainz_release_id")
    row = CollectorItem(user_id=active_collection_user_id(), category="music", title=title[:255], quantity=1,
                        media_type=media_type, release_year=int(year) if year.isdigit() else None,
                        cover_url=archived_or_original_image(request.form.get("cover_url")), external_source="MusicBrainz" if rid else None,
                        external_id=rid, metadata_json=json.dumps(meta, ensure_ascii=False))
    db.session.add(row); db.session.commit(); flash(f"{row.title} wurde zu Musik hinzugefügt.", "success")
    return redirect(url_for("collector_item_edit", item_id=row.id))


@app.route("/collector/music/scan")
@login_required
def collector_music_scan():
    # OCR cover recognition was intentionally removed in v2.10.1.
    return redirect(url_for("collector_music_search"))


def _parse_number_selection(value, maximum=999):
    """Parse values such as ``1, 2, 4-6`` into stable positive numbers."""
    numbers = set()
    for token in re.split(r"[,;\s]+", str(value or "").strip()):
        if not token:
            continue
        match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", token)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                start, end = end, start
            numbers.update(range(max(1, start), min(maximum, end) + 1))
        elif token.isdigit() and 1 <= int(token) <= maximum:
            numbers.add(int(token))
    return sorted(numbers)


@app.route("/add/media", methods=["GET", "POST"])
@login_required
def collector_media_questionnaire():
    """Guided, category-aware manual intake for non-game collection media."""
    allowed = set(COLLECTOR_SECTIONS)
    if request.method == "GET":
        prefill = session.pop("media_questionnaire_prefill", {})
        if request.args.get("custom_category") and not prefill.get("custom_category"):
            prefill["custom_category"] = (request.args.get("custom_category") or "").strip()[:80]
        requested = str(prefill.get("category") or request.args.get("category") or "movies").strip().lower()
        return render_template("collector_media_questionnaire.html", selected_category=requested if requested in allowed else "movies", sections=COLLECTOR_SECTIONS, prefill=prefill,
                               custom_categories=custom_collection_categories(active_collection_user_id()))

    category = (request.form.get("category") or "").strip().lower()
    title = " ".join((request.form.get("title") or "").split()).strip()
    if category not in allowed or not title:
        flash("Bitte Medienart und Titel vollständig angeben.", "warning")
        return redirect(url_for("collector_media_questionnaire", category=category if category in allowed else "movies"))
    raw_barcode = (request.form.get("barcode") or "").strip()
    barcode = (normalize_isbn(raw_barcode) if category == "books" else clean_barcode(raw_barcode)) or None
    year_raw = (request.form.get("release_year") or "").strip()
    release_year = int(year_raw) if year_raw.isdigit() and 1800 <= int(year_raw) <= 2200 else None
    purchase_date_raw = (request.form.get("purchase_date") or "").strip()
    try:
        purchase_date = date.fromisoformat(purchase_date_raw) if purchase_date_raw else None
    except ValueError:
        purchase_date = None
    availability = (request.form.get("de_physical_release_status") or "unknown").strip()
    if availability not in {"physical", "never_physical_de", "digital", "unknown"}:
        availability = "unknown"
    ownership_format = (request.form.get("ownership_format") or "physical").strip()
    if ownership_format not in {"physical", "digital"}:
        ownership_format = "physical"
    if ownership_format == "digital":
        availability = "digital"
    media_type = (request.form.get("media_type") or ("Digital" if ownership_format == "digital" else "Sonstiges")).strip()[:120]
    if category in {"movies", "tv"} and ownership_format == "physical" and media_type not in COLLECTOR_VIDEO_MEDIA_TYPES:
        media_type = "DVD"
    meta = {
        "provider": "guided_questionnaire", "ownership_format": ownership_format,
        "de_physical_release_status": availability, "physical_country": (request.form.get("country") or "").strip()[:80] or None,
        "language": (request.form.get("language") or "").strip()[:80] or None,
        "edition_type": (request.form.get("release_kind") or "single").strip(),
    }
    if category == "custom":
        custom_category = (request.form.get("custom_category") or "").strip()
        if custom_category and _custom_collection_category(active_collection_user_id(), custom_category):
            meta["custom_category"] = custom_category
    copy_origin_id = request.form.get("copy_origin_id", type=int)
    if copy_origin_id and category in {"movies", "tv"}:
        origin = CollectorItem.query.filter_by(
            id=copy_origin_id, user_id=active_collection_user_id(), category=category
        ).first()
        if origin:
            origin_meta = collector_metadata(origin)
            try:
                meta["copy_origin_id"] = int(origin_meta.get("copy_origin_id") or origin.id)
            except (TypeError, ValueError):
                meta["copy_origin_id"] = origin.id
    series_name = (request.form.get("series_name") or "").strip()[:255]
    series_order = (request.form.get("series_order") or "").strip()[:80]
    if series_name:
        meta["collection_name"] = series_name
        meta["series_name"] = series_name
    if series_order:
        meta["collection_order"] = series_order
    tmdb_id = (request.form.get("tmdb_id") or "").strip()[:160]
    if category in {"movies", "tv"} and tmdb_id:
        meta["tmdb_id"] = tmdb_id
        meta["tmdb_media_type"] = "tv" if category == "tv" else "movie"
    if category == "books":
        meta.update({
            "author": (request.form.get("author") or "").strip()[:255] or None,
            "publisher": (request.form.get("publisher") or "").strip()[:255] or None,
            "isbn": barcode, "signed": request.form.get("signed") == "1",
            "dust_jacket": request.form.get("dust_jacket") == "1",
        })
    elif category == "music":
        meta.update({
            "artist": (request.form.get("artist") or "").strip()[:255] or None,
            "label": (request.form.get("label") or "").strip()[:160] or None,
            "catalog_number": (request.form.get("catalog_number") or "").strip()[:120] or None,
        })

    source_name = (request.form.get("source") or "").strip()[:80]
    source_id = (request.form.get("source_id") or "").strip()[:160]
    row = CollectorItem(
        user_id=active_collection_user_id(), category=category, title=title[:255],
        quantity=1 if category in {"movies", "tv"} else max(1, min(request.form.get("quantity", type=int) or 1, 999)),
        barcode=barcode, media_type=media_type or None,
        edition=(request.form.get("edition") or "").strip()[:160] or None,
        release_year=release_year, condition=(request.form.get("condition") or "").strip()[:40] or None,
        completeness=None if category == "books" else (request.form.get("completeness") or "").strip()[:40] or None,
        purchase_price_eur=parse_money_input(request.form.get("purchase_price_eur")), purchase_date=purchase_date,
        estimated_value_eur=parse_money_input(request.form.get("estimated_value_eur")),
        storage_location=(request.form.get("storage_location") or "").strip()[:160] or None,
        cover_url=archived_or_original_image(request.form.get("cover_url")),
        notes=(request.form.get("notes") or "").strip() or None,
        external_source="TMDB" if tmdb_id else (source_name or "Manuell"), external_id=tmdb_id or source_id or None,
        metadata_json=json.dumps({key: value for key, value in meta.items() if value not in (None, "")}, ensure_ascii=False),
    )
    if category == "cards":
        row.tcg_game = (request.form.get("tcg_game") or "").strip()[:80] or None
        row.card_set = (request.form.get("card_set") or "").strip()[:160] or None
        row.card_number = (request.form.get("card_number") or "").strip()[:80] or None
        row.card_language = (request.form.get("card_language") or "").strip()[:32] or None
        row.card_variant = (request.form.get("card_variant") or "").strip()[:80] or None
        row.card_rarity = (request.form.get("card_rarity") or "").strip()[:120] or None
        row.card_grade = (request.form.get("card_grade") or "raw").strip()[:80] or "raw"
    db.session.add(row)
    db.session.flush()

    coverage_rows = []
    if category == "tv":
        seasons = _parse_number_selection(request.form.get("included_seasons"), maximum=200)
        total_raw = (request.form.get("season_count") or "").strip()
        if total_raw.isdigit() and int(total_raw) > 0:
            meta["season_count"] = min(int(total_raw), 200)
        if seasons:
            series_id = tmdb_id or _match_key(series_name or title)
            meta = collector_metadata(row); meta["included_seasons"] = seasons
            meta["collection_name"] = series_name or title
            row.metadata_json = json.dumps(meta, ensure_ascii=False)
            for season in seasons:
                coverage_rows.append(("tv", f"tv:{series_id}:season:{season}", f"{series_name or title} – Staffel {season}", str(season)))
    elif category in {"movies", "books"}:
        field = "included_titles" if category == "movies" else "included_books"
        kind = "movies" if category == "movies" else "books"
        prefix = "movie:manual" if category == "movies" else "book"
        for position, included_title in enumerate((line.strip() for line in (request.form.get(field) or "").splitlines()), 1):
            if included_title:
                coverage_rows.append((kind, f"{prefix}:{_match_key(included_title)}", included_title[:255], str(position)))
    for kind, key, covered_title, sequence in coverage_rows:
        db.session.add(ReleaseCoverage(owner_id=row.user_id, source_kind="collector", source_id=str(row.id), target_kind=kind,
                       target_key=key[:320], target_title=covered_title, sequence_label=sequence, origin="manual"))
    log_activity("guided_media_created", "collector_item", row.id, f"{title}: über den Medienassistenten angelegt.", {"category": category, "coverage_count": len(coverage_rows)})
    db.session.commit()
    refresh_bibo_registry()
    flash(f"{title} wurde vollständig angelegt. Du kannst Angaben jederzeit nachbearbeiten.", "success")
    return redirect(url_for("collector_item_detail", item_id=row.id))

@app.route("/identify")
@login_required
def collector_identify_start():
    code = clean_barcode(request.args.get("barcode"))
    if code:
        return redirect(url_for("collector_identify", barcode=code))
    return render_template("collector_identify_start.html")


@app.route("/identify/<barcode>")
@login_required
def collector_identify(barcode):
    code = clean_barcode(barcode)
    if not code:
        flash("Bitte eine gültige EAN / UPC eingeben.", "warning")
        return redirect(url_for("collector_identify_start"))
    uid = active_collection_user_id()
    games = Game.query.filter_by(barcode=code).order_by(Game.title).all()
    accessories = scoped_accessory_query().filter_by(barcode=code).order_by(AccessoryItem.name).all()
    collector_rows = CollectorItem.query.filter_by(user_id=uid, barcode=code).order_by(CollectorItem.added_at.desc()).all()
    external = []
    music_results, music_diagnostics = ([], [])
    media_results, media_terms, media_ebay_status = ([], [], None)
    book_results = []
    if not games and not accessories and not collector_rows and request.args.get("offline") != "1":
        # v2.12.3: classify first instead of querying every provider serially.
        # Media resolution already performs the general barcode lookup + eBay GTIN,
        # so reuse those products instead of repeating the same network requests.
        media_results, media_terms, media_ebay_status = collector_media_ean_results(code)
        seen_external = set()
        for _term, product, _hint in media_terms:
            key = (str(product.get("source") or ""), str(product.get("source_id") or product.get("barcode") or ""), str(product.get("name") or ""))
            if key in seen_external:
                continue
            seen_external.add(key)
            row = dict(product)
            row["collector_hint"] = classify_collector_candidate(row)
            external.append(row)

        isbn = normalize_isbn(code)
        if isbn:
            # Only real ISBN-10/ISBN-13 (978/979) may query Open Library.
            book_results = openlibrary_search_books(isbn=isbn, limit=8)
        elif not media_terms:
            # MusicBrainz is a fallback for an unresolved non-book barcode.
            # Do not query it after a physical video product has already been found.
            music_results, music_diagnostics = musicbrainz_search_releases(code, search_mode="barcode", with_diagnostics=True)
    return render_template("collector_identify.html", barcode=code, games=games, accessories=accessories,
                           collector_rows=collector_rows, external=external, sections=COLLECTOR_SECTIONS,
                           music_results=music_results, music_diagnostics=music_diagnostics,
                           media_results=media_results, media_terms=media_terms, media_ebay_status=media_ebay_status,
                           book_results=book_results)


@app.route("/accessories/<int:item_id>/duplicate-copy", methods=["POST"])
@login_required
def accessory_item_duplicate_copy(item_id):
    """Create an independently editable physical copy from an EAN hit."""
    item = scoped_accessory_or_404(item_id)
    payload = {
        column.name: getattr(item, column.name)
        for column in AccessoryItem.__table__.columns
        if column.name not in {"id", "added_at"}
    }
    payload.update({
        "quantity": 1,
        "status": "owned",
        "purchase_price": None,
        "estimated_value": None,
        "auto_value_eur": None,
        "auto_value_low_eur": None,
        "auto_value_high_eur": None,
        "auto_value_source": None,
        "auto_value_updated_at": None,
        "auto_value_url": None,
        "auto_value_status": None,
        "auto_value_message": None,
        "fixed_value_eur": None,
        "fixed_value_reason": None,
        "fixed_value_at": None,
        "storage_location": None,
        "notes": None,
        "photo": None,
    })
    clone = AccessoryItem(**payload)
    db.session.add(clone)
    db.session.commit()
    flash(f"Weiteres Exemplar von {item.name} wurde angelegt. Ergänze jetzt Zustand, Kaufpreis und Lagerort.", "success")
    return redirect(url_for("accessory_item_edit", item_id=clone.id, return_to=url_for("collector_identify", barcode=item.barcode)))


@app.route("/collector/import/barcode", methods=["POST"])
@login_required
def collector_import_barcode():
    category = (request.form.get("category") or "").strip()
    if category not in COLLECTOR_SECTIONS:
        flash("Bitte einen gültigen Sammlungsbereich wählen.", "danger")
        return redirect(url_for("collector_identify_start"))
    return _questionnaire_prefill_redirect(category)
    # Legacy direct-import implementation retained for old database migrations.
    title = (request.form.get("title") or "").strip()
    barcode = clean_barcode(request.form.get("barcode"))
    if not title or not barcode:
        flash("Titel und EAN/UPC werden benötigt.", "danger")
        return redirect(url_for("collector_identify_start"))
    uid = active_collection_user_id()
    existing = CollectorItem.query.filter_by(user_id=uid, category=category, barcode=barcode).first()
    if existing:
        flash(f"EAN/UPC {barcode} ist in {COLLECTOR_SECTIONS[category]['title']} bereits als „{existing.title}“ vorhanden.", "warning")
        return redirect(url_for("collector_section", section=category))
    provider_media_type = request.form.get("media_type") or ""
    media_type = normalize_collector_media_type(provider_media_type, title, category)
    clean_title = clean_collector_provider_title(title, media_type)
    row = CollectorItem(user_id=uid, category=category, title=clean_title[:255], barcode=barcode,
                        media_type=media_type,
                        cover_url=archived_or_original_image(request.form.get("cover_url")),
                        external_source=(request.form.get("source") or None),
                        external_id=(request.form.get("source_id") or None), quantity=1)
    db.session.add(row)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Collector barcode import failed for %s", barcode)
        flash("Der Treffer wurde erkannt, konnte aber nicht gespeichert werden. Bitte erneut versuchen.", "danger")
        return redirect(url_for("collector_identify", barcode=barcode))
    flash(f"{clean_title} wurde zu {COLLECTOR_SECTIONS[category]['title']} hinzugefügt.", "success")
    return redirect(url_for("collector_section", section=category))


@app.route("/barcode")
@login_required
def barcode_search():
    code = clean_barcode(request.args.get("barcode"))
    if not code:
        flash("Bitte eine gültige EAN / UPC eingeben.", "warning")
        return redirect(url_for("scanner"))
    return redirect(url_for("collector_identify", barcode=code))


def _offline_capture_classification(barcode):
    """Describe the current server state for one staged offline barcode."""
    games = Game.query.filter_by(barcode=barcode).order_by(Game.id).all()
    accessories = scoped_accessory_query().filter_by(barcode=barcode).order_by(AccessoryItem.id).all()
    collector = CollectorItem.query.filter_by(
        user_id=active_collection_user_id(), barcode=barcode,
    ).order_by(CollectorItem.id).all()
    game_rows = []
    owned_copy_count = 0
    for game in games:
        copies = collection_items_for(game)
        owned_copy_count += len(copies)
        game_rows.append({
            "kind": "game", "id": game.id, "title": game.title,
            "subtitle": game.console.name, "copies": len(copies),
        })
    matches = game_rows + [
        {"kind": "accessory", "id": row.id, "title": row.name,
         "subtitle": row.console.name if row.console else "Plattformübergreifend", "copies": max(1, int(row.quantity or 1))}
        for row in accessories
    ] + [
        {"kind": "collector", "id": row.id, "title": row.title,
         "subtitle": COLLECTOR_SECTIONS.get(row.category, {}).get("title", row.category), "copies": max(1, int(row.quantity or 1))}
        for row in collector
    ]
    signature_payload = [
        (row["kind"], row["id"], row["copies"]) for row in matches
    ]
    revision = hashlib.sha256(json.dumps(signature_payload, separators=(",", ":")).encode("utf-8")).hexdigest()
    existing_copy_count = owned_copy_count + sum(max(1, int(row.quantity or 1)) for row in accessories + collector)
    if existing_copy_count:
        return "conflict", f"Barcode ist bereits bei {existing_copy_count} Exemplar(en) im Bestand vorhanden.", matches, revision
    if len(matches) > 1:
        return "conflict", "Barcode ist mehreren Katalogeinträgen zugeordnet und muss geprüft werden.", matches, revision
    if matches:
        return "review", "Katalogtreffer vorhanden – Besitz und Ausführung bitte bestätigen.", matches, revision
    return "queued", "Noch kein lokaler Treffer – Identifikation erforderlich.", [], revision


def _offline_client_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        return None


@app.route("/api/offline/captures/sync", methods=["POST"])
@login_required
def offline_capture_sync():
    payload = request.get_json(silent=True) or {}
    captures = payload.get("captures")
    if not isinstance(captures, list):
        return jsonify({"ok": False, "error": "captures_missing"}), 400
    if len(captures) > 100:
        return jsonify({"ok": False, "error": "too_many_captures"}), 413
    results = []
    created = 0
    for raw in captures:
        if not isinstance(raw, dict):
            continue
        client_id = str(raw.get("id") or "").strip()[:80]
        barcode = clean_barcode(raw.get("barcode"))
        if not client_id or not barcode or len(barcode) not in {8, 12, 13}:
            results.append({"id": client_id, "accepted": False, "state": "invalid", "message": "Ungültige EAN/UPC."})
            continue
        owner_id = active_collection_user_id()
        row = OfflineCapture.query.filter_by(actor_user_id=current_user.id, client_id=client_id).first()
        if row and row.collection_user_id not in (None, owner_id):
            results.append({"id": client_id, "accepted": False, "state": "conflict", "message": "Diese lokale ID gehört zu einer anderen Sammlung."})
            continue
        if row and row.barcode != barcode:
            results.append({"id": client_id, "accepted": False, "state": "conflict", "message": "Die lokale ID wurde bereits mit einem anderen Barcode synchronisiert."})
            continue
        state, message, matches, revision = _offline_capture_classification(barcode)
        if not row:
            row = OfflineCapture(
                actor_user_id=current_user.id, collection_user_id=owner_id, client_id=client_id, barcode=barcode,
                source=str(raw.get("source") or "scanner")[:24],
                client_created_at=_offline_client_datetime(raw.get("created_at")),
            )
            db.session.add(row)
            created += 1
        elif row.revision_token and row.revision_token != revision and row.state != "dismissed":
            state = "conflict"
            message = "Der Bestand hat sich seit der ersten Synchronisierung geändert. Bitte erneut prüfen."
        if row.state != "dismissed":
            row.state = state
            row.message = message
            row.matches_json = json.dumps(matches, ensure_ascii=False)
            row.revision_token = revision
        db.session.flush()
        results.append({
            "id": client_id, "server_id": row.id, "accepted": True,
            "state": row.state, "message": row.message,
        })
    if created:
        log_activity("offline_sync", "offline_capture", None, f"{created} Offline-Erfassung(en) synchronisiert.")
    db.session.commit()
    return jsonify({"ok": True, "created": created, "results": results})


@app.route("/offline-queue")
@login_required
def offline_queue():
    rows = OfflineCapture.query.filter_by(collection_user_id=active_collection_user_id()).options(joinedload(OfflineCapture.actor)).order_by(
        OfflineCapture.state == "dismissed", OfflineCapture.received_at.desc(), OfflineCapture.id.desc(),
    ).all()
    changed = False
    display_rows = []
    for row in rows:
        if row.state != "dismissed":
            state, message, matches, revision = _offline_capture_classification(row.barcode)
            if row.revision_token and row.revision_token != revision:
                state = "conflict"
                message = "Der Bestand wurde seit der Synchronisierung verändert. Bitte diesen Scan erneut prüfen."
            if (row.state, row.message, row.matches_json, row.revision_token) != (
                state, message, json.dumps(matches, ensure_ascii=False), revision,
            ):
                row.state = state; row.message = message
                row.matches_json = json.dumps(matches, ensure_ascii=False); row.revision_token = revision
                changed = True
        try:
            matches = json.loads(row.matches_json or "[]")
        except (TypeError, ValueError):
            matches = []
        display_rows.append({"capture": row, "matches": matches})
    if changed:
        db.session.commit()
    counts = {key: sum(1 for row in rows if row.state == key) for key in ("queued", "review", "conflict", "dismissed")}
    return render_template("offline_queue.html", rows=display_rows, counts=counts)


@app.route("/offline-queue/<int:capture_id>/dismiss", methods=["POST"])
@login_required
def offline_capture_dismiss(capture_id):
    row = db.get_or_404(OfflineCapture, capture_id)
    if row.collection_user_id not in (None, active_collection_user_id()): abort(403)
    row.state = "dismissed"; row.reviewed_at = utc_now()
    log_activity("offline_capture_dismissed", "offline_capture", row.id, f"Offline-Scan {row.barcode} abgeschlossen.")
    db.session.commit()
    flash("Offline-Erfassung wurde als erledigt markiert.", "success")
    return redirect(url_for("offline_queue"))


@app.route("/offline-queue/<int:capture_id>/restore", methods=["POST"])
@login_required
def offline_capture_restore(capture_id):
    row = db.get_or_404(OfflineCapture, capture_id)
    if row.collection_user_id not in (None, active_collection_user_id()): abort(403)
    state, message, matches, revision = _offline_capture_classification(row.barcode)
    row.state = state; row.message = message; row.reviewed_at = None
    row.matches_json = json.dumps(matches, ensure_ascii=False); row.revision_token = revision
    db.session.commit()
    flash("Offline-Erfassung ist wieder in der Prüfliste.", "success")
    return redirect(url_for("offline_queue"))


@app.route("/scanner")
@login_required
def scanner():
    batch_id = request.args.get("batch", type=int)
    batch = None
    if batch_id:
        batch = CaptureBatch.query.filter_by(id=batch_id, collection_user_id=active_collection_user_id(), state="open").first_or_404()
    return render_template("scanner.html", capture_batch=batch)


@app.route("/capture-batches", methods=["GET", "POST"])
@login_required
def capture_batches():
    owner_id = active_collection_user_id()
    if request.method == "POST":
        title = " ".join((request.form.get("title") or "Neue Erfassung").split())[:160]
        batch = CaptureBatch(collection_user_id=owner_id, actor_user_id=current_user.id, title=title or "Neue Erfassung",
                             store=" ".join((request.form.get("store") or "").split())[:160] or None,
                             purchase_total_eur=parse_money_input(request.form.get("purchase_total")))
        db.session.add(batch); db.session.commit()
        return redirect(url_for("capture_batch_detail", batch_id=batch.id))
    rows = CaptureBatch.query.filter_by(collection_user_id=owner_id).order_by(CaptureBatch.created_at.desc()).limit(100).all()
    return render_template("capture_batches.html", rows=rows)


@app.route("/capture-batches/<int:batch_id>", methods=["GET", "POST"])
@login_required
def capture_batch_detail(batch_id):
    batch = CaptureBatch.query.filter_by(id=batch_id, collection_user_id=active_collection_user_id()).first_or_404()
    if request.method == "POST":
        if batch.state != "open": abort(409)
        barcode = clean_barcode(request.form.get("barcode"))
        if not barcode or len(barcode) not in {8, 12, 13}:
            flash("Bitte eine gültige EAN/UPC mit 8, 12 oder 13 Ziffern eingeben.", "danger")
            return redirect(url_for("capture_batch_detail", batch_id=batch.id))
        existing = CaptureBatchItem.query.filter_by(batch_id=batch.id, barcode=barcode).first()
        if existing:
            existing.quantity += 1
            flash(f"{barcode} war bereits enthalten – Menge ist jetzt {existing.quantity}.", "success")
        else:
            state, message, matches, _revision = _offline_capture_classification(barcode)
            db.session.add(CaptureBatchItem(batch_id=batch.id, barcode=barcode, state=state, message=message,
                           matches_json=json.dumps(matches, ensure_ascii=False), purchase_price_eur=parse_money_input(request.form.get("purchase_price"))))
        db.session.commit()
        return redirect(url_for("capture_batch_detail", batch_id=batch.id, added=barcode))
    rows = []
    for item in batch.items:
        try: matches = json.loads(item.matches_json or "[]")
        except (TypeError, ValueError): matches = []
        rows.append({"item": item, "matches": matches})
    assigned_total = sum((row["item"].purchase_price_eur or 0) * max(row["item"].quantity or 1, 1) for row in rows)
    return render_template("capture_batch_detail.html", batch=batch, rows=rows, assigned_total=assigned_total)


@app.route("/capture-batches/<int:batch_id>/items/<int:item_id>", methods=["POST"])
@login_required
def capture_batch_item_update(batch_id, item_id):
    batch = CaptureBatch.query.filter_by(id=batch_id, collection_user_id=active_collection_user_id()).first_or_404()
    item = CaptureBatchItem.query.filter_by(id=item_id, batch_id=batch.id).first_or_404()
    if request.form.get("action") == "remove":
        db.session.delete(item)
    else:
        item.quantity = max(1, min(request.form.get("quantity", type=int) or 1, 999))
        item.purchase_price_eur = parse_money_input(request.form.get("purchase_price"))
    db.session.commit()
    return redirect(url_for("capture_batch_detail", batch_id=batch.id))


@app.route("/capture-batches/<int:batch_id>/finish", methods=["POST"])
@login_required
def capture_batch_finish(batch_id):
    batch = CaptureBatch.query.filter_by(id=batch_id, collection_user_id=active_collection_user_id()).first_or_404()
    batch.state = "review" if any(item.state in {"queued", "review", "conflict"} for item in batch.items) else "finished"
    batch.finished_at = utc_now()
    log_activity("capture_batch_finished", "capture_batch", batch.id, f"Stapel „{batch.title}“ mit {len(batch.items)} Barcodes abgeschlossen.")
    db.session.commit()
    flash("Stapel gespeichert. Ungeklärte Barcodes können jetzt einzeln zugeordnet werden.", "success")
    return redirect(url_for("capture_batch_detail", batch_id=batch.id))


@app.route("/api/capture-batches/<int:batch_id>/scan", methods=["POST"])
@login_required
def capture_batch_scan_api(batch_id):
    batch = CaptureBatch.query.filter_by(id=batch_id, collection_user_id=active_collection_user_id(), state="open").first_or_404()
    barcode = clean_barcode((request.get_json(silent=True) or {}).get("barcode"))
    if not barcode or len(barcode) not in {8, 12, 13}:
        return {"ok": False, "error": "invalid_barcode"}, 400
    item = CaptureBatchItem.query.filter_by(batch_id=batch.id, barcode=barcode).first()
    if item:
        item.quantity += 1; duplicate = True
    else:
        state, message, matches, _revision = _offline_capture_classification(barcode)
        item = CaptureBatchItem(batch_id=batch.id, barcode=barcode, state=state, message=message, matches_json=json.dumps(matches, ensure_ascii=False))
        db.session.add(item); duplicate = False
    db.session.commit()
    return {"ok": True, "barcode": barcode, "quantity": item.quantity, "duplicate": duplicate}


@app.route("/barcode/<barcode>")
@login_required
def barcode_lookup(barcode):
    code = clean_barcode(barcode)
    matches = Game.query.filter_by(barcode=code).order_by(Game.title).all() if code else []
    accessory_matches = scoped_accessory_query().filter_by(barcode=code).order_by(AccessoryItem.name).all() if code else []
    external_matches = []
    external_status = None
    if code and not matches and not accessory_matches and request.args.get("offline") != "1":
        external_matches = lookup_barcode_external(code)
        external_status = "ok" if external_matches else "empty"
    if request.args.get("json") == "1":
        return jsonify({
            "barcode": code,
            "matches": [{"id": g.id, "title": g.title, "console": g.console.name, "region": g.region, "edition": g.edition,
                         "owned": bool(collection_for(g) and collection_for(g).status == "owned")} for g in matches],
            "external_matches": external_matches,
            "accessory_matches": [{"id": a.id, "name": a.name, "category": a.category} for a in accessory_matches],
        })
    return render_template("barcode_result.html", barcode=code, matches=matches, external_matches=external_matches,
                           external_status=external_status, consoles=Console.query.order_by(Console.name).all(),
                           accessory_matches=accessory_matches, barcode_conflict=(len(matches) > 1), total_copies=sum(len(collection_items_for(g)) for g in matches))


@app.route("/external/import/barcode", methods=["POST"])
@login_required
def import_barcode_match():
    title = request.form.get("title", "").strip()
    platform = request.form.get("platform", "").strip()
    barcode = clean_barcode(request.form.get("barcode"))
    if not title or not platform:
        flash("Externer Treffer ist unvollständig.", "danger")
        return redirect(url_for("scanner"))
    console = get_or_create_console(platform)
    existing_barcode_games = barcode_conflicts(barcode)
    if existing_barcode_games and request.form.get("force_new") != "1":
        same = next((g for g in existing_barcode_games if g.console_id == console.id), existing_barcode_games[0])
        flash(f"EAN/UPC {barcode} ist bereits bei „{same.title}“ hinterlegt. Füge bei identischer Ausgabe lieber ein weiteres Exemplar hinzu.", "warning")
        return redirect(url_for("barcode_lookup", barcode=barcode))
    region = request.form.get("region", "PAL").strip() or "PAL"
    source = request.form.get("source", "External").strip()
    source_id = request.form.get("source_id", "").strip()
    game = None
    if source_id:
        game = Game.query.filter_by(external_source=source, external_id=source_id).first()
    if not game and barcode:
        game = Game.query.filter_by(barcode=barcode, console_id=console.id).first()
    if not game:
        game = Game(title=title, console_id=console.id, region=region, edition="Standard", barcode=barcode,
                    publisher=request.form.get("publisher", "").strip() or None,
                    cover_url=archived_or_original_image(request.form.get("cover_url")),
                    external_source=source, external_id=source_id or None)
        db.session.add(game)
        db.session.flush()
    db.session.commit()
    flash(f"{game.title} wurde als Katalogtitel gespeichert. Jetzt deine konkrete Kopie erfassen.", "success")
    return redirect(url_for("collection_configure", game_id=game.id, new=1, new_copy=1, ean_flow=1))


@app.route("/external/search/game", methods=["POST"])
@login_required
def external_game_search():
    barcode = clean_barcode(request.form.get("barcode"))
    title = request.form.get("title", "").strip()
    console_id = request.form.get("console_id", type=int)
    selected_console = db.session.get(Console, console_id) if console_id else None
    if not barcode or not title:
        flash("Barcode und Spieltitel sind für die Fallback-Suche erforderlich.", "danger")
        return redirect(url_for("scanner"))
    results, rawg_status = search_game_metadata(title, selected_console.name if selected_console else None)
    if not results:
        if rawg_status == "missing_key":
            flash("Kein Treffer. Für die breite Spiele-Metadatensuche kannst du optional RAWG_API_KEY in .env hinterlegen.", "warning")
        else:
            flash("Auch die Titelsuche hat keinen passenden Treffer geliefert.", "warning")
    return render_template("game_search_results.html", barcode=barcode, query=title, results=results,
                           selected_console=selected_console, consoles=Console.query.order_by(Console.name).all(),
                           rawg_status=rawg_status)


@app.route("/games/search/import", methods=["POST"])
@login_required
def import_catalog_search_match():
    """Create a master-catalog game from an online title search without creating a collection copy."""
    destination = request.form.get("destination", "catalog")
    title = request.form.get("title", "").strip()
    console_id = request.form.get("console_id", type=int)
    console = db.session.get(Console, console_id) if console_id else None
    if not title or not console:
        flash("Titel und Plattform sind für einen Katalogeintrag erforderlich.", "danger")
        return redirect(url_for("game_catalog_search", q=title))
    source = request.form.get("source", "External Game Search").strip()
    source_id = request.form.get("source_id", "").strip()
    region = request.form.get("region", "PAL").strip() or "PAL"
    barcode = clean_barcode(request.form.get("barcode"))

    game = None
    if source_id:
        game = Game.query.filter_by(external_source=source, external_id=source_id, console_id=console.id).first()
    if not game:
        game = Game.query.filter(
            db.func.lower(Game.title) == title.casefold(),
            Game.console_id == console.id,
            Game.region == region,
        ).first()
    if game:
        flash(f"„{game.title}“ ist bereits im Master-Katalog vorhanden.", "info")
        if destination == "collection":
            return redirect(url_for("collection_configure", game_id=game.id, new_copy=1))
        return redirect(url_for("game_detail", game_id=game.id))

    year = request.form.get("release_year", "").strip()
    rawg_detail = rawg_game_detail(source_id) if source == "RAWG" else {}
    game = Game(
        title=title, console_id=console.id, region=region, edition=request.form.get("edition", "Standard").strip() or "Standard",
        barcode=barcode,
        release_year=int(year) if year.isdigit() else (int(rawg_detail.get("release_year")) if str(rawg_detail.get("release_year", "")).isdigit() else None),
        publisher=request.form.get("publisher", "").strip() or rawg_detail.get("publisher") or None,
        developer=request.form.get("developer", "").strip() or rawg_detail.get("developer") or None,
        genre=request.form.get("genre", "").strip() or rawg_detail.get("genre") or None,
        cover_url=archived_or_original_image(request.form.get("cover_url", "").strip() or rawg_detail.get("cover_url")),
        external_source=source, external_id=source_id or None,
    )
    detected, source_name = infer_franchise_from_rawg(game)
    if detected:
        game.franchise = detected
        game.franchise_source = source_name
    game.series_status = "series" if game.franchise else "unreviewed"
    db.session.add(game)
    try:
        db.session.flush()
        log_activity("game_created", "game", game.id, f"Katalogtitel „{game.title}“ über Online-Suche angelegt.")
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Der Katalogeintrag konnte nicht angelegt werden. Möglicherweise existiert diese Variante bereits.", "warning")
        return redirect(url_for("game_catalog_search", q=title, console_id=console.id))
    if destination == "collection":
        flash(f"„{game.title}“ wurde angelegt. Erfasse jetzt dein Exemplar.", "success")
        return redirect(url_for("collection_configure", game_id=game.id, new=1, new_copy=1))
    flash(f"„{game.title}“ wurde als neuer Katalogtitel angelegt. Du besitzt das Spiel noch nicht? Kein Problem – es bleibt zunächst nur im Master-Katalog.", "success")
    return redirect(url_for("game_detail", game_id=game.id))


@app.route("/external/import/game-search", methods=["POST"])
@login_required
def import_game_search_match():
    title = request.form.get("title", "").strip()
    barcode = clean_barcode(request.form.get("barcode"))
    local_console_id = request.form.get("console_id", type=int)
    platform = request.form.get("platform", "").strip()
    console = db.session.get(Console, local_console_id) if local_console_id else None
    if not console:
        console = get_or_create_console(platform or "Unbekannte Plattform")
    if not title:
        flash("Der Suchtreffer ist unvollständig.", "danger")
        return redirect(url_for("game_catalog_search"))
    source = request.form.get("source", "External Game Search").strip()
    source_id = request.form.get("source_id", "").strip()
    rawg_detail = rawg_game_detail(source_id) if source == "RAWG" else {}
    game = Game.query.filter_by(barcode=barcode, console_id=console.id).first() if barcode else None
    if not game and source_id:
        game = Game.query.filter_by(external_source=source, external_id=source_id, console_id=console.id).first()
    if not game:
        game = Game.query.filter(
            db.func.lower(Game.title) == title.casefold(),
            Game.console_id == console.id,
            Game.region == (request.form.get("region", "PAL").strip() or "PAL"),
            Game.edition == "Standard",
        ).first()
    if not game:
        year = request.form.get("release_year", "").strip()
        game = Game(
            title=title, console_id=console.id, region=request.form.get("region", "PAL").strip() or "PAL",
            edition="Standard", barcode=barcode,
            release_year=int(year) if year.isdigit() else (int(rawg_detail.get("release_year")) if str(rawg_detail.get("release_year", "")).isdigit() else None),
            publisher=request.form.get("publisher", "").strip() or rawg_detail.get("publisher") or None,
            developer=request.form.get("developer", "").strip() or rawg_detail.get("developer") or None,
            genre=request.form.get("genre", "").strip() or rawg_detail.get("genre") or None,
            cover_url=archived_or_original_image(request.form.get("cover_url", "").strip() or rawg_detail.get("cover_url")),
            external_source=source, external_id=source_id or None,
        )
        db.session.add(game)
        db.session.flush()
    else:
        # Never lose the scanned identifier when enriching an existing external record.
        game.barcode = barcode
        if not game.cover_url:
            game.cover_url = archived_or_original_image(request.form.get("cover_url", "").strip() or rawg_detail.get("cover_url"))
        if not game.publisher:
            game.publisher = request.form.get("publisher", "").strip() or rawg_detail.get("publisher") or None
        if not game.developer:
            game.developer = request.form.get("developer", "").strip() or rawg_detail.get("developer") or None
        if not game.genre:
            game.genre = request.form.get("genre", "").strip() or rawg_detail.get("genre") or None
        if not game.release_year and request.form.get("release_year", "").isdigit():
            game.release_year = int(request.form.get("release_year"))
    if not game.franchise:
        detected, source_name = infer_franchise_from_rawg(game)
        if detected:
            game.franchise = detected
            game.franchise_source = source_name
    # Catalog search is also a pre-purchase workflow: importing a result must not
    # force the user to create a physical collection copy.
    db.session.commit()
    if request.form.get("destination") == "catalog":
        flash(f"{game.title} wurde als Katalogtitel gespeichert. EAN/UPC kann später ergänzt werden.", "success")
        return redirect(url_for("game_detail", game_id=game.id))
    flash(f"{game.title} wurde mit EAN/UPC {barcode} im Katalog gespeichert. Jetzt Zustand und Vollständigkeit erfassen.", "success")
    return redirect(url_for("collection_configure", game_id=game.id, new=1, new_copy=1, ean_flow=1))


@app.route("/retro", methods=["GET", "POST"])
@login_required
def retro_lookup():
    consoles = Console.query.order_by(Console.name).all()
    results = []
    title = request.form.get("title", "").strip() if request.method == "POST" else request.args.get("title", "").strip()
    console_id = request.form.get("console_id", type=int) if request.method == "POST" else request.args.get("console_id", type=int)
    product_code = (request.form.get("product_code", "") if request.method == "POST" else request.args.get("product_code", "")).strip()
    selected_console = db.session.get(Console, console_id) if console_id else None
    if request.method == "POST" and not selected_console:
        flash("Bitte zuerst eine Plattform auswählen.", "danger")
    elif request.method == "POST" and not title:
        flash("Bitte einen Spieltitel eingeben.", "danger")
    elif title and selected_console:
        results = retrobase_search(title, selected_console.name)
        if not results:
            flash("RetroBase hat keinen passenden Treffer geliefert. Du kannst das Spiel weiterhin manuell anlegen.", "warning")
    return render_template("retro.html", consoles=consoles, results=results, title=title,
                           selected_console=selected_console, product_code=product_code)


@app.route("/external/import/retro", methods=["POST"])
@login_required
def import_retro_match():
    title = request.form.get("title", "").strip()
    local_console_id = request.form.get("console_id", type=int)
    platform = request.form.get("platform", "").strip()
    console = db.session.get(Console, local_console_id) if local_console_id else None
    if not console:
        console = get_or_create_console(platform)
    region = request.form.get("region", "PAL").strip() or "PAL"
    external_id = request.form.get("external_id", "").strip()
    game = Game.query.filter_by(external_source="RetroBase Collection", external_id=external_id).first() if external_id else None
    if not game:
        game = Game(
            title=title, console_id=console.id, region=region, edition="Standard",
            release_year=int(request.form.get("release_year")) if request.form.get("release_year", "").isdigit() else None,
            publisher=request.form.get("publisher", "").strip(),
            developer=request.form.get("developer", "").strip(),
            genre=request.form.get("genre", "").strip(),
            product_code=normalize_product_code(request.form.get("product_code")),
            cover_url=archived_or_original_image(request.form.get("cover_url")),
            external_source="RetroBase Collection", external_id=external_id or None,
        )
        db.session.add(game)
        db.session.flush()
    if not game.franchise:
        detected = infer_franchise_name(game.title)
        if detected:
            game.franchise = detected
            game.franchise_source = "auto-rule"
            game.series_status = "series"
    elif game.franchise:
        game.series_status = "series"
    db.session.commit()
    flash(f"{game.title} wurde aus RetroBase als Katalogtitel übernommen. Jetzt deine konkrete Kopie erfassen.", "success")
    return redirect(url_for("collection_configure", game_id=game.id, new=1, new_copy=1, retro_flow=1))


def _csv_header_key(value):
    """Normalize spreadsheet headers, including hidden BOM/zero-width chars."""
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.replace("\ufeff", "").replace("\u200b", "").replace("\u2060", "")
    value = re.sub(r"[\s_-]+", "", value).casefold()
    return value


def _csv_alias(row, *names):
    lowered = {_csv_header_key(key): value for key, value in row.items()}
    for name in names:
        value = lowered.get(_csv_header_key(name))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _csv_reader_for_import(content, selected_delimiter):
    """Return a validated reader and recover from a wrongly submitted delimiter."""
    candidates = [selected_delimiter]
    try:
        detected = csv.Sniffer().sniff(content[:8192], delimiters=";,\t").delimiter
        if detected not in candidates:
            candidates.append(detected)
    except csv.Error:
        pass
    for delimiter in candidates:
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        headers = {_csv_header_key(value) for value in (reader.fieldnames or [])}
        if headers.intersection({"title", "titel"}) and headers.intersection({"console", "konsole", "plattform"}):
            return reader, delimiter
    visible = ", ".join(repr(str(value)) for value in (reader.fieldnames or []))
    raise ValueError(f"Pflichtspalten Titel/Title und Konsole/Console fehlen. Erkannte Kopfzeile: {visible or 'leer'}")


def _import_game_payload(row):
    title = _csv_alias(row, "title", "titel")
    console_name = canonical_console_name(_csv_alias(row, "console", "konsole", "plattform"))
    region = _csv_alias(row, "region") or "PAL"
    edition = _csv_alias(row, "edition", "ausgabe") or "Standard"
    year = _csv_alias(row, "release_year", "jahr", "erscheinungsjahr")
    franchise = _csv_alias(row, "franchise", "serie", "spielreihe")
    ownership_format = _csv_alias(row, "ownership_format", "besitztyp", "format").casefold()
    ownership_format = "digital" if ownership_format in {"digital", "download"} else "physical"
    return {
        "title": title, "console": console_name, "region": region, "edition": edition,
        "release_year": int(year) if year.isdigit() else None,
        "publisher": _csv_alias(row, "publisher", "herausgeber"),
        "developer": _csv_alias(row, "developer", "entwickler"),
        "genre": _csv_alias(row, "genre"), "franchise": canonical_franchise_name(franchise) if franchise else "",
        "barcode": clean_barcode(_csv_alias(row, "barcode", "ean", "upc")),
        "product_code": normalize_product_code(_csv_alias(row, "product_code", "produktcode", "productcode")),
        "cover_url": _csv_alias(row, "cover_url", "cover"),
        "ownership_format": ownership_format,
        "completeness": _csv_alias(row, "completeness", "vollständigkeit") or ("Digital" if ownership_format == "digital" else "Loose"),
        "storage_location": _csv_alias(row, "storage_location", "lagerort"),
        "notes": _csv_alias(row, "notes", "notizen"),
    }


def _import_row_match(payload):
    console = Console.query.filter(db.func.lower(Console.name) == payload["console"].casefold()).first()
    if not console:
        return None, "new", "Neue Plattform/Katalogtitel"
    exact = Game.query.filter(
        db.func.lower(Game.title) == payload["title"].casefold(), Game.console_id == console.id,
        db.func.lower(Game.region) == payload["region"].casefold(), db.func.lower(Game.edition) == payload["edition"].casefold(),
    ).first()
    if exact:
        return exact, "exact_duplicate", "Titel, Plattform, Region und Edition vorhanden"
    if payload.get("barcode"):
        match = Game.query.filter_by(barcode=payload["barcode"]).first()
        if match:
            return match, "barcode_duplicate", f"EAN/UPC bereits bei {match.title}"
    if payload.get("product_code"):
        match = Game.query.filter(Game.console_id == console.id, db.func.lower(Game.product_code) == payload["product_code"].casefold()).first()
        if match:
            return match, "product_duplicate", f"Produktcode bereits bei {match.title}"
    return None, "new", "Neuer Katalogtitel"


@app.route("/import/csv", methods=["GET", "POST"])
@login_required
def import_csv():
    uid = active_collection_user_id()
    if request.method == "POST":
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            flash("Bitte eine CSV-Datei auswählen.", "danger")
            return redirect(url_for("import_csv"))
        delimiter = request.form.get("delimiter", ";")
        if delimiter not in {";", ",", "\t"}:
            delimiter = ";"
        try:
            content = uploaded.read().decode("utf-8-sig")
            reader, delimiter = _csv_reader_for_import(content, delimiter)
            batch = ImportBatch(user_id=uid, filename=str(uploaded.filename)[:255], delimiter=delimiter, state="preview")
            db.session.add(batch); db.session.flush()
            seen_keys = {}; seen_barcodes = {}; seen_products = {}
            for number, raw in enumerate(reader, start=2):
                payload = _import_game_payload(raw)
                status = "new"; message = "Neuer Katalogtitel"; matched = None; duplicate_row = None
                if not payload["title"] or not payload["console"]:
                    status = "invalid"; message = "Titel oder Konsole fehlt"
                else:
                    row_key = (_search_text(payload["title"]), _search_text(payload["console"]), payload["region"].casefold(), payload["edition"].casefold())
                    prior_id = seen_keys.get(row_key) or (seen_barcodes.get(payload["barcode"]) if payload["barcode"] else None) or (seen_products.get((_search_text(payload["console"]), payload["product_code"].casefold())) if payload["product_code"] else None)
                    if prior_id:
                        status = "file_duplicate"; message = "Doppelzeile innerhalb dieser CSV-Datei"; duplicate_row = prior_id
                    else:
                        matched, status, message = _import_row_match(payload)
                    seen_keys[row_key] = None  # filled after row flush
                decision = "skip" if status == "invalid" else ("copy" if status != "new" else "owned")
                batch_row = ImportBatchRow(batch_id=batch.id, row_number=number, payload_json=json.dumps(payload, ensure_ascii=False), status=status, message=message, matched_game_id=matched.id if matched else None, duplicate_of_row_id=duplicate_row, decision=decision)
                db.session.add(batch_row); db.session.flush()
                if status != "invalid":
                    row_key = (_search_text(payload["title"]), _search_text(payload["console"]), payload["region"].casefold(), payload["edition"].casefold())
                    if seen_keys.get(row_key) is None: seen_keys[row_key] = batch_row.id
                    if payload["barcode"] and payload["barcode"] not in seen_barcodes: seen_barcodes[payload["barcode"]] = batch_row.id
                    product_key = (_search_text(payload["console"]), payload["product_code"].casefold()) if payload["product_code"] else None
                    if product_key and product_key not in seen_products: seen_products[product_key] = batch_row.id
            batch.total_count = len(batch.rows)
            batch.new_count = sum(1 for row in batch.rows if row.status == "new")
            batch.invalid_count = sum(1 for row in batch.rows if row.status == "invalid")
            batch.duplicate_count = batch.total_count - batch.new_count - batch.invalid_count
            db.session.commit()
            flash("CSV analysiert. Der Bestand wurde noch nicht verändert.", "success")
            return redirect(url_for("import_batch_detail", batch_id=batch.id))
        except Exception as exc:
            db.session.rollback(); flash(f"CSV-Vorschau fehlgeschlagen: {exc}", "danger")
            return redirect(url_for("import_csv"))
    batches = ImportBatch.query.filter_by(user_id=uid).order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc()).limit(20).all()
    return render_template("import_csv.html", batches=batches)


@app.route("/import/csv/batch/<int:batch_id>")
@login_required
def import_batch_detail(batch_id):
    batch = db.get_or_404(ImportBatch, batch_id)
    if batch.user_id != active_collection_user_id(): abort(403)
    rows = []
    for row in batch.rows:
        rows.append({"row": row, "payload": json.loads(row.payload_json)})
    return render_template("import_batch.html", batch=batch, rows=rows)


def _game_from_import_payload(payload):
    console = get_or_create_console(payload["console"])
    franchise = payload.get("franchise") or infer_franchise_name(payload["title"])
    return Game(title=payload["title"], console_id=console.id, region=payload["region"], edition=payload["edition"],
                release_year=payload.get("release_year"), publisher=payload.get("publisher"), developer=payload.get("developer"), genre=payload.get("genre"),
                franchise=franchise or None, franchise_source="manual" if payload.get("franchise") else ("auto-rule" if franchise else None),
                series_status="series" if franchise else "unreviewed", barcode=payload.get("barcode") or None,
                product_code=payload.get("product_code") or None, cover_url=archived_or_original_image(payload.get("cover_url")))


def _copy_from_import_payload(game, payload, user_id):
    digital = payload.get("ownership_format") == "digital"
    return CollectionItem(game_id=game.id, user_id=user_id, status="owned", ownership_format="digital" if digital else "physical",
                          completeness="Digital" if digital else (payload.get("completeness") or "Loose"), media_present=not digital,
                          storage_location=payload.get("storage_location") or None, notes=payload.get("notes") or None)


@app.route("/import/csv/batch/<int:batch_id>/apply", methods=["POST"])
@login_required
def import_batch_apply(batch_id):
    batch = db.get_or_404(ImportBatch, batch_id); uid = active_collection_user_id()
    if batch.user_id != uid: abort(403)
    if batch.state != "preview":
        flash("Dieser Importlauf wurde bereits verarbeitet.", "warning"); return redirect(url_for("import_batch_detail", batch_id=batch.id))
    added_games = added_copies = skipped = 0
    try:
        for row in batch.rows:
            decision = str(request.form.get(f"decision_{row.id}") or row.decision or "skip")
            allowed = {"skip"} if row.status == "invalid" else ({"owned", "catalog", "skip"} if row.status == "new" else {"copy", "skip"})
            if row.status == "file_duplicate": allowed = {"copy", "skip"}
            if decision not in allowed: decision = "skip"
            row.decision = decision
            if decision == "skip": skipped += 1; continue
            payload = json.loads(row.payload_json)
            game = row.matched_game
            if row.duplicate_of_row_id:
                prior = db.session.get(ImportBatchRow, row.duplicate_of_row_id)
                game = db.session.get(Game, prior.created_game_id) if prior and prior.created_game_id else (prior.matched_game if prior else None)
            if row.status == "new":
                game = _game_from_import_payload(payload); db.session.add(game); db.session.flush(); row.created_game_id = game.id; added_games += 1
            if decision in {"owned", "copy"}:
                if not game and row.status == "file_duplicate":
                    row.decision = "skip"; row.message = (row.message or "Doppelzeile") + " · Bezugszeile wurde übersprungen"
                    skipped += 1; continue
                if not game: raise ValueError(f"Zeile {row.row_number}: kein Zielspiel für das Exemplar")
                copy = _copy_from_import_payload(game, payload, uid); db.session.add(copy); db.session.flush(); row.created_copy_id = copy.id; added_copies += 1
        batch.state = "applied"; batch.applied_at = utc_now(); batch.added_game_count = added_games; batch.added_copy_count = added_copies
        log_activity("csv_import_applied", "import_batch", batch.id, f"{batch.filename}: {added_games} Katalogtitel, {added_copies} Exemplare, {skipped} übersprungen.")
        db.session.commit(); flash(f"Import abgeschlossen: {added_games} Katalogtitel und {added_copies} Exemplare angelegt; {skipped} übersprungen.", "success")
    except Exception as exc:
        db.session.rollback(); flash(f"Import abgebrochen; es wurde nichts gespeichert: {exc}", "danger")
    return redirect(url_for("import_batch_detail", batch_id=batch.id))


@app.route("/import/csv/batch/<int:batch_id>/undo", methods=["POST"])
@login_required
def import_batch_undo(batch_id):
    batch = db.get_or_404(ImportBatch, batch_id); uid = active_collection_user_id()
    if batch.user_id != uid: abort(403)
    if batch.state != "applied":
        flash("Nur ein ausgeführter Import kann rückgängig gemacht werden.", "warning"); return redirect(url_for("import_batch_detail", batch_id=batch.id))
    removed_copies = removed_games = kept_games = 0
    for row in reversed(batch.rows):
        copy = db.session.get(CollectionItem, row.created_copy_id) if row.created_copy_id else None
        if copy and copy.user_id == uid:
            db.session.delete(copy); removed_copies += 1; db.session.flush()
        game = db.session.get(Game, row.created_game_id) if row.created_game_id else None
        if game:
            if CollectionItem.query.filter_by(game_id=game.id).count() == 0:
                db.session.delete(game); removed_games += 1
            else:
                kept_games += 1
    batch.state = "undone"; batch.undone_at = utc_now()
    log_activity("csv_import_undone", "import_batch", batch.id, f"{batch.filename}: {removed_games} Titel und {removed_copies} Exemplare entfernt; {kept_games} nachträglich verwendete Titel behalten.")
    db.session.commit(); flash(f"Import rückgängig: {removed_games} Katalogtitel und {removed_copies} Exemplare entfernt." + (f" {kept_games} inzwischen verwendete Titel blieben erhalten." if kept_games else ""), "success")
    return redirect(url_for("import_batch_detail", batch_id=batch.id))



@app.route("/quality/duplicate-ignore", methods=["POST"])
@login_required
def duplicate_ignore():
    a = request.form.get("game_a_id", type=int); b = request.form.get("game_b_id", type=int)
    if not a or not b or a == b: abort(400)
    x,y=_dup_pair(a,b)
    if not DuplicateIgnore.query.filter_by(game_a_id=x, game_b_id=y).first():
        db.session.add(DuplicateIgnore(game_a_id=x, game_b_id=y)); db.session.commit()
    flash("Dieses Paar wird künftig nicht mehr als Dublette gemeldet.", "success")
    return redirect(url_for("quality", issue=request.form.get("issue") or ""))


@app.route("/quality/duplicate-merge", methods=["POST"])
@login_required
def duplicate_merge():
    keep_id = request.form.get("keep_game_id", type=int); remove_id = request.form.get("remove_game_id", type=int)
    if not keep_id or not remove_id or keep_id == remove_id: abort(400)
    pair = _dup_pair(keep_id, remove_id)
    candidates = {_dup_pair(row["a"].id, row["b"].id) for row in duplicate_candidates()}
    if pair not in candidates:
        flash("Dieses Paar ist kein aktuell bestätigter Dublettenkandidat.", "danger")
        return redirect(url_for("quality", issue="duplicate"))
    keep = db.get_or_404(Game, keep_id); remove = db.get_or_404(Game, remove_id)
    for field in ("language", "release_year", "publisher", "developer", "genre", "franchise", "franchise_source", "series_group", "series_generation", "barcode", "product_code", "cover_url", "external_source", "external_id"):
        if not getattr(keep, field, None) and getattr(remove, field, None):
            setattr(keep, field, getattr(remove, field))
    if keep.series_status == "unreviewed" and remove.series_status != "unreviewed":
        keep.series_status = remove.series_status
    moved = CollectionItem.query.filter_by(game_id=remove.id).update({CollectionItem.game_id: keep.id}, synchronize_session=False)
    ImportBatchRow.query.filter_by(matched_game_id=remove.id).update({ImportBatchRow.matched_game_id: keep.id}, synchronize_session=False)
    DuplicateIgnore.query.filter(db.or_(DuplicateIgnore.game_a_id == remove.id, DuplicateIgnore.game_b_id == remove.id, DuplicateIgnore.game_a_id == keep.id, DuplicateIgnore.game_b_id == keep.id)).delete(synchronize_session=False)
    removed_title = remove.title
    db.session.delete(remove)
    log_activity("catalog_duplicate_merged", "game", keep.id, f"{removed_title} wurde mit {keep.title} zusammengeführt; {moved} Exemplare verschoben.")
    db.session.commit()
    flash(f"Dubletten zusammengeführt. {moved} Exemplare blieben einzeln erhalten und wurden „{keep.title}“ zugeordnet.", "success")
    return redirect(url_for("game_detail", game_id=keep.id))


@app.route("/collection/<int:item_id>/quick-edit", methods=["POST"])
@login_required
def collection_quick_edit(item_id):
    item=db.get_or_404(CollectionItem,item_id)
    if item.user_id != active_collection_user_id(): abort(403)
    item.completeness="Digital" if item.ownership_format == "digital" else request.form.get("completeness", item.completeness)
    item.storage_location=request.form.get("storage_location", "").strip() or None
    item.play_status=request.form.get("play_status", item.play_status)
    for field in (("purchase_price",) if item.ownership_format == "digital" else ("purchase_price", "estimated_value")):
        present, value, error = form_money(field)
        if error:
            flash(error, "danger")
            return redirect(request.referrer or url_for("game_detail", game_id=item.game_id))
        if present:
            setattr(item, field, value)
    log_activity("copy_quick_edit", "collection_item", item.id, f"{item.game.title}: Schnellbearbeitung gespeichert.")
    if item.status == "owned":
        collection_total_value_snapshot()
    db.session.commit(); flash("Exemplar aktualisiert.", "success")
    return redirect(request.referrer or url_for("game_detail", game_id=item.game_id))


@app.route("/admin/data-health")
@login_required
def data_health():
    games=Game.query.all(); items=CollectionItem.query.filter_by(user_id=active_collection_user_id()).all()
    owned=[i for i in items if i.status=="owned"]
    def pct(n,d): return round(n/d*100) if d else 100
    stats={
      "games":len(games), "copies":len(owned),
      "barcode":sum(1 for g in games if g.barcode), "cover":sum(1 for g in games if g.cover_url),
      "external":sum(1 for g in games if g.external_source and g.external_id),
      "franchise":sum(1 for g in games if g.franchise),
      "valued":sum(1 for i in owned if effective_value(i) is not None),
      "quality":len(quality_issues()), "duplicates":len(duplicate_candidates()),
    }
    stats.update({"barcode_pct":pct(stats["barcode"],stats["games"]),"cover_pct":pct(stats["cover"],stats["games"]),"external_pct":pct(stats["external"],stats["games"]),"franchise_pct":pct(stats["franchise"],stats["games"]),"valued_pct":pct(stats["valued"],stats["copies"])})
    return render_template("data_health.html", stats=stats)


@app.route("/admin/operations")
@admin_required
def operations_center():
    """Compact operational diagnostics without exposing secrets or raw exceptions."""
    tables = set(inspect(db.engine).get_table_names())
    required = {"user", "collection_space", "collection_permission", "activity_log", "application_error", "bibo_work", "bibo_copy", "storage_location", "loan_record", "inventory_session"}
    upload_root = Path(app.root_path) / "static" / "uploads"
    upload_files = [path for path in upload_root.rglob("*") if path.is_file()] if upload_root.exists() else []
    backups_root = Path("/opt/gamecollector/backups")
    latest_backup = None
    if backups_root.exists():
        candidates = sorted((path for path in backups_root.rglob("*") if path.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)
        if candidates:
            latest_backup = datetime.fromtimestamp(candidates[0].stat().st_mtime)
    stats = {
        "schema_ok": required.issubset(tables), "missing_tables": sorted(required - tables),
        "users": User.query.filter_by(is_system=False).count(), "spaces": CollectionSpace.query.count(),
        "works": BiboWork.query.count(), "copies": BiboCopy.query.filter_by(active=True).count(),
        "locations": StorageLocation.query.count(), "open_loans": LoanRecord.query.filter_by(returned_at=None).count(),
        "errors_24h": ApplicationError.query.filter(ApplicationError.created_at >= utc_now() - timedelta(hours=24)).count(),
        "activity_24h": ActivityLog.query.filter(ActivityLog.created_at >= utc_now() - timedelta(hours=24)).count(),
        "archived_images": ImageAsset.query.filter_by(status="archived").count(),
        "failed_images": ImageAsset.query.filter_by(status="failed").count(),
        "upload_files": len(upload_files), "upload_bytes": sum(path.stat().st_size for path in upload_files),
        "latest_backup": latest_backup,
    }
    recent_errors = ApplicationError.query.order_by(ApplicationError.created_at.desc()).limit(12).all()
    recent_activity = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(12).all()
    return render_template("operations_center.html", stats=stats, recent_errors=recent_errors, recent_activity=recent_activity)


@app.route("/wishlist")
@login_required
def wishlist():
    rows = CollectionItem.query.join(Game).filter(CollectionItem.user_id == active_collection_user_id(), CollectionItem.status == "wishlist").all()
    rows.sort(key=lambda i: (-(i.wishlist_priority or 2), i.game.title.lower()))
    return render_template("wishlist.html", items=rows)


@app.route("/wishlist/<int:item_id>/purchased", methods=["POST"])
@login_required
def wishlist_purchased(item_id):
    item = db.get_or_404(CollectionItem, item_id)
    if item.user_id != active_collection_user_id(): abort(403)
    item.status = "owned"
    item.media_present = True
    item.purchase_price = parse_money_input(request.form.get("purchase_price")) or item.wishlist_target_price
    item.purchase_date = date.today()
    item.completeness = derive_completeness(item.media_present, item.box_present, item.manual_present, item.sealed)
    log_activity("wishlist_purchased", "collection_item", item.id, f"{item.game.title}: von der Wunschliste als gekauft markiert.")
    collection_total_value_snapshot()
    db.session.commit()
    flash("Spiel wurde in die Sammlung übernommen.", "success")
    return redirect(url_for("wishlist"))


@app.route("/collection/bulk", methods=["GET", "POST"])
@login_required
def collection_bulk():
    uid = active_collection_user_id()
    type_filter = (request.values.get("type") or "all").strip().lower()
    allowed_types = {"all", "games", "movies", "tv", "books", "music", "cards", "custom", "hardware", "accessories"}
    if type_filter not in allowed_types:
        type_filter = "all"
    query_text = (request.values.get("q") or "").strip()

    game_items = CollectionItem.query.join(Game).filter(CollectionItem.user_id == uid).order_by(Game.title, CollectionItem.id).all()
    collector_items = CollectorItem.query.filter_by(user_id=uid).order_by(CollectorItem.category, CollectorItem.title, CollectorItem.id).all()
    hardware_items = scoped_hardware_query().options(joinedload(HardwareItem.model).joinedload(HardwareModel.console)).order_by(HardwareItem.id).all()
    accessory_items = scoped_accessory_query().options(joinedload(AccessoryItem.console)).order_by(AccessoryItem.name, AccessoryItem.id).all()

    labels = {"games":"Games", "movies":"Filme", "tv":"TV-Serien", "books":"Bücher", "music":"Musik", "cards":"Sammelkarten", "custom":"Weitere", "hardware":"Hardware", "accessories":"Zubehör"}
    icons = {"games":"🎮", "movies":"🎬", "tv":"📺", "books":"📚", "music":"💿", "cards":"🃏", "custom":"📦", "hardware":"🕹️", "accessories":"🎛️"}
    rows = []
    for item in game_items:
        rows.append({"key":f"game:{item.id}", "kind":"games", "label":labels["games"], "icon":icons["games"], "title":item.game.title,
                     "subtitle":f"{item.game.console.name} · Exemplar #{item.id} · {item.status}", "storage":item.storage_location or ""})
    for item in collector_items:
        kind = item.category if item.category in labels else "custom"
        rows.append({"key":f"collector:{item.id}", "kind":kind, "label":labels[kind], "icon":icons[kind], "title":item.title,
                     "subtitle":f"{item.media_type or labels[kind]} · Exemplar #{item.id}", "storage":item.storage_location or ""})
    for item in hardware_items:
        rows.append({"key":f"hardware:{item.id}", "kind":"hardware", "label":labels["hardware"], "icon":icons["hardware"], "title":item.model.name,
                     "subtitle":f"{item.model.console.name} · Exemplar #{item.id} · {item.status}", "storage":item.storage_location or ""})
    for item in accessory_items:
        rows.append({"key":f"accessory:{item.id}", "kind":"accessories", "label":labels["accessories"], "icon":icons["accessories"], "title":item.name,
                     "subtitle":f"{item.console.name if item.console else 'Ohne Plattform'} · Exemplar #{item.id} · {item.status}", "storage":item.storage_location or ""})

    if type_filter != "all":
        rows = [row for row in rows if row["kind"] == type_filter]
    if query_text:
        needle = _search_text(query_text)
        rows = [row for row in rows if needle in _search_text(row["title"] + " " + row["subtitle"])]

    if request.method == "POST":
        selected_keys = set(request.form.getlist("item_keys"))
        selected_rows = [row for row in rows if row["key"] in selected_keys]
        if not selected_rows:
            flash("Bitte mindestens einen Eintrag auswählen.", "warning")
            return redirect(url_for("collection_bulk", type=type_filter, q=query_text))

        selected_by_type = {"game":[], "collector":[], "hardware":[], "accessory":[]}
        for key in selected_keys:
            prefix, sep, raw_id = key.partition(":")
            if sep and prefix in selected_by_type and raw_id.isdigit():
                selected_by_type[prefix].append(int(raw_id))
        selected_games = [x for x in game_items if x.id in selected_by_type["game"]]
        selected_collectors = [x for x in collector_items if x.id in selected_by_type["collector"]]
        selected_hardware = [x for x in hardware_items if x.id in selected_by_type["hardware"]]
        selected_accessories = [x for x in accessory_items if x.id in selected_by_type["accessory"]]

        storage_mode = request.form.get("storage_mode") or "keep"
        storage_value = request.form.get("storage_location", "").strip() or None
        note_addition = request.form.get("append_notes", "").strip()
        all_selected = selected_games + selected_collectors + selected_hardware + selected_accessories
        for item in all_selected:
            if storage_mode == "set": item.storage_location = storage_value
            elif storage_mode == "clear": item.storage_location = None
            if note_addition:
                item.notes = ((item.notes or "").rstrip() + ("\n" if item.notes else "") + note_addition)

        status = request.form.get("set_status") or ""
        for item in selected_games + selected_hardware + selected_accessories:
            if status in {"owned", "wishlist"}: item.status = status

        for item in selected_games:
            if request.form.get("tags"): item.tags = request.form["tags"].strip() or None
            if request.form.get("play_status"): item.play_status = request.form["play_status"]
            if request.form.get("region"): item.game.region = request.form["region"].strip()
            cid = request.form.get("console_id", type=int)
            if cid: item.game.console_id = cid
            if request.form.get("media_present") in {"yes", "no"}: item.media_present = request.form.get("media_present") == "yes"
            if request.form.get("box_present") in {"yes", "no"}: item.box_present = request.form.get("box_present") == "yes"
            if request.form.get("manual_present") in {"yes", "no"}: item.manual_present = request.form.get("manual_present") == "yes"
            item.completeness = derive_completeness(item.media_present, item.box_present, item.manual_present, item.sealed)

        collector_condition = request.form.get("collector_condition") or ""
        collector_completeness = request.form.get("collector_completeness") or ""
        collector_media_type = request.form.get("collector_media_type", "").strip()
        de_physical_status = request.form.get("de_physical_status") or ""
        for item in selected_collectors:
            if collector_condition: item.condition = collector_condition
            # Completeness is meaningful for packaged media, but not books.
            if collector_completeness and item.category != "books": item.completeness = collector_completeness
            if collector_media_type: item.media_type = collector_media_type[:120]
            if item.category in {"movies", "tv"} and de_physical_status in {"physical", "never_physical_de", "unknown"}:
                meta = collector_metadata(item)
                if de_physical_status == "unknown": meta.pop("de_physical_release_status", None)
                else: meta["de_physical_release_status"] = de_physical_status
                item.metadata_json = json.dumps(meta, ensure_ascii=False)
                tmdb_id = str(meta.get("tmdb_id") or (item.external_id if str(item.external_source or "").upper() == "TMDB" else "") or "").strip()
                if item.category == "movies" and tmdb_id.isdigit():
                    collection = meta.get("tmdb_collection") or {}
                    collection_id = str(collection.get("id") or "").strip() if isinstance(collection, dict) else ""
                    if collection_id:
                        statuses = _movie_collection_statuses(uid, collection_id)
                        if de_physical_status == "unknown": statuses.pop(tmdb_id, None)
                        else: statuses[tmdb_id] = de_physical_status
                        _set_movie_collection_statuses(uid, collection_id, statuses)
                elif item.category == "tv" and tmdb_id.isdigit():
                    season = _tv_season_number(item, meta)
                    if season is not None:
                        statuses = _tv_disc_statuses(uid, tmdb_id)
                        if de_physical_status == "unknown": statuses.pop(str(season), None)
                        else: statuses[str(season)] = de_physical_status
                        _set_tv_disc_statuses(uid, tmdb_id, statuses)

        score = request.form.get("condition_score", type=int)
        boxed = request.form.get("boxed") or ""
        tested = request.form.get("tested_status") or ""
        for item in selected_hardware + selected_accessories:
            if score is not None and 1 <= score <= 10: item.condition = score
            if boxed in {"yes", "no"}: item.boxed = boxed == "yes"
        for item in selected_hardware:
            if tested in {"tested", "untested", "defective"}: item.tested_status = tested
            item.completeness = derive_hardware_completeness(item)
            calculate_hardware_set(item)

        count = len(selected_rows)
        log_activity("bulk_update", "bibo_inventory", None, f"{count} Bibo-Einträge gesammelt bearbeitet.", {"keys": sorted(selected_keys)})
        collection_total_value_snapshot()
        db.session.commit()
        flash(f"{count} Einträge aus {sum(bool(x) for x in (selected_games, selected_collectors, selected_hardware, selected_accessories))} Bereichen aktualisiert.", "success")
        return redirect(url_for("collection_bulk", type=type_filter, q=query_text))
    counts = {key: 0 for key in labels}
    for row in rows: counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    return render_template("bulk_edit.html", rows=rows, counts=counts, labels=labels, icons=icons, selected_type=type_filter,
                           query_text=query_text, consoles=Console.query.order_by(Console.name).all())


@app.route("/standalone")
@login_required
def standalone_games():
    games = Game.query.filter(Game.series_status == "standalone").order_by(Game.console_id, Game.title).all()
    return render_template("standalone.html", games=games)


@app.route("/timeline")
@login_required
def timeline():
    games = Game.query.order_by(Game.release_year.desc().nullslast(), Game.title).all()
    years = {}
    for game in games:
        years.setdefault(game.release_year or "Unbekannt", []).append(game)
    return render_template("timeline.html", years=years)


@app.route("/publishers")
@login_required
def publishers():
    rows = db.session.query(Game.publisher, db.func.count(Game.id)).filter(Game.publisher.isnot(None), Game.publisher != "").group_by(Game.publisher).order_by(Game.publisher).all()
    return render_template("metadata_index.html", heading="Publisher", rows=rows, field="publisher")


@app.route("/developers")
@login_required
def developers():
    rows = db.session.query(Game.developer, db.func.count(Game.id)).filter(Game.developer.isnot(None), Game.developer != "").group_by(Game.developer).order_by(Game.developer).all()
    return render_template("metadata_index.html", heading="Entwickler", rows=rows, field="developer")


@app.route("/metadata/<field>/<path:value>")
@login_required
def metadata_games(field, value):
    if field not in {"publisher", "developer"}: abort(404)
    column = Game.publisher if field == "publisher" else Game.developer
    games = Game.query.filter(column == value).order_by(Game.release_year.asc().nullslast(), Game.title).all()
    return render_template("metadata_games.html", heading=("Publisher" if field == "publisher" else "Entwickler"), value=value, games=games)


HARDWARE_CLASS_LABELS = {"stationary":"Stationäre Konsole", "handheld":"Handheld", "hybrid":"Hybridkonsole", "mini":"Mini-/Classic-Konsole", "accessory":"Zubehörgerät", "pc":"Desktop-PC"}
HARDWARE_COMPONENT_PROFILES = {
 "stationary":[("console","Konsole / Gehäuse",30),("function","Funktion und Laufwerk",25),("controller","Original-Controller",20),("box","OVP und Inlays",12),("power","Netzteil",6),("cables","Bild-/Anschlusskabel",4),("manual","Anleitung und Beilagen",3)],
 "handheld":[("case","Gehäuse",22),("display","Display(s)",22),("function","Funktion / Modulschacht",18),("hinge","Scharnier",10),("controls","Tasten / Steuerkreuz / Circle Pad",12),("stylus","Original-Stylus",4),("battery","Akku",5),("box","OVP und Inlays",5),("power","Netzteil / Ladekabel",2)],
 "hybrid":[("console","Tablet / Konsole",24),("display","Display / Touchscreen",16),("function","Funktion / Modulschacht",15),("controllers","Joy-Cons / Controller",18),("rails","Schienen / Sticks / Tasten",8),("dock","Dockingstation",8),("box","OVP und Inlays",6),("power","Netzteil",3),("cables","HDMI-/Anschlusskabel",2)],
 "mini":[("console","Konsole / Gehäuse",30),("function","Funktion",25),("controllers","Original-Controller",22),("box","OVP und Inlays",12),("power","USB-Netzteil",6),("cables","HDMI-/Anschlusskabel",5)],
 "accessory":[("device","Gerät / Gehäuse",35),("function","Funktion",30),("controls","Tasten / Sticks / Sensoren",20),("box","OVP und Inlays",10),("cables","Kabel / Empfänger / Adapter",5)],
 "pc":[("case","Gehäuse",8),("mainboard","Mainboard",13),("cpu","Prozessor (CPU)",15),("cpu_cooler","CPU-Kühler",5),("ram","Arbeitsspeicher (RAM)",10),("gpu","Grafikkarte / integrierte Grafik",15),("storage_primary","Primärer Speicher (SSD/HDD)",10),("storage_secondary","Weiterer Speicher",4),("psu","Netzteil",10),("network","Netzwerk / WLAN",3),("optical","Optisches Laufwerk",2),("function","Gesamtsystem und Anschlüsse",5)],
}

PC_COMPONENT_FIELDS = {
    "case": [
        {"key":"brand","label":"Hersteller","choices":["be quiet!","Corsair","Fractal Design","Lian Li","NZXT","Cooler Master","Thermaltake","Sonstige"]},
        {"key":"family","label":"Bauform","choices":["Full-Tower","Midi-Tower","Mini-Tower","Desktop","Small Form Factor (SFF)","Mini-PC","Sonstige"]},
    ],
    "mainboard": [
        {"key":"brand","label":"Hersteller","choices":["ASUS","MSI","Gigabyte","ASRock","Biostar","OEM","Sonstige"]},
        {"key":"family","label":"Sockel / Plattform","choices":["AM5","AM4","TRX50","sTRX4","LGA 1851","LGA 1700","LGA 1200","LGA 1151","Sonstige"]},
        {"key":"spec","label":"Formfaktor","choices":["E-ATX","ATX","Micro-ATX","Mini-ITX","Proprietär","Sonstige"]},
    ],
    "cpu": [
        {"key":"brand","label":"CPU-Hersteller","choices":["AMD","Intel","Apple","VIA","Sonstige"]},
        {"key":"family","label":"Architektur / Familie","choices":["AMD Ryzen 3","AMD Ryzen 5","AMD Ryzen 7","AMD Ryzen 9","AMD Ryzen Threadripper","AMD FX","Intel Core i3","Intel Core i5","Intel Core i7","Intel Core i9","Intel Core Ultra 5","Intel Core Ultra 7","Intel Core Ultra 9","Intel Xeon","Sonstige"]},
    ],
    "cpu_cooler": [
        {"key":"brand","label":"Hersteller","choices":["be quiet!","Noctua","Arctic","Corsair","NZXT","Cooler Master","Thermalright","AMD Boxed","Intel Boxed","Sonstige"]},
        {"key":"family","label":"Kühlung","choices":["Luftkühler","AIO-Wasserkühlung 120 mm","AIO-Wasserkühlung 240 mm","AIO-Wasserkühlung 280 mm","AIO-Wasserkühlung 360 mm","Custom-Wasserkühlung","Boxed-Kühler","Passiv","Sonstige"]},
    ],
    "ram": [
        {"key":"brand","label":"Hersteller","choices":["Corsair","G.Skill","Kingston","Crucial","Samsung","TeamGroup","Patriot","OEM","Sonstige"]},
        {"key":"capacity","label":"Gesamtkapazität","choices":["4 GB","8 GB","16 GB","24 GB","32 GB","48 GB","64 GB","96 GB","128 GB","192 GB","256 GB","Sonstige"]},
        {"key":"family","label":"Generation","choices":["DDR2","DDR3","DDR4","DDR5","LPDDR4","LPDDR5","Sonstige"]},
        {"key":"spec","label":"Takt","choices":["1600 MHz","2133 MHz","2400 MHz","2666 MHz","2933 MHz","3200 MHz","3600 MHz","4800 MHz","5200 MHz","5600 MHz","6000 MHz","6400 MHz","7200 MHz","Sonstige"]},
    ],
    "gpu": [
        {"key":"brand","label":"GPU-Hersteller","choices":["NVIDIA","AMD","Intel","Integriert","Sonstige"]},
        {"key":"family","label":"Grafikfamilie","choices":["NVIDIA GeForce RTX","NVIDIA GeForce GTX","NVIDIA Quadro / RTX Pro","AMD Radeon RX","AMD Radeon Pro","Intel Arc","Intel UHD / Iris Xe","AMD Radeon Graphics (integriert)","Sonstige"]},
        {"key":"capacity","label":"Grafikspeicher","choices":["Integriert / Shared","2 GB","4 GB","6 GB","8 GB","10 GB","12 GB","16 GB","20 GB","24 GB","32 GB","Sonstige"]},
    ],
    "storage_primary": [
        {"key":"brand","label":"Hersteller","choices":["Samsung","Western Digital","Crucial","Kingston","Seagate","SanDisk","Kioxia","SK hynix","Sonstige"]},
        {"key":"family","label":"Speichertyp","choices":["NVMe SSD (M.2)","SATA SSD (2,5 Zoll)","SATA HDD (3,5 Zoll)","SATA HDD (2,5 Zoll)","PCIe-Steckkarte","Sonstige"]},
        {"key":"capacity","label":"Kapazität","choices":["128 GB","256 GB","500 GB","512 GB","1 TB","2 TB","4 TB","8 TB","12 TB","16 TB","Sonstige"]},
    ],
    "storage_secondary": [
        {"key":"brand","label":"Hersteller","choices":["Samsung","Western Digital","Crucial","Kingston","Seagate","SanDisk","Kioxia","SK hynix","Sonstige"]},
        {"key":"family","label":"Speichertyp","choices":["NVMe SSD (M.2)","SATA SSD (2,5 Zoll)","SATA HDD (3,5 Zoll)","SATA HDD (2,5 Zoll)","Externes Laufwerk","Sonstige"]},
        {"key":"capacity","label":"Kapazität","choices":["128 GB","256 GB","500 GB","512 GB","1 TB","2 TB","4 TB","8 TB","12 TB","16 TB","Sonstige"]},
    ],
    "psu": [
        {"key":"brand","label":"Hersteller","choices":["be quiet!","Corsair","Seasonic","Enermax","Cooler Master","Thermaltake","ASUS","MSI","OEM","Sonstige"]},
        {"key":"capacity","label":"Leistung","choices":["300 W","400 W","450 W","500 W","550 W","600 W","650 W","700 W","750 W","800 W","850 W","1000 W","1200 W","1500 W","Sonstige"]},
        {"key":"family","label":"Effizienz","choices":["Ohne Zertifikat","80 PLUS","80 PLUS Bronze","80 PLUS Silver","80 PLUS Gold","80 PLUS Platinum","80 PLUS Titanium","Sonstige"]},
    ],
    "network": [
        {"key":"brand","label":"Hersteller","choices":["Intel","Realtek","Broadcom","Killer","TP-Link","ASUS","Onboard","Sonstige"]},
        {"key":"family","label":"Anbindung","choices":["1 Gbit LAN","2,5 Gbit LAN","5 Gbit LAN","10 Gbit LAN","WLAN 5","WLAN 6","WLAN 6E","WLAN 7","Bluetooth","Sonstige"]},
    ],
    "optical": [
        {"key":"brand","label":"Hersteller","choices":["ASUS","LG","Pioneer","Samsung","Sony","Lite-On","Sonstige"]},
        {"key":"family","label":"Laufwerkstyp","choices":["DVD-ROM","DVD-Brenner","Blu-ray-ROM","Blu-ray-Brenner","4K-UHD-Blu-ray","Sonstige"]},
    ],
}

# Model-specific profiles. A generic "handheld" profile cannot describe a
# classic Game Boy, a folding GBA SP and a touch-based DS correctly at once.
HARDWARE_MODEL_COMPONENT_PROFILES = {
 "gameboy_classic":[("case","Gehäuse",25),("display","Display / Displayscheibe",20),("function","Funktion / Modulschacht",20),("controls","Tasten / Steuerkreuz",18),("battery_compartment","Batteriefach und Kontakte",10),("box","OVP und Inlays",5),("manual","Anleitung und Beilagen",2)],
 "gameboy_advance":[("case","Gehäuse",23),("display","Display / Displayscheibe",20),("function","Funktion / Modulschacht",18),("controls","Tasten, Steuerkreuz und Schultertasten",20),("battery_compartment","Batteriefach und Kontakte",10),("box","OVP und Inlays",6),("manual","Anleitung und Beilagen",3)],
 "gameboy_advance_sp":[("case","Gehäuse",18),("display","Display",18),("function","Funktion / Modulschacht",16),("hinge","Scharnier und Klappmechanik",12),("controls","Tasten, Steuerkreuz und Schultertasten",18),("battery","Akku",8),("power","Original-Ladegerät",5),("box","OVP und Inlays",3),("manual","Anleitung und Beilagen",2)],
 "gameboy_micro":[("case","Gehäuse / Frontblende",20),("display","Display",20),("function","Funktion / Modulschacht",18),("controls","Tasten, Steuerkreuz und Schultertasten",22),("battery","Akku",10),("power","Original-Ladegerät",5),("box","OVP und Inlays",3),("manual","Anleitung und Beilagen",2)],
 "ds_clamshell":[("case","Gehäuse",14),("display","Beide Displays / Touchscreen",20),("function","Funktion / Modulschächte",15),("hinge","Scharnier und Klappmechanik",12),("controls","Tasten, Steuerkreuz und Touchfunktion",15),("stylus","Original-Touchpen",7),("battery","Akku",7),("power","Original-Ladegerät",5),("box","OVP und Inlays",3),("manual","Anleitung und Beilagen",2)],
 "ds_slab":[("case","Gehäuse",18),("display","Beide Displays / Touchscreen",22),("function","Funktion / Modulschacht",16),("controls","Tasten, Steuerkreuz und Touchfunktion",18),("stylus","Original-Touchpen",8),("battery","Akku",8),("power","Original-Ladegerät",5),("box","OVP und Inlays",3),("manual","Anleitung und Beilagen",2)],
 "sony_handheld":[("case","Gehäuse",20),("display","Display / Touchscreen",20),("function","Funktion / Laufwerk oder Kartenschacht",20),("controls","Tasten, Steuerkreuz und Analogsticks",22),("battery","Akku",8),("power","Original-Ladegerät",5),("box","OVP und Inlays",3),("manual","Anleitung und Beilagen",2)],
 "classic_handheld":[("case","Gehäuse",24),("display","Display / Displayscheibe",20),("function","Funktion / Modulschacht",22),("controls","Tasten / Steuerkreuz",18),("battery_compartment","Batteriefach und Kontakte",9),("box","OVP und Inlays",5),("manual","Anleitung und Beilagen",2)],
 "switch_standard":[("console","Tablet / Konsole",20),("display","Display / Touchscreen",14),("function","Funktion / Modulschacht",13),("controllers","Joy-Con-Paar",16),("rails","Joy-Con-Schienen, Sticks und Tasten",8),("dock","Dockingstation",8),("grip","Joy-Con-Halterung und Schlaufen",5),("power","Original-Netzteil",5),("cables","HDMI-Kabel",3),("box","OVP und Inlays",5),("manual","Anleitung und Beilagen",3)],
 "switch_lite":[("case","Gehäuse",20),("display","Display / Touchscreen",18),("function","Funktion / Modulschacht",18),("controls","Tasten, Steuerkreuz und Sticks",24),("battery","Akku",8),("power","Original-Netzteil",5),("box","OVP und Inlays",5),("manual","Anleitung und Beilagen",2)],
 "wii_u":[("console","Wii-U-Konsole",22),("function","Funktion und Laufwerk",18),("gamepad","Wii U GamePad",20),("gamepad_display","GamePad-Display und Touchscreen",10),("gamepad_controls","GamePad-Tasten und Sticks",8),("power","Konsolen-Netzteil",5),("gamepad_power","GamePad-Netzteil",5),("cables","HDMI-/Anschlusskabel",3),("box","OVP und Inlays",6),("manual","Anleitung und Beilagen",3)],
}

def _is_pc_hardware_model(model):
    console_name = _search_text(model.console.name if model.console else "")
    manufacturer = _search_text(model.console.manufacturer if model.console else "")
    text_value = _search_text(" ".join(x for x in (model.name, model.console.name if model.console else "") if x))
    return (
        console_name in {"pc", "pc windows", "windows pc", "computer", "desktop pc"}
        or manufacturer in {"pc", "computer"}
        or any(x in text_value for x in ("gaming pc", "desktop pc", "tower pc", "windows pc", "pc windows"))
    )


def infer_hardware_class(model):
    text_value = _search_text(" ".join(x for x in (model.name, model.console.name if model.console else "") if x))
    if any(x in text_value for x in ("switch", "steam deck", "rog ally")): return "hybrid"
    if _is_pc_hardware_model(model): return "pc"
    if any(x in text_value for x in ("game boy", "nintendo ds", "3ds", "2ds", "psp", "vita", "game gear", "pocket", "handheld")): return "handheld"
    if any(x in text_value for x in ("mini", "classic", "playstation tv")): return "mini"
    if any(x in text_value for x in ("controller", "kamera", "camera", "portal", "adapter")): return "accessory"
    return "stationary"

def hardware_class(model):
    if _is_pc_hardware_model(model):
        return "pc"
    value = (model.hardware_class or "").strip()
    return value if value in HARDWARE_COMPONENT_PROFILES else infer_hardware_class(model)


def repair_pc_hardware_profiles():
    """Convert legacy PC rows that were accidentally treated as consoles."""
    changed = 0
    optional = {"storage_secondary", "network", "optical"}
    for model in HardwareModel.query.options(joinedload(HardwareModel.console)).all():
        if not _is_pc_hardware_model(model):
            continue
        if model.hardware_class != "pc":
            model.hardware_class = "pc"
            changed += 1
        profile = HARDWARE_COMPONENT_PROFILES["pc"]
        allowed = {key for key, _, _ in profile}
        for item in model.items:
            old_data = hardware_components(item)
            data = {key: value for key, value in old_data.items() if key in allowed and isinstance(value, dict)}
            for key, _, _ in profile:
                if key in data:
                    continue
                data[key] = {
                    "availability": "na" if key in optional else "present",
                    "condition": item.condition or 8,
                    "function": "tested" if item.tested_status == "tested" else (item.tested_status or "untested"),
                    "original": True,
                    "details": "",
                    "notes": "",
                }
            serialized = json.dumps(data, ensure_ascii=False)
            if item.component_data != serialized:
                item.component_data = serialized
                changed += 1
            if item.controller_present:
                item.controller_present = False
                item.controller_condition = 8
                changed += 1
            item.completeness = derive_hardware_completeness(item)
            calculate_hardware_set(item)
    if changed:
        db.session.commit()
        app.logger.info("Bibo repaired %d PC hardware profile field(s)", changed)
    return changed

def hardware_components(item):
    try: data = json.loads(item.component_data or "{}")
    except (TypeError, ValueError): data = {}
    return data if isinstance(data, dict) else {}

def component_profile(model):
    name = _search_text(" ".join(x for x in (model.name, model.console.name if model.console else "") if x))
    if hardware_class(model) == "pc": profile_key = "pc"
    elif "game boy advance sp" in name: profile_key = "gameboy_advance_sp"
    elif "game boy micro" in name: profile_key = "gameboy_micro"
    elif "game boy advance" in name: profile_key = "gameboy_advance"
    elif any(x in name for x in ("game boy color", "game boy pocket", "game boy light", "game boy")): profile_key = "gameboy_classic"
    elif "new nintendo 2ds xl" in name: profile_key = "ds_clamshell"
    elif "nintendo 2ds" in name: profile_key = "ds_slab"
    elif any(x in name for x in ("nintendo ds", "nintendo dsi", "nintendo 3ds", "new nintendo 3ds")): profile_key = "ds_clamshell"
    elif any(x in name for x in ("psp", "ps vita")): profile_key = "sony_handheld"
    elif any(x in name for x in ("game gear", "neo geo pocket")): profile_key = "classic_handheld"
    elif "switch lite" in name: profile_key = "switch_lite"
    elif "nintendo switch" in name: profile_key = "switch_standard"
    elif "wii u" in name: profile_key = "wii_u"
    else: profile_key = hardware_class(model)
    profile = HARDWARE_MODEL_COMPONENT_PROFILES.get(profile_key, HARDWARE_COMPONENT_PROFILES.get(profile_key))
    return [{"key":k,"label":label,"weight":weight} for k,label,weight in profile]

def component_form_values(item):
    saved = hardware_components(item)
    return {comp["key"]:(saved.get(comp["key"]) or _legacy_component_default(item, comp["key"])) for comp in component_profile(item.model)}

def _legacy_component_default(item, key):
    presence = {"controller":item.controller_present,"controllers":item.controller_present,"gamepad":item.controller_present,"box":item.boxed,"power":item.power_supply_present,"gamepad_power":item.power_supply_present,"cables":item.cables_present,"manual":item.manual_present}
    condition = item.box_condition if key == "box" else (item.controller_condition if key in {"controller","controllers","controls"} else item.condition)
    return {"availability":"present" if presence.get(key, True) else "missing", "condition":condition or 8, "function":"tested" if item.tested_status == "tested" else (item.tested_status or "untested"), "original":bool(presence.get(key, True)), "notes":""}

def calculate_hardware_set(item):
    profile = component_profile(item.model)
    data = hardware_components(item)
    weighted = weight_total = 0.0; present = missing = 0; problems = []
    for comp in profile:
        row = data.get(comp["key"]) or _legacy_component_default(item, comp["key"])
        availability = row.get("availability", "present")
        if availability == "na": continue
        if availability == "missing": missing += 1; continue
        present += 1; score = max(1, min(10, int(row.get("condition") or 8)))
        if row.get("function") == "defective": score *= .35; problems.append(f"{comp['label']} defekt")
        elif row.get("function") == "partial": score *= .65; problems.append(f"{comp['label']} teilweise defekt")
        elif row.get("function") == "untested": score *= .85
        if not row.get("original", True): score *= .95
        weighted += score * comp["weight"]; weight_total += comp["weight"]
    result = round(weighted / weight_total, 1) if weight_total else float(item.condition or 8)
    label = "Neuwertig" if result >= 9 else "Sehr gut" if result >= 8 else "Gut" if result >= 6.5 else "Akzeptabel" if result >= 5 else "Defekt / Restaurierungsobjekt"
    item.set_condition=result; item.set_condition_label=label; item.condition=max(1,min(10,round(result)))
    item.condition_summary=f"{item.model.name} · {item.completeness or 'Loose'} · Gesamtzustand {result:.1f}/10 ({label}). {present} Komponenten bewertet"
    if missing: item.condition_summary += f", {missing} fehlen"
    if problems: item.condition_summary += ". " + "; ".join(problems[:3])
    return result

def apply_component_form(item):
    data = {}
    for comp in component_profile(item.model):
        key=comp["key"]; availability=request.form.get(f"component_{key}_availability","present")
        data[key]={"availability":availability if availability in {"present","missing","na"} else "present",
                   "condition":max(1,min(10,request.form.get(f"component_{key}_condition",type=int) or 8)),
                   "function":request.form.get(f"component_{key}_function","tested") if request.form.get(f"component_{key}_function","tested") in {"tested","untested","partial","defective"} else "tested",
                   "original":request.form.get(f"component_{key}_original")=="1",
                   "details":request.form.get(f"component_{key}_details","").strip()[:300],
                   "notes":request.form.get(f"component_{key}_notes","").strip()[:300]}
        if hardware_class(item.model) == "pc":
            for field in PC_COMPONENT_FIELDS.get(key, []):
                field_key = field["key"]
                data[key][field_key] = request.form.get(f"component_{key}_{field_key}", "").strip()[:160]
    item.component_data=json.dumps(data,ensure_ascii=False)

HARDWARE_MODEL_PRESETS = {
    "Nintendo Entertainment System (NES)": ["NES Frontloader", "NES Toploader"],
    "Super Nintendo (SNES)": ["Super Nintendo PAL", "SNES Jr."],
    "Nintendo 64": ["Nintendo 64"], "Nintendo GameCube": ["Nintendo GameCube DOL-001", "Nintendo GameCube DOL-101"],
    "Wii": ["Wii RVL-001", "Wii Family Edition RVL-101", "Wii mini RVL-201"], "Wii U": ["Wii U Basic", "Wii U Premium"],
    "Nintendo Switch": ["Nintendo Switch V1", "Nintendo Switch V2", "Nintendo Switch Lite", "Nintendo Switch OLED"],
    "Nintendo Switch 2": ["Nintendo Switch 2"],
    "Game Boy": ["Game Boy", "Game Boy Pocket", "Game Boy Light"],
    "Game Boy Color": ["Game Boy Color"], "Game Boy Advance": ["Game Boy Advance", "Game Boy Advance SP", "Game Boy Micro"],
    "Nintendo DS": ["Nintendo DS", "Nintendo DS Lite", "Nintendo DSi", "Nintendo DSi XL"],
    "Nintendo 3DS": ["Nintendo 3DS", "Nintendo 3DS XL", "Nintendo 2DS", "New Nintendo 3DS", "New Nintendo 3DS XL", "New Nintendo 2DS XL"],
    "PlayStation": ["PlayStation SCPH-100x", "PlayStation PS one"], "PlayStation 2": ["PlayStation 2 Fat", "PlayStation 2 Slim"],
    "PlayStation 3": ["PlayStation 3 Fat", "PlayStation 3 Slim", "PlayStation 3 Super Slim"],
    "PlayStation 4": ["PlayStation 4", "PlayStation 4 Slim", "PlayStation 4 Pro"],
    "PlayStation 5": ["PlayStation 5 Disc", "PlayStation 5 Digital", "PlayStation 5 Slim Disc", "PlayStation 5 Slim Digital", "PlayStation 5 Pro"],
    "PSP": ["PSP-1000", "PSP-2000", "PSP-3000", "PSP Go", "PSP Street"], "PS Vita": ["PS Vita OLED", "PS Vita Slim"],
    "Xbox": ["Xbox Original"], "Xbox 360": ["Xbox 360 Fat", "Xbox 360 S", "Xbox 360 E"],
    "Xbox One": ["Xbox One", "Xbox One S", "Xbox One X"], "Xbox Series X|S": ["Xbox Series S", "Xbox Series X"],
    "Master System": ["Master System", "Master System II"], "Mega Drive / Genesis": ["Mega Drive", "Mega Drive II"],
    "Game Gear": ["Game Gear"], "Saturn": ["Sega Saturn"], "Dreamcast": ["Sega Dreamcast"],
    "Atari 2600": ["Atari 2600", "Atari 2600 Jr."], "Atari 7800": ["Atari 7800"], "Atari Jaguar": ["Atari Jaguar"],
    "Neo Geo": ["Neo Geo AES", "Neo Geo CD", "Neo Geo Pocket", "Neo Geo Pocket Color"], "PC": ["Gaming-PC", "Handheld-PC"],
}


@app.route("/hardware", methods=["GET", "POST"])
@login_required
def hardware():
    if request.method == "POST":
        console_id = request.form.get("console_id", type=int)
        name = request.form.get("custom_name", "").strip() if request.form.get("preset_name") == "__custom__" else request.form.get("preset_name", "").strip()
        name = name or request.form.get("name", "").strip()
        if console_id and name:
            duplicate = HardwareModel.query.filter(HardwareModel.console_id == console_id, db.func.lower(HardwareModel.name) == name.casefold(), db.func.coalesce(HardwareModel.edition, "") == (request.form.get("edition", "").strip())).first()
            if duplicate:
                flash("Dieses Hardware-Modell bzw. diese Edition ist bereits vorhanden.", "warning")
                return redirect(url_for("hardware_detail", model_id=duplicate.id))
            model = HardwareModel(console_id=console_id, name=name, model_number=request.form.get("model_number", "").strip() or None, revision=request.form.get("revision", "").strip() or None, color=request.form.get("color", "").strip() or None, region=request.form.get("region", "").strip() or None, release_year=request.form.get("release_year", type=int), reference_image=archived_or_original_image(request.form.get("reference_image")), notes=request.form.get("notes", "").strip() or None, edition=request.form.get("edition", "").strip() or None, hardware_class=request.form.get("hardware_class") if request.form.get("hardware_class") in HARDWARE_COMPONENT_PROFILES else None)
            db.session.add(model); db.session.commit(); flash("Hardware-Modell angelegt.", "success")
        return redirect(url_for("hardware"))
    query = HardwareModel.query.join(Console)
    manufacturer = request.args.get("manufacturer", "").strip(); console_id = request.args.get("console_id", type=int); q = request.args.get("q", "").strip()
    valuation = request.args.get("valuation", "").strip(); sort = (request.args.get("sort") or "").strip()
    hardware_sorts = {"name", "name_desc", "value_desc", "value_asc", "updated_desc"}
    if sort in hardware_sorts: session["collector_sort_hardware"] = sort
    else: sort = session.get("collector_sort_hardware", "name")
    if sort not in hardware_sorts: sort = "name"
    if manufacturer: query = query.filter(Console.manufacturer == manufacturer)
    if console_id: query = query.filter(HardwareModel.console_id == console_id)
    if q: query = query.filter(db.or_(HardwareModel.name.ilike(f"%{q}%"), HardwareModel.model_number.ilike(f"%{q}%"), HardwareModel.edition.ilike(f"%{q}%")))
    models = query.order_by(Console.manufacturer, Console.name, HardwareModel.name).all()
    now_utc = utc_now()
    catalog_rows = []
    for model in models:
        owned_items = [item for item in model.items if item.status == "owned" and item.user_id == active_collection_user_id()]
        valued_items = [item for item in owned_items if effective_hardware_value(item) is not None]
        total_value = sum((effective_hardware_value(item) or 0) for item in valued_items)
        automatic = [item for item in owned_items if item.auto_value_eur is not None]
        updated_values = [item.auto_value_updated_at for item in automatic if item.auto_value_updated_at]
        updated_at = max(updated_values) if updated_values else None
        stale = bool(automatic and (not updated_at or (now_utc - updated_at).days >= 30))
        manual = any(item.auto_value_eur is None and item.estimated_value is not None for item in owned_items)
        sources = sorted({item.auto_value_source for item in automatic if item.auto_value_source})
        lows = [item.auto_value_low_eur for item in automatic if item.auto_value_low_eur is not None]
        highs = [item.auto_value_high_eur for item in automatic if item.auto_value_high_eur is not None]
        status = "unvalued" if owned_items and not valued_items else ("stale" if stale else ("valued" if automatic else ("manual" if manual else "empty")))
        catalog_rows.append({"model": model, "owned_count": len(owned_items), "valued_count": len(valued_items),
                             "total_value": total_value, "average_value": total_value / len(valued_items) if valued_items else None,
                             "low": sum(lows) if lows else None, "high": sum(highs) if highs else None,
                             "source": ", ".join(sources), "updated_at": updated_at, "status": status})
    if valuation in {"valued", "unvalued", "stale", "manual"}:
        catalog_rows = [row for row in catalog_rows if row["status"] == valuation or (valuation == "valued" and row["valued_count"])]
    if sort == "name_desc": catalog_rows.sort(key=lambda row: row["model"].name.casefold(), reverse=True)
    elif sort == "value_desc": catalog_rows.sort(key=lambda row: (row["total_value"], row["model"].name.casefold()), reverse=True)
    elif sort == "value_asc": catalog_rows.sort(key=lambda row: (row["total_value"] if row["valued_count"] else float("inf"), row["model"].name.casefold()))
    elif sort == "updated_desc": catalog_rows.sort(key=lambda row: (row["updated_at"] or datetime.min), reverse=True)
    consoles = Console.query.order_by(Console.manufacturer, Console.name).all()
    all_items=scoped_hardware_query().all()
    hardware_quality={
        "models_missing_number":HardwareModel.query.filter(db.or_(HardwareModel.model_number.is_(None),HardwareModel.model_number=="")).count(),
        "models_missing_image":HardwareModel.query.filter(db.or_(HardwareModel.reference_image.is_(None),HardwareModel.reference_image=="")).count(),
        "items_unvalued":sum(1 for i in all_items if i.status=="owned" and i.estimated_value is None and i.auto_value_eur is None),
        "items_untested":sum(1 for i in all_items if i.tested_status in (None,"untested")),
    }
    return render_template("hardware.html", models=models, catalog_rows=catalog_rows, consoles=consoles, hardware_presets=HARDWARE_MODEL_PRESETS,
                           manufacturers=sorted({c.manufacturer or "Unbekannt" for c in consoles}), selected_manufacturer=manufacturer, selected_console=console_id, q=q,
                           selected_valuation=valuation, selected_sort=sort, hardware_quality=hardware_quality)


@app.route("/quality/errors")
@login_required
def error_center():
    owner_id = active_collection_user_id()
    failed_logs = RevaluationLog.query.join(CollectionItem, RevaluationLog.collection_item_id == CollectionItem.id).filter(
        RevaluationLog.status == "Fehler", CollectionItem.user_id == owner_id
    ).order_by(RevaluationLog.recorded_at.desc()).limit(100).all()
    hardware_failures = scoped_hardware_query().filter(
        HardwareItem.status == "owned", HardwareItem.auto_value_eur.is_(None),
        HardwareItem.auto_value_updated_at.isnot(None)
    ).order_by(HardwareItem.auto_value_updated_at.desc()).limit(100).all()
    incidents = ApplicationError.query.filter_by(collection_user_id=owner_id).order_by(ApplicationError.created_at.desc()).limit(100).all()
    route_checks = [
        ("Startseite", url_for("collector_home")), ("Bewertungen", url_for("dashboard")),
        ("Reihen & Sammlungen", url_for("collector_collections")), ("Preiszentrum", url_for("price_center")),
        ("Datenpflege", url_for("quality")), ("Datenbank-Status", url_for("data_health")),
    ]
    return render_template("error_center.html", failed_logs=failed_logs, hardware_failures=hardware_failures, incidents=incidents, route_checks=route_checks)


@app.route("/hardware/<int:model_id>", methods=["GET", "POST"])
@login_required
def hardware_detail(model_id):
    model = db.get_or_404(HardwareModel, model_id)
    if request.method == "POST":
        item = HardwareItem(hardware_model_id=model.id, model=model, user_id=active_collection_user_id())
        db.session.add(item)
        apply_hardware_item_form(item)
        db.session.flush()
        item.photo_front = _save_hardware_photo(request.files.get("photo_front"), item.id, "front")
        item.photo_back = _save_hardware_photo(request.files.get("photo_back"), item.id, "back")
        log_activity("hardware_added", "hardware_item", item.id, f"Hardware {model.name} zur Sammlung hinzugefügt.")
        db.session.commit(); flash("Hardware-Exemplar gespeichert.", "success"); return redirect(url_for("hardware_detail", model_id=model.id))
    owned_items = scoped_hardware_query().filter_by(hardware_model_id=model.id).order_by(HardwareItem.id).all()
    set_committed_value(model, "items", owned_items)
    draft=HardwareItem(hardware_model_id=model.id,condition=8,tested_status="tested",user_id=active_collection_user_id())
    defaults={comp["key"]:_legacy_component_default(draft,comp["key"]) for comp in component_profile(model)}
    return render_template("hardware_detail.html", model=model, owned_items=scoped_hardware_query().filter_by(hardware_model_id=model.id).order_by(HardwareItem.id).all(), hardware_class=hardware_class(model), hardware_class_label=HARDWARE_CLASS_LABELS[hardware_class(model)], component_profile=component_profile(model), component_values=defaults)


def derive_hardware_completeness(item):
    model = item.model or db.session.get(HardwareModel, item.hardware_model_id)
    components = hardware_components(item)
    if components:
        present = {key for key,row in components.items() if row.get("availability") == "present"}
        relevant = {key for key,row in components.items() if row.get("availability") != "na"}
        if item.sealed: return "Sealed"
        if model and hardware_class(model) == "pc":
            core = {"case", "mainboard", "cpu", "ram", "storage_primary", "psu", "function"}
            if core <= present and not (relevant - present): return "Komplettsystem"
            if core <= present: return "PC vollständig"
            return "PC unvollständig"
        if "box" in present and relevant and present >= relevant: return "CIB"
        if "box" in present: return "OVP"
        if present & {"controller","controllers","power","cables","stylus","dock"}: return "Konsole + Zubehör"
        return "Loose"
    handheld = any(token in (model.name if model else "").casefold() for token in ("game boy","ds","psp","vita","lite","handheld"))
    if item.sealed: return "Sealed"
    if item.boxed and item.manual_present and item.inserts_present and item.power_supply_present and (item.controller_present or handheld): return "CIB"
    if item.boxed: return "OVP"
    if item.power_supply_present and (item.controller_present or handheld): return "Konsole + Zubehör"
    return "Loose"


def apply_hardware_item_form(item):
    item.status=request.form.get("status", item.status or "owned")
    item.serial_number=request.form.get("serial_number", "").strip() or None
    item.condition=max(1,min(10,request.form.get("condition",type=int) or item.condition or 8))
    item.box_condition=max(1,min(10,request.form.get("box_condition",type=int) or item.box_condition or 8))
    item.controller_condition=max(1,min(10,request.form.get("controller_condition",type=int) or item.controller_condition or 8))
    for field in ("boxed","controller_present","power_supply_present","cables_present","manual_present","inserts_present","original_accessories_present","sealed"):
        setattr(item, field, request.form.get(field) == "1")
    if hardware_class(item.model) == "pc":
        item.controller_present = False
        item.controller_condition = 8
    item.purchase_price=parse_money_input(request.form.get("purchase_price")); item.estimated_value=parse_money_input(request.form.get("estimated_value"))
    item.purchase_date=datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d").date() if request.form.get("purchase_date") else None
    item.storage_location=request.form.get("storage_location", "").strip() or None; item.firmware=request.form.get("firmware", "").strip() or None
    item.tested_status=request.form.get("tested_status", "tested"); item.notes=request.form.get("notes", "").strip() or None
    item.accessories_present=request.form.get("accessories_present", "").strip() or None
    apply_component_form(item)
    item.completeness=derive_hardware_completeness(item)
    calculate_hardware_set(item)


@app.route("/hardware/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def hardware_item_edit(item_id):
    item=scoped_hardware_or_404(item_id)
    if request.method == "POST":
        apply_hardware_item_form(item); db.session.commit(); flash("Hardware-Exemplar aktualisiert.","success")
        return redirect(url_for("hardware_detail",model_id=item.hardware_model_id))
    return render_template("hardware_item_edit.html",item=item, hardware_class=hardware_class(item.model), hardware_class_label=HARDWARE_CLASS_LABELS[hardware_class(item.model)], component_profile=component_profile(item.model), component_values=component_form_values(item))


@app.route("/hardware/items/<int:item_id>/delete", methods=["POST"])
@login_required
def hardware_item_delete(item_id):
    item=scoped_hardware_or_404(item_id); model_id=item.hardware_model_id
    db.session.delete(item); db.session.commit(); flash("Hardware-Exemplar gelöscht. Das Modell bleibt erhalten.","success")
    return redirect(url_for("hardware_detail",model_id=model_id))


@app.route("/hardware/models/<int:model_id>/edit", methods=["GET", "POST"])
@login_required
def hardware_model_edit(model_id):
    model=db.get_or_404(HardwareModel,model_id)
    if request.method == "POST":
        old_reference_image = model.reference_image
        new_local_image = None
        for field in ("name","model_number","revision","color","region","notes","edition","pricecharting_url"):
            setattr(model,field,request.form.get(field,"").strip() or None)
        if request.form.get("hardware_class") in HARDWARE_COMPONENT_PROFILES: model.hardware_class=request.form.get("hardware_class")
        if "pricecharting_url" in request.form:
            model.pricecharting_name = request.form.get("pricecharting_name", "").strip() or model.pricecharting_name
        try:
            upload = request.files.get("reference_image_file")
            if upload and upload.filename:
                new_local_image = _save_hardware_model_image(upload, model.id)
                model.reference_image = new_local_image
            elif request.form.get("remove_reference_image") == "1":
                model.reference_image = None
            else:
                external_image = request.form.get("reference_image_url", "").strip()
                if external_image:
                    parsed = urlsplit(external_image)
                    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                        raise ValueError("Die Referenzbild-URL muss mit http:// oder https:// beginnen.")
                    model.reference_image = archived_or_original_image(external_image)
            model.release_year=request.form.get("release_year",type=int)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            if new_local_image:
                _delete_hardware_model_image(new_local_image)
            flash(str(exc), "error")
            return redirect(url_for("hardware_model_edit", model_id=model.id))
        if old_reference_image != model.reference_image:
            _delete_hardware_model_image(old_reference_image)
        flash("Hardware-Modell aktualisiert.","success")
        return redirect(url_for("hardware_detail",model_id=model.id))
    targets=HardwareModel.query.filter(HardwareModel.id!=model.id).join(Console).order_by(Console.name,HardwareModel.name).all()
    return render_template("hardware_model_edit.html",model=model,targets=targets,hardware_classes=HARDWARE_CLASS_LABELS,selected_hardware_class=hardware_class(model))


@app.route("/hardware/models/<int:model_id>/merge",methods=["POST"])
@login_required
def hardware_model_merge(model_id):
    source=db.get_or_404(HardwareModel,model_id); target=db.get_or_404(HardwareModel,request.form.get("target_id",type=int))
    if source.id==target.id: abort(400)
    discarded_image = None
    if not target.reference_image and source.reference_image:
        target.reference_image = source.reference_image
    elif source.reference_image and source.reference_image != target.reference_image:
        discarded_image = source.reference_image
    HardwareItem.query.filter_by(hardware_model_id=source.id).update({"hardware_model_id":target.id})
    db.session.delete(source); db.session.commit()
    if discarded_image:
        _delete_hardware_model_image(discarded_image)
    flash("Hardware-Modelle zusammengeführt; alle Exemplare wurden übernommen.","success")
    return redirect(url_for("hardware_detail",model_id=target.id))


@app.route("/hardware/models/<int:model_id>/delete",methods=["POST"])
@login_required
def hardware_model_delete(model_id):
    model=db.get_or_404(HardwareModel,model_id)
    if model.items:
        flash("Das Modell besitzt Exemplare und kann erst nach deren Zuordnung oder Löschung entfernt werden.","warning")
        return redirect(url_for("hardware_model_edit",model_id=model.id))
    reference_image = model.reference_image
    db.session.delete(model); db.session.commit()
    _delete_hardware_model_image(reference_image)
    flash("Hardware-Modell gelöscht.","success")
    return redirect(url_for("hardware"))


PRICECHARTING_BASE = "https://www.pricecharting.com"
_PRICECHARTING_RATE_CACHE = {"value": None, "at": 0.0}

class _PriceChartingSearchParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.current=None; self.rows=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag == "tr": self.current={"text":[],"links":[]}; return
        if self.current is not None and tag == "a" and attrs.get("href","").startswith("/game/"):
            self.current["links"].append(attrs["href"])
    def handle_endtag(self, tag):
        if tag == "tr" and self.current is not None:
            self.rows.append(self.current); self.current=None
    def handle_data(self, data):
        if self.current is not None:
            value=re.sub(r"\s+"," ",data or "").strip()
            if value: self.current["text"].append(value)

def _public_html(url, timeout=18):
    req=Request(url,headers={"User-Agent":f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 GameCollector/{APP_VERSION}","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"de-DE,de;q=0.9,en;q=0.7"})
    with urlopen(req,timeout=timeout) as response:
        if response.status != 200: raise RuntimeError(f"HTTP {response.status}")
        return response.read(2_000_000).decode("utf-8","ignore"),response.geturl()

def _usd_to_eur_rate():
    now=time.time()
    if _PRICECHARTING_RATE_CACHE["value"] and now-_PRICECHARTING_RATE_CACHE["at"]<21600: return _PRICECHARTING_RATE_CACHE["value"]
    try:
        req=Request("https://api.frankfurter.dev/v2/providers/ecb/rate/usd/eur",headers={"User-Agent":f"GameCollector/{APP_VERSION}"})
        with urlopen(req,timeout=8) as response: payload=json.loads(response.read().decode("utf-8"))
        rate=float(payload["rate"])
        if .4<rate<1.5:
            _PRICECHARTING_RATE_CACHE.update(value=rate,at=now); return rate
    except Exception as exc: app.logger.warning("Frankfurter USD/EUR lookup failed: %s",exc)
    return None

def _pc_score_candidate(item,row_text):
    target=" ".join(x for x in (item.model.name,item.model.edition,item.model.model_number) if x)
    name_key = _match_key(item.model.name)
    if name_key == "nes frontloader": target = "Nintendo Entertainment System NES Console"
    elif name_key == "nes toploader": target = "Nintendo NES Top Loader Console"
    t=_match_key(target); r=_match_key(row_text)
    words={w for w in t.split() if len(w)>1 and w not in {"console","system"}}
    score=(sum(1 for w in words if w in r.split())/max(1,len(words)))*70+SequenceMatcher(None,t,r).ratio()*30
    if "PAL" in (item.model.region or "").upper() and "pal " in (row_text or "").lower(): score+=18
    if item.model.edition and _match_key(item.model.edition) in r: score+=22
    return score

def pricecharting_find_hardware(item):
    pinned=(item.model.pricecharting_url or "").strip()
    if pinned:
        if pinned.startswith("/"): pinned=urljoin(PRICECHARTING_BASE,pinned)
        if not pinned.startswith("https://www.pricecharting.com/"): return None,"pricecharting_bad_url"
        return pinned,"pinned"
    query=_hardware_search_query(item)
    if not query.strip(): return None,"pricecharting_no_query"
    url=PRICECHARTING_BASE+"/search-products?"+urlencode({"q":query,"type":"prices","region-name":"all"})
    try: body,final_url=_public_html(url)
    except Exception as exc:
        app.logger.warning("PriceCharting search failed: %s",exc); return None,"pricecharting_unreachable"
    if "/game/" in urlsplit(final_url).path: return final_url,"auto"
    parser=_PriceChartingSearchParser()
    try: parser.feed(body)
    except Exception: pass
    candidates=[]; seen=set()
    for row in parser.rows:
        if not row["links"]: continue
        href=row["links"][0]
        if href in seen: continue
        seen.add(href); txt=" ".join(row["text"]); score=_pc_score_candidate(item,txt)
        if any(term in _match_key(txt) for term in ("controller only","replacement","empty box","manual only")): score-=40
        candidates.append((score,href,txt[:220]))
    if not candidates:
        pattern = r'''href=["'](/game/[^"']+)["'][^>]*>(.*?)</a>'''
        for href,label in re.findall(pattern,body,flags=re.I|re.S):
            txt=html_lib.unescape(re.sub(r"<[^>]+>"," ",label)); txt=re.sub(r"\s+"," ",txt).strip()
            if txt: candidates.append((_pc_score_candidate(item,txt),href,txt[:220]))
    if not candidates: return None,"pricecharting_no_results"
    candidates.sort(key=lambda x:x[0],reverse=True); best=candidates[0]
    if best[0]<52: return None,"pricecharting_no_confident_match"
    return urljoin(PRICECHARTING_BASE,best[1]),best[2]

def _pc_price_cell(body,cell_id):
    pattern = r'''<td[^>]+id=["']''' + re.escape(cell_id) + r'''["'][^>]*>(.*?)</td>'''
    m=re.search(pattern,body,flags=re.I|re.S)
    if not m: return None
    txt=html_lib.unescape(re.sub(r"<[^>]+>"," ",m.group(1))); pm=re.search(r"\$\s*([\d,]+(?:\.\d{2})?)",txt)
    return float(pm.group(1).replace(",","")) if pm else None

def pricecharting_hardware_value(item):
    url,match_info=pricecharting_find_hardware(item)
    if not url: return None,match_info
    try: body,final_url=_public_html(url)
    except Exception as exc:
        app.logger.warning("PriceCharting product fetch failed: %s",exc); return None,"pricecharting_unreachable"
    name_pattern = r'''<h1[^>]+id=["']product_name["'][^>]*>(.*?)</h1>'''
    nm=re.search(name_pattern,body,flags=re.I|re.S); product_name=None
    if nm:
        product_name=html_lib.unescape(re.sub(r"<[^>]+>"," ",nm.group(1))); product_name=re.sub(r"\s+"," ",product_name).strip()
    loose,cib,new=_pc_price_cell(body,"used_price"),_pc_price_cell(body,"complete_price"),_pc_price_cell(body,"new_price")
    if loose is None and cib is None and new is None: return None,"pricecharting_no_price"
    completeness=item.completeness or derive_hardware_completeness(item)
    if completeness=="Sealed": raw,kind=(new or cib or loose),"New"
    elif completeness in ("CIB","OVP"): raw,kind=(cib or loose or new),"CIB"
    else: raw,kind=(loose or cib or new),"Loose"
    if raw is None: return None,"pricecharting_condition_missing"
    rate=_usd_to_eur_rate()
    if rate is None: return None,"pricecharting_fx_unavailable"
    condition=max(1,min(10,float(item.set_condition if item.set_condition is not None else (item.condition or 8)))); factor=.65+condition*.035
    if item.tested_status=="defective": factor*=.35
    elif item.tested_status=="untested": factor*=.75
    value=round(raw*rate*factor,2)
    return {"value":value,"low":round(value*.90,2),"high":round(value*1.10,2),"url":final_url,"name":product_name,"price_kind":kind,"raw_usd":raw,"usd_eur":rate,"match":match_info},"ok"


def _hardware_norm(value):
    """Aggressive comparison normalization for hardware listing text."""
    return " ".join(_match_key(value or "").split())


def _hardware_compact(value):
    """Model-number comparison without punctuation/whitespace."""
    return "".join(ch for ch in _hardware_norm(value) if ch.isalnum())


def _hardware_model_aliases(model_number):
    """Known equivalent spellings/model identifiers."""
    compact = _hardware_compact(model_number)

    aliases = {
        # Nintendo
        "dmg01": {"dmg01", "dmg001"},
        "dmg001": {"dmg01", "dmg001"},
        "cgb001": {"cgb001"},
        "agb001": {"agb001"},
        "ags001": {"ags001"},
        "ags101": {"ags101"},
        "mgb001": {"mgb001"},
        "ntr001": {"ntr001"},
        "ctr001": {"ctr001"},
        "spr001": {"spr001"},
        "red001": {"red001"},
        "hdh001": {"hdh001"},
        "hac00101": {"hac00101"},
        "dol001": {"dol001"},
        "dol101": {"dol101"},

        # Sony
        "psp2004": {"psp2004", "psp2000"},
        "psp2000": {"psp2004", "psp2000"},

        # Microsoft
        "1540": {"1540"},
        "1439": {"1439"},
        "1882": {"1882"},
    }

    return aliases.get(compact, {compact} if compact else set())




def _hardware_search_query(item):
    """Build a search query optimized for the concrete hardware family."""
    model = item.model

    name = (model.name or "").strip()
    number = (model.model_number or "").strip()
    color = (model.color or "").strip()

    name_key = _hardware_norm(name)
    number_key = _hardware_compact(number)

    # --------------------------------------------------------
    # Known market/search aliases
    # --------------------------------------------------------

    if "game boy color dandelion" in name_key:
        return "Game Boy Color Yellow CGB-001"

    if "game boy advance pink clear" in name_key:
        return "Game Boy Advance Pink AGB-001"

    # Replacement Zelda shell:
    # Value the underlying AGS-101, NOT an original Zelda edition.
    if (
        "game boy advance sp" in name_key
        and "zelda" in name_key
        and number_key == "ags101"
    ):
        return "Game Boy Advance SP AGS-101"

    if (
        name_key == "game boy pocket"
        and _hardware_norm(color) in {"grun", "gruen", "green"}
    ):
        return "Game Boy Pocket Grün MGB-001"

    if (
        name_key == "nintendo ds"
        and _hardware_norm(color) in {"blau", "blue"}
    ):
        return "Nintendo DS Blau NTR-001"

    if "nintendo switch v2" in name_key:
        return "Nintendo Switch HAC-001-01"

    # German marketplace listings rarely use our internal Frontloader model
    # label on its own.  Include both the full console name and the familiar
    # NES abbreviation so eBay and PriceCharting return actual consoles.
    if name_key == "nes frontloader":
        return "Nintendo Entertainment System NES Konsole Frontloader"

    if name_key == "nes toploader":
        return "Nintendo NES Top Loader Konsole"

    if name_key == "xbox original":
        return "Microsoft Xbox Classic Konsole"

    if name_key == "xbox 360 fat":
        return "Microsoft Xbox 360 Fat Konsole"

    if name_key == "nintendo dsi xl":
        return "Nintendo DSi XL"

    # PSP-2004 is the European member of PSP-2000.
    if "psp" in name_key and number_key == "psp2004":
        return "Sony PSP-2000 PSP2004"

    parts = [name]

    if model.edition:
        parts.append(model.edition)

    # Do not produce e.g.
    # "Nintendo GameCube DOL-001 DOL-001".
    if number and number_key not in _hardware_compact(name):
        if number_key == "hac00101":
            parts.append("HAC-001-01")
        else:
            parts.append(number)

    return " ".join(x for x in parts if x)

def _hardware_listing_flags(row):
    """Classify an eBay result on independent semantic dimensions."""
    title = _hardware_norm(row.get("name") or "")
    category = _hardware_norm(row.get("category") or "")
    description = _hardware_norm(" ".join(
        x for x in (
            row.get("short_description"),
            row.get("condition_description"),
        ) if x
    ))
    condition = _hardware_norm(row.get("condition") or "")

    text = " ".join((title, category, description, condition))

    defective_terms = (
        "defekt", "defective", "for parts", "parts only",
        "ersatzteil", "bastler", "rrod", "e74",
        "displayfehler", "laufwerk klemmt", "not working",
    )

    untested_terms = (
        "ungetestet",
        "untested",
        "nicht getestet",
        "not tested",
        "funktion unbekannt",
        "function unknown",
    )

    part_terms = (
        "mainboard", "motherboard", "hdmi port", "hdmi buchse",
        "hdmi board", "power switch board", "speaker",
        "lautsprecher", "schrauben set", "screw set",
        "battery cover", "batteriefachdeckel", "display lens",
        "displayglas", "ersatzgehause", "ersatzgehäuse",
        "replacement shell",
    )

    accessory_terms = (
        "netzteil", "power supply", "charger", "ladegerat",
        "ladegerät", "akku", "battery", "controller", "gamepad",
        "memory card", "speicher erweiterung", "festplatte",
        "hard drive", "hdd", "kabel", "cable", "stand",
        "halterung",
    )

    modified_terms = (
        "ips", "amoled", "oled mod", "usb c", "usb-c",
        "custom shell", "new shell", "replacement shell",
        "reshell", "gemoddet", "modded", "gehackt",
        "region free", "rgh", "cerbios", "evox",
        "freestyle", "aurora", "modxo", "smartxx",
    )

    refurbished_terms = (
        "refurbished", "aufgefrischt", "generaluberholt",
        "generalüberholt", "serviced",
    )

    # Parts can mention the target console/model and must be removed before
    # any model-number matching.
    is_part = any(term in text for term in part_terms)

    # ACCESSORY is deliberately title/category driven. A legitimate listing
    # such as "Konsole + Controller + Kabel" must remain a console.
    console_words = (
        "konsole", "console", "handheld", "spielkonsole",
        "handheld system", "handheld-system"
    )
    has_console_word = any(term in title for term in console_words)

    accessory_title = any(term in title for term in accessory_terms)
    accessory_category = any(term in category for term in (
        "controller", "controllers", "accessories", "zubehor",
        "zubehör", "cables", "kabel", "batteries", "akkus",
        "power supplies", "netzteil",
    ))

    is_accessory = (
        not is_part
        and not has_console_word
        and (accessory_title or accessory_category)
    )

    return {
        "title": title,
        "category": category,
        "description": description,
        "condition": condition,
        "text": text,
        "defective": any(term in text for term in defective_terms),
        "untested": any(term in text for term in untested_terms),
        "part": is_part,
        "accessory": is_accessory,
        "modified": any(term in text for term in modified_terms),
        "refurbished": any(term in text for term in refurbished_terms),
    }




def _hardware_family_conflict(item, flags):
    """Reject known different generations/revisions of the same family."""
    text = flags["text"]
    compact = _hardware_compact(text)

    name = _hardware_norm(item.model.name)
    number = _hardware_compact(item.model.model_number or "")

    # NES family: keep the original 8-bit console separate from SNES,
    # Classic Mini, Famicom and the opposite case revision.
    if name in {"nes frontloader", "nes toploader"}:
        if any(x in text for x in (
            "super nintendo", "snes", "nes classic", "classic mini",
            "nes mini", "nintendo mini", "famicom",
        )):
            return True
        if name == "nes frontloader" and any(x in text for x in ("toploader", "top loader", "nes 101")):
            return True
        if name == "nes toploader" and any(x in text for x in ("frontloader", "front loader", "nes 001")):
            return True

    # Game Boy Advance SP
    if number == "ags101" and "ags001" in compact:
        return True
    if number == "ags001" and "ags101" in compact:
        return True

    # GameCube
    if number == "dol001" and "dol101" in compact:
        return True
    if number == "dol101" and "dol001" in compact:
        return True

    # Original Nintendo DS
    if name == "nintendo ds":
        if any(x in text for x in (
            "ds lite", "dsi", "3ds", "2ds", "new 3ds"
        )):
            return True

    # Original Nintendo 3DS
    if name == "nintendo 3ds":
        if any(x in text for x in (
            "3ds xl", "new 3ds", "2ds", "dsi"
        )):
            return True

    # Original Nintendo 3DS XL / SPR-001
    if name == "nintendo 3ds xl":
        if any(x in text for x in (
            "new nintendo 3ds xl",
            "new 3ds xl",
            "newnintendo 3ds xl",
            "3ds ll",
        )):
            return True

        if "red001" in compact:
            return True

    # New Nintendo 3DS XL / RED-001.
    # This is the reverse protection missing above.
    if "new 3ds xl" in name or "new nintendo 3ds xl" in name:
        if "spr001" in compact:
            return True

        old_xl = (
            "3ds xl" in text
            and "new 3ds xl" not in text
            and "new nintendo 3ds xl" not in text
        )

        if old_xl:
            return True

    # Switch family
    if "nintendo switch lite" in name:
        if any(x in compact for x in ("hac001", "heg001")):
            return True

    if "nintendo switch v2" in name:
        if "hdh001" in compact or "heg001" in compact:
            return True

        if (
            "hac001" in compact
            and "hac00101" not in compact
            and any(x in text for x in (
                "1 gen", "1 generation", "v1", "unpatched", "xaj"
            ))
        ):
            return True

    # Original Xbox
    if name == "xbox original":
        if any(x in text for x in (
            "xbox 360", "xbox one", "series x", "series s"
        )):
            return True

    # Xbox One 1540
    if name == "xbox one":
        if any(x in text for x in (
            "xbox one s", "xbox one x", "series s", "series x"
        )):
            return True

    # Xbox 360 S
    if name == "xbox 360 s":
        if any(x in text for x in (
            "xbox 360 e", "xbox one", "series x", "series s"
        )):
            return True

    # Xbox 360 Fat
    if name == "xbox 360 fat":
        if any(x in text for x in (
            "xbox 360 slim", "xbox 360 s ", "xbox 360 e",
            "xbox one", "series x", "series s"
        )):
            return True

    return False


def _hardware_edition_conflict(item, flags):
    """Handle genuine editions separately from cosmetic modifications."""
    wanted = _hardware_norm(item.model.edition or "")
    text = flags["text"]

    name = _hardware_norm(item.model.name)
    number = _hardware_compact(item.model.model_number or "")

    # Our Zelda SP is an AGS-101 with a replacement Zelda shell.
    # It must use the ordinary AGS-101 market, not genuine Zelda
    # limited-edition listings.
    replacement_zelda_shell = (
        "game boy advance sp" in name
        and "zelda" in (name + " " + wanted)
        and number == "ags101"
    )

    if replacement_zelda_shell:
        # Genuine Zelda-edition listings are not the correct market
        # comparison for the replacement-shell unit.
        if "zelda" in text:
            return True

        return False

    if not wanted:
        return False

    # Modified seller hardware must not establish the market price
    # of a genuine factory edition.
    if flags["modified"]:
        return True

    wanted_words = {
        w for w in wanted.split()
        if len(w) >= 3 and w not in {"edition", "limited"}
    }

    return (
        bool(wanted_words)
        and not all(w in text for w in wanted_words)
    )


def _hardware_name_match(item, flags):
    """Family-name validation with known marketplace aliases."""
    title = flags["title"]
    title_words = set(title.split())

    name = _hardware_norm(item.model.name)
    number = _hardware_compact(item.model.model_number or "")

    # --------------------------------------------------------
    # Explicit family aliases
    # --------------------------------------------------------

    if name in {"nes frontloader", "nes toploader"}:
        return (
            "nes" in title_words
            or "nintendo entertainment system" in title
        )

    # Original Xbox is commonly sold as Xbox Classic.
    if name == "xbox original":
        if any(x in title for x in (
            "xbox classic",
            "original xbox",
            "microsoft xbox",
        )):
            return True

        # Bare "Xbox Konsole" is allowed only after family-conflict
        # filtering has already removed 360/One/Series.
        return "xbox" in title_words

    # Pink Clear is a collection description; marketplace titles
    # commonly just say Pink.
    if "game boy advance pink clear" in name:
        return (
            "game" in title_words
            and "boy" in title_words
            and "advance" in title_words
        )

    # Replacement Zelda shell -> compare underlying AGS-101.
    if (
        "game boy advance sp" in name
        and "zelda" in name
        and number == "ags101"
    ):
        return (
            "game" in title_words
            and "boy" in title_words
            and "advance" in title_words
            and "sp" in title_words
        )

    wanted = {
        w for w in name.split()
        if len(w) > 1
    }

    if not wanted:
        return True

    # PSP-2000 may be expressed as PSP-2004.
    if "psp" in wanted and "psp" in title_words:
        wanted.discard("2000")

    matched = sum(
        1 for w in wanted
        if w in title_words
    )

    required = (
        1
        if len(wanted) <= 1
        else max(2, len(wanted) - 1)
    )

    return matched >= required

def _hardware_model_match(item, flags):
    """Return exact/equivalent model-number evidence when available."""
    number = item.model.model_number
    if not number:
        return False

    compact = _hardware_compact(flags["text"])
    aliases = _hardware_model_aliases(number)

    return any(alias and alias in compact for alias in aliases)




def _hardware_listing_completeness(flags):
    """Classify seller completeness independently from owned completeness."""
    import re

    text = flags["text"]

    has_box = any(x in text for x in (
        "ovp",
        "originalverpackung",
        "original box",
        "boxed",
        "box and manuals",
        "komplett in ovp",
    ))

    # IMPORTANT:
    # Never classify the word "Game" itself as a bundle.
    # Otherwise "Game Boy" becomes a games bundle.
    bundle_phrases = (
        "mit spiel",
        "mit spielen",
        "inkl spiel",
        "inklusive spiel",
        "inkl spiele",
        "inklusive spiele",
        "with game",
        "with games",
        "games bundle",
        "game bundle",
        "spiele bundle",
        "spiel bundle",
        "plus spiele",
        "plus games",
    )

    has_games = any(
        phrase in text
        for phrase in bundle_phrases
    )

    # Examples:
    # "+ 3 Spiele", "mit 5 Games", "inkl 2 Spiele"
    if not has_games:
        has_games = bool(re.search(
            r"(?:\+|mit|inkl|inklusive|with)\s*"
            r"\d+\s*(?:spiel|spiele|game|games)\b",
            text,
        ))

    has_controller = any(x in text for x in (
        "controller",
        "gamepad",
    ))

    has_cable = any(x in text for x in (
        "kabel",
        "cable",
        "netzteil",
        "power supply",
        "ladegerat",
        "ladegerät",
        "charger",
    ))

    if has_box:
        return "BOXED"

    if has_games:
        return "BUNDLE"

    if has_controller or has_cable:
        return "ACCESSORIES"

    return "CONSOLE"

def _hardware_item_factor(item):
    """Apply only properties of the concrete owned hardware item."""
    set_condition = (
        item.set_condition
        if item.set_condition is not None
        else (item.condition or 8)
    )

    completeness_factor = {
        "Loose": .82,
        "Konsole + Zubehör": 1.00,
        "OVP": 1.18,
        "CIB": 1.28,
        "Sealed": 1.80,
    }.get(item.completeness, 1.00)

    condition_factor = max(
        .45,
        min(1.12, .55 + set_condition * .057)
    )

    factor = completeness_factor * condition_factor

    if item.tested_status == "defective":
        factor *= .35
    elif item.tested_status == "untested":
        factor *= .72
    elif item.tested_status == "partial":
        factor *= .84

    return factor


def _hardware_market_key(item):
    """Stable identity for hardware sharing the same market sample."""
    model = item.model

    name = _hardware_norm(model.name)
    number = _hardware_compact(model.model_number or "")
    edition = _hardware_norm(model.edition or "")

    # Cosmetic replacement shells must eventually be represented separately
    # from genuine factory editions. Until then, known reshell items use the
    # normal underlying hardware market.
    if (
        "game boy advance sp" in name
        and "zelda" in edition
        and number == "ags101"
    ):
        edition = ""

    return "|".join((name, number, edition))


def _hardware_ebay_search_with_retry(query, limit=60, attempts=2):
    """Retry only technical eBay failures, never semantic no-result cases."""
    last_rows = []
    last_status = "ebay_unreachable"

    retryable = {
        "ebay_unreachable",
        "ebay_timeout",
        "ebay_api_error",
    }

    for attempt in range(max(1, attempts)):
        rows, status = ebay_search_items(query, limit=limit)

        last_rows = rows
        last_status = status

        if status == "ok":
            return rows, status

        if status not in retryable:
            return rows, status

        if attempt + 1 < attempts:
            import time
            time.sleep(.8)

    return last_rows, last_status


def _hardware_ebay_value(
    item,
    reference_value=None,
    market_cache=None,
):
    """Hardware valuation v2.2: shared market first, owned item second."""

    query = _hardware_search_query(item)
    market_key = _hardware_market_key(item)

    # A caller may share this dictionary across several HardwareItems.
    # The cached object contains ONLY market information, never an
    # item-specific condition/completeness factor.
    cached = (
        market_cache.get(market_key)
        if market_cache is not None
        else None
    )

    if cached is None:
        rows, status = _hardware_ebay_search_with_retry(
            query,
            limit=60,
            attempts=2,
        )

        if status != "ok":
            return None, status

        rows = ebay_enrich_candidates(rows, limit=20)

        candidates = []

        for row in rows:
            if (
                row.get("currency") != "EUR"
                or row.get("price") is None
            ):
                continue

            flags = _hardware_listing_flags(row)

            if flags["defective"]:
                continue
            if flags["untested"]:
                continue
            if flags["part"]:
                continue
            if flags["accessory"]:
                continue
            if flags["modified"]:
                continue
            if _hardware_family_conflict(item, flags):
                continue
            if _hardware_edition_conflict(item, flags):
                continue
            if not _hardware_name_match(item, flags):
                continue

            value = (
                float(row["price"])
                + float(row.get("shipping") or 0)
            )

            if value <= 0:
                continue

            if reference_value:
                if value < reference_value * .45:
                    continue
                if value > reference_value * 2.20:
                    continue

            candidates.append({
                "value": value,
                "model_match": _hardware_model_match(item, flags),
                "listing_completeness":
                    _hardware_listing_completeness(flags),
                "refurbished": flags["refurbished"],
            })

        if len(candidates) < 3:
            cached = {
                "ok": False,
                "status": "too_few_results",
                "query": query,
            }

            if market_cache is not None:
                market_cache[market_key] = cached

            return None, "too_few_results"

        # Prefer exact/equivalent model-number samples if enough exist.
        model_candidates = [
            x for x in candidates
            if x["model_match"]
        ]

        if len(model_candidates) >= 3:
            candidates = model_candidates

        # Prefer ordinary used hardware over refurbished listings.
        normal = [
            x for x in candidates
            if not x["refurbished"]
        ]

        if len(normal) >= 3:
            candidates = normal

        # Normalize SELLER listing completeness to a common market base.
        normalization = {
            "CONSOLE": 1.00,
            "ACCESSORIES": .90,
            "BUNDLE": .78,
            "BOXED": .82,
        }

        normalized = [
            x["value"]
            * normalization[x["listing_completeness"]]
            for x in candidates
        ]

        if len(normalized) < 3:
            return None, "too_few_results"

        median = statistics.median(normalized)

        normalized = [
            value
            for value in normalized
            if median * .55 <= value <= median * 1.80
        ]

        if len(normalized) < 3:
            return None, "too_few_results"

        median = statistics.median(normalized)

        if reference_value:
            ratio = median / reference_value

            if ratio < .55 or ratio > 1.80:
                cached = {
                    "ok": False,
                    "status": "implausible_vs_pricecharting",
                    "query": query,
                }

                if market_cache is not None:
                    market_cache[market_key] = cached

                return None, "implausible_vs_pricecharting"

        cached = {
            "ok": True,
            "status": "ok",
            "query": query,
            "market_base": median,
            "market_low": min(normalized),
            "market_high": max(normalized),
            "count": len(normalized),
        }

        if market_cache is not None:
            market_cache[market_key] = cached

    if not cached.get("ok"):
        return None, cached.get("status", "too_few_results")

    factor = _hardware_item_factor(item)

    return {
        "value": round(cached["market_base"] * factor, 2),
        "low": round(cached["market_low"] * factor, 2),
        "high": round(cached["market_high"] * factor, 2),
        "query": cached["query"],
        "count": cached["count"],
        "market_base": round(cached["market_base"], 2),
        "factor": round(factor, 4),
        "market_key": market_key,
    }, "ok"


def hardware_auto_value(item, market_cache=None):
    calculate_hardware_set(item)
    now = utc_now()

    # If an exact PriceCharting product has been pinned, evaluate it first as
    # a plausibility reference. It does NOT automatically become the primary
    # source; eBay still wins when its sample is credible.
    pc = None
    pc_status = "not_checked"
    reference_value = None

    if (item.model.pricecharting_url or "").strip():
        pc, pc_status = pricecharting_hardware_value(item)
        if pc:
            reference_value = pc["value"]

    ebay, ebay_status = _hardware_ebay_value(
        item,
        reference_value=reference_value,
        market_cache=market_cache,
    )

    if ebay:
        item.auto_value_eur = ebay["value"]
        item.auto_value_low_eur = ebay["low"]
        item.auto_value_high_eur = ebay["high"]
        item.auto_value_source = "eBay Browse API"
        item.auto_value_updated_at = now
        item.auto_value_url = None

        item.valuation_breakdown = json.dumps({
            "source": "eBay Browse API",
            "sample_count": ebay["count"],
            "completeness": item.completeness,
            "set_condition": item.set_condition,
            "pricecharting_reference_eur": reference_value,
            "result_eur": ebay["value"],
        }, ensure_ascii=False)

        anchor_text = (
            f" · gegen PriceCharting-Referenz "
            f"{reference_value:.2f} € plausibilisiert"
            if reference_value is not None else ""
        )

        item.auto_value_message = (
            f"Primärwert aus {ebay['count']} plausiblen aktuellen "
            f"eBay-Angeboten via offizieller Browse API"
            f"{anchor_text} · {item.completeness} · "
            f"Setzustand {item.set_condition:.1f}/10"
        )

        db.session.add(HardwarePriceHistory(
            hardware_item_id=item.id,
            value_eur=ebay["value"],
            low_eur=ebay["low"],
            high_eur=ebay["high"],
            source=item.auto_value_source,
        ))
        return True, "ok"

    # If PriceCharting was not already checked as an exact pinned reference,
    # try automatic PriceCharting matching now as the fallback.
    if pc is None:
        pc, pc_status = pricecharting_hardware_value(item)

    if pc:
        item.auto_value_eur = pc["value"]
        item.auto_value_low_eur = pc["low"]
        item.auto_value_high_eur = pc["high"]
        item.auto_value_source = (
            "PriceCharting PAL"
            if "PAL" in (item.model.region or "").upper()
            else "PriceCharting"
        )
        item.auto_value_updated_at = now
        item.auto_value_url = pc["url"]

        item.model.pricecharting_name = (
            pc.get("name") or item.model.pricecharting_name
        )

        item.valuation_breakdown = json.dumps({
            "source_base_eur": round(
                pc["raw_usd"] * pc["usd_eur"], 2
            ),
            "completeness": item.completeness,
            "set_condition": item.set_condition,
            "result_eur": pc["value"],
            "ebay_status": ebay_status,
        }, ensure_ascii=False)

        item.auto_value_message = (
            f"eBay verworfen: {ebay_status}. "
            f"PriceCharting-Fallback: {pc['price_kind']} "
            f"${pc['raw_usd']:.2f} · USD/EUR "
            f"{pc['usd_eur']:.4f} · Setzustand "
            f"{item.set_condition:.1f}/10 · "
            f"{item.model.pricecharting_name or 'PriceCharting-Treffer'}"
        )

        db.session.add(HardwarePriceHistory(
            hardware_item_id=item.id,
            value_eur=pc["value"],
            low_eur=pc["low"],
            high_eur=pc["high"],
            source=item.auto_value_source,
        ))
        return True, "ok_fallback"

    item.auto_value_updated_at = now
    item.auto_value_message = (
        f"eBay: {ebay_status}; PriceCharting: {pc_status}. "
        f"Kein sicherer Konsolenpreis gefunden."
    )
    return False, ebay_status


@app.route("/hardware/items/<int:item_id>/value",methods=["POST"])
@login_required
def hardware_item_value(item_id):
    item=scoped_hardware_or_404(item_id); ok,status=hardware_auto_value(item)
    if ok: db.session.commit(); flash(f"Hardwarewert aktualisiert: {item.auto_value_eur:.2f} €.","success")
    else: db.session.commit(); flash("Kein ausreichend sicherer Hardware-Preisvergleich gefunden.","warning")
    return redirect_back("hardware_detail",model_id=item.hardware_model_id)


@app.route("/hardware/revalue", methods=["POST"])
@login_required
def hardware_revalue_all():
    items=scoped_hardware_query().filter_by(status="owned").filter(HardwareItem.auto_value_eur.is_(None)).order_by(HardwareItem.id).all(); valued=0; failed=0
    market_cache = {}
    for item in items:
        try:
            ok,_=hardware_auto_value(item, market_cache=market_cache); valued += 1 if ok else 0; failed += 0 if ok else 1; db.session.commit()
        except Exception as exc:
            db.session.rollback(); failed+=1; app.logger.exception("Hardware revaluation failed for item %s: %s",item.id,exc)
    flash(f"Konsolenbewertung abgeschlossen: {valued} aktualisiert, {failed} ohne sicheren Preis, bereits bewertete übersprungen.","success" if valued else "warning")
    return redirect(request.form.get("return_to") or url_for("hardware"))



def _accessory_kind(item):
    """Return a stable accessory product family."""
    text = _hardware_norm(" ".join(x for x in (
        item.name,
        item.manufacturer,
        item.model_number,
        item.console.name if item.console else None,
    ) if x))

    if ("game boy player" in text or "gameboy player" in text) and (
        getattr(item, "component_kind", None) == "software_disc"
        or getattr(item, "category", None) == "software_disc"
        or "startup disc" in text
        or "start up disc" in text
    ):
        return "GAME_BOY_PLAYER_DISC"

    if "game boy player" in text or "gameboy player" in text:
        return "GAME_BOY_PLAYER"

    if "kinect" in text:
        return "KINECT"

    if any(x in text for x in ("controller", "gamepad", "joy con", "joycon")):
        return "CONTROLLER"

    if any(x in text for x in ("kamera", "camera", "eye camera")):
        return "CAMERA"

    if any(x in text for x in ("portal", "portal of power")):
        return "PORTAL"

    if any(x in text for x in (
        "netzteil", "power supply", "ac adapter", "adapter"
    )):
        return "POWER"

    if any(x in text for x in (
        "memory card", "speicherkarte", "memory unit"
    )):
        return "MEMORY"

    if any(x in text for x in ("kabel", "cable")):
        return "CABLE"

    return "GENERIC"


def _accessory_search_query(item):
    """Build a marketplace query for the actual accessory product."""
    kind = _accessory_kind(item)

    if kind == "GAME_BOY_PLAYER_DISC":
        return "Nintendo GameCube Game Boy Player Startup Disc DOL-017"

    if kind == "GAME_BOY_PLAYER":
        has_disc = bool(getattr(item, "media_present", False)) or any(
            getattr(child, "component_kind", "") == "software_disc"
            for child in getattr(item, "components", [])
        )
        return "Nintendo GameCube Game Boy Player mit Startup Disc" if has_disc else "Nintendo GameCube Game Boy Player Adapter ohne Disc"

    if kind == "KINECT":
        console = _hardware_norm(
            item.console.name if item.console else ""
        )

        if "xbox 360" in console:
            return "Microsoft Xbox 360 Kinect Sensor"

        if "xbox one" in console:
            return "Microsoft Xbox One Kinect Sensor"

    parts = []

    if item.manufacturer:
        parts.append(item.manufacturer)

    if item.console:
        parts.append(item.console.name)

    if item.name:
        parts.append(item.name)

    number = (item.model_number or "").strip()

    # Do not duplicate identifiers already contained in the text.
    if number:
        existing = _hardware_compact(" ".join(parts))
        if _hardware_compact(number) not in existing:
            parts.append(number)

    return " ".join(parts)


def _accessory_market_key(item):
    """Market identity independent from condition/boxed state."""
    kind = _accessory_kind(item)

    console = _hardware_norm(
        item.console.name if item.console else ""
    )

    if kind == "GAME_BOY_PLAYER_DISC":
        return "game-boy-player|dol017|startup-disc-only"

    if kind == "GAME_BOY_PLAYER":
        has_disc = bool(getattr(item, "media_present", False)) or any(
            getattr(child, "component_kind", "") == "software_disc"
            for child in getattr(item, "components", [])
        )
        return f"game-boy-player|adapter|disc:{int(has_disc)}"

    if kind == "KINECT":
        return f"kinect|{console}"

    return "|".join((
        kind.lower(),
        console,
        _hardware_norm(item.manufacturer or ""),
        _hardware_norm(item.name or ""),
        _hardware_compact(item.model_number or ""),
    ))


def _accessory_item_factor(item):
    """Apply only properties of the owned accessory."""
    condition = max(
        1,
        min(10, item.condition or 8),
    )

    # 8/10 is approximately neutral.
    condition_factor = max(
        .55,
        min(1.08, .62 + condition * .046),
    )

    boxed_factor = 1.15 if item.boxed else 1.00

    return condition_factor * boxed_factor


def _accessory_listing_flags(row):
    """Semantic flags for an eBay accessory listing."""
    title = _hardware_norm(row.get("name") or "")
    category = _hardware_norm(row.get("category") or "")

    description = _hardware_norm(" ".join(
        x for x in (
            row.get("short_description"),
            row.get("condition_description"),
        ) if x
    ))

    condition = _hardware_norm(row.get("condition") or "")

    text = " ".join((
        title,
        category,
        description,
        condition,
    ))

    defective_terms = (
        "defekt",
        "defective",
        "not working",
        "for parts",
        "parts only",
        "bastler",
        "kaputt",
    )

    untested_terms = (
        "ungetestet",
        "untested",
        "nicht getestet",
        "not tested",
        "funktion unbekannt",
        "function unknown",
    )

    part_terms = (
        "ersatzteil",
        "replacement part",
        "replacement shell",
        "ersatzgehause",
        "ersatzgehäuse",
        "analog stick",
        "thumbstick",
        "joystick replacement",
        "repair kit",
        "reparatur",
        "mainboard",
        "motherboard",
        "platine",
        "pcb",
    )

    refurbished_terms = (
        "refurbished",
        "generaluberholt",
        "generalüberholt",
        "aufgefrischt",
        "serviced",
    )

    return {
        "title": title,
        "category": category,
        "description": description,
        "condition": condition,
        "text": text,
        "defective": any(x in text for x in defective_terms),
        "untested": any(x in text for x in untested_terms),
        "part": any(x in text for x in part_terms),
        "refurbished": any(x in text for x in refurbished_terms),
    }


def _accessory_product_match(item, flags):
    """Strict product-family validation."""
    import re

    kind = _accessory_kind(item)
    title = flags["title"]
    text = flags["text"]
    compact = _hardware_compact(text)

    if kind == "GAME_BOY_PLAYER_DISC":
        return (
            ("game boy player" in text or "gameboy player" in text)
            and any(x in text for x in ("startup disc", "start up disc", "startup disk", "start up disk", "dol-017", "dol017"))
            and not any(x in title for x in ("adapter only", "player only", "ohne disc", "ohne disk"))
        )

    if kind == "GAME_BOY_PLAYER":
        # Must actually be a Game Boy Player.
        if not (
            ("game boy player" in text or "gameboy player" in text)
            and "gamecube" in text
        ):
            return False

        has_owned_disc = bool(getattr(item, "media_present", False)) or any(
            getattr(child, "component_kind", "") == "software_disc"
            for child in getattr(item, "components", [])
        )

        # Reject disc-only listings.
        disc_only = any(x in title for x in (
            "disc only",
            "disk only",
            "cd only",
            "nur disc",
            "nur disk",
            "nur cd",
            "startup disc only",
            "start up disc only",
        ))

        if disc_only:
            return False

        # Compare complete sets only with complete sets; the adapter alone
        # deliberately uses listings without the required startup disc.
        has_disc = any(x in text for x in (
            "startup disc",
            "start up disc",
            "startup disk",
            "start up disk",
            "startdisc",
            "start disc",
            "startdisk",
            "start disk",
            "boot disc",
            "boot disk",
            "software disc",
            "software disk",
            "mit cd",
            "inkl cd",
            "inkl. cd",
            "mit disc",
            "inkl disc",
            "inkl. disc",
        ))

        if has_owned_disc and not has_disc:
            return False
        if not has_owned_disc and has_disc:
            return False

        return True

    if kind == "KINECT":
        # Must actually contain a Kinect sensor/camera.
        if "kinect" not in text:
            return False

        if not any(x in text for x in (
            "sensor",
            "kamera",
            "camera",
            "bewegungssensor",
            "sensorleiste",
        )):
            return False

        console = _hardware_norm(
            item.console.name if item.console else ""
        )

        if "xbox 360" in console:
            # Hard conflict: Xbox One Kinect.
            if any(x in text for x in (
                "xbox one",
                "xboxone",
                "kinect 2.0",
                "kinect v2",
            )):
                return False

            # Require 360 evidence.
            if (
                "xbox 360" not in text
                and "xbox360" not in compact
                and "modell 1414" not in text
                and "model 1414" not in text
            ):
                return False

        # Reject complete console bundles.
        if any(x in title for x in (
            "heimkonsole",
            "xbox 360 konsole",
            "xbox360 konsole",
            "console bundle",
            "konsole mit kinect",
        )):
            return False

        # Reject Kinect accessories rather than the sensor.
        accessory_only = any(x in title for x in (
            "netzteil fur",
            "netzteil für",
            "power supply for",
            "adapter fur",
            "adapter für",
            "adapter for",
            "halterung",
            "wall mount",
            "wand halterung",
            "mounting clip",
            "tv clip",
            "extension cable",
            "verlangerungskabel",
            "verlängerungskabel",
        ))

        if accessory_only:
            return False

        # Reject game-only listings that merely say Kinect is required.
        if any(x in text for x in (
            "kinect sensor erforderlich",
            "kinect required",
            "requires kinect",
        )):
            return False

        return True

    # Generic matcher.
    wanted = {
        w for w in _hardware_norm(item.name).split()
        if len(w) > 2
    }

    if not wanted:
        return True

    title_words = set(title.split())
    matched = sum(1 for w in wanted if w in title_words)

    required = max(
        1,
        min(len(wanted), (len(wanted) + 1) // 2),
    )

    return matched >= required


def _accessory_listing_completeness(item, flags):
    """Normalize extras in seller listings separately from owned state."""
    import re

    text = flags["text"]
    kind = _accessory_kind(item)

    # Game Boy Player + startup disc is already our target product.
    # Do not treat its required disc as an ordinary game bundle.
    if kind in {"GAME_BOY_PLAYER", "GAME_BOY_PLAYER_DISC"}:
        if any(x in text for x in (
            "ovp",
            "originalverpackung",
            "original box",
            "boxed",
        )):
            return "BOXED"

        return "TARGET"

    has_box = any(x in text for x in (
        "ovp",
        "originalverpackung",
        "original box",
        "boxed",
        "mit karton",
    ))

    game_bundle = any(x in text for x in (
        "inkl spiel",
        "inkl. spiel",
        "inklusive spiel",
        "inkl spiele",
        "inkl. spiele",
        "inklusive spiele",
        "mit spiel",
        "mit spielen",
        "with game",
        "with games",
        "games bundle",
    ))

    if not game_bundle:
        game_bundle = bool(re.search(
            r"(?:\+|mit|inkl|inklusive|with)\s*"
            r"\d+\s*(?:spiel|spiele|game|games)\b",
            text,
        ))

    if has_box:
        return "BOXED"

    if game_bundle:
        return "BUNDLE"

    return "TARGET"


def _accessory_ebay_value(item, market_cache=None):
    """Accessory valuation v2: clean market first, owned item second."""
    query = _accessory_search_query(item)
    market_key = _accessory_market_key(item)

    cached = (
        market_cache.get(market_key)
        if market_cache is not None
        else None
    )

    if cached is None:
        rows, status = _hardware_ebay_search_with_retry(
            query,
            limit=60,
            attempts=2,
        )

        if status != "ok":
            return None, status

        rows = ebay_enrich_candidates(rows, limit=60)

        candidates = []

        for row in rows:
            if (
                row.get("currency") != "EUR"
                or row.get("price") is None
            ):
                continue

            flags = _accessory_listing_flags(row)

            if flags["defective"]:
                continue

            if flags["untested"]:
                continue

            if flags["part"]:
                continue

            if not _accessory_product_match(item, flags):
                continue

            try:
                value = (
                    float(row["price"])
                    + float(row.get("shipping") or 0)
                )
            except (TypeError, ValueError):
                continue

            if value <= 0:
                continue

            candidates.append({
                "value": value,
                "listing_completeness":
                    _accessory_listing_completeness(item, flags),
                "refurbished": flags["refurbished"],
                "url":
                    row.get("url")
                    or row.get("itemWebUrl")
                    or "",
            })

        if len(candidates) < 3:
            cached = {
                "ok": False,
                "status": "too_few_results",
                "query": query,
            }

            if market_cache is not None:
                market_cache[market_key] = cached

            return None, "too_few_results"

        # Prefer normal used products.
        normal = [
            x for x in candidates
            if not x["refurbished"]
        ]

        if len(normal) >= 3:
            candidates = normal

        # Convert listings to a common target-product market base.
        normalization = {
            "TARGET": 1.00,
            "BUNDLE": .85,
            "BOXED": .90,
        }

        normalized = [
            {
                **x,
                "normalized":
                    x["value"]
                    * normalization[x["listing_completeness"]],
            }
            for x in candidates
        ]

        values = [x["normalized"] for x in normalized]

        median = statistics.median(values)

        # Tighter than old .4x - 2.5x filter.
        normalized = [
            x for x in normalized
            if median * .55 <= x["normalized"] <= median * 1.80
        ]

        if len(normalized) < 3:
            return None, "too_few_results"

        values = [x["normalized"] for x in normalized]

        market_base = statistics.median(values)

        cached = {
            "ok": True,
            "status": "ok",
            "query": query,
            "market_base": round(market_base, 2),
            "market_low": round(min(values), 2),
            "market_high": round(max(values), 2),
            "count": len(values),
            "url": normalized[0]["url"] if normalized else "",
        }

        if market_cache is not None:
            market_cache[market_key] = cached

    if not cached.get("ok"):
        return None, cached.get("status", "too_few_results")

    factor = _accessory_item_factor(item)

    result = {
        **cached,
        "factor": round(factor, 4),
        "value": round(cached["market_base"] * factor, 2),
        "low": round(cached["market_low"] * factor, 2),
        "high": round(cached["market_high"] * factor, 2),
        "market_key": market_key,
    }

    return result, "ok"



def accessory_auto_value(item, market_cache=None):
    """Value one accessory using Accessory Matcher v2."""
    result, status = _accessory_ebay_value(
        item,
        market_cache=market_cache,
    )

    now = utc_now()

    if not result:
        item.auto_value_updated_at = now
        item.auto_value_status = status
        item.auto_value_message = (
            "Kein ausreichend sicherer Zubehör-Preisvergleich gefunden."
        )
        return False, status

    item.auto_value_eur = result["value"]
    item.auto_value_low_eur = result["low"]
    item.auto_value_high_eur = result["high"]
    item.auto_value_source = "eBay Browse API"
    item.auto_value_updated_at = now
    item.auto_value_status = "ok"
    item.auto_value_url = result.get("url") or None

    item.auto_value_message = (
        f"Accessory Matcher v2 · "
        f"Marktbasis {result['market_base']:.2f} € · "
        f"{result['count']} plausible Angebote · "
        f"Zustand {item.condition or 8}/10"
        + (" · mit OVP" if item.boxed else "")
    )

    db.session.add(
        AccessoryPriceHistory(
            accessory_item_id=item.id,
            value_eur=item.auto_value_eur,
            low_eur=item.auto_value_low_eur,
            high_eur=item.auto_value_high_eur,
            source=item.auto_value_source,
        )
    )

    return True, "ok"

@app.route("/accessories/<int:item_id>/value", methods=["POST"])
@login_required
def accessory_item_value(item_id):
    item = scoped_accessory_or_404(item_id)
    ok, status = accessory_auto_value(item)
    if ok:
        db.session.commit()
        flash(f"Zubehörwert aktualisiert: {item.auto_value_eur:.2f} €.", "success")
    else:
        db.session.commit()
        flash("Kein ausreichend sicherer Zubehör-Preisvergleich gefunden.", "warning")
    return redirect_back("accessories")


@app.route("/accessories/revalue", methods=["POST"])
@login_required

def accessories_revalue_all():
    items = (
        scoped_accessory_query()
        .filter_by(status="owned")
        .filter(AccessoryItem.auto_value_eur.is_(None))
        .order_by(AccessoryItem.id)
        .all()
    )

    valued = 0
    failed = 0
    market_cache = {}

    for item in items:
        try:
            ok, _ = accessory_auto_value(
                item,
                market_cache=market_cache,
            )

            valued += 1 if ok else 0
            failed += 0 if ok else 1

            db.session.commit()

        except Exception as exc:
            db.session.rollback()
            failed += 1

            app.logger.exception(
                "Accessory revaluation failed for item %s: %s",
                item.id,
                exc,
            )

    flash(
        f"Zubehörbewertung abgeschlossen: "
        f"{valued} aktualisiert, "
        f"{failed} ohne sicheren Preis, "
        f"bereits bewertete übersprungen.",
        "success" if valued else "warning",
    )

    return redirect(
        request.form.get("return_to")
        or url_for("accessories")
    )

@app.route("/accessories", methods=["GET", "POST"])
@login_required
def accessories():
    if request.method == "POST":
        name=request.form.get("name", "").strip()
        if name:
            barcode = clean_barcode(request.form.get("barcode"))
            product_code = request.form.get("product_code", "").strip() or None
            duplicate_checks = []
            if barcode:
                duplicate_checks.append(AccessoryItem.barcode == barcode)
            if product_code:
                duplicate_checks.append(AccessoryItem.product_code.ilike(product_code))
            duplicate = scoped_accessory_query().filter(db.or_(*duplicate_checks)).first() if duplicate_checks else None
            if duplicate and request.form.get("confirm_duplicate") != "1":
                flash(f"Zubehör „{duplicate.name}“ ist mit dieser Kennung bereits vorhanden. Öffne den Treffer oder füge bewusst ein weiteres Exemplar hinzu.", "warning")
                return redirect(url_for("accessory_item_edit", item_id=duplicate.id))
            item=AccessoryItem(user_id=active_collection_user_id(), name=name, console_id=request.form.get("console_id", type=int), manufacturer=request.form.get("manufacturer", "").strip() or None, model_number=request.form.get("model_number", "").strip() or None, barcode=barcode or None, product_code=product_code, category=request.form.get("category", "other"), compatibility=request.form.get("compatibility", "").strip() or None, original_product=request.form.get("original_product") == "1", component_kind=request.form.get("component_kind", "device"), parent_accessory_id=request.form.get("parent_accessory_id", type=int), included_in_parent_value=request.form.get("included_in_parent_value") == "1", media_present=request.form.get("media_present") == "1", case_present=request.form.get("case_present") == "1", manual_present=request.form.get("manual_present") == "1", disc_condition=request.form.get("disc_condition", type=int), color=request.form.get("color", "").strip() or None, status=request.form.get("status", "owned"), quantity=max(1, request.form.get("quantity", type=int) or 1), condition=request.form.get("condition", type=int) or 8, boxed=request.form.get("boxed") == "1", purchase_price=parse_money_input(request.form.get("purchase_price")), estimated_value=parse_money_input(request.form.get("estimated_value")), storage_location=request.form.get("storage_location", "").strip() or None, reference_image=archived_or_original_image(request.form.get("reference_image")), notes=request.form.get("notes", "").strip() or None)
            db.session.add(item); db.session.flush()
            item.photo = _save_hardware_photo(request.files.get("photo"), item.id, "accessory")
            db.session.commit(); flash("Zubehör gespeichert.", "success")
        return redirect(request.form.get("return_to") or url_for("accessories"))

    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    console_id = request.args.get("console_id", type=int)
    status = request.args.get("status", "").strip()
    sort = (request.args.get("sort") or "").strip()
    accessory_sorts = {"name", "name_desc", "value_desc", "value_asc", "total_desc", "total_asc", "newest"}
    if sort in accessory_sorts: session["collector_sort_accessories"] = sort
    else: sort = session.get("collector_sort_accessories", "name")
    if sort not in accessory_sorts: sort = "name"
    query = scoped_accessory_query()
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(AccessoryItem.name.ilike(like), AccessoryItem.manufacturer.ilike(like), AccessoryItem.model_number.ilike(like), AccessoryItem.barcode.ilike(like), AccessoryItem.product_code.ilike(like), AccessoryItem.compatibility.ilike(like)))
    if category:
        query = query.filter(AccessoryItem.category == category)
    if console_id:
        query = query.filter(AccessoryItem.console_id == console_id)
    if status:
        query = query.filter(AccessoryItem.status == status)
    items = query.all()
    def _accessory_unit_value(item):
        value = effective_accessory_value(item)
        return float(value) if value is not None else -1.0
    def _accessory_total_value(item):
        value = _accessory_unit_value(item)
        return value * max(item.quantity or 1, 1) if value >= 0 else -1.0
    if sort == "name_desc": items.sort(key=lambda item:(item.name or "").casefold(), reverse=True)
    elif sort == "value_desc": items.sort(key=lambda item:(_accessory_unit_value(item), (item.name or "").casefold()), reverse=True)
    elif sort == "value_asc": items.sort(key=lambda item:(_accessory_unit_value(item) < 0, _accessory_unit_value(item), (item.name or "").casefold()))
    elif sort == "total_desc": items.sort(key=lambda item:(_accessory_total_value(item), (item.name or "").casefold()), reverse=True)
    elif sort == "total_asc": items.sort(key=lambda item:(_accessory_total_value(item) < 0, _accessory_total_value(item), (item.name or "").casefold()))
    elif sort == "newest": items.sort(key=lambda item:item.added_at or datetime.min, reverse=True)
    else: items.sort(key=lambda item:(item.name or "").casefold())
    return render_template("accessories.html", items=items, consoles=Console.query.order_by(Console.name).all(), categories=ACCESSORY_CATEGORIES, component_kinds=ACCESSORY_COMPONENT_KINDS, parent_items=scoped_accessory_query().filter(AccessoryItem.parent_accessory_id.is_(None)).order_by(AccessoryItem.name).all(), q=q, selected_category=category, selected_console_id=console_id, selected_status=status, selected_sort=sort)


@app.route("/accessories/search")
@login_required
def accessory_search():
    q = request.args.get("q", "").strip()
    console_id = request.args.get("console_id", type=int)
    category = request.args.get("category", "").strip()
    local_results = []
    online_results = []
    online_status = None
    online_queries = []
    if q:
        like = f"%{q}%"
        local_query = scoped_accessory_query().filter(db.or_(AccessoryItem.name.ilike(like), AccessoryItem.manufacturer.ilike(like), AccessoryItem.model_number.ilike(like), AccessoryItem.barcode.ilike(like), AccessoryItem.product_code.ilike(like), AccessoryItem.compatibility.ilike(like)))
        if console_id:
            local_query = local_query.filter(AccessoryItem.console_id == console_id)
        if category:
            local_query = local_query.filter(AccessoryItem.category == category)
        local_results = local_query.order_by(AccessoryItem.name).limit(40).all()
        console = db.session.get(Console, console_id) if console_id else None
        # Category labels are intentionally not appended: translated UI labels
        # such as "Start- / Zubehör-Disc" made Browse searches overly strict.
        primary_query = " ".join(x for x in (q, console.name if console else None) if x)
        online_queries.append(primary_query)
        online_results, online_status = ebay_search_items(primary_query, limit=30)

        # If a platform-qualified search has no hits, retry the user's exact
        # phrase. This catches alternative platform names and accessories that
        # are offered as universal products without console text in the title.
        if not online_results and online_status == "ok" and console and q != primary_query:
            online_queries.append(q)
            online_results, online_status = ebay_search_items(q, limit=30)

    online_status_messages = {
        "ebay_not_configured": "eBay ist noch nicht vollständig konfiguriert. Bitte Client-ID und Client-Secret im Nutzermanagement prüfen.",
        "ebay_auth_failed": "eBay hat die Zugangsdaten abgewiesen. Bitte Production/Sandbox und die hinterlegten Schlüssel prüfen.",
        "ebay_api_denied": "Das Zugriffstoken funktioniert, aber die eBay Browse API hat die Suchanfrage abgewiesen.",
        "ebay_unreachable": "eBay ist momentan nicht erreichbar oder hat nicht rechtzeitig geantwortet.",
    }
    return render_template("accessory_search.html", q=q, consoles=Console.query.order_by(Console.name).all(), selected_console_id=console_id, categories=ACCESSORY_CATEGORIES, selected_category=category, local_results=local_results, online_results=online_results, online_status=online_status, online_status_message=online_status_messages.get(online_status), online_queries=online_queries)


@app.route("/accessories/search/import", methods=["POST"])
@login_required
def accessory_search_import():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Der Zubehörname fehlt.", "warning")
        return redirect(url_for("accessory_search"))
    source_id = request.form.get("source_id", "").strip()
    existing = scoped_accessory_query().filter(AccessoryItem.name.ilike(name), AccessoryItem.console_id == request.form.get("console_id", type=int)).first()
    if existing:
        flash("Ein gleichnamiger Zubehörtreffer ist bereits vorhanden. Du kannst dort ein weiteres Exemplar erfassen.", "warning")
        return redirect(url_for("accessory_item_edit", item_id=existing.id))
    item = AccessoryItem(user_id=active_collection_user_id(), name=name, console_id=request.form.get("console_id", type=int), category=request.form.get("category", "other"), manufacturer=request.form.get("manufacturer", "").strip() or None, model_number=request.form.get("model_number", "").strip() or None, reference_image=archived_or_original_image(request.form.get("cover_url")), status="owned", quantity=1, condition=8, original_product=True, component_kind=request.form.get("component_kind", "device"), notes=(f"Importiert aus eBay Browse API · {source_id}" if source_id else "Importiert aus eBay Browse API"))
    db.session.add(item); db.session.commit()
    flash("Zubehörtreffer angelegt. Jetzt Zustand, Vollständigkeit und Kennungen ergänzen.", "success")
    return redirect(url_for("accessory_item_edit", item_id=item.id))



@app.route("/accessories/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def accessory_item_edit(item_id):
    item = scoped_accessory_or_404(item_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Name darf nicht leer sein.", "warning")
            return render_template(
                "accessory_item_edit.html",
                item=item,
                consoles=Console.query.order_by(Console.name).all(),
                categories=ACCESSORY_CATEGORIES,
                component_kinds=ACCESSORY_COMPONENT_KINDS,
                parent_items=scoped_accessory_query().filter(AccessoryItem.id != item.id, AccessoryItem.parent_accessory_id.is_(None)).order_by(AccessoryItem.name).all(),
                return_to=request.form.get("return_to", ""),
            )

        item.name = name
        item.console_id = request.form.get("console_id", type=int)
        item.manufacturer = (
            request.form.get("manufacturer", "").strip() or None
        )
        item.model_number = (
            request.form.get("model_number", "").strip() or None
        )
        item.barcode = clean_barcode(request.form.get("barcode")) or None
        item.product_code = request.form.get("product_code", "").strip() or None
        item.category = request.form.get("category", "other")
        item.compatibility = request.form.get("compatibility", "").strip() or None
        item.original_product = request.form.get("original_product") == "1"
        item.component_kind = request.form.get("component_kind", "device")
        item.parent_accessory_id = request.form.get("parent_accessory_id", type=int)
        if item.parent_accessory_id == item.id:
            item.parent_accessory_id = None
        item.included_in_parent_value = request.form.get("included_in_parent_value") == "1"
        item.media_present = request.form.get("media_present") == "1"
        item.case_present = request.form.get("case_present") == "1"
        item.manual_present = request.form.get("manual_present") == "1"
        item.disc_condition = request.form.get("disc_condition", type=int)
        item.color = request.form.get("color", "").strip() or None
        item.status = request.form.get("status", "owned")
        item.quantity = max(
            1,
            request.form.get("quantity", type=int) or 1,
        )
        item.condition = max(
            1,
            min(10, request.form.get("condition", type=int) or 8),
        )
        item.boxed = request.form.get("boxed") == "1"
        item.purchase_price = parse_money_input(
            request.form.get("purchase_price")
        )
        item.estimated_value = parse_money_input(
            request.form.get("estimated_value")
        )
        item.storage_location = (
            request.form.get("storage_location", "").strip() or None
        )
        item.reference_image = archived_or_original_image(request.form.get("reference_image"))
        item.notes = request.form.get("notes", "").strip() or None

        # Vorhandenes Foto behalten, solange kein neues hochgeladen wird.
        upload = request.files.get("photo")
        if upload and upload.filename:
            new_photo = _save_hardware_photo(
                upload,
                item.id,
                "accessory",
            )
            if new_photo:
                item.photo = new_photo

        db.session.commit()
        flash("Zubehör aktualisiert.", "success")
        return redirect(request.form.get("return_to") or url_for("accessories"))

    return render_template(
        "accessory_item_edit.html",
        item=item,
        consoles=Console.query.order_by(Console.name).all(),
        categories=ACCESSORY_CATEGORIES,
        component_kinds=ACCESSORY_COMPONENT_KINDS,
        parent_items=scoped_accessory_query().filter(AccessoryItem.id != item.id, AccessoryItem.parent_accessory_id.is_(None)).order_by(AccessoryItem.name).all(),
        return_to=request.args.get("return_to", ""),
    )


@app.route("/accessories/<int:item_id>/delete", methods=["POST"])
@login_required
def accessory_item_delete(item_id):
    item = scoped_accessory_or_404(item_id)
    name = item.name

    db.session.delete(item)
    db.session.commit()

    flash(f"Zubehör „{name}“ gelöscht.", "success")
    return redirect(url_for("accessories"))


def _csv_response(rows, filename):
    buf = io.StringIO(); writer = csv.writer(buf, delimiter=';')
    for row in rows: writer.writerow(row)
    return Response('\ufeff' + buf.getvalue(), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.route("/export/collection.csv")
@login_required
def export_collection_csv():
    items = CollectionItem.query.join(Game).filter(CollectionItem.user_id == active_collection_user_id()).order_by(Game.title).all()
    rows = [["Copy-ID","Titel","Konsole","Region","Sprache","Edition","EAN/UPC","Produktcode","Serienstatus","Serie","Publisher","Developer","Jahr","Status","Format","Vollständigkeit","Kaufpreis EUR","Manueller Schätzwert EUR","Automatischer Marktwert EUR","Fixierter Wert EUR","Fixierungsgrund","Fixiert am","Effektiver Wert EUR","Preisquelle","Letzte Bewertung","Lagerplatz","Tags","Spielstatus","Notizen"]]
    for i in items:
        rows.append([i.id,i.game.title,i.game.console.name,i.game.region or '',i.game.language or '',i.game.edition or '',i.game.barcode or '',i.game.product_code or '',i.game.series_status or 'unreviewed',i.game.franchise or '',i.game.publisher or '',i.game.developer or '',i.game.release_year or '',i.status,i.ownership_format or 'physical',i.completeness,i.purchase_price if i.purchase_price is not None else '',i.estimated_value if i.estimated_value is not None else '',i.auto_value_eur if i.auto_value_eur is not None else '',i.fixed_value_eur if i.fixed_value_eur is not None else '',i.fixed_value_reason or '',i.fixed_value_at.isoformat() if i.fixed_value_at else '',effective_value(i) if effective_value(i) is not None else '',effective_value_source(i) or '',i.auto_value_updated_at.isoformat() if i.auto_value_updated_at else '',i.storage_location or '',i.tags or '',i.play_status or '',i.notes or ''])
    return _csv_response(rows, f"gamecollector-sammlung-{date.today().isoformat()}.csv")


@app.route("/export/hardware.csv")
@login_required
def export_hardware_csv():
    rows=[["Exemplar-ID","Hersteller","Familie","Modell","Edition","Modellnummer","Revision","Farbe","Region","Status","Vollständigkeit","Funktionsstatus","Konsolenzustand","OVP-Zustand","Controllerzustand","Seriennummer","Netzteil","Kabel","Controller","Anleitung","Inlays","Originalzubehör","Kaufpreis EUR","Eigener Schätzwert EUR","Automatischer Wert EUR","Fixierter Wert EUR","Fixierungsgrund","Effektiver Wert EUR","Preisquelle","Bewertungsdatum","Lagerplatz","Firmware","Notizen"]]
    for i in scoped_hardware_query().join(HardwareModel).join(Console).order_by(Console.manufacturer,Console.name,HardwareModel.name).all():
        m=i.model; rows.append([i.id,m.console.manufacturer or "",m.console.name,m.name,m.edition or "",m.model_number or "",m.revision or "",m.color or "",m.region or "",i.status,i.completeness or "Loose",i.tested_status,i.condition,i.box_condition if i.boxed else "",i.controller_condition if i.controller_present else "",i.serial_number or "",i.power_supply_present,i.cables_present,i.controller_present,i.manual_present,i.inserts_present,i.original_accessories_present,i.purchase_price if i.purchase_price is not None else "",i.estimated_value if i.estimated_value is not None else "",i.auto_value_eur if i.auto_value_eur is not None else "",i.fixed_value_eur if i.fixed_value_eur is not None else "",i.fixed_value_reason or "",effective_hardware_value(i) if effective_hardware_value(i) is not None else "",effective_value_source(i) or "",i.auto_value_updated_at.isoformat() if i.auto_value_updated_at else "",i.storage_location or "",i.firmware or "",i.notes or ""])
    return _csv_response(rows,f"gamecollector-hardware-{date.today().isoformat()}.csv")


@app.route("/export/catalog.csv")
@login_required
def export_catalog_csv():
    rows=[["ID","Titel","Konsole","Region","Sprache","Jahr","Publisher","Developer","Genre","Edition","Serienstatus","Serie","Unterreihe","Generation","EAN/UPC","Produktcode","Externe Quelle","Externe ID"]]
    for g in Game.query.order_by(Game.title).all(): rows.append([g.id,g.title,g.console.name,g.region or '',g.language or '',g.release_year or '',g.publisher or '',g.developer or '',g.genre or '',g.edition or '',g.series_status or 'unreviewed',g.franchise or '',g.series_group or '',g.series_generation or '',g.barcode or '',g.product_code or '',g.external_source or '',g.external_id or ''])
    return _csv_response(rows, f"gamecollector-katalog-{date.today().isoformat()}.csv")

@app.route("/export/accessories.csv")
@login_required
def export_accessories_csv():
    rows=[["ID","Name","Konsole","Hersteller","Modellnummer","Farbe","Status","Anzahl","Zustand","OVP","Kaufpreis EUR","Eigener Schätzwert EUR","Automatischer Wert EUR","Fixierter Wert EUR","Fixierungsgrund","Effektiver Einzelwert EUR","Preisquelle","Bewertungsdatum","Lagerplatz","Notizen"]]
    for i in scoped_accessory_query().order_by(AccessoryItem.name).all(): rows.append([i.id,i.name,i.console.name if i.console else '',i.manufacturer or '',i.model_number or '',i.color or '',i.status,i.quantity,i.condition,'Ja' if i.boxed else 'Nein',i.purchase_price if i.purchase_price is not None else '',i.estimated_value if i.estimated_value is not None else '',i.auto_value_eur if i.auto_value_eur is not None else '',i.fixed_value_eur if i.fixed_value_eur is not None else '',i.fixed_value_reason or '',effective_accessory_value(i) if effective_accessory_value(i) is not None else '',effective_value_source(i) or '',i.auto_value_updated_at.isoformat() if i.auto_value_updated_at else '',i.storage_location or '',i.notes or ''])
    return _csv_response(rows, f"gamecollector-zubehoer-{date.today().isoformat()}.csv")

@app.route("/export/price-activity.csv")
@login_required
def export_price_activity_csv():
    rows=[["Zeitpunkt","Titel","Konsole","Vorher EUR","Neu EUR","Differenz EUR","Typ","Quelle"]]
    for a in PriceActivity.query.order_by(PriceActivity.recorded_at.desc()).all(): rows.append([a.recorded_at.isoformat(),a.collection_item.game.title,a.collection_item.game.console.name,a.previous_value_eur if a.previous_value_eur is not None else '',a.value_eur,a.delta_eur,a.change_type,a.source])
    return _csv_response(rows, f"gamecollector-preisaktivitaet-{date.today().isoformat()}.csv")

@app.route("/export/all.zip")
@login_required
def export_all_csv_zip():
    def csv_bytes(rows):
        b=io.StringIO(); w=csv.writer(b,delimiter=';'); [w.writerow(r) for r in rows]; return ('\\ufeff'+b.getvalue()).encode('utf-8')
    files={}
    games=[["ID","Titel","Konsole","Region","Edition","EAN","Serienstatus","Serie","Publisher","Developer"]]+[[g.id,g.title,g.console.name,g.region or '',g.edition or '',g.barcode or '',g.series_status or 'unreviewed',g.franchise or '',g.publisher or '',g.developer or ''] for g in Game.query.order_by(Game.title).all()]
    coll=[["Copy-ID","Titel","Konsole","Format","Kaufpreis","Manuell","Automatisch","Effektiv","Quelle"]]+[[i.id,i.game.title,i.game.console.name,i.ownership_format or 'physical',i.purchase_price or '',i.estimated_value or '',i.auto_value_eur or '',effective_value(i) if effective_value(i) is not None else '',effective_value_source(i) or ''] for i in CollectionItem.query.filter_by(user_id=active_collection_user_id()).all()]
    hw=[["ID","Konsole","Modell","Modellnummer","Status","Schätzwert"]]+[[i.id,i.model.console.name,i.model.name,i.model.model_number or '',i.status,i.estimated_value or ''] for i in scoped_hardware_query().all()]
    acc=[["ID","Name","Konsole","Status","Anzahl","Schätzwert"]]+[[i.id,i.name,i.console.name if i.console else '',i.status,i.quantity,i.estimated_value or ''] for i in scoped_accessory_query().all()]
    pa=[["Zeitpunkt","Titel","Wert","Differenz","Typ","Quelle"]]+[[a.recorded_at.isoformat(),a.collection_item.game.title,a.value_eur,a.delta_eur,a.change_type,a.source] for a in PriceActivity.query.order_by(PriceActivity.recorded_at).all()]
    for name,rows in [("katalog.csv",games),("sammlung.csv",coll),("hardware.csv",hw),("zubehoer.csv",acc),("preisaktivitaet.csv",pa)]: files[name]=csv_bytes(rows)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items(): z.writestr(name,data)
    out.seek(0); return send_file(out,mimetype='application/zip',as_attachment=True,download_name=f"gamecollector-komplettexport-{date.today().isoformat()}.zip")


@app.route("/export/collection.json")
@login_required
def export_collection_json():
    items = CollectionItem.query.join(Game).filter(CollectionItem.user_id == active_collection_user_id()).order_by(Game.title).all()
    payload=[]
    for i in items:
        payload.append({"copy_id":i.id,"title":i.game.title,"console":i.game.console.name,"region":i.game.region,"status":i.status,"ownership_format":i.ownership_format or "physical","completeness":i.completeness,"purchase_price":i.purchase_price,"value_eur":effective_value(i),"storage_location":i.storage_location,"tags":i.tags,"play_status":i.play_status,"notes":i.notes})
    data=json.dumps({"version":APP_VERSION,"exported_at":utc_now().isoformat(),"items":payload},ensure_ascii=False,indent=2)
    return Response(data, mimetype="application/json", headers={"Content-Disposition":f'attachment; filename="gamecollector-sammlung-{date.today().isoformat()}.json"'})


@app.route("/admin/backup")
@admin_required
def admin_backup():
    backup_roots = []
    updates = Path("/opt/gamecollector/updates")
    if updates.exists():
        for path in sorted(updates.glob("v*/backup-pre-v*"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]:
            try: backup_roots.append({"name": str(path), "mtime": datetime.fromtimestamp(path.stat().st_mtime), "size": sum(f.stat().st_size for f in path.rglob("*") if f.is_file())})
            except OSError: pass
    return render_template("backup.html", backup_roots=backup_roots)


@app.route("/admin/images")
@admin_required
def admin_images():
    candidates = external_image_candidates()
    by_kind = {}
    for label, _, _, _ in candidates:
        by_kind[label] = by_kind.get(label, 0) + 1
    stats = {
        "remaining": len(candidates),
        "archived": ImageAsset.query.filter_by(status="archived").count(),
        "failed": ImageAsset.query.filter_by(status="failed").count(),
        "bytes": sum(int(row.byte_size or 0) for row in ImageAsset.query.filter_by(status="archived").all()),
    }
    failures = ImageAsset.query.filter_by(status="failed").order_by(ImageAsset.last_attempt_at.desc()).limit(20).all()
    return render_template("image_archive.html", stats=stats, by_kind=by_kind, failures=failures)


@app.route("/admin/images/archive", methods=["POST"])
@admin_required
def admin_images_archive():
    result = archive_external_image_batch(
        limit=request.form.get("limit", type=int) or 30,
        force_failed=request.form.get("force_failed") == "1",
    )
    if result["migrated"]:
        flash(f'{result["migrated"]} Bilder wurden dauerhaft lokal archiviert.', "success")
    if result["failed"]:
        flash(f'{result["failed"]} Bilder konnten nicht geladen werden. Details stehen im Bildarchiv.', "warning")
    if not result["migrated"] and not result["failed"] and result["remaining"] == 0:
        flash("Alle gespeicherten Bildverweise sind bereits lokal.", "success")
    return redirect(url_for("admin_images"))


@app.route("/admin/backup/download")
@admin_required
def admin_backup_download():
    dburl = db.engine.url.render_as_string(hide_password=False).replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        result = subprocess.run(["pg_dump", "--no-owner", "--no-privileges", dburl], capture_output=True, check=True, timeout=90)
    except Exception as exc:
        app.logger.exception("pg_dump failed")
        flash(f"Datenbankbackup fehlgeschlagen: {exc}", "danger")
        return redirect(url_for("admin_backup"))
    log_activity("backup_created", "database", None, "Administrator hat ein SQL-Datenbankbackup heruntergeladen.")
    db.session.commit()
    return Response(result.stdout, mimetype="application/sql", headers={"Content-Disposition":f'attachment; filename="gamecollector-backup-{datetime.now().strftime("%Y%m%d-%H%M")}.sql"'})


@app.route("/admin/backup/archive")
@admin_required
def admin_backup_archive():
    """Portable archive: SQL dump plus uploaded images when available."""
    dburl = db.engine.url.render_as_string(hide_password=False).replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        result = subprocess.run(["pg_dump", "--no-owner", "--no-privileges", dburl], capture_output=True, check=True, timeout=90)
    except Exception as exc:
        app.logger.exception("pg_dump archive failed")
        flash(f"Komplettbackup fehlgeschlagen: {exc}", "danger")
        return redirect(url_for("admin_backup"))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("database.sql", result.stdout)
        uploads = Path(app.root_path) / "static" / "uploads"
        if uploads.exists():
            for path in uploads.rglob("*"):
                if path.is_file() and path.name != ".gitkeep":
                    z.write(path, str(Path("uploads") / path.relative_to(uploads)))
        z.writestr("README.txt", f"Bibo {APP_VERSION} Komplettbackup\nErstellt: {datetime.now().isoformat()}\nEnthält database.sql und uploads/.\n")
    out.seek(0)
    log_activity("backup_archive_created", "database", None, "Administrator hat ein Komplettbackup erstellt.")
    db.session.commit()
    return send_file(out, mimetype="application/zip", as_attachment=True, download_name=f"gamecollector-komplettbackup-{datetime.now().strftime('%Y%m%d-%H%M')}.zip")


@app.route("/projects", methods=["GET", "POST"])
@login_required
def collection_projects():
    if request.method == "POST":
        name=request.form.get("name","").strip()
        if name:
            db.session.add(CollectionProject(collection_user_id=active_collection_user_id(), name=name, description=request.form.get("description","").strip() or None, target_query=request.form.get("target_query","").strip() or None, target_count=request.form.get("target_count", type=int)))
            db.session.commit(); flash("Sammlungsprojekt angelegt.", "success")
        return redirect(url_for("collection_projects"))
    projects=CollectionProject.query.filter_by(collection_user_id=active_collection_user_id()).order_by(CollectionProject.created_at.desc()).all()
    owned_titles=[i.game.title.casefold() for i in CollectionItem.query.filter_by(status="owned", user_id=active_collection_user_id()).all()]
    cards=[]
    for p in projects:
        current=sum(1 for t in owned_titles if not p.target_query or p.target_query.casefold() in t)
        target=p.target_count or current
        cards.append({"project":p,"current":current,"target":target,"pct":min(100,round(current*100/max(target,1)))})
    return render_template("projects.html", cards=cards)

@app.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def collection_project_delete(project_id):
    p=CollectionProject.query.filter_by(id=project_id, collection_user_id=active_collection_user_id()).first_or_404(); db.session.delete(p); db.session.commit(); flash("Sammlungsprojekt gelöscht.","success"); return redirect(url_for("collection_projects"))

@app.route("/offline")
def offline_page():
    return render_template("offline.html")


def repair_v116_franchise_aliases():
    """Normalize legacy Pokémon aliases without violating series-entry uniqueness.

    v1.1.6 initially renamed every SeriesEntry row in place.  If both
    ``Pokemon`` and ``Pokémon`` already contained the same RAWG id this hit
    uq_series_entry_external during application boot.  Grouping by external
    identity lets us merge the alias row first and only rename when there is
    no canonical row yet.  The repair is intentionally best-effort: a data
    cleanup must never prevent the web or scheduler container from booting.
    """
    changed = 0
    try:
        for game in Game.query.all():
            if _search_text(game.franchise) == "pokemon" and game.franchise != "Pokémon":
                game.franchise = "Pokémon"
                if game.franchise_source != "manual":
                    game.franchise_source = game.franchise_source or "auto-rule"
                changed += 1

        pokemon_entries = [
            entry for entry in SeriesEntry.query.order_by(SeriesEntry.id).all()
            if _search_text(entry.franchise) == "pokemon"
        ]
        grouped = {}
        for entry in pokemon_entries:
            key = (str(entry.external_source or ""), str(entry.external_id or ""))
            grouped.setdefault(key, []).append(entry)

        merge_fields = ("title", "release_year", "cover_url", "platforms",
                        "series_group", "series_generation")
        for rows in grouped.values():
            canonical = next((row for row in rows if row.franchise == "Pokémon"), None)
            keeper = canonical or rows[0]

            # Preserve useful metadata before dropping duplicate alias rows.
            for row in rows:
                if row.id == keeper.id:
                    continue
                for field in merge_fields:
                    if not getattr(keeper, field, None) and getattr(row, field, None):
                        setattr(keeper, field, getattr(row, field))
                db.session.delete(row)
                changed += 1

            if keeper.franchise != "Pokémon":
                keeper.franchise = "Pokémon"
                changed += 1

        if changed:
            db.session.commit()
            app.logger.info("v1.1.6 normalized/merged %d Pokémon franchise aliases", changed)
        return changed
    except Exception:
        db.session.rollback()
        app.logger.exception("v1.1.6 Pokémon alias repair skipped after an unexpected error")
        return 0

with app.app_context():
    db.create_all()
    ensure_schema()
    recover_stale_revaluation_runs(force=True)
    ensure_default_consoles()
    normalize_existing_consoles()
    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_password and not User.query.filter_by(username=admin_user).first():
        db.session.add(User(username=admin_user, display_name=admin_user, password_hash=generate_password_hash(admin_password), is_admin=True, is_system=False))
        db.session.commit()
    shared = User.query.filter_by(username=SHARED_COLLECTION_USERNAME).first()
    if not shared:
        shared = User(username=SHARED_COLLECTION_USERNAME, display_name="Gemeinsame Sammlung",
                      password_hash=generate_password_hash(os.urandom(32).hex()), is_admin=False, is_system=True)
        db.session.add(shared)
        db.session.commit()
    ensure_single_shared_collection()
    ensure_collection_spaces()
    repair_pc_hardware_profiles()
    try:
        refresh_bibo_registry()
    except Exception:
        db.session.rollback()
        app.logger.exception("Bibo registry refresh skipped during startup")
    split_grouped_video_copies()
    repair_pokemon_card_valuation_artifacts()
    # Alias collisions must be merged before curated/online series data is
    # touched; otherwise legacy Pokemon/Pokémon rows can violate the unique key.
    repair_v116_franchise_aliases()
    repair_lego_franchise_metadata()
    repair_series_v102_metadata()
    ensure_curated_series_entries()
    repair_series_v103_metadata()
    repair_series_v104_metadata()

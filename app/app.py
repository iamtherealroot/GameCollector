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
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet, InvalidToken
from difflib import SequenceMatcher
from functools import wraps
import re
import subprocess
import tempfile
import zipfile
import threading
import time
import statistics
from pathlib import Path
from html.parser import HTMLParser

APP_VERSION = "2.1.2"
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
    "nintendo entertainment system": "Nintendo Entertainment System (NES)",
    "snes": "Super Nintendo (SNES)",
    "super nintendo": "Super Nintendo (SNES)",
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
    return CONSOLE_ALIASES.get(cleaned.casefold(), cleaned)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    role = db.Column(db.String(20), default="editor", nullable=False)
    display_name = db.Column(db.String(120))
    is_system = db.Column(db.Boolean, default=False, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)


class AppSetting(db.Model):
    """Global application settings. Secret values are encrypted before storage."""
    key = db.Column(db.String(120), primary_key=True)
    value = db.Column(db.Text)
    is_secret = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)


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
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    goal_type = db.Column(db.String(30), default="manual", nullable=False)
    target_count = db.Column(db.Integer, nullable=False, default=1)
    franchise = db.Column(db.Text)
    series_group = db.Column(db.String(120))
    console_id = db.Column(db.Integer, db.ForeignKey("console.id"))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
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


def active_collection_owner():
    """All signed-in users work on one shared collection."""
    if not current_user.is_authenticated:
        return None
    return shared_collection_user()


def active_collection_user_id():
    owner = active_collection_owner()
    return owner.id if owner else None


@app.context_processor
def inject_globals():
    owner = active_collection_owner() if current_user.is_authenticated else None
    return {
        "now": local_datetime(utc_now()), "app_version": APP_VERSION, "user_collection": collection_for, "user_collection_items": collection_items_for,
        "active_collection_scope": "shared",
        "active_collection_label": "Sammlung",
        "active_collection_owner": owner,
        "effective_role": effective_role() if current_user.is_authenticated else None,
        "eur": format_eur,
        "game_price": game_price_info,
        "effective_value": effective_value,
        "effective_value_source": effective_value_source,
        "accessory_category_label": accessory_category_label,
        "accessory_counts_in_total": accessory_counts_in_total,
        "display_timezone": DISPLAY_TIMEZONE_NAME,
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
        actor_user_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id,
        message=message, details_json=json.dumps(details, ensure_ascii=False) if details else None,
    )
    db.session.add(row)
    return row


def effective_role(user=None):
    user = user or current_user
    if getattr(user, "is_admin", False):
        return "admin"
    return getattr(user, "role", None) or "editor"


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if effective_role() != "admin":
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
        with urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8")), "ok"
    except HTTPError as exc:
        if exc.code == 401:
            _EBAY_TOKEN_CACHE["expires_at"] = 0
        return None, "ebay_api_denied" if exc.code in (401, 403) else "ebay_unreachable"
    except (URLError, TimeoutError, ValueError):
        return None, "ebay_unreachable"


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
    if effective_role() != "viewer":
        return None
    # Viewer may update their own display name/password and log out, but cannot alter shared data.
    if request.endpoint in {"account", "logout"}:
        return None
    abort(403)


@app.before_request
def enforce_bootstrap_password_change():
    """A public default login may only reach the password-change screen."""
    if not current_user.is_authenticated or not getattr(current_user, "must_change_password", False):
        return None
    if request.endpoint in {"account", "logout", "health", "health_deep", "static"}:
        return None
    flash("Bitte ersetze zuerst das vorläufige Admin-Passwort.", "warning")
    return redirect(url_for("account"))


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
        wanted_run = {"current_index":"INTEGER DEFAULT 0 NOT NULL", "total_count":"INTEGER DEFAULT 0 NOT NULL", "current_title":"VARCHAR(240)", "state":"VARCHAR(20) DEFAULT 'queued' NOT NULL", "heartbeat_at":"TIMESTAMP"}
        with db.engine.begin() as conn:
            for column, sql_type in wanted_run.items():
                if column not in cols:
                    conn.execute(text(f'ALTER TABLE "revaluation_run" ADD COLUMN {column} {sql_type}'))
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
            if "must_change_password" not in existing_user:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE NOT NULL'))
            conn.execute(text("UPDATE \"user\" SET role = 'admin' WHERE is_admin = TRUE"))

    # v0.3.5 collection-copy details and market-value metadata.
    inspector = inspect(db.engine)
    if "collection_item" in inspector.get_table_names():
        existing_collection = {c["name"] for c in inspector.get_columns("collection_item")}
        collection_wanted = {
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

    # Assign legacy single-user collection to the first admin (or first account).
    inspector = inspect(db.engine)
    if "collection_item" in inspector.get_table_names() and "user" in inspector.get_table_names():
        with db.engine.begin() as conn:
            owner_id = conn.execute(text('SELECT id FROM "user" ORDER BY is_admin DESC, id ASC LIMIT 1')).scalar()
            if owner_id is not None:
                conn.execute(text('UPDATE "collection_item" SET user_id = :uid WHERE user_id IS NULL'), {"uid": owner_id})


def ensure_single_shared_collection():
    """Keep every physical copy, but move legacy per-user rows into the one shared collection."""
    shared = shared_collection_user()
    if not shared:
        return
    changed = False
    for item in CollectionItem.query.filter(CollectionItem.user_id != shared.id).all():
        item.user_id = shared.id
        changed = True
    if changed:
        db.session.commit()


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
    """Automatic market value wins; manual estimate is the fallback."""
    if item.auto_value_eur is not None:
        return float(item.auto_value_eur)
    if item.estimated_value is not None:
        return float(item.estimated_value)
    return None


def effective_value_source(item):
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


def store_auto_valuation(item, valuation, prices, run=None):
    now = utc_now()
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
        if len(found) >= 8:
            break
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
        if game_words and matched < max(1, (len(game_words) + 1) // 2):
            continue
        total = float(row["price"]) + float(row.get("shipping") or 0)
        if 0.5 <= total <= 5000:
            values.append(total)
    if len(values) < 2:
        return None, None, "ebay_too_few_results"

    center = statistics.median(values)
    values = [v for v in values if center * 0.35 <= v <= center * 2.5]
    if len(values) >= 4:
        ordered = sorted(values)
        half = len(ordered) // 2
        q1 = statistics.median(ordered[:half])
        q3 = statistics.median(ordered[-half:])
        iqr = q3 - q1
        if iqr > 0:
            trimmed = [v for v in ordered if q1 - 1.5 * iqr <= v <= q3 + 1.5 * iqr]
            if len(trimmed) >= 2:
                values = trimmed
    if len(values) < 2:
        return None, None, "ebay_too_few_results"

    kind, completeness = value_kind_for_item(item)
    completeness_factor = 1.25 if kind == "new" else (0.75 if kind == "loose" else (1.0 if kind == "cib" else 0.85))
    value = round(statistics.median(values) * completeness_factor * condition_factor(item), 2)
    low = round(min(values) * completeness_factor * condition_factor(item), 2)
    high = round(max(values) * completeness_factor * condition_factor(item), 2)
    confidence = "mittel" if len(values) >= 6 else ("niedrig" if len(values) >= 3 else "vorläufig")
    prices = {
        "source": "eBay-Angebote", "url": f"https://www.ebay.de/sch/i.html?{urlencode({'_nkw': queries[-1]})}",
        "market": "aktive Festpreisangebote" if len(values) >= 3 else "vorläufig aus zwei aktiven Festpreisangeboten", "offer_count": len(values),
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
    "ebay_too_few_results": "Weniger als drei plausible eBay-Angebote; es wurde bewusst kein Wert gespeichert.",
}

def auto_value_item(item, run=None):
    if not game_is_physical_candidate(item.game):
        item.auto_value_status = "non_physical_excluded"
        item.auto_value_message = "Nicht physisch veröffentlicht; von automatischer Bewertung und Serienfortschritt ausgeschlossen."
        return False, "Nicht physisch"
    # v2.0.1 source priority: 1) eBay Browse API, 2) PrixRetro, 3) PriceCharting, 4) VGPreise.
    ebay_valuation, ebay_prices, ebay_status = ebay_offer_valuation(item)
    if ebay_valuation:
        store_auto_valuation(item, ebay_valuation, ebay_prices, run=run)
        item.auto_value_status = "ok"
        prefix = "Vorläufiger Wert" if ebay_prices.get("offer_count", 0) == 2 else "Primärwert"
        item.auto_value_message = f"{prefix} aus {ebay_prices.get('offer_count')} plausiblen eBay-Festpreisangeboten; Details geeigneter Treffer wurden mit getItem geprüft."
        return True, "eBay-Angebote"

    prix_prices, prix_status = prixretro_lookup(item.game)
    if prix_prices:
        valuation = valuation_from_prices(item, prix_prices)
        if valuation:
            store_auto_valuation(item, valuation, prix_prices, run=run)
            item.auto_value_status = "ok"
            item.auto_value_message = "Automatisch bewertet über PrixRetro.com (Fallback nach eBay)."
            return True, "PrixRetro.com"
        prix_status = "condition_price_missing"

    vg_prices, vg_status = vgpreise_lookup(item.game)
    if vg_prices:
        valuation = valuation_from_prices(item, vg_prices)
        if valuation:
            store_auto_valuation(item, valuation, vg_prices, run=run)
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
    """Move every game from source to target and remove source. Caller commits."""
    conflicts = _console_merge_conflicts(source, target)
    if conflicts:
        return False, conflicts
    Game.query.filter_by(console_id=source.id).update(
        {Game.console_id: target.id}, synchronize_session=False
    )
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
    game.cover_url = request.form.get("cover_url", "").strip() or None
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


def apply_collection_form(item):
    """Compatibility wrapper; all CollectionItem writes use one implementation."""
    return update_collection_item_from_form(item)



@app.route("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}, 200

@app.route("/health/deep")
def health_deep():
    """1.0 stable readiness probe: database connectivity and core tables."""
    try:
        db.session.execute(text("SELECT 1"))
        return {"status":"ok","version":APP_VERSION,"database":"ok","games":Game.query.count(),"collection_items":CollectionItem.query.count()}, 200
    except Exception as exc:
        app.logger.exception("deep healthcheck failed")
        return {"status":"error","version":APP_VERSION,"database":"error","message":str(exc)[:160]}, 503


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "").strip(), is_system=False).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            session.permanent = True
            login_user(user, remember=True, duration=timedelta(days=SESSION_DAYS))
            return redirect(url_for("account" if user.must_change_password else "dashboard"))
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
        if current_user.must_change_password and not password:
            flash("Bitte lege ein neues Passwort mit mindestens 8 Zeichen fest.", "danger")
            return redirect(url_for("account"))
        if password:
            if len(password) < 8:
                flash("Das neue Passwort muss mindestens 8 Zeichen lang sein.", "danger")
                return redirect(url_for("account"))
            current_user.password_hash = generate_password_hash(password)
            current_user.must_change_password = False
        db.session.commit()
        flash("Kontoeinstellungen gespeichert.", "success")
        return redirect(url_for("account"))
    ebay = ebay_credentials()
    return render_template(
        "account.html", ebay_configured=bool(ebay["client_id"] and ebay["client_secret"]),
        ebay_client_id=ebay["client_id"], ebay_dev_id=ebay["dev_id"],
        ebay_marketplace=ebay["marketplace"], ebay_environment=ebay["environment"],
    )


MARKET_MOVEMENT_PERIODS = {
    "latest": {"label": "Letzte Bewertung", "days": None},
    "1d": {"label": "24 Stunden", "days": 1},
    "7d": {"label": "7 Tage", "days": 7},
    "30d": {"label": "30 Tage", "days": 30},
}


def collection_market_movement(period, game_items, hardware_items, accessory_items):
    """Compare successful automatic valuations without treating stock as profit.

    Games use PriceActivity because it also records unchanged checks. Hardware
    and accessories use their complete price histories. Manual estimates never
    participate in market movement.
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

    category_delta = {
        "game": round(sum(r["impact"] for r in rows if r["kind"] == "game"), 2),
        "hardware": round(sum(r["impact"] for r in rows if r["kind"] == "hardware"), 2),
        "accessory": round(sum(r["impact"] for r in rows if r["kind"] == "accessory"), 2),
    }
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


@app.route("/")
@login_required
def dashboard():
    owned_items = [i for i in CollectionItem.query.filter_by(status="owned", user_id=active_collection_user_id()).all() if game_is_physical_candidate(i.game)]
    wishlist_items = [i for i in CollectionItem.query.filter_by(status="wishlist", user_id=active_collection_user_id()).all() if game_is_physical_candidate(i.game)]
    owned = len(owned_items)
    wishlist = len(wishlist_items)
    total_value = sum((effective_value(i) or 0) for i in owned_items)
    valued_count = sum(1 for i in owned_items if i.auto_value_eur is not None or i.estimated_value is not None)
    auto_valued_count = sum(1 for i in owned_items if i.auto_value_eur is not None)
    purchase_total = sum((i.purchase_price or 0) for i in owned_items)
    console_count = Console.query.count()
    catalog_count = Game.query.count()
    recent = sorted(owned_items, key=lambda i:i.added_at or datetime.min, reverse=True)[:8]
    valuation_status_counts = {}
    for item in owned_items:
        key = item.auto_value_status or ("ok" if item.auto_value_eur is not None else "not_checked")
        valuation_status_counts[key] = valuation_status_counts.get(key, 0) + 1
    auto_missing_count = sum(1 for i in owned_items if i.auto_value_eur is None)
    no_value_count = sum(1 for i in owned_items if i.auto_value_eur is None and i.estimated_value is None)

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
        [i for i in owned_items if i.auto_value_eur is not None or i.estimated_value is not None],
        key=lambda i: effective_value(i) or 0,
        reverse=True,
    )[:10]

    price_changes = []
    for item in owned_items:
        history = sorted(item.price_history, key=lambda h: h.recorded_at or datetime.min, reverse=True)
        if len(history) >= 2:
            latest, previous = history[0], history[1]
            delta = latest.value_eur - previous.value_eur
            pct = (delta / previous.value_eur * 100) if previous.value_eur else 0
            price_changes.append({"item": item, "current": latest.value_eur, "previous": previous.value_eur, "delta": delta, "pct": pct})
    price_changes.sort(key=lambda x: abs(x["delta"]), reverse=True)
    change_total = sum(x["delta"] for x in price_changes)

    series_rows = db.session.query(
        Game.franchise, db.func.count(db.distinct(Game.id)).label("total"),
        db.func.count(db.distinct(db.case((db.and_(CollectionItem.status == "owned", CollectionItem.user_id == active_collection_user_id()), Game.id)))).label("owned")
    ).outerjoin(CollectionItem, CollectionItem.game_id == Game.id).filter(
        Game.franchise.isnot(None), Game.franchise != ""
    ).group_by(Game.franchise).all()
    series_stats = []
    for name, total, owned_count in series_rows:
        if _search_text(name) == "pokemon":
            external_total = len(POKEMON_CURATED_SERIES) + len(POKEMON_CURATED_SPINOFFS)
        else:
            external_total = (SeriesEntry.query.filter_by(franchise=name, external_source="GameCollector").count() if name in CURATED_SERIES else SeriesEntry.query.filter_by(franchise=name).count())
        denominator = max(total, external_total)
        series_stats.append({"name": name, "owned": owned_count, "total": denominator, "pct": round((owned_count / denominator) * 100) if denominator else 0})
    series_stats.sort(key=lambda x: (x["owned"], x["total"]), reverse=True)

    missing_cover_count = sum(1 for i in owned_items if not i.game.cover_url)
    incomplete_data_count = len(quality_issues())
    high_priority_wishlist = CollectionItem.query.filter_by(user_id=active_collection_user_id(), status="wishlist", wishlist_priority=3).count()
    recent_activity = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(6).all()

    # v0.7.9 valuation health: only successfully completed runs count as fresh.
    latest_auto_run = RevaluationRun.query.filter_by(source="automatic", success=True).order_by(RevaluationRun.finished_at.desc()).first()
    latest_manual_run = RevaluationRun.query.filter_by(source="manual", success=True).order_by(RevaluationRun.finished_at.desc()).first()
    valuation_health = {"state": "unknown", "label": "Noch kein automatischer Lauf protokolliert", "last_auto": None, "last_manual": None, "next_auto": None}
    try:
        from zoneinfo import ZoneInfo
        tz_name = os.environ.get("TZ", "Europe/Berlin")
        tz = ZoneInfo(tz_name)
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

    recent_price_activity = PriceActivity.query.order_by(PriceActivity.recorded_at.desc()).limit(10).all()
    hardware_owned = HardwareItem.query.filter_by(status="owned").count()
    accessory_owned = db.session.query(db.func.coalesce(db.func.sum(AccessoryItem.quantity), 0)).filter(AccessoryItem.status == "owned").scalar() or 0
    hardware_items_owned = HardwareItem.query.filter_by(status="owned").all()
    hardware_value = sum((effective_hardware_value(x) or 0) for x in hardware_items_owned)
    hardware_valued_count = sum(1 for x in hardware_items_owned if x.estimated_value is not None or x.auto_value_eur is not None)
    top_hardware_items = sorted([x for x in HardwareItem.query.filter_by(status="owned").all() if effective_hardware_value(x) is not None], key=lambda x: effective_hardware_value(x) or 0, reverse=True)[:10]
    accessory_items_owned = AccessoryItem.query.filter_by(status="owned").all()
    accessory_value = sum(((effective_accessory_value(x) or 0) * (x.quantity or 1)) for x in accessory_items_owned if accessory_counts_in_total(x))
    accessory_valued_count = sum((x.quantity or 1) for x in accessory_items_owned if effective_accessory_value(x) is not None)
    top_accessory_items = sorted([x for x in accessory_items_owned if effective_accessory_value(x) is not None], key=lambda x: (effective_accessory_value(x) or 0) * (x.quantity or 1), reverse=True)[:10]
    complete_collection_value = total_value + hardware_value + accessory_value
    movement_period = request.args.get("movement", "latest")
    market_movement = collection_market_movement(
        movement_period, owned_items, hardware_items_owned, accessory_items_owned,
    )
    snapshots = CollectionValueSnapshot.query.order_by(CollectionValueSnapshot.recorded_at).all()
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
    latest_run = RevaluationRun.query.order_by(RevaluationRun.started_at.desc()).first()
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

    return render_template("dashboard.html", owned=owned, wishlist=wishlist, total_value=total_value,
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
                           series_mismatch_count=series_mismatch_count, data_quality_score=data_quality_score)


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
            db.session.add(user); db.session.flush(); log_activity("user_created", "user", user.id, f"Benutzer {username} wurde angelegt."); db.session.commit()
            flash(f"Benutzer {username} wurde angelegt.", "success")
        return redirect(url_for("admin_users"))
    users = User.query.filter_by(is_system=False).order_by(User.username).all()
    ebay = ebay_credentials()
    return render_template(
        "users.html", users=users,
        ebay_configured=bool(ebay["client_id"] and ebay["client_secret"]),
        ebay_client_id=ebay["client_id"], ebay_dev_id=ebay["dev_id"],
        ebay_marketplace=ebay["marketplace"], ebay_environment=ebay["environment"],
    )


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
                flash("GameCollector nimmt ausschließlich physisch veröffentlichte Spiele auf. Mobile- und reine Online-Titel sind ausgeschlossen.", "warning")
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
                cover_url=request.form.get("cover_url", "").strip(),
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
            game.cover_url = local_cover or candidate["cover_url"]
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
                           historical=historical, historical_status=historical_status)


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
        if item.estimated_value is not None:
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


def recover_stale_revaluation_runs(force=False):
    """Recover orphaned valuation runs. At app startup no old daemon worker survives."""
    from datetime import timedelta
    cutoff = utc_now() - timedelta(minutes=20)
    runs = RevaluationRun.query.filter(RevaluationRun.state.in_(["queued", "running", "cancel_requested"])).all()
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
    recover_stale_revaluation_runs()
    active = RevaluationRun.query.filter(RevaluationRun.state.in_(["queued", "running", "cancel_requested"])).order_by(RevaluationRun.started_at.desc()).first()
    if active:
        flash("Eine Neubewertung läuft bereits.", "warning")
        if request.form.get("return_to") == "dashboard":
            return redirect(url_for("dashboard"))
        return redirect(url_for("valuation_detail", run_id=active.id))
    owner_id = active_collection_user_id()
    total = CollectionItem.query.join(Game).filter(CollectionItem.status=="owned", CollectionItem.user_id==owner_id, CollectionItem.auto_value_eur.is_(None), Game.physical_status!="excluded").count()
    run = RevaluationRun(source="manual", started_at=utc_now(), total_count=total, state="queued", heartbeat_at=utc_now(), message="Neubewertung wartet auf Start")
    db.session.add(run); db.session.commit(); run_id = run.id

    def worker(app_obj, rid, uid):
        with app_obj.app_context():
            run = db.session.get(RevaluationRun, rid)
            try:
                run.state = "running"; run.message = "Neubewertung läuft"; run.heartbeat_at = utc_now(); db.session.commit()
                items = [i for i in CollectionItem.query.filter_by(status="owned", user_id=uid).filter(CollectionItem.auto_value_eur.is_(None)).order_by(CollectionItem.id).all() if game_is_physical_candidate(i.game)]
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
    recover_stale_revaluation_runs()
    run = RevaluationRun.query.order_by(RevaluationRun.started_at.desc()).first()
    return redirect(url_for("valuation_detail", run_id=run.id)) if run else render_template("valuation.html", run=None, logs=[])

@app.route("/valuation/<int:run_id>")
@login_required
def valuation_detail(run_id):
    recover_stale_revaluation_runs()
    run = db.session.get(RevaluationRun, run_id) or abort(404)
    logs = RevaluationLog.query.filter_by(revaluation_run_id=run.id).order_by(RevaluationLog.position.desc()).limit(250).all()
    return render_template("valuation.html", run=run, logs=logs)

@app.route("/api/valuation/<int:run_id>")
@login_required
def valuation_status_api(run_id):
    recover_stale_revaluation_runs()
    run = db.session.get(RevaluationRun, run_id) or abort(404)
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
    query = PriceActivity.query.join(CollectionItem).filter(CollectionItem.user_id == active_collection_user_id())
    if change in {"up", "down", "same", "new"}:
        query = query.filter(PriceActivity.change_type == change)
    rows = query.order_by(PriceActivity.recorded_at.desc()).limit(300).all()
    return render_template("price_activity.html", rows=rows, change=change)


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
    if valuation == "auto":
        query = query.filter(CollectionItem.auto_value_eur.isnot(None))
    elif valuation == "valued":
        query = query.filter(db.or_(CollectionItem.auto_value_eur.isnot(None), CollectionItem.estimated_value.isnot(None)))
    elif valuation == "no_value":
        query = query.filter(CollectionItem.auto_value_eur.is_(None), CollectionItem.estimated_value.is_(None))
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
    return render_template("collection.html", items=items, status=status, q=q, consoles=Console.query.order_by(Console.name).all(),
                           selected_console=console_id, valuation=valuation, completeness=completeness, selected_franchise=franchise,
                           region=region, sort=sort, view=view, franchises=franchises, regions=regions,
                           completeness_options=completeness_options,
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
    q = ActivityLog.query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    rows = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(rows) > per_page
    return render_template("activity.html", rows=rows[:per_page], page=page, has_next=has_next)


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
    return issues


@app.route("/quality/export.csv")
@login_required
def quality_export_csv():
    rows = [["Typ","ID","Spiel-ID","Titel","Konsole","Fehler","Jahr","Publisher","Serie","Serienstatus","EAN/UPC","Produktcode","Cover-URL","Externe Quelle","Externe ID","Schätzwert EUR","Notizen"]]
    for row in quality_issues():
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
            g.cover_url = (row.get("Cover-URL") or "").strip() or None
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
    priority = {"barcode_duplicate": 0, "external_shared": 1, "series_mismatch": 2, "cover": 3, "external": 4, "identifier": 5, "series_review": 6, "franchise": 7, "year": 8, "publisher": 8, "value": 9, "copy_details": 10}
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
            goal = CollectionGoal(
                name=name, description=request.form.get("description", "").strip() or None,
                goal_type=request.form.get("goal_type", "manual"), target_count=target,
                franchise=request.form.get("franchise", "").strip() or None,
                series_group=request.form.get("series_group", "").strip() or None,
                console_id=request.form.get("console_id", type=int), created_by_user_id=current_user.id,
            )
            db.session.add(goal); db.session.flush()
            log_activity("goal_created", "collection_goal", goal.id, f"Sammlungsziel „{goal.name}“ angelegt.")
            db.session.commit(); flash("Sammlungsziel angelegt.", "success")
        return redirect(url_for("goals"))
    rows = CollectionGoal.query.order_by(CollectionGoal.created_at.desc()).all()
    rendered = [{"goal": g, "progress": goal_progress(g)} for g in rows]
    franchises = [r[0] for r in db.session.query(Game.franchise).filter(Game.franchise.isnot(None), Game.franchise != "").distinct().order_by(Game.franchise).all()]
    series_groups = [r[0] for r in db.session.query(Game.series_group).filter(Game.series_group.isnot(None), Game.series_group != "").distinct().order_by(Game.series_group).all()]
    return render_template("goals.html", rows=rendered, consoles=Console.query.order_by(Console.name).all(), franchises=franchises, series_groups=series_groups)


@app.route("/goals/<int:goal_id>/delete", methods=["POST"])
@login_required
def goal_delete(goal_id):
    goal = db.get_or_404(CollectionGoal, goal_id)
    name = goal.name
    log_activity("goal_deleted", "collection_goal", goal.id, f"Sammlungsziel „{name}“ gelöscht.")
    db.session.delete(goal); db.session.commit(); flash("Sammlungsziel gelöscht.", "success")
    return redirect(url_for("goals"))


@app.route("/price-history")
@login_required
def price_history_page():
    # v0.7.2: the primary graph is the complete shared collection.
    snapshots = CollectionValueSnapshot.query.order_by(CollectionValueSnapshot.recorded_at).all()
    collection_points = [{
        "date": h.recorded_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "value": round(h.total_value_eur, 2),
        "owned": h.owned_count,
        "valued": h.valued_count,
    } for h in snapshots]

    # Ensure a first baseline exists immediately after updating to v0.7.2.
    if not collection_points:
        snap = collection_total_value_snapshot()
        db.session.commit()
        if snap:
            collection_points = [{
                "date": snap.recorded_at.strftime("%Y-%m-%dT%H:%M:%S"),
                "value": round(snap.total_value_eur, 2),
                "owned": snap.owned_count,
                "valued": snap.valued_count,
            }]
    return render_template("price_history.html", collection_points=collection_points)


@app.route("/franchises")
@login_required
def franchises():
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
    latest_series_scan = SeriesScanRun.query.order_by(SeriesScanRun.started_at.desc()).first()
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
    latest_series_scan = SeriesScanRun.query.order_by(SeriesScanRun.started_at.desc()).first()
    return render_template("franchises.html", franchises=data, unassigned=unassigned, standalone=standalone,
                           rawg_enabled=bool(os.environ.get("RAWG_API_KEY", "").strip()), latest_series_scan=latest_series_scan)


@app.route("/franchises/rebuild", methods=["POST"])
@login_required
def franchises_rebuild():
    overwrite_auto = request.form.get("refresh_auto") == "1"
    games_to_check = Game.query.order_by(Game.id).all()
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
    return redirect(url_for("franchises"))


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
        entry.cover_url = row.get("cover_url")
        entry.platforms = ", ".join(row.get("platforms") or []) or None
        entry.series_group, entry.series_generation = classify_series_item(name, row["name"])
    db.session.commit()
    return added, updated, len(discovered)


@app.route("/franchises/scan-all", methods=["POST"])
@login_required
def franchises_scan_all():
    active = SeriesScanRun.query.filter(SeriesScanRun.state.in_(["queued", "running"])).order_by(SeriesScanRun.started_at.desc()).first()
    if active:
        flash("Ein Serienabgleich läuft bereits.", "warning")
        return redirect(url_for("series_scan_detail", run_id=active.id))
    names = {x[0] for x in db.session.query(Game.franchise).filter(Game.franchise.isnot(None), Game.franchise != "").distinct().all()}
    names.update(CURATED_SERIES.keys())
    names = sorted(names, key=str.casefold)
    run = SeriesScanRun(state="queued", total_count=len(names), message="Serienabgleich wartet auf Start")
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
        platform_totals = {}
        item_value = 0.0
        for game in item.get("local_games") or []:
            for copy in collection_items_for(game):
                if copy.status != "owned":
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
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("dashboard"))
    code = clean_barcode(q)
    if code and len(code) in {8, 12, 13} and re.fullmatch(r"[0-9\s-]+", q):
        return redirect(url_for("barcode_lookup", barcode=code))
    like = f"%{q}%"
    local_results = Game.query.filter(db.or_(Game.title.ilike(like), Game.barcode.ilike(like), Game.product_code.ilike(like), Game.edition.ilike(like))).order_by(Game.title).limit(30).all()
    hardware_results = HardwareModel.query.filter(db.or_(HardwareModel.name.ilike(like), HardwareModel.model_number.ilike(like), HardwareModel.revision.ilike(like), HardwareModel.color.ilike(like))).order_by(HardwareModel.name).limit(20).all()
    accessory_results = AccessoryItem.query.filter(db.or_(AccessoryItem.name.ilike(like), AccessoryItem.manufacturer.ilike(like), AccessoryItem.model_number.ilike(like), AccessoryItem.barcode.ilike(like), AccessoryItem.product_code.ilike(like), AccessoryItem.compatibility.ilike(like))).order_by(AccessoryItem.name).limit(20).all()
    online_results = []
    online_status = None
    if not local_results or request.args.get("online") == "1":
        online_results, online_status = search_game_metadata(q)
    return render_template("universal_search.html", query=q, local_results=local_results, hardware_results=hardware_results, accessory_results=accessory_results, online_results=online_results, online_status=online_status)


@app.route("/barcode")
@login_required
def barcode_search():
    code = clean_barcode(request.args.get("barcode"))
    if not code:
        flash("Bitte eine gültige EAN / UPC eingeben.", "warning")
        return redirect(url_for("scanner"))
    return redirect(url_for("barcode_lookup", barcode=code))


@app.route("/scanner")
@login_required
def scanner():
    return render_template("scanner.html")


@app.route("/barcode/<barcode>")
@login_required
def barcode_lookup(barcode):
    code = clean_barcode(barcode)
    matches = Game.query.filter_by(barcode=code).order_by(Game.title).all() if code else []
    accessory_matches = AccessoryItem.query.filter_by(barcode=code).order_by(AccessoryItem.name).all() if code else []
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
                    cover_url=request.form.get("cover_url", "").strip() or None,
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
        cover_url=request.form.get("cover_url", "").strip() or rawg_detail.get("cover_url") or None,
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
            cover_url=request.form.get("cover_url", "").strip() or rawg_detail.get("cover_url") or None,
            external_source=source, external_id=source_id or None,
        )
        db.session.add(game)
        db.session.flush()
    else:
        # Never lose the scanned identifier when enriching an existing external record.
        game.barcode = barcode
        if not game.cover_url:
            game.cover_url = request.form.get("cover_url", "").strip() or rawg_detail.get("cover_url") or None
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
            cover_url=request.form.get("cover_url", "").strip(),
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


@app.route("/import/csv", methods=["GET", "POST"])
@login_required
def import_csv():
    if request.method == "POST":
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            flash("Bitte eine CSV-Datei auswählen.", "danger")
            return redirect(url_for("import_csv"))
        try:
            content = uploaded.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content), delimiter=request.form.get("delimiter", ";"))
            added, skipped = 0, 0
            for row in reader:
                title = (row.get("title") or row.get("Titel") or "").strip()
                console_name = (row.get("console") or row.get("Konsole") or "").strip()
                if not title or not console_name:
                    skipped += 1
                    continue
                console = get_or_create_console(console_name)
                region = (row.get("region") or row.get("Region") or "PAL").strip() or "PAL"
                edition = (row.get("edition") or row.get("Edition") or "Standard").strip() or "Standard"
                exists = Game.query.filter_by(title=title, console_id=console.id, region=region, edition=edition).first()
                if exists:
                    action = request.form.get("duplicate_action", "skip")
                    if action == "copy":
                        db.session.add(CollectionItem(game_id=exists.id, user_id=active_collection_user_id(), status="owned", completeness="Loose", media_present=True))
                        log_activity("copy_added", "collection_item", None, f"{exists.title}: weiteres Exemplar per CSV importiert.")
                        added += 1
                    else:
                        skipped += 1
                    continue
                year = (row.get("release_year") or row.get("Jahr") or "").strip()
                incoming_barcode = clean_barcode(row.get("barcode") or row.get("EAN") or row.get("UPC"))
                barcode_match = Game.query.filter_by(barcode=incoming_barcode).first() if incoming_barcode else None
                if barcode_match:
                    action = request.form.get("duplicate_action", "skip")
                    if action == "copy":
                        db.session.add(CollectionItem(game_id=barcode_match.id, user_id=active_collection_user_id(), status="owned", completeness="Loose", media_present=True))
                        added += 1
                    else:
                        skipped += 1
                    continue
                db.session.add(Game(
                    title=title, console_id=console.id, region=region, edition=edition,
                    release_year=int(year) if year.isdigit() else None,
                    publisher=(row.get("publisher") or row.get("Publisher") or "").strip(),
                    developer=(row.get("developer") or row.get("Developer") or "").strip(),
                    genre=(row.get("genre") or row.get("Genre") or "").strip(),
                    franchise=(row.get("franchise") or row.get("Serie") or "").strip() or None,
                    franchise_source="manual" if (row.get("franchise") or row.get("Serie") or "").strip() else None,
                    series_status="series" if (row.get("franchise") or row.get("Serie") or "").strip() else "unreviewed",
                    barcode=incoming_barcode,
                    product_code=normalize_product_code(row.get("product_code") or row.get("Produktcode") or row.get("ProductCode")),
                    cover_url=(row.get("cover_url") or row.get("Cover") or "").strip(),
                ))
                added += 1
            db.session.commit()
            flash(f"CSV importiert: {added} Spiele hinzugefügt, {skipped} übersprungen.", "success")
        except Exception as exc:
            db.session.rollback()
            flash(f"CSV-Import fehlgeschlagen: {exc}", "danger")
        return redirect(url_for("games"))
    return render_template("import_csv.html")



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


@app.route("/collection/<int:item_id>/quick-edit", methods=["POST"])
@login_required
def collection_quick_edit(item_id):
    item=db.get_or_404(CollectionItem,item_id)
    if item.user_id != active_collection_user_id(): abort(403)
    item.completeness=request.form.get("completeness", item.completeness)
    item.storage_location=request.form.get("storage_location", "").strip() or None
    item.play_status=request.form.get("play_status", item.play_status)
    for field in ("purchase_price", "estimated_value"):
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
      "valued":sum(1 for i in owned if i.auto_value_eur is not None or i.estimated_value is not None),
      "quality":len(quality_issues()), "duplicates":len(duplicate_candidates()),
    }
    stats.update({"barcode_pct":pct(stats["barcode"],stats["games"]),"cover_pct":pct(stats["cover"],stats["games"]),"external_pct":pct(stats["external"],stats["games"]),"franchise_pct":pct(stats["franchise"],stats["games"]),"valued_pct":pct(stats["valued"],stats["copies"])})
    return render_template("data_health.html", stats=stats)


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
    items = CollectionItem.query.join(Game).filter(CollectionItem.user_id == active_collection_user_id()).order_by(Game.title).all()
    if request.method == "POST":
        ids = [int(x) for x in request.form.getlist("item_ids") if x.isdigit()]
        selected = [i for i in items if i.id in ids]
        if not selected:
            flash("Bitte mindestens einen Eintrag auswählen.", "warning")
            return redirect(url_for("collection_bulk"))
        for item in selected:
            if request.form.get("set_status"): item.status = request.form["set_status"]
            if request.form.get("storage_location"): item.storage_location = request.form["storage_location"].strip() or None
            if request.form.get("tags"): item.tags = request.form["tags"].strip() or None
            if request.form.get("play_status"): item.play_status = request.form["play_status"]
            if request.form.get("region"): item.game.region = request.form["region"].strip()
            cid = request.form.get("console_id", type=int)
            if cid: item.game.console_id = cid
            if request.form.get("media_present") in {"yes", "no"}: item.media_present = request.form.get("media_present") == "yes"
            if request.form.get("box_present") in {"yes", "no"}: item.box_present = request.form.get("box_present") == "yes"
            if request.form.get("manual_present") in {"yes", "no"}: item.manual_present = request.form.get("manual_present") == "yes"
            item.completeness = derive_completeness(item.media_present, item.box_present, item.manual_present, item.sealed)
        log_activity("bulk_update", "collection_item", None, f"{len(selected)} Sammlungseinträge gesammelt bearbeitet.", {"ids": ids})
        db.session.commit()
        flash(f"{len(selected)} Einträge aktualisiert.", "success")
        return redirect(url_for("collection_bulk"))
    return render_template("bulk_edit.html", items=items, consoles=Console.query.order_by(Console.name).all())


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


HARDWARE_CLASS_LABELS = {"stationary":"Stationäre Konsole", "handheld":"Handheld", "hybrid":"Hybridkonsole", "mini":"Mini-/Classic-Konsole", "accessory":"Zubehörgerät"}
HARDWARE_COMPONENT_PROFILES = {
 "stationary":[("console","Konsole / Gehäuse",30),("function","Funktion und Laufwerk",25),("controller","Original-Controller",20),("box","OVP und Inlays",12),("power","Netzteil",6),("cables","Bild-/Anschlusskabel",4),("manual","Anleitung und Beilagen",3)],
 "handheld":[("case","Gehäuse",22),("display","Display(s)",22),("function","Funktion / Modulschacht",18),("hinge","Scharnier",10),("controls","Tasten / Steuerkreuz / Circle Pad",12),("stylus","Original-Stylus",4),("battery","Akku",5),("box","OVP und Inlays",5),("power","Netzteil / Ladekabel",2)],
 "hybrid":[("console","Tablet / Konsole",24),("display","Display / Touchscreen",16),("function","Funktion / Modulschacht",15),("controllers","Joy-Cons / Controller",18),("rails","Schienen / Sticks / Tasten",8),("dock","Dockingstation",8),("box","OVP und Inlays",6),("power","Netzteil",3),("cables","HDMI-/Anschlusskabel",2)],
 "mini":[("console","Konsole / Gehäuse",30),("function","Funktion",25),("controllers","Original-Controller",22),("box","OVP und Inlays",12),("power","USB-Netzteil",6),("cables","HDMI-/Anschlusskabel",5)],
 "accessory":[("device","Gerät / Gehäuse",35),("function","Funktion",30),("controls","Tasten / Sticks / Sensoren",20),("box","OVP und Inlays",10),("cables","Kabel / Empfänger / Adapter",5)],
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

def infer_hardware_class(model):
    text_value = _search_text(" ".join(x for x in (model.name, model.console.name if model.console else "") if x))
    if any(x in text_value for x in ("switch", "steam deck", "rog ally")): return "hybrid"
    if any(x in text_value for x in ("game boy", "nintendo ds", "3ds", "2ds", "psp", "vita", "game gear", "pocket", "handheld")): return "handheld"
    if any(x in text_value for x in ("mini", "classic", "playstation tv")): return "mini"
    if any(x in text_value for x in ("controller", "kamera", "camera", "portal", "adapter")): return "accessory"
    return "stationary"

def hardware_class(model):
    value = (model.hardware_class or "").strip()
    return value if value in HARDWARE_COMPONENT_PROFILES else infer_hardware_class(model)

def hardware_components(item):
    try: data = json.loads(item.component_data or "{}")
    except (TypeError, ValueError): data = {}
    return data if isinstance(data, dict) else {}

def component_profile(model):
    name = _search_text(" ".join(x for x in (model.name, model.console.name if model.console else "") if x))
    if "game boy advance sp" in name: profile_key = "gameboy_advance_sp"
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
                   "notes":request.form.get(f"component_{key}_notes","").strip()[:300]}
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
            model = HardwareModel(console_id=console_id, name=name, model_number=request.form.get("model_number", "").strip() or None, revision=request.form.get("revision", "").strip() or None, color=request.form.get("color", "").strip() or None, region=request.form.get("region", "").strip() or None, release_year=request.form.get("release_year", type=int), reference_image=request.form.get("reference_image", "").strip() or None, notes=request.form.get("notes", "").strip() or None, edition=request.form.get("edition", "").strip() or None, hardware_class=request.form.get("hardware_class") if request.form.get("hardware_class") in HARDWARE_COMPONENT_PROFILES else None)
            db.session.add(model); db.session.commit(); flash("Hardware-Modell angelegt.", "success")
        return redirect(url_for("hardware"))
    query = HardwareModel.query.join(Console)
    manufacturer = request.args.get("manufacturer", "").strip(); console_id = request.args.get("console_id", type=int); q = request.args.get("q", "").strip()
    valuation = request.args.get("valuation", "").strip(); sort = request.args.get("sort", "name").strip()
    if manufacturer: query = query.filter(Console.manufacturer == manufacturer)
    if console_id: query = query.filter(HardwareModel.console_id == console_id)
    if q: query = query.filter(db.or_(HardwareModel.name.ilike(f"%{q}%"), HardwareModel.model_number.ilike(f"%{q}%"), HardwareModel.edition.ilike(f"%{q}%")))
    models = query.order_by(Console.manufacturer, Console.name, HardwareModel.name).all()
    now_utc = utc_now()
    catalog_rows = []
    for model in models:
        owned_items = [item for item in model.items if item.status == "owned"]
        valued_items = [item for item in owned_items if item.estimated_value is not None or item.auto_value_eur is not None]
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
    if sort == "value_desc": catalog_rows.sort(key=lambda row: (row["total_value"], row["model"].name.casefold()), reverse=True)
    elif sort == "value_asc": catalog_rows.sort(key=lambda row: (row["total_value"] if row["valued_count"] else float("inf"), row["model"].name.casefold()))
    elif sort == "updated_desc": catalog_rows.sort(key=lambda row: (row["updated_at"] or datetime.min), reverse=True)
    consoles = Console.query.order_by(Console.manufacturer, Console.name).all()
    all_items=HardwareItem.query.all()
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
    failed_logs = RevaluationLog.query.filter(RevaluationLog.status == "Fehler").order_by(RevaluationLog.recorded_at.desc()).limit(100).all()
    hardware_failures = HardwareItem.query.filter(
        HardwareItem.status == "owned", HardwareItem.auto_value_eur.is_(None),
        HardwareItem.auto_value_updated_at.isnot(None)
    ).order_by(HardwareItem.auto_value_updated_at.desc()).limit(100).all()
    return render_template("error_center.html", failed_logs=failed_logs, hardware_failures=hardware_failures)


@app.route("/hardware/<int:model_id>", methods=["GET", "POST"])
@login_required
def hardware_detail(model_id):
    model = db.get_or_404(HardwareModel, model_id)
    if request.method == "POST":
        item = HardwareItem(hardware_model_id=model.id, model=model)
        db.session.add(item)
        apply_hardware_item_form(item)
        db.session.flush()
        item.photo_front = _save_hardware_photo(request.files.get("photo_front"), item.id, "front")
        item.photo_back = _save_hardware_photo(request.files.get("photo_back"), item.id, "back")
        log_activity("hardware_added", "hardware_item", item.id, f"Hardware {model.name} zur Sammlung hinzugefügt.")
        db.session.commit(); flash("Hardware-Exemplar gespeichert.", "success"); return redirect(url_for("hardware_detail", model_id=model.id))
    draft=HardwareItem(hardware_model_id=model.id,condition=8,tested_status="tested")
    defaults={comp["key"]:_legacy_component_default(draft,comp["key"]) for comp in component_profile(model)}
    return render_template("hardware_detail.html", model=model, hardware_class=hardware_class(model), hardware_class_label=HARDWARE_CLASS_LABELS[hardware_class(model)], component_profile=component_profile(model), component_values=defaults)


def derive_hardware_completeness(item):
    model = item.model or db.session.get(HardwareModel, item.hardware_model_id)
    components = hardware_components(item)
    if components:
        present = {key for key,row in components.items() if row.get("availability") == "present"}
        relevant = {key for key,row in components.items() if row.get("availability") != "na"}
        if item.sealed: return "Sealed"
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
    item=db.get_or_404(HardwareItem,item_id)
    if request.method == "POST":
        apply_hardware_item_form(item); db.session.commit(); flash("Hardware-Exemplar aktualisiert.","success")
        return redirect(url_for("hardware_detail",model_id=item.hardware_model_id))
    return render_template("hardware_item_edit.html",item=item, hardware_class=hardware_class(item.model), hardware_class_label=HARDWARE_CLASS_LABELS[hardware_class(item.model)], component_profile=component_profile(item.model), component_values=component_form_values(item))


@app.route("/hardware/items/<int:item_id>/delete", methods=["POST"])
@login_required
def hardware_item_delete(item_id):
    item=db.get_or_404(HardwareItem,item_id); model_id=item.hardware_model_id
    db.session.delete(item); db.session.commit(); flash("Hardware-Exemplar gelöscht. Das Modell bleibt erhalten.","success")
    return redirect(url_for("hardware_detail",model_id=model_id))


@app.route("/hardware/models/<int:model_id>/edit", methods=["GET", "POST"])
@login_required
def hardware_model_edit(model_id):
    model=db.get_or_404(HardwareModel,model_id)
    if request.method == "POST":
        for field in ("name","model_number","revision","color","region","reference_image","notes","edition","pricecharting_url"):
            setattr(model,field,request.form.get(field,"").strip() or None)
        if request.form.get("hardware_class") in HARDWARE_COMPONENT_PROFILES: model.hardware_class=request.form.get("hardware_class")
        if "pricecharting_url" in request.form:
            model.pricecharting_name = request.form.get("pricecharting_name", "").strip() or model.pricecharting_name
        model.release_year=request.form.get("release_year",type=int); db.session.commit(); flash("Hardware-Modell aktualisiert.","success")
        return redirect(url_for("hardware_detail",model_id=model.id))
    targets=HardwareModel.query.filter(HardwareModel.id!=model.id).join(Console).order_by(Console.name,HardwareModel.name).all()
    return render_template("hardware_model_edit.html",model=model,targets=targets,hardware_classes=HARDWARE_CLASS_LABELS,selected_hardware_class=hardware_class(model))


@app.route("/hardware/models/<int:model_id>/merge",methods=["POST"])
@login_required
def hardware_model_merge(model_id):
    source=db.get_or_404(HardwareModel,model_id); target=db.get_or_404(HardwareModel,request.form.get("target_id",type=int))
    if source.id==target.id: abort(400)
    HardwareItem.query.filter_by(hardware_model_id=source.id).update({"hardware_model_id":target.id})
    db.session.delete(source); db.session.commit(); flash("Hardware-Modelle zusammengeführt; alle Exemplare wurden übernommen.","success")
    return redirect(url_for("hardware_detail",model_id=target.id))


@app.route("/hardware/models/<int:model_id>/delete",methods=["POST"])
@login_required
def hardware_model_delete(model_id):
    model=db.get_or_404(HardwareModel,model_id)
    if model.items:
        flash("Das Modell besitzt Exemplare und kann erst nach deren Zuordnung oder Löschung entfernt werden.","warning")
        return redirect(url_for("hardware_model_edit",model_id=model.id))
    db.session.delete(model); db.session.commit(); flash("Hardware-Modell gelöscht.","success")
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
    target=" ".join(x for x in (item.model.name,item.model.edition,item.model.model_number) if x); t=_match_key(target); r=_match_key(row_text)
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
    query=" ".join(x for x in (item.model.name,item.model.edition,item.model.model_number) if x)
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
    item=db.get_or_404(HardwareItem,item_id); ok,status=hardware_auto_value(item)
    if ok: db.session.commit(); flash(f"Hardwarewert aktualisiert: {item.auto_value_eur:.2f} €.","success")
    else: db.session.commit(); flash("Kein ausreichend sicherer Hardware-Preisvergleich gefunden.","warning")
    return redirect(url_for("hardware_detail",model_id=item.hardware_model_id))


@app.route("/hardware/revalue", methods=["POST"])
@login_required
def hardware_revalue_all():
    items=HardwareItem.query.filter_by(status="owned").filter(HardwareItem.auto_value_eur.is_(None)).order_by(HardwareItem.id).all(); valued=0; failed=0
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
    item = db.get_or_404(AccessoryItem, item_id)
    ok, status = accessory_auto_value(item)
    if ok:
        db.session.commit()
        flash(f"Zubehörwert aktualisiert: {item.auto_value_eur:.2f} €.", "success")
    else:
        db.session.commit()
        flash("Kein ausreichend sicherer Zubehör-Preisvergleich gefunden.", "warning")
    return redirect(url_for("accessories"))


@app.route("/accessories/revalue", methods=["POST"])
@login_required

def accessories_revalue_all():
    items = (
        AccessoryItem.query
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
            duplicate = AccessoryItem.query.filter(db.or_(*duplicate_checks)).first() if duplicate_checks else None
            if duplicate and request.form.get("confirm_duplicate") != "1":
                flash(f"Zubehör „{duplicate.name}“ ist mit dieser Kennung bereits vorhanden. Öffne den Treffer oder füge bewusst ein weiteres Exemplar hinzu.", "warning")
                return redirect(url_for("accessory_item_edit", item_id=duplicate.id))
            item=AccessoryItem(name=name, console_id=request.form.get("console_id", type=int), manufacturer=request.form.get("manufacturer", "").strip() or None, model_number=request.form.get("model_number", "").strip() or None, barcode=barcode or None, product_code=product_code, category=request.form.get("category", "other"), compatibility=request.form.get("compatibility", "").strip() or None, original_product=request.form.get("original_product") == "1", component_kind=request.form.get("component_kind", "device"), parent_accessory_id=request.form.get("parent_accessory_id", type=int), included_in_parent_value=request.form.get("included_in_parent_value") == "1", media_present=request.form.get("media_present") == "1", case_present=request.form.get("case_present") == "1", manual_present=request.form.get("manual_present") == "1", disc_condition=request.form.get("disc_condition", type=int), color=request.form.get("color", "").strip() or None, status=request.form.get("status", "owned"), quantity=max(1, request.form.get("quantity", type=int) or 1), condition=request.form.get("condition", type=int) or 8, boxed=request.form.get("boxed") == "1", purchase_price=parse_money_input(request.form.get("purchase_price")), estimated_value=parse_money_input(request.form.get("estimated_value")), storage_location=request.form.get("storage_location", "").strip() or None, reference_image=request.form.get("reference_image", "").strip() or None, notes=request.form.get("notes", "").strip() or None)
            db.session.add(item); db.session.flush()
            item.photo = _save_hardware_photo(request.files.get("photo"), item.id, "accessory")
            db.session.commit(); flash("Zubehör gespeichert.", "success")
        return redirect(request.form.get("return_to") or url_for("accessories"))

    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    console_id = request.args.get("console_id", type=int)
    status = request.args.get("status", "").strip()
    sort = request.args.get("sort", "name")
    query = AccessoryItem.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(AccessoryItem.name.ilike(like), AccessoryItem.manufacturer.ilike(like), AccessoryItem.model_number.ilike(like), AccessoryItem.barcode.ilike(like), AccessoryItem.product_code.ilike(like), AccessoryItem.compatibility.ilike(like)))
    if category:
        query = query.filter(AccessoryItem.category == category)
    if console_id:
        query = query.filter(AccessoryItem.console_id == console_id)
    if status:
        query = query.filter(AccessoryItem.status == status)
    ordering = {
        "value_desc": AccessoryItem.auto_value_eur.desc().nullslast(),
        "condition_desc": AccessoryItem.condition.desc(),
        "newest": AccessoryItem.added_at.desc(),
    }.get(sort, AccessoryItem.name.asc())
    items = query.order_by(ordering, AccessoryItem.name.asc()).all()
    return render_template("accessories.html", items=items, consoles=Console.query.order_by(Console.name).all(), categories=ACCESSORY_CATEGORIES, component_kinds=ACCESSORY_COMPONENT_KINDS, parent_items=AccessoryItem.query.filter(AccessoryItem.parent_accessory_id.is_(None)).order_by(AccessoryItem.name).all(), q=q, selected_category=category, selected_console_id=console_id, selected_status=status, selected_sort=sort)


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
        local_query = AccessoryItem.query.filter(db.or_(AccessoryItem.name.ilike(like), AccessoryItem.manufacturer.ilike(like), AccessoryItem.model_number.ilike(like), AccessoryItem.barcode.ilike(like), AccessoryItem.product_code.ilike(like), AccessoryItem.compatibility.ilike(like)))
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
    existing = AccessoryItem.query.filter(AccessoryItem.name.ilike(name), AccessoryItem.console_id == request.form.get("console_id", type=int)).first()
    if existing:
        flash("Ein gleichnamiger Zubehörtreffer ist bereits vorhanden. Du kannst dort ein weiteres Exemplar erfassen.", "warning")
        return redirect(url_for("accessory_item_edit", item_id=existing.id))
    item = AccessoryItem(name=name, console_id=request.form.get("console_id", type=int), category=request.form.get("category", "other"), manufacturer=request.form.get("manufacturer", "").strip() or None, model_number=request.form.get("model_number", "").strip() or None, reference_image=request.form.get("cover_url", "").strip() or None, status="owned", quantity=1, condition=8, original_product=True, component_kind=request.form.get("component_kind", "device"), notes=(f"Importiert aus eBay Browse API · {source_id}" if source_id else "Importiert aus eBay Browse API"))
    db.session.add(item); db.session.commit()
    flash("Zubehörtreffer angelegt. Jetzt Zustand, Vollständigkeit und Kennungen ergänzen.", "success")
    return redirect(url_for("accessory_item_edit", item_id=item.id))



@app.route("/accessories/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def accessory_item_edit(item_id):
    item = db.get_or_404(AccessoryItem, item_id)

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
                parent_items=AccessoryItem.query.filter(AccessoryItem.id != item.id, AccessoryItem.parent_accessory_id.is_(None)).order_by(AccessoryItem.name).all(),
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
        item.reference_image = (
            request.form.get("reference_image", "").strip() or None
        )
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
        parent_items=AccessoryItem.query.filter(AccessoryItem.id != item.id, AccessoryItem.parent_accessory_id.is_(None)).order_by(AccessoryItem.name).all(),
        return_to=request.args.get("return_to", ""),
    )


@app.route("/accessories/<int:item_id>/delete", methods=["POST"])
@login_required
def accessory_item_delete(item_id):
    item = db.get_or_404(AccessoryItem, item_id)
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
    rows = [["Copy-ID","Titel","Konsole","Region","Sprache","Edition","EAN/UPC","Produktcode","Serienstatus","Serie","Publisher","Developer","Jahr","Status","Vollständigkeit","Kaufpreis EUR","Manueller Schätzwert EUR","Automatischer Marktwert EUR","Effektiver Wert EUR","Preisquelle","Letzte Bewertung","Lagerplatz","Tags","Spielstatus","Notizen"]]
    for i in items:
        rows.append([i.id,i.game.title,i.game.console.name,i.game.region or '',i.game.language or '',i.game.edition or '',i.game.barcode or '',i.game.product_code or '',i.game.series_status or 'unreviewed',i.game.franchise or '',i.game.publisher or '',i.game.developer or '',i.game.release_year or '',i.status,i.completeness,i.purchase_price if i.purchase_price is not None else '',i.estimated_value if i.estimated_value is not None else '',i.auto_value_eur if i.auto_value_eur is not None else '',effective_value(i) if effective_value(i) is not None else '',i.auto_value_source or ('Eigene Schätzung' if i.estimated_value is not None else ''),i.auto_value_updated_at.isoformat() if i.auto_value_updated_at else '',i.storage_location or '',i.tags or '',i.play_status or '',i.notes or ''])
    return _csv_response(rows, f"gamecollector-sammlung-{date.today().isoformat()}.csv")


@app.route("/export/hardware.csv")
@login_required
def export_hardware_csv():
    rows=[["Exemplar-ID","Hersteller","Familie","Modell","Edition","Modellnummer","Revision","Farbe","Region","Status","Vollständigkeit","Funktionsstatus","Konsolenzustand","OVP-Zustand","Controllerzustand","Seriennummer","Netzteil","Kabel","Controller","Anleitung","Inlays","Originalzubehör","Kaufpreis EUR","Eigener Schätzwert EUR","Automatischer Wert EUR","Preisquelle","Bewertungsdatum","Lagerplatz","Firmware","Notizen"]]
    for i in HardwareItem.query.join(HardwareModel).join(Console).order_by(Console.manufacturer,Console.name,HardwareModel.name).all():
        m=i.model; rows.append([i.id,m.console.manufacturer or "",m.console.name,m.name,m.edition or "",m.model_number or "",m.revision or "",m.color or "",m.region or "",i.status,i.completeness or "Loose",i.tested_status,i.condition,i.box_condition if i.boxed else "",i.controller_condition if i.controller_present else "",i.serial_number or "",i.power_supply_present,i.cables_present,i.controller_present,i.manual_present,i.inserts_present,i.original_accessories_present,i.purchase_price if i.purchase_price is not None else "",i.estimated_value if i.estimated_value is not None else "",i.auto_value_eur if i.auto_value_eur is not None else "",i.auto_value_source or "",i.auto_value_updated_at.isoformat() if i.auto_value_updated_at else "",i.storage_location or "",i.firmware or "",i.notes or ""])
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
    rows=[["ID","Name","Konsole","Hersteller","Modellnummer","Farbe","Status","Anzahl","Zustand","OVP","Kaufpreis EUR","Eigener Schätzwert EUR","Automatischer Wert EUR","Effektiver Einzelwert EUR","Preisquelle","Bewertungsdatum","Lagerplatz","Notizen"]]
    for i in AccessoryItem.query.order_by(AccessoryItem.name).all(): rows.append([i.id,i.name,i.console.name if i.console else '',i.manufacturer or '',i.model_number or '',i.color or '',i.status,i.quantity,i.condition,'Ja' if i.boxed else 'Nein',i.purchase_price if i.purchase_price is not None else '',i.estimated_value if i.estimated_value is not None else '',i.auto_value_eur if i.auto_value_eur is not None else '',effective_accessory_value(i) if effective_accessory_value(i) is not None else '',i.auto_value_source or ('Eigene Schätzung' if i.estimated_value is not None else ''),i.auto_value_updated_at.isoformat() if i.auto_value_updated_at else '',i.storage_location or '',i.notes or ''])
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
    coll=[["Copy-ID","Titel","Konsole","Kaufpreis","Manuell","Automatisch","Effektiv","Quelle"]]+[[i.id,i.game.title,i.game.console.name,i.purchase_price or '',i.estimated_value or '',i.auto_value_eur or '',effective_value(i) if effective_value(i) is not None else '',i.auto_value_source or ''] for i in CollectionItem.query.filter_by(user_id=active_collection_user_id()).all()]
    hw=[["ID","Konsole","Modell","Modellnummer","Status","Schätzwert"]]+[[i.id,i.model.console.name,i.model.name,i.model.model_number or '',i.status,i.estimated_value or ''] for i in HardwareItem.query.all()]
    acc=[["ID","Name","Konsole","Status","Anzahl","Schätzwert"]]+[[i.id,i.name,i.console.name if i.console else '',i.status,i.quantity,i.estimated_value or ''] for i in AccessoryItem.query.all()]
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
        payload.append({"copy_id":i.id,"title":i.game.title,"console":i.game.console.name,"region":i.game.region,"status":i.status,"completeness":i.completeness,"purchase_price":i.purchase_price,"value_eur":effective_value(i),"storage_location":i.storage_location,"tags":i.tags,"play_status":i.play_status,"notes":i.notes})
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
        z.writestr("README.txt", f"GameCollector {APP_VERSION} Komplettbackup\nErstellt: {datetime.now().isoformat()}\nEnthält database.sql und uploads/.\n")
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
            db.session.add(CollectionProject(name=name, description=request.form.get("description","").strip() or None, target_query=request.form.get("target_query","").strip() or None, target_count=request.form.get("target_count", type=int)))
            db.session.commit(); flash("Sammlungsprojekt angelegt.", "success")
        return redirect(url_for("collection_projects"))
    projects=CollectionProject.query.order_by(CollectionProject.created_at.desc()).all()
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
    p=db.session.get(CollectionProject,project_id) or abort(404); db.session.delete(p); db.session.commit(); flash("Sammlungsprojekt gelöscht.","success"); return redirect(url_for("collection_projects"))

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
        force_change = os.environ.get("ADMIN_FORCE_PASSWORD_CHANGE", "0").strip().lower() in {"1", "true", "yes", "on"}
        db.session.add(User(username=admin_user, display_name=admin_user, password_hash=generate_password_hash(admin_password), is_admin=True, is_system=False, must_change_password=force_change))
        db.session.commit()
    shared = User.query.filter_by(username=SHARED_COLLECTION_USERNAME).first()
    if not shared:
        shared = User(username=SHARED_COLLECTION_USERNAME, display_name="Gemeinsame Sammlung",
                      password_hash=generate_password_hash(os.urandom(32).hex()), is_admin=False, is_system=True)
        db.session.add(shared)
        db.session.commit()
    ensure_single_shared_collection()
    # Alias collisions must be merged before curated/online series data is
    # touched; otherwise legacy Pokemon/Pokémon rows can violate the unique key.
    repair_v116_franchise_aliases()
    repair_lego_franchise_metadata()
    repair_series_v102_metadata()
    ensure_curated_series_entries()
    repair_series_v103_metadata()
    repair_series_v104_metadata()

import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.app import (
    app, db, CollectionItem, HardwareItem, AccessoryItem, RevaluationRun,
    RevaluationLog, shared_collection_user, auto_value_item,
    hardware_auto_value, accessory_auto_value, collection_total_value_snapshot,
    recover_stale_revaluation_runs, utc_now,
)


def seconds_until_run(hour: int, tz_name: str) -> float:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def run_revaluation():
    with app.app_context():
        recover_stale_revaluation_runs()
        active = RevaluationRun.query.filter(RevaluationRun.state.in_(["queued", "running", "cancel_requested"])).first()
        if active:
            print(f"[scheduler] valuation already active: run {active.id}; skipping", flush=True)
            return
        shared = shared_collection_user()
        if not shared:
            print("[scheduler] Shared collection user not found", flush=True)
            return
        items = CollectionItem.query.filter_by(user_id=shared.id, status="owned").order_by(CollectionItem.id).all()
        hardware_items = HardwareItem.query.filter_by(status="owned").order_by(HardwareItem.id).all()
        accessory_items = AccessoryItem.query.filter_by(status="owned").order_by(AccessoryItem.id).all()
        complete_count = len(items) + len(hardware_items) + len(accessory_items)
        run = RevaluationRun(source="automatic", started_at=utc_now(), state="running", total_count=complete_count, heartbeat_at=utc_now(), message="Automatische Neubewertung läuft")
        db.session.add(run)
        db.session.commit()
        updated = unsupported = failed = 0
        for pos, item in enumerate(items, 1):
            run.current_index = pos
            run.current_title = item.game.title
            run.heartbeat_at = utc_now()
            db.session.commit()
            if run.state == "cancel_requested":
                run.finished_at = utc_now()
                run.success = False
                run.state = "cancelled"
                run.current_title = None
                run.message = "Automatische Neubewertung wurde abgebrochen."
                db.session.commit()
                print("[scheduler] cancelled", flush=True)
                return
            try:
                ok, status = auto_value_item(item, run=run)
                if ok:
                    updated += 1
                elif status in ("unsupported_platform", "no_automatic_price_source", "no_match", "empty", "not_found"):
                    unsupported += 1
                else:
                    failed += 1
                msg = item.auto_value_message or (f"{item.auto_value_eur:.2f} € · {item.auto_value_source}" if ok and item.auto_value_eur is not None else status)
                db.session.add(RevaluationLog(revaluation_run_id=run.id, collection_item_id=item.id, position=pos, title=item.game.title, status="Bewertet" if ok else ("Ohne Quelle" if status in ("unsupported_platform", "no_automatic_price_source", "no_match", "empty", "not_found") else "Fehler"), message=msg))
                run.checked_count = pos
                run.valued_count = updated
                run.unsupported_count = unsupported
                run.failed_count = failed
                # Persist each item separately so one later provider error cannot roll
                # back already completed valuations or activity rows.
                db.session.commit()
            except Exception as exc:
                failed += 1
                print(f"[scheduler] item {item.id}: {exc}", flush=True)
                db.session.rollback()
                run = db.session.get(RevaluationRun, run.id)
                run.checked_count = pos
                run.failed_count = failed
                db.session.add(RevaluationLog(revaluation_run_id=run.id, collection_item_id=item.id, position=pos, title=item.game.title, status="Fehler", message=str(exc)[:300]))
                db.session.commit()
        # A scheduled run deliberately refreshes all owned hardware and accessories,
        # including entries skipped by manual bulk runs because they already had a value.
        for item in hardware_items:
            try:
                ok, _ = hardware_auto_value(item)
                updated += 1 if ok else 0
                failed += 0 if ok else 1
                db.session.commit()
            except Exception as exc:
                failed += 1
                db.session.rollback()
                print(f"[scheduler] hardware {item.id}: {exc}", flush=True)
        for item in accessory_items:
            try:
                ok, _ = accessory_auto_value(item)
                updated += 1 if ok else 0
                failed += 0 if ok else 1
                db.session.commit()
            except Exception as exc:
                failed += 1
                db.session.rollback()
                print(f"[scheduler] accessory {item.id}: {exc}", flush=True)
        collection_total_value_snapshot()
        run.finished_at = utc_now()
        run.success = True
        run.state = "finished"
        run.checked_count = complete_count
        run.valued_count = updated
        run.unsupported_count = unsupported
        run.failed_count = failed
        run.current_title = None
        run.heartbeat_at = utc_now()
        run.message = "Automatische Neubewertung abgeschlossen"
        db.session.commit()
        print(f"[scheduler] done: {complete_count} checked, {updated} valued, {unsupported} without source, {failed} failed", flush=True)


if __name__ == "__main__":
    hour = int(os.environ.get("AUTOMATIC_REVALUE_HOUR", "3"))
    tz_name = os.environ.get("TZ", "Europe/Berlin")
    print(f"[scheduler] automatic valuation enabled daily at {hour:02d}:00 ({tz_name})", flush=True)
    while True:
        wait = seconds_until_run(hour, tz_name)
        print(f"[scheduler] next run in {wait/3600:.2f} h", flush=True)
        time.sleep(wait)
        run_revaluation()

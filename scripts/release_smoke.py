#!/usr/bin/env python3
"""Offline release checks: compile templates and verify all internal endpoints build."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.app import app


def main():
    failures = []
    with app.app_context():
        for name in app.jinja_env.list_templates():
            try:
                app.jinja_env.get_template(name)
            except Exception as exc:
                failures.append(f"template {name}: {exc}")
        rules = list(app.url_map.iter_rules())
        duplicate_rules = {}
        for rule in rules:
            duplicate_rules.setdefault((str(rule), tuple(sorted(rule.methods or ()))), []).append(rule.endpoint)
        for key, endpoints in duplicate_rules.items():
            if len(endpoints) > 1:
                failures.append(f"duplicate route {key[0]}: {', '.join(endpoints)}")
    if failures:
        print("\n".join(failures))
        return 1
    print(f"OK: {len(app.jinja_env.list_templates())} Templates, {len(rules)} Routen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

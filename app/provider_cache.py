"""Shared, short-lived provider metadata cache; inventory is never cached."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


def cached_json(directory, key, fetch, ttl=3600):
    directory = Path(directory)
    target = directory / (hashlib.sha256(key.encode()).hexdigest() + '.json')
    try:
        payload = json.loads(target.read_text())
        age = time.time() - payload['saved_at']
        if 0 <= age < ttl and isinstance(payload['data'], dict):
            return payload['data']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    data = fetch()
    if not isinstance(data, dict):
        return data
    temp = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=directory, delete=False) as file:
            temp = file.name
            json.dump({'saved_at': time.time(), 'data': data}, file)
        os.replace(temp, target)
    except OSError:
        pass
    finally:
        if temp:
            try:
                os.unlink(temp)
            except FileNotFoundError:
                pass
            except OSError:
                pass
    return data

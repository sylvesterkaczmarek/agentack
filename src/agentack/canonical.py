from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import Action


def canonical_json(value: Any) -> str:
    """Serialize JSON data deterministically for security-relevant identity."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def action_hash(action: Action) -> str:
    payload = canonical_json(action.to_dict()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

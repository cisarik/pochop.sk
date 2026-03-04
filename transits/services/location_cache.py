from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from django.db.models import F
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from transits.models import LocationLookupCache

logger = logging.getLogger(__name__)


def _next_local_midnight(now: datetime | None = None) -> datetime:
    now = now or timezone.now()
    local_now = timezone.localtime(now)
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def get_daily_location_cache(lookup_type: str, lookup_key: str) -> dict[str, Any] | None:
    now = timezone.now()
    today_local = timezone.localtime(now).date()

    try:
        item = (
            LocationLookupCache.objects
            .filter(
                lookup_type=lookup_type,
                lookup_key=lookup_key,
                cache_day=today_local,
                expires_at__gt=now,
            )
            .only('id', 'payload_json')
            .first()
        )
        if not item:
            return None

        LocationLookupCache.objects.filter(pk=item.pk).update(
            hits=F('hits') + 1,
            last_served_at=now,
            updated_at=now,
        )
        return item.payload_json if isinstance(item.payload_json, dict) else None
    except (OperationalError, ProgrammingError, Exception) as exc:
        logger.warning('DB location cache read failed [%s]: %s', lookup_type, exc)
        return None


def set_daily_location_cache(
    lookup_type: str,
    lookup_key: str,
    payload_json: dict[str, Any],
    *,
    provider: str = '',
) -> None:
    if not isinstance(payload_json, dict):
        return

    now = timezone.now()
    today_local = timezone.localtime(now).date()
    expires_at = _next_local_midnight(now)
    if expires_at <= now:
        expires_at = now + timedelta(hours=24)

    try:
        LocationLookupCache.objects.update_or_create(
            lookup_type=lookup_type,
            lookup_key=lookup_key,
            cache_day=today_local,
            defaults={
                'provider': str(provider or '').strip(),
                'payload_json': payload_json,
                'last_served_at': now,
                'expires_at': expires_at,
            },
        )
    except (OperationalError, ProgrammingError, Exception) as exc:
        logger.warning('DB location cache write failed [%s]: %s', lookup_type, exc)

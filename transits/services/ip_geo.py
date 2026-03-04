from __future__ import annotations

import ipaddress
import logging
import time
from datetime import timedelta
from hashlib import sha256
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .location_cache import get_daily_location_cache, set_daily_location_cache

logger = logging.getLogger(__name__)

IP_GEO_CACHE_PREFIX = 'geo:ip:v1:'


def _settings_float(name: str, default: float) -> float:
    raw = getattr(settings, name, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _settings_int(name: str, default: int) -> int:
    raw = getattr(settings, name, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _normalize_ip(ip: str) -> str:
    try:
        return str(ipaddress.ip_address(str(ip).strip()))
    except ValueError:
        return ''


def _cache_key_for_ip(ip: str) -> str:
    digest = sha256(ip.encode('utf-8')).hexdigest()
    return f'{IP_GEO_CACHE_PREFIX}{digest}'


def _cache_ttl() -> int:
    now = timezone.now()
    max_ttl = max(60, _settings_int('IP_GEO_CACHE_TTL_SECONDS', 60 * 60 * 24))
    local_now = timezone.localtime(now)
    next_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    daily_ttl = int((next_midnight - local_now).total_seconds())
    return max(60, min(max_ttl, daily_ttl))


def _request_ipapi(ip: str) -> dict[str, Any] | None:
    url_template = str(getattr(settings, 'IP_GEO_URL_TEMPLATE', 'https://ipapi.co/{ip}/json/')).strip()
    if not url_template:
        return None

    url = url_template.format(ip=ip)
    timeout = (
        max(1.0, _settings_float('IP_GEO_CONNECT_TIMEOUT_SECONDS', 3.0)),
        max(1.0, _settings_float('IP_GEO_READ_TIMEOUT_SECONDS', 5.0)),
    )
    max_retries = max(1, _settings_int('IP_GEO_MAX_RETRIES', 3))
    backoff_base = max(0.25, _settings_float('IP_GEO_RETRY_BACKOFF_SECONDS', 1.0))
    user_agent = str(getattr(settings, 'IP_GEO_USER_AGENT', 'pochop.sk-ipgeo/1.0')).strip()

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                url,
                headers={'User-Agent': user_agent, 'Accept': 'application/json'},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            if attempt >= max_retries:
                logger.warning('IP geolocation request failed: %s', exc)
                return None
            time.sleep(backoff_base * (2 ** (attempt - 1)))
            continue

        if response.status_code == 429 or response.status_code >= 500:
            if attempt >= max_retries:
                logger.warning('IP geolocation upstream unavailable (status=%s).', response.status_code)
                return None
            time.sleep(backoff_base * (2 ** (attempt - 1)))
            continue

        if response.status_code >= 400:
            logger.info('IP geolocation returned non-success status=%s', response.status_code)
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        if not isinstance(payload, dict):
            return None
        if payload.get('error'):
            return None
        return payload

    return None


def ip_to_location(ip: str) -> dict[str, Any] | None:
    """Return country/city(/lat/lon) for client IP. Never raises."""
    ip_clean = _normalize_ip(ip)
    if not ip_clean:
        return None

    cache_key = _cache_key_for_ip(ip_clean)
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    db_cached = get_daily_location_cache('ip', cache_key)
    if isinstance(db_cached, dict):
        cache.set(cache_key, db_cached, timeout=_cache_ttl())
        return db_cached

    payload = _request_ipapi(ip_clean)
    if not payload:
        return None

    country = str(payload.get('country_name') or payload.get('country') or '').strip()
    city = str(payload.get('city') or '').strip()
    region = str(payload.get('region') or payload.get('region_name') or '').strip()

    lat_raw = payload.get('latitude', payload.get('lat'))
    lon_raw = payload.get('longitude', payload.get('lon'))
    lat_val: float | None = None
    lon_val: float | None = None

    try:
        if lat_raw is not None and lon_raw is not None:
            lat_val = float(lat_raw)
            lon_val = float(lon_raw)
    except (TypeError, ValueError):
        lat_val = None
        lon_val = None

    if not country and not city and lat_val is None and lon_val is None:
        return None

    result = {
        'country': country,
        'city': city,
        'region': region,
        'lat': lat_val,
        'lon': lon_val,
        'raw': payload,
    }
    set_daily_location_cache('ip', cache_key, result, provider='ipapi')
    cache.set(cache_key, result, timeout=_cache_ttl())
    return result


__all__ = ['ip_to_location']

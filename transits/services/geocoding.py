from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.module_loading import import_string
from geopy.exc import (
    GeocoderQuotaExceeded,
    GeocoderServiceError,
    GeocoderTimedOut,
    GeocoderUnavailable,
)
from geopy.geocoders import Nominatim

from .location_cache import get_daily_location_cache, set_daily_location_cache

logger = logging.getLogger(__name__)

REVERSE_CACHE_PREFIX = 'geo:reverse:v1:'
FORWARD_CACHE_PREFIX = 'geo:forward:v1:'


class GeocodingProvider(Protocol):
    def reverse(self, lat: float, lon: float) -> dict[str, Any] | None:
        ...

    def forward(self, query: str) -> dict[str, Any] | None:
        ...


class _RateGate:
    """Global in-process rate gate to keep at least min-delay between requests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    def wait(self, min_delay_seconds: float) -> None:
        if min_delay_seconds <= 0:
            return

        sleep_for = 0.0
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next_allowed_at - now)
            self._next_allowed_at = max(now, self._next_allowed_at) + min_delay_seconds

        if sleep_for > 0:
            time.sleep(sleep_for)


_RATE_GATE = _RateGate()
_PROVIDER_INSTANCE: GeocodingProvider | None = None
_PROVIDER_LOCK = threading.Lock()


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


def _normalize_space(value: str) -> str:
    return ' '.join(str(value or '').strip().split())


def _normalize_key_part(value: str) -> str:
    return _normalize_space(value).lower()


def build_forward_query(country: str, city: str, region: str | None = None) -> str:
    parts = [_normalize_space(city)]
    region_clean = _normalize_space(region or '')
    if region_clean:
        parts.append(region_clean)
    parts.append(_normalize_space(country))
    return ', '.join([part for part in parts if part])


def _normalize_reverse_coords(lat: float, lon: float, precision: int) -> tuple[str, str]:
    return (f'{float(lat):.{precision}f}', f'{float(lon):.{precision}f}')


def build_reverse_cache_key(lat: float, lon: float, precision: int | None = None) -> str:
    if precision is None:
        precision = _settings_int('GEOCODING_REVERSE_PRECISION', 5)
    lat_key, lon_key = _normalize_reverse_coords(lat, lon, max(1, precision))
    return f'{REVERSE_CACHE_PREFIX}{lat_key}:{lon_key}'


def build_forward_cache_key(query: str) -> str:
    normalized = _normalize_key_part(query)
    digest = sha256(normalized.encode('utf-8')).hexdigest()
    return f'{FORWARD_CACHE_PREFIX}{digest}'


def _city_from_address(address: dict[str, Any]) -> str:
    for key in ('city', 'town', 'village', 'municipality', 'hamlet', 'county'):
        value = _normalize_space(str(address.get(key) or ''))
        if value:
            return value
    return ''


def _region_from_address(address: dict[str, Any]) -> str:
    for key in ('state', 'region', 'county'):
        value = _normalize_space(str(address.get(key) or ''))
        if value:
            return value
    return ''


def _is_retryable_geopy_error(exc: Exception) -> bool:
    if isinstance(exc, (GeocoderTimedOut, GeocoderUnavailable, GeocoderQuotaExceeded)):
        return True

    msg = str(exc).lower()
    if '429' in msg or 'too many requests' in msg:
        return True
    if 'timed out' in msg or 'timeout' in msg:
        return True
    if '503' in msg or '502' in msg or '500' in msg:
        return True
    if 'service unavailable' in msg:
        return True
    return isinstance(exc, GeocoderServiceError)


class NominatimProvider:
    """Default geocoding provider backed by OpenStreetMap Nominatim via geopy."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float,
        min_delay_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
        language: str = 'sk,en',
    ) -> None:
        if not user_agent:
            raise ValueError('GEOCODING_USER_AGENT must not be empty for Nominatim.')

        self._timeout_seconds = max(1.0, float(timeout_seconds))
        self._min_delay_seconds = max(1.0, float(min_delay_seconds))
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.25, float(retry_backoff_seconds))
        self._language = _normalize_space(language) or 'sk,en'
        self._geolocator = Nominatim(
            user_agent=user_agent,
            timeout=self._timeout_seconds,
        )

    def _call_with_retry(self, fn_name: str, *args: Any, **kwargs: Any) -> Any:
        attempt = 0
        while True:
            attempt += 1
            _RATE_GATE.wait(self._min_delay_seconds)
            method = getattr(self._geolocator, fn_name)
            try:
                return method(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                retryable = _is_retryable_geopy_error(exc)
                if (not retryable) or attempt >= self._max_retries:
                    raise
                backoff = self._retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    'Nominatim %s retry %s/%s after error: %s',
                    fn_name,
                    attempt,
                    self._max_retries,
                    exc,
                )
                time.sleep(backoff)

    def reverse(self, lat: float, lon: float) -> dict[str, Any] | None:
        location = self._call_with_retry(
            'reverse',
            (lat, lon),
            exactly_one=True,
            language=self._language,
            addressdetails=True,
            zoom=18,
        )
        if not location:
            return None

        raw = dict(location.raw or {})
        address = raw.get('address') or {}
        if not isinstance(address, dict):
            address = {}

        country = _normalize_space(str(address.get('country') or ''))
        city = _city_from_address(address)
        region = _region_from_address(address)
        postcode = _normalize_space(str(address.get('postcode') or ''))

        return {
            'country': country,
            'city': city,
            'region': region,
            'postcode': postcode,
            'raw': raw,
        }

    def forward(self, query: str) -> dict[str, Any] | None:
        query_clean = _normalize_space(query)
        if not query_clean:
            return None

        location = self._call_with_retry(
            'geocode',
            query_clean,
            exactly_one=True,
            language=self._language,
            addressdetails=True,
        )
        if not location:
            return None

        raw = dict(location.raw or {})
        address = raw.get('address') or {}
        if not isinstance(address, dict):
            address = {}

        country = _normalize_space(str(address.get('country') or ''))
        city = _city_from_address(address)
        region = _region_from_address(address)

        return {
            'lat': float(location.latitude),
            'lon': float(location.longitude),
            'country': country,
            'city': city,
            'region': region,
            'raw': raw,
        }


def _build_default_provider() -> GeocodingProvider:
    provider_class_path = _normalize_space(getattr(settings, 'GEOCODING_PROVIDER_CLASS', ''))

    if provider_class_path:
        provider_class = import_string(provider_class_path)
        return provider_class()

    return NominatimProvider(
        user_agent=_normalize_space(
            getattr(settings, 'GEOCODING_USER_AGENT', 'pochop.sk-geocoder/1.0')
        ),
        timeout_seconds=_settings_float('GEOCODING_TIMEOUT_SECONDS', 5.0),
        min_delay_seconds=_settings_float('GEOCODING_MIN_DELAY_SECONDS', 1.0),
        max_retries=_settings_int('GEOCODING_MAX_RETRIES', 3),
        retry_backoff_seconds=_settings_float('GEOCODING_RETRY_BACKOFF_SECONDS', 1.0),
        language=_normalize_space(getattr(settings, 'GEOCODING_LANGUAGE', 'sk,en')),
    )


def get_geocoding_provider() -> GeocodingProvider:
    global _PROVIDER_INSTANCE

    if _PROVIDER_INSTANCE is not None:
        return _PROVIDER_INSTANCE

    with _PROVIDER_LOCK:
        if _PROVIDER_INSTANCE is None:
            _PROVIDER_INSTANCE = _build_default_provider()
        return _PROVIDER_INSTANCE


def _cache_ttl(now: datetime | None = None) -> int:
    now = now or timezone.now()
    max_ttl = max(60, _settings_int('GEOCODING_CACHE_TTL_SECONDS', 60 * 60 * 24))
    local_now = timezone.localtime(now)
    next_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_midnight = next_midnight + timedelta(days=1)
    daily_ttl = int((next_midnight - local_now).total_seconds())
    return max(60, min(max_ttl, daily_ttl))


def geocode_reverse(lat: float, lon: float) -> dict[str, Any] | None:
    try:
        lat_val = float(lat)
        lon_val = float(lon)
    except (TypeError, ValueError):
        return None

    if not (-90.0 <= lat_val <= 90.0 and -180.0 <= lon_val <= 180.0):
        return None

    cache_key = build_reverse_cache_key(lat_val, lon_val)
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    db_cached = get_daily_location_cache('reverse', cache_key)
    if isinstance(db_cached, dict):
        cache.set(cache_key, db_cached, timeout=_cache_ttl())
        return db_cached

    try:
        payload = get_geocoding_provider().reverse(lat_val, lon_val)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Reverse geocoding failed for lat=%s lon=%s: %s', lat_val, lon_val, exc)
        return None

    if not payload:
        return None

    sanitized = {
        'country': _normalize_space(str(payload.get('country') or '')),
        'city': _normalize_space(str(payload.get('city') or '')),
        'region': _normalize_space(str(payload.get('region') or '')),
        'postcode': _normalize_space(str(payload.get('postcode') or '')),
        'raw': payload.get('raw') if isinstance(payload.get('raw'), dict) else {},
    }
    set_daily_location_cache('reverse', cache_key, sanitized, provider='nominatim')
    cache.set(cache_key, sanitized, timeout=_cache_ttl())
    return sanitized


def geocode_forward(country: str, city: str, region: str | None = None) -> dict[str, Any] | None:
    country_clean = _normalize_space(country)
    city_clean = _normalize_space(city)
    region_clean = _normalize_space(region or '')
    if not country_clean or not city_clean:
        return None

    query = build_forward_query(country_clean, city_clean, region_clean)
    cache_key = build_forward_cache_key(query)
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    db_cached = get_daily_location_cache('forward', cache_key)
    if isinstance(db_cached, dict):
        cache.set(cache_key, db_cached, timeout=_cache_ttl())
        return db_cached

    try:
        payload = get_geocoding_provider().forward(query)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Forward geocoding failed for query=%s: %s', query, exc)
        return None

    if not payload:
        return None

    try:
        lat_val = float(payload.get('lat'))
        lon_val = float(payload.get('lon'))
    except (TypeError, ValueError):
        return None

    sanitized = {
        'lat': lat_val,
        'lon': lon_val,
        'country': _normalize_space(str(payload.get('country') or country_clean)),
        'city': _normalize_space(str(payload.get('city') or city_clean)),
        'region': _normalize_space(str(payload.get('region') or region_clean)),
        'raw': payload.get('raw') if isinstance(payload.get('raw'), dict) else {},
    }
    set_daily_location_cache('forward', cache_key, sanitized, provider='nominatim')
    cache.set(cache_key, sanitized, timeout=_cache_ttl())
    return sanitized


def _reset_provider_for_tests() -> None:
    global _PROVIDER_INSTANCE
    with _PROVIDER_LOCK:
        _PROVIDER_INSTANCE = None


__all__ = [
    'GeocodingProvider',
    'NominatimProvider',
    'build_forward_cache_key',
    'build_forward_query',
    'build_reverse_cache_key',
    'geocode_forward',
    'geocode_reverse',
    'get_geocoding_provider',
]

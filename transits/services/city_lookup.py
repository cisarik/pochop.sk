from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from transits.models import SlovakCity


@dataclass(frozen=True)
class NearestCityResult:
    name: str
    district: str
    lat: float
    lon: float
    distance_km: float

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'district': self.district,
            'lat': self.lat,
            'lon': self.lon,
            'distance_km': self.distance_km,
        }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * (math.sin(dlon / 2) ** 2)
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


def find_nearest_slovak_city(
    lat: float,
    lon: float,
    *,
    max_distance_km: float = 120.0,
) -> dict[str, Any] | None:
    """Find nearest SlovakCity for coordinates.

    Returns None when no city is close enough or inputs are invalid.
    """
    try:
        lat_val = float(lat)
        lon_val = float(lon)
    except (TypeError, ValueError):
        return None

    if not (-90.0 <= lat_val <= 90.0 and -180.0 <= lon_val <= 180.0):
        return None

    lat_delta = max_distance_km / 111.0
    cos_lat = max(0.2, math.cos(math.radians(lat_val)))
    lon_delta = max_distance_km / (111.0 * cos_lat)

    candidates = list(
        SlovakCity.objects.filter(
            lat__gte=lat_val - lat_delta,
            lat__lte=lat_val + lat_delta,
            lon__gte=lon_val - lon_delta,
            lon__lte=lon_val + lon_delta,
        ).only('name', 'district', 'lat', 'lon')
    )
    if not candidates:
        return None

    best: NearestCityResult | None = None
    for city in candidates:
        distance = _haversine_km(lat_val, lon_val, float(city.lat), float(city.lon))
        if best is None or distance < best.distance_km:
            best = NearestCityResult(
                name=str(city.name),
                district=str(city.district or ''),
                lat=float(city.lat),
                lon=float(city.lon),
                distance_km=round(distance, 2),
            )

    if best is None:
        return None
    if best.distance_km > max_distance_km:
        return None
    return best.to_dict()


__all__ = ['find_nearest_slovak_city']


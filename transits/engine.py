"""
Astrologický engine pre výpočet tranzitov pomocou Swiss Ephemeris.
"""

import swisseph as swe
from datetime import datetime, timedelta, date, time
from typing import Optional
import pytz
from timezonefinder import TimezoneFinder

# Inicializácia Swiss Ephemeris
swe.set_ephe_path(None)  # Použije vstavaný moshier ephemeris

# Mapovanie planét
PLANETS = {
    'sun': swe.SUN,
    'moon': swe.MOON,
    'mercury': swe.MERCURY,
    'venus': swe.VENUS,
    'mars': swe.MARS,
    'jupiter': swe.JUPITER,
    'saturn': swe.SATURN,
    'uranus': swe.URANUS,
    'neptune': swe.NEPTUNE,
    'pluto': swe.PLUTO,
}

PLANET_NAMES_SK = {
    'sun': 'Slnko',
    'moon': 'Mesiac',
    'mercury': 'Merkúr',
    'venus': 'Venuša',
    'mars': 'Mars',
    'jupiter': 'Jupiter',
    'saturn': 'Saturn',
    'uranus': 'Urán',
    'neptune': 'Neptún',
    'pluto': 'Pluto',
}

# Aspekty a ich uhly
ASPECTS = {
    'conjunction': 0.0,
    'sextile': 60.0,
    'square': 90.0,
    'trine': 120.0,
    'opposition': 180.0,
}

ASPECT_NAMES_SK = {
    'conjunction': 'konjunkcia',
    'sextile': 'sextil',
    'square': 'kvadratúra',
    'trine': 'trigón',
    'opposition': 'opozícia',
}

# Orby pre tranzitné aspekty (v stupňoch)
TRANSIT_ORBS = {
    'sun': 1.5,
    'moon': 1.5,
    'mercury': 1.0,
    'venus': 1.0,
    'mars': 1.5,
    'jupiter': 2.0,
    'saturn': 2.0,
    'uranus': 2.5,
    'neptune': 2.5,
    'pluto': 2.5,
}

# Priemerná rýchlosť planét (stupne za deň)
PLANET_SPEEDS = {
    'sun': 1.0,
    'moon': 13.0,
    'mercury': 1.2,
    'venus': 1.0,
    'mars': 0.5,
    'jupiter': 0.08,
    'saturn': 0.03,
    'uranus': 0.01,
    'neptune': 0.006,
    'pluto': 0.004,
}


def datetime_to_jd(dt: datetime) -> float:
    """Konvertuje datetime na Julian Day."""
    return swe.julday(
        dt.year, dt.month, dt.day,
        dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    )


def get_planet_position(planet_id: int, jd: float) -> float:
    """Vráti ekliptickú dĺžku planéty pre daný Julian Day."""
    result, flag = swe.calc_ut(jd, planet_id)
    return result[0]


def normalize_angle(angle: float) -> float:
    """Normalizuje uhol do rozsahu 0-360."""
    return angle % 360.0


def angle_diff(a: float, b: float) -> float:
    """Najmenší uhol medzi dvoma pozíciami (0-180)."""
    diff = abs(normalize_angle(a) - normalize_angle(b))
    if diff > 180:
        diff = 360 - diff
    return diff


def check_aspect(transit_pos: float, natal_pos: float, aspect_angle: float, orb: float):
    """
    Skontroluje, či je medzi dvoma pozíciami aspekt.
    Vráti (is_in_orb, actual_orb) alebo (False, None).
    """
    diff = angle_diff(transit_pos, natal_pos)
    actual_orb = abs(diff - aspect_angle)
    if actual_orb <= orb:
        return True, actual_orb
    return False, None


def calculate_natal_positions(
    birth_date: date,
    birth_time: time,
    birth_lat: float,
    birth_lon: float,
    timezone_str: str = 'Europe/Bratislava'
) -> dict:
    """Vypočíta natálne pozície planét."""
    tz = pytz.timezone(timezone_str)
    birth_dt = datetime.combine(birth_date, birth_time)
    birth_dt = tz.localize(birth_dt)
    birth_utc = birth_dt.astimezone(pytz.UTC)
    jd = datetime_to_jd(birth_utc)

    positions = {}
    for key, planet_id in PLANETS.items():
        positions[key] = get_planet_position(planet_id, jd)
    return positions


def _find_exact(planet_id, natal_pos, aspect_angle, jd_start, jd_end, precision=0.001):
    """Nájde presný čas aspektu pomocou bisekcie."""
    def orb_at(jd):
        pos = get_planet_position(planet_id, jd)
        return angle_diff(pos, natal_pos) - aspect_angle

    val_start = orb_at(jd_start)
    val_end = orb_at(jd_end)

    if val_start * val_end > 0:
        # Hľadáme minimum
        min_jd = jd_start
        min_val = abs(val_start)
        steps = 30
        step = (jd_end - jd_start) / steps
        for i in range(steps + 1):
            jd = jd_start + i * step
            val = abs(orb_at(jd))
            if val < min_val:
                min_val = val
                min_jd = jd
        return min_jd if min_val < precision * 5 else None

    jd_low, jd_high = jd_start, jd_end
    for _ in range(60):
        jd_mid = (jd_low + jd_high) / 2
        val_mid = orb_at(jd_mid)
        if abs(val_mid) < precision:
            return jd_mid
        if val_start * val_mid < 0:
            jd_high = jd_mid
        else:
            jd_low = jd_mid
            val_start = val_mid
    return (jd_low + jd_high) / 2


def _find_orb_boundary(planet_id, natal_pos, aspect_angle, orb_limit,
                        jd_ref, direction=1, max_days=90):
    """Nájde hranicu orbu (vstup/výstup)."""
    step = 0.25 * direction
    jd = jd_ref
    max_steps = int(max_days * 4)

    for _ in range(max_steps):
        jd += step
        pos = get_planet_position(planet_id, jd)
        in_orb, _ = check_aspect(pos, natal_pos, aspect_angle, orb_limit)
        if not in_orb:
            # Spresnenie
            jd_fine = jd - step
            fine_step = step / 20
            for _ in range(40):
                jd_fine += fine_step
                pos2 = get_planet_position(planet_id, jd_fine)
                in_orb2, _ = check_aspect(pos2, natal_pos, aspect_angle, orb_limit)
                if not in_orb2:
                    return jd_fine - fine_step
            return jd_fine
    return jd


def jd_to_datetime(jd: float, timezone_str: str = 'Europe/Bratislava') -> datetime:
    """Konvertuje Julian Day na datetime."""
    year, month, day, hour_float = swe.revjul(jd)
    hours = int(hour_float)
    minutes = int((hour_float - hours) * 60)
    seconds = int(((hour_float - hours) * 60 - minutes) * 60)
    dt_utc = datetime(year, month, day, hours, minutes, seconds, tzinfo=pytz.UTC)
    tz = pytz.timezone(timezone_str)
    return dt_utc.astimezone(tz)


def calculate_transits(
    natal_positions: dict,
    target_date: date,
    days_range: int = 30,
    timezone_str: str = 'Europe/Bratislava'
) -> list:
    """
    Skenuje celých days_range dní a nájde všetky tranzity.
    Pre každú kombináciu planéta-aspekt-planéta skenuje deň po dni.
    """
    tz = pytz.timezone(timezone_str)
    start_dt = tz.localize(datetime.combine(target_date, time(0, 0)))
    start_utc = start_dt.astimezone(pytz.UTC)
    jd_start = datetime_to_jd(start_utc)

    # Kľúč pre deduplikáciu tranzitov
    found_transits = {}  # key -> transit_info

    for t_key, t_planet_id in PLANETS.items():
        orb_limit = TRANSIT_ORBS[t_key]
        speed = PLANET_SPEEDS[t_key]

        # Krok skenovania závisí od rýchlosti planéty
        if speed >= 5:  # Mesiac
            scan_step = 0.25  # každých 6 hodín
        elif speed >= 0.5:  # Slnko, Merkúr, Venuša, Mars
            scan_step = 0.5
        elif speed >= 0.05:  # Jupiter, Saturn
            scan_step = 2.0
        else:  # Urán, Neptún, Pluto
            scan_step = 5.0

        for n_key, natal_pos in natal_positions.items():
            for aspect_key, aspect_angle in ASPECTS.items():
                # Skenujeme celý rozsah
                prev_in_orb = False
                transit_start_jd = None
                steps = int(days_range / scan_step) + 1

                for step_i in range(steps + 1):
                    jd = jd_start + step_i * scan_step
                    t_pos = get_planet_position(t_planet_id, jd)
                    in_orb, orb_val = check_aspect(
                        t_pos, natal_pos, aspect_angle, orb_limit
                    )

                    if in_orb and not prev_in_orb:
                        # Vstup do orbu - nájdi presný začiatok
                        transit_start_jd = jd - scan_step
                        # Spresnenie
                        fine_step = scan_step / 20
                        for fi in range(20):
                            jd_f = transit_start_jd + fi * fine_step
                            t_pos_f = get_planet_position(t_planet_id, jd_f)
                            in_f, _ = check_aspect(
                                t_pos_f, natal_pos, aspect_angle, orb_limit
                            )
                            if in_f:
                                transit_start_jd = jd_f
                                break

                    elif not in_orb and prev_in_orb and transit_start_jd is not None:
                        # Výstup z orbu - nájdi presný koniec
                        transit_end_jd = jd
                        fine_step = scan_step / 20
                        for fi in range(20):
                            jd_f = (jd - scan_step) + fi * fine_step
                            t_pos_f = get_planet_position(t_planet_id, jd_f)
                            in_f, _ = check_aspect(
                                t_pos_f, natal_pos, aspect_angle, orb_limit
                            )
                            if not in_f:
                                transit_end_jd = jd_f
                                break

                        _add_transit(
                            found_transits, t_key, t_planet_id, n_key,
                            natal_pos, aspect_key, aspect_angle, orb_limit,
                            transit_start_jd, transit_end_jd,
                            jd_start, days_range, timezone_str, speed
                        )
                        transit_start_jd = None

                    prev_in_orb = in_orb

                # Ak tranzit stále trvá na konci skenovania
                if prev_in_orb and transit_start_jd is not None:
                    # Nájdi koniec za rozsahom
                    end_jd = _find_orb_boundary(
                        t_planet_id, natal_pos, aspect_angle, orb_limit,
                        jd_start + days_range, direction=1,
                        max_days=max(90, orb_limit / max(speed, 0.001) * 2)
                    )
                    _add_transit(
                        found_transits, t_key, t_planet_id, n_key,
                        natal_pos, aspect_key, aspect_angle, orb_limit,
                        transit_start_jd, end_jd,
                        jd_start, days_range, timezone_str, speed
                    )

                # Ak tranzit začal pred začiatkom skenovania
                if not found_transits.get(f"{t_key}_{n_key}_{aspect_key}"):
                    # Skontroluj či je v orbe hneď na začiatku
                    t_pos_0 = get_planet_position(t_planet_id, jd_start)
                    in_orb_0, _ = check_aspect(
                        t_pos_0, natal_pos, aspect_angle, orb_limit
                    )
                    if in_orb_0:
                        start_bound = _find_orb_boundary(
                            t_planet_id, natal_pos, aspect_angle, orb_limit,
                            jd_start, direction=-1,
                            max_days=max(90, orb_limit / max(speed, 0.001) * 2)
                        )
                        end_bound = _find_orb_boundary(
                            t_planet_id, natal_pos, aspect_angle, orb_limit,
                            jd_start, direction=1,
                            max_days=max(90, orb_limit / max(speed, 0.001) * 2)
                        )
                        _add_transit(
                            found_transits, t_key, t_planet_id, n_key,
                            natal_pos, aspect_key, aspect_angle, orb_limit,
                            start_bound, end_bound,
                            jd_start, days_range, timezone_str, speed
                        )

    result = list(found_transits.values())
    result.sort(key=lambda x: x['start_date_iso'])
    return result


def _add_transit(found_transits, t_key, t_planet_id, n_key, natal_pos,
                 aspect_key, aspect_angle, orb_limit,
                 start_jd, end_jd, jd_range_start, days_range,
                 timezone_str, speed):
    """Pridá tranzit do slovníka, ak ešte neexistuje."""
    key = f"{t_key}_{n_key}_{aspect_key}"

    if end_jd <= start_jd:
        end_jd = start_jd + max(0.5, orb_limit / max(speed, 0.001))

    # Nájdi presný aspekt
    exact_jd = _find_exact(t_planet_id, natal_pos, aspect_angle, start_jd, end_jd)

    start_dt = jd_to_datetime(start_jd, timezone_str)
    end_dt = jd_to_datetime(end_jd, timezone_str)
    exact_dt = jd_to_datetime(exact_jd, timezone_str) if exact_jd else None

    # Aktuálny orb (dnes)
    jd_now = jd_range_start + 0.5  # poludnie dnes
    t_pos_now = get_planet_position(t_planet_id, jd_now)
    _, orb_now = check_aspect(t_pos_now, natal_pos, aspect_angle, orb_limit)
    if orb_now is None:
        orb_now = orb_limit
    intensity = max(0.0, 1.0 - (orb_now / orb_limit))

    if aspect_key in ('trine', 'sextile'):
        default_effect = 'positive'
    elif aspect_key in ('square', 'opposition'):
        default_effect = 'negative'
    else:
        default_effect = 'neutral'

    transit_info = {
        'transit_planet': t_key,
        'natal_planet': n_key,
        'aspect': aspect_key,
        'aspect_name_sk': ASPECT_NAMES_SK[aspect_key],
        'transit_planet_name_sk': PLANET_NAMES_SK[t_key],
        'natal_planet_name_sk': PLANET_NAMES_SK[n_key],
        'orb': round(orb_now, 2),
        'orb_limit': orb_limit,
        'exact_date': exact_dt.strftime('%d.%m.%Y %H:%M') if exact_dt else None,
        'exact_date_iso': exact_dt.isoformat() if exact_dt else None,
        'start_date': start_dt.strftime('%d.%m.%Y %H:%M'),
        'start_date_iso': start_dt.isoformat(),
        'end_date': end_dt.strftime('%d.%m.%Y %H:%M'),
        'end_date_iso': end_dt.isoformat(),
        'intensity': round(intensity, 3),
        'default_effect': default_effect,
    }

    # Ak už existuje tranzit pre tento kľúč, ponecháme ten s kratším orbom
    if key in found_transits:
        if found_transits[key]['orb'] <= orb_now:
            return
    found_transits[key] = transit_info


def get_timezone_for_location(lat: float, lon: float) -> str:
    """Nájde časové pásmo pre danú polohu."""
    tf = TimezoneFinder()
    tz = tf.timezone_at(lat=lat, lng=lon)
    return tz or 'Europe/Bratislava'


# ═══════════════════════════════════════════
# Natálny horoskop - kompletná analýza
# ═══════════════════════════════════════════

ZODIAC_SIGNS = [
    ('Baran', '♈'), ('Býk', '♉'), ('Blíženci', '♊'), ('Rak', '♋'),
    ('Lev', '♌'), ('Panna', '♍'), ('Váhy', '♎'), ('Škorpión', '♏'),
    ('Strelec', '♐'), ('Kozorožec', '♑'), ('Vodnár', '♒'), ('Ryby', '♓'),
]

ZODIAC_ELEMENTS = {
    'Baran': 'Oheň', 'Lev': 'Oheň', 'Strelec': 'Oheň',
    'Býk': 'Zem', 'Panna': 'Zem', 'Kozorožec': 'Zem',
    'Blíženci': 'Vzduch', 'Váhy': 'Vzduch', 'Vodnár': 'Vzduch',
    'Rak': 'Voda', 'Škorpión': 'Voda', 'Ryby': 'Voda',
}

ZODIAC_MODALITY = {
    'Baran': 'Kardinálny', 'Rak': 'Kardinálny', 'Váhy': 'Kardinálny', 'Kozorožec': 'Kardinálny',
    'Býk': 'Fixný', 'Lev': 'Fixný', 'Škorpión': 'Fixný', 'Vodnár': 'Fixný',
    'Blíženci': 'Mutabilný', 'Panna': 'Mutabilný', 'Strelec': 'Mutabilný', 'Ryby': 'Mutabilný',
}

# Natálne orby (väčšie než tranzitné)
NATAL_ORBS = {
    'conjunction': 8.0,
    'sextile': 5.0,
    'square': 7.0,
    'trine': 7.0,
    'opposition': 8.0,
}


def longitude_to_sign(lon: float):
    """Konvertuje ekliptickú dĺžku na znamenie a stupeň."""
    lon = normalize_angle(lon)
    sign_idx = int(lon // 30)
    degree = lon % 30
    name, symbol = ZODIAC_SIGNS[sign_idx]
    return {
        'sign': name,
        'symbol': symbol,
        'degree': round(degree, 1),
        'element': ZODIAC_ELEMENTS[name],
        'modality': ZODIAC_MODALITY[name],
    }


def calculate_natal_chart(
    birth_date: date,
    birth_time: time,
    birth_lat: float,
    birth_lon: float,
    timezone_str: str = 'Europe/Bratislava'
) -> dict:
    """
    Vypočíta kompletný natálny horoskop:
    - pozície planét v znameniach
    - ascendent, MC
    - aspekty medzi natálnymi planétami
    - rozloženie elementov a modalít
    """
    tz = pytz.timezone(timezone_str)
    birth_dt = datetime.combine(birth_date, birth_time)
    birth_dt = tz.localize(birth_dt)
    birth_utc = birth_dt.astimezone(pytz.UTC)
    jd = datetime_to_jd(birth_utc)

    # Pozície planét
    planets = {}
    for key, planet_id in PLANETS.items():
        lon = get_planet_position(planet_id, jd)
        sign_info = longitude_to_sign(lon)
        planets[key] = {
            'longitude': round(lon, 2),
            'name_sk': PLANET_NAMES_SK[key],
            **sign_info,
        }

    # Ascendent a MC (domy)
    houses_data = swe.houses(jd, birth_lat, birth_lon, b'P')  # Placidus
    cusps = houses_data[0]    # 12 domov
    ascmc = houses_data[1]    # ASC, MC, ARMC, Vertex, ...

    asc_lon = ascmc[0]
    mc_lon = ascmc[1]
    asc_info = longitude_to_sign(asc_lon)
    mc_info = longitude_to_sign(mc_lon)

    houses = []
    for i, cusp in enumerate(cusps):
        si = longitude_to_sign(cusp)
        houses.append({
            'house': i + 1,
            'cusp': round(cusp, 2),
            'sign': si['sign'],
            'symbol': si['symbol'],
            'degree': si['degree'],
        })

    # Aspekty medzi natálnymi planétami
    planet_keys = list(PLANETS.keys())
    aspects = []
    for i in range(len(planet_keys)):
        for j in range(i + 1, len(planet_keys)):
            p1, p2 = planet_keys[i], planet_keys[j]
            lon1 = planets[p1]['longitude']
            lon2 = planets[p2]['longitude']
            for asp_name, asp_angle in ASPECTS.items():
                orb_limit = NATAL_ORBS[asp_name]
                in_orb, actual_orb = check_aspect(lon1, lon2, asp_angle, orb_limit)
                if in_orb:
                    aspects.append({
                        'planet1': p1,
                        'planet1_sk': planets[p1]['name_sk'],
                        'planet2': p2,
                        'planet2_sk': planets[p2]['name_sk'],
                        'aspect': asp_name,
                        'aspect_sk': ASPECT_NAMES_SK[asp_name],
                        'orb': round(actual_orb, 2),
                    })

    # Rozloženie elementov a modalít
    elements = {'Oheň': 0, 'Zem': 0, 'Vzduch': 0, 'Voda': 0}
    modalities = {'Kardinálny': 0, 'Fixný': 0, 'Mutabilný': 0}
    for p in planets.values():
        elements[p['element']] += 1
        modalities[p['modality']] += 1

    return {
        'planets': planets,
        'ascendant': {'longitude': round(asc_lon, 2), **asc_info},
        'midheaven': {'longitude': round(mc_lon, 2), **mc_info},
        'houses': houses,
        'aspects': aspects,
        'elements': elements,
        'modalities': modalities,
    }

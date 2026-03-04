import logging
from datetime import date, datetime, time

import pytz
import swisseph as swe

from .credits import AICreditLimitExceededError
from .engine import ASPECTS, ASPECT_NAMES_SK, PLANETS, check_aspect, datetime_to_jd, longitude_to_sign
from .gemini_utils import (
    GeminiLimitExceededError,
    generate_gemini_text,
    get_active_model_context,
    get_gemini_model,
    has_ai_key,
)
from .models import ASPECT_SYMBOLS, PLANET_SYMBOLS, MomentReport
from .transit_data import TRANSIT_DATA

logger = logging.getLogger(__name__)

MOMENT_TZ = 'Europe/Bratislava'
MOMENT_LOCATION_NAME = 'Bratislava, Slovensko'
MOMENT_LAT = 48.1486
MOMENT_LON = 17.1077
MOMENT_LOCATION_PRECISION = 4
MOMENT_DEFAULT_LOCATION_KEY = f"{MOMENT_LAT:.{MOMENT_LOCATION_PRECISION}f}:{MOMENT_LON:.{MOMENT_LOCATION_PRECISION}f}"
MOMENT_ASPECT_ORB = 4.0
MOMENT_FALLBACK_ASPECT_TEXT = {
    'conjunction': 'Silná koncentrácia energie - tému treba uchopiť vedome a prakticky.',
    'sextile': 'Podporný aspekt prináša príležitosť, ktorú je dobré aktívne využiť.',
    'square': 'Napätie tlačí na zmenu návykov a konkrétne rozhodnutie.',
    'trine': 'Plynulý tok energie podporuje ľahší progres v tejto oblasti.',
    'opposition': 'Polarita ukazuje dve strany témy - cieľom je nájsť rovnováhu.',
}
MOMENT_ASPECT_TEXT_MAP = {
    (str(transit), str(natal), str(aspect)): str(text).strip()
    for transit, natal, aspect, _effect, text in TRANSIT_DATA
    if str(text or '').strip()
}

MOMENT_SYSTEM_PROMPT = """Si senior astrológ so znalosťou tranzitov, planét, aspektov, uhlov horoskopu a praktickej dennej interpretácie.

PRAVIDLÁ:
- Pracuj striktne s dodanými dátami pre dodanú lokalitu.
- Buď konkrétny, praktický, bez klišé.
- Zohľadni povahu planét, typ aspektov, orb a okamihové uhly (ASC/MC).

VÝSTUP:
- Vráť LEN validný JSON (žiadny markdown, žiadny text navyše).
- Použi štruktúru:
{
  "rating": 1-10 integer,
  "energy": "2-4 vety",
  "themes": ["bod 1", "bod 2", "bod 3"],
  "focus": ["bod 1", "bod 2", "bod 3"],
  "avoid": ["bod 1", "bod 2", "bod 3"]
}
"""


def _has_gemini_key(model_name=None):
    return has_ai_key(model_name=model_name)


def _normalize_moment_model_ref(active_model_ctx):
    provider = str(active_model_ctx.get('provider') or '').strip().lower()
    model = str(active_model_ctx.get('model') or '').strip()
    if provider and model:
        return f"{provider}:{model}"
    return model or provider or 'ai:unknown'


def _attach_runtime_meta(report_obj, *, cache_hit, model_ref, model_ctx):
    report_obj._cache_hit = bool(cache_hit)  # noqa: SLF001 - runtime-only marker for views/templates
    report_obj._active_model_ref = str(model_ref or '').strip()  # noqa: SLF001
    report_obj._active_model_ctx = dict(model_ctx or {})  # noqa: SLF001
    return report_obj


def build_moment_location_payload(
    *,
    lat: float | None = None,
    lon: float | None = None,
    city: str = '',
    country: str = '',
    name: str = '',
    timezone_name: str = MOMENT_TZ,
):
    try:
        lat_val = float(lat) if lat is not None else float(MOMENT_LAT)
        lon_val = float(lon) if lon is not None else float(MOMENT_LON)
    except (TypeError, ValueError):
        lat_val = float(MOMENT_LAT)
        lon_val = float(MOMENT_LON)

    if not (-90.0 <= lat_val <= 90.0):
        lat_val = float(MOMENT_LAT)
    if not (-180.0 <= lon_val <= 180.0):
        lon_val = float(MOMENT_LON)

    city_clean = ' '.join(str(city or '').strip().split())
    country_clean = ' '.join(str(country or '').strip().split())
    name_clean = ' '.join(str(name or '').strip().split())
    if not name_clean:
        if city_clean and country_clean:
            name_clean = f"{city_clean}, {country_clean}"
        elif city_clean:
            name_clean = city_clean
        elif country_clean:
            name_clean = country_clean
        else:
            name_clean = MOMENT_LOCATION_NAME

    location_key = (
        f"{lat_val:.{MOMENT_LOCATION_PRECISION}f}:"
        f"{lon_val:.{MOMENT_LOCATION_PRECISION}f}"
    )

    return {
        'name': name_clean,
        'city': city_clean,
        'country': country_clean,
        'lat': lat_val,
        'lon': lon_val,
        'timezone': timezone_name or MOMENT_TZ,
        'key': location_key,
    }


def _planet_name_sk(key):
    return {
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
    }.get(key, key)


def _lookup_moment_aspect_text(planet1, planet2, aspect_key):
    direct = MOMENT_ASPECT_TEXT_MAP.get((planet1, planet2, aspect_key), '')
    if direct:
        return direct
    reverse = MOMENT_ASPECT_TEXT_MAP.get((planet2, planet1, aspect_key), '')
    if reverse:
        return reverse
    return MOMENT_FALLBACK_ASPECT_TEXT.get(aspect_key, '')


def enrich_moment_aspects_with_text(aspects):
    if not isinstance(aspects, list):
        return []

    enriched = []
    for item in aspects:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        text = str(row.get('text') or '').strip()
        if not text:
            text = _lookup_moment_aspect_text(
                str(row.get('planet1') or '').strip().lower(),
                str(row.get('planet2') or '').strip().lower(),
                str(row.get('aspect') or '').strip().lower(),
            )
        row['text'] = text
        enriched.append(row)
    return enriched


def calculate_moment_snapshot(snapshot_dt=None, timezone=MOMENT_TZ):
    tz = pytz.timezone(timezone)
    if snapshot_dt is None:
        snapshot_dt = datetime.now(tz)
    elif snapshot_dt.tzinfo is None:
        snapshot_dt = tz.localize(snapshot_dt)
    else:
        snapshot_dt = snapshot_dt.astimezone(tz)

    jd = datetime_to_jd(snapshot_dt.astimezone(pytz.UTC))

    planets = []
    for key, planet_id in PLANETS.items():
        result, _ = swe.calc_ut(jd, planet_id)
        lon = result[0]
        lon_speed = result[3]
        sign = longitude_to_sign(lon)
        planets.append({
            'key': key,
            'name_sk': _planet_name_sk(key),
            'symbol': PLANET_SYMBOLS.get(key, ''),
            'longitude': round(lon, 3),
            'longitude_deg': round(lon % 30, 2),
            'sign': sign['sign'],
            'sign_symbol': sign['symbol'],
            'retrograde': lon_speed < 0,
        })

    planets.sort(key=lambda x: x['longitude'])
    return planets


def calculate_moment_angles(snapshot_dt, *, lat=MOMENT_LAT, lon=MOMENT_LON, timezone=MOMENT_TZ):
    tz = pytz.timezone(timezone)
    if snapshot_dt.tzinfo is None:
        snapshot_dt = tz.localize(snapshot_dt)
    else:
        snapshot_dt = snapshot_dt.astimezone(tz)
    jd = datetime_to_jd(snapshot_dt.astimezone(pytz.UTC))
    houses_data = swe.houses(jd, float(lat), float(lon), b'P')
    ascmc = houses_data[1]
    asc_lon = ascmc[0]
    mc_lon = ascmc[1]
    asc_sign = longitude_to_sign(asc_lon)
    mc_sign = longitude_to_sign(mc_lon)
    return {
        'ascendant': {
            'longitude': round(asc_lon, 3),
            'sign': asc_sign['sign'],
            'degree': asc_sign['degree'],
            'symbol': asc_sign['symbol'],
        },
        'midheaven': {
            'longitude': round(mc_lon, 3),
            'sign': mc_sign['sign'],
            'degree': mc_sign['degree'],
            'symbol': mc_sign['symbol'],
        },
    }


def calculate_moment_aspects(planets):
    aspects = []
    for i in range(len(planets)):
        for j in range(i + 1, len(planets)):
            p1 = planets[i]
            p2 = planets[j]
            for asp_key, asp_angle in ASPECTS.items():
                in_orb, orb_val = check_aspect(
                    p1['longitude'],
                    p2['longitude'],
                    asp_angle,
                    MOMENT_ASPECT_ORB,
                )
                if not in_orb:
                    continue
                if asp_key in ('trine', 'sextile'):
                    effect = 'positive'
                elif asp_key in ('square', 'opposition'):
                    effect = 'negative'
                else:
                    effect = 'neutral'
                aspects.append({
                    'planet1': p1['key'],
                    'planet2': p2['key'],
                    'planet1_symbol': p1['symbol'],
                    'planet2_symbol': p2['symbol'],
                    'planet1_name_sk': p1['name_sk'],
                    'planet2_name_sk': p2['name_sk'],
                    'aspect': asp_key,
                    'aspect_symbol': ASPECT_SYMBOLS.get(asp_key, ''),
                    'aspect_name_sk': ASPECT_NAMES_SK.get(asp_key, asp_key),
                    'orb': round(float(orb_val), 2),
                    'effect': effect,
                    'text': _lookup_moment_aspect_text(p1['key'], p2['key'], asp_key),
                })
                break
    aspects.sort(key=lambda x: x['orb'])
    return aspects


def _build_moment_prompt(target_date, planets, aspects, angles, location):
    lines = [
        f"Dátum reportu: {target_date.strftime('%d.%m.%Y')}",
        f"Lokalita: {location['name']} ({location['lat']}, {location['lon']})",
        f"Časové pásmo: {location['timezone']}",
        (
            f"Ascendent okamihu: {angles['ascendant']['degree']}° {angles['ascendant']['sign']} "
            f"{angles['ascendant']['symbol']}; "
            f"MC: {angles['midheaven']['degree']}° {angles['midheaven']['sign']} {angles['midheaven']['symbol']}"
        ),
        "Aktuálne planetárne pozície:",
    ]
    for p in planets:
        retro = " Rx" if p['retrograde'] else ""
        lines.append(
            f"- {p['name_sk']} {p['symbol']} v znamení {p['sign']} {p['sign_symbol']} na {p['longitude_deg']}°{retro}"
        )

    lines.append("")
    lines.append("Kľúčové aspekty:")
    if aspects:
        for a in aspects[:14]:
            lines.append(
                f"- {a['planet1_name_sk']} {a['aspect_name_sk']} {a['planet2_name_sk']} (orb {a['orb']}°)"
            )
    else:
        lines.append("- Dnes nie sú výrazné tesné aspekty.")
    lines.append("")
    lines.append("Vytvor verejný denný rozbor okamihu pre zadanú lokalitu a vráť len validný JSON.")
    return "\n".join(lines)


def _fallback_report(aspects):
    positives = [a for a in aspects if a['effect'] == 'positive']
    negatives = [a for a in aspects if a['effect'] == 'negative']
    score = 6 + min(2, len(positives)) - min(2, len(negatives))
    score = max(2, min(9, score))
    return {
        'rating': score,
        'energy': 'Deň má premenlivé tempo. Najlepšie funguje vedomé plánovanie a realistické očakávania.',
        'themes': [
            'Nastavenie priorít a čistá komunikácia.',
            'Vyvažovanie emócií a pragmatických krokov.',
            'Priebežné úpravy plánov namiesto tvrdého tlačenia.',
        ],
        'focus': [
            'Práca na úlohách s jasným výsledkom.',
            'Rozhovory, ktoré riešia podstatu problému.',
            'Krátke bloky sústredenia a pravidelné pauzy.',
        ],
        'avoid': [
            'Impulzívne rozhodnutia pod tlakom.',
            'Zbytočné konflikty a obrannú komunikáciu.',
            'Preplnený harmonogram bez rezervy.',
        ],
        'raw': '',
    }


def _parse_moment_text_response(text):
    result = {
        'rating': 6,
        'energy': '',
        'themes': [],
        'focus': [],
        'avoid': [],
        'raw': text or '',
    }
    section = None
    for line in (text or '').split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith('HODNOTENIE:'):
            try:
                val = stripped.split(':', 1)[1].strip().split('/')[0]
                result['rating'] = max(1, min(10, int(val)))
            except (ValueError, IndexError):
                pass
            section = None
            continue
        if upper.startswith('ENERGIA OKAMIHU:'):
            section = 'energy'
            continue
        if upper.startswith('HLAVNÉ TÉMY:') or upper.startswith('HLAVNE TEMY:'):
            section = 'themes'
            continue
        if upper.startswith('NA ČO JE VHODNÝ ČAS:') or upper.startswith('NA CO JE VHODNY CAS:'):
            section = 'focus'
            continue
        if upper.startswith('POZOR NA:'):
            section = 'avoid'
            continue

        if stripped.startswith('- '):
            item = stripped[2:].strip()
            if section in ('themes', 'focus', 'avoid'):
                result[section].append(item)
            elif section == 'energy':
                result['energy'] += (item + ' ')
            continue

        if section == 'energy':
            result['energy'] += stripped + ' '

    result['energy'] = result['energy'].strip()
    for key in ('themes', 'focus', 'avoid'):
        result[key] = result[key][:3]
    return result


def _parse_moment_response(payload):
    if not isinstance(payload, dict):
        return _parse_moment_text_response(payload or '')

    result = {
        'rating': 6,
        'energy': (payload.get('energy') or '').strip(),
        'themes': [str(x).strip() for x in (payload.get('themes') or []) if str(x).strip()][:3],
        'focus': [str(x).strip() for x in (payload.get('focus') or []) if str(x).strip()][:3],
        'avoid': [str(x).strip() for x in (payload.get('avoid') or []) if str(x).strip()][:3],
        'raw': payload,
    }
    try:
        result['rating'] = max(1, min(10, int(payload.get('rating', 6))))
    except Exception:
        result['rating'] = 6
    return result


def _generate_ai_moment_report(report_date, planets, aspects, angles, location, model_name=None):
    active_model = get_gemini_model(model_name)
    if not _has_gemini_key(model_name=active_model):
        return _fallback_report(aspects)
    try:
        prompt = _build_moment_prompt(report_date, planets, aspects, angles, location)
        text = generate_gemini_text(
            model_name=active_model,
            contents=prompt,
            system_instruction=MOMENT_SYSTEM_PROMPT,
            temperature=0.55,
            max_output_tokens=700,
            response_mime_type='application/json',
            cache_ttl_seconds=60 * 60 * 24 * 14,
            retries=2,
            timeout_seconds=55,
        )
        from .gemini_utils import parse_json_payload
        payload = parse_json_payload(text)
        parsed = _parse_moment_response(payload if payload is not None else text)
        if not parsed['energy'] or not parsed['focus'] or not parsed['avoid']:
            return _fallback_report(aspects)
        return parsed
    except GeminiLimitExceededError:
        logger.warning("Moment report: denný limit API volaní prekročený.")
        return _fallback_report(aspects)
    except AICreditLimitExceededError:
        logger.warning("Moment report: nedostatok kreditov pre requestové AI volanie.")
        return _fallback_report(aspects)
    except Exception as exc:
        logger.error("Generovanie moment reportu cez AI provider zlyhalo: %s", exc)
        return _fallback_report(aspects)


def get_or_generate_moment_report(
    report_date=None,
    force=False,
    timezone=MOMENT_TZ,
    model_name=None,
    location=None,
):
    tz = pytz.timezone(timezone)
    if report_date is None:
        report_date = datetime.now(tz).date()
    elif isinstance(report_date, datetime):
        report_date = report_date.astimezone(tz).date()
    elif not isinstance(report_date, date):
        raise ValueError("report_date musí byť date alebo datetime")

    active_model = get_gemini_model(model_name)
    active_model_ctx = get_active_model_context(model_name=active_model)
    normalized_model_ref = _normalize_moment_model_ref(active_model_ctx)
    location_payload = build_moment_location_payload(
        lat=(location or {}).get('lat') if isinstance(location, dict) else None,
        lon=(location or {}).get('lon') if isinstance(location, dict) else None,
        city=(location or {}).get('city', '') if isinstance(location, dict) else '',
        country=(location or {}).get('country', '') if isinstance(location, dict) else '',
        name=(location or {}).get('name', '') if isinstance(location, dict) else '',
        timezone_name=timezone,
    )

    if not force:
        existing = MomentReport.objects.filter(
            report_date=report_date,
            model_ref=normalized_model_ref,
            location_key=location_payload['key'],
        ).first()
        if existing:
            return _attach_runtime_meta(
                existing,
                cache_hit=True,
                model_ref=normalized_model_ref,
                model_ctx=active_model_ctx,
            )

    snapshot_dt = tz.localize(datetime.combine(report_date, time(12, 0)))
    planets = calculate_moment_snapshot(snapshot_dt=snapshot_dt, timezone=timezone)
    angles = calculate_moment_angles(
        snapshot_dt=snapshot_dt,
        lat=location_payload['lat'],
        lon=location_payload['lon'],
        timezone=timezone,
    )
    aspects = enrich_moment_aspects_with_text(calculate_moment_aspects(planets))
    ai_report = _generate_ai_moment_report(
        report_date,
        planets,
        aspects,
        angles,
        location_payload,
        model_name=active_model,
    )
    ai_report['location'] = {
        'name': location_payload['name'],
        'lat': location_payload['lat'],
        'lon': location_payload['lon'],
        'timezone': location_payload['timezone'],
    }
    ai_report['angles'] = angles
    ai_report['model_ref'] = normalized_model_ref
    ai_report['ai_model_badge'] = active_model_ctx.get('badge', normalized_model_ref)

    obj, _ = MomentReport.objects.update_or_create(
        report_date=report_date,
        model_ref=normalized_model_ref,
        location_key=location_payload['key'],
        defaults={
            'model_ref': normalized_model_ref,
            'location_key': location_payload['key'],
            'location_name': location_payload['name'],
            'location_lat': location_payload['lat'],
            'location_lon': location_payload['lon'],
            'timezone': timezone,
            'planets_json': planets,
            'aspects_json': aspects,
            'ai_report_json': ai_report,
        },
    )
    return _attach_runtime_meta(
        obj,
        cache_hit=False,
        model_ref=normalized_model_ref,
        model_ctx=active_model_ctx,
    )

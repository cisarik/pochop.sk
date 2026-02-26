from __future__ import annotations

import math
from html import escape
from typing import Iterable, List

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .gemini_utils import get_active_model_context
from .moment_service import MOMENT_LAT, MOMENT_LOCATION_NAME, MOMENT_LON, MOMENT_TZ

SVG_SIGNS = ['\u2648', '\u2649', '\u264A', '\u264B', '\u264C', '\u264D', '\u264E', '\u264F', '\u2650', '\u2651', '\u2652', '\u2653']
SVG_SIGN_COLORS = ['#ff6b8f', '#ff9552', '#ffd166', '#7ed0ff', '#f7cd5d', '#92e58f', '#79f0ce', '#58b9ff', '#8d8aff', '#b699ff', '#c58bff', '#ff88d6']
SVG_ASPECT_COLORS = {
    'positive': 'rgba(102, 255, 195, 0.95)',
    'negative': 'rgba(255, 120, 166, 0.95)',
    'neutral': 'rgba(208, 156, 255, 0.92)',
}
SVG_FONT_STACK = "'Noto Sans Symbols 2','Segoe UI Symbol','Noto Sans Symbols','Arial Unicode MS','DejaVu Sans',sans-serif"


def _normalize_email_list(values: Iterable[str] | None) -> List[str]:
    emails = []
    for value in values or []:
        if not value:
            continue
        for token in str(value).replace(';', ',').split(','):
            email = token.strip()
            if email and '@' in email and email not in emails:
                emails.append(email)
    return emails


def collect_admin_report_recipients(extra: Iterable[str] | None = None) -> List[str]:
    # Nightly report má ísť iba na explicitne nastavený ADMIN_EMAIL.
    admin_email = (getattr(settings, 'ADMIN_EMAIL', '') or '').strip()
    if admin_email and '@' in admin_email:
        return [admin_email]

    # Fallback iba pre manuálny run bez ADMIN_EMAIL.
    return _normalize_email_list(extra)


def _polar_to_xy(angle: float, radius: float, center: float = 310) -> tuple[float, float]:
    rad = (float(angle) - 90.0) * math.pi / 180.0
    return (center + math.cos(rad) * radius, center + math.sin(rad) * radius)


def build_moment_svg(planets: list, aspects: list, size: int = 620) -> str:
    if not planets:
        return ''

    center = size / 2
    r_outer = 276
    r_inner = 214
    r_planet = 188
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 620 620" '
            'role="img" aria-label="Aktualne planetarne usporiadanie" '
            'style="display:block;margin:0 auto;background:transparent;color-scheme:only light;">'
        ),
        (
            '<defs>'
            '<filter id="planetGlow" x="-50%" y="-50%" width="200%" height="200%">'
            '<feGaussianBlur stdDeviation="1.35" result="blur"/>'
            '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
            '</filter>'
            '</defs>'
        ),
        '<circle cx="310" cy="310" r="276" fill="none" stroke="rgba(201,157,255,0.3)" stroke-width="1.3" />',
        '<circle cx="310" cy="310" r="214" fill="none" stroke="rgba(201,157,255,0.18)" stroke-width="1.3" />',
    ]

    for i in range(12):
        angle = i * 30
        x1, y1 = _polar_to_xy(angle, r_inner, center)
        x2, y2 = _polar_to_xy(angle, r_outer, center)
        sx, sy = _polar_to_xy(angle + 15, (r_outer + r_inner) / 2, center)
        parts.append(
            (
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                'stroke="rgba(201,157,255,0.14)" stroke-width="1" />'
            )
        )
        parts.append(
            (
                f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="16" fill="{SVG_SIGN_COLORS[i]}" '
                'fill-opacity="0.08" />'
            )
        )
        parts.append(
            (
                f'<text x="{sx:.2f}" y="{sy + 1:.2f}" fill="{SVG_SIGN_COLORS[i]}" '
                f'font-size="40" font-weight="700" text-anchor="middle" dominant-baseline="middle" font-family="{SVG_FONT_STACK}" '
                f'style="fill:{SVG_SIGN_COLORS[i]} !important;">'
                f'{SVG_SIGNS[i]}</text>'
            )
        )

    by_key = {}
    for p in planets:
        key = p.get('key')
        if key:
            by_key[key] = p

    for a in (aspects or [])[:44]:
        p1 = by_key.get(a.get('planet1'))
        p2 = by_key.get(a.get('planet2'))
        if not p1 or not p2:
            continue
        x1, y1 = _polar_to_xy(p1.get('longitude', 0), r_planet, center)
        x2, y2 = _polar_to_xy(p2.get('longitude', 0), r_planet, center)
        color = SVG_ASPECT_COLORS.get(a.get('effect'), SVG_ASPECT_COLORS['neutral'])
        parts.append(
            (
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                f'stroke="{color}" stroke-width="2.7" stroke-linecap="round" />'
            )
        )

    for p in planets:
        lon = p.get('longitude', 0)
        symbol = escape(str(p.get('symbol', '')))
        x, y = _polar_to_xy(lon, r_planet, center)
        parts.append(
            (
                f'<text x="{x + 0.7:.2f}" y="{y + 1.8:.2f}" fill="rgba(8,6,22,0.88)" font-size="44" font-weight="700" '
                f'text-anchor="middle" dominant-baseline="middle" font-family="{SVG_FONT_STACK}" filter="url(#planetGlow)" '
                'style="fill:rgba(8,6,22,0.88) !important;">'
                f'{symbol}</text>'
                f'<text x="{x:.2f}" y="{y + 1:.2f}" fill="#f6fbff" font-size="44" font-weight="700" '
                f'text-anchor="middle" dominant-baseline="middle" font-family="{SVG_FONT_STACK}" '
                'stroke="rgba(9,6,22,0.92)" stroke-width="1.6" paint-order="stroke" filter="url(#planetGlow)" '
                'style="fill:#f6fbff !important;stroke:rgba(9,6,22,0.92) !important;">'
                f'{symbol}</text>'
            )
        )

    parts.append('</svg>')
    return ''.join(parts)


def send_daily_moment_report_email(*, report, recipients: Iterable[str]) -> int:
    to_emails = _normalize_email_list(recipients)
    if not to_emails:
        return 0

    ai = report.ai_report_json or {}
    aspects = report.aspects_json or []
    active_model = get_active_model_context()

    context = {
        'report': report,
        'ai': ai,
        'aspects': aspects[:10],
        'location_name': MOMENT_LOCATION_NAME,
        'location_lat': MOMENT_LAT,
        'location_lon': MOMENT_LON,
        'location_tz': MOMENT_TZ,
        'active_ai_model_badge': active_model.get('badge', ''),
        'moment_svg_email': build_moment_svg(report.planets_json or [], aspects),
    }

    subject = f"Pochop.sk - Astrologický rozbor okamihu ({report.report_date.strftime('%d.%m.%Y')})"
    text_body = render_to_string('registration/moment_report_daily.txt', context)
    html_body = render_to_string('registration/moment_report_daily.html', context)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to_emails,
    )
    msg.attach_alternative(html_body, 'text/html')
    return msg.send(fail_silently=False)

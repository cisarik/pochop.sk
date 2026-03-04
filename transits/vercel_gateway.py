import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import AIModelOption

logger = logging.getLogger(__name__)

DEFAULT_VERCEL_GATEWAY_BASE_URL = 'https://ai-gateway.vercel.sh/v1'


class VercelGatewaySyncError(RuntimeError):
    """Chyba pri synchronizácii katalógu modelov z Vercel AI Gateway."""


def get_vercel_gateway_api_key():
    return (
        (getattr(settings, 'VERCEL_AI_GATEWAY_API_KEY', '') or '')
        or (getattr(settings, 'AI_GATEWAY_API_KEY', '') or '')
    ).strip()


def get_vercel_gateway_base_url():
    return (getattr(settings, 'VERCEL_AI_GATEWAY_BASE_URL', DEFAULT_VERCEL_GATEWAY_BASE_URL) or DEFAULT_VERCEL_GATEWAY_BASE_URL).strip().rstrip('/')


def _coerce_positive_int(value):
    try:
        num = int(value)
    except Exception:
        return None
    return num if num > 0 else None


def fetch_vercel_models(*, timeout_seconds=20):
    """Načíta aktuálny zoznam modelov z Vercel AI Gateway /v1/models."""
    base_url = get_vercel_gateway_base_url()
    url = f"{base_url}/models"
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'pochop.sk/ai-gateway-sync',
    }
    api_key = get_vercel_gateway_api_key()
    if api_key:
        headers['Authorization'] = f"Bearer {api_key}"

    req = Request(url, headers=headers, method='GET')
    try:
        with urlopen(req, timeout=max(5, int(timeout_seconds))) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
    except HTTPError as exc:
        details = exc.read().decode('utf-8', errors='replace') if hasattr(exc, 'read') else ''
        raise VercelGatewaySyncError(
            f"Vercel AI Gateway HTTP {exc.code}: {details[:280]}"
        ) from exc
    except URLError as exc:
        raise VercelGatewaySyncError(f"Nepodarilo sa pripojiť na Vercel AI Gateway: {exc}") from exc
    except Exception as exc:
        raise VercelGatewaySyncError(f"Neočakávaná chyba pri čítaní Vercel modelov: {exc}") from exc

    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise VercelGatewaySyncError(f"Vercel vrátil neplatný JSON payload: {exc}") from exc

    data = payload.get('data')
    if not isinstance(data, list):
        raise VercelGatewaySyncError("Vercel payload neobsahuje pole `data` s modelmi.")
    return data


def _normalize_vercel_model_item(item):
    model_id = str(item.get('id') or '').strip()
    if not model_id:
        return None

    label = str(item.get('name') or item.get('display_name') or model_id).strip()
    owner = str(item.get('owned_by') or item.get('provider') or '').strip()
    model_type = str(item.get('type') or item.get('modality') or '').strip()
    description = str(item.get('description') or '').strip()
    tags_raw = item.get('tags')
    tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()] if isinstance(tags_raw, list) else []
    pricing = item.get('pricing') if isinstance(item.get('pricing'), dict) else {}
    context_window = _coerce_positive_int(
        item.get('context_window')
        or item.get('contextWindow')
        or item.get('max_context_tokens')
    )
    max_tokens = _coerce_positive_int(
        item.get('max_output_tokens')
        or item.get('max_tokens')
        or item.get('output_token_limit')
    )
    return {
        'model_id': model_id,
        'model_ref': f"vercel:{model_id}",
        'label': label or model_id,
        'owner': owner,
        'model_type': model_type,
        'description': description,
        'tags_json': tags,
        'pricing_json': pricing,
        'context_window': context_window,
        'max_tokens': max_tokens,
        'raw_meta_json': item if isinstance(item, dict) else {},
    }


def sync_vercel_models(
    *,
    disable_missing=True,
    enable_new=False,
    pro_only_for_new=True,
    timeout_seconds=20,
):
    """
    Synchronizuje AIModelOption katalóg z Vercel AI Gateway.

    - Nové modely sa založia s `source=vercel`.
    - Existujúcim modelom zachová admin-toggle polia (`is_enabled`, `is_pro_only`, `sort_order`).
    - Modely chýbajúce v novom katalógu sa voliteľne označia ako nedostupné.
    """
    rows = fetch_vercel_models(timeout_seconds=timeout_seconds)
    normalized = [item for item in (_normalize_vercel_model_item(row) for row in rows) if item]
    now = timezone.now()

    created = 0
    updated = 0
    unchanged = 0
    seen_refs = []

    with transaction.atomic():
        for idx, item in enumerate(normalized):
            model_ref = item['model_ref']
            seen_refs.append(model_ref)
            defaults = {
                'label': item['label'],
                'source': 'vercel',
                'owner': item['owner'],
                'model_type': item['model_type'],
                'context_window': item['context_window'],
                'max_tokens': item['max_tokens'],
                'description': item['description'],
                'tags_json': item['tags_json'],
                'pricing_json': item['pricing_json'],
                'raw_meta_json': item['raw_meta_json'],
                'is_available': True,
                'last_synced_at': now,
                'sort_order': 1000 + idx,
                'is_enabled': bool(enable_new),
                'is_pro_only': bool(pro_only_for_new),
            }
            obj, was_created = AIModelOption.objects.get_or_create(
                model_ref=model_ref,
                defaults=defaults,
            )
            if was_created:
                created += 1
                continue

            update_fields = []
            for field in (
                'label',
                'source',
                'owner',
                'model_type',
                'context_window',
                'max_tokens',
                'description',
                'tags_json',
                'pricing_json',
                'raw_meta_json',
                'is_available',
                'last_synced_at',
            ):
                new_val = defaults[field]
                if getattr(obj, field) != new_val:
                    setattr(obj, field, new_val)
                    update_fields.append(field)
            if update_fields:
                obj.save(update_fields=update_fields + ['updated_at'])
                updated += 1
            else:
                unchanged += 1

        missing_count = 0
        if disable_missing:
            missing_qs = AIModelOption.objects.filter(source='vercel').exclude(model_ref__in=seen_refs)
            missing_count = missing_qs.count()
            if missing_count:
                missing_qs.update(
                    is_available=False,
                    is_enabled=False,
                    last_synced_at=now,
                    updated_at=now,
                )
        else:
            missing_count = AIModelOption.objects.filter(source='vercel').exclude(model_ref__in=seen_refs).count()

    result = {
        'total_remote': len(normalized),
        'created': created,
        'updated': updated,
        'unchanged': unchanged,
        'missing': missing_count,
        'seen_refs': seen_refs,
    }
    logger.info("Vercel model sync done: %s", result)
    return result

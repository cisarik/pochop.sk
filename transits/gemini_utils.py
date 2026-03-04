import json
import re
import time
import hashlib
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone


SUPPORTED_AI_PROVIDERS = ('gemini', 'openai', 'vercel')


class AILimitExceededError(Exception):
    pass


# Backward compatibility for existing imports.
GeminiLimitExceededError = AILimitExceededError


def _is_provider_quota_error(exc):
    """Detekcia provider-level quota/rate-limit chýb (429/RESOURCE_EXHAUSTED)."""
    msg = str(exc or '').strip().lower()
    if not msg:
        return False

    strong_markers = (
        'resource_exhausted',
        'insufficient_quota',
    )
    if any(marker in msg for marker in strong_markers):
        return True

    quota_markers = (
        'quota',
        'rate limit',
        'too many requests',
        'billing hard limit',
    )
    if any(marker in msg for marker in quota_markers):
        return True

    if '429' in msg and ('exceeded' in msg or 'limit' in msg):
        return True
    return False


def _normalize_cache_value(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        except Exception:
            return str(value)
    return str(value)


def _build_ai_cache_key(
    *,
    provider,
    model_name,
    contents,
    system_instruction,
    temperature,
    max_output_tokens,
    response_mime_type,
    response_schema,
):
    try:
        temp_val = float(temperature)
    except Exception:
        temp_val = 0.0
    try:
        max_tokens_val = int(max_output_tokens)
    except Exception:
        max_tokens_val = 0

    payload = {
        'provider': (provider or '').strip().lower(),
        'model': (model_name or '').strip().lower(),
        'contents': _normalize_cache_value(contents),
        'system_instruction': _normalize_cache_value(system_instruction),
        'temperature': temp_val,
        'max_output_tokens': max_tokens_val,
        'response_mime_type': _normalize_cache_value(response_mime_type),
        'response_schema': _normalize_cache_value(response_schema),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _resolve_cache_ttl_seconds(cache_ttl_seconds):
    if cache_ttl_seconds is None:
        cache_ttl_seconds = getattr(settings, 'AI_RESPONSE_CACHE_TTL_SECONDS', 86400)
    try:
        return max(0, int(cache_ttl_seconds))
    except Exception:
        return 0


def _is_cache_enabled(ttl_seconds):
    if ttl_seconds <= 0:
        return False
    return bool(getattr(settings, 'AI_RESPONSE_CACHE_ENABLED', True))


def _get_cached_ai_response(cache_key):
    try:
        from .models import AIResponseCache

        now = timezone.now()
        item = (
            AIResponseCache.objects
            .filter(cache_key=cache_key, expires_at__gt=now)
            .only('id', 'response_text', 'hits')
            .first()
        )
        if not item:
            return ''
        AIResponseCache.objects.filter(pk=item.pk).update(
            hits=item.hits + 1,
            updated_at=now,
        )
        return (item.response_text or '').strip()
    except (OperationalError, ProgrammingError):
        return ''
    except Exception:
        return ''


def _store_cached_ai_response(cache_key, provider, model_name, text, ttl_seconds):
    if not text:
        return
    try:
        from .models import AIResponseCache

        now = timezone.now()
        AIResponseCache.objects.update_or_create(
            cache_key=cache_key,
            defaults={
                'provider': (provider or '').strip().lower(),
                'model_name': (model_name or '').strip(),
                'response_text': text,
                'expires_at': now + timedelta(seconds=ttl_seconds),
            },
        )
    except (OperationalError, ProgrammingError):
        return
    except Exception:
        return


def _get_admin_config():
    try:
        from .models import GeminiConfig
        return GeminiConfig.objects.order_by('-updated_at').first()
    except Exception:
        return None


def get_default_model(model_name=None):
    if model_name:
        return str(model_name).strip()
    cfg = _get_admin_config()
    if cfg and cfg.default_model:
        return cfg.default_model.strip()
    return getattr(
        settings,
        'DEFAULT_MODEL',
        getattr(settings, 'VERCEL_AI_GATEWAY_DEFAULT_MODEL', 'openai/gpt-4o-mini'),
    ).strip()


def _as_vercel_model_ref(provider, model_name):
    provider_clean = (provider or '').strip().lower()
    model_clean = (model_name or '').strip()
    if not model_clean:
        return ''
    if provider_clean == 'vercel':
        return model_clean
    if '/' in model_clean and provider_clean in ('openai', 'gemini', 'google', 'anthropic', 'xai', 'mistral', 'meta'):
        return model_clean
    if provider_clean in ('gemini', 'google'):
        return f"google/{model_clean}"
    if provider_clean in ('openai', 'chatgpt'):
        return f"openai/{model_clean}"
    if provider_clean:
        return f"{provider_clean}/{model_clean}"
    return model_clean


def _resolve_provider_and_model(model_name=None):
    raw = get_default_model(model_name)
    cleaned = (raw or '').strip()
    if not cleaned:
        cleaned = getattr(settings, 'VERCEL_AI_GATEWAY_DEFAULT_MODEL', 'openai/gpt-4o-mini').strip()
    lower = cleaned.lower()
    force_vercel = bool(getattr(settings, 'AI_FORCE_VERCEL_GATEWAY', False))

    # Explicit provider prefix: openai:gpt-5.2, gemini:gemini-2.5-pro, vercel:openai/gpt-5.2
    if ':' in cleaned:
        provider_hint, explicit_model = cleaned.split(':', 1)
        provider = provider_hint.strip().lower()
        explicit_model = explicit_model.strip()
        if provider in SUPPORTED_AI_PROVIDERS and explicit_model:
            if force_vercel and provider != 'vercel':
                forced_model = _as_vercel_model_ref(provider, explicit_model)
                if forced_model:
                    return 'vercel', forced_model
            return provider, explicit_model

    # Provider aliases always resolve to gateway default model.
    if lower in ('gemini', 'google'):
        model_val = getattr(settings, 'VERCEL_AI_GATEWAY_DEFAULT_MODEL', 'openai/gpt-4o-mini').strip()
        return 'vercel', _as_vercel_model_ref('gemini', model_val)
    if lower in ('openai', 'chatgpt'):
        model_val = getattr(settings, 'VERCEL_AI_GATEWAY_DEFAULT_MODEL', 'openai/gpt-4o-mini').strip()
        return 'vercel', _as_vercel_model_ref('openai', model_val)
    if lower in ('vercel', 'gateway', 'ai-gateway'):
        return 'vercel', getattr(settings, 'VERCEL_AI_GATEWAY_DEFAULT_MODEL', 'openai/gpt-4o-mini').strip()

    # Gateway route style (owner/model).
    if '/' in cleaned:
        owner_hint, model_hint = cleaned.split('/', 1)
        owner_hint = owner_hint.strip().lower()
        model_hint = model_hint.strip()
        if owner_hint in ('openai', 'google', 'gemini', 'anthropic', 'xai', 'mistral', 'meta'):
            if owner_hint in ('openai',):
                return 'openai', model_hint
            if owner_hint in ('google', 'gemini'):
                return 'gemini', model_hint
            return 'vercel', cleaned

    # Heuristics by model naming for legacy refs.
    if lower.startswith('gemini'):
        if force_vercel:
            return 'vercel', _as_vercel_model_ref('gemini', cleaned)
        return 'gemini', cleaned
    if lower.startswith(('gpt-', 'o1', 'o3', 'o4', 'gpt4', 'gpt-4', 'gpt-5')):
        if force_vercel:
            return 'vercel', _as_vercel_model_ref('openai', cleaned)
        return 'openai', cleaned

    # Default to Vercel route.
    if force_vercel:
        forced_model = _as_vercel_model_ref('vercel', cleaned)
        if forced_model:
            return 'vercel', forced_model
    return 'vercel', cleaned


def get_active_model_context(model_name=None):
    provider, resolved_model = _resolve_provider_and_model(model_name=model_name)
    provider_label = 'Vercel AI Gateway'
    model_display = (resolved_model or '').strip()

    # Avoid duplicate provider text in badge.
    if model_display.lower().startswith(provider_label.lower()):
        badge = model_display
    else:
        badge = f"{provider_label} {model_display}".strip()

    return {
        'provider': provider,
        'provider_label': provider_label,
        'model': model_display,
        'badge': badge,
    }


def get_provider_api_key(provider):
    del provider
    return (
        (getattr(settings, 'VERCEL_AI_GATEWAY_API_KEY', '') or '')
        or (getattr(settings, 'AI_GATEWAY_API_KEY', '') or '')
    ).strip()


def has_ai_key(model_name=None):
    del model_name
    key = get_provider_api_key('vercel')
    if not key:
        return False
    placeholder_values = {
        'your-vercel-ai-gateway-api-key-here',
        'change-me',
    }
    return key not in placeholder_values


def get_ai_max_calls_daily():
    cfg = _get_admin_config()
    if cfg and cfg.max_calls_daily:
        return int(cfg.max_calls_daily)
    return int(getattr(settings, 'AI_MAX_CALLS_DAILY', 500))


def get_today_usage():
    from .models import GeminiDailyUsage

    usage, _ = GeminiDailyUsage.objects.get_or_create(
        usage_date=date.today(),
        defaults={'calls_made': 0},
    )
    return usage


def is_daily_limit_exceeded():
    usage = get_today_usage()
    return usage.calls_made >= get_ai_max_calls_daily()


def reserve_ai_call():
    """Atómovo navýši denný counter alebo vyhodí limit error."""
    from .models import GeminiDailyUsage

    with transaction.atomic():
        usage, _ = GeminiDailyUsage.objects.select_for_update().get_or_create(
            usage_date=date.today(),
            defaults={'calls_made': 0},
        )
        limit = get_ai_max_calls_daily()
        if usage.calls_made >= limit:
            raise AILimitExceededError(
                f"Denný limit AI API volaní ({limit}) bol prekročený."
            )
        usage.calls_made += 1
        usage.save(update_fields=['calls_made', 'updated_at'])
    return usage.calls_made, limit


def _generate_with_openai(
    *,
    api_key,
    model_name,
    base_url=None,
    contents,
    system_instruction,
    temperature,
    max_output_tokens,
    response_mime_type,
    timeout_seconds,
):
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError(
            "OpenAI SDK nie je nainštalovaný. Doinštaluj balík `openai`."
        ) from exc

    kwargs_client = {'api_key': api_key, 'timeout': timeout_seconds}
    if base_url:
        kwargs_client['base_url'] = base_url
    client = OpenAI(**kwargs_client)
    kwargs = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': system_instruction},
            {'role': 'user', 'content': contents},
        ],
        'temperature': temperature,
        'max_completion_tokens': max_output_tokens,
    }
    if response_mime_type == 'application/json':
        kwargs['response_format'] = {'type': 'json_object'}

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        msg = str(exc).lower()
        # Compatibility fallback for models that still expect max_tokens.
        if 'max_completion_tokens' in msg and 'unsupported' in msg:
            kwargs.pop('max_completion_tokens', None)
            kwargs['max_tokens'] = max_output_tokens
            response = client.chat.completions.create(**kwargs)
        # Some reasoning models ignore temperature.
        elif 'temperature' in msg and 'unsupported' in msg:
            kwargs.pop('temperature', None)
            response = client.chat.completions.create(**kwargs)
        # Some gateway-routed models reject response_format=json_object.
        elif 'response_format' in msg:
            kwargs.pop('response_format', None)
            response = client.chat.completions.create(**kwargs)
        else:
            raise
    choices = getattr(response, 'choices', None) or []
    if not choices:
        return ''
    message = getattr(choices[0], 'message', None)
    if not message:
        return ''
    content = getattr(message, 'content', '')
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                parts.append(item.get('text', ''))
        return ''.join(parts).strip()
    return ''


def generate_ai_text(
    *,
    contents,
    system_instruction,
    temperature=0.7,
    max_output_tokens=800,
    model_name=None,
    api_key=None,
    response_mime_type=None,
    response_schema=None,
    cache_ttl_seconds=None,
    retries=2,
    timeout_seconds=45,
):
    """Jednotný wrapper na AI volanie (transport cez Vercel AI Gateway)."""
    provider, resolved_model = _resolve_provider_and_model(model_name=model_name)
    gateway_model = _as_vercel_model_ref(provider, resolved_model)
    resolved_api_key = (api_key or '').strip() or get_provider_api_key('vercel')
    if not resolved_api_key:
        raise RuntimeError("API key pre Vercel AI Gateway nie je nastavený.")

    ttl_seconds = _resolve_cache_ttl_seconds(cache_ttl_seconds)
    cache_enabled = _is_cache_enabled(ttl_seconds)
    cache_key = ''
    if cache_enabled:
        cache_key = _build_ai_cache_key(
            provider='vercel',
            model_name=gateway_model,
            contents=contents,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type=response_mime_type,
            response_schema=response_schema,
        )
        cached_text = _get_cached_ai_response(cache_key)
        if cached_text:
            return cached_text

    last_text = ""
    last_exc = None
    attempts = max(1, retries)
    for attempt in range(attempts):
        reserve_ai_call()
        try:
            base_url = (
                getattr(settings, 'VERCEL_AI_GATEWAY_BASE_URL', 'https://ai-gateway.vercel.sh/v1')
                or 'https://ai-gateway.vercel.sh/v1'
            ).strip()
            text = _generate_with_openai(
                api_key=resolved_api_key,
                model_name=gateway_model,
                base_url=base_url.rstrip('/'),
                contents=contents,
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type=response_mime_type,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            if _is_provider_quota_error(exc):
                raise AILimitExceededError(
                    'Externý AI provider momentálne hlási vyčerpanú kvótu (429).'
                ) from exc
            last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise

        text = (text or '').strip()
        if text:
            if cache_enabled and cache_key:
                _store_cached_ai_response(
                    cache_key,
                    provider='vercel',
                    model_name=gateway_model,
                    text=text,
                    ttl_seconds=ttl_seconds,
                )
            return text
        last_text = text
        if attempt + 1 < attempts:
            time.sleep(0.2 * (attempt + 1))

    if last_exc:
        raise last_exc
    return last_text


# Backward-compatible function names used across the current codebase.
def get_gemini_model(model_name=None):
    return get_default_model(model_name=model_name)


def get_gemini_api_key(api_key=None):
    return (api_key or '').strip() or get_provider_api_key('vercel')


def get_gemini_max_calls_daily():
    return get_ai_max_calls_daily()


def has_gemini_key():
    # Legacy name, but now checks key for currently active default model.
    return has_ai_key()


def reserve_gemini_call():
    return reserve_ai_call()


def generate_gemini_text(
    *,
    contents,
    system_instruction,
    temperature=0.7,
    max_output_tokens=800,
    model_name=None,
    api_key=None,
    response_mime_type=None,
    response_schema=None,
    cache_ttl_seconds=None,
    retries=2,
    timeout_seconds=45,
):
    return generate_ai_text(
        contents=contents,
        system_instruction=system_instruction,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        model_name=model_name,
        api_key=api_key,
        response_mime_type=response_mime_type,
        response_schema=response_schema,
        cache_ttl_seconds=cache_ttl_seconds,
        retries=retries,
        timeout_seconds=timeout_seconds,
    )


def parse_json_payload(text):
    """Skúsi vytiahnuť JSON objekt/pole aj z textu s code-fence obalom."""
    if not text:
        return None
    raw = text.strip()

    # Priamy parse
    try:
        return json.loads(raw)
    except Exception:
        pass

    # ```json ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.S | re.I)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass

    # Prvý JSON-like blok
    for pattern in (r"(\{.*\})", r"(\[.*\])"):
        m = re.search(pattern, raw, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                continue
    return None

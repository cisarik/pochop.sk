import json
import re
import time
import hashlib
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone


SUPPORTED_AI_PROVIDERS = ('gemini', 'openai')


class AILimitExceededError(Exception):
    pass


# Backward compatibility for existing imports.
GeminiLimitExceededError = AILimitExceededError


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
    return getattr(settings, 'DEFAULT_MODEL', getattr(settings, 'GEMINI_MODEL', 'gemini-3.1-pro-preview')).strip()


def _resolve_provider_and_model(model_name=None):
    raw = get_default_model(model_name)
    cleaned = (raw or '').strip()
    if not cleaned:
        cleaned = getattr(settings, 'GEMINI_MODEL', 'gemini-3.1-pro-preview').strip()
    lower = cleaned.lower()

    # Explicit provider prefix: openai:gpt-4.1-mini, gemini:gemini-3.1-pro-preview
    if ':' in cleaned:
        provider_hint, explicit_model = cleaned.split(':', 1)
        provider = provider_hint.strip().lower()
        explicit_model = explicit_model.strip()
        if provider in SUPPORTED_AI_PROVIDERS and explicit_model:
            return provider, explicit_model

    # Provider aliases.
    if lower in ('gemini', 'google'):
        return 'gemini', getattr(settings, 'GEMINI_MODEL', 'gemini-3.1-pro-preview').strip()
    if lower in ('openai', 'chatgpt'):
        return 'openai', getattr(settings, 'OPENAI_MODEL', 'gpt-4.1-mini').strip()

    # Heuristics by model naming.
    if lower.startswith('gemini'):
        return 'gemini', cleaned
    if lower.startswith(('gpt-', 'o1', 'o3', 'o4', 'gpt4', 'gpt-4', 'gpt-5')):
        return 'openai', cleaned

    default_provider = (getattr(settings, 'DEFAULT_PROVIDER', 'gemini') or 'gemini').strip().lower()
    if default_provider not in SUPPORTED_AI_PROVIDERS:
        default_provider = 'gemini'
    return default_provider, cleaned


def get_active_model_context(model_name=None):
    provider, resolved_model = _resolve_provider_and_model(model_name=model_name)
    provider_label = 'OpenAI' if provider == 'openai' else 'Gemini'
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
    provider = (provider or '').strip().lower()
    if provider == 'openai':
        return (getattr(settings, 'OPENAI_API_KEY', '') or '').strip()
    return (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()


def has_ai_key(model_name=None):
    provider, _ = _resolve_provider_and_model(model_name=model_name)
    key = get_provider_api_key(provider)
    if not key:
        return False
    placeholder_values = {
        'your-gemini-api-key-here',
        'your-openai-api-key-here',
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


def _generate_with_gemini(
    *,
    api_key,
    model_name,
    contents,
    system_instruction,
    temperature,
    max_output_tokens,
    response_mime_type,
    response_schema,
    timeout_seconds,
):
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key,
        # google.genai HttpOptions.timeout je v milisekundách.
        http_options=types.HttpOptions(timeout=int(max(10, timeout_seconds) * 1000)),
    )

    cfg_kwargs = {
        'system_instruction': system_instruction,
        'temperature': temperature,
        'max_output_tokens': max_output_tokens,
    }
    if response_mime_type:
        cfg_kwargs['response_mime_type'] = response_mime_type
    if response_schema is not None:
        cfg_kwargs['response_schema'] = response_schema

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=genai.types.GenerateContentConfig(**cfg_kwargs),
    )
    text = (getattr(response, 'text', '') or '').strip()
    if text:
        return text

    candidates = getattr(response, 'candidates', None) or []
    if candidates:
        parts = []
        content = getattr(candidates[0], 'content', None)
        for p in (getattr(content, 'parts', None) or []):
            part_text = getattr(p, 'text', None)
            if part_text:
                parts.append(part_text)
        text = "\n".join(parts).strip()
    return text


def _generate_with_openai(
    *,
    api_key,
    model_name,
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

    client = OpenAI(api_key=api_key, timeout=timeout_seconds)
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
    """Jednotný wrapper na AI volanie naprieč providermi."""
    provider, resolved_model = _resolve_provider_and_model(model_name=model_name)
    resolved_api_key = (api_key or '').strip() or get_provider_api_key(provider)
    if not resolved_api_key:
        raise RuntimeError(f"API key pre provider `{provider}` nie je nastavený.")

    ttl_seconds = _resolve_cache_ttl_seconds(cache_ttl_seconds)
    cache_enabled = _is_cache_enabled(ttl_seconds)
    cache_key = ''
    if cache_enabled:
        cache_key = _build_ai_cache_key(
            provider=provider,
            model_name=resolved_model,
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
            if provider == 'openai':
                text = _generate_with_openai(
                    api_key=resolved_api_key,
                    model_name=resolved_model,
                    contents=contents,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_mime_type=response_mime_type,
                    timeout_seconds=timeout_seconds,
                )
            else:
                text = _generate_with_gemini(
                    api_key=resolved_api_key,
                    model_name=resolved_model,
                    contents=contents,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_mime_type=response_mime_type,
                    response_schema=response_schema,
                    timeout_seconds=timeout_seconds,
                )
        except Exception as exc:
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
                    provider=provider,
                    model_name=resolved_model,
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
    return (api_key or '').strip() or get_provider_api_key('gemini')


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

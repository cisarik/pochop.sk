from django.db.utils import OperationalError, ProgrammingError

from .access import user_can_switch_ai_model, user_has_pro_account
from .gemini_utils import get_active_model_context


HEADER_MODEL_FALLBACKS = (
    ('GPT-5.2', 'openai:gpt-5.2'),
    ('Gemini Pro 2.5', 'gemini:gemini-2.5-pro'),
)


def _normalize_model_key(provider, model):
    provider_part = (provider or '').strip().lower()
    model_part = (model or '').strip().lower()
    if not provider_part and not model_part:
        return ''
    return f"{provider_part}:{model_part}".strip(':')


def _build_dropdown_item(label, model_ref, active_key):
    try:
        model_ctx = get_active_model_context(model_name=model_ref)
    except Exception:
        model_ctx = {
            'provider': '',
            'provider_label': 'AI',
            'model': (model_ref or '').strip(),
            'badge': (label or '').strip(),
        }

    item_key = _normalize_model_key(model_ctx.get('provider'), model_ctx.get('model'))
    return {
        'label': (label or '').strip(),
        'model_ref': (model_ref or '').strip(),
        'provider_label': model_ctx.get('provider_label', 'AI'),
        'model': model_ctx.get('model', ''),
        'badge': model_ctx.get('badge', ''),
        'key': item_key,
        'is_active': bool(active_key and active_key == item_key),
    }


def _clean_model_badge_label(label):
    cleaned = (label or '').strip()
    if not cleaned:
        return ''
    provider_prefix = 'vercel ai gateway '
    if cleaned.lower().startswith(provider_prefix):
        cleaned = cleaned[len(provider_prefix):].strip()

    # Normalize provider route/prefix styles to model-only label in header trigger.
    providers = {
        'openai', 'google', 'gemini', 'anthropic', 'xai',
        'mistral', 'meta', 'deepseek', 'perplexity',
    }
    compact = cleaned.strip()
    if ' ' not in compact:
        if '/' in compact:
            owner, model = compact.split('/', 1)
            if owner.strip().lower() in providers and model.strip():
                return model.strip()
        if ':' in compact:
            owner, model = compact.split(':', 1)
            if owner.strip().lower() in providers and model.strip():
                return model.strip()
    return cleaned


def _resolve_active_model_label(active, dropdown_models):
    active_item = next((item for item in dropdown_models if item.get('is_active')), None)
    if active_item and active_item.get('label'):
        return _clean_model_badge_label(active_item.get('label'))

    model_label = _clean_model_badge_label(active.get('model'))
    if model_label:
        return model_label

    badge_label = _clean_model_badge_label(active.get('badge'))
    if badge_label:
        return badge_label
    return 'AI model'


def _get_header_models(active_key, user=None):
    rows = []
    try:
        from .models import AIModelOption

        allow_pro_only = bool(
            getattr(user, 'is_staff', False)
            or getattr(user, 'is_superuser', False)
            or user_has_pro_account(user)
        )
        qs = AIModelOption.objects.filter(is_enabled=True, is_available=True)
        if not allow_pro_only:
            qs = qs.filter(is_pro_only=False)
        rows = list(
            qs
            .order_by('sort_order', 'label')
            .values_list('label', 'model_ref')
        )
    except (OperationalError, ProgrammingError):
        try:
            from .models import AIModelOption

            rows = list(
                AIModelOption.objects.filter(is_enabled=True)
                .order_by('sort_order', 'label')
                .values_list('label', 'model_ref')
            )
        except Exception:
            rows = []
    except Exception:
        rows = []

    if not rows:
        rows = list(HEADER_MODEL_FALLBACKS)
    return [_build_dropdown_item(label, model_ref, active_key) for label, model_ref in rows]


def ai_runtime_context(request):
    try:
        active = get_active_model_context()
    except Exception:
        active = {
            'provider': 'gemini',
            'provider_label': 'Gemini',
            'model': 'gemini-3.1-pro-preview',
            'badge': 'Gemini gemini-3.1-pro-preview',
        }
    active_model_key = _normalize_model_key(active.get('provider'), active.get('model'))
    req_user = getattr(request, 'user', None)
    ai_dropdown_models = _get_header_models(active_model_key, user=req_user)
    if active_model_key and not any(item.get('is_active') for item in ai_dropdown_models):
        ai_dropdown_models.insert(
            0,
            _build_dropdown_item(active.get('model'), active_model_key, active_model_key),
        )
    active_ai_model_label = _resolve_active_model_label(active, ai_dropdown_models)
    ai_dropdown_options = [item for item in ai_dropdown_models if not item.get('is_active')]
    can_switch_ai_model = user_can_switch_ai_model(req_user)
    has_pro_account = user_has_pro_account(req_user)
    return {
        'active_ai_provider': active['provider'],
        'active_ai_provider_label': active['provider_label'],
        'active_ai_model': active['model'],
        'active_ai_model_badge': active['badge'],
        'active_ai_model_label': active_ai_model_label,
        'active_ai_model_key': active_model_key,
        'ai_dropdown_models': ai_dropdown_models,
        'ai_dropdown_options': ai_dropdown_options,
        'can_switch_ai_model': can_switch_ai_model,
        'has_pro_account': has_pro_account,
    }

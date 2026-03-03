from django.db.utils import OperationalError, ProgrammingError

from .access import user_can_switch_ai_model
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


def _get_header_models(active_key):
    rows = []
    try:
        from .models import AIModelOption

        rows = list(
            AIModelOption.objects.filter(is_enabled=True)
            .order_by('sort_order', 'label')
            .values_list('label', 'model_ref')
        )
    except (OperationalError, ProgrammingError):
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
    ai_dropdown_models = _get_header_models(active_model_key)
    if active_model_key and not any(item.get('is_active') for item in ai_dropdown_models):
        ai_dropdown_models.insert(
            0,
            _build_dropdown_item(active.get('badge'), active_model_key, active_model_key),
        )
    ai_dropdown_options = [item for item in ai_dropdown_models if not item.get('is_active')]
    can_switch_ai_model = user_can_switch_ai_model(getattr(request, 'user', None))
    return {
        'active_ai_provider': active['provider'],
        'active_ai_provider_label': active['provider_label'],
        'active_ai_model': active['model'],
        'active_ai_model_badge': active['badge'],
        'active_ai_model_key': active_model_key,
        'ai_dropdown_models': ai_dropdown_models,
        'ai_dropdown_options': ai_dropdown_options,
        'can_switch_ai_model': can_switch_ai_model,
    }

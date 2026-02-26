from .gemini_utils import get_active_model_context


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
    return {
        'active_ai_provider': active['provider'],
        'active_ai_provider_label': active['provider_label'],
        'active_ai_model': active['model'],
        'active_ai_model_badge': active['badge'],
    }

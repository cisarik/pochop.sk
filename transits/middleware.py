from django.shortcuts import render
from django.http import JsonResponse

from .ai_request_context import clear_ai_request_context, set_ai_request_context
from .gemini_utils import is_daily_limit_exceeded


class GeminiQuotaMiddleware:
    """Pri prekročení denného Gemini limitu zobraz outage page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        bypass_prefixes = (
            '/admin',
            '/static/',
            '/media/',
            '/api/ai-model/select/',
        )
        if path.startswith(bypass_prefixes):
            return self.get_response(request)

        if is_daily_limit_exceeded():
            if path.startswith('/api/'):
                return JsonResponse({
                    'error': 'Ospravedlňujeme sa, stránka má dočasný výpadok (denný AI limit bol vyčerpaný).',
                    'limit_exceeded': True,
                }, status=503)
            return render(request, 'transits/outage.html', status=503)

        return self.get_response(request)


class AICreditContextMiddleware:
    """Poskytne request-level kontext (user/path) pre AI billing vrstvu."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        user_id = None
        if getattr(user, 'is_authenticated', False):
            user_id = getattr(user, 'pk', None)
        set_ai_request_context(
            user_id=user_id,
            path=request.path,
            method=request.method,
        )
        try:
            return self.get_response(request)
        finally:
            clear_ai_request_context()

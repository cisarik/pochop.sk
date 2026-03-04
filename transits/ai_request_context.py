import threading


_CTX = threading.local()


def set_ai_request_context(*, user_id=None, path='', method=''):
    _CTX.user_id = int(user_id) if user_id else None
    _CTX.path = str(path or '')
    _CTX.method = str(method or '')


def get_ai_request_context():
    return {
        'user_id': getattr(_CTX, 'user_id', None),
        'path': getattr(_CTX, 'path', ''),
        'method': getattr(_CTX, 'method', ''),
    }


def clear_ai_request_context():
    for attr in ('user_id', 'path', 'method'):
        if hasattr(_CTX, attr):
            delattr(_CTX, attr)

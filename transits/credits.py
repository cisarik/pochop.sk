import math

from django.conf import settings
from django.db import transaction


class AICreditLimitExceededError(Exception):
    """Používateľ nemá dostatočný kredit pre nové AI volanie."""


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _get_min_credit_charge():
    return max(1, _safe_int(getattr(settings, 'AI_CREDITS_MIN_CHARGE', 1), 1))


def _get_usage_est_chars_per_token():
    raw = getattr(settings, 'AI_USAGE_EST_CHARS_PER_TOKEN', 4)
    try:
        val = float(raw)
    except Exception:
        val = 4.0
    return max(1.0, val)


def _estimate_completion_tokens(response_text, max_output_tokens):
    text = str(response_text or '')
    if not text.strip():
        return max(1, _safe_int(max_output_tokens, 0) or 1)
    estimate = math.ceil(len(text) / _get_usage_est_chars_per_token())
    if max_output_tokens:
        estimate = min(max(1, estimate), max(1, _safe_int(max_output_tokens, 1)))
    return max(1, estimate)


def normalize_usage_tokens(usage, *, response_text='', max_output_tokens=0):
    payload = usage if isinstance(usage, dict) else {}
    prompt_tokens = max(0, _safe_int(payload.get('prompt_tokens', payload.get('input_tokens', 0)), 0))
    completion_tokens = max(0, _safe_int(payload.get('completion_tokens', payload.get('output_tokens', 0)), 0))
    total_tokens = max(0, _safe_int(payload.get('total_tokens', 0), 0))

    source = 'provider'
    if completion_tokens <= 0:
        completion_tokens = _estimate_completion_tokens(response_text, max_output_tokens)
        source = 'estimated'
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    if total_tokens <= 0:
        total_tokens = completion_tokens
    return {
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': total_tokens,
        'usage_source': source,
    }


def compute_credit_cost(usage_tokens):
    usage = usage_tokens if isinstance(usage_tokens, dict) else {}
    prompt_tokens = max(0, _safe_int(usage.get('prompt_tokens', 0), 0))
    completion_tokens = max(0, _safe_int(usage.get('completion_tokens', 0), 0))
    input_rate = max(0, _safe_int(getattr(settings, 'AI_CREDITS_INPUT_PER_1K_TOKENS', 0), 0))
    output_rate = max(0, _safe_int(getattr(settings, 'AI_CREDITS_OUTPUT_PER_1K_TOKENS', 2), 2))
    min_charge = _get_min_credit_charge()

    weighted_tokens = (prompt_tokens * input_rate) + (completion_tokens * output_rate)
    if weighted_tokens <= 0:
        return min_charge
    return max(min_charge, math.ceil(weighted_tokens / 1000))


def ensure_user_can_afford_ai_call(user_id):
    if not user_id:
        return

    from .models import UserProStatus

    status = (
        UserProStatus.objects
        .filter(user_id=user_id)
        .only('id', 'is_pro', 'credits')
        .first()
    )
    if not status or not bool(status.is_pro):
        return

    min_required = _get_min_credit_charge()
    if _safe_int(status.credits, 0) < min_required:
        raise AICreditLimitExceededError('Nedostatok AI kreditov. Dobitie kreditov nájdeš v Pro účte.')


def charge_user_for_ai_call(
    *,
    user_id,
    model_ref,
    endpoint_path='',
    usage=None,
    response_text='',
    max_output_tokens=0,
    cache_hit=False,
    meta=None,
):
    if not user_id:
        return {'charged': False, 'reason': 'no-user'}
    if cache_hit:
        return {'charged': False, 'reason': 'cache-hit'}

    from .models import AICreditTransaction, UserProStatus

    usage_tokens = normalize_usage_tokens(
        usage,
        response_text=response_text,
        max_output_tokens=max_output_tokens,
    )
    requested_cost = compute_credit_cost(usage_tokens)

    with transaction.atomic():
        status = (
            UserProStatus.objects
            .select_for_update()
            .filter(user_id=user_id)
            .first()
        )
        if not status or not bool(status.is_pro):
            return {'charged': False, 'reason': 'not-pro'}

        balance_before = _safe_int(status.credits, 0)
        if balance_before <= 0:
            raise AICreditLimitExceededError('Nedostatok AI kreditov. Dobitie kreditov nájdeš v Pro účte.')

        charged_credits = min(balance_before, max(1, requested_cost))
        balance_after = balance_before - charged_credits
        status.credits = balance_after
        status.save(update_fields=['credits', 'updated_at'])

        AICreditTransaction.objects.create(
            user_id=user_id,
            pro_status=status,
            event_type='charge',
            credits_delta=-charged_credits,
            credits_before=balance_before,
            credits_after=balance_after,
            credits_requested=max(1, requested_cost),
            model_ref=str(model_ref or '').strip(),
            endpoint_path=str(endpoint_path or '').strip()[:220],
            prompt_tokens=usage_tokens['prompt_tokens'],
            completion_tokens=usage_tokens['completion_tokens'],
            total_tokens=usage_tokens['total_tokens'],
            usage_source=usage_tokens['usage_source'],
            cache_hit=bool(cache_hit),
            meta_json=meta if isinstance(meta, dict) else {},
        )

    return {
        'charged': True,
        'charged_credits': charged_credits,
        'requested_credits': max(1, requested_cost),
        'balance_after': balance_after,
        'usage_tokens': usage_tokens,
    }


def adjust_user_credits(*, user_id, delta, event_type='adjustment', note=''):
    delta_int = _safe_int(delta, 0)
    if delta_int == 0:
        return None

    from .models import AICreditTransaction, UserProStatus

    with transaction.atomic():
        status = (
            UserProStatus.objects
            .select_for_update()
            .filter(user_id=user_id)
            .first()
        )
        if not status:
            return None
        balance_before = _safe_int(status.credits, 0)
        balance_after = max(0, balance_before + delta_int)
        status.credits = balance_after
        status.save(update_fields=['credits', 'updated_at'])

        AICreditTransaction.objects.create(
            user_id=user_id,
            pro_status=status,
            event_type=event_type,
            credits_delta=balance_after - balance_before,
            credits_before=balance_before,
            credits_after=balance_after,
            credits_requested=abs(delta_int),
            model_ref='',
            endpoint_path='',
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            usage_source='',
            cache_hit=False,
            meta_json={'note': str(note or '').strip()} if note else {},
        )
    return balance_after


def top_up_user_credits(*, user_id, amount, note=''):
    amount_int = max(0, _safe_int(amount, 0))
    if amount_int <= 0:
        raise ValueError('amount musí byť kladné celé číslo')
    return adjust_user_credits(
        user_id=user_id,
        delta=amount_int,
        event_type='topup',
        note=note,
    )


def record_credit_adjustment(*, user_id, delta, credits_before, credits_after, note=''):
    delta_int = _safe_int(delta, 0)
    if delta_int == 0:
        return None

    from .models import AICreditTransaction, UserProStatus

    status = UserProStatus.objects.filter(user_id=user_id).first()
    if not status:
        return None
    return AICreditTransaction.objects.create(
        user_id=user_id,
        pro_status=status,
        event_type='adjustment',
        credits_delta=delta_int,
        credits_before=_safe_int(credits_before, 0),
        credits_after=_safe_int(credits_after, 0),
        credits_requested=abs(delta_int),
        model_ref='',
        endpoint_path='',
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        usage_source='',
        cache_hit=False,
        meta_json={'note': str(note or '').strip()} if note else {},
    )

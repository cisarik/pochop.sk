from django.core.exceptions import ObjectDoesNotExist


def user_has_pro_account(user):
    """True ak prihlásený používateľ má profil s aktívnym Pro flagom."""
    if not getattr(user, 'is_authenticated', False):
        return False
    try:
        profile = user.natal_profile
    except (AttributeError, ObjectDoesNotExist):
        return False
    return bool(getattr(profile, 'is_pro', False))


def user_can_switch_ai_model(user):
    """
    Oprávnenie na prepínanie AI modelu:
    - staff/superuser vždy,
    - alebo bežný používateľ s Pro účtom.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)):
        return True
    return user_has_pro_account(user)

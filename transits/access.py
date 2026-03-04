from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import OperationalError, ProgrammingError


def _user_pro_status_flag(user):
    """Vráti Pro flag z user-level tabuľky; None ak nie je dostupný."""
    if not getattr(user, 'is_authenticated', False):
        return None
    try:
        pro_status = user.pro_status
    except (AttributeError, ObjectDoesNotExist):
        return None
    except (OperationalError, ProgrammingError):
        return None
    return bool(getattr(pro_status, 'is_pro', False))


def user_has_pro_account(user):
    """True ak prihlásený používateľ má aktívny Pro účet."""
    if not getattr(user, 'is_authenticated', False):
        return False

    user_level_flag = _user_pro_status_flag(user)
    if user_level_flag is not None:
        return user_level_flag

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

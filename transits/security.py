import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings
from django.db import models


ENCRYPTION_PREFIX = 'enc::'
USER_ENCRYPTION_PREFIX = 'usr::'
SESSION_PROFILE_KEYS = 'profile_unlock_keys'


def _get_fernet():
    password = (getattr(settings, 'PII_ENCRYPTION_PASSWORD', '') or '').strip()
    if not password:
        # Last-resort fallback so app still boots, but this should be set in .env.
        password = getattr(settings, 'SECRET_KEY', 'fallback-secret-key')
    digest = hashlib.sha256(password.encode('utf-8')).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def is_encrypted(value):
    return bool(value and isinstance(value, str) and value.startswith(ENCRYPTION_PREFIX))


def encrypt_text(value):
    if value in (None, ''):
        return value
    raw = str(value)
    if is_encrypted(raw):
        return raw
    token = _get_fernet().encrypt(raw.encode('utf-8')).decode('utf-8')
    return f'{ENCRYPTION_PREFIX}{token}'


def decrypt_text(value):
    if value in (None, ''):
        return value
    raw = str(value)
    if not is_encrypted(raw):
        return raw
    token = raw[len(ENCRYPTION_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return ''


class EncryptedTextField(models.TextField):
    """Transparentné field-level šifrovanie/dešifrovanie textu."""

    description = "Encrypted text"

    def from_db_value(self, value, expression, connection):
        return decrypt_text(value)

    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, str):
            return decrypt_text(value)
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        return encrypt_text(value)


def generate_user_salt():
    return secrets.token_hex(16)


def derive_user_key_b64(raw_password, salt_hex):
    if not raw_password:
        raise ValueError('Chýba používateľské heslo pre odvodenie šifrovacieho kľúča.')
    if not salt_hex:
        raise ValueError('Chýba user salt pre odvodenie šifrovacieho kľúča.')
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=bytes.fromhex(salt_hex),
        iterations=390000,
    )
    key = kdf.derive(raw_password.encode('utf-8'))
    return base64.urlsafe_b64encode(key).decode('utf-8')


def encrypt_with_user_key(plain_text, key_b64):
    if plain_text in (None, ''):
        return ''
    token = Fernet(key_b64.encode('utf-8')).encrypt(str(plain_text).encode('utf-8')).decode('utf-8')
    return f'{USER_ENCRYPTION_PREFIX}{token}'


def decrypt_with_user_key(cipher_text, key_b64):
    if cipher_text in (None, ''):
        return ''
    raw = str(cipher_text)
    if raw.startswith(USER_ENCRYPTION_PREFIX):
        raw = raw[len(USER_ENCRYPTION_PREFIX):]
    try:
        return Fernet(key_b64.encode('utf-8')).decrypt(raw.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return ''


def store_profile_key_in_session(session, profile_id, key_b64):
    payload = dict(session.get(SESSION_PROFILE_KEYS, {}))
    payload[str(profile_id)] = key_b64
    session[SESSION_PROFILE_KEYS] = payload
    session.modified = True


def get_profile_key_from_session(session, profile_id):
    payload = session.get(SESSION_PROFILE_KEYS, {}) or {}
    return payload.get(str(profile_id))

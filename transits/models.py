from django.conf import settings
from django.db import models
from datetime import datetime
import json
import secrets

from .security import (
    derive_user_key_b64,
    decrypt_text,
    encrypt_text,
    decrypt_with_user_key,
    encrypt_with_user_key,
    generate_user_salt,
)


PLANET_CHOICES = [
    ('sun', 'Slnko'),
    ('moon', 'Mesiac'),
    ('mercury', 'Merkúr'),
    ('venus', 'Venuša'),
    ('mars', 'Mars'),
    ('jupiter', 'Jupiter'),
    ('saturn', 'Saturn'),
    ('uranus', 'Urán'),
    ('neptune', 'Neptún'),
    ('pluto', 'Pluto'),
]

ASPECT_CHOICES = [
    ('conjunction', 'Konjunkcia'),
    ('sextile', 'Sextil'),
    ('square', 'Kvadratúra'),
    ('trine', 'Trigón'),
    ('opposition', 'Opozícia'),
]

EFFECT_CHOICES = [
    ('positive', 'Pozitívny'),
    ('negative', 'Negatívny'),
    ('neutral', 'Neutrálny'),
]

PLANET_SYMBOLS = {
    'sun': '☉',
    'moon': '☽',
    'mercury': '☿',
    'venus': '♀',
    'mars': '♂',
    'jupiter': '♃',
    'saturn': '♄',
    'uranus': '♅',
    'neptune': '♆',
    'pluto': '♇',
}

ASPECT_SYMBOLS = {
    'conjunction': '☌',
    'sextile': '⚹',
    'square': '□',
    'trine': '△',
    'opposition': '☍',
}


class TransitAspect(models.Model):
    """Databáza výkladov tranzitových aspektov."""

    transit_planet = models.CharField(
        'Tranzitná planéta', max_length=20, choices=PLANET_CHOICES
    )
    natal_planet = models.CharField(
        'Natálna planéta', max_length=20, choices=PLANET_CHOICES
    )
    aspect_type = models.CharField(
        'Typ aspektu', max_length=20, choices=ASPECT_CHOICES
    )
    effect = models.CharField(
        'Pôsobenie', max_length=20, choices=EFFECT_CHOICES, default='neutral'
    )
    default_text = models.TextField(
        'Predvolený text',
        help_text='Automaticky generovaný popis tranzitu'
    )
    user_text = models.TextField(
        'Vlastný text',
        blank=True,
        default='',
        help_text='Vlastný popis - ak je vyplnený, zobrazí sa namiesto predvoleného'
    )

    class Meta:
        unique_together = ('transit_planet', 'natal_planet', 'aspect_type')
        verbose_name = 'Výklad tranzitu'
        verbose_name_plural = 'Výklady tranzitov'
        ordering = ['transit_planet', 'natal_planet', 'aspect_type']

    @property
    def display_text(self):
        """Vráti vlastný text ak existuje, inak predvolený."""
        return self.user_text if self.user_text else self.default_text

    @property
    def transit_symbol(self):
        return PLANET_SYMBOLS.get(self.transit_planet, '')

    @property
    def natal_symbol(self):
        return PLANET_SYMBOLS.get(self.natal_planet, '')

    @property
    def aspect_symbol(self):
        return ASPECT_SYMBOLS.get(self.aspect_type, '')

    def __str__(self):
        return (
            f"{self.get_aspect_type_display()} "
            f"t.{self.get_transit_planet_display()} - "
            f"n.{self.get_natal_planet_display()}"
        )


class SlovakCity(models.Model):
    """Databáza slovenských obcí s GPS súradnicami."""

    name = models.CharField('Názov', max_length=100, db_index=True)
    district = models.CharField('Okres', max_length=100)
    lat = models.FloatField('Zemepisná šírka')
    lon = models.FloatField('Zemepisná dĺžka')

    class Meta:
        verbose_name = 'Slovenská obec'
        verbose_name_plural = 'Slovenské obce'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (okres {self.district})"


class NatalProfile(models.Model):
    """Profil s údajmi o narodení pre výpočet tranzitov."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='natal_profile',
        verbose_name='Používateľ',
    )
    name = models.CharField('Meno', max_length=100)
    # Legacy/plain fields zostávajú pre spätnú kompatibilitu, no nové zápisy ich nulujú.
    birth_date = models.DateField('Dátum narodenia', null=True, blank=True)
    birth_time = models.TimeField('Čas narodenia', null=True, blank=True)
    birth_place = models.TextField('Miesto narodenia', null=True, blank=True)
    birth_lat = models.FloatField('Zemepisná šírka', null=True, blank=True)
    birth_lon = models.FloatField('Zemepisná dĺžka', null=True, blank=True)
    birth_data_salt = models.CharField('User crypto salt', max_length=32, blank=True, default='')
    birth_date_encrypted = models.TextField('Birth date (enc)', blank=True, default='')
    birth_time_encrypted = models.TextField('Birth time (enc)', blank=True, default='')
    birth_place_encrypted = models.TextField('Birth place (enc)', blank=True, default='')
    birth_lat_encrypted = models.TextField('Birth lat (enc)', blank=True, default='')
    birth_lon_encrypted = models.TextField('Birth lon (enc)', blank=True, default='')
    birth_data_recovery_encrypted = models.TextField(
        'Birth data recovery (enc)',
        blank=True,
        default='',
        help_text='Server-side recovery envelope pre bezpečný re-encrypt po reset hesla.',
    )
    timezone = models.CharField(
        'Časové pásmo', max_length=50, default='Europe/Bratislava'
    )
    # Uložené AI analýzy (generované raz pri registrácii)
    natal_analysis_json = models.JSONField(
        'Natálna analýza', null=True, blank=True,
        help_text='AI natálna analýza (sekcie)',
    )
    natal_aspects_json = models.JSONField(
        'Analýza aspektov', null=True, blank=True,
        help_text='AI hlboká analýza natálnych aspektov',
    )
    natal_chart_json = models.JSONField(
        'Natálny chart', null=True, blank=True,
        help_text='Vypočítaný natálny horoskop (planéty, aspekty, domy)',
    )
    natal_positions_json = models.JSONField(
        'Natálne pozície',
        null=True,
        blank=True,
        help_text='Predpočítané natálne pozície pre výpočet tranzitov bez potreby dešifrovania PII.',
    )
    public_hash = models.CharField(
        'Public hash',
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        help_text='Pseudonymizovaný identifikátor pre OSS/export účely.',
    )

    created_at = models.DateTimeField('Vytvorené', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'Natálny profil'
        verbose_name_plural = 'Natálne profily'
        ordering = ['-created_at']

    @property
    def has_analysis(self):
        return bool(self.natal_analysis_json and self.natal_aspects_json)

    def ensure_public_hash(self):
        if not self.public_hash:
            self.public_hash = secrets.token_hex(24)

    def save(self, *args, **kwargs):
        self.ensure_public_hash()
        return super().save(*args, **kwargs)

    def set_encrypted_birth_data(
        self,
        *,
        raw_password,
        birth_date,
        birth_time,
        birth_place,
        birth_lat,
        birth_lon,
    ):
        if not self.birth_data_salt:
            self.birth_data_salt = generate_user_salt()
        key_b64 = derive_user_key_b64(raw_password, self.birth_data_salt)

        self.birth_date_encrypted = encrypt_with_user_key(str(birth_date.isoformat()), key_b64)
        self.birth_time_encrypted = encrypt_with_user_key(str(birth_time.strftime('%H:%M:%S')), key_b64)
        self.birth_place_encrypted = encrypt_with_user_key(str(birth_place), key_b64)
        self.birth_lat_encrypted = encrypt_with_user_key(str(float(birth_lat)), key_b64)
        self.birth_lon_encrypted = encrypt_with_user_key(str(float(birth_lon)), key_b64)
        self._set_recovery_birth_data(
            birth_date=birth_date,
            birth_time=birth_time,
            birth_place=birth_place,
            birth_lat=birth_lat,
            birth_lon=birth_lon,
            timezone=self.timezone,
        )

        # Plain PII vypnieme.
        self.birth_date = None
        self.birth_time = None
        self.birth_place = None
        self.birth_lat = None
        self.birth_lon = None
        self.ensure_public_hash()

        return key_b64

    def migrate_legacy_birth_data(self, raw_password):
        """Prevedie legacy plain birth polia do per-user encrypted polí."""
        if self.birth_date_encrypted:
            return
        if not (self.birth_date and self.birth_time and self.birth_place and self.birth_lat is not None and self.birth_lon is not None):
            return
        place_plain = decrypt_text(self.birth_place)
        self.set_encrypted_birth_data(
            raw_password=raw_password,
            birth_date=self.birth_date,
            birth_time=self.birth_time,
            birth_place=place_plain or self.birth_place,
            birth_lat=self.birth_lat,
            birth_lon=self.birth_lon,
        )

    def _set_recovery_birth_data(self, *, birth_date, birth_time, birth_place, birth_lat, birth_lon, timezone):
        payload = {
            'birth_date': birth_date.isoformat(),
            'birth_time': birth_time.strftime('%H:%M:%S'),
            'birth_place': str(birth_place),
            'birth_lat': float(birth_lat),
            'birth_lon': float(birth_lon),
            'timezone': timezone or self.timezone or 'Europe/Bratislava',
        }
        self.birth_data_recovery_encrypted = encrypt_text(json.dumps(payload, ensure_ascii=False))

    def get_recovery_birth_data(self):
        if not self.birth_data_recovery_encrypted:
            return None
        raw = decrypt_text(self.birth_data_recovery_encrypted)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            return {
                'birth_date': datetime.strptime(payload['birth_date'], '%Y-%m-%d').date(),
                'birth_time': datetime.strptime(payload['birth_time'], '%H:%M:%S').time(),
                'birth_place': payload['birth_place'],
                'birth_lat': float(payload['birth_lat']),
                'birth_lon': float(payload['birth_lon']),
                'timezone': payload.get('timezone') or self.timezone,
            }
        except Exception:
            return None

    def reencrypt_birth_data(self, *, new_raw_password, old_raw_password=None):
        """
        Bezpečne prešifruje birth dáta na nové heslo.
        Primárne používa staré heslo; fallback je recovery envelope.
        """
        birth = None
        if self.birth_date_encrypted and old_raw_password and self.birth_data_salt:
            try:
                old_key = derive_user_key_b64(old_raw_password, self.birth_data_salt)
                birth = self.decrypt_birth_data(key_b64=old_key)
            except Exception:
                birth = None

        if not birth:
            birth = self.get_recovery_birth_data()

        if not birth and self.birth_date and self.birth_time and self.birth_lat is not None and self.birth_lon is not None:
            birth = {
                'birth_date': self.birth_date,
                'birth_time': self.birth_time,
                'birth_place': decrypt_text(self.birth_place or '') or (self.birth_place or ''),
                'birth_lat': float(self.birth_lat),
                'birth_lon': float(self.birth_lon),
                'timezone': self.timezone,
            }

        if not birth:
            return False

        self.timezone = birth.get('timezone') or self.timezone
        self.birth_data_salt = generate_user_salt()
        self.set_encrypted_birth_data(
            raw_password=new_raw_password,
            birth_date=birth['birth_date'],
            birth_time=birth['birth_time'],
            birth_place=birth['birth_place'],
            birth_lat=birth['birth_lat'],
            birth_lon=birth['birth_lon'],
        )
        return True

    def decrypt_birth_data(self, key_b64=None):
        # Legacy fallback (staré profily)
        if not self.birth_date_encrypted:
            if not self.birth_date or self.birth_lat is None or self.birth_lon is None:
                return None
            return {
                'birth_date': self.birth_date,
                'birth_time': self.birth_time,
                'birth_place': decrypt_text(self.birth_place or '') or (self.birth_place or ''),
                'birth_lat': float(self.birth_lat),
                'birth_lon': float(self.birth_lon),
                'timezone': self.timezone,
            }

        if not key_b64:
            return None
        try:
            date_raw = decrypt_with_user_key(self.birth_date_encrypted, key_b64)
            time_raw = decrypt_with_user_key(self.birth_time_encrypted, key_b64)
            place_raw = decrypt_with_user_key(self.birth_place_encrypted, key_b64)
            lat_raw = decrypt_with_user_key(self.birth_lat_encrypted, key_b64)
            lon_raw = decrypt_with_user_key(self.birth_lon_encrypted, key_b64)
            if not (date_raw and time_raw and lat_raw and lon_raw):
                return None
            return {
                'birth_date': datetime.strptime(date_raw, '%Y-%m-%d').date(),
                'birth_time': datetime.strptime(time_raw, '%H:%M:%S').time(),
                'birth_place': place_raw,
                'birth_lat': float(lat_raw),
                'birth_lon': float(lon_raw),
                'timezone': self.timezone,
            }
        except Exception:
            return None

    def __str__(self):
        return f"{self.name} ({self.public_hash[:10] if self.public_hash else self.pk})"


class MomentReport(models.Model):
    """Denný verejný astrologický rozbor okamihu."""

    report_date = models.DateField('Dátum reportu', unique=True, db_index=True)
    timezone = models.CharField('Časové pásmo', max_length=50, default='Europe/Bratislava')
    generated_at = models.DateTimeField('Generované', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    planets_json = models.JSONField('Planéty', default=list)
    aspects_json = models.JSONField('Aspekty', default=list)
    ai_report_json = models.JSONField('AI report', default=dict)

    class Meta:
        verbose_name = 'Rozbor okamihu'
        verbose_name_plural = 'Rozbory okamihu'
        ordering = ['-report_date']

    def __str__(self):
        return f"Okamih {self.report_date.strftime('%d.%m.%Y')}"


class GeminiConfig(models.Model):
    """Runtime AI konfigurácia nastaviteľná v admin rozhraní."""

    default_model = models.CharField(
        'DEFAULT_MODEL',
        max_length=100,
        default='gemini-3.1-pro-preview',
        help_text='Príklady: gemini-3.1-pro-preview, openai:gpt-4.1-mini, openai',
    )
    max_calls_daily = models.PositiveIntegerField(
        'Max API calls denne',
        default=500,
        help_text='Tvrdý denný limit volaní na AI API.',
    )
    created_at = models.DateTimeField('Vytvorené', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'AI konfigurácia'
        verbose_name_plural = 'AI konfigurácia'

    def __str__(self):
        return f"AI config ({self.default_model})"

    # Backward compatibility for older code paths.
    @property
    def model_name(self):
        return self.default_model

    @model_name.setter
    def model_name(self, value):
        self.default_model = value


class GeminiDailyUsage(models.Model):
    """Denný agregovaný počet Gemini API volaní."""

    usage_date = models.DateField('Dátum', unique=True, db_index=True)
    calls_made = models.PositiveIntegerField('Počet volaní', default=0)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'Denné použitie Gemini'
        verbose_name_plural = 'Denné použitie Gemini'
        ordering = ['-usage_date']

    def __str__(self):
        return f"{self.usage_date}: {self.calls_made} volaní"

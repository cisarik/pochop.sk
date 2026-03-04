from django.conf import settings
from django.db import models
from django.db.utils import OperationalError, ProgrammingError
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

GENDER_CHOICES = [
    ('male', 'Muž'),
    ('female', 'Žena'),
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


class UserProStatus(models.Model):
    """User-level Pro flag pre features viazané na účet (nie profil)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pro_status',
        verbose_name='Používateľ',
    )
    is_pro = models.BooleanField(
        'Pro účet',
        default=False,
        help_text='Určuje, či má používateľ Pro oprávnenia (napr. prepínanie AI modelov).',
    )
    credits = models.BigIntegerField(
        'AI kredity',
        default=0,
        help_text='Aktuálny kreditový zostatok pre AI volania (odpočítava sa len pri cache-miss).',
    )
    created_at = models.DateTimeField('Vytvorené', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'Pro status používateľa'
        verbose_name_plural = 'Pro statusy používateľov'
        ordering = ['-updated_at']

    def __str__(self):
        tier = 'PRO' if self.is_pro else 'FREE'
        return f"{self.user} [{tier}]"

    def save(self, *args, **kwargs):
        saved = super().save(*args, **kwargs)
        try:
            NatalProfile.objects.filter(user_id=self.user_id).update(is_pro=bool(self.is_pro))
        except (OperationalError, ProgrammingError):
            return saved
        return saved


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
    gender = models.CharField('Pohlavie', max_length=10, choices=GENDER_CHOICES, default='male')
    is_pro = models.BooleanField(
        'Pro účet',
        default=False,
        help_text='Ak je zapnuté, používateľ má Pro oprávnenia (napr. prepínanie AI modelu).',
    )
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

    def _sync_user_pro_status(self, *, previous_is_pro=None):
        if not self.user_id:
            return
        try:
            status = UserProStatus.objects.filter(user_id=self.user_id).first()
            if status is None:
                UserProStatus.objects.create(
                    user_id=self.user_id,
                    is_pro=bool(self.is_pro),
                )
                return

            # Explicitná zmena flagu v profile (napr. admin edit) sa prenesie do user-level statusu.
            if previous_is_pro is not None and bool(previous_is_pro) != bool(self.is_pro):
                if bool(status.is_pro) != bool(self.is_pro):
                    status.is_pro = bool(self.is_pro)
                    status.save(update_fields=['is_pro', 'updated_at'])
                return

            # Ak profil ešte nebol explicitne menený, user-level status je nadradený.
            if bool(status.is_pro) != bool(self.is_pro):
                NatalProfile.objects.filter(pk=self.pk).update(is_pro=bool(status.is_pro))
                self.is_pro = bool(status.is_pro)
        except (OperationalError, ProgrammingError):
            # Tolerujeme stav počas migrácie, aby page flow nespadol.
            return

    def save(self, *args, **kwargs):
        previous_is_pro = None
        if self.pk:
            try:
                previous_is_pro = (
                    NatalProfile.objects
                    .filter(pk=self.pk)
                    .values_list('is_pro', flat=True)
                    .first()
                )
            except Exception:
                previous_is_pro = None
        self.ensure_public_hash()
        saved = super().save(*args, **kwargs)
        self._sync_user_pro_status(previous_is_pro=previous_is_pro)
        return saved

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

    report_date = models.DateField('Dátum reportu', db_index=True)
    model_ref = models.CharField(
        'Model',
        max_length=120,
        default='',
        db_index=True,
        help_text='Normalizovaný model_ref (napr. openai:gpt-5.2).',
    )
    location_key = models.CharField(
        'Location key',
        max_length=64,
        default='48.1486:17.1077',
        db_index=True,
        help_text='Normalizovaný kľúč lokality pre cache (zaokrúhlené lat/lon).',
    )
    location_name = models.CharField(
        'Lokalita',
        max_length=160,
        default='Bratislava, Slovensko',
        help_text='Textový názov lokality použitý v reporte.',
    )
    location_lat = models.FloatField('Zemepisná šírka', default=48.1486)
    location_lon = models.FloatField('Zemepisná dĺžka', default=17.1077)
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
        constraints = [
            models.UniqueConstraint(
                fields=['report_date', 'model_ref', 'location_key'],
                name='uniq_moment_report_date_model_location',
            ),
        ]
        indexes = [
            models.Index(fields=['report_date', 'model_ref', 'location_key']),
        ]

    def __str__(self):
        model = self.model_ref or 'default'
        return f"Okamih {self.report_date.strftime('%d.%m.%Y')} [{model}] @ {self.location_key}"


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
    max_compare_models = models.PositiveSmallIntegerField(
        'Max modelov v porovnaní',
        default=3,
        help_text='Limit modelov v compare režime (timeline + natálna analýza).',
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


class AIModelOption(models.Model):
    """Modely zobrazované v header dropdown-e."""

    MODEL_SOURCE_CHOICES = [
        ('manual', 'Manuálne'),
        ('vercel', 'Vercel AI Gateway'),
    ]

    label = models.CharField(
        'Názov modelu',
        max_length=80,
        help_text='Viditeľný názov v UI, napr. GPT-5.2 alebo Gemini Pro 2.5.',
    )
    model_ref = models.CharField(
        'Model identifikátor',
        max_length=120,
        unique=True,
        help_text='Runtime hodnota, napr. openai:gpt-5.2 alebo gemini:gemini-2.5-pro.',
    )
    source = models.CharField(
        'Zdroj',
        max_length=20,
        choices=MODEL_SOURCE_CHOICES,
        default='manual',
        db_index=True,
        help_text='manual = ručne spravovaný model, vercel = synchronizovaný z Vercel AI Gateway.',
    )
    owner = models.CharField('Provider/owner', max_length=80, blank=True, default='')
    model_type = models.CharField('Typ', max_length=40, blank=True, default='')
    context_window = models.PositiveIntegerField('Context window', null=True, blank=True)
    max_tokens = models.PositiveIntegerField('Max output tokens', null=True, blank=True)
    description = models.TextField('Popis modelu', blank=True, default='')
    tags_json = models.JSONField('Tagy', default=list, blank=True)
    pricing_json = models.JSONField('Pricing', default=dict, blank=True)
    raw_meta_json = models.JSONField('Raw metadata', default=dict, blank=True)
    is_available = models.BooleanField(
        'Dostupný v katalógu',
        default=True,
        help_text='Pri sync z Vercel sa vypne, ak model zmizne z katalógu.',
    )
    is_pro_only = models.BooleanField(
        'Len pre Pro účty',
        default=False,
        help_text='Ak je zapnuté, model je viditeľný a použiteľný iba pre Pro účty (alebo staff).',
    )
    sort_order = models.PositiveIntegerField('Poradie', default=10)
    is_enabled = models.BooleanField(
        'Aktívny',
        default=True,
        help_text=(
            'Ak je zapnuté, model je aktívny v aplikácii: '
            'zobrazí sa v header dropdown-e/compare režime a použije sa pri refresh_to_cache.'
        ),
    )
    last_synced_at = models.DateTimeField('Naposledy synchronizované', null=True, blank=True)
    created_at = models.DateTimeField('Vytvorené', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'AI model'
        verbose_name_plural = 'AI modely'
        ordering = ['sort_order', 'label']

    def __str__(self):
        return f"{self.label} ({self.model_ref})"


class AIResponseCache(models.Model):
    """Persistovaná cache AI odpovedí na šetrenie API volaní."""

    cache_key = models.CharField('Cache key', max_length=64, unique=True, db_index=True)
    provider = models.CharField('Provider', max_length=20, default='gemini')
    model_name = models.CharField('Model', max_length=120, default='')
    response_text = models.TextField('Response text', default='')
    hits = models.PositiveIntegerField('Počet cache hitov', default=0)
    expires_at = models.DateTimeField('Expirácia', db_index=True)
    created_at = models.DateTimeField('Vytvorené', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'AI response cache'
        verbose_name_plural = 'AI response cache'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.provider}:{self.model_name} [{self.cache_key[:10]}...]"


class LocationLookupCache(models.Model):
    """Denná cache geolokačných lookupov (reverse/forward/ip)."""

    LOOKUP_TYPE_CHOICES = [
        ('reverse', 'Reverse geocoding'),
        ('forward', 'Forward geocoding'),
        ('ip', 'IP geolocation'),
    ]

    lookup_type = models.CharField('Typ lookupu', max_length=20, choices=LOOKUP_TYPE_CHOICES, db_index=True)
    lookup_key = models.CharField('Lookup key', max_length=100, db_index=True)
    cache_day = models.DateField('Cache deň', db_index=True)
    provider = models.CharField('Provider', max_length=40, blank=True, default='')
    payload_json = models.JSONField('Payload', default=dict)
    hits = models.PositiveIntegerField('Počet cache hitov', default=0)
    generated_at = models.DateTimeField('Generované', auto_now_add=True)
    last_served_at = models.DateTimeField('Naposledy servované', null=True, blank=True)
    expires_at = models.DateTimeField('Expirácia', db_index=True)
    created_at = models.DateTimeField('Vytvorené', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'Location lookup cache'
        verbose_name_plural = 'Location lookup cache'
        ordering = ['-cache_day', '-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['lookup_type', 'lookup_key', 'cache_day'],
                name='uniq_location_lookup_type_key_day',
            ),
        ]
        indexes = [
            models.Index(fields=['lookup_type', 'cache_day', 'expires_at']),
        ]

    def __str__(self):
        return f"{self.lookup_type}:{self.lookup_key[:16]}... [{self.cache_day}]"


class AIDayReportCache(models.Model):
    """Per-profil/per-deň cache pre AI hodnotenie dňa v timeline."""

    profile = models.ForeignKey(
        NatalProfile,
        on_delete=models.CASCADE,
        related_name='ai_day_report_cache_rows',
        verbose_name='Profil',
    )
    target_date = models.DateField('Dátum hodnotenia', db_index=True)
    model_ref = models.CharField('Model', max_length=120, db_index=True)
    payload_json = models.JSONField('AI payload', default=dict)
    profile_updated_at = models.DateTimeField('Profil updated_at snapshot', null=True, blank=True)
    hits = models.PositiveIntegerField('Počet cache hitov', default=0)
    generated_at = models.DateTimeField('Generované', auto_now_add=True)
    last_served_at = models.DateTimeField('Naposledy servované', null=True, blank=True)
    expires_at = models.DateTimeField('Expirácia', db_index=True)
    created_at = models.DateTimeField('Vytvorené', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'AI hodnotenie dňa cache'
        verbose_name_plural = 'AI hodnotenie dňa cache'
        ordering = ['-target_date', '-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'target_date', 'model_ref'],
                name='uniq_ai_day_cache_profile_date_model',
            ),
        ]
        indexes = [
            models.Index(fields=['target_date', 'model_ref']),
        ]

    def __str__(self):
        return f"{self.target_date} | {self.model_ref} | profile={self.profile_id}"


class AINatalAnalysisCache(models.Model):
    """Per-profil/per-model cache pre AI natálnu analýzu."""

    profile = models.ForeignKey(
        NatalProfile,
        on_delete=models.CASCADE,
        related_name='ai_natal_analysis_cache_rows',
        verbose_name='Profil',
    )
    model_ref = models.CharField('Model', max_length=120, db_index=True)
    analysis_json = models.JSONField('Natálna analýza', default=list)
    aspects_json = models.JSONField('Analýza aspektov', default=list)
    profile_updated_at = models.DateTimeField('Profil updated_at snapshot', null=True, blank=True)
    hits = models.PositiveIntegerField('Počet cache hitov', default=0)
    generated_at = models.DateTimeField('Generované', auto_now_add=True)
    last_served_at = models.DateTimeField('Naposledy servované', null=True, blank=True)
    expires_at = models.DateTimeField('Expirácia', db_index=True)
    created_at = models.DateTimeField('Vytvorené', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'AI natálna analýza cache'
        verbose_name_plural = 'AI natálne analýzy cache'
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'model_ref'],
                name='uniq_ai_natal_cache_profile_model',
            ),
        ]
        indexes = [
            models.Index(fields=['model_ref', 'expires_at']),
        ]

    def __str__(self):
        return f"{self.model_ref} | profile={self.profile_id}"


class AICreditTransaction(models.Model):
    """Audit transakcií kreditov viazaných na AI volania."""

    EVENT_CHOICES = [
        ('charge', 'Odpočet'),
        ('topup', 'Dobitie'),
        ('adjustment', 'Úprava'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_credit_transactions',
        verbose_name='Používateľ',
    )
    pro_status = models.ForeignKey(
        UserProStatus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_transactions',
        verbose_name='Pro status',
    )
    event_type = models.CharField('Typ transakcie', max_length=20, choices=EVENT_CHOICES, db_index=True)
    credits_delta = models.BigIntegerField('Zmena kreditov')
    credits_before = models.BigIntegerField('Stav pred')
    credits_after = models.BigIntegerField('Stav po')
    credits_requested = models.PositiveBigIntegerField('Požadovaný odpočet', default=0)
    model_ref = models.CharField('Model', max_length=120, blank=True, default='', db_index=True)
    endpoint_path = models.CharField('Endpoint', max_length=220, blank=True, default='')
    prompt_tokens = models.PositiveIntegerField('Prompt tokeny', default=0)
    completion_tokens = models.PositiveIntegerField('Output tokeny', default=0)
    total_tokens = models.PositiveIntegerField('Total tokeny', default=0)
    usage_source = models.CharField('Zdroj usage', max_length=20, blank=True, default='')
    cache_hit = models.BooleanField('Cache hit', default=False)
    meta_json = models.JSONField('Meta', default=dict, blank=True)
    created_at = models.DateTimeField('Vytvorené', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'AI kredit transakcia'
        verbose_name_plural = 'AI kredit transakcie'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['event_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user_id} | {self.event_type} | {self.credits_delta}"


class AIDayReportDailyStat(models.Model):
    """Agregované denné metriky endpointu AI hodnotenia dňa."""

    stat_date = models.DateField('Dátum', db_index=True)
    model_ref = models.CharField('Model', max_length=120, db_index=True)
    total_requests = models.PositiveIntegerField('Počet requestov', default=0)
    cache_hits = models.PositiveIntegerField('Cache hity', default=0)
    generated_reports = models.PositiveIntegerField('Nové generovania', default=0)
    fallback_reports = models.PositiveIntegerField('Fallback odpovede', default=0)
    errors_count = models.PositiveIntegerField('Chyby endpointu', default=0)
    updated_at = models.DateTimeField('Aktualizované', auto_now=True)

    class Meta:
        verbose_name = 'AI hodnotenie dňa štatistika'
        verbose_name_plural = 'AI hodnotenie dňa štatistiky'
        ordering = ['-stat_date', 'model_ref']
        constraints = [
            models.UniqueConstraint(
                fields=['stat_date', 'model_ref'],
                name='uniq_ai_day_stats_date_model',
            ),
        ]

    def __str__(self):
        return f"{self.stat_date} | {self.model_ref} | req={self.total_requests}"


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

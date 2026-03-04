# Pochop.sk

Astrologická web aplikácia v Django: výpočty tranzitov + AI interpretácia (`AI Hodnotenie dňa`, `Astrologický rozbor okamihu`).

## Stack
- Django 6
- Swiss Ephemeris (`pyswisseph`)
- Vercel AI Gateway (jediný runtime transport pre AI volania)
- SQLite (default)

## Quick Start
1. `cp .env.example .env`
2. Vyplň `.env`:
   - `SECRET_KEY`
   - `VERCEL_AI_GATEWAY_API_KEY`
   - `DEFAULT_MODEL` (napr. `openai/gpt-5.2` alebo `google/gemini-2.5-pro`)
   - `AI_FORCE_VERCEL_GATEWAY=True`
  - `PII_ENCRYPTION_PASSWORD` (fallback/legacy, nepoužíva sa pre user-password PII flow)
3. `python -m venv venv && source venv/bin/activate`
4. `pip install -r requirements.txt`
5. `python manage.py migrate`
6. `python manage.py createsuperuser`
7. `python manage.py runserver`

## AI Model Routing
- Runtime ide cez Vercel AI Gateway.
- `DEFAULT_MODEL` určuje gateway model (`owner/model`).
- Odporúčaný formát:
  - `openai/gpt-5.2`
  - `google/gemini-2.5-pro`
  - `anthropic/claude-3.7-sonnet`
- Legacy formáty (`openai:...`, `gemini:...`, `vercel:...`) sú stále podporené kvôli spätnej kompatibilite.

V adminovi (`AI konfigurácia`) vieš meniť:
- `DEFAULT_MODEL`
- `Max API calls denne`
- `Max modelov v porovnaní` (limit pre compare režim v timeline/natal + `refresh_to_cache`)

API kľúče sa už **neukladajú do DB**. Čítajú sa iba z `.env`.

## Geolocation API (GPS / City / IP)
- `POST /api/location/reverse` body: `{"lat": 48.1486, "lon": 17.1077}`
  - response: `{"country","city","region","postcode"}`
- `POST /api/location/forward` body: `{"country":"Slovensko","city":"Bratislava","region":"Bratislavský kraj"}`
  - response: `{"lat","lon","country","city","region"}`
- `GET /api/location/from-ip`
  - response: `{"country","city","region","lat","lon"}` alebo `204 No Content`

Použité služby:
- reverse/forward: OpenStreetMap Nominatim cez `geopy` (`transits/services/geocoding.py`)
- IP fallback: `ipapi.co` (`transits/services/ip_geo.py`)
- nearest city pre GPS: lokálna DB `SlovakCity` (`transits/services/city_lookup.py`)

Rate limit + retry:
- Nominatim má minimálny rozostup volaní `>= 1s`, custom `User-Agent`, retry + backoff pri `429/5xx`.
- Výsledky geocodingu/IP sú cacheované do DB (`LocationLookupCache`) + Django cache.
- Cache je scoped per lookup/per deň (max 1 externý lookup na rovnaký kľúč za deň).
- Pri `from-ip` (Slovensko) sa city doplní podľa najbližšej obce ku GPS.

### ENV premenné (geolocation)
- `GEOCODING_USER_AGENT=pochop.sk-geocoder/1.0`
- `GEOCODING_TIMEOUT_SECONDS=5`
- `GEOCODING_MIN_DELAY_SECONDS=1.0`
- `GEOCODING_MAX_RETRIES=3`
- `GEOCODING_RETRY_BACKOFF_SECONDS=1.0`
- `GEOCODING_CACHE_TTL_SECONDS=86400`
- `GEOCODING_REVERSE_PRECISION=5`
- `GEOCODING_PROVIDER_CLASS=` (voliteľné, dotted path pre custom provider)
- `IP_GEO_URL_TEMPLATE=https://ipapi.co/{ip}/json/`
- `IP_GEO_USER_AGENT=pochop.sk-ipgeo/1.0`
- `IP_GEO_CONNECT_TIMEOUT_SECONDS=3`
- `IP_GEO_READ_TIMEOUT_SECONDS=5`
- `IP_GEO_MAX_RETRIES=3`
- `IP_GEO_RETRY_BACKOFF_SECONDS=1.0`
- `IP_GEO_CACHE_TTL_SECONDS=86400`

## Astrologický rozbor okamihu podľa GPS
- `MomentReport` je cacheovaný per:
  - `report_date`
  - `model_ref`
  - `location_key` (zaokrúhlené `lat/lon`)
- Verejnú stránku `/okamih/` vieš volať aj s lokalitou:
  - `/okamih/?lat=48.1486&lon=17.1077&city=Bratislava&country=Slovensko`
- Ak parametre chýbajú, použije sa default `Bratislava, Slovensko`.

### Frontend snippet (GPS -> reverse, fallback na IP)
```html
<script>
async function detectLocation() {
  const reverseUrl = '/api/location/reverse';
  const ipUrl = '/api/location/from-ip';

  const fromIp = async () => {
    const r = await fetch(ipUrl, { credentials: 'same-origin' });
    if (r.status === 204) return null;
    if (!r.ok) return null;
    return r.json();
  };

  if (!navigator.geolocation) return fromIp();

  try {
    const pos = await new Promise((resolve, reject) =>
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: false,
        timeout: 8000,
        maximumAge: 300000
      })
    );

    const csrf = document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.split('=')[1] || '';
    const r = await fetch(reverseUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ lat: pos.coords.latitude, lon: pos.coords.longitude })
    });
    if (!r.ok) return fromIp();
    return r.json();
  } catch {
    return fromIp();
  }
}
</script>
```

### Redis cache (odporúčané)
V `settings.py` môžeš prepnúť default cache na Redis:
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

## Vercel AI Gateway (Admin katalog modelov)
- Admin vie zosynchronizovať modely z Vercel AI Gateway do `AI modely`:
  - v Django admine je tlačidlo `Sync Vercel Models` na stránke AI modelov.
- Každý model má:
  - `Zdroj` (`manual` / `vercel`)
  - `Dostupný v katalógu`
  - `Len pre Pro účty`
  - `Aktívny` (model sa používa v dropdown-e, compare režime a refresh_to_cache)
- Pro-only modely sú dostupné len pre Pro účty (alebo staff).

## Privacy / Security
- Citlivé birth údaje (`birth_date`, `birth_time`, `birth_place`, `birth_lat`, `birth_lon`) sú ukladané šifrovane per-user heslom.
- Dešifrovanie prebieha po login-e (session unlock key odvodený z hesla používateľa).
- Plain PII fields sú nulované.
- Pri zmene hesla sa PII automaticky prešifruje novým heslom (bez straty dát).
- Pri reset-e hesla cez e-mail sa použije recovery envelope a následne sa PII tiež prešifruje novým heslom.
- Analýzy ostávajú čitateľné, ale profil má pseudonym `public_hash`.
- Registrácia vyžaduje validný e-mail.
- Nový účet je aktivovaný až po potvrdení e-mailu (verifikačný odkaz).

## Management Commands
- Rychly refresh po manualnych zmenach:
  - `bash deploy/refresh.sh`
  - `bash deploy/refresh.sh --with-migrate` (ak si menil modely/migracie)
  - default obsahuje aj AI warmup (`sync_vercel_models` + `refresh_to_cache` s global natal + moment)
  - ak chceš iba rýchly reload bez AI warmupu: `bash deploy/refresh.sh --skip-ai-warmup`
- Synchronizácia Vercel modelov:
  - `python manage.py sync_vercel_models`
  - `python manage.py sync_vercel_models --enable-new --new-for-free`
- Refresh lazy cache pre natálne analýzy + AI day report:
  - `python manage.py refresh_to_cache --profiles pro --days 0,1,2`
  - `python manage.py refresh_to_cache --profiles all --days 0 --invalidate`
  - moment warmup je cache-first (`force` len pri `--invalidate`)
  - plný warmup vrátane globálnych natálnych analýz a moment reportu:
    - `python manage.py refresh_to_cache --profiles all --days 0,1,2 --with-global-natal --with-moment --moment-days 0,1`
  - shortcut script: `bash deploy/refresh_to_cache.sh --profiles pro --days 0,1,2`
- Zmena modelu + refresh:
  - `python manage.py change_model --model openai/gpt-5.2`
- Verejný denný report:
  - `python manage.py generate_moment_report --force`
  - `python manage.py generate_moment_report --force --email-admin`
  - `python manage.py generate_moment_report --force --email-admin --to tvoj@email.sk` (fallback, ak `ADMIN_EMAIL` nie je nastavený)
- SMTP diagnostika:
  - `python manage.py smtp_diagnose` (test pripojenia)
  - `python manage.py smtp_diagnose --to tvoj@email.sk` (test reálneho doručenia)
- Anonymizácia DB pre GitHub:
  - `python manage.py anonymize_for_github --yes`
  - Poznámka: command mení DB in-place a nastaví user účty na neprihlásiteľné.
- Safe public snapshot DB (bez zásahu do live DB):
  - `python manage.py create_public_snapshot --output snapshots/db_public.sqlite3 --overwrite`

## Open Source Notes
- `.env` je v `.gitignore`.
- `db.sqlite3` je v `.gitignore` (aby sa live DB omylom nepushla).
- Pred pushom DB do verejného repozitára spusti `anonymize_for_github --yes`.
- Admin nightly e-mail pre moment report:
  - nastav `ADMIN_EMAIL=tvoj@email.sk`,
  - report sa odosiela iba na túto adresu.

## Backup + VPS Migrácia
- Ak chceš mať kompletný backup aj s `db.sqlite3`, používaj privátny repozitár.
- Pre verejný repozitár vždy najprv anonymizuj DB: `python manage.py anonymize_for_github --yes`.
- Odporúčaný public flow (safe):
  - `bash deploy/prepare_public_backup.sh`
  - script vytvorí anonymizovaný snapshot `snapshots/db_public.sqlite3` bez zásahu do produkčnej DB.
- Prenos na nový VPS po `git pull`:
  - `bash deploy/init_after_pull.sh`
- Script `deploy/init_after_pull.sh` spraví:
  - ak chýba `.env`, skopíruje `.env.example`,
  - ak chýba `db.sqlite3` a existuje `snapshots/db_public.sqlite3`, použije tento snapshot,
  - inštaláciu dependencies,
  - `migrate`, `collectstatic`,
  - `populate_transits`, `populate_cities`,
  - prewarm `generate_moment_report --force --email-admin`,
  - restart `pochop.service` a `pochop-moment.timer` (ak je dostupný `systemctl`).

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

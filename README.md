# Pochop.sk

Astrologická web aplikácia v Django: výpočty tranzitov + AI interpretácia (`AI Hodnotenie dňa`, `Astrologický rozbor okamihu`).

## Stack
- Django 6
- Swiss Ephemeris (`pyswisseph`)
- Gemini + OpenAI (prepínateľné cez `DEFAULT_MODEL`)
- SQLite (default)

## Quick Start
1. `cp .env.example .env`
2. Vyplň `.env`:
   - `SECRET_KEY`
   - `GEMINI_API_KEY` a/alebo `OPENAI_API_KEY`
   - `DEFAULT_MODEL` (napr. `gemini-3.1-pro-preview` alebo `openai:gpt-4.1-mini`)
  - `PII_ENCRYPTION_PASSWORD` (fallback/legacy, nepoužíva sa pre user-password PII flow)
3. `python -m venv venv && source venv/bin/activate`
4. `pip install -r requirements.txt`
5. `python manage.py migrate`
6. `python manage.py createsuperuser`
7. `python manage.py runserver`

## AI Model Routing
- `DEFAULT_MODEL` určuje provider aj model.
- Podporované formáty:
  - `gemini-3.1-pro-preview`
  - `openai:gpt-4.1-mini`
  - `openai` (použije `OPENAI_MODEL`)
  - `gemini` (použije `GEMINI_MODEL`)

V adminovi (`AI konfigurácia`) vieš meniť:
- `DEFAULT_MODEL`
- `Max API calls denne`

API kľúče sa už **neukladajú do DB**. Čítajú sa iba z `.env`.

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
- Zmena modelu + refresh:
  - `python manage.py change_model --model openai:gpt-4.1-mini`
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

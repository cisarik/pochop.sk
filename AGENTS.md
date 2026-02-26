# Pochop.sk Agent Notes

## North Star
- This is an astrology product.
- Core value is not only transit calculation, but also high-quality AI astrology interpretation for users.
- Two critical user-facing features must stay healthy:
  - `AI Hodnotenie dňa`
  - `Astrologický rozbor okamihu`

## Engineering Priorities
- Preserve correctness of algorithmic astrology calculations (time/place sensitive).
- Ensure AI output is always usable:
  - never return empty sections,
  - apply parser + fallback safeguards when model output is malformed.
- Prefer structured JSON outputs from model prompts for critical flows (`AI Hodnotenie dňa`, `Rozbor okamihu`), then validate and sanitize before render.
- Keep AI integrations provider-agnostic (Gemini/OpenAI now, easy extension later).
- Protect reliability and cost:
  - respect daily AI call limits,
  - show graceful outage state when quota is exceeded.

## When Changing AI Model
- Validate model availability with a real API call.
- Refresh cached/generated AI content after model switches:
  - user natal analyses,
  - daily moment report.

## Secrets Policy
- Never store API keys in DB.
- API keys must come from environment (`.env` / deployment secrets).

## PII Policy
- Birth PII is encrypted per user password (not with a global app password).
- Keep plain PII fields empty/null.
- For OSS database publishing, run anonymization command before push.

## Public Backup Policy
- Never commit live `db.sqlite3` to public repo.
- Use public-safe snapshot flow:
  - `bash deploy/prepare_public_backup.sh`
  - commit `snapshots/db_public.sqlite3` only.
- For VPS restore after `git pull`, use:
  - `bash deploy/init_after_pull.sh`
  - this bootstrap script is the source of truth for first-run init.

## Moment Report Location
- `Astrologický rozbor okamihu` is anchored to Bratislava.
- Keep location context explicit in prompts and output:
  - `Bratislava, Slovensko`
  - `lat: 48.1486`
  - `lon: 17.1077`

## UX Consistency
- Keep the wheel visual language consistent between landing, `/okamih/`, and e-mail snapshot.
- Planet glyphs are rendered without filled planet circles (symbol-first style).

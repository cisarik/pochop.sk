from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from transits.gemini_utils import generate_ai_text, has_ai_key
from transits.models import GeminiConfig, NatalProfile
from transits.moment_service import get_or_generate_moment_report
from transits.views import _generate_and_save_analyses


def _upsert_env_var(env_path: Path, key: str, value: str):
    line = f"{key}={value}"
    if not env_path.exists():
        env_path.write_text(line + "\n", encoding="utf-8")
        return

    raw = env_path.read_text(encoding="utf-8")
    rows = raw.splitlines()
    replaced = False
    for i, row in enumerate(rows):
        if row.startswith(f"{key}="):
            rows[i] = line
            replaced = True
            break
    if not replaced:
        if rows and rows[-1].strip():
            rows.append("")
        rows.append(line)
    env_path.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")


class Command(BaseCommand):
    help = (
        "Zmení aktívny DEFAULT_MODEL, otestuje API spojenie a "
        "zregeneruje používateľské analýzy + moment report."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            type=str,
            default=getattr(settings, "DEFAULT_MODEL", "gemini-3.1-pro-preview"),
            help="Nový model (napr. gemini-3.1-pro-preview alebo openai:gpt-4.1-mini).",
        )
        parser.add_argument(
            "--skip-users-refresh",
            action="store_true",
            help="Preskočí regeneráciu natálnych analýz používateľov.",
        )
        parser.add_argument(
            "--skip-moment-refresh",
            action="store_true",
            help="Preskočí regeneráciu verejného reportu okamihu.",
        )
    def _test_connection(self, model_name):
        if not has_ai_key(model_name=model_name):
            raise CommandError("API key pre vybraný model/provider nie je nakonfigurovaný v .env.")
        try:
            last_text = generate_ai_text(
                model_name=model_name,
                contents="Vrat presne text: OK",
                system_instruction="Odpovedz iba jedným slovom: OK",
                temperature=0,
                max_output_tokens=8,
            )
            display = last_text if last_text else "(prázdna textová odpoveď, ale volanie prebehlo)"
            self.stdout.write(self.style.SUCCESS(f"API test OK: {display}"))
        except Exception as exc:
            raise CommandError(f"Gemini API test zlyhal: {exc}") from exc

    def handle(self, *args, **options):
        model_name = options["model"].strip()
        if not model_name:
            raise CommandError("Model nemôže byť prázdny.")

        self.stdout.write(f"Mením DEFAULT_MODEL na: {model_name}")
        self._test_connection(model_name)

        env_path = Path(settings.BASE_DIR) / ".env"
        _upsert_env_var(env_path, "DEFAULT_MODEL", model_name)
        self.stdout.write(self.style.SUCCESS(f"Uložené do .env: DEFAULT_MODEL={model_name}"))

        cfg, _ = GeminiConfig.objects.get_or_create(id=1)
        cfg.default_model = model_name
        cfg.save(update_fields=["default_model", "updated_at"])
        self.stdout.write(self.style.SUCCESS("Aktualizované aj v admin AI konfigurácii."))

        if not options.get("skip_users_refresh"):
            total = NatalProfile.objects.count()
            ok = 0
            fail = 0
            self.stdout.write(f"Regenerujem analýzy používateľov: {total}")
            for profile in NatalProfile.objects.all().iterator():
                if _generate_and_save_analyses(profile, model_name=model_name):
                    ok += 1
                else:
                    fail += 1
            self.stdout.write(
                self.style.SUCCESS(f"Refresh users dokončený. OK={ok}, FAIL={fail}")
            )

        if not options.get("skip_moment_refresh"):
            report = get_or_generate_moment_report(force=True, model_name=model_name)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Moment report regen OK pre {report.report_date} (id={report.id})"
                )
            )

        self.stdout.write(
            self.style.WARNING(
                "Ak beží web server, reštartni službu pre načítanie nového DEFAULT_MODEL z .env."
            )
        )

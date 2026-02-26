from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from transits.moment_service import get_or_generate_moment_report
from transits.moment_notifications import (
    collect_admin_report_recipients,
    send_daily_moment_report_email,
)


class Command(BaseCommand):
    help = "Vygeneruje verejný denný astrologický rozbor okamihu (s cache do DB)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Dátum vo formáte YYYY-MM-DD (default: dnes v Europe/Bratislava).',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Prepíše už existujúci report pre daný deň.',
        )
        parser.add_argument(
            '--model',
            type=str,
            help='Voliteľný model override pre tento run (napr. openai:gpt-4.1-mini).',
        )
        parser.add_argument(
            '--email-admin',
            action='store_true',
            help='Po vygenerovaní odošle admin e-mail so snapshotom reportu.',
        )
        parser.add_argument(
            '--to',
            action='append',
            default=[],
            help='Voliteľný príjemca navyše (možno použiť viackrát alebo oddeliť čiarkou).',
        )

    def handle(self, *args, **options):
        target_date = None
        if options.get('date'):
            try:
                target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError as exc:
                raise CommandError('Neplatný formát dátumu. Použi YYYY-MM-DD.') from exc

        report = get_or_generate_moment_report(
            report_date=target_date,
            force=options.get('force', False),
            model_name=options.get('model'),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Moment report pripravený pre {report.report_date} (id={report.id})"
            )
        )

        if options.get('email_admin'):
            recipients = collect_admin_report_recipients(extra=options.get('to') or [])
            if not recipients:
                self.stdout.write(
                    self.style.WARNING(
                        'Admin e-mail nebol odoslaný: nenašli sa žiadni príjemcovia.'
                    )
                )
                return
            sent = send_daily_moment_report_email(report=report, recipients=recipients)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Admin e-mail odoslaný ({sent}) na: {", ".join(recipients)}'
                )
            )

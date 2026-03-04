from django.core.management.base import BaseCommand, CommandError

from transits.vercel_gateway import VercelGatewaySyncError, sync_vercel_models


class Command(BaseCommand):
    help = "Synchronizuje katalóg modelov z Vercel AI Gateway do AIModelOption."

    def add_arguments(self, parser):
        parser.add_argument(
            '--enable-new',
            action='store_true',
            help='Nové modely hneď zapne (is_enabled=True).',
        )
        parser.add_argument(
            '--new-for-free',
            action='store_true',
            help='Nové modely neoznačí ako Pro-only.',
        )
        parser.add_argument(
            '--keep-missing',
            action='store_true',
            help='Modely, ktoré zmizli z Vercel katalógu, nedeaktivuje.',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=25,
            help='HTTP timeout pre Vercel sync v sekundách (default: 25).',
        )

    def handle(self, *args, **options):
        try:
            stats = sync_vercel_models(
                disable_missing=not bool(options.get('keep_missing')),
                enable_new=bool(options.get('enable_new')),
                pro_only_for_new=not bool(options.get('new_for_free')),
                timeout_seconds=max(5, int(options.get('timeout') or 25)),
            )
        except VercelGatewaySyncError as exc:
            raise CommandError(f"Vercel sync zlyhal: {exc}") from exc
        except Exception as exc:
            raise CommandError(f"Neočakávaná chyba syncu: {exc}") from exc

        self.stdout.write(self.style.SUCCESS('Vercel sync dokončený.'))
        self.stdout.write(
            (
                f"remote={stats.get('total_remote')} "
                f"created={stats.get('created')} "
                f"updated={stats.get('updated')} "
                f"unchanged={stats.get('unchanged')} "
                f"missing={stats.get('missing')}"
            )
        )

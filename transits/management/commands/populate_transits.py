"""
Management command na naplnenie databázy tranzitových výkladov.
Spustenie: python manage.py populate_transits
"""

from django.core.management.base import BaseCommand
from transits.models import TransitAspect
from transits.transit_data import TRANSIT_DATA


class Command(BaseCommand):
    help = 'Naplní databázu výkladmi tranzitových aspektov v slovenčine'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Vymaže existujúce záznamy pred naplnením',
        )

    def handle(self, *args, **options):
        if options['reset']:
            count = TransitAspect.objects.count()
            TransitAspect.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f'Vymazaných {count} existujúcich záznamov.')
            )

        created = 0
        updated = 0

        for transit_planet, natal_planet, aspect_type, effect, text_sk in TRANSIT_DATA:
            obj, was_created = TransitAspect.objects.update_or_create(
                transit_planet=transit_planet,
                natal_planet=natal_planet,
                aspect_type=aspect_type,
                defaults={
                    'effect': effect,
                    'default_text': text_sk,
                }
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Hotovo! Vytvorených: {created}, aktualizovaných: {updated}. '
                f'Celkom záznamov: {TransitAspect.objects.count()}'
            )
        )

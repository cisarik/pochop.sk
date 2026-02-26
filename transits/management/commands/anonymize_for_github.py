import hashlib

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from transits.models import NatalProfile


class Command(BaseCommand):
    help = (
        "Anonymizuje databázu pre open-source zdieľanie: "
        "odpojí profily od používateľov, anonymizuje usernames a vyčistí sessions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Potvrdí, že chceš vykonať anonymizáciu in-place.',
        )
        parser.add_argument(
            '--keep-users-linked',
            action='store_true',
            help='Neodpájať profily od user účtov.',
        )

    @staticmethod
    def _anon_username(user_id, username):
        payload = f'{user_id}:{username}'.encode('utf-8')
        return f"user_{hashlib.sha256(payload).hexdigest()[:16]}"

    @staticmethod
    def _anon_profile_name(public_hash):
        token = (public_hash or 'profile')[:10]
        return f"profile_{token}"

    def handle(self, *args, **options):
        if not options.get('yes'):
            raise CommandError("Tento command mení DB in-place. Spusti ho s --yes.")

        keep_users_linked = options.get('keep_users_linked', False)

        with transaction.atomic():
            # 1) Anonymize users.
            for user in User.objects.all().iterator():
                user.username = self._anon_username(user.id, user.username)
                user.email = ''
                user.first_name = ''
                user.last_name = ''
                # Pre OSS snapshot nech sú účty neprihlásiteľné.
                user.set_unusable_password()
                user.save(update_fields=['username', 'email', 'first_name', 'last_name', 'password'])

            # 2) Anonymize profiles and remove residual plain PII fields.
            for profile in NatalProfile.objects.all().iterator():
                profile.name = self._anon_profile_name(profile.public_hash)
                profile.birth_date = None
                profile.birth_time = None
                profile.birth_place = None
                profile.birth_lat = None
                profile.birth_lon = None
                profile.birth_data_recovery_encrypted = ''
                if not keep_users_linked:
                    profile.user = None
                    profile.save(update_fields=[
                        'name',
                        'birth_date',
                        'birth_time',
                        'birth_place',
                        'birth_lat',
                        'birth_lon',
                        'birth_data_recovery_encrypted',
                        'user',
                        'updated_at',
                    ])
                else:
                    profile.save(update_fields=[
                        'name',
                        'birth_date',
                        'birth_time',
                        'birth_place',
                        'birth_lat',
                        'birth_lon',
                        'birth_data_recovery_encrypted',
                        'updated_at',
                    ])

            # 3) Remove live sessions and admin logs (low value in OSS snapshot).
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM django_session")
                cursor.execute("DELETE FROM django_admin_log")

        self.stdout.write(self.style.SUCCESS("Anonymizácia databázy dokončená."))

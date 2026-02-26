import hashlib
import shutil
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Vytvorí anonymizovaný SQLite snapshot vhodný na public GitHub backup, "
        "bez zásahu do live DB."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default='snapshots/db_public.sqlite3',
            help='Cesta výstupného anonymizovaného snapshotu.',
        )
        parser.add_argument(
            '--source',
            default='',
            help='Voliteľná source DB cesta (default: DATABASES[default][NAME]).',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Prepíše existujúci output súbor.',
        )

    @staticmethod
    def _anon_username(user_id, username):
        payload = f'{user_id}:{username}'.encode('utf-8')
        return f"user_{hashlib.sha256(payload).hexdigest()[:16]}"

    @staticmethod
    def _anon_profile_name(public_hash, profile_id):
        token = (public_hash or f'profile_{profile_id}')[:10]
        return f"profile_{token}"

    def handle(self, *args, **options):
        src = Path(options['source'] or settings.DATABASES['default']['NAME'])
        dst = Path(options['output'])

        if not src.exists():
            raise CommandError(f"Source DB neexistuje: {src}")

        if dst.exists() and not options.get('overwrite'):
            raise CommandError(f"Output už existuje: {dst}. Použi --overwrite.")

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        conn = sqlite3.connect(str(dst))
        conn.row_factory = sqlite3.Row

        try:
            cur = conn.cursor()

            # 1) auth_user anonymize
            try:
                users = cur.execute('SELECT id, username FROM auth_user').fetchall()
                for user in users:
                    anon_username = self._anon_username(user['id'], user['username'] or '')
                    cur.execute(
                        '''
                        UPDATE auth_user
                           SET username = ?,
                               email = '',
                               first_name = '',
                               last_name = '',
                               password = '!' || substr(hex(randomblob(8)), 1, 8)
                         WHERE id = ?
                        ''',
                        (anon_username, user['id']),
                    )
            except sqlite3.OperationalError:
                pass

            # 2) Natal profiles anonymize
            try:
                profiles = cur.execute(
                    'SELECT id, public_hash FROM transits_natalprofile'
                ).fetchall()
                for profile in profiles:
                    anon_name = self._anon_profile_name(profile['public_hash'], profile['id'])
                    cur.execute(
                        '''
                        UPDATE transits_natalprofile
                           SET name = ?,
                               user_id = NULL,
                               birth_date = NULL,
                               birth_time = NULL,
                               birth_place = NULL,
                               birth_lat = NULL,
                               birth_lon = NULL,
                               birth_data_recovery_encrypted = ''
                         WHERE id = ?
                        ''',
                        (anon_name, profile['id']),
                    )
            except sqlite3.OperationalError:
                pass

            # 3) low-value runtime data
            for table in ('django_session', 'django_admin_log'):
                try:
                    cur.execute(f'DELETE FROM {table}')
                except sqlite3.OperationalError:
                    pass

            conn.commit()
            cur.execute('VACUUM')
        finally:
            conn.close()

        self.stdout.write(self.style.SUCCESS(f"Public snapshot pripravený: {dst}"))

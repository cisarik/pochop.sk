import socket
import ssl
from smtplib import SMTPAuthenticationError, SMTPConnectError, SMTPException

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.mail import EmailMultiAlternatives, get_connection


class Command(BaseCommand):
    help = (
        "Diagnostika SMTP konfigurácie. Vie otestovať pripojenie na server a "
        "voliteľne poslať testovací e-mail."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            type=str,
            default='',
            help='Príjemca testovacieho e-mailu (ak nie je zadaný, testuje sa len connection).',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=20,
            help='SMTP timeout v sekundách (default: 20).',
        )
        parser.add_argument(
            '--subject',
            type=str,
            default='Pochop.sk SMTP test',
            help='Predmet testovacieho e-mailu.',
        )
        parser.add_argument(
            '--body',
            type=str,
            default='Toto je test doručenia SMTP z Pochop.sk.',
            help='Text testovacieho e-mailu.',
        )

    def handle(self, *args, **options):
        recipient = (options.get('to') or '').strip()
        timeout = int(options.get('timeout') or 20)
        subject = options.get('subject') or 'Pochop.sk SMTP test'
        body = options.get('body') or 'Toto je test doručenia SMTP z Pochop.sk.'

        backend = getattr(settings, 'EMAIL_BACKEND', '')
        host = getattr(settings, 'EMAIL_HOST', '')
        port = int(getattr(settings, 'EMAIL_PORT', 0) or 0)
        user = getattr(settings, 'EMAIL_HOST_USER', '')
        use_tls = bool(getattr(settings, 'EMAIL_USE_TLS', False))
        use_ssl = bool(getattr(settings, 'EMAIL_USE_SSL', False))
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '')

        self.stdout.write('SMTP diagnostika')
        self.stdout.write(f'- EMAIL_BACKEND: {backend}')
        self.stdout.write(f'- EMAIL_HOST: {host}')
        self.stdout.write(f'- EMAIL_PORT: {port}')
        self.stdout.write(f'- EMAIL_HOST_USER: {"set" if user else "missing"}')
        self.stdout.write(f'- EMAIL_HOST_PASSWORD: {"set" if bool(getattr(settings, "EMAIL_HOST_PASSWORD", "")) else "missing"}')
        self.stdout.write(f'- EMAIL_USE_TLS: {use_tls}')
        self.stdout.write(f'- EMAIL_USE_SSL: {use_ssl}')
        self.stdout.write(f'- DEFAULT_FROM_EMAIL: {from_email}')

        if backend != 'django.core.mail.backends.smtp.EmailBackend':
            raise CommandError(
                'EMAIL_BACKEND nie je SMTP backend. '
                'Nastav v .env EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend '
                'a reštartuj službu.'
            )

        if not host or not port:
            raise CommandError('EMAIL_HOST/EMAIL_PORT nie sú správne nastavené.')

        if use_tls and use_ssl:
            raise CommandError('EMAIL_USE_TLS a EMAIL_USE_SSL nemôžu byť zapnuté naraz.')

        connection = get_connection(timeout=timeout)
        try:
            opened = connection.open()
            if opened is False:
                raise CommandError('SMTP connection.open() vrátil False.')
            self.stdout.write(self.style.SUCCESS('SMTP pripojenie: OK'))

            if recipient:
                message = EmailMultiAlternatives(
                    subject=subject,
                    body=body,
                    from_email=from_email,
                    to=[recipient],
                    connection=connection,
                )
                sent_count = message.send(fail_silently=False)
                if sent_count != 1:
                    raise CommandError(
                        f'Očakával sa 1 odoslaný e-mail, odoslané: {sent_count}'
                    )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Testovací e-mail bol odoslaný na {recipient}.'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        'Connection test prebehol, ale e-mail sa neposielal '
                        '(chýba --to).'
                    )
                )

        except SMTPAuthenticationError as exc:
            raise CommandError(
                f'SMTP auth chyba ({exc.smtp_code}): {exc.smtp_error!r}. '
                'Skontroluj username/password, app password a 2FA nastavenia.'
            )
        except (SMTPConnectError, SMTPException) as exc:
            raise CommandError(f'SMTP chyba: {exc!r}')
        except ssl.SSLError as exc:
            raise CommandError(
                f'TLS/SSL handshake chyba: {exc!r}. '
                'Skontroluj EMAIL_USE_TLS/EMAIL_USE_SSL a port (587 vs 465).'
            )
        except socket.gaierror as exc:
            raise CommandError(f'DNS chyba pre EMAIL_HOST: {exc!r}')
        except TimeoutError as exc:
            raise CommandError(f'Timeout pri pripájaní na SMTP server: {exc!r}')
        finally:
            try:
                connection.close()
            except Exception:
                pass

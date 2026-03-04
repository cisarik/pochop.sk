import json
import os
import re
from types import SimpleNamespace
from datetime import date, time, datetime, timedelta
from django.core import mail
from io import StringIO
from unittest.mock import MagicMock, patch
from unittest import skipUnless

from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone

from .engine import calculate_natal_chart, calculate_natal_positions, get_timezone_for_location
from .gemini_utils import GeminiLimitExceededError, generate_ai_text, parse_json_payload
from .moment_service import enrich_moment_aspects_with_text, get_or_generate_moment_report
from .models import (
    AIDayReportCache,
    AIDayReportDailyStat,
    AINatalAnalysisCache,
    AIModelOption,
    AIResponseCache,
    GeminiConfig,
    MomentReport,
    NatalProfile,
    SlovakCity,
    UserProStatus,
)
from .security import derive_user_key_b64
from .vercel_gateway import sync_vercel_models
from .views import _generate_natal_analyses_payload


class IndexSecurityUxTests(TestCase):
    def test_index_contains_security_explanation(self):
        client = Client(HTTP_HOST='pochop.sk')
        response = client.get(reverse('transits:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bezpečnosť citlivých údajov')
        self.assertContains(response, 'šifrovane')

    def test_index_shows_active_model_from_admin_config(self):
        GeminiConfig.objects.create(default_model='openai:gpt-5.2', max_calls_daily=500)
        client = Client(HTTP_HOST='pochop.sk')
        response = client.get(reverse('transits:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Vercel AI Gateway gpt-5.2')

    def test_index_renders_cached_moment_wheel(self):
        MomentReport.objects.create(
            report_date=date.today(),
            timezone='Europe/Bratislava',
            planets_json=[
                {
                    'key': 'sun',
                    'name_sk': 'Slnko',
                    'symbol': '☉',
                    'longitude': 124.5,
                    'longitude_deg': 4.5,
                    'sign': 'Lev',
                    'sign_symbol': '♌',
                    'retrograde': False,
                }
            ],
            aspects_json=[],
            ai_report_json={'rating': 6, 'energy': 'Test'},
        )
        client = Client(HTTP_HOST='pochop.sk')
        response = client.get(reverse('transits:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Aktuálne planetárne usporiadanie')
        self.assertContains(response, 'landingMomentWheel')

    def test_index_shows_locked_hint_for_non_pro(self):
        client = Client(HTTP_HOST='pochop.sk')
        response = client.get(reverse('transits:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Model compare dostupný len pre Pro')

    def test_index_nav_model_trigger_uses_plain_model_label(self):
        GeminiConfig.objects.create(default_model='openai:gpt-5.2', max_calls_daily=500)
        AIModelOption.objects.update_or_create(
            model_ref='openai:gpt-5.2',
            defaults={
                'label': 'GPT-5.2',
                'is_enabled': True,
                'is_available': True,
                'sort_order': 10,
            },
        )

        client = Client(HTTP_HOST='pochop.sk')
        response = client.get(reverse('transits:index'))
        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.content.decode('utf-8'),
            r'<span class="nav-ai-trigger-model">\s*GPT-5\.2\s*</span>',
        )

    def test_index_adds_pro_dropdown_skin_for_pro_user(self):
        GeminiConfig.objects.create(default_model='openai:gpt-5.2', max_calls_daily=500)
        AIModelOption.objects.update_or_create(
            model_ref='openai:gpt-5.2',
            defaults={
                'label': 'GPT-5.2',
                'is_enabled': True,
                'is_available': True,
                'sort_order': 10,
            },
        )
        pro_user = User.objects.create_user(
            username='header_pro_user',
            email='header_pro_user@example.com',
            password='StrongPass123!',
        )
        UserProStatus.objects.create(user=pro_user, is_pro=True)

        client = Client(HTTP_HOST='pochop.sk')
        client.force_login(pro_user)
        response = client.get(reverse('transits:index'))
        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.content.decode('utf-8'),
            r'class="nav-ai nav-ai--tagline nav-ai--pro"',
        )


class UserAdminProVisibilityTests(TestCase):
    def test_user_admin_exposes_pro_column(self):
        user_admin = django_admin.site._registry[User]
        self.assertIn('pro_account', user_admin.list_display)
        self.assertIn('pro_status__is_pro', user_admin.list_filter)

    def test_user_admin_pro_column_uses_user_pro_status(self):
        user = User.objects.create_user(
            username='admin_user_pro_col',
            email='admin_user_pro_col@example.com',
            password='StrongPass123!',
        )
        user_admin = django_admin.site._registry[User]
        self.assertFalse(user_admin.pro_account(user))

        UserProStatus.objects.create(user=user, is_pro=True)
        user.refresh_from_db()
        self.assertTrue(user_admin.pro_account(user))


class AIModelSwitchApiTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='staff_user',
            email='staff@example.com',
            password='StrongPass123!',
            is_staff=True,
            is_superuser=True,
        )
        self.user = User.objects.create_user(
            username='regular_user',
            email='regular@example.com',
            password='StrongPass123!',
        )
        AIModelOption.objects.update_or_create(
            model_ref='openai:gpt-5.2',
            defaults={'label': 'GPT-5.2', 'sort_order': 10, 'is_enabled': True},
        )
        AIModelOption.objects.update_or_create(
            model_ref='gemini:gemini-2.5-pro',
            defaults={'label': 'Gemini Pro 2.5', 'sort_order': 20, 'is_enabled': True},
        )
        GeminiConfig.objects.update_or_create(
            id=1,
            defaults={'default_model': 'openai:gpt-5.2', 'max_calls_daily': 500},
        )

    def test_requires_staff_or_pro_permissions(self):
        client = Client(HTTP_HOST='pochop.sk')
        client.force_login(self.user)
        response = client.post(
            reverse('transits:api_select_ai_model'),
            data=json.dumps({'model_ref': 'gemini:gemini-2.5-pro'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    @patch('transits.views._generate_and_save_analyses')
    @patch('transits.views.has_ai_key')
    def test_pro_user_can_switch_model(
        self,
        has_ai_key_mock,
        generate_analyses_mock,
    ):
        has_ai_key_mock.return_value = True
        generate_analyses_mock.return_value = True

        pro_user = User.objects.create_user(
            username='pro_user',
            email='pro@example.com',
            password='StrongPass123!',
        )
        NatalProfile.objects.create(user=pro_user, name='Pro User', is_pro=True)

        client = Client(HTTP_HOST='pochop.sk')
        client.force_login(pro_user)
        response = client.post(
            reverse('transits:api_select_ai_model'),
            data=json.dumps({'model_ref': 'gemini:gemini-2.5-pro'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertTrue(payload.get('ok'))
        self.assertIn('2.5', payload.get('active_badge', ''))
        self.assertEqual(payload.get('users_refresh_mode'), 'lazy')
        cfg = GeminiConfig.objects.get()
        self.assertEqual(cfg.default_model, 'gemini:gemini-2.5-pro')
        self.assertEqual(generate_analyses_mock.call_count, 0)
        self.assertEqual(payload.get('moment_refresh_mode'), 'lazy')

    @patch('transits.views.has_ai_key')
    def test_switch_succeeds_with_warning_when_gateway_key_missing(
        self,
        has_ai_key_mock,
    ):
        has_ai_key_mock.return_value = False

        client = Client(HTTP_HOST='pochop.sk')
        client.force_login(self.staff)
        response = client.post(
            reverse('transits:api_select_ai_model'),
            data=json.dumps({'model_ref': 'gemini:gemini-2.5-pro'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertTrue(payload.get('ok'))
        self.assertIn('fallback', payload.get('warning', '').lower())
        cfg = GeminiConfig.objects.get()
        self.assertEqual(cfg.default_model, 'gemini:gemini-2.5-pro')

    @patch('transits.views.generate_ai_text')
    @patch('transits.views.has_ai_key')
    def test_switch_is_lazy_without_live_probe_call(
        self,
        has_ai_key_mock,
        generate_ai_text_mock,
    ):
        has_ai_key_mock.return_value = True
        generate_ai_text_mock.side_effect = AssertionError('API probe should not be called')

        client = Client(HTTP_HOST='pochop.sk')
        client.force_login(self.staff)
        response = client.post(
            reverse('transits:api_select_ai_model'),
            data=json.dumps({'model_ref': 'gemini:gemini-2.5-pro'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertTrue(payload.get('ok'))
        self.assertEqual(generate_ai_text_mock.call_count, 0)

    @patch('transits.views._generate_and_save_analyses')
    @patch('transits.views.has_ai_key')
    def test_user_level_pro_status_can_switch_model_without_profile(
        self,
        has_ai_key_mock,
        generate_analyses_mock,
    ):
        has_ai_key_mock.return_value = True
        generate_analyses_mock.return_value = True

        pro_user = User.objects.create_user(
            username='pro_flag_user',
            email='proflag@example.com',
            password='StrongPass123!',
        )
        UserProStatus.objects.create(user=pro_user, is_pro=True)

        client = Client(HTTP_HOST='pochop.sk')
        client.force_login(pro_user)
        response = client.post(
            reverse('transits:api_select_ai_model'),
            data=json.dumps({'model_ref': 'gemini:gemini-2.5-pro'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertTrue(payload.get('ok'))
        self.assertIn('2.5', payload.get('active_badge', ''))

    @patch('transits.views._generate_and_save_analyses')
    @patch('transits.views.has_ai_key')
    def test_switch_updates_runtime_model(
        self,
        has_ai_key_mock,
        generate_analyses_mock,
    ):
        has_ai_key_mock.return_value = True
        generate_analyses_mock.return_value = True

        p1 = NatalProfile.objects.create(
            name='A',
            natal_analysis_json=[{'id': 'sun'}],
            natal_aspects_json=[{'header': 'A'}],
        )
        p2 = NatalProfile.objects.create(
            name='B',
            natal_analysis_json=[{'id': 'moon'}],
            natal_aspects_json=[{'header': 'B'}],
        )

        client = Client(HTTP_HOST='pochop.sk')
        client.force_login(self.staff)
        response = client.post(
            reverse('transits:api_select_ai_model'),
            data=json.dumps({'model_ref': 'gemini:gemini-2.5-pro'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertTrue(payload.get('ok'))
        self.assertIn('2.5', payload.get('active_badge', ''))
        self.assertEqual(payload.get('users_refresh_mode'), 'lazy')
        self.assertEqual(payload.get('users_marked'), 2)

        cfg = GeminiConfig.objects.get()
        self.assertEqual(cfg.default_model, 'gemini:gemini-2.5-pro')
        self.assertEqual(generate_analyses_mock.call_count, 0)

        p1.refresh_from_db(fields=['natal_analysis_json', 'natal_aspects_json'])
        p2.refresh_from_db(fields=['natal_analysis_json', 'natal_aspects_json'])
        self.assertIsNone(p1.natal_analysis_json)
        self.assertIsNone(p1.natal_aspects_json)
        self.assertIsNone(p2.natal_analysis_json)
        self.assertIsNone(p2.natal_aspects_json)


class AIDayReportApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='timeline_user',
            email='timeline@example.com',
            password='StrongPass123!',
        )
        self.profile = NatalProfile.objects.create(
            user=self.user,
            name='Timeline User',
            gender='male',
        )
        GeminiConfig.objects.update_or_create(
            id=1,
            defaults={'default_model': 'openai:gpt-5.2', 'max_calls_daily': 500},
        )
        AIModelOption.objects.update_or_create(
            model_ref='openai:gpt-5.2',
            defaults={'label': 'GPT-5.2', 'sort_order': 10, 'is_enabled': True},
        )
        AIModelOption.objects.update_or_create(
            model_ref='gemini:gemini-2.5-pro',
            defaults={'label': 'Gemini Pro 2.5', 'sort_order': 20, 'is_enabled': True},
        )
        self.client = Client(HTTP_HOST='pochop.sk')
        self.client.force_login(self.user)

    def _active_transits_today(self):
        start_dt = datetime.combine(date.today(), time(0, 0))
        end_dt = datetime.combine(date.today(), time(23, 59))
        return [
            {
                'title': 'Mesiac trigón Slnko',
                'effect': 'positive',
                'orb': 0.7,
                'orb_limit': 2.0,
                'intensity': 0.82,
                'text': 'Silná podpora pre tvorivosť a komunikáciu.',
                'start_date_iso': start_dt.isoformat(),
                'end_date_iso': end_dt.isoformat(),
            }
        ]

    @patch('transits.views.has_ai_key')
    @patch('transits.views._compute_transits_for_profile')
    @patch('transits.views.generate_gemini_text')
    def test_ai_day_report_returns_model_and_generated_time(
        self,
        generate_ai_text_mock,
        compute_transits_mock,
        has_key_mock,
    ):
        has_key_mock.return_value = True
        compute_transits_mock.return_value = self._active_transits_today()
        generate_ai_text_mock.return_value = json.dumps({
            'rating': 8,
            'energy': 'Silný mentálny focus a praktický drive.',
            'focus': ['Dokonči najdôležitejšiu úlohu.', 'Komunikuj vecne.', 'Drž rytmus.'],
            'avoid': ['Nehovor v afekte.', 'Nerob multitasking.', 'Neodkladaj priority.'],
        })

        response = self.client.post(
            reverse('transits:ai_day_report'),
            data=json.dumps({'profile_id': self.profile.pk, 'day_offset': 0}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))

        self.assertEqual(payload.get('rating'), 8)
        self.assertEqual(payload.get('ai_model_ref'), 'openai:gpt-5.2')
        self.assertIn('Vercel AI Gateway', payload.get('ai_model_badge', ''))
        self.assertTrue(payload.get('generated_at_display'))
        self.assertFalse(payload.get('cache_hit'))
        self.assertEqual(AIDayReportCache.objects.count(), 1)

        stat = AIDayReportDailyStat.objects.get(stat_date=date.today(), model_ref='openai:gpt-5.2')
        self.assertEqual(stat.total_requests, 1)
        self.assertEqual(stat.cache_hits, 0)
        self.assertEqual(stat.generated_reports, 1)
        self.assertEqual(stat.fallback_reports, 0)
        self.assertEqual(stat.errors_count, 0)

    @patch('transits.views.has_ai_key')
    @patch('transits.views._compute_transits_for_profile')
    @patch('transits.views.generate_gemini_text')
    def test_ai_day_report_supports_explicit_model_ref(
        self,
        generate_ai_text_mock,
        compute_transits_mock,
        has_key_mock,
    ):
        has_key_mock.return_value = True
        compute_transits_mock.return_value = self._active_transits_today()
        generate_ai_text_mock.return_value = json.dumps({
            'rating': 7,
            'energy': 'Gemini špecifická energia.',
            'focus': ['G1', 'G2', 'G3'],
            'avoid': ['G4', 'G5', 'G6'],
        })

        response = self.client.post(
            reverse('transits:ai_day_report'),
            data=json.dumps({
                'profile_id': self.profile.pk,
                'day_offset': 0,
                'model_ref': 'gemini:gemini-2.5-pro',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload.get('ai_model_ref'), 'gemini:gemini-2.5-pro')
        self.assertIn('2.5', payload.get('ai_model_badge', ''))

    @patch('transits.views.has_ai_key')
    @patch('transits.views._compute_transits_for_profile')
    @patch('transits.views.generate_gemini_text')
    def test_ai_day_report_uses_db_cache_on_repeated_request(
        self,
        generate_ai_text_mock,
        compute_transits_mock,
        has_key_mock,
    ):
        has_key_mock.return_value = True
        compute_transits_mock.return_value = self._active_transits_today()
        generate_ai_text_mock.return_value = json.dumps({
            'rating': 7,
            'energy': 'Stabilný deň so silným praktickým potenciálom.',
            'focus': ['Prioritizuj úlohy.', 'Drž tempo.', 'Pýtaj sa presne.'],
            'avoid': ['Náhlivé reakcie.', 'Zbytočný chaos.', 'Nedotiahnuté záväzky.'],
        })

        url = reverse('transits:ai_day_report')
        body = json.dumps({'profile_id': self.profile.pk, 'day_offset': 0})
        first = self.client.post(url, data=body, content_type='application/json')
        second = self.client.post(url, data=body, content_type='application/json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_payload = json.loads(first.content.decode('utf-8'))
        second_payload = json.loads(second.content.decode('utf-8'))

        self.assertFalse(first_payload.get('cache_hit'))
        self.assertTrue(second_payload.get('cache_hit'))
        self.assertEqual(generate_ai_text_mock.call_count, 1)

        stat = AIDayReportDailyStat.objects.get(stat_date=date.today(), model_ref='openai:gpt-5.2')
        self.assertEqual(stat.total_requests, 2)
        self.assertEqual(stat.cache_hits, 1)
        self.assertEqual(stat.generated_reports, 1)
        self.assertEqual(stat.fallback_reports, 0)
        self.assertEqual(stat.errors_count, 0)

    @patch('transits.views.has_ai_key')
    @patch('transits.views._compute_transits_for_profile')
    @patch('transits.views.generate_gemini_text')
    def test_ai_day_report_cache_expires_at_next_midnight(
        self,
        generate_ai_text_mock,
        compute_transits_mock,
        has_key_mock,
    ):
        has_key_mock.return_value = True
        compute_transits_mock.return_value = self._active_transits_today()
        generate_ai_text_mock.return_value = json.dumps({
            'rating': 6,
            'energy': 'Stabilný deň.',
            'focus': ['A', 'B', 'C'],
            'avoid': ['D', 'E', 'F'],
        })

        response = self.client.post(
            reverse('transits:ai_day_report'),
            data=json.dumps({'profile_id': self.profile.pk, 'day_offset': 0}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        row = AIDayReportCache.objects.get()
        expires_local = timezone.localtime(row.expires_at)
        self.assertEqual(expires_local.hour, 0)
        self.assertEqual(expires_local.minute, 0)
        self.assertEqual(expires_local.second, 0)
        self.assertGreater(row.expires_at, timezone.now())

    @patch('transits.views.has_ai_key')
    def test_ai_day_report_forbidden_for_foreign_profile(self, has_key_mock):
        has_key_mock.return_value = True
        other_user = User.objects.create_user(
            username='other_user',
            email='other@example.com',
            password='StrongPass123!',
        )
        other_profile = NatalProfile.objects.create(
            user=other_user,
            name='Other',
            gender='female',
        )

        response = self.client.post(
            reverse('transits:ai_day_report'),
            data=json.dumps({'profile_id': other_profile.pk, 'day_offset': 0}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

        stat = AIDayReportDailyStat.objects.get(stat_date=date.today(), model_ref='openai:gpt-5.2')
        self.assertEqual(stat.total_requests, 1)
        self.assertEqual(stat.errors_count, 1)


class AIDayReportCompareApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='timeline_compare_user',
            email='timeline-compare@example.com',
            password='StrongPass123!',
        )
        self.profile = NatalProfile.objects.create(
            user=self.user,
            name='Timeline Compare User',
            gender='male',
        )
        GeminiConfig.objects.update_or_create(
            id=1,
            defaults={'default_model': 'openai:gpt-5.2', 'max_calls_daily': 500},
        )
        AIModelOption.objects.update_or_create(
            model_ref='openai:gpt-5.2',
            defaults={'label': 'GPT-5.2', 'sort_order': 10, 'is_enabled': True},
        )
        AIModelOption.objects.update_or_create(
            model_ref='gemini:gemini-2.5-pro',
            defaults={'label': 'Gemini Pro 2.5', 'sort_order': 20, 'is_enabled': True},
        )
        self.client = Client(HTTP_HOST='pochop.sk')
        self.client.force_login(self.user)
        self.url = reverse('transits:ai_day_report_compare')

    def _active_transits_today(self):
        start_dt = datetime.combine(date.today(), time(0, 0))
        end_dt = datetime.combine(date.today(), time(23, 59))
        return [
            {
                'title': 'Slnko sextil Jupiter',
                'effect': 'positive',
                'orb': 1.1,
                'orb_limit': 2.0,
                'intensity': 0.78,
                'text': 'Podpora pre expanziu a praktické rozhodnutia.',
                'start_date_iso': start_dt.isoformat(),
                'end_date_iso': end_dt.isoformat(),
            }
        ]

    @patch('transits.views.has_ai_key')
    @patch('transits.views._compute_transits_for_profile')
    @patch('transits.views.generate_gemini_text')
    def test_compare_endpoint_cache_miss_then_hit_for_all_models(
        self,
        generate_ai_text_mock,
        compute_transits_mock,
        has_key_mock,
    ):
        has_key_mock.return_value = True
        compute_transits_mock.return_value = self._active_transits_today()
        generate_ai_text_mock.side_effect = [
            json.dumps({
                'rating': 8,
                'energy': 'Model A energia.',
                'focus': ['A1', 'A2', 'A3'],
                'avoid': ['A4', 'A5', 'A6'],
            }),
            json.dumps({
                'rating': 7,
                'energy': 'Model B energia.',
                'focus': ['B1', 'B2', 'B3'],
                'avoid': ['B4', 'B5', 'B6'],
            }),
        ]

        body = {
            'profile_id': self.profile.pk,
            'day_offset': 0,
            'model_refs': ['openai:gpt-5.2', 'gemini:gemini-2.5-pro'],
        }
        first = self.client.post(self.url, data=json.dumps(body), content_type='application/json')
        second = self.client.post(self.url, data=json.dumps(body), content_type='application/json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        first_payload = first.json()
        second_payload = second.json()
        self.assertEqual(len(first_payload.get('results', [])), 2)
        self.assertTrue(all(item.get('ok') for item in first_payload['results']))
        self.assertEqual([item.get('cache_hit') for item in first_payload['results']], [False, False])
        self.assertEqual([item.get('cache_hit') for item in second_payload['results']], [True, True])
        self.assertEqual(generate_ai_text_mock.call_count, 2)
        self.assertEqual(AIDayReportCache.objects.count(), 2)

    @patch('transits.views.has_ai_key')
    @patch('transits.views._compute_transits_for_profile')
    @patch('transits.views.generate_gemini_text')
    def test_compare_endpoint_supports_mix_of_cached_and_new_model(
        self,
        generate_ai_text_mock,
        compute_transits_mock,
        has_key_mock,
    ):
        has_key_mock.return_value = True
        compute_transits_mock.return_value = self._active_transits_today()
        generate_ai_text_mock.return_value = json.dumps({
            'rating': 6,
            'energy': 'Nový model energia.',
            'focus': ['C1', 'C2', 'C3'],
            'avoid': ['C4', 'C5', 'C6'],
        })

        AIDayReportCache.objects.create(
            profile=self.profile,
            target_date=date.today(),
            model_ref='openai:gpt-5.2',
            payload_json={
                'rating': 9,
                'energy': 'Cache model energia.',
                'focus': ['X1', 'X2', 'X3'],
                'avoid': ['X4', 'X5', 'X6'],
            },
            profile_updated_at=self.profile.updated_at,
            expires_at=timezone.now() + timedelta(hours=2),
        )

        response = self.client.post(
            self.url,
            data=json.dumps({
                'profile_id': self.profile.pk,
                'day_offset': 0,
                'model_refs': ['openai:gpt-5.2', 'gemini:gemini-2.5-pro'],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item.get('cache_hit') for item in payload.get('results', [])], [True, False])
        self.assertEqual(generate_ai_text_mock.call_count, 1)

    def test_compare_endpoint_rejects_invalid_model_ref(self):
        response = self.client.post(
            self.url,
            data=json.dumps({
                'profile_id': self.profile.pk,
                'day_offset': 0,
                'model_refs': ['openai:gpt-5.2', 'openai:unknown-model'],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('model_refs', response.json().get('error', '').lower())

    def test_compare_endpoint_respects_admin_max_models_limit(self):
        GeminiConfig.objects.update_or_create(
            id=1,
            defaults={
                'default_model': 'openai:gpt-5.2',
                'max_calls_daily': 500,
                'max_compare_models': 1,
            },
        )
        response = self.client.post(
            self.url,
            data=json.dumps({
                'profile_id': self.profile.pk,
                'day_offset': 0,
                'model_refs': ['openai:gpt-5.2', 'gemini:gemini-2.5-pro'],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('maximálne 1 modely', response.json().get('error', '').lower())

    def test_compare_endpoint_rejects_pro_only_model_for_free_user(self):
        AIModelOption.objects.filter(model_ref='gemini:gemini-2.5-pro').update(is_pro_only=True)
        response = self.client.post(
            self.url,
            data=json.dumps({
                'profile_id': self.profile.pk,
                'day_offset': 0,
                'model_refs': ['gemini:gemini-2.5-pro'],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('neplatné model_refs', response.json().get('error', '').lower())

    @patch('transits.views.has_ai_key')
    @patch('transits.views._compute_transits_for_profile')
    @patch('transits.views.generate_gemini_text')
    def test_compare_endpoint_allows_pro_only_model_for_pro_user(
        self,
        generate_ai_text_mock,
        compute_transits_mock,
        has_key_mock,
    ):
        AIModelOption.objects.filter(model_ref='gemini:gemini-2.5-pro').update(is_pro_only=True)
        has_key_mock.return_value = True
        compute_transits_mock.return_value = self._active_transits_today()
        generate_ai_text_mock.return_value = json.dumps({
            'rating': 7,
            'energy': 'Pro model energia.',
            'focus': ['P1', 'P2', 'P3'],
            'avoid': ['P4', 'P5', 'P6'],
        })

        pro_user = User.objects.create_user(
            username='compare_pro_user',
            email='compare-pro@example.com',
            password='StrongPass123!',
        )
        UserProStatus.objects.create(user=pro_user, is_pro=True)
        pro_profile = NatalProfile.objects.create(
            user=pro_user,
            name='Compare Pro',
            gender='male',
        )

        client = Client(HTTP_HOST='pochop.sk')
        client.force_login(pro_user)
        response = client.post(
            self.url,
            data=json.dumps({
                'profile_id': pro_profile.pk,
                'day_offset': 0,
                'model_refs': ['gemini:gemini-2.5-pro'],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get('ok_models'), 1)
        self.assertEqual(payload['results'][0].get('ai_model_ref'), 'gemini:gemini-2.5-pro')

    def test_compare_endpoint_rejects_foreign_profile(self):
        other_user = User.objects.create_user(
            username='foreign_user',
            email='foreign@example.com',
            password='StrongPass123!',
        )
        other_profile = NatalProfile.objects.create(
            user=other_user,
            name='Foreign',
            gender='female',
        )
        response = self.client.post(
            self.url,
            data=json.dumps({
                'profile_id': other_profile.pk,
                'day_offset': 0,
                'model_refs': ['openai:gpt-5.2'],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    @patch('transits.views.has_ai_key')
    @patch('transits.views._compute_transits_for_profile')
    @patch('transits.views.generate_gemini_text')
    def test_compare_endpoint_handles_limit_and_exception_with_partial_results(
        self,
        generate_ai_text_mock,
        compute_transits_mock,
        has_key_mock,
    ):
        has_key_mock.return_value = True
        compute_transits_mock.return_value = self._active_transits_today()
        generate_ai_text_mock.side_effect = [
            Exception('provider timeout'),
            GeminiLimitExceededError('daily limit'),
        ]

        response = self.client.post(
            self.url,
            data=json.dumps({
                'profile_id': self.profile.pk,
                'day_offset': 0,
                'model_refs': ['openai:gpt-5.2', 'gemini:gemini-2.5-pro'],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload.get('results', [])), 2)
        self.assertTrue(payload['results'][0].get('ok'))
        self.assertFalse(payload['results'][1].get('ok'))
        self.assertTrue(payload['results'][1].get('limit_exceeded'))
        self.assertTrue(payload.get('partial'))
        self.assertEqual(len(payload.get('errors', [])), 1)


class NatalAnalysisCompareCacheTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='natal_compare_user',
            email='natal-compare@example.com',
            password='StrongPass123!',
        )
        self.profile = NatalProfile.objects.create(
            user=self.user,
            name='Natal Compare User',
            gender='female',
        )
        AIModelOption.objects.update_or_create(
            model_ref='openai:gpt-5.2',
            defaults={'label': 'GPT-5.2', 'sort_order': 10, 'is_enabled': True},
        )
        AIModelOption.objects.update_or_create(
            model_ref='gemini:gemini-2.5-pro',
            defaults={'label': 'Gemini Pro 2.5', 'sort_order': 20, 'is_enabled': True},
        )
        self.client = Client(HTTP_HOST='pochop.sk')
        self.client.force_login(self.user)
        self.url = reverse('transits:api_natal_analysis_compare')

    def _analysis_payload(self, suffix='A'):
        return {
            'analysis_json': [
                {
                    'id': 'sun',
                    'icon': '☉',
                    'title': f'Sekcia {suffix}',
                    'text': f'Natálna sekcia {suffix}.',
                    'items': [],
                }
            ],
            'aspects_json': [
                {
                    'header': f'Aspekt {suffix}',
                    'aspect_type': 'trine',
                    'text': f'Aspektová analýza {suffix}.',
                }
            ],
            'model_ref': 'openai:gpt-5.2',
            'ai_model_ctx': {
                'provider': 'vercel',
                'provider_label': 'Vercel AI Gateway',
                'model': 'gpt-5.2',
                'badge': 'Vercel AI Gateway gpt-5.2',
            },
        }

    @patch('transits.views.has_ai_key')
    @patch('transits.views._generate_natal_analyses_payload')
    def test_natal_compare_lazy_generation_then_cache_hit(
        self,
        generate_payload_mock,
        has_key_mock,
    ):
        has_key_mock.return_value = True
        generate_payload_mock.return_value = self._analysis_payload('A')
        body = {
            'profile_id': self.profile.pk,
            'model_refs': ['openai:gpt-5.2'],
        }

        first = self.client.post(self.url, data=json.dumps(body), content_type='application/json')
        second = self.client.post(self.url, data=json.dumps(body), content_type='application/json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_item = first.json()['results'][0]
        second_item = second.json()['results'][0]
        self.assertTrue(first_item.get('ok'))
        self.assertFalse(first_item.get('cache_hit'))
        self.assertTrue(second_item.get('cache_hit'))
        self.assertEqual(generate_payload_mock.call_count, 1)
        self.assertEqual(AINatalAnalysisCache.objects.count(), 1)

    @patch('transits.views.has_ai_key')
    @patch('transits.views._generate_natal_analyses_payload')
    def test_natal_compare_cache_invalidates_after_profile_updated_at_change(
        self,
        generate_payload_mock,
        has_key_mock,
    ):
        has_key_mock.return_value = True
        generate_payload_mock.side_effect = [
            self._analysis_payload('A'),
            self._analysis_payload('B'),
        ]
        body = {
            'profile_id': self.profile.pk,
            'model_refs': ['openai:gpt-5.2'],
        }

        first = self.client.post(self.url, data=json.dumps(body), content_type='application/json')
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()['results'][0].get('cache_hit'))

        self.profile.refresh_from_db()
        self.profile.name = 'Natal Compare User Updated'
        self.profile.save()

        second = self.client.post(self.url, data=json.dumps(body), content_type='application/json')
        self.assertEqual(second.status_code, 200)
        second_item = second.json()['results'][0]
        self.assertFalse(second_item.get('cache_hit'))
        self.assertEqual(generate_payload_mock.call_count, 2)
        cache_row = AINatalAnalysisCache.objects.get(profile=self.profile, model_ref='openai:gpt-5.2')
        self.assertEqual(cache_row.analysis_json[0]['title'], 'Sekcia B')

    def test_natal_compare_respects_admin_max_models_limit(self):
        GeminiConfig.objects.update_or_create(
            id=1,
            defaults={
                'default_model': 'openai:gpt-5.2',
                'max_calls_daily': 500,
                'max_compare_models': 1,
            },
        )
        response = self.client.post(
            self.url,
            data=json.dumps({
                'profile_id': self.profile.pk,
                'model_refs': ['openai:gpt-5.2', 'gemini:gemini-2.5-pro'],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('maximálne 1 modely', response.json().get('error', '').lower())


class NatalPayloadQualityGuardTests(TestCase):
    def setUp(self):
        self.profile = NatalProfile.objects.create(
            name='Quality Guard',
            gender='female',
            natal_chart_json={
                'planets': {
                    'sun': {'name_sk': 'Slnko', 'degree': 10.0, 'sign': 'Baran', 'symbol': '☉'},
                    'moon': {'name_sk': 'Mesiac', 'degree': 20.0, 'sign': 'Rak', 'symbol': '☽'},
                },
                'ascendant': {'degree': 5.0, 'sign': 'Lev', 'symbol': '♌'},
                'midheaven': {'degree': 15.0, 'sign': 'Býk', 'symbol': '♉'},
                'aspects': [
                    {
                        'planet1_sk': 'Slnko',
                        'aspect_sk': 'Trigón',
                        'planet2_sk': 'Mesiac',
                        'orb': 1.2,
                        'planet1': 'sun',
                        'planet2': 'moon',
                        'aspect': 'trine',
                        'effect': 'positive',
                    }
                ],
                'elements': {'Oheň': 4, 'Voda': 3, 'Vzduch': 2, 'Zem': 1},
                'modalities': {'Kardinálne': 4, 'Pevné': 3, 'Premenlivé': 3},
            },
            natal_positions_json={'ok': True},
        )

    @patch('transits.views._natal_payload_is_valid')
    @patch('transits.views._parse_aspects_response')
    @patch('transits.views._parse_natal_response')
    @patch('transits.views.generate_gemini_text')
    @patch('transits.views.has_ai_key')
    def test_low_quality_natal_response_retries_without_cache_before_fallback(
        self,
        has_key_mock,
        generate_ai_mock,
        parse_natal_mock,
        parse_aspects_mock,
        payload_valid_mock,
    ):
        has_key_mock.return_value = True
        generate_ai_mock.side_effect = [
            'first-natal-response',
            'retry-natal-response',
            'aspects-response',
        ]
        parse_natal_mock.side_effect = [
            [{'id': 'summary', 'icon': '✦', 'title': 'Natálna analýza', 'text': 'bad', 'items': []}],
            [{'id': 'sun', 'icon': '☉', 'title': 'Slnečné znamenie', 'text': 'valid', 'items': []}],
        ]
        payload_valid_mock.side_effect = [False, True]
        parse_aspects_mock.return_value = [
            {'header': 'Slnko trigón Mesiac', 'aspect_type': 'trine', 'text': 'Valid aspekt text.'}
        ]

        payload = _generate_natal_analyses_payload(self.profile, model_name='gemini:gemini-2.5-pro')

        self.assertIsNotNone(payload)
        self.assertFalse(payload.get('fallback_used'))
        self.assertIn('druhý pokus', payload.get('warning', '').lower())
        self.assertEqual(generate_ai_mock.call_count, 3)
        self.assertEqual(generate_ai_mock.call_args_list[1].kwargs.get('cache_ttl_seconds'), 0)
        self.assertEqual(generate_ai_mock.call_args_list[0].kwargs.get('cache_ttl_seconds'), 60 * 60 * 24 * 30)


class PerUserEncryptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='enc_user', password='StrongPass123!')
        self.lat = 48.1486
        self.lon = 17.1077
        self.tz = get_timezone_for_location(self.lat, self.lon)
        self.profile = NatalProfile.objects.create(
            user=self.user,
            name='Enc User',
            timezone=self.tz,
        )
        self.profile.set_encrypted_birth_data(
            raw_password='StrongPass123!',
            birth_date=date(1991, 9, 15),
            birth_time=time(14, 45),
            birth_place='Bratislava',
            birth_lat=self.lat,
            birth_lon=self.lon,
        )
        self.profile.natal_positions_json = calculate_natal_positions(
            date(1991, 9, 15), time(14, 45), self.lat, self.lon, self.tz
        )
        self.profile.natal_chart_json = calculate_natal_chart(
            date(1991, 9, 15), time(14, 45), self.lat, self.lon, self.tz
        )
        self.profile.save()

    def test_plain_birth_fields_are_nulled(self):
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.birth_date)
        self.assertIsNone(self.profile.birth_time)
        self.assertIsNone(self.profile.birth_place)
        self.assertIsNone(self.profile.birth_lat)
        self.assertIsNone(self.profile.birth_lon)

    def test_db_contains_encrypted_values_not_plaintext(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT birth_date_encrypted, birth_place_encrypted
                FROM transits_natalprofile
                WHERE id = %s
                """,
                [self.profile.pk],
            )
            row = cursor.fetchone()
        self.assertIsNotNone(row)
        birth_date_enc, birth_place_enc = row
        self.assertTrue(str(birth_date_enc).startswith('usr::'))
        self.assertTrue(str(birth_place_enc).startswith('usr::'))
        self.assertNotIn('1991-09-15', str(birth_date_enc))
        self.assertNotIn('Bratislava', str(birth_place_enc))

    def test_can_decrypt_with_correct_password_only(self):
        key_ok = derive_user_key_b64('StrongPass123!', self.profile.birth_data_salt)
        decrypted = self.profile.decrypt_birth_data(key_b64=key_ok)
        self.assertIsNotNone(decrypted)
        self.assertEqual(decrypted['birth_place'], 'Bratislava')
        self.assertEqual(decrypted['birth_date'].isoformat(), '1991-09-15')

        key_bad = derive_user_key_b64('WrongPass123!', self.profile.birth_data_salt)
        decrypted_bad = self.profile.decrypt_birth_data(key_b64=key_bad)
        self.assertIsNone(decrypted_bad)


class RegistrationAndPrivacyFlowTests(TestCase):
    def test_registration_requires_email_verification_before_login(self):
        client = Client(HTTP_HOST='pochop.sk')
        payload = {
            'username': 'reg_user',
            'email': 'reg_user@example.com',
            'password1': 'RegStrong123!',
            'password2': 'RegStrong123!',
            'birth_date': '17.05.1990',
            'birth_time': '08:30',
            'birth_place': 'Bratislava',
            'birth_lat': '48.1486',
            'birth_lon': '17.1077',
        }
        response = client.post(reverse('transits:register'), payload)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('transits:verify_email_sent'), response.url)

        user = User.objects.get(username='reg_user')
        self.assertFalse(user.is_active)
        profile = NatalProfile.objects.get(user__username='reg_user')
        self.assertEqual(profile.gender, 'male')
        self.assertTrue(profile.birth_date_encrypted.startswith('usr::'))
        self.assertTrue(profile.birth_place_encrypted.startswith('usr::'))
        self.assertIsNone(profile.birth_date)
        self.assertIsNone(profile.birth_place)
        self.assertTrue(profile.public_hash)

        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        match = re.search(r'https?://[^\s]+/email/verify/[^\s]+/', body)
        self.assertIsNotNone(match)
        verify_url = match.group(0)

        # Bez verifikácie nebude prístup do timeline.
        timeline_response = client.get(reverse('transits:timeline'))
        self.assertEqual(timeline_response.status_code, 302)
        self.assertIn(reverse('transits:login'), timeline_response.url)

        verify_response = client.get(verify_url)
        self.assertEqual(verify_response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        login_response = client.post(reverse('transits:login'), {
            'username': 'reg_user',
            'password': 'RegStrong123!',
        })
        self.assertEqual(login_response.status_code, 302)

        # Po verifikácii + login unlockne session birth metadata.
        timeline_response = client.get(reverse('transits:timeline'))
        self.assertEqual(timeline_response.status_code, 200)
        self.assertContains(timeline_response, 'Bratislava')
        self.assertContains(timeline_response, '17.05.1990')

    def test_registration_persists_selected_gender(self):
        client = Client(HTTP_HOST='pochop.sk')
        payload = {
            'username': 'reg_user_f',
            'email': 'reg_user_f@example.com',
            'password1': 'RegStrong123!',
            'password2': 'RegStrong123!',
            'birth_date': '17.05.1990',
            'birth_time': '08:30',
            'birth_place': 'Bratislava',
            'birth_lat': '48.1486',
            'birth_lon': '17.1077',
            'gender': 'female',
        }
        response = client.post(reverse('transits:register'), payload)
        self.assertEqual(response.status_code, 302)
        profile = NatalProfile.objects.get(user__username='reg_user_f')
        self.assertEqual(profile.gender, 'female')

    def test_api_transits_hides_birth_metadata_without_unlock(self):
        user = User.objects.create_user(username='api_priv_user', password='ApiPass123!')
        lat = 48.1486
        lon = 17.1077
        tz = get_timezone_for_location(lat, lon)
        profile = NatalProfile.objects.create(user=user, name='Api User', timezone=tz)
        profile.set_encrypted_birth_data(
            raw_password='ApiPass123!',
            birth_date=date(1988, 1, 3),
            birth_time=time(6, 20),
            birth_place='Kosice',
            birth_lat=lat,
            birth_lon=lon,
        )
        profile.natal_positions_json = calculate_natal_positions(
            date(1988, 1, 3), time(6, 20), lat, lon, tz
        )
        profile.natal_chart_json = calculate_natal_chart(
            date(1988, 1, 3), time(6, 20), lat, lon, tz
        )
        profile.save()

        anon_client = Client(HTTP_HOST='pochop.sk')
        response = anon_client.get(reverse('transits:api_transits', args=[profile.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['profile']['birth_date'], 'súkromné')
        self.assertEqual(data['profile']['birth_time'], 'súkromné')
        self.assertEqual(data['profile']['birth_place'], 'súkromné')


class RegistrationEmailValidationTests(TestCase):
    def test_registration_requires_email(self):
        client = Client(HTTP_HOST='pochop.sk')
        payload = {
            'username': 'missing_email',
            'password1': 'RegStrong123!',
            'password2': 'RegStrong123!',
            'birth_date': '17.05.1990',
            'birth_time': '08:30',
            'birth_place': 'Bratislava',
            'birth_lat': '48.1486',
            'birth_lon': '17.1077',
        }
        response = client.post(
            reverse('transits:register'),
            payload,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json().get('errors', {}))

    def test_registration_rejects_invalid_email(self):
        client = Client(HTTP_HOST='pochop.sk')
        payload = {
            'username': 'invalid_email',
            'email': 'invalid-email',
            'password1': 'RegStrong123!',
            'password2': 'RegStrong123!',
            'birth_date': '17.05.1990',
            'birth_time': '08:30',
            'birth_place': 'Bratislava',
            'birth_lat': '48.1486',
            'birth_lon': '17.1077',
        }
        response = client.post(
            reverse('transits:register'),
            payload,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json().get('errors', {}))


class EmailVerificationFlowTests(TestCase):
    def test_resend_verification_sends_email_for_inactive_user(self):
        user = User.objects.create_user(
            username='inactive_user',
            email='inactive_user@example.com',
            password='Inactive123!',
            is_active=False,
        )
        self.assertFalse(user.is_active)

        client = Client(HTTP_HOST='pochop.sk')
        response = client.post(reverse('transits:verify_email_resend'), {
            'email': 'inactive_user@example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Ak účet s týmto e-mailom existuje a nie je ešte aktivovaný',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/email/verify/', mail.outbox[0].body)

    def test_inactive_user_cannot_login(self):
        User.objects.create_user(
            username='inactive_login',
            email='inactive_login@example.com',
            password='Inactive123!',
            is_active=False,
        )
        client = Client(HTTP_HOST='pochop.sk')
        response = client.post(reverse('transits:login'), {
            'username': 'inactive_login',
            'password': 'Inactive123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Účet ešte nie je overený cez e-mail')


class PasswordChangeReencryptTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='pwd_user',
            email='pwd_user@example.com',
            password='OldPass123!',
        )
        lat = 48.1486
        lon = 17.1077
        tz = get_timezone_for_location(lat, lon)
        self.profile = NatalProfile.objects.create(
            user=self.user,
            name='Pwd User',
            timezone=tz,
        )
        self.profile.set_encrypted_birth_data(
            raw_password='OldPass123!',
            birth_date=date(1994, 7, 8),
            birth_time=time(11, 15),
            birth_place='Bratislava',
            birth_lat=lat,
            birth_lon=lon,
        )
        self.profile.natal_positions_json = calculate_natal_positions(
            date(1994, 7, 8), time(11, 15), lat, lon, tz
        )
        self.profile.natal_chart_json = calculate_natal_chart(
            date(1994, 7, 8), time(11, 15), lat, lon, tz
        )
        self.profile.save()

    def test_password_change_reencrypts_pii_without_data_loss(self):
        client = Client(HTTP_HOST='pochop.sk')
        self.assertTrue(client.login(username='pwd_user', password='OldPass123!'))

        old_salt = self.profile.birth_data_salt
        old_key = derive_user_key_b64('OldPass123!', old_salt)
        self.assertEqual(
            self.profile.decrypt_birth_data(key_b64=old_key)['birth_place'],
            'Bratislava',
        )

        response = client.post(reverse('transits:password_change'), {
            'old_password': 'OldPass123!',
            'new_password1': 'NewPass123!',
            'new_password2': 'NewPass123!',
        })
        self.assertRedirects(response, reverse('transits:password_change_done'))

        self.user.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertTrue(self.user.check_password('NewPass123!'))
        self.assertNotEqual(self.profile.birth_data_salt, old_salt)
        self.assertIsNone(self.profile.decrypt_birth_data(key_b64=old_key))

        new_key = derive_user_key_b64('NewPass123!', self.profile.birth_data_salt)
        decrypted = self.profile.decrypt_birth_data(key_b64=new_key)
        self.assertIsNotNone(decrypted)
        self.assertEqual(decrypted['birth_place'], 'Bratislava')
        self.assertEqual(decrypted['birth_date'].isoformat(), '1994-07-08')


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='reset_user',
            email='reset_user@example.com',
            password='ResetOld123!',
        )
        lat = 48.1486
        lon = 17.1077
        tz = get_timezone_for_location(lat, lon)
        self.profile = NatalProfile.objects.create(
            user=self.user,
            name='Reset User',
            timezone=tz,
        )
        self.profile.set_encrypted_birth_data(
            raw_password='ResetOld123!',
            birth_date=date(1992, 11, 4),
            birth_time=time(9, 10),
            birth_place='Kosice',
            birth_lat=lat,
            birth_lon=lon,
        )
        self.profile.save()

    def test_password_reset_request_sends_email(self):
        client = Client(HTTP_HOST='pochop.sk')
        response = client.post(reverse('transits:password_reset'), {
            'email': 'reset_user@example.com',
        })
        self.assertRedirects(response, reverse('transits:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/password/reset/', mail.outbox[0].body)

    def test_password_reset_confirm_reencrypts_profile(self):
        client = Client(HTTP_HOST='pochop.sk')
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        old_salt = self.profile.birth_data_salt
        old_key = derive_user_key_b64('ResetOld123!', old_salt)
        self.assertEqual(
            self.profile.decrypt_birth_data(key_b64=old_key)['birth_place'],
            'Kosice',
        )

        confirm_url = reverse('transits:password_reset_confirm', args=[uid, token])
        confirm_get = client.get(confirm_url)
        self.assertEqual(confirm_get.status_code, 302)

        response = client.post(
            confirm_get.url,
            {
                'new_password1': 'ResetNew123!',
                'new_password2': 'ResetNew123!',
            },
        )
        self.assertRedirects(response, reverse('transits:password_reset_complete'))

        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertTrue(self.user.check_password('ResetNew123!'))
        self.assertNotEqual(self.profile.birth_data_salt, old_salt)
        self.assertIsNone(self.profile.decrypt_birth_data(key_b64=old_key))

        new_key = derive_user_key_b64('ResetNew123!', self.profile.birth_data_salt)
        decrypted = self.profile.decrypt_birth_data(key_b64=new_key)
        self.assertIsNotNone(decrypted)
        self.assertEqual(decrypted['birth_place'], 'Kosice')


class AnonymizationCommandTests(TestCase):
    def test_anonymize_for_github_masks_users_and_profiles(self):
        user = User.objects.create_user(username='orig_user', password='OrigPass123!')
        lat = 48.1486
        lon = 17.1077
        tz = get_timezone_for_location(lat, lon)
        profile = NatalProfile.objects.create(user=user, name='Original Name', timezone=tz)
        profile.set_encrypted_birth_data(
            raw_password='OrigPass123!',
            birth_date=date(1993, 2, 12),
            birth_time=time(10, 15),
            birth_place='Trnava',
            birth_lat=lat,
            birth_lon=lon,
        )
        profile.save()

        call_command('anonymize_for_github', '--yes')

        user.refresh_from_db()
        profile.refresh_from_db()
        self.assertTrue(user.username.startswith('user_'))
        self.assertFalse(user.has_usable_password())
        self.assertIsNone(profile.user)
        self.assertTrue(profile.name.startswith('profile_'))
        self.assertIsNone(profile.birth_date)
        self.assertIsNone(profile.birth_place)


class MomentReportCommandEmailTests(TestCase):
    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='noreply@pochop.sk',
        MOMENT_REPORT_ADMIN_EMAILS='',
        ADMIN_EMAIL='agilehardware@gmail.com',
        ADMINS=(),
    )
    @patch('transits.management.commands.generate_moment_report.get_or_generate_moment_report')
    def test_generate_moment_report_sends_admin_email_from_env(self, mock_get_report):
        User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='AdminStrong123!',
        )
        fake_report = SimpleNamespace(
            id=42,
            report_date=date(2026, 2, 26),
            planets_json=[
                {
                    'key': 'sun',
                    'symbol': '☉',
                    'longitude': 120.0,
                },
                {
                    'key': 'saturn',
                    'symbol': '♄',
                    'longitude': 240.0,
                },
            ],
            ai_report_json={
                'rating': 8,
                'energy': 'Silný moment pre fokus.',
                'themes': ['Téma 1'],
                'focus': ['Fokus 1'],
                'avoid': ['Vyhnúť 1'],
            },
            aspects_json=[
                {
                    'planet1_symbol': '☉',
                    'aspect_symbol': '△',
                    'planet2_symbol': '♄',
                    'aspect_name_sk': 'Trigón',
                    'planet1_name_sk': 'Slnko',
                    'planet2_name_sk': 'Saturn',
                    'orb': 1.2,
                    'effect': 'positive',
                }
            ],
        )
        mock_get_report.return_value = fake_report

        out = StringIO()
        call_command('generate_moment_report', '--force', '--email-admin', stdout=out)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['agilehardware@gmail.com'])
        self.assertIn('Astrologický rozbor okamihu', mail.outbox[0].subject)
        html_alternatives = [alt for alt in mail.outbox[0].alternatives if len(alt) >= 2 and alt[1] == 'text/html']
        self.assertTrue(html_alternatives)
        self.assertIn('<svg', html_alternatives[0][0])
        self.assertIn('Aktuálne planetárne usporiadanie', html_alternatives[0][0])
        self.assertIn('Admin e-mail odoslaný', out.getvalue())

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='noreply@pochop.sk',
        MOMENT_REPORT_ADMIN_EMAILS='',
        ADMIN_EMAIL='',
        ADMINS=(),
    )
    @patch('transits.management.commands.generate_moment_report.get_or_generate_moment_report')
    def test_generate_moment_report_email_warns_when_no_recipients(self, mock_get_report):
        fake_report = SimpleNamespace(
            id=43,
            report_date=date(2026, 2, 26),
            planets_json=[],
            ai_report_json={'rating': 6, 'energy': '', 'themes': [], 'focus': [], 'avoid': []},
            aspects_json=[],
        )
        mock_get_report.return_value = fake_report

        out = StringIO()
        call_command('generate_moment_report', '--force', '--email-admin', stdout=out)

        self.assertEqual(len(mail.outbox), 0)
        self.assertIn('nenašli sa žiadni príjemcovia', out.getvalue())


class SmtpDiagnoseCommandTests(TestCase):
    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='smtp.example.com',
        EMAIL_PORT=587,
        EMAIL_HOST_USER='mailer@example.com',
        EMAIL_HOST_PASSWORD='secret',
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        DEFAULT_FROM_EMAIL='noreply@example.com',
    )
    @patch('transits.management.commands.smtp_diagnose.get_connection')
    def test_smtp_diagnose_connection_only(self, mock_get_connection):
        fake_conn = MagicMock()
        fake_conn.open.return_value = True
        mock_get_connection.return_value = fake_conn

        out = StringIO()
        call_command('smtp_diagnose', stdout=out)

        output = out.getvalue()
        self.assertIn('SMTP diagnostika', output)
        self.assertIn('EMAIL_HOST_PASSWORD: set', output)
        self.assertIn('SMTP pripojenie: OK', output)
        fake_conn.open.assert_called_once()
        fake_conn.close.assert_called_once()

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='smtp.example.com',
        EMAIL_PORT=587,
        EMAIL_HOST_USER='mailer@example.com',
        EMAIL_HOST_PASSWORD='secret',
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        DEFAULT_FROM_EMAIL='noreply@example.com',
    )
    @patch('transits.management.commands.smtp_diagnose.EmailMultiAlternatives')
    @patch('transits.management.commands.smtp_diagnose.get_connection')
    def test_smtp_diagnose_send_email(self, mock_get_connection, mock_email):
        fake_conn = MagicMock()
        fake_conn.open.return_value = True
        mock_get_connection.return_value = fake_conn

        fake_msg = MagicMock()
        fake_msg.send.return_value = 1
        mock_email.return_value = fake_msg

        out = StringIO()
        call_command('smtp_diagnose', '--to', 'receiver@example.com', stdout=out)

        output = out.getvalue()
        self.assertIn('Testovací e-mail bol odoslaný na receiver@example.com.', output)
        fake_msg.send.assert_called_once_with(fail_silently=False)


@skipUnless(
    os.getenv('RUN_REAL_SMTP_TESTS') == '1',
    "Set RUN_REAL_SMTP_TESTS=1 and SMTP_TEST_RECIPIENT to execute real SMTP delivery tests.",
)
class RealSmtpDeliveryTests(TestCase):
    def test_real_smtp_delivery(self):
        recipient = (os.getenv('SMTP_TEST_RECIPIENT') or '').strip()
        self.assertTrue(recipient, 'Set SMTP_TEST_RECIPIENT to a real inbox.')

        email_use_tls = os.getenv('EMAIL_USE_TLS', 'False').lower() in ('true', '1', 'yes')
        email_use_ssl = os.getenv('EMAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes')

        with override_settings(
            EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
            EMAIL_HOST=os.getenv('EMAIL_HOST', ''),
            EMAIL_PORT=int(os.getenv('EMAIL_PORT', '25')),
            EMAIL_HOST_USER=os.getenv('EMAIL_HOST_USER', ''),
            EMAIL_HOST_PASSWORD=os.getenv('EMAIL_HOST_PASSWORD', ''),
            EMAIL_USE_TLS=email_use_tls,
            EMAIL_USE_SSL=email_use_ssl,
            DEFAULT_FROM_EMAIL=os.getenv('DEFAULT_FROM_EMAIL', 'noreply@pochop.sk'),
        ):
            out = StringIO()
            call_command('smtp_diagnose', '--to', recipient, stdout=out)
            output = out.getvalue()
            self.assertIn('SMTP pripojenie: OK', output)
            self.assertIn('Testovací e-mail bol odoslaný', output)


class VercelGatewaySyncTests(TestCase):
    @patch('transits.vercel_gateway.fetch_vercel_models')
    def test_sync_creates_vercel_model_options(self, fetch_mock):
        fetch_mock.return_value = [
            {
                'id': 'openai/gpt-5.2',
                'name': 'GPT-5.2',
                'owned_by': 'openai',
                'type': 'chat',
                'context_window': 200000,
                'max_tokens': 8192,
                'pricing': {'input': 1.0, 'output': 3.0},
                'tags': ['reasoning', 'premium'],
            },
            {
                'id': 'anthropic/claude-3.7-sonnet',
                'owned_by': 'anthropic',
                'type': 'chat',
            },
        ]

        stats = sync_vercel_models(disable_missing=True, enable_new=False, pro_only_for_new=True)
        self.assertEqual(stats.get('created'), 2)
        self.assertEqual(AIModelOption.objects.filter(source='vercel').count(), 2)

        row = AIModelOption.objects.get(model_ref='vercel:openai/gpt-5.2')
        self.assertEqual(row.label, 'GPT-5.2')
        self.assertEqual(row.owner, 'openai')
        self.assertEqual(row.model_type, 'chat')
        self.assertEqual(row.context_window, 200000)
        self.assertEqual(row.max_tokens, 8192)
        self.assertTrue(row.is_pro_only)
        self.assertFalse(row.is_enabled)
        self.assertTrue(row.is_available)

    @patch('transits.vercel_gateway.fetch_vercel_models')
    def test_sync_preserves_admin_toggles_and_marks_missing(self, fetch_mock):
        existing = AIModelOption.objects.create(
            label='Old GPT',
            model_ref='vercel:openai/gpt-5.2',
            source='vercel',
            is_enabled=True,
            is_pro_only=False,
            is_available=True,
            sort_order=55,
        )
        missing = AIModelOption.objects.create(
            label='Old Missing',
            model_ref='vercel:openai/gpt-missing',
            source='vercel',
            is_enabled=True,
            is_pro_only=True,
            is_available=True,
            sort_order=66,
        )
        fetch_mock.return_value = [
            {
                'id': 'openai/gpt-5.2',
                'name': 'GPT-5.2 Updated',
                'owned_by': 'openai',
                'type': 'chat',
            },
        ]

        stats = sync_vercel_models(disable_missing=True, enable_new=False, pro_only_for_new=True)
        self.assertEqual(stats.get('updated'), 1)
        self.assertEqual(stats.get('missing'), 1)

        existing.refresh_from_db()
        missing.refresh_from_db()
        self.assertEqual(existing.label, 'GPT-5.2 Updated')
        self.assertTrue(existing.is_enabled)   # preserve manual toggle
        self.assertFalse(existing.is_pro_only)  # preserve manual toggle
        self.assertEqual(existing.sort_order, 55)
        self.assertFalse(missing.is_enabled)
        self.assertFalse(missing.is_available)


class RefreshToCacheCommandTests(TestCase):
    def setUp(self):
        self.free_user = User.objects.create_user(
            username='cache_free_user',
            email='cache_free@example.com',
            password='StrongPass123!',
        )
        self.pro_user = User.objects.create_user(
            username='cache_pro_user',
            email='cache_pro@example.com',
            password='StrongPass123!',
        )
        UserProStatus.objects.create(user=self.pro_user, is_pro=True)
        self.free_profile = NatalProfile.objects.create(user=self.free_user, name='Cache Free')
        self.pro_profile = NatalProfile.objects.create(user=self.pro_user, name='Cache Pro')

        AIModelOption.objects.update_or_create(
            model_ref='openai:gpt-5.2',
            defaults={
                'label': 'GPT-5.2',
                'is_enabled': True,
                'is_available': True,
                'is_pro_only': False,
                'sort_order': 10,
            },
        )
        AIModelOption.objects.update_or_create(
            model_ref='gemini:gemini-2.5-pro',
            defaults={
                'label': 'Gemini Pro 2.5',
                'is_enabled': True,
                'is_available': True,
                'is_pro_only': True,
                'sort_order': 20,
            },
        )

    @patch('transits.management.commands.refresh_to_cache._get_or_generate_natal_compare_for_model')
    def test_refresh_to_cache_excludes_pro_only_models_for_free_scope(self, natal_mock):
        natal_mock.return_value = ({'cache_hit': False}, None)
        call_command('refresh_to_cache', '--profiles', 'free', '--days', '0', '--skip-day')

        called_refs = [call.args[1] for call in natal_mock.call_args_list]
        self.assertTrue(called_refs)
        self.assertTrue(all(ref == 'openai:gpt-5.2' for ref in called_refs))

    @patch('transits.management.commands.refresh_to_cache._get_or_generate_natal_compare_for_model')
    def test_refresh_to_cache_includes_pro_only_models_for_pro_scope(self, natal_mock):
        natal_mock.return_value = ({'cache_hit': False}, None)
        call_command('refresh_to_cache', '--profiles', 'pro', '--days', '0', '--skip-day')

        called_refs = [call.args[1] for call in natal_mock.call_args_list]
        self.assertIn('openai:gpt-5.2', called_refs)
        self.assertIn('gemini:gemini-2.5-pro', called_refs)

    @patch('transits.management.commands.refresh_to_cache._get_or_generate_natal_compare_for_model')
    def test_refresh_to_cache_respects_admin_compare_limit(self, natal_mock):
        natal_mock.return_value = ({'cache_hit': False}, None)
        GeminiConfig.objects.update_or_create(
            id=1,
            defaults={
                'default_model': 'openai:gpt-5.2',
                'max_calls_daily': 500,
                'max_compare_models': 1,
            },
        )
        call_command('refresh_to_cache', '--profiles', 'pro', '--days', '0', '--skip-day')
        called_refs = [call.args[1] for call in natal_mock.call_args_list]
        self.assertTrue(called_refs)
        self.assertTrue(all(ref == 'openai:gpt-5.2' for ref in called_refs))

    @patch('transits.management.commands.refresh_to_cache._generate_and_save_analyses')
    def test_refresh_to_cache_supports_global_natal_warmup(self, global_natal_mock):
        global_natal_mock.return_value = True
        call_command(
            'refresh_to_cache',
            '--profiles', 'free',
            '--skip-natal',
            '--skip-day',
            '--with-global-natal',
            '--global-model', 'openai:gpt-5.2',
        )
        self.assertGreaterEqual(global_natal_mock.call_count, 1)
        called_model_refs = [call.kwargs.get('model_name') for call in global_natal_mock.call_args_list]
        self.assertTrue(all(ref == 'openai:gpt-5.2' for ref in called_model_refs))

    @patch('transits.management.commands.refresh_to_cache.get_or_generate_moment_report')
    def test_refresh_to_cache_supports_moment_warmup(self, moment_mock):
        moment_mock.return_value = SimpleNamespace(id=1, report_date=date(2026, 3, 4))
        call_command(
            'refresh_to_cache',
            '--profiles', 'free',
            '--skip-natal',
            '--skip-day',
            '--with-moment',
            '--moment-days', '0,1',
            '--moment-model', 'openai:gpt-5.2',
        )
        self.assertEqual(moment_mock.call_count, 2)
        for call_obj in moment_mock.call_args_list:
            self.assertFalse(call_obj.kwargs.get('force'))
            self.assertEqual(call_obj.kwargs.get('model_name'), 'openai:gpt-5.2')

    @patch('transits.management.commands.refresh_to_cache.get_or_generate_moment_report')
    def test_refresh_to_cache_moment_warmup_forces_regeneration_with_invalidate(self, moment_mock):
        moment_mock.return_value = SimpleNamespace(id=1, report_date=date(2026, 3, 4))
        call_command(
            'refresh_to_cache',
            '--profiles', 'free',
            '--skip-natal',
            '--skip-day',
            '--with-moment',
            '--moment-days', '0',
            '--moment-model', 'openai:gpt-5.2',
            '--invalidate',
        )
        self.assertEqual(moment_mock.call_count, 1)
        call_obj = moment_mock.call_args_list[0]
        self.assertTrue(call_obj.kwargs.get('force'))
        self.assertEqual(call_obj.kwargs.get('model_name'), 'openai:gpt-5.2')


class MomentAspectExplanationTests(TestCase):
    def test_enrich_moment_aspects_adds_text_from_lexicon_data(self):
        aspects = [{
            'planet1': 'uranus',
            'planet2': 'venus',
            'aspect': 'sextile',
            'effect': 'positive',
        }]
        enriched = enrich_moment_aspects_with_text(aspects)
        self.assertEqual(len(enriched), 1)
        self.assertIn('Nečakané finančné príležitosti', enriched[0].get('text', ''))

    def test_enrich_moment_aspects_preserves_existing_text(self):
        aspects = [{
            'planet1': 'sun',
            'planet2': 'moon',
            'aspect': 'trine',
            'effect': 'positive',
            'text': 'Vlastný text aspektu.',
        }]
        enriched = enrich_moment_aspects_with_text(aspects)
        self.assertEqual(enriched[0].get('text'), 'Vlastný text aspektu.')

    @patch('transits.views.get_or_generate_moment_report')
    def test_moment_overview_injects_explanations_for_cached_rows_without_text(self, report_mock):
        report_mock.return_value = SimpleNamespace(
            report_date=date(2026, 3, 4),
            planets_json=[],
            aspects_json=[{
                'planet1': 'uranus',
                'planet2': 'venus',
                'planet1_symbol': '♅',
                'planet2_symbol': '♀',
                'planet1_name_sk': 'Urán',
                'planet2_name_sk': 'Venuša',
                'aspect': 'sextile',
                'aspect_symbol': '⚹',
                'aspect_name_sk': 'sextil',
                'orb': 0.29,
                'effect': 'positive',
            }],
            ai_report_json={
                'rating': 7,
                'energy': 'Test energia.',
                'themes': ['T1'],
                'focus': ['F1'],
                'avoid': ['A1'],
            },
            updated_at=timezone.now(),
            _active_model_ctx={'badge': 'GPT-5.2'},
            _cache_hit=True,
        )
        client = Client(HTTP_HOST='pochop.sk')
        response = client.get(reverse('transits:moment_overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nečakané finančné príležitosti')

    @patch('transits.views.get_or_generate_moment_report')
    def test_moment_overview_forwards_location_query_to_generator(self, report_mock):
        report_mock.return_value = SimpleNamespace(
            report_date=date(2026, 3, 4),
            planets_json=[],
            aspects_json=[],
            ai_report_json={
                'rating': 7,
                'energy': 'Test energia.',
                'themes': ['T1'],
                'focus': ['F1'],
                'avoid': ['A1'],
                'location': {
                    'name': 'Žilina, Slovensko',
                    'lat': 49.223,
                    'lon': 18.739,
                },
            },
            location_name='Žilina, Slovensko',
            location_lat=49.223,
            location_lon=18.739,
            updated_at=timezone.now(),
            _active_model_ctx={'badge': 'GPT-5.2'},
            _cache_hit=False,
        )
        client = Client(HTTP_HOST='pochop.sk')
        response = client.get(
            reverse('transits:moment_overview'),
            {
                'lat': '49.223',
                'lon': '18.739',
                'city': 'Žilina',
                'country': 'Slovensko',
            },
        )
        self.assertEqual(response.status_code, 200)
        location_arg = report_mock.call_args.kwargs.get('location') or {}
        self.assertEqual(location_arg.get('lat'), 49.223)
        self.assertEqual(location_arg.get('lon'), 18.739)
        self.assertEqual(location_arg.get('city'), 'Žilina')
        self.assertEqual(location_arg.get('country'), 'Slovensko')

    @patch('transits.views.get_or_generate_moment_report')
    def test_moment_overview_backfills_city_from_nearest_when_missing(self, report_mock):
        SlovakCity.objects.create(
            name='Bratislava',
            district='Bratislava I',
            lat=48.1486,
            lon=17.1077,
        )
        report_mock.return_value = SimpleNamespace(
            report_date=date(2026, 3, 4),
            planets_json=[],
            aspects_json=[],
            ai_report_json={
                'rating': 7,
                'energy': 'Test energia.',
                'themes': ['T1'],
                'focus': ['F1'],
                'avoid': ['A1'],
                'location': {'name': 'Bratislava, Slovensko', 'lat': 48.1486, 'lon': 17.1077},
            },
            location_name='Bratislava, Slovensko',
            location_lat=48.1486,
            location_lon=17.1077,
            updated_at=timezone.now(),
            _active_model_ctx={'badge': 'GPT-5.2'},
            _cache_hit=False,
        )

        client = Client(HTTP_HOST='pochop.sk')
        response = client.get(
            reverse('transits:moment_overview'),
            {'lat': '48.1486', 'lon': '17.1077'},
        )
        self.assertEqual(response.status_code, 200)
        location_arg = report_mock.call_args.kwargs.get('location') or {}
        self.assertEqual(location_arg.get('city'), 'Bratislava')
        self.assertEqual(location_arg.get('country'), 'Slovensko')


class MomentReportModelCacheTests(TestCase):
    @patch('transits.moment_service._generate_ai_moment_report')
    @patch('transits.moment_service.calculate_moment_aspects')
    @patch('transits.moment_service.calculate_moment_angles')
    @patch('transits.moment_service.calculate_moment_snapshot')
    def test_moment_report_cache_is_scoped_by_model(
        self,
        snapshot_mock,
        angles_mock,
        aspects_mock,
        generate_report_mock,
    ):
        snapshot_mock.return_value = [
            {
                'key': 'sun',
                'name_sk': 'Slnko',
                'symbol': '☉',
                'longitude': 15.1,
                'longitude_deg': 15.1,
                'sign': 'Baran',
                'sign_symbol': '♈',
                'retrograde': False,
            }
        ]
        angles_mock.return_value = {
            'ascendant': {'longitude': 100.0, 'sign': 'Rak', 'degree': 10.0, 'symbol': '♋'},
            'midheaven': {'longitude': 250.0, 'sign': 'Strelec', 'degree': 10.0, 'symbol': '♐'},
        }
        aspects_mock.return_value = []
        generate_report_mock.return_value = {
            'rating': 7,
            'energy': 'Test energia.',
            'themes': ['T1', 'T2', 'T3'],
            'focus': ['F1', 'F2', 'F3'],
            'avoid': ['A1', 'A2', 'A3'],
        }

        target_date = date(2026, 3, 4)
        first = get_or_generate_moment_report(report_date=target_date, model_name='openai:gpt-5.2')
        second = get_or_generate_moment_report(report_date=target_date, model_name='openai:gpt-5.2')
        third = get_or_generate_moment_report(report_date=target_date, model_name='gemini:gemini-2.5-pro')

        self.assertFalse(getattr(first, '_cache_hit', True))
        self.assertTrue(getattr(second, '_cache_hit', False))
        self.assertFalse(getattr(third, '_cache_hit', True))
        self.assertEqual(generate_report_mock.call_count, 2)

        rows = MomentReport.objects.filter(report_date=target_date).order_by('model_ref')
        self.assertEqual(rows.count(), 2)
        self.assertEqual(
            set(rows.values_list('model_ref', flat=True)),
            {'openai:gpt-5.2', 'gemini:gemini-2.5-pro'},
        )

    @patch('transits.moment_service._generate_ai_moment_report')
    @patch('transits.moment_service.calculate_moment_aspects')
    @patch('transits.moment_service.calculate_moment_angles')
    @patch('transits.moment_service.calculate_moment_snapshot')
    def test_moment_report_force_regenerates_same_model_cache(
        self,
        snapshot_mock,
        angles_mock,
        aspects_mock,
        generate_report_mock,
    ):
        snapshot_mock.return_value = []
        angles_mock.return_value = {
            'ascendant': {'longitude': 100.0, 'sign': 'Rak', 'degree': 10.0, 'symbol': '♋'},
            'midheaven': {'longitude': 250.0, 'sign': 'Strelec', 'degree': 10.0, 'symbol': '♐'},
        }
        aspects_mock.return_value = []
        generate_report_mock.return_value = {
            'rating': 6,
            'energy': 'Force test.',
            'themes': ['T1'],
            'focus': ['F1'],
            'avoid': ['A1'],
        }

        target_date = date(2026, 3, 4)
        first = get_or_generate_moment_report(report_date=target_date, model_name='openai:gpt-5.2')
        second = get_or_generate_moment_report(
            report_date=target_date,
            model_name='openai:gpt-5.2',
            force=True,
        )

        self.assertFalse(getattr(first, '_cache_hit', True))
        self.assertFalse(getattr(second, '_cache_hit', True))
        self.assertEqual(generate_report_mock.call_count, 2)
        self.assertEqual(MomentReport.objects.filter(report_date=target_date, model_ref='openai:gpt-5.2').count(), 1)

    @patch('transits.moment_service._generate_ai_moment_report')
    @patch('transits.moment_service.calculate_moment_aspects')
    @patch('transits.moment_service.calculate_moment_angles')
    @patch('transits.moment_service.calculate_moment_snapshot')
    def test_moment_report_cache_is_scoped_by_location(
        self,
        snapshot_mock,
        angles_mock,
        aspects_mock,
        generate_report_mock,
    ):
        snapshot_mock.return_value = []
        angles_mock.return_value = {
            'ascendant': {'longitude': 100.0, 'sign': 'Rak', 'degree': 10.0, 'symbol': '♋'},
            'midheaven': {'longitude': 250.0, 'sign': 'Strelec', 'degree': 10.0, 'symbol': '♐'},
        }
        aspects_mock.return_value = []
        generate_report_mock.return_value = {
            'rating': 6,
            'energy': 'Lokálny test.',
            'themes': ['T1'],
            'focus': ['F1'],
            'avoid': ['A1'],
        }

        target_date = date(2026, 3, 4)
        first = get_or_generate_moment_report(
            report_date=target_date,
            model_name='openai:gpt-5.2',
            location={'lat': 48.1486, 'lon': 17.1077, 'city': 'Bratislava', 'country': 'Slovensko'},
        )
        second = get_or_generate_moment_report(
            report_date=target_date,
            model_name='openai:gpt-5.2',
            location={'lat': 48.1486, 'lon': 17.1077, 'city': 'Bratislava', 'country': 'Slovensko'},
        )
        third = get_or_generate_moment_report(
            report_date=target_date,
            model_name='openai:gpt-5.2',
            location={'lat': 49.0, 'lon': 18.0, 'city': 'Žilina', 'country': 'Slovensko'},
        )

        self.assertFalse(getattr(first, '_cache_hit', True))
        self.assertTrue(getattr(second, '_cache_hit', False))
        self.assertFalse(getattr(third, '_cache_hit', True))
        self.assertEqual(generate_report_mock.call_count, 2)

        rows = MomentReport.objects.filter(report_date=target_date, model_ref='openai:gpt-5.2')
        self.assertEqual(rows.count(), 2)
        self.assertEqual(set(rows.values_list('location_key', flat=True)), {'48.1486:17.1077', '49.0000:18.0000'})


class AIResponseCacheTests(TestCase):
    @override_settings(
        VERCEL_AI_GATEWAY_API_KEY='test-vercel-key',
        AI_RESPONSE_CACHE_ENABLED=True,
        AI_RESPONSE_CACHE_TTL_SECONDS=3600,
    )
    @patch('transits.gemini_utils._generate_with_openai')
    @patch('transits.gemini_utils.reserve_ai_call')
    def test_generate_ai_text_uses_cache_for_same_prompt(self, reserve_call_mock, openai_mock):
        openai_mock.return_value = '{"ok":true}'

        kwargs = {
            'model_name': 'openai:gpt-5.2',
            'contents': 'Vrat validny JSON {"ok":true}',
            'system_instruction': 'Len JSON.',
            'temperature': 0.0,
            'max_output_tokens': 80,
            'response_mime_type': 'application/json',
            'retries': 1,
            'timeout_seconds': 10,
        }
        first = generate_ai_text(**kwargs)
        second = generate_ai_text(**kwargs)

        self.assertEqual(first, second)
        self.assertEqual(openai_mock.call_count, 1)
        self.assertEqual(reserve_call_mock.call_count, 1)
        self.assertEqual(AIResponseCache.objects.count(), 1)
        cache_row = AIResponseCache.objects.first()
        self.assertEqual(cache_row.hits, 1)

    @override_settings(
        VERCEL_AI_GATEWAY_API_KEY='test-vercel-key',
        AI_RESPONSE_CACHE_ENABLED=False,
        AI_RESPONSE_CACHE_TTL_SECONDS=3600,
    )
    @patch('transits.gemini_utils._generate_with_openai')
    @patch('transits.gemini_utils.reserve_ai_call')
    def test_generate_ai_text_without_cache_calls_provider_each_time(self, reserve_call_mock, openai_mock):
        openai_mock.return_value = '{"ok":true}'

        kwargs = {
            'model_name': 'openai:gpt-5.2',
            'contents': 'Vrat validny JSON {"ok":true}',
            'system_instruction': 'Len JSON.',
            'temperature': 0.0,
            'max_output_tokens': 80,
            'response_mime_type': 'application/json',
            'retries': 1,
            'timeout_seconds': 10,
        }
        _ = generate_ai_text(**kwargs)
        _ = generate_ai_text(**kwargs)

        self.assertEqual(openai_mock.call_count, 2)
        self.assertEqual(reserve_call_mock.call_count, 2)

    @override_settings(
        VERCEL_AI_GATEWAY_API_KEY='test-vercel-key',
        VERCEL_AI_GATEWAY_BASE_URL='https://ai-gateway.vercel.sh/v1',
        AI_RESPONSE_CACHE_ENABLED=False,
    )
    @patch('transits.gemini_utils._generate_with_openai')
    @patch('transits.gemini_utils.reserve_ai_call')
    def test_generate_ai_text_routes_vercel_provider_via_openai_compat(
        self,
        reserve_call_mock,
        openai_mock,
    ):
        openai_mock.return_value = '{"ok":true}'
        response_text = generate_ai_text(
            model_name='vercel:openai/gpt-5.2',
            contents='Vrat JSON.',
            system_instruction='Len JSON.',
            temperature=0,
            max_output_tokens=50,
            response_mime_type='application/json',
            retries=1,
            timeout_seconds=10,
        )
        self.assertEqual(response_text, '{"ok":true}')
        self.assertEqual(openai_mock.call_count, 1)
        kwargs = openai_mock.call_args.kwargs
        self.assertEqual(kwargs.get('base_url'), 'https://ai-gateway.vercel.sh/v1')
        self.assertEqual(kwargs.get('model_name'), 'openai/gpt-5.2')

    @override_settings(
        VERCEL_AI_GATEWAY_API_KEY='test-vercel-key',
        VERCEL_AI_GATEWAY_BASE_URL='https://ai-gateway.vercel.sh/v1',
        AI_FORCE_VERCEL_GATEWAY=True,
        AI_RESPONSE_CACHE_ENABLED=False,
    )
    @patch('transits.gemini_utils._generate_with_openai')
    @patch('transits.gemini_utils.reserve_ai_call')
    def test_generate_ai_text_force_vercel_gateway_for_openai_ref(
        self,
        reserve_call_mock,
        openai_mock,
    ):
        openai_mock.return_value = '{"ok":true}'
        response_text = generate_ai_text(
            model_name='openai:gpt-5.2',
            contents='Vrat JSON.',
            system_instruction='Len JSON.',
            temperature=0,
            max_output_tokens=50,
            response_mime_type='application/json',
            retries=1,
            timeout_seconds=10,
        )
        self.assertEqual(response_text, '{"ok":true}')
        self.assertEqual(openai_mock.call_count, 1)
        kwargs = openai_mock.call_args.kwargs
        self.assertEqual(kwargs.get('base_url'), 'https://ai-gateway.vercel.sh/v1')
        self.assertEqual(kwargs.get('model_name'), 'openai/gpt-5.2')

    @override_settings(
        VERCEL_AI_GATEWAY_API_KEY='test-vercel-key',
        VERCEL_AI_GATEWAY_BASE_URL='https://ai-gateway.vercel.sh/v1',
        AI_RESPONSE_CACHE_ENABLED=False,
    )
    @patch('transits.gemini_utils._generate_with_openai')
    @patch('transits.gemini_utils.reserve_ai_call')
    def test_generate_ai_text_accepts_vercel_route_style_model_without_prefix(
        self,
        reserve_call_mock,
        openai_mock,
    ):
        openai_mock.return_value = '{"ok":true}'
        response_text = generate_ai_text(
            model_name='openai/gpt-5.2',
            contents='Vrat JSON.',
            system_instruction='Len JSON.',
            temperature=0,
            max_output_tokens=50,
            response_mime_type='application/json',
            retries=1,
            timeout_seconds=10,
        )
        self.assertEqual(response_text, '{"ok":true}')
        self.assertEqual(openai_mock.call_count, 1)
        kwargs = openai_mock.call_args.kwargs
        self.assertEqual(kwargs.get('base_url'), 'https://ai-gateway.vercel.sh/v1')
        self.assertEqual(kwargs.get('model_name'), 'openai/gpt-5.2')


@skipUnless(
    os.getenv('RUN_REAL_AI_TESTS') == '1',
    "Set RUN_REAL_AI_TESTS=1 to execute real provider request tests.",
)
class RealAiRequestTests(TestCase):
    def test_real_ai_json_request(self):
        model = os.getenv('REAL_AI_MODEL', 'openai:gpt-5.2')
        response_text = generate_ai_text(
            model_name=model,
            contents='Vráť presne JSON objekt {"ok":true,"domain":"astrology"}',
            system_instruction='Odpovedz striktne validným JSON objektom.',
            temperature=0,
            max_output_tokens=60,
            response_mime_type='application/json',
            retries=1,
            timeout_seconds=35,
        )
        payload = parse_json_payload(response_text)
        self.assertIsInstance(payload, dict)
        self.assertTrue(payload.get('ok'))

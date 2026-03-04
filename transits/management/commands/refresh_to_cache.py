from datetime import timedelta
import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from transits.access import user_has_pro_account
from transits.gemini_utils import get_default_model, has_ai_key
from transits.moment_service import get_or_generate_moment_report
from transits.models import AIDayReportCache, AINatalAnalysisCache, AIModelOption, NatalProfile
from transits.views import (
    _generate_and_save_analyses,
    _get_compare_models_limit,
    _get_or_generate_ai_day_report_for_model,
    _get_or_generate_natal_compare_for_model,
)


def _parse_csv(value):
    return [part.strip() for part in str(value or '').split(',') if part.strip()]


class Command(BaseCommand):
    help = "Prewarm/refresh AI cache pre day report, natálne analýzy, globálne natal polia a moment report."

    def add_arguments(self, parser):
        parser.add_argument(
            '--profiles',
            choices=['pro', 'free', 'all'],
            default='pro',
            help='Scope profilov (default: pro).',
        )
        parser.add_argument(
            '--days',
            default='0,1,2',
            help='CSV day_offset hodnôt pre AI day cache (default: 0,1,2).',
        )
        parser.add_argument(
            '--model-refs',
            default='',
            help='Voliteľný CSV zoznam model_ref override (inak všetky enabled+available).',
        )
        parser.add_argument(
            '--max-profiles',
            type=int,
            default=0,
            help='Limit profilov (0 = bez limitu).',
        )
        parser.add_argument(
            '--skip-natal',
            action='store_true',
            help='Preskočí refresh natálnych analýz cache.',
        )
        parser.add_argument(
            '--skip-day',
            action='store_true',
            help='Preskočí refresh AI day report cache.',
        )
        parser.add_argument(
            '--invalidate',
            action='store_true',
            help='Pred refreshom vymaže existujúce cache záznamy pre cieľové modely.',
        )
        parser.add_argument(
            '--with-global-natal',
            action='store_true',
            help='Vygeneruje aj globálne natal_analysis_json/natal_aspects_json pre každý profil.',
        )
        parser.add_argument(
            '--global-model',
            default='',
            help='Voliteľný model_ref override pre globálne natálne analýzy (default: aktívny DEFAULT_MODEL).',
        )
        parser.add_argument(
            '--with-moment',
            action='store_true',
            help='Vygeneruje aj moment report cache (Bratislava) pre zvolený rozsah dní.',
        )
        parser.add_argument(
            '--moment-days',
            default='0',
            help='CSV day_offset hodnôt pre moment report warmup (default: 0).',
        )
        parser.add_argument(
            '--moment-model',
            default='',
            help='Voliteľný model_ref override pre moment report warmup.',
        )

    def _resolve_day_offsets(self, raw_value):
        offsets = []
        for token in _parse_csv(raw_value):
            try:
                val = int(token)
            except Exception:
                raise CommandError(f'Neplatný day offset: {token}')
            if val < -30 or val > 365:
                raise CommandError(f'day offset mimo povolený rozsah: {val}')
            offsets.append(val)
        if not offsets:
            offsets = [0]
        return sorted(set(offsets))

    def _is_pro_profile(self, profile):
        if bool(profile.is_pro):
            return True
        user = getattr(profile, 'user', None)
        if not user:
            return False
        return user_has_pro_account(user)

    def _resolve_models(self, *, profile_is_pro, requested_refs, max_models):
        qs = AIModelOption.objects.filter(is_enabled=True, is_available=True).order_by('sort_order', 'label')
        if requested_refs:
            qs = qs.filter(model_ref__in=requested_refs)
        if not profile_is_pro:
            qs = qs.filter(is_pro_only=False)
        refs = list(qs.values_list('model_ref', flat=True))
        if not requested_refs and max_models > 0:
            refs = refs[:max_models]
        return refs

    def handle(self, *args, **options):
        skip_natal = bool(options.get('skip_natal'))
        skip_day = bool(options.get('skip_day'))
        with_global_natal = bool(options.get('with_global_natal'))
        with_moment = bool(options.get('with_moment'))
        if skip_natal and skip_day and not with_global_natal and not with_moment:
            raise CommandError(
                'Nič na refresh: --skip-natal aj --skip-day sú zapnuté a chýba --with-global-natal/--with-moment.'
            )

        requested_refs = _parse_csv(options.get('model_refs'))
        day_offsets = self._resolve_day_offsets(options.get('days'))
        moment_offsets = self._resolve_day_offsets(options.get('moment_days')) if with_moment else []
        profile_scope = options.get('profiles') or 'pro'
        max_profiles = max(0, int(options.get('max_profiles') or 0))
        invalidate = bool(options.get('invalidate'))
        global_model_ref = str(options.get('global_model') or '').strip() or get_default_model()
        moment_model_ref = str(options.get('moment_model') or '').strip() or get_default_model()
        compare_limit = _get_compare_models_limit()

        profiles_qs = NatalProfile.objects.order_by('id')
        if profile_scope == 'pro':
            profiles = [p for p in profiles_qs.iterator() if self._is_pro_profile(p)]
        elif profile_scope == 'free':
            profiles = [p for p in profiles_qs.iterator() if not self._is_pro_profile(p)]
        else:
            profiles = list(profiles_qs.iterator())

        if max_profiles:
            profiles = profiles[:max_profiles]

        total_profiles = len(profiles)
        self.stdout.write(
            (
                f"Refresh cache: profiles={total_profiles}, scope={profile_scope}, "
                f"days={day_offsets}, moment_days={moment_offsets}, invalidate={invalidate}, "
                f"with_global_natal={with_global_natal}, with_moment={with_moment}, "
                f"compare_limit={compare_limit}"
            )
        )
        if with_global_natal and not has_ai_key(model_name=global_model_ref):
            self.stdout.write(
                self.style.WARNING(
                    f"Globálne natálne analýzy: model {global_model_ref} nemá API key v .env (bude fallback/skip)."
                )
            )
        if with_moment and not has_ai_key(model_name=moment_model_ref):
            self.stdout.write(
                self.style.WARNING(
                    f"Moment warmup: model {moment_model_ref} nemá API key v .env (report sa vygeneruje fallbackom)."
                )
            )

        stats = {
            'profiles': total_profiles,
            'models_processed': 0,
            'natal_ok': 0,
            'natal_err': 0,
            'day_ok': 0,
            'day_err': 0,
            'global_natal_ok': 0,
            'global_natal_err': 0,
            'moment_ok': 0,
            'moment_err': 0,
            'cache_hits': 0,
        }
        limit_exceeded = False

        for idx, profile in enumerate(profiles, start=1):
            profile_is_pro = self._is_pro_profile(profile)
            model_refs = self._resolve_models(
                profile_is_pro=profile_is_pro,
                requested_refs=requested_refs,
                max_models=compare_limit,
            )
            has_compare_work = (not skip_natal) or (not skip_day)
            if not model_refs and has_compare_work:
                self.stdout.write(
                    self.style.WARNING(
                        f"[{idx}/{total_profiles}] profile={profile.pk} ({profile.name}): žiadne dostupné modely"
                    )
                )
                if not with_global_natal:
                    continue

            if invalidate and model_refs:
                AINatalAnalysisCache.objects.filter(profile=profile, model_ref__in=model_refs).delete()
                AIDayReportCache.objects.filter(profile=profile, model_ref__in=model_refs).delete()

            stats['models_processed'] += len(model_refs)
            self.stdout.write(
                (
                    f"[{idx}/{total_profiles}] profile={profile.pk} ({profile.name}) "
                    f"models={len(model_refs)} pro={profile_is_pro}"
                )
            )

            if with_global_natal:
                started_at = time.monotonic()
                self.stdout.write(f"  global_natal {global_model_ref}: start")
                if _generate_and_save_analyses(profile, model_name=global_model_ref):
                    stats['global_natal_ok'] += 1
                    self.stdout.write(
                        f"  global_natal {global_model_ref}: ok ({time.monotonic() - started_at:.1f}s)"
                    )
                else:
                    stats['global_natal_err'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"  global_natal {global_model_ref}: error ({time.monotonic() - started_at:.1f}s)"
                        )
                    )

            if not skip_natal and model_refs:
                for model_ref in model_refs:
                    started_at = time.monotonic()
                    self.stdout.write(f"  natal_compare {model_ref}: start")
                    result, err = _get_or_generate_natal_compare_for_model(
                        profile,
                        model_ref,
                        request=None,
                        key_error_status=503,
                    )
                    if result.get('cache_hit'):
                        stats['cache_hits'] += 1
                    if err:
                        stats['natal_err'] += 1
                        if err.get('limit_exceeded'):
                            limit_exceeded = True
                        self.stdout.write(
                            self.style.WARNING(
                                f"  natal_compare {model_ref}: {err.get('error')} ({time.monotonic() - started_at:.1f}s)"
                            )
                        )
                    else:
                        stats['natal_ok'] += 1
                        cache_suffix = " cache_hit" if result.get('cache_hit') else ""
                        fallback_suffix = " fallback" if result.get('fallback_used') else ""
                        self.stdout.write(
                            f"  natal_compare {model_ref}: ok{cache_suffix}{fallback_suffix} ({time.monotonic() - started_at:.1f}s)"
                        )

            if limit_exceeded:
                break

            if not skip_day and model_refs:
                for day_offset in day_offsets:
                    target_date = timezone.localdate() + timedelta(days=day_offset)
                    active_transits = None
                    for model_ref in model_refs:
                        started_at = time.monotonic()
                        self.stdout.write(
                            f"  day_compare {target_date.isoformat()} {model_ref}: start"
                        )
                        item, err, active_transits = _get_or_generate_ai_day_report_for_model(
                            profile,
                            target_date,
                            model_ref,
                            request=None,
                            active_transits=active_transits,
                            key_error_status=503,
                        )
                        if item.get('cache_hit'):
                            stats['cache_hits'] += 1
                        if err:
                            stats['day_err'] += 1
                            if err.get('limit_exceeded'):
                                limit_exceeded = True
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  day_compare {target_date.isoformat()} {model_ref}: "
                                    f"{err.get('error')} ({time.monotonic() - started_at:.1f}s)"
                                )
                            )
                        else:
                            stats['day_ok'] += 1
                            cache_suffix = " cache_hit" if item.get('cache_hit') else ""
                            self.stdout.write(
                                f"  day_compare {target_date.isoformat()} {model_ref}: "
                                f"ok{cache_suffix} ({time.monotonic() - started_at:.1f}s)"
                            )
                    if limit_exceeded:
                        break
            if limit_exceeded:
                break

        if with_moment:
            for day_offset in moment_offsets:
                target_date = timezone.localdate() + timedelta(days=day_offset)
                started_at = time.monotonic()
                self.stdout.write(f"moment {target_date.isoformat()} {moment_model_ref}: start")
                try:
                    report = get_or_generate_moment_report(
                        report_date=target_date,
                        force=bool(invalidate),
                        model_name=moment_model_ref,
                    )
                    if bool(getattr(report, '_cache_hit', False)):
                        stats['cache_hits'] += 1
                    stats['moment_ok'] += 1
                    cache_suffix = " cache_hit" if bool(getattr(report, '_cache_hit', False)) else ""
                    self.stdout.write(
                        f"moment {target_date.isoformat()} {moment_model_ref}: ok{cache_suffix} ({time.monotonic() - started_at:.1f}s)"
                    )
                except Exception as exc:
                    stats['moment_err'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"moment {target_date.isoformat()} {moment_model_ref}: "
                            f"{exc} ({time.monotonic() - started_at:.1f}s)"
                        )
                    )

        summary = (
            f"profiles={stats['profiles']} "
            f"models={stats['models_processed']} "
            f"natal_ok={stats['natal_ok']} natal_err={stats['natal_err']} "
            f"day_ok={stats['day_ok']} day_err={stats['day_err']} "
            f"global_natal_ok={stats['global_natal_ok']} global_natal_err={stats['global_natal_err']} "
            f"moment_ok={stats['moment_ok']} moment_err={stats['moment_err']} "
            f"cache_hits={stats['cache_hits']}"
        )
        if limit_exceeded:
            self.stdout.write(self.style.WARNING(f"Refresh zastavený kvôli AI limitu. {summary}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Refresh cache hotový. {summary}"))

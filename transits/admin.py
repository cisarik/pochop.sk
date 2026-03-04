from datetime import date

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from .access import user_has_pro_account
from .credits import record_credit_adjustment, top_up_user_credits
from .vercel_gateway import sync_vercel_models, VercelGatewaySyncError
from .models import (
    TransitAspect,
    NatalProfile,
    UserProStatus,
    SlovakCity,
    MomentReport,
    GeminiConfig,
    GeminiDailyUsage,
    AIModelOption,
    AIResponseCache,
    LocationLookupCache,
    AIDayReportCache,
    AIDayReportDailyStat,
    AINatalAnalysisCache,
    AICreditTransaction,
)

admin.site.unregister(User)


class UserProStatusInline(admin.StackedInline):
    model = UserProStatus
    fk_name = 'user'
    extra = 0
    max_num = 1
    can_delete = False
    verbose_name = 'Pro účet'
    verbose_name_plural = 'Pro účet'
    fields = ['is_pro', 'credits']

    def get_extra(self, request, obj=None, **kwargs):
        if obj is None:
            return 0
        has_row = UserProStatus.objects.filter(user=obj).exists()
        return 0 if has_row else 1


@admin.register(User)
class PochopUserAdmin(BaseUserAdmin):
    inlines = [UserProStatusInline]
    list_display = list(BaseUserAdmin.list_display) + ['pro_account']
    list_filter = list(BaseUserAdmin.list_filter) + ['pro_status__is_pro']
    actions = ['mark_users_as_pro', 'mark_users_as_free']

    @admin.display(boolean=True, description='Pro účet')
    def pro_account(self, obj):
        return user_has_pro_account(obj)

    @admin.action(description='Nastaviť Pro účet (vybraní používatelia)')
    def mark_users_as_pro(self, request, queryset):
        updated = 0
        for user in queryset.iterator():
            UserProStatus.objects.update_or_create(
                user=user,
                defaults={'is_pro': True},
            )
            updated += 1
        self.message_user(request, f'Pro účet zapnutý pre {updated} používateľov.', level=messages.SUCCESS)

    @admin.action(description='Vypnúť Pro účet (vybraní používatelia)')
    def mark_users_as_free(self, request, queryset):
        updated = 0
        for user in queryset.iterator():
            UserProStatus.objects.update_or_create(
                user=user,
                defaults={'is_pro': False},
            )
            updated += 1
        self.message_user(request, f'Pro účet vypnutý pre {updated} používateľov.', level=messages.SUCCESS)


@admin.register(TransitAspect)
class TransitAspectAdmin(admin.ModelAdmin):
    list_display = [
        'transit_planet', 'aspect_type', 'natal_planet',
        'effect', 'has_custom_text'
    ]
    list_filter = ['transit_planet', 'natal_planet', 'aspect_type', 'effect']
    search_fields = ['default_text', 'user_text']
    list_editable = ['effect']
    fieldsets = (
        ('Aspekt', {
            'fields': ('transit_planet', 'natal_planet', 'aspect_type', 'effect')
        }),
        ('Texty', {
            'fields': ('default_text', 'user_text'),
            'description': (
                'Predvolený text je automaticky generovaný. '
                'Ak vyplníte vlastný text, zobrazí sa namiesto predvoleného.'
            )
        }),
    )

    @admin.display(boolean=True, description='Vlastný text')
    def has_custom_text(self, obj):
        return bool(obj.user_text)


@admin.register(NatalProfile)
class NatalProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'gender', 'is_pro', 'user', 'public_hash', 'has_encrypted_birth', 'created_at']
    search_fields = ['name', 'user__username', 'public_hash']
    list_filter = ['gender', 'is_pro', 'created_at']
    list_editable = ['is_pro']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['mark_as_pro', 'remove_pro']

    def _sync_pro_status_from_profiles(self, queryset):
        for profile in queryset.exclude(user__isnull=True).only('user_id', 'is_pro').iterator():
            UserProStatus.objects.update_or_create(
                user_id=profile.user_id,
                defaults={'is_pro': bool(profile.is_pro)},
            )

    @admin.display(boolean=True, description='PII encrypted')
    def has_encrypted_birth(self, obj):
        return bool(obj.birth_date_encrypted and obj.birth_place_encrypted)

    @admin.action(description='Nastaviť Pro účet (vybrané profily)')
    def mark_as_pro(self, request, queryset):
        updated = queryset.update(is_pro=True)
        self._sync_pro_status_from_profiles(queryset)
        self.message_user(request, f'Pro účet zapnutý pre {updated} profil(ov).', level=messages.SUCCESS)

    @admin.action(description='Vypnúť Pro účet (vybrané profily)')
    def remove_pro(self, request, queryset):
        updated = queryset.update(is_pro=False)
        self._sync_pro_status_from_profiles(queryset)
        self.message_user(request, f'Pro účet vypnutý pre {updated} profil(ov).', level=messages.SUCCESS)


@admin.register(UserProStatus)
class UserProStatusAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_pro', 'credits', 'updated_at']
    list_filter = ['is_pro', 'updated_at']
    search_fields = ['user__username', 'user__email']
    list_editable = ['is_pro']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['add_500_credits', 'add_2000_credits', 'add_10000_credits']

    @admin.action(description='Pridať +500 kreditov')
    def add_500_credits(self, request, queryset):
        self._bulk_top_up(request, queryset, 500)

    @admin.action(description='Pridať +2000 kreditov')
    def add_2000_credits(self, request, queryset):
        self._bulk_top_up(request, queryset, 2000)

    @admin.action(description='Pridať +10000 kreditov')
    def add_10000_credits(self, request, queryset):
        self._bulk_top_up(request, queryset, 10000)

    def _bulk_top_up(self, request, queryset, amount):
        success = 0
        for row in queryset.only('user_id').iterator():
            try:
                top_up_user_credits(
                    user_id=row.user_id,
                    amount=int(amount),
                    note=f'Admin action by {request.user.username}',
                )
                success += 1
            except Exception:
                continue
        self.message_user(
            request,
            f'Kredity navýšené pre {success} používateľov (+{int(amount)}).',
            level=messages.SUCCESS,
        )

    def save_model(self, request, obj, form, change):
        previous_credits = None
        if obj.pk:
            previous_credits = (
                UserProStatus.objects
                .filter(pk=obj.pk)
                .values_list('credits', flat=True)
                .first()
            )
        super().save_model(request, obj, form, change)
        NatalProfile.objects.filter(user=obj.user).update(is_pro=bool(obj.is_pro))
        if previous_credits is not None:
            delta = int(obj.credits or 0) - int(previous_credits or 0)
            if delta:
                record_credit_adjustment(
                    user_id=obj.user_id,
                    delta=delta,
                    credits_before=previous_credits,
                    credits_after=obj.credits,
                    note=f'Manual admin edit by {request.user.username}',
                )


@admin.register(SlovakCity)
class SlovakCityAdmin(admin.ModelAdmin):
    list_display = ['name', 'district', 'lat', 'lon']
    search_fields = ['name', 'district']
    list_filter = ['district']


@admin.register(MomentReport)
class MomentReportAdmin(admin.ModelAdmin):
    list_display = ['report_date', 'model_ref', 'location_name', 'location_key', 'timezone', 'updated_at']
    list_filter = ['model_ref', 'timezone']
    search_fields = ['report_date', 'model_ref', 'location_name', 'location_key']
    readonly_fields = ['generated_at', 'updated_at']


@admin.register(GeminiConfig)
class GeminiConfigAdmin(admin.ModelAdmin):
    list_display = [
        'default_model',
        'max_calls_daily',
        'max_compare_models',
        'today_calls',
        'has_vercel_env_key',
        'updated_at',
    ]
    readonly_fields = ['created_at', 'updated_at', 'env_keys_status']
    fields = [
        'default_model',
        'max_calls_daily',
        'max_compare_models',
        'env_keys_status',
        'created_at',
        'updated_at',
    ]

    @admin.display(boolean=True, description='Vercel key (.env)')
    def has_vercel_env_key(self, obj):
        return bool(
            (getattr(settings, 'VERCEL_AI_GATEWAY_API_KEY', '') or '').strip()
            or (getattr(settings, 'AI_GATEWAY_API_KEY', '') or '').strip()
        )

    @admin.display(description='API key stav')
    def env_keys_status(self, obj):
        vercel = 'OK' if self.has_vercel_env_key(obj) else 'chýba'
        return (
            f"VERCEL_AI_GATEWAY_API_KEY: {vercel} "
            "(kľúč sa číta iba z .env, runtime ide cez Vercel AI Gateway)"
        )

    def has_add_permission(self, request):
        # Singleton konfigurácia
        return not GeminiConfig.objects.exists()

    @admin.display(description='Volaní dnes')
    def today_calls(self, obj):
        usage = GeminiDailyUsage.objects.filter(usage_date=date.today()).first()
        return usage.calls_made if usage else 0

    def save_model(self, request, obj, form, change):
        model_changed = ('default_model' in form.changed_data)
        super().save_model(request, obj, form, change)

        if not model_changed:
            return

        from .views import _invalidate_all_natal_analyses, _generate_and_save_analyses
        total = NatalProfile.objects.count()
        ok = 0
        fail = 0
        users_marked = 0
        eager_users_refresh = bool(getattr(settings, 'AI_MODEL_SWITCH_EAGER_USERS_REFRESH', False))
        try:
            if eager_users_refresh:
                for profile in NatalProfile.objects.all().iterator():
                    if _generate_and_save_analyses(profile, model_name=obj.default_model):
                        ok += 1
                    else:
                        fail += 1
            else:
                users_marked = _invalidate_all_natal_analyses()

            if eager_users_refresh:
                messages.info(
                    request,
                    (
                        f"DEFAULT_MODEL zmenený na {obj.default_model}. Refresh analýz dokončený: "
                        f"OK={ok}, FAIL={fail}, PROFILES={total}."
                    ),
                )
            else:
                messages.info(
                    request,
                    (
                        f"DEFAULT_MODEL zmenený na {obj.default_model}. "
                        f"Lazy režim: označené profily na refresh pri ďalšej návšteve: {users_marked}/{total}."
                    ),
                )
        except Exception as exc:
            messages.error(
                request,
                f"Model bol uložený, ale refresh analýz zlyhal: {exc}",
            )


@admin.register(GeminiDailyUsage)
class GeminiDailyUsageAdmin(admin.ModelAdmin):
    list_display = ['usage_date', 'calls_made', 'updated_at']
    readonly_fields = ['usage_date', 'calls_made', 'updated_at']
    ordering = ['-usage_date']


@admin.register(AIModelOption)
class AIModelOptionAdmin(admin.ModelAdmin):
    list_display = [
        'label',
        'model_ref',
        'source',
        'owner',
        'model_type',
        'is_available',
        'is_pro_only',
        'is_enabled',
        'sort_order',
        'last_synced_at',
    ]
    list_filter = ['source', 'is_enabled', 'is_available', 'is_pro_only', 'model_type', 'owner']
    search_fields = ['label', 'model_ref', 'owner', 'description']
    list_editable = ['is_enabled', 'is_pro_only', 'sort_order']
    readonly_fields = ['last_synced_at']
    change_list_template = 'admin/transits/aimodeloption/change_list.html'
    actions = ['mark_models_active', 'mark_models_inactive', 'sync_selected_labels_from_vercel']

    @admin.action(description='Nastaviť ako aktívne')
    def mark_models_active(self, request, queryset):
        updated = queryset.update(is_enabled=True)
        self.message_user(request, f'Aktivované modely: {updated}', level=messages.SUCCESS)

    @admin.action(description='Nastaviť ako neaktívne')
    def mark_models_inactive(self, request, queryset):
        updated = queryset.update(is_enabled=False)
        self.message_user(request, f'Deaktivované modely: {updated}', level=messages.SUCCESS)

    fieldsets = (
        ('Základ', {
            'fields': (
                'label',
                'model_ref',
                'source',
                'owner',
                'model_type',
                'description',
            )
        }),
        ('Použitie v appke', {
            'fields': (
                'is_available',
                'is_enabled',
                'is_pro_only',
                'sort_order',
                'last_synced_at',
            )
        }),
        ('Metadata z Vercel', {
            'fields': (
                'context_window',
                'max_tokens',
                'tags_json',
                'pricing_json',
                'raw_meta_json',
            )
        }),
    )

    @admin.action(description='Aktualizovať labely vybraných Vercel modelov podľa posledného raw meta')
    def sync_selected_labels_from_vercel(self, request, queryset):
        updated = 0
        for row in queryset.filter(source='vercel').iterator():
            raw = row.raw_meta_json if isinstance(row.raw_meta_json, dict) else {}
            label = str(raw.get('name') or raw.get('display_name') or row.label or '').strip()
            if label and label != row.label:
                row.label = label
                row.save(update_fields=['label', 'updated_at'])
                updated += 1
        self.message_user(request, f'Aktualizované labely: {updated}', level=messages.SUCCESS)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'sync-vercel/',
                self.admin_site.admin_view(self.sync_vercel_view),
                name='transits_aimodeloption_sync_vercel',
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['vercel_sync_url'] = reverse('admin:transits_aimodeloption_sync_vercel')
        return super().changelist_view(request, extra_context=extra_context)

    def sync_vercel_view(self, request):
        try:
            stats = sync_vercel_models(
                disable_missing=True,
                enable_new=False,
                pro_only_for_new=True,
                timeout_seconds=25,
            )
            self.message_user(
                request,
                (
                    'Vercel sync hotový: '
                    f"remote={stats.get('total_remote')} "
                    f"created={stats.get('created')} updated={stats.get('updated')} "
                    f"unchanged={stats.get('unchanged')} missing={stats.get('missing')}"
                ),
                level=messages.SUCCESS,
            )
        except VercelGatewaySyncError as exc:
            self.message_user(request, f'Vercel sync zlyhal: {exc}', level=messages.ERROR)
        except Exception as exc:
            self.message_user(request, f'Neočakávaná chyba syncu: {exc}', level=messages.ERROR)
        return HttpResponseRedirect(reverse('admin:transits_aimodeloption_changelist'))


@admin.register(AIResponseCache)
class AIResponseCacheAdmin(admin.ModelAdmin):
    list_display = ['provider', 'model_name', 'hits', 'expires_at', 'updated_at']
    list_filter = ['provider', 'model_name']
    search_fields = ['cache_key', 'model_name']
    readonly_fields = [
        'cache_key',
        'provider',
        'model_name',
        'response_text',
        'hits',
        'expires_at',
        'created_at',
        'updated_at',
    ]
    ordering = ['-updated_at']


@admin.register(LocationLookupCache)
class LocationLookupCacheAdmin(admin.ModelAdmin):
    list_display = [
        'lookup_type',
        'cache_day',
        'provider',
        'hits',
        'expires_at',
        'last_served_at',
        'updated_at',
    ]
    list_filter = ['lookup_type', 'provider', 'cache_day']
    search_fields = ['lookup_key']
    readonly_fields = [
        'lookup_type',
        'lookup_key',
        'cache_day',
        'provider',
        'payload_json',
        'hits',
        'generated_at',
        'last_served_at',
        'expires_at',
        'created_at',
        'updated_at',
    ]
    ordering = ['-cache_day', '-updated_at']


@admin.register(AIDayReportCache)
class AIDayReportCacheAdmin(admin.ModelAdmin):
    list_display = [
        'target_date',
        'profile',
        'model_ref',
        'hits',
        'generated_at',
        'expires_at',
        'last_served_at',
    ]
    list_filter = ['target_date', 'model_ref']
    search_fields = ['profile__name', 'profile__user__username', 'model_ref']
    readonly_fields = [
        'profile',
        'target_date',
        'model_ref',
        'payload_json',
        'profile_updated_at',
        'hits',
        'generated_at',
        'last_served_at',
        'expires_at',
        'created_at',
        'updated_at',
    ]
    ordering = ['-target_date', '-updated_at']


@admin.register(AIDayReportDailyStat)
class AIDayReportDailyStatAdmin(admin.ModelAdmin):
    list_display = [
        'stat_date',
        'model_ref',
        'total_requests',
        'cache_hits',
        'generated_reports',
        'fallback_reports',
        'errors_count',
        'cache_hit_rate',
        'updated_at',
    ]
    list_filter = ['stat_date', 'model_ref']
    search_fields = ['model_ref']
    readonly_fields = [
        'stat_date',
        'model_ref',
        'total_requests',
        'cache_hits',
        'generated_reports',
        'fallback_reports',
        'errors_count',
        'updated_at',
    ]
    ordering = ['-stat_date', 'model_ref']

    @admin.display(description='Cache hit %')
    def cache_hit_rate(self, obj):
        if not obj.total_requests:
            return '0%'
        pct = (obj.cache_hits / obj.total_requests) * 100
        return f"{pct:.1f}%"


@admin.register(AINatalAnalysisCache)
class AINatalAnalysisCacheAdmin(admin.ModelAdmin):
    list_display = [
        'profile',
        'model_ref',
        'hits',
        'generated_at',
        'expires_at',
        'last_served_at',
    ]
    list_filter = ['model_ref']
    search_fields = ['profile__name', 'profile__user__username', 'model_ref']
    readonly_fields = [
        'profile',
        'model_ref',
        'analysis_json',
        'aspects_json',
        'profile_updated_at',
        'hits',
        'generated_at',
        'last_served_at',
        'expires_at',
        'created_at',
        'updated_at',
    ]
    ordering = ['-updated_at']


@admin.register(AICreditTransaction)
class AICreditTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'created_at',
        'user',
        'event_type',
        'credits_delta',
        'credits_before',
        'credits_after',
        'model_ref',
        'completion_tokens',
        'cache_hit',
    ]
    list_filter = ['event_type', 'cache_hit', 'model_ref', 'created_at']
    search_fields = ['user__username', 'user__email', 'model_ref', 'endpoint_path']
    readonly_fields = [
        'user',
        'pro_status',
        'event_type',
        'credits_delta',
        'credits_before',
        'credits_after',
        'credits_requested',
        'model_ref',
        'endpoint_path',
        'prompt_tokens',
        'completion_tokens',
        'total_tokens',
        'usage_source',
        'cache_hit',
        'meta_json',
        'created_at',
    ]
    ordering = ['-created_at']

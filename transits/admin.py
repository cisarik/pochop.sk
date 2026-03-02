from datetime import date

from django.contrib import admin, messages
from django.conf import settings
from .models import TransitAspect, NatalProfile, SlovakCity, MomentReport, GeminiConfig, GeminiDailyUsage


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
    list_display = ['name', 'gender', 'user', 'public_hash', 'has_encrypted_birth', 'created_at']
    search_fields = ['name', 'user__username', 'public_hash']
    list_filter = ['gender', 'created_at']
    readonly_fields = ['created_at', 'updated_at']

    @admin.display(boolean=True, description='PII encrypted')
    def has_encrypted_birth(self, obj):
        return bool(obj.birth_date_encrypted and obj.birth_place_encrypted)


@admin.register(SlovakCity)
class SlovakCityAdmin(admin.ModelAdmin):
    list_display = ['name', 'district', 'lat', 'lon']
    search_fields = ['name', 'district']
    list_filter = ['district']


@admin.register(MomentReport)
class MomentReportAdmin(admin.ModelAdmin):
    list_display = ['report_date', 'timezone', 'updated_at']
    search_fields = ['report_date']
    readonly_fields = ['generated_at', 'updated_at']


@admin.register(GeminiConfig)
class GeminiConfigAdmin(admin.ModelAdmin):
    list_display = [
        'default_model',
        'max_calls_daily',
        'today_calls',
        'has_gemini_env_key',
        'has_openai_env_key',
        'updated_at',
    ]
    readonly_fields = ['created_at', 'updated_at', 'env_keys_status']
    fields = ['default_model', 'max_calls_daily', 'env_keys_status', 'created_at', 'updated_at']

    @admin.display(boolean=True, description='Gemini key (.env)')
    def has_gemini_env_key(self, obj):
        return bool((getattr(settings, 'GEMINI_API_KEY', '') or '').strip())

    @admin.display(boolean=True, description='OpenAI key (.env)')
    def has_openai_env_key(self, obj):
        return bool((getattr(settings, 'OPENAI_API_KEY', '') or '').strip())

    @admin.display(description='API key stav')
    def env_keys_status(self, obj):
        gem = 'OK' if self.has_gemini_env_key(obj) else 'chýba'
        oai = 'OK' if self.has_openai_env_key(obj) else 'chýba'
        return f"GEMINI_API_KEY: {gem} | OPENAI_API_KEY: {oai} (kľúče sa čítajú iba z .env)"

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

        from .views import _generate_and_save_analyses
        from .moment_service import get_or_generate_moment_report

        total = NatalProfile.objects.count()
        ok = 0
        fail = 0
        try:
            for profile in NatalProfile.objects.all().iterator():
                if _generate_and_save_analyses(profile, model_name=obj.default_model):
                    ok += 1
                else:
                    fail += 1

            get_or_generate_moment_report(force=True, model_name=obj.default_model)
            messages.info(
                request,
                f"DEFAULT_MODEL zmenený na {obj.default_model}. Refresh analýz dokončený: OK={ok}, FAIL={fail}, PROFILES={total}.",
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

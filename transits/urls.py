from django.urls import path
from . import views

app_name = 'transits'

urlpatterns = [
    path('', views.index, name='index'),
    path('lexikon/', views.lexikon, name='lexikon'),
    path('okamih/', views.moment_overview, name='moment_overview'),
    path('email/verify/sent/', views.verify_email_sent_view, name='verify_email_sent'),
    path('email/verify/resend/', views.resend_verification_view, name='verify_email_resend'),
    path(
        'email/verify/<uidb64>/<token>/',
        views.verify_email_confirm_view,
        name='verify_email_confirm',
    ),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('loginpro/', views.loginpro_view, name='loginpro'),
    path('password/change/', views.password_change_view, name='password_change'),
    path('password/change/done/', views.password_change_done_view, name='password_change_done'),
    path('password/reset/', views.PochopPasswordResetView.as_view(), name='password_reset'),
    path('password/reset/done/', views.PochopPasswordResetDoneView.as_view(), name='password_reset_done'),
    path(
        'password/reset/<uidb64>/<token>/',
        views.PochopPasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
    path(
        'password/reset/complete/',
        views.PochopPasswordResetCompleteView.as_view(),
        name='password_reset_complete',
    ),
    path('logout/', views.logout_view, name='logout'),
    path('natal/', views.natal_analysis, name='natal_analysis'),
    path('timeline/', views.timeline, name='timeline'),
    path('timeline/<int:profile_id>/', views.timeline, name='timeline_profile'),
    path('api/cities/', views.api_cities, name='api_cities'),
    path('api/transits/<int:profile_id>/', views.api_transits, name='api_transits'),
    path('api/ai-day-report/', views.ai_day_report, name='ai_day_report'),
    path('api/ai-model/select/', views.api_select_ai_model, name='api_select_ai_model'),
    path('api/natal-analysis-status/', views.api_natal_analysis_status, name='api_natal_analysis_status'),
]

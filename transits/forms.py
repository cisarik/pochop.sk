from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.core.validators import validate_email


class RegistrationForm(forms.Form):
    """Registračný formulár s natálnymi údajmi."""

    GENDER_CHOICES = (
        ('male', 'Muž'),
        ('female', 'Žena'),
    )

    username = forms.CharField(
        label='Používateľské meno',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Používateľské meno',
            'autocomplete': 'username',
            'aria-label': 'Používateľské meno',
        }),
    )
    email = forms.EmailField(
        label='E-mail',
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'E-mail',
            'autocomplete': 'email',
            'aria-label': 'E-mail',
        }),
    )
    password1 = forms.CharField(
        label='Heslo',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Heslo',
            'autocomplete': 'new-password',
            'aria-label': 'Heslo',
        }),
    )
    password2 = forms.CharField(
        label='Potvrdenie hesla',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Potvrdenie hesla',
            'autocomplete': 'new-password',
            'aria-label': 'Potvrdenie hesla',
        }),
    )
    birth_date = forms.DateField(
        label='Dátum narodenia',
        input_formats=['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'DD.MM.RRRR',
            'inputmode': 'numeric',
            'maxlength': '10',
            'autocomplete': 'bday',
            'id': 'id_birth_date',
        }),
    )
    birth_time = forms.TimeField(
        label='Čas narodenia',
        required=False,
        input_formats=['%H:%M', '%H.%M'],
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'HH:MM (napr. 14:30)',
            'inputmode': 'numeric',
            'maxlength': '5',
            'id': 'id_birth_time',
        }),
    )
    birth_place = forms.CharField(
        label='Miesto narodenia',
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Začni písať mesto...',
            'id': 'birthPlaceInput',
            'autocomplete': 'off',
        }),
    )
    gender = forms.ChoiceField(
        label='Pohlavie',
        choices=GENDER_CHOICES,
        initial='male',
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-input',
            'id': 'id_gender',
            'aria-label': 'Pohlavie',
        }),
    )
    birth_lat = forms.FloatField(widget=forms.HiddenInput(), required=False)
    birth_lon = forms.FloatField(widget=forms.HiddenInput(), required=False)

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Toto používateľské meno je už obsadené.')
        return username

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        try:
            validate_email(email)
        except forms.ValidationError:
            raise forms.ValidationError('Zadaj platný e-mail.')
        domain = email.split('@', 1)[-1] if '@' in email else ''
        if '.' not in domain:
            raise forms.ValidationError('Zadaj platný e-mail.')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Tento e-mail je už použitý.')
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Heslá sa nezhodujú.')
        if p1 and len(p1) < 6:
            self.add_error('password1', 'Heslo musí mať aspoň 6 znakov.')
        if not cleaned.get('birth_lat') or not cleaned.get('birth_lon'):
            self.add_error('birth_place', 'Vyber miesto zo zoznamu.')
        if not cleaned.get('birth_time'):
            cleaned['birth_time'] = __import__('datetime').time(12, 0)
        if cleaned.get('gender') not in dict(self.GENDER_CHOICES):
            cleaned['gender'] = 'male'
        return cleaned


class LoginForm(AuthenticationForm):
    """Login formulár s vlastným štýlovaním."""

    username = forms.CharField(
        label='Používateľské meno',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Používateľské meno',
            'autocomplete': 'username',
        }),
    )
    password = forms.CharField(
        label='Heslo',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Heslo',
            'autocomplete': 'current-password',
        }),
    )


class StyledPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label='Aktuálne heslo',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Zadaj aktuálne heslo',
            'autocomplete': 'current-password',
        }),
    )
    new_password1 = forms.CharField(
        label='Nové heslo',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Zadaj nové heslo',
            'autocomplete': 'new-password',
        }),
    )
    new_password2 = forms.CharField(
        label='Potvrdenie nového hesla',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Zopakuj nové heslo',
            'autocomplete': 'new-password',
        }),
    )


class StyledPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        label='E-mail',
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Zadaj registračný e-mail',
            'autocomplete': 'email',
        }),
    )


class StyledSetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label='Nové heslo',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Zadaj nové heslo',
            'autocomplete': 'new-password',
        }),
    )
    new_password2 = forms.CharField(
        label='Potvrdenie nového hesla',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Zopakuj nové heslo',
            'autocomplete': 'new-password',
        }),
    )


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(
        label='E-mail',
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Zadaj registračný e-mail',
            'autocomplete': 'email',
        }),
    )

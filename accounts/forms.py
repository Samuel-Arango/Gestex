from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Usuario


class LoginForm(AuthenticationForm):
    """Inicio de sesión con correo y contraseña."""

    username = forms.EmailField(
        label='Correo electrónico',
        max_length=100,
        widget=forms.EmailInput(attrs={
            'autofocus': True,
            'autocomplete': 'email',
            'placeholder': 'correo@ejemplo.com',
        }),
    )
    password = forms.CharField(
        label='Contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'placeholder': 'Tu contraseña',
        }),
    )

    error_messages = {
        'invalid_login': 'Correo o contraseña incorrectos.',
        'inactive': 'Esta cuenta está desactivada. Contacta al administrador.',
    }

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()


class RegistroForm(forms.Form):
    """Registro de un nuevo usuario (campos de la tabla Usuarios)."""

    nombre = forms.CharField(
        label='Nombre completo',
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Ej. María Pérez',
            'autocomplete': 'name',
        }),
    )
    correo = forms.EmailField(
        label='Correo electrónico',
        max_length=100,
        widget=forms.EmailInput(attrs={
            'placeholder': 'correo@ejemplo.com',
            'autocomplete': 'email',
        }),
    )
    password1 = forms.CharField(
        label='Contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Mínimo 8 caracteres',
            'autocomplete': 'new-password',
        }),
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Repite la contraseña',
            'autocomplete': 'new-password',
        }),
    )

    def clean_nombre(self):
        nombre = ' '.join(self.cleaned_data['nombre'].split())  # Quita espacios sobrantes.
        if len(nombre) < 3:
            raise ValidationError('El nombre debe tener al menos 3 caracteres.')
        return nombre

    def clean_correo(self):
        correo = self.cleaned_data['correo'].strip().lower()
        if Usuario.objects.filter(correo=correo).exists():
            raise ValidationError('No se pudo completar el registro con este correo.')
        return correo

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')

        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Las contraseñas no coinciden.')

        if password1:
            candidato = Usuario(
                nombre=cleaned.get('nombre', ''),
                correo=cleaned.get('correo', ''),
            )
            try:
                validate_password(password1, user=candidato)
            except ValidationError as error:
                self.add_error('password1', error)

        return cleaned

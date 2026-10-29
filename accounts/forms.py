from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import ROL_ADMINISTRADOR, Rol, Usuario


class UsuarioEditarForm(forms.ModelForm):
    """
    Edición de un usuario por el administrador: nombre, rol y estado.
    La contraseña nunca se edita desde aquí.
    """

    class Meta:
        model = Usuario
        fields = ['nombre', 'id_rol', 'estado']
        labels = {'id_rol': 'Rol', 'estado': 'Cuenta activa'}
        help_texts = {
            'id_rol': 'Administrador: acceso total. Operario: registra y consulta el inventario.',
            'estado': 'Si se desactiva, la persona no podrá iniciar sesión.',
        }

    def __init__(self, *args, **kwargs):
        # El administrador que edita; se usa para evitar que se bloquee a sí mismo.
        self.solicitante = kwargs.pop('solicitante')
        super().__init__(*args, **kwargs)
        self.fields['id_rol'].queryset = Rol.objects.order_by('nombre_rol')

    def clean(self):
        cleaned = super().clean()
        # En clean() la instancia aún tiene los valores guardados en la base de datos.
        if self.instance.pk is None:
            return cleaned

        nuevo_rol = cleaned.get('id_rol')
        nuevo_estado = cleaned.get('estado', True)
        sera_admin_activo = bool(
            nuevo_rol and nuevo_rol.nombre_rol == ROL_ADMINISTRADOR and nuevo_estado
        )

        if self.instance.pk == self.solicitante.pk:
            if not nuevo_estado:
                self.add_error('estado', 'No puedes desactivar tu propia cuenta.')
            if nuevo_rol and nuevo_rol.nombre_rol != ROL_ADMINISTRADOR:
                self.add_error('id_rol', 'No puedes quitarte tu propio rol de administrador.')

        era_admin_activo = self.instance.es_administrador and self.instance.estado
        if era_admin_activo and not sera_admin_activo:
            otros_admins = (
                Usuario.objects.filter(id_rol__nombre_rol=ROL_ADMINISTRADOR, estado=True)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if not otros_admins:
                self.add_error(None, 'Debe quedar al menos un administrador activo en el sistema.')

        return cleaned


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

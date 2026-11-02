"""Vistas de cuentas: gestión de usuarios (solo administrador), inicio de sesión y registro."""
import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, UpdateView

from .forms import LoginForm, RegistroForm, UsuarioEditarForm
from .models import Usuario


class SoloAdministradorMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Permite el acceso solo a administradores activos.

    - Sin sesión: redirige al inicio de sesión.
    - Con sesión pero sin rol de administrador: responde 403 (prohibido).
    """

    def test_func(self):
        """Devuelve True solo si la cuenta está activa y tiene rol de administrador."""
        # Se revisa en cada petición, así una cuenta desactivada pierde el acceso al instante.
        usuario = self.request.user
        return usuario.is_active and usuario.es_administrador


class UsuarioListaView(SoloAdministradorMixin, ListView):
    """Lista de usuarios para el administrador."""

    model = Usuario
    template_name = 'accounts/usuarios_lista.html'
    context_object_name = 'usuarios'

    def get_queryset(self):
        # select_related evita una consulta extra por cada usuario para leer su rol.
        return Usuario.objects.select_related('id_rol').order_by('nombre')


class UsuarioEditarView(SoloAdministradorMixin, UpdateView):
    """Cambiar nombre, rol o estado de un usuario."""

    model = Usuario
    form_class = UsuarioEditarForm
    template_name = 'accounts/usuario_form.html'
    success_url = reverse_lazy('accounts:usuarios')

    def get_form_kwargs(self):
        """Pasa al formulario el usuario que edita, para aplicar las reglas de auto-protección."""
        kwargs = super().get_form_kwargs()
        kwargs['solicitante'] = self.request.user
        return kwargs

    def form_valid(self, form):
        """Guarda los cambios y muestra un mensaje de confirmación."""
        messages.success(self.request, f'Datos de {form.instance.nombre} actualizados.')
        return super().form_valid(form)


def _clave_intentos(request, correo):
    """Clave de caché por combinación IP + correo (no guarda el correo en claro)."""
    # El bloqueo es por IP y correo: los fallos desde una IP no bloquean otras IPs.
    ip = request.META.get('REMOTE_ADDR', '')
    origen = f'{ip}|{correo}'.encode('utf-8')
    return 'login_fallidos:' + hashlib.sha256(origen).hexdigest()


class InicioSesionView(LoginView):
    """Inicio de sesión que cuenta los intentos fallidos y bloquea temporalmente al exceder el límite."""

    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        """Revisa el bloqueo antes de validar la contraseña."""
        correo = request.POST.get('username', '').strip().lower()
        clave = _clave_intentos(request, correo)

        # Si ya superó el límite, no se valida la contraseña: se muestra el bloqueo.
        if cache.get(clave, 0) >= settings.LOGIN_MAX_INTENTOS:
            form = self.get_form()
            form.add_error(
                None,
                'Demasiados intentos fallidos. Espera 15 minutos e inténtalo de nuevo.',
            )
            return self.render_to_response(self.get_context_data(form=form))

        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """Inicio correcto: borra el contador de fallos de ese correo."""
        correo = form.cleaned_data['username']
        cache.delete(_clave_intentos(self.request, correo))
        return super().form_valid(form)

    def form_invalid(self, form):
        """Registra un intento fallido y luego muestra el error del formulario."""
        correo = form.data.get('username', '').strip().lower()
        clave = _clave_intentos(self.request, correo)
        # cache.add crea el contador con vencimiento; incr lo aumenta sin reiniciar el plazo.
        cache.add(clave, 0, timeout=settings.LOGIN_BLOQUEO_SEGUNDOS)
        try:
            cache.incr(clave)
        except ValueError:
            # El contador expiró entre add e incr: se crea de nuevo con el primer fallo.
            cache.set(clave, 1, timeout=settings.LOGIN_BLOQUEO_SEGUNDOS)
        return super().form_invalid(form)


def registro(request):
    """Registro público. Los usuarios nuevos quedan con rol Operario."""
    # Quien ya inició sesión no necesita registrarse de nuevo.
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            try:
                # La transacción evita dejar datos a medias si el guardado falla.
                with transaction.atomic():
                    Usuario.objects.create_user(
                        correo=form.cleaned_data['correo'],
                        nombre=form.cleaned_data['nombre'],
                        password=form.cleaned_data['password1'],
                    )
            except IntegrityError:
                # Condición de carrera: el correo se registró entre la validación y el guardado.
                form.add_error('correo', 'No se pudo completar el registro con este correo.')
            else:
                messages.success(request, 'Cuenta creada. Ya puedes iniciar sesión.')
                return redirect('accounts:login')
    else:
        form = RegistroForm()

    return render(request, 'accounts/register.html', {'form': form})

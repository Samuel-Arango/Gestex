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
        kwargs = super().get_form_kwargs()
        kwargs['solicitante'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f'Datos de {form.instance.nombre} actualizados.')
        return super().form_valid(form)


def _clave_intentos(request, correo):
    """Clave de caché por combinación IP + correo (no guarda el correo en claro)."""
    ip = request.META.get('REMOTE_ADDR', '')
    origen = f'{ip}|{correo}'.encode('utf-8')
    return 'login_fallidos:' + hashlib.sha256(origen).hexdigest()


class InicioSesionView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        correo = request.POST.get('username', '').strip().lower()
        clave = _clave_intentos(request, correo)

        if cache.get(clave, 0) >= settings.LOGIN_MAX_INTENTOS:
            form = self.get_form()
            form.add_error(
                None,
                'Demasiados intentos fallidos. Espera 15 minutos e inténtalo de nuevo.',
            )
            return self.render_to_response(self.get_context_data(form=form))

        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        correo = form.cleaned_data['username']
        cache.delete(_clave_intentos(self.request, correo))
        return super().form_valid(form)

    def form_invalid(self, form):
        correo = form.data.get('username', '').strip().lower()
        clave = _clave_intentos(self.request, correo)
        # cache.add crea el contador con vencimiento; incr lo aumenta sin reiniciar el plazo.
        cache.add(clave, 0, timeout=settings.LOGIN_BLOQUEO_SEGUNDOS)
        try:
            cache.incr(clave)
        except ValueError:
            cache.set(clave, 1, timeout=settings.LOGIN_BLOQUEO_SEGUNDOS)
        return super().form_invalid(form)


def registro(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            try:
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

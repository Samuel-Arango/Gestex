import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from .forms import LoginForm, RegistroForm
from .models import Usuario


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

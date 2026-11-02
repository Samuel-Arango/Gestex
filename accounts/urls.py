"""Rutas de la app accounts. Se montan bajo /cuenta/ en config/urls.py."""
from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    # Acceso público: inicio de sesión y registro de nuevos usuarios.
    path('login/', views.InicioSesionView.as_view(), name='login'),
    path('registro/', views.registro, name='register'),
    # Solo acepta POST (Django 5+): evita cierres de sesión forzados por enlaces externos.
    path('logout/', LogoutView.as_view(next_page='accounts:login'), name='logout'),

    # Gestión de usuarios (solo administrador)
    path('usuarios/', views.UsuarioListaView.as_view(), name='usuarios'),
    path('usuarios/<int:pk>/editar/', views.UsuarioEditarView.as_view(), name='usuario_editar'),
]

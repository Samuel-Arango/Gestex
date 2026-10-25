from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView

app_name = 'accounts'

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(
        template_name='accounts/login.html',
        redirect_authenticated_user=True,
    ), name='login'),
    # Solo renderiza la plantilla; la lógica de registro se añadirá después.
    path('registro/', TemplateView.as_view(
        template_name='accounts/register.html',
    ), name='register'),
    path('logout/', auth_views.LogoutView.as_view(
        next_page='accounts:login',
    ), name='logout'),
]

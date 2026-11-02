from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Ruta raíz de la app: muestra el resumen del taller.
    path('', views.dashboard_home, name='home'),
]

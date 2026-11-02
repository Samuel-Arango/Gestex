"""
Rutas de la aplicación de inventario.

Todas las rutas quedan bajo el prefijo que se define en el proyecto principal.
El nombre (name=...) permite usar reverse() o {% url %} en vez de escribir la ruta a mano.
"""
from django.urls import path

from . import views

# Espacio de nombres: en las plantillas se escribe 'inventario:lista', etc.
app_name = 'inventario'

urlpatterns = [
    # Productos. Las rutas con <int:pk> solo aceptan números; por eso no chocan con 'nuevo/'.
    path('', views.ProductoListaView.as_view(), name='lista'),
    path('nuevo/', views.ProductoCrearView.as_view(), name='crear'),
    path('<int:pk>/', views.ProductoDetalleView.as_view(), name='detalle'),
    path('<int:pk>/editar/', views.ProductoEditarView.as_view(), name='editar'),
    path('<int:pk>/estado/', views.producto_cambiar_estado, name='cambiar_estado'),

    # Movimientos de inventario (entradas y salidas). Las existencias solo cambian aquí.
    path('movimientos/entrada/', views.MovimientoEntradaView.as_view(), name='entrada'),
    path('movimientos/salida/', views.MovimientoSalidaView.as_view(), name='salida'),
    path('movimientos/', views.HistorialMovimientosView.as_view(), name='historial'),

    # Producciones. 'terminar/' ingresa las unidades al inventario (ver finalizar_produccion).
    path('producciones/', views.ProduccionListaView.as_view(), name='producciones'),
    path('producciones/nueva/', views.ProduccionCrearView.as_view(), name='produccion_crear'),
    path('producciones/<int:pk>/', views.ProduccionDetalleView.as_view(), name='produccion_detalle'),
    path('producciones/<int:pk>/editar/', views.ProduccionEditarView.as_view(), name='produccion_editar'),
    path('producciones/<int:pk>/consumo/', views.ProduccionConsumoView.as_view(), name='produccion_consumo'),
    path('producciones/<int:pk>/terminar/', views.produccion_terminar, name='produccion_terminar'),

    # Reportes y exportación
    path('reportes/', views.ReportesView.as_view(), name='reportes'),
    path('reportes/exportar/<str:formato>/', views.exportar_reporte, name='exportar_reporte'),
]

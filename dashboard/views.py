from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q
from django.shortcuts import render
from django.utils import timezone

from inventario.models import (
    EstadoProduccion,
    EstadoProducto,
    MovimientoInventario,
    Producto,
    Produccion,
    TipoProducto,
)


@login_required
def dashboard_home(request):
    """
    Resumen del taller. Cada bloque solo se calcula si el usuario tiene permiso
    para verlo, así un rol sin permisos de inventario no recibe esos datos.
    """
    usuario = request.user
    contexto = {'title': 'Dashboard'}

    if usuario.has_perm('inventario.view_producto'):
        activos = Producto.objects.filter(estado=EstadoProducto.ACTIVO)
        resumen = activos.aggregate(
            insumos=Count('id', filter=Q(tipo=TipoProducto.INSUMO)),
            terminados=Count('id', filter=Q(tipo=TipoProducto.PRODUCTO_TERMINADO)),
            en_alerta=Count('id', filter=Q(cantidad_actual__lte=F('stock_minimo'))),
        )
        contexto.update({
            'total_insumos': resumen['insumos'],
            'total_terminados': resumen['terminados'],
            'total_en_alerta': resumen['en_alerta'],
            # Los 5 productos activos con menos existencias en relación a su mínimo.
            'productos_alerta': (
                activos.filter(cantidad_actual__lte=F('stock_minimo'))
                .order_by('cantidad_actual')[:5]
            ),
        })

    if usuario.has_perm('inventario.view_movimientoinventario'):
        hoy = timezone.localdate()
        contexto.update({
            'movimientos_hoy': MovimientoInventario.objects.filter(fecha__date=hoy).count(),
            'ultimos_movimientos': (
                MovimientoInventario.objects.select_related('producto', 'usuario')[:6]
            ),
        })

    if usuario.has_perm('inventario.view_produccion'):
        contexto.update({
            'producciones_activas': (
                Produccion.objects.filter(estado__in=[
                    EstadoProduccion.PENDIENTE, EstadoProduccion.EN_PROCESO,
                ])
                .annotate(total_materiales=Count('detalles'))
                .order_by('fecha_entrega')[:5]
            ),
            'total_producciones_activas': Produccion.objects.filter(estado__in=[
                EstadoProduccion.PENDIENTE, EstadoProduccion.EN_PROCESO,
            ]).count(),
        })

    return render(request, 'dashboard/home.html', contexto)

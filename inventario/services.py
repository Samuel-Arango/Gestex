"""
Servicios de inventario: aquí se cambian las existencias.

Regla principal: las existencias solo cambian a través de registrar_movimiento().
Las vistas y los formularios no suman ni restan directamente.

Cada movimiento se guarda en una sola transacción (transaction.atomic):
si algo falla, no queda ni el cambio de existencias ni el movimiento a medias.

Protección contra existencias negativas, en tres capas:
1. El formulario avisa antes de enviar (mejor experiencia).
2. Este servicio vuelve a comprobar el stock con los datos actuales.
3. La actualización es condicional (solo resta si hay suficiente) y la
   base de datos tiene una restricción CHECK (cantidad_actual >= 0).
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F

from .models import (
    DetalleMaterial,
    EstadoProducto,
    MovimientoInventario,
    Producto,
    TipoMovimiento,
)

CANTIDAD_MINIMA = Decimal('0.01')
CANTIDAD_MAXIMA = Decimal('99999999.99')  # Cabe en DecimalField(max_digits=10, decimal_places=2)


class ErrorMovimiento(Exception):
    """Error de negocio al registrar un movimiento. El mensaje es apto para el usuario."""


class StockInsuficiente(ErrorMovimiento):
    """Se intentó sacar más de lo disponible."""


class ProductoNoDisponible(ErrorMovimiento):
    """El producto está inactivo y no admite movimientos."""


def _validar_cantidad(cantidad):
    try:
        cantidad = Decimal(str(cantidad))
    except (InvalidOperation, TypeError, ValueError):
        raise ErrorMovimiento('La cantidad debe ser un número válido.')

    if not cantidad.is_finite():
        raise ErrorMovimiento('La cantidad debe ser un número válido.')
    if cantidad < CANTIDAD_MINIMA:
        raise ErrorMovimiento('La cantidad debe ser mayor que cero.')
    if cantidad > CANTIDAD_MAXIMA:
        raise ErrorMovimiento('La cantidad es demasiado grande.')
    if cantidad.as_tuple().exponent < -2:
        raise ErrorMovimiento('La cantidad admite como máximo 2 decimales.')
    return cantidad


def _registrar_consumo_en_produccion(produccion, producto, cantidad):
    """Suma la cantidad consumida al material de la producción (si el insumo está en su lista)."""
    detalle = (
        DetalleMaterial.objects.select_for_update()
        .filter(produccion=produccion, producto=producto)
        .first()
    )
    if detalle is not None:
        DetalleMaterial.objects.filter(pk=detalle.pk).update(
            cantidad_utilizada=F('cantidad_utilizada') + cantidad,
        )


def registrar_movimiento(*, producto, usuario, tipo, cantidad, motivo, produccion=None):
    """
    Registra una entrada o una salida y actualiza las existencias de forma segura.

    Args:
        producto: instancia de Producto (insumo o producto terminado).
        usuario: quien registra el movimiento.
        tipo: TipoMovimiento.ENTRADA o TipoMovimiento.SALIDA.
        cantidad: cantidad positiva (se acepta texto, int o Decimal).
        motivo: texto obligatorio que explica el movimiento.
        produccion: Produccion relacionada (opcional).

    Returns:
        El MovimientoInventario creado.

    Raises:
        ErrorMovimiento (o una subclase) si el movimiento no se puede registrar.
        En ese caso no cambia nada en la base de datos.
    """
    if tipo not in TipoMovimiento.values:
        raise ErrorMovimiento('El tipo de movimiento no es válido.')

    cantidad = _validar_cantidad(cantidad)

    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorMovimiento('Indica el motivo del movimiento.')

    with transaction.atomic():
        # Bloquea la fila del producto hasta terminar la transacción.
        # Tiene efecto en MySQL y PostgreSQL; en SQLite se ignora y lo protege la base.
        bloqueado = Producto.objects.select_for_update().get(pk=producto.pk)

        if bloqueado.estado != EstadoProducto.ACTIVO:
            raise ProductoNoDisponible(
                f'"{bloqueado.nombre}" está inactivo. Actívalo para registrar movimientos.'
            )

        if tipo == TipoMovimiento.SALIDA:
            # Solo resta si hay stock suficiente; la comprobación y el cambio son una sola operación.
            filas = Producto.objects.filter(
                pk=bloqueado.pk,
                cantidad_actual__gte=cantidad,
            ).update(cantidad_actual=F('cantidad_actual') - cantidad)

            if filas == 0:
                bloqueado.refresh_from_db(fields=['cantidad_actual'])
                raise StockInsuficiente(
                    f'No hay suficiente "{bloqueado.nombre}". Disponible: '
                    f'{bloqueado.cantidad_actual} {bloqueado.unidad_medida}; '
                    f'solicitado: {cantidad} {bloqueado.unidad_medida}.'
                )
        else:
            Producto.objects.filter(pk=bloqueado.pk).update(
                cantidad_actual=F('cantidad_actual') + cantidad,
            )

        movimiento = MovimientoInventario.objects.create(
            producto=bloqueado,
            usuario=usuario,
            tipo_movimiento=tipo,
            cantidad=cantidad,
            motivo=motivo,
            produccion=produccion,
        )

        # Una salida ligada a una producción cuenta como material utilizado.
        if produccion is not None and tipo == TipoMovimiento.SALIDA:
            _registrar_consumo_en_produccion(produccion, bloqueado, cantidad)

    # Devuelve al llamador el producto con las existencias actualizadas.
    producto.refresh_from_db(fields=['cantidad_actual'])
    return movimiento

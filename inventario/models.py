"""
Modelos del inventario del taller de confección.

Tablas:
- Producto:            insumos (telas, hilos, botones...) y productos terminados.
- Produccion:          una orden de confección (por ejemplo, 50 camisas).
- DetalleMaterial:     qué insumos y cuánto necesita cada producción.
- MovimientoInventario: historial de entradas y salidas (no se edita ni se borra).

Nota: la lógica para cambiar existencias (entradas y salidas) vive en
inventario/services.py (Fase 4). Aquí solo se definen los datos y sus reglas básicas.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


# ---------------------------------------------------------------------------
# Opciones fijas (choices). Usar TextChoices evita escribir textos a mano.
# ---------------------------------------------------------------------------
class TipoProducto(models.TextChoices):
    INSUMO = 'insumo', 'Insumo'
    PRODUCTO_TERMINADO = 'producto_terminado', 'Producto terminado'


class EstadoProducto(models.TextChoices):
    ACTIVO = 'activo', 'Activo'
    INACTIVO = 'inactivo', 'Inactivo'


class EstadoProduccion(models.TextChoices):
    # Los valores coinciden con el texto que ya guardaba la columna, así no hay que migrar datos.
    PENDIENTE = 'Pendiente', 'Pendiente'
    EN_PROCESO = 'En proceso', 'En proceso'
    TERMINADA = 'Terminada', 'Terminada'
    CANCELADA = 'Cancelada', 'Cancelada'


class TipoMovimiento(models.TextChoices):
    ENTRADA = 'entrada', 'Entrada'
    SALIDA = 'salida', 'Salida'


class MovimientoInmutableError(Exception):
    """Se lanza al intentar editar o borrar un movimiento ya registrado."""


# ---------------------------------------------------------------------------
# Producto
# ---------------------------------------------------------------------------
class Producto(models.Model):
    """Insumo de confección o producto terminado."""

    nombre = models.CharField('nombre', max_length=100, db_index=True)
    descripcion = models.TextField('descripción', blank=True)
    tipo = models.CharField('tipo', max_length=20, choices=TipoProducto.choices)
    unidad_medida = models.CharField(
        'unidad de medida',
        max_length=20,
        help_text='Por ejemplo: metros, unidades, conos, rollos o kilos.',
    )
    # Solo cambia mediante movimientos (RF05). Por eso no es editable en formularios.
    cantidad_actual = models.DecimalField(
        'cantidad actual',
        max_digits=10,
        decimal_places=2,
        default=0,
        editable=False,
    )
    stock_minimo = models.DecimalField(
        'stock mínimo',
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Cuando la cantidad actual llegue a este valor se mostrará una alerta.',
    )
    estado = models.CharField(
        'estado',
        max_length=10,
        choices=EstadoProducto.choices,
        default=EstadoProducto.ACTIVO,
    )

    class Meta:
        verbose_name = 'producto'
        verbose_name_plural = 'productos'
        ordering = ['nombre']
        constraints = [
            models.CheckConstraint(
                condition=Q(cantidad_actual__gte=0),
                name='producto_cantidad_no_negativa',
            ),
            models.CheckConstraint(
                condition=Q(stock_minimo__gte=0),
                name='producto_stock_minimo_no_negativo',
            ),
        ]

    def __str__(self):
        return f'{self.nombre} ({self.unidad_medida})'

    @property
    def en_alerta(self):
        """True cuando hay que reponer (cantidad actual <= stock mínimo)."""
        return self.cantidad_actual <= self.stock_minimo


# ---------------------------------------------------------------------------
# Producción
# ---------------------------------------------------------------------------
class Produccion(models.Model):
    """Orden de confección que consume insumos."""

    descripcion = models.TextField('descripción')
    tipo = models.CharField('tipo de producción', max_length=50)
    cantidad_solicitada = models.PositiveIntegerField(
        'cantidad solicitada',
        validators=[MinValueValidator(1)],
        help_text='Número de prendas o piezas a producir.',
    )
    fecha_inicio = models.DateField('fecha de inicio')
    fecha_entrega = models.DateField('fecha de entrega')
    estado = models.CharField(
        'estado',
        max_length=100,
        choices=EstadoProduccion.choices,
        default=EstadoProduccion.PENDIENTE,
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='producciones',
        verbose_name='responsable',
    )

    class Meta:
        verbose_name = 'producción'
        verbose_name_plural = 'producciones'
        ordering = ['-fecha_inicio']
        constraints = [
            models.CheckConstraint(
                condition=Q(cantidad_solicitada__gt=0),
                name='produccion_cantidad_positiva',
            ),
            models.CheckConstraint(
                condition=Q(fecha_entrega__gte=F('fecha_inicio')),
                name='produccion_entrega_despues_de_inicio',
            ),
        ]

    def __str__(self):
        return f'{self.tipo}: {self.descripcion[:40]}'

    def clean(self):
        super().clean()
        if self.fecha_inicio and self.fecha_entrega and self.fecha_entrega < self.fecha_inicio:
            raise ValidationError({
                'fecha_entrega': 'La fecha de entrega no puede ser anterior a la fecha de inicio.',
            })


class DetalleMaterial(models.Model):
    """Cuánto de cada insumo necesita una producción."""

    produccion = models.ForeignKey(
        Produccion,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name='producción',
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,  # Un insumo usado en producciones no se puede borrar.
        related_name='usos_en_produccion',
        verbose_name='insumo',
        limit_choices_to={'tipo': TipoProducto.INSUMO},
    )
    cantidad_requerida = models.DecimalField(
        'cantidad requerida',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    cantidad_utilizada = models.DecimalField(
        'cantidad utilizada',
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
    )

    class Meta:
        verbose_name = 'material de producción'
        verbose_name_plural = 'materiales de producción'
        constraints = [
            # Un mismo insumo aparece una sola vez por producción.
            models.UniqueConstraint(
                fields=['produccion', 'producto'],
                name='detalle_material_unico_por_produccion',
            ),
            models.CheckConstraint(
                condition=Q(cantidad_requerida__gt=0),
                name='detalle_requerida_positiva',
            ),
            models.CheckConstraint(
                condition=Q(cantidad_utilizada__gte=0),
                name='detalle_utilizada_no_negativa',
            ),
        ]

    def __str__(self):
        return f'{self.producto.nombre} para producción #{self.produccion_id}'

    def clean(self):
        super().clean()
        if self.producto_id and self.producto.tipo != TipoProducto.INSUMO:
            raise ValidationError({'producto': 'Solo se pueden asignar insumos a una producción.'})


# ---------------------------------------------------------------------------
# Movimientos (historial inmutable)
# ---------------------------------------------------------------------------
class MovimientoInventario(models.Model):
    """Entrada o salida de un producto. Es un registro histórico: no se edita ni se borra."""

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name='movimientos',
        verbose_name='producto',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='movimientos',
        verbose_name='usuario',
    )
    tipo_movimiento = models.CharField(
        'tipo de movimiento',
        max_length=10,
        choices=TipoMovimiento.choices,
    )
    cantidad = models.DecimalField(
        'cantidad',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    fecha = models.DateTimeField('fecha', auto_now_add=True, db_index=True)
    motivo = models.CharField('motivo', max_length=255)
    produccion = models.ForeignKey(
        Produccion,
        on_delete=models.PROTECT,
        related_name='movimientos',
        verbose_name='producción relacionada',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'movimiento de inventario'
        verbose_name_plural = 'movimientos de inventario'
        ordering = ['-fecha', '-id']
        constraints = [
            models.CheckConstraint(
                condition=Q(cantidad__gt=0),
                name='movimiento_cantidad_positiva',
            ),
        ]

    def __str__(self):
        return f'{self.get_tipo_movimiento_display()} de {self.cantidad} - {self.producto.nombre}'

    def save(self, *args, **kwargs):
        # Solo se permite crear registros nuevos.
        if not self._state.adding:
            raise MovimientoInmutableError(
                'Los movimientos no se editan. Registra un movimiento nuevo para corregir.'
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise MovimientoInmutableError('Los movimientos no se eliminan del historial.')

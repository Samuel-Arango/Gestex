"""
Carga datos de ejemplo para probar el inventario.

Uso:
    python manage.py cargar_datos_prueba

Crea insumos, productos terminados y una producción de ejemplo.
Puede ejecutarse varias veces sin duplicar datos.

Las existencias empiezan en 0. Las cantidades se registran con movimientos
de entrada (Fase 4), para que siempre pasen por las mismas reglas de negocio.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import ROL_ADMINISTRADOR, Usuario
from inventario.models import DetalleMaterial, Producto, Produccion, TipoProducto

# (nombre, unidad de medida, stock mínimo)
INSUMOS = [
    ('Tela algodón blanca', 'metros', Decimal('20')),
    ('Tela jean azul', 'metros', Decimal('15')),
    ('Hilo poliéster blanco', 'conos', Decimal('5')),
    ('Botones nácar 15 mm', 'unidades', Decimal('100')),
    ('Cierre metálico 20 cm', 'unidades', Decimal('20')),
]

# (nombre, unidad de medida, stock mínimo)
PRODUCTOS_TERMINADOS = [
    ('Camisa básica blanca', 'unidades', Decimal('5')),
    ('Pantalón jean clásico', 'unidades', Decimal('5')),
]

DESCRIPCION_PRODUCCION = 'Pedido de prueba: 20 camisas básicas'


class Command(BaseCommand):
    help = 'Carga insumos, productos terminados y una producción de ejemplo.'

    def handle(self, *args, **options):
        # El responsable de las producciones de prueba es un administrador activo.
        responsable = (
            Usuario.objects.filter(id_rol__nombre_rol=ROL_ADMINISTRADOR, estado=True)
            .order_by('id_usuario')
            .first()
        )
        if responsable is None:
            raise CommandError(
                'No hay un administrador activo. Crea uno con: python manage.py createsuperuser'
            )

        with transaction.atomic():
            insumos = self._crear_productos(INSUMOS, TipoProducto.INSUMO)
            self._crear_productos(PRODUCTOS_TERMINADOS, TipoProducto.PRODUCTO_TERMINADO)
            self._crear_produccion_de_ejemplo(responsable, insumos)

        self.stdout.write(self.style.SUCCESS('Datos de prueba cargados correctamente.'))
        self.stdout.write('Las existencias están en 0; regístralas con entradas en la Fase 4.')

    def _crear_productos(self, definiciones, tipo):
        creados = {}
        for nombre, unidad, stock_minimo in definiciones:
            producto, creado = Producto.objects.get_or_create(
                nombre=nombre,
                defaults={
                    'tipo': tipo,
                    'unidad_medida': unidad,
                    'stock_minimo': stock_minimo,
                    'descripcion': 'Dato de prueba.',
                },
            )
            creados[nombre] = producto
            estado = 'creado' if creado else 'ya existía'
            self.stdout.write(f'  - {producto} {estado}')
        return creados

    def _crear_produccion_de_ejemplo(self, responsable, insumos):
        hoy = timezone.localdate()
        produccion, creada = Produccion.objects.get_or_create(
            descripcion=DESCRIPCION_PRODUCCION,
            defaults={
                'tipo': 'Confección',
                'cantidad_solicitada': 20,
                'fecha_inicio': hoy,
                'fecha_entrega': hoy + timedelta(days=7),
                'estado': 'Pendiente',
                'usuario': responsable,
            },
        )
        if not creada:
            return

        materiales = [
            (insumos['Tela algodón blanca'], Decimal('40')),
            (insumos['Botones nácar 15 mm'], Decimal('20')),
        ]
        for producto, cantidad in materiales:
            DetalleMaterial.objects.create(
                produccion=produccion,
                producto=producto,
                cantidad_requerida=cantidad,
            )
        self.stdout.write(f'  - Producción de ejemplo creada (#{produccion.pk})')

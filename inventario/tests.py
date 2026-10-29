from datetime import date, timedelta
from io import StringIO
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario

from .models import (
    DetalleMaterial,
    MovimientoInmutableError,
    MovimientoInventario,
    Producto,
    Produccion,
    TipoMovimiento,
    TipoProducto,
)


def crear_usuario(correo='operario@taller.co'):
    return Usuario.objects.create_user(correo, 'Operario de prueba', 'Clave-Segura-2026')


def crear_producto(nombre='Tela algodÃ³n', tipo=TipoProducto.INSUMO, **extra):
    return Producto.objects.create(
        nombre=nombre,
        tipo=tipo,
        unidad_medida='metros',
        stock_minimo=Decimal('10'),
        **extra,
    )


class ProductoTests(TestCase):

    def test_cantidad_inicial_es_cero(self):
        producto = crear_producto()
        self.assertEqual(producto.cantidad_actual, Decimal('0'))

    def test_base_de_datos_rechaza_existencias_negativas(self):
        producto = crear_producto()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Producto.objects.filter(pk=producto.pk).update(cantidad_actual=Decimal('-1'))

    def test_alerta_cuando_llega_al_stock_minimo(self):
        producto = crear_producto()
        producto.cantidad_actual = Decimal('10')  # igual al mÃ­nimo
        self.assertTrue(producto.en_alerta)
        producto.cantidad_actual = Decimal('10.01')
        self.assertFalse(producto.en_alerta)

    def test_stock_minimo_no_puede_ser_negativo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Producto.objects.create(
                nombre='Hilo', tipo=TipoProducto.INSUMO, unidad_medida='conos',
                stock_minimo=Decimal('-5'),
            )


class ProduccionTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario()

    def _produccion(self, **extra):
        datos = {
            'descripcion': 'Camisas',
            'tipo': 'ConfecciÃ³n',
            'cantidad_solicitada': 10,
            'fecha_inicio': date(2026, 1, 10),
            'fecha_entrega': date(2026, 1, 20),
            'usuario': self.usuario,
        }
        datos.update(extra)
        return Produccion.objects.create(**datos)

    def test_fecha_de_entrega_no_puede_ser_anterior_al_inicio(self):
        produccion = Produccion(
            descripcion='Camisas', tipo='ConfecciÃ³n', cantidad_solicitada=5,
            fecha_inicio=date(2026, 2, 10), fecha_entrega=date(2026, 2, 1),
            usuario=self.usuario,
        )
        with self.assertRaises(ValidationError):
            produccion.full_clean()

    def test_base_de_datos_rechaza_entrega_anterior_al_inicio(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._produccion(fecha_inicio=date(2026, 2, 10), fecha_entrega=date(2026, 2, 1))

    def test_cantidad_solicitada_debe_ser_positiva(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._produccion(cantidad_solicitada=0)


class DetalleMaterialTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario()
        self.produccion = Produccion.objects.create(
            descripcion='Camisas', tipo='ConfecciÃ³n', cantidad_solicitada=10,
            fecha_inicio=date(2026, 1, 10), fecha_entrega=date(2026, 1, 20),
            usuario=self.usuario,
        )

    def test_solo_se_pueden_asignar_insumos(self):
        terminado = crear_producto('Camisa', tipo=TipoProducto.PRODUCTO_TERMINADO)
        detalle = DetalleMaterial(
            produccion=self.produccion, producto=terminado, cantidad_requerida=Decimal('2'),
        )
        with self.assertRaises(ValidationError):
            detalle.full_clean()

    def test_un_insumo_no_se_repite_en_la_misma_produccion(self):
        insumo = crear_producto()
        DetalleMaterial.objects.create(
            produccion=self.produccion, producto=insumo, cantidad_requerida=Decimal('2'),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DetalleMaterial.objects.create(
                produccion=self.produccion, producto=insumo, cantidad_requerida=Decimal('3'),
            )

    def test_cantidad_requerida_debe_ser_positiva(self):
        insumo = crear_producto()
        with self.assertRaises(IntegrityError), transaction.atomic():
            DetalleMaterial.objects.create(
                produccion=self.produccion, producto=insumo, cantidad_requerida=Decimal('0'),
            )


class MovimientoInventarioTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario()
        self.producto = crear_producto()

    def _movimiento(self, **extra):
        datos = {
            'producto': self.producto,
            'usuario': self.usuario,
            'tipo_movimiento': TipoMovimiento.ENTRADA,
            'cantidad': Decimal('5'),
            'motivo': 'Compra a proveedor',
        }
        datos.update(extra)
        return MovimientoInventario.objects.create(**datos)

    def test_se_puede_registrar_un_movimiento_nuevo(self):
        movimiento = self._movimiento()
        self.assertIsNotNone(movimiento.pk)
        self.assertIsNotNone(movimiento.fecha)

    def test_cantidad_cero_o_negativa_no_se_guarda(self):
        for cantidad in (Decimal('0'), Decimal('-3')):
            with self.assertRaises(IntegrityError), transaction.atomic():
                self._movimiento(cantidad=cantidad)

    def test_no_se_puede_editar_un_movimiento(self):
        movimiento = self._movimiento()
        movimiento.motivo = 'Cambio malicioso'
        with self.assertRaises(MovimientoInmutableError):
            movimiento.save()

    def test_no_se_puede_borrar_un_movimiento(self):
        movimiento = self._movimiento()
        with self.assertRaises(MovimientoInmutableError):
            movimiento.delete()
        self.assertTrue(MovimientoInventario.objects.filter(pk=movimiento.pk).exists())

    def test_movimiento_puede_estar_ligado_a_una_produccion(self):
        produccion = Produccion.objects.create(
            descripcion='Camisas', tipo='ConfecciÃ³n', cantidad_solicitada=10,
            fecha_inicio=date(2026, 1, 10), fecha_entrega=date(2026, 1, 20),
            usuario=self.usuario,
        )
        movimiento = self._movimiento(
            tipo_movimiento=TipoMovimiento.SALIDA, produccion=produccion,
            motivo='Consumo en corte',
        )
        self.assertEqual(movimiento.produccion, produccion)

    def test_no_se_puede_borrar_un_producto_con_movimientos(self):
        from django.db.models import ProtectedError
        self._movimiento()
        with self.assertRaises(ProtectedError):
            self.producto.delete()


class CargarDatosPruebaTests(TestCase):

    def test_requiere_un_administrador(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('cargar_datos_prueba', stdout=StringIO())

    def test_carga_datos_y_no_duplica_al_repetir(self):
        from django.core.management import call_command
        Usuario.objects.create_superuser('admin@taller.co', 'Admin', 'Clave-Segura-2026')

        call_command('cargar_datos_prueba', stdout=StringIO())
        call_command('cargar_datos_prueba', stdout=StringIO())

        self.assertEqual(Producto.objects.filter(tipo=TipoProducto.INSUMO).count(), 5)
        self.assertEqual(Producto.objects.filter(tipo=TipoProducto.PRODUCTO_TERMINADO).count(), 2)
        self.assertEqual(Produccion.objects.count(), 1)
        self.assertEqual(DetalleMaterial.objects.count(), 2)
        # Las existencias empiezan en cero; el comando no crea movimientos.
        self.assertFalse(Producto.objects.exclude(cantidad_actual=0).exists())
        self.assertFalse(MovimientoInventario.objects.exists())


class AdminInventarioTests(TestCase):
    """Comprueba que las pÃ¡ginas del admin cargan y que el historial es de solo lectura."""

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin@taller.co', 'Admin', 'Clave-Segura-2026')
        self.client.force_login(self.admin)
        self.producto = crear_producto()

    def test_listados_del_admin_cargan(self):
        for nombre in ('inventario_producto', 'inventario_produccion', 'inventario_movimientoinventario'):
            with self.subTest(modelo=nombre):
                r = self.client.get(reverse(f'admin:{nombre}_changelist'))
                self.assertEqual(r.status_code, 200)

    def test_no_se_pueden_crear_movimientos_desde_el_admin(self):
        r = self.client.get(reverse('admin:inventario_movimientoinventario_add'))
        self.assertEqual(r.status_code, 403)

    def test_no_se_pueden_borrar_productos_desde_el_admin(self):
        r = self.client.get(reverse('admin:inventario_producto_delete', args=[self.producto.pk]))
        self.assertEqual(r.status_code, 403)


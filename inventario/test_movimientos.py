"""Pruebas de entradas y salidas (Fase 4): reglas de negocio, transacciones y vistas."""
from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from accounts.models import ROL_ADMINISTRADOR, ROL_OPERARIO, Rol, Usuario

from .forms import MovimientoForm
from .models import (
    DetalleMaterial,
    MovimientoInventario,
    Producto,
    Produccion,
    TipoMovimiento,
    TipoProducto,
)
from .services import (
    ErrorMovimiento,
    ProductoNoDisponible,
    StockInsuficiente,
    registrar_movimiento,
)

PASSWORD = 'Clave-Segura-2026'


def crear_usuario(correo, nombre, nombre_rol):
    return Usuario.objects.create_user(
        correo, nombre, PASSWORD, id_rol=Rol.objects.get(nombre_rol=nombre_rol),
    )


def crear_producto(nombre='Tela algodón', existencias='0', estado='activo'):
    producto = Producto.objects.create(
        nombre=nombre, tipo=TipoProducto.INSUMO, unidad_medida='metros',
        stock_minimo=Decimal('5'), estado=estado,
    )
    if existencias != '0':
        Producto.objects.filter(pk=producto.pk).update(cantidad_actual=Decimal(existencias))
        producto.refresh_from_db()
    return producto


def recargar(producto):
    producto.refresh_from_db()
    return producto


class BaseMovimientoTests(TestCase):

    def setUp(self):
        self.operario = crear_usuario('operario@taller.co', 'Operario', ROL_OPERARIO)
        self.producto = crear_producto(existencias='10')

    def entrada(self, cantidad, **extra):
        return registrar_movimiento(
            producto=self.producto, usuario=self.operario, tipo=TipoMovimiento.ENTRADA,
            cantidad=cantidad, motivo=extra.pop('motivo', 'Compra'), **extra,
        )

    def salida(self, cantidad, producto=None, **extra):
        return registrar_movimiento(
            producto=producto or self.producto, usuario=self.operario,
            tipo=TipoMovimiento.SALIDA, cantidad=cantidad,
            motivo=extra.pop('motivo', 'Consumo'), **extra,
        )


class ReglasDeExistenciasTests(BaseMovimientoTests):

    def test_entrada_suma_a_las_existencias(self):
        movimiento = self.entrada(Decimal('5'))
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('15'))
        self.assertEqual(movimiento.tipo_movimiento, TipoMovimiento.ENTRADA)
        self.assertEqual(movimiento.usuario, self.operario)

    def test_salida_resta_de_las_existencias(self):
        self.salida(Decimal('4'))
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('6'))

    def test_salida_puede_dejar_el_stock_en_cero(self):
        self.salida(Decimal('10'))
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('0'))

    def test_salida_mayor_que_el_stock_se_rechaza_con_mensaje_claro(self):
        with self.assertRaises(StockInsuficiente) as contexto:
            self.salida(Decimal('10.01'))
        self.assertIn('Disponible: 10.00 metros', str(contexto.exception))
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('10'))

    def test_salida_rechazada_no_crea_movimiento(self):
        antes = MovimientoInventario.objects.count()
        with self.assertRaises(StockInsuficiente):
            self.salida(Decimal('50'))
        self.assertEqual(MovimientoInventario.objects.count(), antes)

    def test_producto_sin_existencias_no_admite_salidas(self):
        vacio = crear_producto('Hilo', existencias='0')
        with self.assertRaises(StockInsuficiente):
            self.salida(Decimal('0.01'), producto=vacio)
        self.assertEqual(recargar(vacio).cantidad_actual, Decimal('0'))

    def test_producto_inactivo_no_admite_movimientos(self):
        inactivo = crear_producto('Hilo viejo', existencias='5', estado='inactivo')
        with self.assertRaises(ProductoNoDisponible):
            registrar_movimiento(
                producto=inactivo, usuario=self.operario, tipo=TipoMovimiento.ENTRADA,
                cantidad=Decimal('1'), motivo='Compra',
            )
        self.assertEqual(recargar(inactivo).cantidad_actual, Decimal('5'))


class ValidacionesDelServicioTests(BaseMovimientoTests):

    def test_cantidades_invalidas_no_cambian_nada(self):
        casos = [
            Decimal('0'), Decimal('-3'), 'abc', None, Decimal('NaN'), Decimal('Infinity'),
            Decimal('1.001'), Decimal('999999999'),
        ]
        for cantidad in casos:
            with self.subTest(cantidad=cantidad):
                with self.assertRaises(ErrorMovimiento):
                    self.entrada(cantidad)
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('10'))
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_cantidad_acepta_texto_con_decimales(self):
        self.entrada('2.5')
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('12.5'))

    def test_motivo_es_obligatorio(self):
        with self.assertRaises(ErrorMovimiento):
            registrar_movimiento(
                producto=self.producto, usuario=self.operario, tipo=TipoMovimiento.ENTRADA,
                cantidad=Decimal('1'), motivo='   ',
            )

    def test_tipo_invalido_se_rechaza(self):
        with self.assertRaises(ErrorMovimiento):
            registrar_movimiento(
                producto=self.producto, usuario=self.operario, tipo='ajuste',
                cantidad=Decimal('1'), motivo='x',
            )


class AtomicidadTests(BaseMovimientoTests):

    def test_si_falla_el_historial_no_cambian_las_existencias(self):
        # Si la línea de historial falla, la actualización de existencias debe revertirse.
        with mock.patch('inventario.services.MovimientoInventario') as modelo:
            modelo.objects.create.side_effect = RuntimeError('fallo simulado')
            with self.assertRaises(RuntimeError):
                self.salida(Decimal('3'))
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('10'))

    def test_movimiento_y_existencias_se_guardan_juntos(self):
        self.salida(Decimal('3'))
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('7'))
        self.assertEqual(MovimientoInventario.objects.filter(producto=self.producto).count(), 1)


class StockObsoletoTests(BaseMovimientoTests):

    def test_el_servicio_no_confia_en_el_stock_que_ve_el_formulario(self):
        # El formulario lee 10. Mientras el usuario escribe, otra salida deja 2.
        obsoleto = recargar(self.producto)
        self.salida(Decimal('8'))  # quedan 2

        with self.assertRaises(StockInsuficiente):
            registrar_movimiento(
                producto=obsoleto, usuario=self.operario, tipo=TipoMovimiento.SALIDA,
                cantidad=Decimal('5'), motivo='Consumo tardío',
            )
        stock = recargar(self.producto).cantidad_actual
        self.assertEqual(stock, Decimal('2'))
        self.assertGreaterEqual(stock, 0)

    def test_varias_salidas_consecutivas_nunca_dejan_negativo(self):
        cumplidas = 0
        for _ in range(15):
            try:
                self.salida(Decimal('1'))
                cumplidas += 1
            except StockInsuficiente:
                pass
        self.assertEqual(cumplidas, 10)
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('0'))


class LigaConProduccionTests(BaseMovimientoTests):

    def setUp(self):
        super().setUp()
        self.produccion = Produccion.objects.create(
            descripcion='Camisas', tipo='Confección', cantidad_solicitada=20,
            fecha_inicio=date(2026, 1, 1), fecha_entrega=date(2026, 1, 10),
            usuario=self.operario,
        )
        self.detalle = DetalleMaterial.objects.create(
            produccion=self.produccion, producto=self.producto,
            cantidad_requerida=Decimal('40'),
        )

    def test_movimiento_queda_ligado_a_la_produccion(self):
        movimiento = self.salida(Decimal('6'), produccion=self.produccion)
        self.assertEqual(movimiento.produccion, self.produccion)

    def test_salida_ligada_suma_al_material_utilizado(self):
        self.salida(Decimal('6'), produccion=self.produccion)
        self.salida(Decimal('4'), produccion=self.produccion)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad_utilizada, Decimal('10'))

    def test_entrada_ligada_no_cuenta_como_consumo(self):
        self.entrada(Decimal('5'), produccion=self.produccion)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad_utilizada, Decimal('0'))

    def test_salida_de_insumo_que_no_esta_en_la_produccion_solo_se_liga(self):
        otro = crear_producto('Botón', existencias='5')
        movimiento = self.salida(Decimal('2'), producto=otro, produccion=self.produccion)
        self.assertEqual(movimiento.produccion, self.produccion)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad_utilizada, Decimal('0'))


class FormularioMovimientoTests(BaseMovimientoTests):

    def datos(self, **cambios):
        datos = {'producto': self.producto.pk, 'cantidad': '3', 'motivo': 'Consumo', 'produccion': ''}
        datos.update(cambios)
        return datos

    def test_solo_muestra_productos_activos(self):
        inactivo = crear_producto('Hilo viejo', existencias='5', estado='inactivo')
        form = MovimientoForm(tipo=TipoMovimiento.SALIDA)
        pks = list(form.fields['producto'].queryset.values_list('pk', flat=True))
        self.assertIn(self.producto.pk, pks)
        self.assertNotIn(inactivo.pk, pks)

    def test_salida_mayor_que_stock_da_error_en_el_campo(self):
        form = MovimientoForm(self.datos(cantidad='11'), tipo=TipoMovimiento.SALIDA)
        self.assertFalse(form.is_valid())
        self.assertIn('cantidad', form.errors)

    def test_entrada_no_se_limita_por_el_stock(self):
        form = MovimientoForm(self.datos(cantidad='500'), tipo=TipoMovimiento.ENTRADA)
        self.assertTrue(form.is_valid(), form.errors)

    def test_cantidad_cero_o_negativa_no_es_valida(self):
        for cantidad in ('0', '-1'):
            with self.subTest(cantidad=cantidad):
                form = MovimientoForm(self.datos(cantidad=cantidad), tipo=TipoMovimiento.ENTRADA)
                self.assertFalse(form.is_valid())

    def test_motivo_es_obligatorio(self):
        form = MovimientoForm(self.datos(motivo=''), tipo=TipoMovimiento.ENTRADA)
        self.assertFalse(form.is_valid())
        self.assertIn('motivo', form.errors)

    def test_opcion_muestra_el_stock_disponible(self):
        form = MovimientoForm(tipo=TipoMovimiento.SALIDA)
        etiqueta = form.fields['producto'].label_from_instance(self.producto)
        self.assertIn('disponible: 10.00 metros', etiqueta)


class VistasMovimientoTests(BaseMovimientoTests):

    def setUp(self):
        super().setUp()
        self.client.force_login(self.operario)
        self.url_salida = reverse('inventario:salida')
        self.url_entrada = reverse('inventario:entrada')

    def datos(self, **cambios):
        datos = {'producto': self.producto.pk, 'cantidad': '3', 'motivo': 'Consumo', 'produccion': ''}
        datos.update(cambios)
        return datos

    def test_visitante_anonimo_es_redirigido(self):
        self.client.logout()
        r = self.client.get(self.url_entrada)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('accounts:login'), r['Location'])

    def test_formulario_se_abre_con_el_producto_preseleccionado(self):
        r = self.client.get(self.url_salida, {'producto': self.producto.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['form'].initial['producto'], self.producto.pk)

    def test_entrada_por_post_registra_y_redirige_a_la_ficha(self):
        r = self.client.post(self.url_entrada, self.datos(cantidad='5', motivo='Compra proveedor'))
        self.assertRedirects(r, reverse('inventario:detalle', args=[self.producto.pk]))
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('15'))
        movimiento = MovimientoInventario.objects.get()
        self.assertEqual(movimiento.usuario, self.operario)
        self.assertEqual(movimiento.tipo_movimiento, TipoMovimiento.ENTRADA)

    def test_salida_por_post_descuenta_existencias(self):
        self.client.post(self.url_salida, self.datos(cantidad='4'))
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('6'))

    def test_salida_excesiva_muestra_error_y_no_cambia_stock(self):
        r = self.client.post(self.url_salida, self.datos(cantidad='99'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'No puedes sacar más de lo que hay.')
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('10'))
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_error_del_servicio_se_muestra_en_el_formulario(self):
        # Caso en que el stock cambia entre la validación del formulario y el servicio.
        with mock.patch('inventario.views.registrar_movimiento',
                        side_effect=StockInsuficiente('No hay suficiente "Tela algodón".')):
            r = self.client.post(self.url_salida, self.datos(cantidad='2'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'No hay suficiente')

    def test_entrada_con_cantidad_negativa_se_rechaza(self):
        r = self.client.post(self.url_entrada, self.datos(cantidad='-5'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(recargar(self.producto).cantidad_actual, Decimal('10'))

    def test_administrador_tambien_registra_movimientos(self):
        admin = crear_usuario('admin@taller.co', 'Admin', ROL_ADMINISTRADOR)
        self.client.force_login(admin)
        self.client.post(self.url_entrada, self.datos(cantidad='1'))
        self.assertEqual(MovimientoInventario.objects.get().usuario, admin)

    def test_ficha_muestra_botones_de_movimiento_solo_si_esta_activo(self):
        r = self.client.get(reverse('inventario:detalle', args=[self.producto.pk]))
        self.assertContains(r, 'Registrar entrada')
        self.assertContains(r, 'Registrar salida')

        inactivo = crear_producto('Hilo viejo', existencias='5', estado='inactivo')
        r = self.client.get(reverse('inventario:detalle', args=[inactivo.pk]))
        self.assertNotContains(r, 'Registrar salida')

    def test_movimientos_no_se_pueden_editar_desde_el_admin(self):
        movimiento = registrar_movimiento(
            producto=self.producto, usuario=self.operario, tipo=TipoMovimiento.ENTRADA,
            cantidad=Decimal('1'), motivo='Compra',
        )
        admin = crear_usuario('admin@taller.co', 'Admin', ROL_ADMINISTRADOR)
        self.client.force_login(admin)
        url = reverse('admin:inventario_movimientoinventario_change', args=[movimiento.pk])
        r = self.client.post(url, {'motivo': 'Cambio indebido', 'cantidad': '99', 'producto': self.producto.pk,
                                   'usuario': self.operario.pk, 'tipo_movimiento': 'entrada'})
        self.assertEqual(r.status_code, 403)
        movimiento.refresh_from_db()
        self.assertEqual(movimiento.motivo, 'Compra')

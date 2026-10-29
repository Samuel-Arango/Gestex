"""Pruebas del historial de movimientos (Fase 5): filtros, fechas, paginación y consultas."""
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import ROL_OPERARIO, Rol, Usuario

from .models import MovimientoInventario, Producto, TipoMovimiento, TipoProducto
from .services import registrar_movimiento

PASSWORD = 'Clave-Segura-2026'


def crear_usuario(correo, nombre):
    return Usuario.objects.create_user(
        correo, nombre, PASSWORD, id_rol=Rol.objects.get(nombre_rol=ROL_OPERARIO),
    )


def crear_producto(nombre, tipo=TipoProducto.INSUMO, existencias='1000'):
    producto = Producto.objects.create(
        nombre=nombre, tipo=tipo, unidad_medida='metros', stock_minimo=Decimal('1'),
    )
    Producto.objects.filter(pk=producto.pk).update(cantidad_actual=Decimal(existencias))
    return producto


def movimiento(producto, usuario, tipo=TipoMovimiento.ENTRADA, cantidad='1', motivo='Compra'):
    return registrar_movimiento(
        producto=producto, usuario=usuario, tipo=tipo,
        cantidad=Decimal(cantidad), motivo=motivo,
    )


def fijar_fecha(mov, fecha):
    """auto_now_add impide asignar la fecha al crear; se fija después con update()."""
    MovimientoInventario.objects.filter(pk=mov.pk).update(
        fecha=timezone.make_aware(datetime.combine(fecha, datetime.min.time().replace(hour=12))),
    )


class BaseHistorialTests(TestCase):

    def setUp(self):
        self.operario = crear_usuario('operario@taller.co', 'Operario Uno')
        self.client.force_login(self.operario)
        self.url = reverse('inventario:historial')
        self.algodon = crear_producto('Tela algodón blanca')
        self.hilo = crear_producto('Hilo poliéster')
        self.camisa = crear_producto('Camisa básica', tipo=TipoProducto.PRODUCTO_TERMINADO)


class AccesoYListadoTests(BaseHistorialTests):

    def test_visitante_anonimo_es_redirigido(self):
        self.client.logout()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('accounts:login'), r['Location'])

    def test_historial_vacio_muestra_mensaje(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Todavía no hay movimientos registrados')

    def test_lista_del_mas_reciente_al_mas_antiguo(self):
        primero = movimiento(self.algodon, self.operario, motivo='Primero')
        segundo = movimiento(self.hilo, self.operario, motivo='Segundo')
        fijar_fecha(primero, datetime(2026, 1, 1).date())
        fijar_fecha(segundo, datetime(2026, 2, 1).date())

        r = self.client.get(self.url)
        ids = [m.pk for m in r.context['movimientos']]
        self.assertEqual(ids, [segundo.pk, primero.pk])

    def test_muestra_usuario_motivo_y_cantidad(self):
        movimiento(self.algodon, self.operario, cantidad='12.5', motivo='Compra proveedor X')
        r = self.client.get(self.url)
        self.assertContains(r, 'Compra proveedor X')
        self.assertContains(r, 'Operario Uno')
        self.assertContains(r, '12,5')  # formato español: coma decimal

    def test_motivo_se_escapa_en_el_html(self):
        movimiento(self.algodon, self.operario, motivo='<b>negrita</b>')
        r = self.client.get(self.url)
        self.assertNotContains(r, '<b>negrita</b>')
        self.assertContains(r, '&lt;b&gt;negrita&lt;/b&gt;')


class FiltrosTests(BaseHistorialTests):

    def setUp(self):
        super().setUp()
        self.e_algodon = movimiento(self.algodon, self.operario, motivo='E algodón')
        self.s_algodon = movimiento(self.algodon, self.operario, tipo=TipoMovimiento.SALIDA, motivo='S algodón')
        self.e_hilo = movimiento(self.hilo, self.operario, motivo='E hilo')
        self.e_camisa = movimiento(self.camisa, self.operario, motivo='E camisa')

    def ids(self, **params):
        r = self.client.get(self.url, params)
        self.assertEqual(r.status_code, 200)
        return {m.pk for m in r.context['movimientos']}

    def test_filtro_por_nombre_sin_mayusculas_ni_tildes(self):
        self.assertEqual(self.ids(q='ALGODON'), {self.e_algodon.pk, self.s_algodon.pk})

    def test_filtro_por_tipo_de_material(self):
        self.assertEqual(self.ids(tipo_material=TipoProducto.PRODUCTO_TERMINADO), {self.e_camisa.pk})
        self.assertEqual(
            self.ids(tipo_material=TipoProducto.INSUMO),
            {self.e_algodon.pk, self.s_algodon.pk, self.e_hilo.pk},
        )

    def test_filtro_por_tipo_de_movimiento(self):
        self.assertEqual(self.ids(tipo_movimiento=TipoMovimiento.SALIDA), {self.s_algodon.pk})

    def test_filtros_combinados(self):
        pks = self.ids(q='algodon', tipo_movimiento=TipoMovimiento.ENTRADA)
        self.assertEqual(pks, {self.e_algodon.pk})

    def test_filtro_por_producto_desde_la_ficha(self):
        r = self.client.get(self.url, {'producto': self.hilo.pk})
        self.assertEqual({m.pk for m in r.context['movimientos']}, {self.e_hilo.pk})
        self.assertContains(r, 'Mostrando solo movimientos de')

    def test_valores_invalidos_no_rompen_el_listado(self):
        r = self.client.get(self.url, {'tipo_material': 'basura', 'tipo_movimiento': 'x', 'producto': 'abc'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['movimientos']), 4)

    def test_cada_filtro_tiene_su_opcion_seleccionada(self):
        r = self.client.get(self.url, {'tipo_movimiento': 'salida'})
        self.assertContains(r, '<option value="salida" selected>')

    def test_limpiar_aparece_solo_con_filtros(self):
        self.assertNotContains(self.client.get(self.url), 'Limpiar')
        self.assertContains(self.client.get(self.url, {'q': 'hilo'}), 'Limpiar')


class FiltroPorFechaTests(BaseHistorialTests):

    def setUp(self):
        super().setUp()
        self.antiguo = movimiento(self.algodon, self.operario, motivo='Antiguo')
        self.reciente = movimiento(self.algodon, self.operario, motivo='Reciente')
        fijar_fecha(self.antiguo, datetime(2026, 1, 10).date())
        fijar_fecha(self.reciente, datetime(2026, 3, 15).date())

    def pks(self, **params):
        r = self.client.get(self.url, params)
        return {m.pk for m in r.context['movimientos']}, r

    def test_desde(self):
        pks, _ = self.pks(desde='2026-02-01')
        self.assertEqual(pks, {self.reciente.pk})

    def test_hasta(self):
        pks, _ = self.pks(hasta='2026-02-01')
        self.assertEqual(pks, {self.antiguo.pk})

    def test_rango_incluye_los_extremos(self):
        pks, _ = self.pks(desde='2026-01-10', hasta='2026-03-15')
        self.assertEqual(pks, {self.antiguo.pk, self.reciente.pk})

    def test_rango_invertido_muestra_error_y_no_filtra(self):
        pks, r = self.pks(desde='2026-03-01', hasta='2026-01-01')
        self.assertContains(r, 'La fecha final no puede ser anterior a la inicial.')
        self.assertEqual(pks, {self.antiguo.pk, self.reciente.pk})

    def test_fecha_con_formato_invalido_muestra_error(self):
        _, r = self.pks(desde='no-es-fecha')
        self.assertContains(r, 'Revisa los filtros')


class PaginacionYResumenTests(BaseHistorialTests):

    def test_pagina_de_20_y_conserva_los_filtros(self):
        for i in range(25):
            movimiento(self.algodon, self.operario, motivo=f'Mov {i}')
        r = self.client.get(self.url, {'q': 'algodon'})
        self.assertEqual(len(r.context['movimientos']), 20)
        self.assertContains(r, 'q=algodon&amp;page=2')

        r2 = self.client.get(self.url, {'q': 'algodon', 'page': 2})
        self.assertEqual(len(r2.context['movimientos']), 5)

    def test_resumen_cuenta_el_conjunto_filtrado_no_la_pagina(self):
        for _ in range(25):
            movimiento(self.algodon, self.operario)
        movimiento(self.algodon, self.operario, tipo=TipoMovimiento.SALIDA, cantidad='3')
        movimiento(self.hilo, self.operario)

        r = self.client.get(self.url, {'q': 'algodon'})
        resumen = r.context['resumen']
        self.assertEqual(resumen['total'], 26)  # 25 entradas + 1 salida de algodón
        self.assertEqual(resumen['entradas'], 25)
        self.assertEqual(resumen['salidas'], 1)

    def test_numero_de_consultas_no_crece_con_el_numero_de_filas(self):
        # select_related evita una consulta extra por cada fila (producto, usuario, producción).
        for _ in range(3):
            movimiento(self.algodon, self.operario)
        with CaptureQueriesContext(connection) as pocas:
            self.client.get(self.url)

        for _ in range(17):
            movimiento(self.hilo, self.operario)
        with CaptureQueriesContext(connection) as muchas:
            self.client.get(self.url)

        self.assertEqual(len(pocas.captured_queries), len(muchas.captured_queries))


class EnlacesTests(BaseHistorialTests):

    def test_menu_tiene_enlace_al_historial(self):
        r = self.client.get(reverse('dashboard:home'))
        self.assertContains(r, reverse('inventario:historial'))

    def test_ficha_enlaza_al_historial_filtrado(self):
        r = self.client.get(reverse('inventario:detalle', args=[self.hilo.pk]))
        self.assertContains(r, f'{reverse("inventario:historial")}?producto={self.hilo.pk}')

    def test_historial_no_permite_editar_ni_borrar(self):
        mov = movimiento(self.algodon, self.operario)
        r = self.client.post(
            reverse('admin:inventario_movimientoinventario_delete', args=[mov.pk]),
        )
        self.assertIn(r.status_code, (302, 403))
        self.assertTrue(MovimientoInventario.objects.filter(pk=mov.pk).exists())

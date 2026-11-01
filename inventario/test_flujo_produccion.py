"""
Flujo completo de producción (Fase 9):
producción -> producto terminado -> ingreso automático al inventario -> dashboard,
y registro de consumo de materiales en una sola operación.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import ROL_OPERARIO, Rol, Usuario

from .forms import ProduccionForm
from .models import (
    DetalleMaterial,
    EstadoProduccion,
    MovimientoInventario,
    Producto,
    Produccion,
    TipoMovimiento,
    TipoProducto,
)
from .services import (
    ErrorMovimiento,
    finalizar_produccion,
    obtener_o_crear_producto_terminado,
    registrar_consumo_produccion,
)

PASSWORD = 'Clave-Segura-2026'


def crear_usuario(correo='op@taller.co'):
    return Usuario.objects.create_user(
        correo, 'Operario', PASSWORD, id_rol=Rol.objects.get(nombre_rol=ROL_OPERARIO),
    )


def crear_insumo(nombre, existencias='100'):
    producto = Producto.objects.create(
        nombre=nombre, tipo=TipoProducto.INSUMO, unidad_medida='metros', stock_minimo=Decimal('1'),
    )
    Producto.objects.filter(pk=producto.pk).update(cantidad_actual=Decimal(existencias))
    return producto


def crear_produccion(usuario, producto_terminado=None, cantidad=20, **extra):
    return Produccion.objects.create(
        descripcion='Camisas básicas', tipo='Confección', cantidad_solicitada=cantidad,
        fecha_inicio=date(2026, 1, 10), fecha_entrega=date(2026, 1, 20), usuario=usuario,
        producto_terminado=producto_terminado, **extra,
    )


def datos_form(**cambios):
    datos = {
        'tipo': 'Confección',
        'descripcion': 'Camisas básicas talla M',
        'cantidad_solicitada': '20',
        'fecha_inicio': '2026-01-10',
        'fecha_entrega': '2026-01-20',
        'producto_nombre': 'Camisa básica blanca',
        'estado': EstadoProduccion.PENDIENTE,
    }
    datos.update(cambios)
    return datos


def stock(producto):
    producto.refresh_from_db()
    return producto.cantidad_actual


class ProductoTerminadoAutomaticoTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario()

    def test_crea_el_producto_terminado_si_no_existe(self):
        producto = obtener_o_crear_producto_terminado('  Camisa   básica blanca ')
        self.assertEqual(producto.nombre, 'Camisa básica blanca')
        self.assertEqual(producto.tipo, TipoProducto.PRODUCTO_TERMINADO)
        self.assertEqual(producto.cantidad_actual, Decimal('0'))

    def test_reutiliza_el_producto_existente_sin_importar_mayusculas(self):
        existente = obtener_o_crear_producto_terminado('Camisa básica blanca')
        otra_vez = obtener_o_crear_producto_terminado('CAMISA BÁSICA BLANCA')
        self.assertEqual(existente.pk, otra_vez.pk)
        self.assertEqual(Producto.objects.filter(tipo=TipoProducto.PRODUCTO_TERMINADO).count(), 1)

    def test_no_convierte_un_insumo_en_producto_terminado(self):
        crear_insumo('Tela algodón')
        with self.assertRaises(ErrorMovimiento):
            obtener_o_crear_producto_terminado('tela algodón')

    def test_formulario_crea_el_producto_al_guardar_la_produccion(self):
        form = ProduccionForm(datos_form())
        form.instance.usuario = self.usuario
        self.assertTrue(form.is_valid(), form.errors)
        produccion = form.save()
        self.assertEqual(produccion.producto_terminado.nombre, 'Camisa básica blanca')
        self.assertEqual(produccion.producto_terminado.tipo, TipoProducto.PRODUCTO_TERMINADO)

    def test_formulario_rechaza_un_nombre_que_es_insumo(self):
        crear_insumo('Tela algodón')
        form = ProduccionForm(datos_form(producto_nombre='tela algodón'))
        form.instance.usuario = self.usuario
        self.assertFalse(form.is_valid())
        self.assertIn('producto_nombre', form.errors)


class IngresoAlTerminarTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario()
        self.camisa = obtener_o_crear_producto_terminado('Camisa básica blanca')

    def test_terminar_ingresa_las_unidades_una_sola_vez(self):
        produccion = crear_produccion(self.usuario, self.camisa, cantidad=20)
        produccion.estado = EstadoProduccion.TERMINADA
        produccion.save()

        finalizar_produccion(produccion, self.usuario)
        finalizar_produccion(produccion, self.usuario)  # segunda vez: no duplica

        self.assertEqual(stock(self.camisa), Decimal('20'))
        self.assertEqual(MovimientoInventario.objects.filter(produccion=produccion).count(), 1)
        movimiento = MovimientoInventario.objects.get()
        self.assertEqual(movimiento.tipo_movimiento, TipoMovimiento.ENTRADA)
        self.assertEqual(movimiento.producto, self.camisa)

    def test_no_ingresa_si_la_produccion_no_esta_terminada(self):
        produccion = crear_produccion(self.usuario, self.camisa)
        with self.assertRaises(ErrorMovimiento):
            finalizar_produccion(produccion, self.usuario)
        self.assertEqual(stock(self.camisa), Decimal('0'))

    def test_no_ingresa_si_no_hay_producto_terminado(self):
        produccion = crear_produccion(self.usuario, None)
        produccion.estado = EstadoProduccion.TERMINADA
        with self.assertRaises(ErrorMovimiento):
            finalizar_produccion(produccion, self.usuario)

    def test_boton_terminar_ingresa_el_stock_y_cierra_la_produccion(self):
        self.client.force_login(self.usuario)
        produccion = crear_produccion(self.usuario, self.camisa, cantidad=15)
        r = self.client.post(reverse('inventario:produccion_terminar', args=[produccion.pk]))
        self.assertRedirects(r, reverse('inventario:produccion_detalle', args=[produccion.pk]))

        produccion.refresh_from_db()
        self.assertEqual(produccion.estado, EstadoProduccion.TERMINADA)
        self.assertTrue(produccion.ingreso_registrado)
        self.assertEqual(stock(self.camisa), Decimal('15'))

    def test_boton_terminar_no_funciona_por_get(self):
        self.client.force_login(self.usuario)
        produccion = crear_produccion(self.usuario, self.camisa)
        self.assertEqual(
            self.client.get(reverse('inventario:produccion_terminar', args=[produccion.pk])).status_code, 405,
        )

    def test_guardar_en_terminada_desde_el_formulario_ingresa_el_stock(self):
        self.client.force_login(self.usuario)
        produccion = crear_produccion(self.usuario, self.camisa, cantidad=8)
        datos = datos_form(estado=EstadoProduccion.TERMINADA, cantidad_solicitada='8')
        datos.update({
            'detalles-TOTAL_FORMS': '0', 'detalles-INITIAL_FORMS': '0',
            'detalles-MIN_NUM_FORMS': '0', 'detalles-MAX_NUM_FORMS': '1000',
        })
        r = self.client.post(reverse('inventario:produccion_editar', args=[produccion.pk]), datos)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(stock(self.camisa), Decimal('8'))

    def test_una_produccion_ingresada_no_puede_volver_a_otro_estado(self):
        produccion = crear_produccion(self.usuario, self.camisa, ingreso_registrado=True,
                                      estado=EstadoProduccion.TERMINADA)
        form = ProduccionForm(datos_form(estado=EstadoProduccion.EN_PROCESO), instance=produccion)
        self.assertFalse(form.is_valid())
        self.assertIn('estado', form.errors)

    def test_una_produccion_ingresada_no_puede_cambiar_de_producto(self):
        produccion = crear_produccion(self.usuario, self.camisa, ingreso_registrado=True,
                                      estado=EstadoProduccion.TERMINADA)
        form = ProduccionForm(
            datos_form(estado=EstadoProduccion.TERMINADA, producto_nombre='Pantalón jean'),
            instance=produccion,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('producto_nombre', form.errors)

    def test_terminada_sin_producto_no_se_puede_guardar(self):
        produccion = crear_produccion(self.usuario, None)
        form = ProduccionForm(
            datos_form(estado=EstadoProduccion.TERMINADA, producto_nombre=''), instance=produccion,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('producto_nombre', form.errors)


class ConsumoEnLoteTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario()
        self.client.force_login(self.usuario)
        self.tela = crear_insumo('Tela algodón', existencias='100')
        self.boton = crear_insumo('Botón nácar', existencias='50')
        self.camisa = obtener_o_crear_producto_terminado('Camisa básica blanca')
        self.produccion = crear_produccion(self.usuario, self.camisa)
        self.det_tela = DetalleMaterial.objects.create(
            produccion=self.produccion, producto=self.tela, cantidad_requerida=Decimal('40'),
        )
        self.det_boton = DetalleMaterial.objects.create(
            produccion=self.produccion, producto=self.boton, cantidad_requerida=Decimal('20'),
        )
        self.url = reverse('inventario:produccion_consumo', args=[self.produccion.pk])

    def test_pantalla_muestra_una_casilla_por_material_prellenada(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="material_%d"' % self.det_tela.pk)
        self.assertContains(r, 'name="material_%d"' % self.det_boton.pk)
        # Lo pendiente de la tela (40) aparece como valor inicial.
        self.assertContains(r, 'value="40.00"')

    def test_registra_todos_los_consumos_en_una_operacion(self):
        r = self.client.post(self.url, {
            f'material_{self.det_tela.pk}': '12.5',
            f'material_{self.det_boton.pk}': '6',
        })
        self.assertRedirects(r, reverse('inventario:produccion_detalle', args=[self.produccion.pk]))

        self.det_tela.refresh_from_db()
        self.det_boton.refresh_from_db()
        self.assertEqual(self.det_tela.cantidad_utilizada, Decimal('12.5'))
        self.assertEqual(self.det_boton.cantidad_utilizada, Decimal('6'))
        self.assertEqual(stock(self.tela), Decimal('87.5'))
        self.assertEqual(stock(self.boton), Decimal('44'))
        self.assertEqual(MovimientoInventario.objects.filter(produccion=self.produccion).count(), 2)

    def test_casillas_vacias_o_en_cero_no_generan_movimientos(self):
        self.client.post(self.url, {
            f'material_{self.det_tela.pk}': '',
            f'material_{self.det_boton.pk}': '0',
        })
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_sin_ninguna_cantidad_muestra_error(self):
        r = self.client.post(self.url, {f'material_{self.det_tela.pk}': ''})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Indica la cantidad utilizada de al menos un material.')

    def test_si_un_material_no_alcanza_no_se_registra_ninguno(self):
        # El botón tiene 50 y pedimos 60: el lote completo debe revertirse.
        r = self.client.post(self.url, {
            f'material_{self.det_tela.pk}': '10',
            f'material_{self.det_boton.pk}': '60',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(MovimientoInventario.objects.exists())
        self.assertEqual(stock(self.tela), Decimal('100'))
        self.det_tela.refresh_from_db()
        self.assertEqual(self.det_tela.cantidad_utilizada, Decimal('0'))

    def test_no_se_puede_consumir_en_una_produccion_terminada(self):
        Produccion.objects.filter(pk=self.produccion.pk).update(estado=EstadoProduccion.TERMINADA)
        r = self.client.get(self.url)
        self.assertRedirects(r, reverse('inventario:produccion_detalle', args=[self.produccion.pk]))

        with self.assertRaises(ErrorMovimiento):
            registrar_consumo_produccion(
                Produccion.objects.get(pk=self.produccion.pk), self.usuario,
                {self.det_tela.pk: Decimal('1')},
            )

    def test_material_de_otra_produccion_no_se_puede_consumir_desde_esta(self):
        otra = crear_produccion(self.usuario, self.camisa)
        ajeno = DetalleMaterial.objects.create(
            produccion=otra, producto=self.tela, cantidad_requerida=Decimal('5'),
        )
        registrar_consumo_produccion(
            self.produccion, self.usuario, {ajeno.pk: Decimal('2')},
        )
        # El ID no pertenece a esta producción: no se registra nada.
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_usuario_sin_permiso_de_movimientos_no_entra(self):
        Rol.objects.get_or_create(nombre_rol='Invitado', defaults={'descripcion': 'Sin permisos.'})
        invitado = Usuario.objects.create_user(
            'inv@taller.co', 'Invitado', PASSWORD, id_rol=Rol.objects.get(nombre_rol='Invitado'),
        )
        self.client.force_login(invitado)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class DashboardProduccionTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario()
        self.client.force_login(self.usuario)

    def test_dashboard_muestra_terminados_sin_cargarlos_a_mano(self):
        camisa = obtener_o_crear_producto_terminado('Camisa básica blanca')
        produccion = crear_produccion(self.usuario, camisa, cantidad=12)
        produccion.estado = EstadoProduccion.TERMINADA
        produccion.save()
        finalizar_produccion(produccion, self.usuario)

        r = self.client.get(reverse('dashboard:home'))
        self.assertEqual(r.context['total_unidades_terminadas'], 12)
        self.assertContains(r, 'Camisa básica blanca')
        self.assertContains(r, f'#{produccion.pk} · Camisa básica blanca')

    def test_dashboard_suma_varias_producciones_del_mismo_producto(self):
        camisa = obtener_o_crear_producto_terminado('Camisa básica blanca')
        for cantidad in (5, 7):
            p = crear_produccion(self.usuario, camisa, cantidad=cantidad)
            p.estado = EstadoProduccion.TERMINADA
            p.save()
            finalizar_produccion(p, self.usuario)
        r = self.client.get(reverse('dashboard:home'))
        self.assertEqual(r.context['total_unidades_terminadas'], 12)

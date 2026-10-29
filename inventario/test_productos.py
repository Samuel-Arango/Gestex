"""Pruebas del CRUD de productos (Fase 3): permisos, búsqueda, validaciones y estados."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import ROL_ADMINISTRADOR, ROL_OPERARIO, Rol, Usuario

from .models import (
    DetalleMaterial,
    MovimientoInventario,
    Producto,
    Produccion,
    TipoMovimiento,
    TipoProducto,
)

PASSWORD = 'Clave-Segura-2026'


def crear_usuario(correo, nombre, nombre_rol):
    return Usuario.objects.create_user(
        correo, nombre, PASSWORD, id_rol=Rol.objects.get(nombre_rol=nombre_rol),
    )


def crear_producto(nombre, tipo=TipoProducto.INSUMO, **extra):
    datos = {'tipo': tipo, 'unidad_medida': 'metros', 'stock_minimo': Decimal('10')}
    datos.update(extra)
    return Producto.objects.create(nombre=nombre, **datos)


def datos_formulario(**cambios):
    datos = {
        'nombre': 'Tela lino beige',
        'tipo': TipoProducto.INSUMO,
        'unidad_medida': 'Metros',
        'stock_minimo': '5',
        'descripcion': 'Ancho 1.50 m',
        'estado': 'activo',  # el formulario de edición lo envía siempre
    }
    datos.update(cambios)
    return datos


class BaseProductoTests(TestCase):

    def setUp(self):
        self.operario = crear_usuario('operario@taller.co', 'Operario', ROL_OPERARIO)
        self.admin = crear_usuario('admin@taller.co', 'Admin', ROL_ADMINISTRADOR)
        self.client.force_login(self.operario)


class ListadoYBusquedaTests(BaseProductoTests):

    def test_visitante_anonimo_es_redirigido_al_login(self):
        self.client.logout()
        r = self.client.get(reverse('inventario:lista'))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('accounts:login'), r['Location'])

    def test_operario_ve_el_listado(self):
        crear_producto('Tela algodón blanca')
        r = self.client.get(reverse('inventario:lista'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Tela algodón blanca')

    def test_busqueda_por_nombre_sin_distinguir_mayusculas(self):
        crear_producto('Tela algodón blanca')
        crear_producto('Hilo poliéster')
        r = self.client.get(reverse('inventario:lista'), {'q': 'ALGODÓN'})
        self.assertContains(r, 'Tela algodón blanca')
        self.assertNotContains(r, 'Hilo poliéster')

    def test_busqueda_ignora_tildes_en_ambos_sentidos(self):
        crear_producto('Tela algodón blanca')
        crear_producto('Tela jean azul')
        # Sin tilde en la búsqueda encuentra el nombre con tilde.
        r = self.client.get(reverse('inventario:lista'), {'q': 'algodon'})
        self.assertContains(r, 'Tela algodón blanca')
        self.assertNotContains(r, 'Tela jean azul')

    def test_busqueda_con_caracteres_especiales_no_rompe_el_listado(self):
        crear_producto('Tela 100% algodón')
        crear_producto('Tela común')
        # El % no debe comportarse como comodín de SQL.
        r = self.client.get(reverse('inventario:lista'), {'q': '%'})
        self.assertContains(r, 'Tela 100% algodón')
        self.assertNotContains(r, 'Tela común')

    def test_busqueda_por_descripcion(self):
        crear_producto('Botón', descripcion='Nácar de 15 mm')
        crear_producto('Cierre')
        r = self.client.get(reverse('inventario:lista'), {'q': 'nácar'})
        self.assertContains(r, 'Botón')
        self.assertNotContains(r, 'Cierre')

    def test_sin_resultados_muestra_mensaje_y_forma_de_limpiar(self):
        crear_producto('Tela algodón')
        r = self.client.get(reverse('inventario:lista'), {'q': 'xyz-no-existe'})
        self.assertContains(r, 'No encontramos productos con esos filtros')
        self.assertContains(r, 'quita los filtros')

    def test_estado_vacio_invita_a_registrar(self):
        r = self.client.get(reverse('inventario:lista'))
        self.assertContains(r, 'Todavía no tienes productos registrados')

    def test_filtro_por_tipo(self):
        crear_producto('Tela algodón', tipo=TipoProducto.INSUMO)
        crear_producto('Camisa básica', tipo=TipoProducto.PRODUCTO_TERMINADO)
        r = self.client.get(reverse('inventario:lista'), {'tipo': TipoProducto.PRODUCTO_TERMINADO})
        self.assertContains(r, 'Camisa básica')
        self.assertNotContains(r, 'Tela algodón')

    def test_filtro_por_estado(self):
        crear_producto('Tela activa')
        crear_producto('Tela vieja', estado='inactivo')
        r = self.client.get(reverse('inventario:lista'), {'estado': 'inactivo'})
        self.assertContains(r, 'Tela vieja')
        self.assertNotContains(r, 'Tela activa')

    def test_valores_de_filtro_invalidos_se_ignoran(self):
        crear_producto('Tela algodón')
        r = self.client.get(reverse('inventario:lista'), {'tipo': 'basura', 'estado': 'x'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Tela algodón')

    def test_listado_se_pagina_y_conserva_la_busqueda(self):
        for i in range(16):
            crear_producto(f'Tela {i:02d}')
        r = self.client.get(reverse('inventario:lista'), {'q': 'Tela'})
        self.assertEqual(len(r.context['productos']), 15)
        self.assertContains(r, 'q=Tela&amp;page=2')

    def test_alerta_cuenta_solo_productos_activos_con_stock_bajo(self):
        bajo = crear_producto('Hilo bajo', stock_minimo=Decimal('5'))
        sano = crear_producto('Hilo sano', stock_minimo=Decimal('5'))
        crear_producto('Hilo inactivo bajo', stock_minimo=Decimal('5'), estado='inactivo')
        Producto.objects.filter(pk=bajo.pk).update(cantidad_actual=Decimal('2'))
        Producto.objects.filter(pk=sano.pk).update(cantidad_actual=Decimal('50'))

        r = self.client.get(reverse('inventario:lista'))
        self.assertEqual(r.context['total_en_alerta'], 1)

    def test_datos_de_producto_se_escapan_en_el_html(self):
        crear_producto('<script>alert(1)</script>')
        r = self.client.get(reverse('inventario:lista'))
        self.assertNotContains(r, '<script>alert(1)</script>')
        self.assertContains(r, '&lt;script&gt;alert(1)&lt;/script&gt;')


class CrearProductoTests(BaseProductoTests):

    def test_formulario_de_alta_carga(self):
        r = self.client.get(reverse('inventario:crear'))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'name="cantidad_actual"')

    def test_registro_valido_crea_producto_con_existencias_en_cero(self):
        r = self.client.post(reverse('inventario:crear'), datos_formulario(cantidad_actual='999'))
        self.assertRedirects(r, reverse('inventario:lista'))
        producto = Producto.objects.get(nombre='Tela lino beige')
        self.assertEqual(producto.unidad_medida, 'metros')  # se normaliza a minúsculas
        self.assertEqual(producto.cantidad_actual, Decimal('0'))  # el campo enviado se ignora
        self.assertEqual(producto.estado, 'activo')

    def test_nombre_repetido_sin_importar_mayusculas_se_rechaza(self):
        crear_producto('Tela Lino Beige')
        r = self.client.post(reverse('inventario:crear'), datos_formulario(nombre='  tela   LINO beige '))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Ya existe un producto con este nombre.')
        self.assertEqual(Producto.objects.filter(nombre__iexact='tela lino beige').count(), 1)

    def test_nombre_demasiado_corto_se_rechaza(self):
        r = self.client.post(reverse('inventario:crear'), datos_formulario(nombre='T'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'al menos 2 caracteres')

    def test_stock_minimo_negativo_se_rechaza(self):
        r = self.client.post(reverse('inventario:crear'), datos_formulario(stock_minimo='-3'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Producto.objects.filter(nombre='Tela lino beige').exists())

    def test_campos_obligatorios(self):
        r = self.client.post(reverse('inventario:crear'), {})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Producto.objects.exists())

    def test_tipo_invalido_se_rechaza(self):
        r = self.client.post(reverse('inventario:crear'), datos_formulario(tipo='otro'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Producto.objects.exists())


class EditarProductoTests(BaseProductoTests):

    def setUp(self):
        super().setUp()
        self.producto = crear_producto('Tela algodón')

    def test_operario_puede_modificar_datos(self):
        r = self.client.post(
            reverse('inventario:editar', args=[self.producto.pk]),
            datos_formulario(nombre='Tela algodón orgánica', stock_minimo='12'),
        )
        self.assertRedirects(r, reverse('inventario:detalle', args=[self.producto.pk]))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.nombre, 'Tela algodón orgánica')
        self.assertEqual(self.producto.stock_minimo, Decimal('12'))

    def test_editar_no_cambia_las_existencias(self):
        Producto.objects.filter(pk=self.producto.pk).update(cantidad_actual=Decimal('30'))
        self.client.post(
            reverse('inventario:editar', args=[self.producto.pk]),
            datos_formulario(nombre='Tela algodón', cantidad_actual='1'),
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad_actual, Decimal('30'))

    def test_no_se_puede_guardar_con_el_nombre_de_otro_producto(self):
        crear_producto('Tela lino')
        r = self.client.post(
            reverse('inventario:editar', args=[self.producto.pk]),
            datos_formulario(nombre='TELA LINO'),
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Ya existe un producto con este nombre.')

    def test_insumo_usado_en_produccion_no_puede_ser_producto_terminado(self):
        produccion = Produccion.objects.create(
            descripcion='Camisas', tipo='Confección', cantidad_solicitada=5,
            fecha_inicio=date(2026, 1, 1), fecha_entrega=date(2026, 1, 9),
            usuario=self.operario,
        )
        DetalleMaterial.objects.create(
            produccion=produccion, producto=self.producto, cantidad_requerida=Decimal('2'),
        )
        r = self.client.post(
            reverse('inventario:editar', args=[self.producto.pk]),
            datos_formulario(nombre='Tela algodón', tipo=TipoProducto.PRODUCTO_TERMINADO),
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'no puede convertirse en producto terminado')

    def test_no_existe_ruta_para_borrar_productos(self):
        r = self.client.post(f'/inventario/{self.producto.pk}/borrar/')
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Producto.objects.filter(pk=self.producto.pk).exists())


class DesactivarProductoTests(BaseProductoTests):

    def setUp(self):
        super().setUp()
        self.producto = crear_producto('Hilo poliéster')
        self.url = reverse('inventario:cambiar_estado', args=[self.producto.pk])

    def test_desactivar_y_reactivar_sin_borrar(self):
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.estado, 'inactivo')

        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.estado, 'activo')

        self.assertTrue(Producto.objects.filter(pk=self.producto.pk).exists())

    def test_cambiar_estado_solo_acepta_post(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 405)

    def test_visitante_anonimo_no_puede_cambiar_estado(self):
        self.client.logout()
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.estado, 'activo')


class DetalleProductoTests(BaseProductoTests):

    def test_ficha_muestra_datos_y_ultimos_movimientos(self):
        producto = crear_producto('Botones nácar')
        MovimientoInventario.objects.create(
            producto=producto, usuario=self.operario, tipo_movimiento=TipoMovimiento.ENTRADA,
            cantidad=Decimal('50'), motivo='Compra proveedor X',
        )
        r = self.client.get(reverse('inventario:detalle', args=[producto.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Botones nácar')
        self.assertContains(r, 'Compra proveedor X')

    def test_ficha_sin_movimientos_muestra_estado_vacio(self):
        producto = crear_producto('Cierre 20 cm')
        r = self.client.get(reverse('inventario:detalle', args=[producto.pk]))
        self.assertContains(r, 'aún no tiene movimientos')

    def test_producto_inexistente_responde_404(self):
        r = self.client.get(reverse('inventario:detalle', args=[9999]))
        self.assertEqual(r.status_code, 404)


class AdministradorTests(BaseProductoTests):

    def test_administrador_tambien_puede_gestionar_productos(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('inventario:lista')).status_code, 200)
        self.assertEqual(self.client.get(reverse('inventario:crear')).status_code, 200)

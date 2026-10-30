"""Pruebas del dashboard de inicio (Fase 8)."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import ROL_ADMINISTRADOR, ROL_OPERARIO, Rol, Usuario
from inventario.models import Producto, Produccion, TipoMovimiento, TipoProducto
from inventario.services import registrar_movimiento

PASSWORD = 'Clave-Segura-2026'


def crear_usuario(correo, nombre, nombre_rol):
    return Usuario.objects.create_user(
        correo, nombre, PASSWORD, id_rol=Rol.objects.get(nombre_rol=nombre_rol),
    )


def crear_producto(nombre, tipo=TipoProducto.INSUMO, existencias='0', stock_minimo='5', estado='activo'):
    producto = Producto.objects.create(
        nombre=nombre, tipo=tipo, unidad_medida='metros',
        stock_minimo=Decimal(stock_minimo), estado=estado,
    )
    Producto.objects.filter(pk=producto.pk).update(cantidad_actual=Decimal(existencias))
    return producto


class DashboardTests(TestCase):

    def setUp(self):
        self.operario = crear_usuario('op@taller.co', 'Operario Uno', ROL_OPERARIO)
        self.client.force_login(self.operario)
        self.url = reverse('dashboard:home')

    def test_requiere_sesion(self):
        self.client.logout()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('accounts:login'), r['Location'])

    def test_estado_vacio_no_rompe_la_pagina(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_insumos'], 0)
        self.assertContains(r, 'Todo tiene existencias suficientes')
        self.assertContains(r, 'Todavía no hay movimientos')
        self.assertContains(r, 'No hay producciones en curso')

    def test_cuenta_insumos_terminados_y_stock_bajo(self):
        crear_producto('Tela algodón', existencias='3', stock_minimo='5')   # bajo
        crear_producto('Hilo', existencias='50', stock_minimo='5')           # sano
        crear_producto('Camisa', tipo=TipoProducto.PRODUCTO_TERMINADO, existencias='0', stock_minimo='2')
        crear_producto('Botón viejo', existencias='0', stock_minimo='5', estado='inactivo')  # no cuenta

        r = self.client.get(self.url)
        self.assertEqual(r.context['total_insumos'], 2)
        self.assertEqual(r.context['total_terminados'], 1)
        self.assertEqual(r.context['total_en_alerta'], 2)  # tela y camisa, no el inactivo

    def test_lista_de_reposicion_muestra_los_productos_en_alerta(self):
        crear_producto('Tela algodón', existencias='3', stock_minimo='5')
        crear_producto('Hilo', existencias='50', stock_minimo='5')
        r = self.client.get(self.url)
        self.assertContains(r, 'Tela algodón')
        self.assertNotContains(r, 'Hilo')

    def test_muestra_movimientos_recientes_y_los_de_hoy(self):
        producto = crear_producto('Hilo', existencias='10')
        registrar_movimiento(
            producto=producto, usuario=self.operario, tipo=TipoMovimiento.SALIDA,
            cantidad=Decimal('2'), motivo='Corte',
        )
        r = self.client.get(self.url)
        self.assertEqual(r.context['movimientos_hoy'], 1)
        self.assertContains(r, 'Hilo')

    def test_muestra_producciones_activas_y_no_las_terminadas(self):
        produccion = Produccion.objects.create(
            descripcion='Camisas', tipo='Confección', cantidad_solicitada=5,
            fecha_inicio=date(2026, 1, 1), fecha_entrega=date(2026, 1, 9), usuario=self.operario,
        )
        Produccion.objects.create(
            descripcion='Entregada', tipo='Reparación', cantidad_solicitada=1,
            fecha_inicio=date(2026, 1, 1), fecha_entrega=date(2026, 1, 2),
            usuario=self.operario, estado='Terminada',
        )
        r = self.client.get(self.url)
        self.assertEqual(r.context['total_producciones_activas'], 1)
        self.assertContains(r, f'#{produccion.pk} · Confección')

    def test_usuario_sin_permisos_de_inventario_no_recibe_esos_datos(self):
        Rol.objects.get_or_create(nombre_rol='Invitado', defaults={'descripcion': 'Sin permisos.'})
        invitado = crear_usuario('inv@taller.co', 'Invitado', 'Invitado')
        crear_producto('Tela secreta', existencias='1')
        self.client.force_login(invitado)

        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('total_insumos', r.context)
        self.assertNotContains(r, 'Tela secreta')

    def test_administrador_ve_el_resumen(self):
        admin = crear_usuario('admin@taller.co', 'Admin', ROL_ADMINISTRADOR)
        self.client.force_login(admin)
        r = self.client.get(self.url)
        self.assertIn('total_insumos', r.context)

    def test_menu_sin_enlaces_de_marcador(self):
        r = self.client.get(self.url)
        self.assertNotContains(r, 'href="#"')
        self.assertNotContains(r, 'Stock por almacén')

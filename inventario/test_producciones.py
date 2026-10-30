"""Pruebas de producciones y lista de materiales (Fase 7)."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import ROL_ADMINISTRADOR, ROL_OPERARIO, Rol, Usuario

from .forms import DetalleMaterialForm, DetalleMaterialFormSet, ProduccionForm
from .models import (
    DetalleMaterial,
    EstadoProduccion,
    MovimientoInventario,
    Producto,
    Produccion,
    TipoMovimiento,
    TipoProducto,
)
from .services import registrar_movimiento

PASSWORD = 'Clave-Segura-2026'


def crear_usuario(correo, nombre, nombre_rol=ROL_OPERARIO):
    return Usuario.objects.create_user(
        correo, nombre, PASSWORD, id_rol=Rol.objects.get(nombre_rol=nombre_rol),
    )


def crear_producto(nombre, tipo=TipoProducto.INSUMO, existencias='100', estado='activo'):
    producto = Producto.objects.create(
        nombre=nombre, tipo=tipo, unidad_medida='metros',
        stock_minimo=Decimal('1'), estado=estado,
    )
    Producto.objects.filter(pk=producto.pk).update(cantidad_actual=Decimal(existencias))
    return producto


def crear_produccion(usuario, **extra):
    datos = {
        'descripcion': 'Camisas básicas', 'tipo': 'Confección', 'cantidad_solicitada': 20,
        'fecha_inicio': date(2026, 1, 10), 'fecha_entrega': date(2026, 1, 20), 'usuario': usuario,
    }
    datos.update(extra)
    return Produccion.objects.create(**datos)


def datos_produccion(**cambios):
    datos = {
        'tipo': 'Confección',
        'descripcion': 'Camisas básicas talla M',
        'cantidad_solicitada': '20',
        'fecha_inicio': '2026-01-10',
        'fecha_entrega': '2026-01-20',
        'estado': 'Pendiente',
    }
    datos.update(cambios)
    return datos


def datos_formset(filas, prefijo='detalles', iniciales=0):
    """Construye el POST del formset. filas: lista de dicts con producto, cantidad y opcional delete."""
    datos = {
        f'{prefijo}-TOTAL_FORMS': str(len(filas)),
        f'{prefijo}-INITIAL_FORMS': str(iniciales),
        f'{prefijo}-MIN_NUM_FORMS': '0',
        f'{prefijo}-MAX_NUM_FORMS': '1000',
    }
    for indice, fila in enumerate(filas):
        datos[f'{prefijo}-{indice}-producto'] = str(fila['producto'])
        datos[f'{prefijo}-{indice}-cantidad_requerida'] = str(fila['cantidad'])
        if fila.get('id'):
            datos[f'{prefijo}-{indice}-id'] = str(fila['id'])
        if fila.get('delete'):
            datos[f'{prefijo}-{indice}-DELETE'] = 'on'
    return datos


class ReglasDelFormularioTests(TestCase):

    def setUp(self):
        self.operario = crear_usuario('op@taller.co', 'Operario')

    def test_fecha_de_entrega_anterior_al_inicio_se_rechaza(self):
        form = ProduccionForm(datos_produccion(fecha_inicio='2026-02-10', fecha_entrega='2026-02-01'))
        form.instance.usuario = self.operario
        self.assertFalse(form.is_valid())
        self.assertIn('fecha_entrega', form.errors)

    def test_nueva_produccion_empieza_pendiente_sin_campo_estado(self):
        form = ProduccionForm()
        self.assertNotIn('estado', form.fields)

    def test_estado_fuera_de_la_lista_se_rechaza(self):
        produccion = crear_produccion(self.operario)
        form = ProduccionForm(datos_produccion(estado='Inventada'), instance=produccion)
        self.assertFalse(form.is_valid())
        self.assertIn('estado', form.errors)

    def test_estado_valido_al_editar(self):
        produccion = crear_produccion(self.operario)
        form = ProduccionForm(datos_produccion(estado=EstadoProduccion.TERMINADA), instance=produccion)
        self.assertTrue(form.is_valid(), form.errors)

    def test_detalle_solo_ofrece_insumos_activos(self):
        activo = crear_producto('Tela activa')
        inactivo = crear_producto('Tela vieja', estado='inactivo')
        terminado = crear_producto('Camisa', tipo=TipoProducto.PRODUCTO_TERMINADO)
        opciones = list(DetalleMaterialForm().fields['producto'].queryset)
        self.assertIn(activo, opciones)
        self.assertNotIn(inactivo, opciones)
        self.assertNotIn(terminado, opciones)

    def test_insumo_inactivo_ya_asignado_se_mantiene_visible_en_su_fila(self):
        produccion = crear_produccion(self.operario)
        insumo = crear_producto('Tela que se desactivó')
        detalle = DetalleMaterial.objects.create(
            produccion=produccion, producto=insumo, cantidad_requerida=Decimal('5'),
        )
        Producto.objects.filter(pk=insumo.pk).update(estado='inactivo')
        form = DetalleMaterialForm(instance=detalle)
        self.assertIn(insumo, list(form.fields['producto'].queryset))


class FormsetTests(TestCase):

    def setUp(self):
        self.operario = crear_usuario('op@taller.co', 'Operario')
        self.produccion = crear_produccion(self.operario)
        self.tela = crear_producto('Tela algodón')
        self.hilo = crear_producto('Hilo')

    def formset(self, datos, instancia=None):
        return DetalleMaterialFormSet(datos, instance=instancia or self.produccion)

    def test_insumo_repetido_se_rechaza_con_mensaje_claro(self):
        formset = self.formset(datos_formset([
            {'producto': self.tela.pk, 'cantidad': '2'},
            {'producto': self.tela.pk, 'cantidad': '3'},
        ]))
        self.assertFalse(formset.is_valid())
        self.assertIn('Un mismo insumo no puede aparecer dos veces', str(formset.non_form_errors()))

    def test_fila_vacia_no_cuenta_como_material(self):
        formset = self.formset(datos_formset([
            {'producto': self.tela.pk, 'cantidad': '2'},
            {'producto': '', 'cantidad': ''},
        ]))
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_cantidad_requerida_no_puede_bajar_del_consumo(self):
        detalle = DetalleMaterial.objects.create(
            produccion=self.produccion, producto=self.tela, cantidad_requerida=Decimal('10'),
        )
        DetalleMaterial.objects.filter(pk=detalle.pk).update(cantidad_utilizada=Decimal('6'))
        formset = self.formset(datos_formset([
            {'id': detalle.pk, 'producto': self.tela.pk, 'cantidad': '4'},
        ], iniciales=1))
        self.assertFalse(formset.is_valid())
        self.assertIn('No puede ser menor a lo ya utilizado', str(formset.errors))

    def test_material_con_consumo_no_se_puede_quitar(self):
        detalle = DetalleMaterial.objects.create(
            produccion=self.produccion, producto=self.tela, cantidad_requerida=Decimal('10'),
        )
        DetalleMaterial.objects.filter(pk=detalle.pk).update(cantidad_utilizada=Decimal('1'))
        formset = self.formset(datos_formset([
            {'id': detalle.pk, 'producto': self.tela.pk, 'cantidad': '10', 'delete': True},
        ], iniciales=1))
        self.assertFalse(formset.is_valid())
        # La regla vive en el formset, así que el mensaje está en los errores generales.
        self.assertIn('No se puede quitar', str(formset.non_form_errors()))

    def test_material_sin_consumo_si_se_puede_quitar(self):
        detalle = DetalleMaterial.objects.create(
            produccion=self.produccion, producto=self.tela, cantidad_requerida=Decimal('10'),
        )
        formset = self.formset(datos_formset([
            {'id': detalle.pk, 'producto': self.tela.pk, 'cantidad': '10', 'delete': True},
        ], iniciales=1))
        self.assertTrue(formset.is_valid(), formset.errors)


class ProduccionesVistasTests(TestCase):

    def setUp(self):
        self.operario = crear_usuario('op@taller.co', 'Operario')
        self.client.force_login(self.operario)
        self.tela = crear_producto('Tela algodón')
        self.boton = crear_producto('Botón nácar')
        self.terminado = crear_producto('Camisa', tipo=TipoProducto.PRODUCTO_TERMINADO)
        self.url_crear = reverse('inventario:produccion_crear')

    def test_visitante_anonimo_es_redirigido(self):
        self.client.logout()
        r = self.client.get(reverse('inventario:producciones'))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('accounts:login'), r['Location'])

    def test_operario_crea_produccion_con_materiales(self):
        datos = datos_produccion()
        datos.update(datos_formset([
            {'producto': self.tela.pk, 'cantidad': '40'},
            {'producto': self.boton.pk, 'cantidad': '20'},
        ]))
        r = self.client.post(self.url_crear, datos)
        produccion = Produccion.objects.get()
        self.assertRedirects(r, reverse('inventario:produccion_detalle', args=[produccion.pk]))
        self.assertEqual(produccion.usuario, self.operario)
        self.assertEqual(produccion.estado, EstadoProduccion.PENDIENTE)
        self.assertEqual(produccion.detalles.count(), 2)

    def test_produccion_sin_materiales_tambien_se_guarda(self):
        datos = datos_produccion()
        datos.update(datos_formset([]))
        self.client.post(self.url_crear, datos)
        self.assertEqual(Produccion.objects.get().detalles.count(), 0)

    def test_si_un_material_falla_no_se_guarda_nada(self):
        datos = datos_produccion()
        datos.update(datos_formset([
            {'producto': self.tela.pk, 'cantidad': '40'},
            {'producto': self.tela.pk, 'cantidad': '5'},  # repetido: el formulario falla
        ]))
        r = self.client.post(self.url_crear, datos)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Produccion.objects.exists())
        self.assertFalse(DetalleMaterial.objects.exists())

    def test_terminado_no_se_puede_usar_como_material(self):
        datos = datos_produccion()
        datos.update(datos_formset([{'producto': self.terminado.pk, 'cantidad': '1'}]))
        r = self.client.post(self.url_crear, datos)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Produccion.objects.exists())

    def test_editar_estado_y_materiales(self):
        produccion = crear_produccion(self.operario)
        detalle = DetalleMaterial.objects.create(
            produccion=produccion, producto=self.tela, cantidad_requerida=Decimal('10'),
        )
        datos = datos_produccion(estado=EstadoProduccion.EN_PROCESO, cantidad_solicitada='25')
        datos.update(datos_formset([
            {'id': detalle.pk, 'producto': self.tela.pk, 'cantidad': '12'},
            {'producto': self.boton.pk, 'cantidad': '30'},
        ], iniciales=1))
        r = self.client.post(reverse('inventario:produccion_editar', args=[produccion.pk]), datos)
        self.assertEqual(r.status_code, 302)
        produccion.refresh_from_db()
        self.assertEqual(produccion.estado, EstadoProduccion.EN_PROCESO)
        self.assertEqual(produccion.cantidad_solicitada, 25)
        self.assertEqual(produccion.detalles.count(), 2)

    def test_quitar_material_con_consumo_muestra_error_al_editar(self):
        produccion = crear_produccion(self.operario)
        detalle = DetalleMaterial.objects.create(
            produccion=produccion, producto=self.tela, cantidad_requerida=Decimal('10'),
        )
        registrar_movimiento(
            producto=self.tela, usuario=self.operario, tipo=TipoMovimiento.SALIDA,
            cantidad=Decimal('2'), motivo='Corte', produccion=produccion,
        )
        datos = datos_produccion()
        datos.update(datos_formset([
            {'id': detalle.pk, 'producto': self.tela.pk, 'cantidad': '10', 'delete': True},
        ], iniciales=1))
        r = self.client.post(reverse('inventario:produccion_editar', args=[produccion.pk]), datos)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(DetalleMaterial.objects.filter(pk=detalle.pk).exists())

    def test_no_existe_ruta_para_borrar_producciones(self):
        produccion = crear_produccion(self.operario)
        r = self.client.post(f'/inventario/producciones/{produccion.pk}/borrar/')
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Produccion.objects.filter(pk=produccion.pk).exists())

    def test_usuario_sin_permisos_no_puede_crear(self):
        Rol.objects.get_or_create(nombre_rol='Invitado', defaults={'descripcion': 'Sin permisos.'})
        invitado = crear_usuario('inv@taller.co', 'Invitado', 'Invitado')
        self.client.force_login(invitado)
        self.assertEqual(self.client.get(self.url_crear).status_code, 403)

    def test_administrador_puede_gestionar_producciones(self):
        admin = crear_usuario('admin@taller.co', 'Admin', ROL_ADMINISTRADOR)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.url_crear).status_code, 200)


class ListaYFichaTests(TestCase):

    def setUp(self):
        self.operario = crear_usuario('op@taller.co', 'Operario')
        self.client.force_login(self.operario)
        self.tela = crear_producto('Tela algodón')
        self.pendiente = crear_produccion(self.operario, descripcion='Camisas de algodón')
        self.terminada = crear_produccion(
            self.operario, descripcion='Pantalones jean', tipo='Reparación',
            estado=EstadoProduccion.TERMINADA,
        )

    def test_lista_muestra_producciones(self):
        r = self.client.get(reverse('inventario:producciones'))
        self.assertContains(r, 'Camisas de algodón')
        self.assertContains(r, 'Pantalones jean')

    def test_filtro_por_estado(self):
        r = self.client.get(reverse('inventario:producciones'), {'estado': EstadoProduccion.TERMINADA})
        pks = [p.pk for p in r.context['producciones']]
        self.assertEqual(pks, [self.terminada.pk])

    def test_busqueda_sin_tildes_en_la_descripcion(self):
        r = self.client.get(reverse('inventario:producciones'), {'q': 'ALGODON'})
        self.assertEqual([p.pk for p in r.context['producciones']], [self.pendiente.pk])

    def test_busqueda_sin_resultados(self):
        r = self.client.get(reverse('inventario:producciones'), {'q': 'xyz'})
        self.assertContains(r, 'No hay producciones con estos filtros')

    def test_ficha_calcula_progreso_y_marca_exceso(self):
        DetalleMaterial.objects.create(
            produccion=self.pendiente, producto=self.tela, cantidad_requerida=Decimal('10'),
        )
        registrar_movimiento(
            producto=self.tela, usuario=self.operario, tipo=TipoMovimiento.SALIDA,
            cantidad=Decimal('4'), motivo='Corte', produccion=self.pendiente,
        )
        r = self.client.get(reverse('inventario:produccion_detalle', args=[self.pendiente.pk]))
        material = r.context['materiales'][0]
        self.assertEqual(material['progreso'], 40)
        self.assertEqual(material['pendiente'], Decimal('6'))
        self.assertFalse(material['excedido'])

    def test_progreso_no_pasa_de_cien_pero_marca_exceso(self):
        detalle = DetalleMaterial.objects.create(
            produccion=self.pendiente, producto=self.tela, cantidad_requerida=Decimal('5'),
        )
        registrar_movimiento(
            producto=self.tela, usuario=self.operario, tipo=TipoMovimiento.SALIDA,
            cantidad=Decimal('8'), motivo='Corte', produccion=self.pendiente,
        )
        r = self.client.get(reverse('inventario:produccion_detalle', args=[self.pendiente.pk]))
        material = r.context['materiales'][0]
        self.assertEqual(material['progreso'], 100)
        self.assertTrue(material['excedido'])
        self.assertEqual(material['pendiente'], Decimal('0'))

    def test_ficha_lista_los_movimientos_de_la_produccion(self):
        registrar_movimiento(
            producto=self.tela, usuario=self.operario, tipo=TipoMovimiento.SALIDA,
            cantidad=Decimal('2'), motivo='Corte lote 3', produccion=self.pendiente,
        )
        r = self.client.get(reverse('inventario:produccion_detalle', args=[self.pendiente.pk]))
        self.assertContains(r, 'Corte lote 3')

    def test_ficha_ofrece_registrar_salida_prellenada(self):
        r = self.client.get(reverse('inventario:produccion_detalle', args=[self.pendiente.pk]))
        self.assertContains(r, f'{reverse("inventario:salida")}?produccion={self.pendiente.pk}')

    def test_formulario_de_salida_recibe_la_produccion(self):
        r = self.client.get(reverse('inventario:salida'), {'produccion': self.pendiente.pk})
        self.assertEqual(r.context['form'].initial['produccion'], self.pendiente.pk)

    def test_produccion_inexistente_responde_404(self):
        r = self.client.get(reverse('inventario:produccion_detalle', args=[9999]))
        self.assertEqual(r.status_code, 404)

"""Pruebas de reportes y exportaciones (Fase 6)."""
import csv
from datetime import datetime
from decimal import Decimal
from io import StringIO

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ROL_OPERARIO, Rol, Usuario

from .exportacion import celda_segura, generar_pdf
from .models import MovimientoInventario, Producto, TipoMovimiento, TipoProducto
from .reportes import descripcion_filtros, generar_reporte, puede_ver_reporte
from .services import registrar_movimiento

PASSWORD = 'Clave-Segura-2026'
SIN_FILTROS = {'q': '', 'tipo_material': '', 'estado': '', 'desde': None, 'hasta': None}


def crear_usuario(correo, nombre, nombre_rol=ROL_OPERARIO):
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


def movimiento(producto, usuario, tipo, cantidad, fecha=None):
    mov = registrar_movimiento(
        producto=producto, usuario=usuario, tipo=tipo, cantidad=Decimal(cantidad), motivo='Prueba',
    )
    if fecha:
        MovimientoInventario.objects.filter(pk=mov.pk).update(
            fecha=timezone.make_aware(datetime.combine(fecha, datetime.min.time().replace(hour=12))),
        )
    return mov


class DatosDeReportesTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario('op@taller.co', 'Operario')
        self.algodon = crear_producto('Tela algodón', existencias='3', stock_minimo='5')
        self.hilo = crear_producto('Hilo poliéster', existencias='50', stock_minimo='5')
        self.inactivo = crear_producto('Botón viejo', existencias='0', estado='inactivo')
        self.camisa = crear_producto('Camisa básica', tipo=TipoProducto.PRODUCTO_TERMINADO)

    def filtros(self, **cambios):
        datos = dict(SIN_FILTROS)
        datos.update(cambios)
        return datos

    def test_existencias_marca_alerta_solo_en_activos(self):
        reporte = generar_reporte('existencias', self.filtros())
        alertas = {f['valores'][0]: f['alerta'] for f in reporte['filas']}
        self.assertTrue(alertas['Tela algodón'])
        self.assertFalse(alertas['Hilo poliéster'])
        self.assertFalse(alertas['Botón viejo'])  # inactivo: sin alerta aunque tenga 0

    def test_existencias_resumen(self):
        reporte = generar_reporte('existencias', self.filtros())
        resumen = dict(reporte['resumen'])
        self.assertEqual(resumen['Productos'], 4)
        # Tela (3 <= 5) y camisa (0 <= 5) están activas y bajo mínimo. El botón inactivo no cuenta.
        self.assertEqual(resumen['Con stock bajo'], 2)
        self.assertEqual(resumen['Sin existencias'], 2)  # botón viejo y camisa

    def test_filtro_de_texto_sin_tildes(self):
        reporte = generar_reporte('existencias', self.filtros(q='ALGODON'))
        self.assertEqual([f['valores'][0] for f in reporte['filas']], ['Tela algodón'])

    def test_filtro_por_tipo_y_estado(self):
        terminados = generar_reporte('existencias', self.filtros(tipo_material=TipoProducto.PRODUCTO_TERMINADO))
        self.assertEqual(len(terminados['filas']), 1)
        inactivos = generar_reporte('catalogo', self.filtros(estado='inactivo'))
        self.assertEqual([f['valores'][0] for f in inactivos['filas']], ['Botón viejo'])

    def test_movimientos_calcula_entradas_salidas_y_balance(self):
        movimiento(self.hilo, self.usuario, TipoMovimiento.ENTRADA, '20')
        movimiento(self.hilo, self.usuario, TipoMovimiento.SALIDA, '5')
        movimiento(self.hilo, self.usuario, TipoMovimiento.SALIDA, '2.5')

        reporte = generar_reporte('movimientos', self.filtros())
        fila = next(f['valores'] for f in reporte['filas'] if f['valores'][0] == 'Hilo poliéster')
        self.assertEqual(fila[3:], ['20', '7.5', '12.5', '3'])

    def test_movimientos_excluye_productos_sin_movimientos(self):
        movimiento(self.hilo, self.usuario, TipoMovimiento.ENTRADA, '1')
        reporte = generar_reporte('movimientos', self.filtros())
        self.assertEqual([f['valores'][0] for f in reporte['filas']], ['Hilo poliéster'])

    def test_movimientos_filtra_por_fechas(self):
        movimiento(self.hilo, self.usuario, TipoMovimiento.ENTRADA, '10', fecha=datetime(2026, 1, 5).date())
        movimiento(self.hilo, self.usuario, TipoMovimiento.ENTRADA, '4', fecha=datetime(2026, 3, 9).date())

        enero = generar_reporte('movimientos', self.filtros(desde=datetime(2026, 1, 1).date(),
                                                            hasta=datetime(2026, 1, 31).date()))
        self.assertEqual(enero['filas'][0]['valores'][3], '10')

        todo = generar_reporte('movimientos', self.filtros())
        self.assertEqual(todo['filas'][0]['valores'][3], '14')

    def test_catalogo_no_incluye_existencias(self):
        reporte = generar_reporte('catalogo', self.filtros())
        self.assertNotIn('Existencias', reporte['encabezados'])
        self.assertEqual(len(reporte['filas']), 4)

    def test_tipo_desconocido_se_rechaza(self):
        with self.assertRaises(ValueError):
            generar_reporte('secreto', self.filtros())

    def test_descripcion_de_filtros(self):
        texto = descripcion_filtros(self.filtros(q='lino', tipo_material='insumo', estado='activo'))
        self.assertIn('Texto: "lino"', texto)
        self.assertIn('Material: Insumo', texto)
        self.assertIn('Estado: Activo', texto)
        self.assertEqual(descripcion_filtros(self.filtros()), 'Sin filtros')


class SeguridadDeExportacionTests(TestCase):

    def test_celdas_con_formulas_se_neutralizan(self):
        self.assertEqual(celda_segura('=HYPERLINK("http://x")'), "'=HYPERLINK(\"http://x\")")
        self.assertEqual(celda_segura('+cmd'), "'+cmd")
        self.assertEqual(celda_segura('@SUM(A1)'), "'@SUM(A1)")
        self.assertEqual(celda_segura('-texto'), "'-texto")

    def test_numeros_negativos_y_texto_normal_no_se_alteran(self):
        self.assertEqual(celda_segura('-3.00'), '-3.00')
        self.assertEqual(celda_segura('Tela algodón'), 'Tela algodón')
        self.assertEqual(celda_segura('12.50'), '12.50')
        self.assertEqual(celda_segura(''), '')

    def test_nombre_malicioso_queda_neutralizado_en_el_csv(self):
        usuario = crear_usuario('op@taller.co', 'Operario')
        crear_producto('=1+1', existencias='2')
        self.client.force_login(usuario)
        r = self.client.get(reverse('inventario:exportar_reporte', args=['csv']), {'tipo': 'existencias'})
        contenido = r.content.decode('utf-8-sig')
        self.assertIn("'=1+1", contenido)
        self.assertNotIn(';=1+1;', contenido)


class CsvTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario('op@taller.co', 'Operario')
        self.client.force_login(self.usuario)
        crear_producto('Tela algodón', existencias='3', stock_minimo='5')
        crear_producto('Hilo poliéster', existencias='50', stock_minimo='5')

    def test_csv_con_bom_separador_y_encabezados(self):
        r = self.client.get(reverse('inventario:exportar_reporte', args=['csv']), {'tipo': 'existencias'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="gestex_existencias_', r['Content-Disposition'])
        self.assertTrue(r.content.startswith(b'\xef\xbb\xbf'))

        filas = list(csv.reader(StringIO(r.content.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(filas[0][0], 'Producto')
        self.assertEqual(len(filas), 3)  # encabezado + 2 productos
        self.assertIn('Tela algodón', [f[0] for f in filas[1:]])

    def test_csv_aplica_los_mismos_filtros_que_la_pantalla(self):
        r = self.client.get(reverse('inventario:exportar_reporte', args=['csv']),
                            {'tipo': 'existencias', 'q': 'hilo'})
        filas = list(csv.reader(StringIO(r.content.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[1][0], 'Hilo poliéster')

    def test_csv_de_movimientos(self):
        producto = Producto.objects.get(nombre='Hilo poliéster')
        movimiento(producto, self.usuario, TipoMovimiento.SALIDA, '4')
        r = self.client.get(reverse('inventario:exportar_reporte', args=['csv']), {'tipo': 'movimientos'})
        filas = list(csv.reader(StringIO(r.content.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(filas[0][:3], ['Producto', 'Tipo', 'Unidad'])
        self.assertEqual(filas[1][0], 'Hilo poliéster')
        self.assertEqual(filas[1][4], '4')  # salidas


class PdfTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario('op@taller.co', 'Operario')
        self.client.force_login(self.usuario)

    def test_pdf_se_descarga_con_el_tipo_correcto(self):
        crear_producto('Tela algodón', existencias='3')
        r = self.client.get(reverse('inventario:exportar_reporte', args=['pdf']), {'tipo': 'existencias'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="gestex_existencias_', r['Content-Disposition'])
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_pdf_sin_datos_tambien_se_genera(self):
        r = self.client.get(reverse('inventario:exportar_reporte', args=['pdf']), {'tipo': 'catalogo'})
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_nombres_con_etiquetas_no_rompen_el_pdf(self):
        crear_producto('<b>Tela</b> & <i>hilo</i> <<>>', existencias='1')
        r = self.client.get(reverse('inventario:exportar_reporte', args=['pdf']), {'tipo': 'existencias'})
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_generar_pdf_directo_con_texto_extremo(self):
        reporte = {
            'titulo': 'Prueba <script>', 'encabezados': ['A & B'],
            'filas': [{'valores': ['x' * 500], 'alerta': True}],
            'resumen': [('Total', 1)], 'nota': 'Nota & más',
            'numericas': [],
        }
        pdf = generar_pdf(reporte, 'Filtro <x>', timezone.now())
        self.assertTrue(pdf.startswith(b'%PDF'))


class PantallaDeReportesTests(TestCase):

    def setUp(self):
        self.usuario = crear_usuario('op@taller.co', 'Operario')
        self.client.force_login(self.usuario)
        self.url = reverse('inventario:reportes')
        crear_producto('Tela algodón', existencias='3')

    def test_visitante_anonimo_es_redirigido(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.get(reverse('inventario:exportar_reporte', args=['csv'])).status_code, 302)

    def test_carga_el_reporte_de_existencias_por_defecto(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['reporte']['tipo'], 'existencias')
        self.assertContains(r, 'Tela algodón')

    def test_fechas_invertidas_muestran_error(self):
        r = self.client.get(self.url, {'tipo': 'movimientos', 'desde': '2026-05-01', 'hasta': '2026-01-01'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'La fecha final no puede ser anterior a la inicial.')
        self.assertIsNone(r.context['reporte'])

    def test_exportacion_con_filtros_invalidos_no_descarga_nada(self):
        r = self.client.get(reverse('inventario:exportar_reporte', args=['csv']), {'tipo': 'desconocido'})
        self.assertEqual(r.status_code, 400)

    def test_formato_inexistente_responde_404(self):
        self.assertEqual(self.client.get(reverse('inventario:exportar_reporte', args=['xlsx'])).status_code, 404)

    def test_pantalla_enlaza_las_exportaciones_con_los_mismos_filtros(self):
        r = self.client.get(self.url, {'q': 'algodon'})
        self.assertContains(r, reverse('inventario:exportar_reporte', args=['csv']) + '?q=algodon')
        self.assertContains(r, reverse('inventario:exportar_reporte', args=['pdf']) + '?q=algodon')

    def test_paginacion_de_la_pantalla(self):
        for i in range(55):
            crear_producto(f'Producto {i:02d}')
        r = self.client.get(self.url)
        self.assertEqual(len(r.context['pagina'].object_list), 50)
        self.assertEqual(r.context['pagina'].paginator.num_pages, 2)

    def test_usuario_sin_permisos_recibe_403(self):
        Rol.objects.get_or_create(nombre_rol='Invitado', defaults={'descripcion': 'Sin permisos.'})
        invitado = crear_usuario('invitado@taller.co', 'Invitado', 'Invitado')
        self.client.force_login(invitado)
        self.assertEqual(self.client.get(self.url, {'tipo': 'existencias'}).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('inventario:exportar_reporte', args=['pdf']), {'tipo': 'existencias'}).status_code,
            403,
        )

    def test_permiso_del_reporte_de_movimientos(self):
        invitado = crear_usuario('x@taller.co', 'X', 'Operario')
        self.assertTrue(puede_ver_reporte(invitado, 'movimientos'))
        Rol.objects.get_or_create(nombre_rol='Invitado', defaults={'descripcion': 'Sin permisos.'})
        sin_permisos = crear_usuario('y@taller.co', 'Y', 'Invitado')
        self.assertFalse(puede_ver_reporte(sin_permisos, 'movimientos'))
        self.assertFalse(puede_ver_reporte(sin_permisos, 'existencias'))

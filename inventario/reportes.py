"""
Reportes de inventario (RF08, RF10).

Cada reporte se calcula una sola vez en generar_reporte(). La misma estructura
la usan la pantalla, la exportación a CSV y la exportación a PDF, así los tres
muestran siempre los mismos datos.

Estructura de un reporte (diccionario):
    tipo          clave del reporte ('existencias', 'movimientos' o 'catalogo')
    titulo        nombre legible
    encabezados   lista de títulos de columna
    filas         lista de {'valores': [...], 'alerta': bool}
    resumen       lista de (etiqueta, valor) para los indicadores
    nota          texto aclaratorio
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum

from .busqueda import campo_normalizado, normalizar_texto
from .models import EstadoProducto, MovimientoInventario, Producto, TipoMovimiento, TipoProducto

TIPOS_REPORTE = {
    'existencias': 'Existencias actuales',
    'movimientos': 'Movimientos por producto',
    'catalogo': 'Catálogo de productos',
}

# Permisos que necesita cada reporte. El de movimientos también muestra el historial.
PERMISOS_REPORTE = {
    'existencias': ('inventario.view_producto',),
    'catalogo': ('inventario.view_producto',),
    'movimientos': ('inventario.view_producto', 'inventario.view_movimientoinventario'),
}


def puede_ver_reporte(usuario, tipo):
    return usuario.has_perms(PERMISOS_REPORTE[tipo])


def _productos_filtrados(filtros):
    """Productos que cumplen los filtros comunes: texto, tipo de material y estado."""
    queryset = Producto.objects.all()

    texto = filtros.get('q', '').strip()
    if texto:
        termino = normalizar_texto(texto)
        queryset = queryset.annotate(
            nombre_busqueda=campo_normalizado('nombre'),
            descripcion_busqueda=campo_normalizado('descripcion'),
        ).filter(Q(nombre_busqueda__contains=termino) | Q(descripcion_busqueda__contains=termino))

    if filtros.get('tipo_material'):
        queryset = queryset.filter(tipo=filtros['tipo_material'])
    if filtros.get('estado'):
        queryset = queryset.filter(estado=filtros['estado'])
    return queryset.order_by('nombre')


def _descripcion_tipo(producto):
    return producto.get_tipo_display()


def _nombre_tipo(valor):
    return dict(TipoProducto.choices).get(valor, valor)


def _reporte_existencias(filtros):
    productos = list(_productos_filtrados(filtros))
    filas = []
    for p in productos:
        alerta = p.estado == EstadoProducto.ACTIVO and p.en_alerta
        filas.append({
            'valores': [
                p.nombre, _descripcion_tipo(p), str(p.cantidad_actual), p.unidad_medida,
                str(p.stock_minimo), p.get_estado_display(), 'Sí' if alerta else 'No',
            ],
            'alerta': alerta,
        })
    return {
        'tipo': 'existencias',
        'titulo': 'Existencias actuales',
        'encabezados': ['Producto', 'Tipo', 'Existencias', 'Unidad', 'Stock mínimo', 'Estado', 'Stock bajo'],
        'numericas': [2, 4],
        'filas': filas,
        'resumen': [
            ('Productos', len(productos)),
            ('Con stock bajo', sum(1 for f in filas if f['alerta'])),
            ('Sin existencias', sum(1 for p in productos if p.cantidad_actual == 0)),
        ],
        'nota': 'Las existencias son el saldo actual. Las filas en rojo tienen stock bajo.',
    }


def _reporte_movimientos(filtros):
    productos = list(_productos_filtrados(filtros))
    movimientos = MovimientoInventario.objects.filter(producto__in=productos)

    desde = filtros.get('desde')
    hasta = filtros.get('hasta')
    if desde:
        movimientos = movimientos.filter(fecha__date__gte=desde)
    if hasta:
        movimientos = movimientos.filter(fecha__date__lte=hasta)

    agregados = (
        movimientos.values('producto_id', 'producto__nombre', 'producto__unidad_medida', 'producto__tipo')
        .annotate(
            entradas=Sum('cantidad', filter=Q(tipo_movimiento=TipoMovimiento.ENTRADA)),
            salidas=Sum('cantidad', filter=Q(tipo_movimiento=TipoMovimiento.SALIDA)),
            numero=Count('id'),
        )
        .order_by('producto__nombre')
    )

    filas = []
    total_movimientos = 0
    for fila in agregados:
        entradas = fila['entradas'] or Decimal('0')
        salidas = fila['salidas'] or Decimal('0')
        balance = entradas - salidas
        total_movimientos += fila['numero']
        filas.append({
            'valores': [
                fila['producto__nombre'],
                _nombre_tipo(fila['producto__tipo']),
                fila['producto__unidad_medida'],
                str(entradas),
                str(salidas),
                str(balance),
                str(fila['numero']),
            ],
            'alerta': False,
        })

    periodo = 'Todo el historial'
    if desde or hasta:
        periodo = f'Desde {desde:%d/%m/%Y}' if desde else 'Desde el inicio'
        periodo += f' hasta {hasta:%d/%m/%Y}' if hasta else ' hasta hoy'

    return {
        'tipo': 'movimientos',
        'titulo': 'Movimientos por producto',
        'encabezados': ['Producto', 'Tipo', 'Unidad', 'Entradas', 'Salidas', 'Balance', 'Movimientos'],
        'numericas': [3, 4, 5, 6],
        'filas': filas,
        'resumen': [
            ('Productos con movimientos', len(filas)),
            ('Movimientos registrados', total_movimientos),
            ('Periodo', periodo),
        ],
        'nota': (
            'Balance = entradas menos salidas en el periodo, en la unidad de cada producto. '
            'Un balance negativo significa que salió más de lo que entró en ese periodo.'
        ),
    }


def _reporte_catalogo(filtros):
    productos = list(_productos_filtrados(filtros))
    filas = [
        {
            'valores': [
                p.nombre, _descripcion_tipo(p), p.unidad_medida, str(p.stock_minimo),
                p.get_estado_display(), p.descripcion or '—',
            ],
            'alerta': False,
        }
        for p in productos
    ]
    return {
        'tipo': 'catalogo',
        'titulo': 'Catálogo de productos',
        'encabezados': ['Producto', 'Tipo', 'Unidad', 'Stock mínimo', 'Estado', 'Descripción'],
        'numericas': [3],
        'filas': filas,
        'resumen': [
            ('Productos', len(productos)),
            ('Activos', sum(1 for p in productos if p.estado == EstadoProducto.ACTIVO)),
            ('Inactivos', sum(1 for p in productos if p.estado == EstadoProducto.INACTIVO)),
        ],
        'nota': 'Listado de productos e insumos registrados, sin existencias.',
    }


GENERADORES = {
    'existencias': _reporte_existencias,
    'movimientos': _reporte_movimientos,
    'catalogo': _reporte_catalogo,
}


def generar_reporte(tipo, filtros):
    """Calcula el reporte pedido con los filtros validados (diccionario cleaned_data)."""
    if tipo not in GENERADORES:
        raise ValueError(f'Tipo de reporte desconocido: {tipo}')
    return GENERADORES[tipo](filtros)


def descripcion_filtros(filtros):
    """Texto legible con los filtros aplicados (para el PDF y la pantalla)."""
    partes = []
    if filtros.get('q'):
        partes.append(f'Texto: "{filtros["q"]}"')
    if filtros.get('tipo_material'):
        partes.append('Material: ' + _nombre_tipo(filtros['tipo_material']))
    if filtros.get('estado'):
        partes.append('Estado: ' + dict(EstadoProducto.choices)[filtros['estado']])
    if filtros.get('desde'):
        partes.append(f'Desde: {filtros["desde"]:%d/%m/%Y}')
    if filtros.get('hasta'):
        partes.append(f'Hasta: {filtros["hasta"]:%d/%m/%Y}')
    return ' · '.join(partes) if partes else 'Sin filtros'

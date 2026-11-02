from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from .busqueda import campo_normalizado, normalizar_texto
from .exportacion import respuesta_csv, respuesta_pdf
from .forms import (
    ConsumoProduccionForm,
    DetalleMaterialFormSet,
    HistorialFiltroForm,
    MovimientoForm,
    ProduccionForm,
    ProductoForm,
    ReporteFiltroForm,
)
from .models import (
    EstadoProducto,
    EstadoProduccion,
    MovimientoInventario,
    Produccion,
    Producto,
    TipoMovimiento,
    TipoProducto,
)
from .reportes import TIPOS_REPORTE, descripcion_filtros, generar_reporte, puede_ver_reporte
from .services import (
    ErrorMovimiento,
    finalizar_produccion,
    registrar_consumo_produccion,
    registrar_movimiento,
)

# Todas las vistas exigen sesión (LoginRequiredMixin) y un permiso del modelo
# (PermissionRequiredMixin). Los permisos por rol están en accounts/permisos.py.
# Así, aunque alguien escriba la URL a mano, no puede ver ni cambiar datos sin permiso.


class ProductoListaView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Listado de productos con búsqueda y filtros (RF02, RF09)."""

    permission_required = 'inventario.view_producto'
    model = Producto
    template_name = 'inventario/producto_lista.html'
    context_object_name = 'productos'
    paginate_by = 15

    def get_queryset(self):
        """Aplica los filtros de la URL (búsqueda, tipo y estado) y ordena por nombre."""
        # Se leen y limpian los filtros de la URL. Los valores no válidos se ignoran
        # para que una URL manipulada no pueda filtrar por valores inexistentes.
        self.busqueda = self.request.GET.get('q', '').strip()[:100]
        self.tipo = self.request.GET.get('tipo', '')
        self.estado = self.request.GET.get('estado', '')

        queryset = Producto.objects.all()
        if self.busqueda:
            # Se compara sin mayúsculas ni tildes: "algodon" encuentra "Algodón".
            termino = normalizar_texto(self.busqueda)
            queryset = queryset.annotate(
                nombre_busqueda=campo_normalizado('nombre'),
                descripcion_busqueda=campo_normalizado('descripcion'),
            ).filter(
                Q(nombre_busqueda__contains=termino) | Q(descripcion_busqueda__contains=termino)
            )
        if self.tipo in TipoProducto.values:
            queryset = queryset.filter(tipo=self.tipo)
        if self.estado in EstadoProducto.values:
            queryset = queryset.filter(estado=self.estado)
        return queryset.order_by('nombre')

    def get_context_data(self, **kwargs):
        """Agrega filtros activos, contadores de alerta y permisos para mostrar los botones."""
        context = super().get_context_data(**kwargs)

        # Parámetros de búsqueda sin "page", para conservarlos al cambiar de página.
        # Los enlaces de paginación usan esta cadena para no perder el filtro.
        parametros = self.request.GET.copy()
        parametros.pop('page', None)

        context.update({
            'busqueda': self.busqueda,
            'tipo_seleccionado': self.tipo,
            'estado_seleccionado': self.estado,
            'tipos': TipoProducto.choices,
            'estados': EstadoProducto.choices,
            'parametros_busqueda': parametros.urlencode(),
            'hay_filtros': bool(self.busqueda or self.tipo or self.estado),
            # Productos activos cuyas existencias llegaron al mínimo.
            'total_en_alerta': Producto.objects.filter(
                estado=EstadoProducto.ACTIVO,
                cantidad_actual__lte=F('stock_minimo'),
            ).count(),
            'total_productos': Producto.objects.count(),
            'puede_crear': self.request.user.has_perm('inventario.add_producto'),
            'puede_editar': self.request.user.has_perm('inventario.change_producto'),
        })
        return context


class ProductoDetalleView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Ficha de un producto con sus últimos movimientos."""

    permission_required = 'inventario.view_producto'
    model = Producto
    template_name = 'inventario/producto_detalle.html'
    context_object_name = 'producto'

    def get_context_data(self, **kwargs):
        """Agrega los últimos movimientos y decide qué acciones mostrar según el permiso del usuario."""
        context = super().get_context_data(**kwargs)
        # select_related evita consultas extra al mostrar usuario y producción de cada fila.
        # Solo se muestran 10 movimientos; el historial completo tiene su propia pantalla.
        context['ultimos_movimientos'] = (
            MovimientoInventario.objects.filter(producto=self.object)
            .select_related('usuario', 'produccion')[:10]
        )
        context['puede_editar'] = self.request.user.has_perm('inventario.change_producto')
        context['puede_movimientos'] = self.request.user.has_perm('inventario.add_movimientoinventario')
        return context


class ProductoCrearView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Registrar un insumo o producto terminado (RF01)."""

    permission_required = 'inventario.add_producto'
    model = Producto
    form_class = ProductoForm
    template_name = 'inventario/producto_form.html'
    success_url = reverse_lazy('inventario:lista')

    def get_context_data(self, **kwargs):
        """Pone el título 'Nuevo producto' en la plantilla."""
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Nuevo producto'
        return context

    def form_valid(self, form):
        """Guarda el producto y avisa que sus existencias empiezan en 0 (se cargan con entradas)."""
        messages.success(
            self.request,
            f'Producto "{form.instance.nombre}" registrado. Sus existencias empiezan en 0.',
        )
        return super().form_valid(form)


class ProductoEditarView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Modificar datos de un producto (RF06). No cambia las existencias."""

    permission_required = 'inventario.change_producto'
    model = Producto
    form_class = ProductoForm
    template_name = 'inventario/producto_form.html'
    context_object_name = 'producto'

    def get_context_data(self, **kwargs):
        """Pone en el título el nombre del producto que se está editando."""
        context = super().get_context_data(**kwargs)
        context['titulo'] = f'Editar: {self.object.nombre}'
        return context

    def get_success_url(self):
        """Tras guardar, vuelve a la ficha del producto."""
        return reverse('inventario:detalle', args=[self.object.pk])

    def form_valid(self, form):
        """Guarda los cambios y muestra un mensaje de confirmación."""
        messages.success(self.request, f'Producto "{form.instance.nombre}" actualizado.')
        return super().form_valid(form)


class MovimientoBaseView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """
    Base para registrar entradas y salidas.

    Toda la lógica de existencias está en services.registrar_movimiento();
    esta vista solo recibe el formulario, llama al servicio y muestra el resultado.
    """

    permission_required = 'inventario.add_movimientoinventario'
    form_class = MovimientoForm
    template_name = 'inventario/movimiento_form.html'
    tipo = None  # lo define cada subclase: TipoMovimiento.ENTRADA o SALIDA

    def get_form_kwargs(self):
        """Pasa el tipo de movimiento al formulario."""
        kwargs = super().get_form_kwargs()
        kwargs['tipo'] = self.tipo
        return kwargs

    def get_initial(self):
        """Prellena producto o producción si llegan por la URL (por ejemplo, desde su ficha)."""
        # Permite abrir el formulario con el producto ya elegido: ?producto=12
        # Se valida con isdigit() para que un valor raro en la URL no provoque un error.
        initial = super().get_initial()
        producto_pk = self.request.GET.get('producto')
        if producto_pk and producto_pk.isdigit():
            initial['producto'] = int(producto_pk)
        # Desde una producción: ?produccion=5 deja la producción ya relacionada.
        produccion_pk = self.request.GET.get('produccion')
        if produccion_pk and produccion_pk.isdigit():
            initial['produccion'] = int(produccion_pk)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        es_entrada = self.tipo == TipoMovimiento.ENTRADA
        context.update({
            'es_entrada': es_entrada,
            'titulo': 'Registrar entrada' if es_entrada else 'Registrar salida',
            'descripcion': (
                'Úsala cuando llega material al taller: compras, devoluciones o ajustes positivos.'
                if es_entrada else
                'Úsala cuando el material sale: consumo en producción, desperdicio o ventas.'
            ),
        })
        return context

    def form_valid(self, form):
        """Delega el movimiento al servicio y devuelve al detalle del producto con un mensaje."""
        datos = form.cleaned_data
        try:
            # El servicio valida el stock y guarda el movimiento dentro de una transacción.
            registrar_movimiento(
                producto=datos['producto'],
                usuario=self.request.user,
                tipo=self.tipo,
                cantidad=datos['cantidad'],
                motivo=datos['motivo'],
                produccion=datos.get('produccion'),
            )
        except ErrorMovimiento as error:
            # Error de negocio (por ejemplo, stock insuficiente): se muestra en el formulario.
            form.add_error(None, str(error))
            return self.form_invalid(form)

        # Se usa la cantidad ya actualizada por el servicio para que el mensaje sea exacto.
        producto = datos['producto']
        if self.tipo == TipoMovimiento.ENTRADA:
            mensaje = f'Entrada registrada. Ahora hay {producto.cantidad_actual} {producto.unidad_medida} de "{producto.nombre}".'
        else:
            mensaje = f'Salida registrada. Quedan {producto.cantidad_actual} {producto.unidad_medida} de "{producto.nombre}".'
        messages.success(self.request, mensaje)
        return redirect(reverse('inventario:detalle', args=[producto.pk]))


class MovimientoEntradaView(MovimientoBaseView):
    """Formulario para registrar una entrada de material (suma existencias)."""

    tipo = TipoMovimiento.ENTRADA


class MovimientoSalidaView(MovimientoBaseView):
    """Formulario para registrar una salida de material (resta existencias)."""

    tipo = TipoMovimiento.SALIDA


class HistorialMovimientosView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Historial de entradas y salidas, con filtros combinables y paginación (RF07, RF09).
    El historial solo se consulta: nunca se edita ni se borra desde aquí.
    """

    permission_required = 'inventario.view_movimientoinventario'
    model = MovimientoInventario
    template_name = 'inventario/historial.html'
    context_object_name = 'movimientos'
    paginate_by = 20

    def get_queryset(self):
        """Filtra los movimientos según los parámetros de la URL, ordenados del más reciente."""
        # Si algún filtro es inválido no se aplica ninguno: el formulario muestra el error
        # y el listado queda completo, para no mostrar resultados parciales engañosos.
        # El historial no se edita porque es el respaldo de las existencias: si se pudiera
        # cambiar, el inventario ya no podría explicarse con sus movimientos.
        self.form = HistorialFiltroForm(data=self.request.GET)
        filtros = self.form.cleaned_data if self.form.is_valid() else {}

        queryset = MovimientoInventario.objects.select_related('producto', 'usuario', 'produccion')

        # Producto ligado desde la ficha: ?producto=12
        self.producto_filtrado = None
        producto_pk = self.request.GET.get('producto', '')
        if producto_pk.isdigit():
            self.producto_filtrado = Producto.objects.filter(pk=int(producto_pk)).first()
            if self.producto_filtrado is not None:
                queryset = queryset.filter(producto=self.producto_filtrado)

        busqueda = filtros.get('q', '').strip()
        if busqueda:
            # Sin distinguir mayúsculas ni tildes, igual que en el inventario.
            queryset = queryset.annotate(
                nombre_busqueda=campo_normalizado('producto__nombre'),
            ).filter(nombre_busqueda__contains=normalizar_texto(busqueda))

        if filtros.get('tipo_material'):
            queryset = queryset.filter(producto__tipo=filtros['tipo_material'])
        if filtros.get('tipo_movimiento'):
            queryset = queryset.filter(tipo_movimiento=filtros['tipo_movimiento'])
        if filtros.get('desde'):
            queryset = queryset.filter(fecha__date__gte=filtros['desde'])
        if filtros.get('hasta'):
            queryset = queryset.filter(fecha__date__lte=filtros['hasta'])

        return queryset.order_by('-fecha', '-id')

    def get_context_data(self, **kwargs):
        """Agrega el formulario de filtros, el resumen de totales y los parámetros para paginar."""
        context = super().get_context_data(**kwargs)

        # Resumen del conjunto filtrado (no de la página actual).
        # Se calcula sobre todo el resultado, no solo sobre los 20 movimientos visibles.
        resumen = self.object_list.aggregate(
            total=Count('id'),
            entradas=Count('id', filter=Q(tipo_movimiento=TipoMovimiento.ENTRADA)),
            salidas=Count('id', filter=Q(tipo_movimiento=TipoMovimiento.SALIDA)),
        )

        parametros = self.request.GET.copy()
        parametros.pop('page', None)

        hay_filtros = any(
            self.request.GET.get(campo)
            for campo in ('q', 'tipo_material', 'tipo_movimiento', 'desde', 'hasta', 'producto')
        )

        context.update({
            'form': self.form,
            'resumen': resumen,
            'parametros_filtro': parametros.urlencode(),
            'hay_filtros': hay_filtros,
            'producto_filtrado': self.producto_filtrado,
        })
        return context


@login_required
@permission_required('inventario.change_producto', raise_exception=True)
@require_POST
def producto_cambiar_estado(request, pk):
    """
    Activa o desactiva un producto. Nunca lo borra: así el historial se conserva.
    Solo acepta POST para que un enlace externo no pueda cambiarlo.
    """
    producto = get_object_or_404(Producto, pk=pk)

    # Un producto inactivo deja de aparecer en los formularios de movimientos y listas de materiales,
    # pero sus movimientos anteriores siguen en el historial.
    if producto.estado == EstadoProducto.ACTIVO:
        producto.estado = EstadoProducto.INACTIVO
        messages.success(request, f'"{producto.nombre}" se desactivó. Su historial se conserva.')
    else:
        producto.estado = EstadoProducto.ACTIVO
        messages.success(request, f'"{producto.nombre}" se activó nuevamente.')

    producto.save(update_fields=['estado'])
    return redirect(reverse('inventario:lista'))


class ReportesView(LoginRequiredMixin, TemplateView):
    """Reportes en pantalla (RF08). Las exportaciones usan los mismos filtros."""

    template_name = 'inventario/reportes.html'
    filas_por_pagina = 50

    def get_context_data(self, **kwargs):
        """Genera el reporte pedido en la URL y lo pagina para mostrarlo en pantalla."""
        context = super().get_context_data(**kwargs)
        form = ReporteFiltroForm(data=self.request.GET)

        reporte = None
        pagina = None
        filtros_texto = ''
        if form.is_valid():
            tipo = form.cleaned_data['tipo']
            # No hay PermissionRequiredMixin en esta vista porque el permiso depende del tipo de reporte:
            # el de movimientos exige además el permiso de ver movimientos, los otros no.
            if not puede_ver_reporte(self.request.user, tipo):
                raise PermissionDenied
            reporte = generar_reporte(tipo, form.cleaned_data)
            pagina = Paginator(reporte['filas'], self.filas_por_pagina).get_page(
                self.request.GET.get('page'),
            )
            filtros_texto = descripcion_filtros(form.cleaned_data)

        # Parámetros para las exportaciones y la paginación, sin "page".
        parametros = self.request.GET.copy()
        parametros.pop('page', None)

        context.update({
            'form': form,
            'reporte': reporte,
            'pagina': pagina,
            'filtros_texto': filtros_texto,
            'tipos': TIPOS_REPORTE,
            'tipo_actual': form['tipo'].value() or 'existencias',
            'parametros': parametros.urlencode(),
            'puede_ver_movimientos': self.request.user.has_perm('inventario.view_movimientoinventario'),
        })
        return context


@login_required
def exportar_reporte(request, formato):
    """
    Descarga un reporte en CSV o PDF. Valida los mismos filtros que la pantalla
    y aplica el mismo permiso, así no se puede exportar más de lo que se ve.
    """
    # Cualquier otro formato se rechaza con 404 para no generar archivos inesperados.
    if formato not in ('csv', 'pdf'):
        raise Http404

    form = ReporteFiltroForm(data=request.GET)
    if not form.is_valid():
        return HttpResponseBadRequest('Los filtros del reporte no son válidos.')

    tipo = form.cleaned_data['tipo']
    if not puede_ver_reporte(request.user, tipo):
        raise PermissionDenied

    reporte = generar_reporte(tipo, form.cleaned_data)
    # La fecha y hora van en el nombre del archivo para distinguir las descargas.
    ahora = timezone.localtime()
    nombre = f'gestex_{tipo}_{ahora:%Y%m%d_%H%M}'

    if formato == 'csv':
        return respuesta_csv(reporte, nombre)
    return respuesta_pdf(reporte, descripcion_filtros(form.cleaned_data), ahora, nombre)


# ---------------------------------------------------------------------------
# Producciones
# ---------------------------------------------------------------------------

class ProduccionListaView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Listado de producciones con búsqueda y filtro por estado."""

    permission_required = 'inventario.view_produccion'
    model = Produccion
    template_name = 'inventario/produccion_lista.html'
    context_object_name = 'producciones'
    paginate_by = 15

    def get_queryset(self):
        """Filtra las producciones por texto y estado; las más recientes (por fecha de inicio) primero."""
        self.busqueda = self.request.GET.get('q', '').strip()[:100]
        self.estado = self.request.GET.get('estado', '')

        queryset = Produccion.objects.select_related('usuario')
        if self.busqueda:
            termino = normalizar_texto(self.busqueda)
            queryset = queryset.annotate(
                descripcion_busqueda=campo_normalizado('descripcion'),
                tipo_busqueda=campo_normalizado('tipo'),
            ).filter(
                Q(descripcion_busqueda__contains=termino) | Q(tipo_busqueda__contains=termino)
            )
        if self.estado in EstadoProduccion.values:
            queryset = queryset.filter(estado=self.estado)

        return queryset.annotate(total_materiales=Count('detalles')).order_by('-fecha_inicio', '-id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        parametros = self.request.GET.copy()
        parametros.pop('page', None)
        context.update({
            'busqueda': self.busqueda,
            'estado_seleccionado': self.estado,
            'estados': EstadoProduccion.choices,
            'parametros_busqueda': parametros.urlencode(),
            'hay_filtros': bool(self.busqueda or self.estado),
            'puede_crear': self.request.user.has_perm('inventario.add_produccion'),
            'puede_editar': self.request.user.has_perm('inventario.change_produccion'),
        })
        return context


class ProduccionDetalleView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Ficha de una producción: materiales, progreso y movimientos relacionados."""

    permission_required = 'inventario.view_produccion'
    model = Produccion
    template_name = 'inventario/produccion_detalle.html'
    context_object_name = 'produccion'

    def get_context_data(self, **kwargs):
        """Calcula, por cada material, cuánto falta y qué porcentaje se ha consumido."""
        context = super().get_context_data(**kwargs)
        materiales = []
        # El progreso se limita a 100 % y 'excedido' avisa si se consumió más de lo requerido.
        for detalle in self.object.detalles.select_related('producto').order_by('producto__nombre'):
            requerida = detalle.cantidad_requerida
            utilizada = detalle.cantidad_utilizada
            progreso = min(100, int(utilizada * 100 / requerida)) if requerida else 0
            materiales.append({
                'detalle': detalle,
                'pendiente': max(requerida - utilizada, Decimal('0')),
                'progreso': progreso,
                'excedido': utilizada > requerida,
            })

        context.update({
            'materiales': materiales,
            'movimientos': (
                MovimientoInventario.objects.filter(produccion=self.object)
                .select_related('producto', 'usuario')[:30]
            ),
            'puede_editar': self.request.user.has_perm('inventario.change_produccion'),
            'puede_movimientos': self.request.user.has_perm('inventario.add_movimientoinventario'),
        })
        return context


class ProduccionFormularioView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    Alta y edición de una producción con su lista de materiales.
    Los datos generales y las filas se validan juntos y se guardan en una sola transacción.
    """

    template_name = 'inventario/produccion_form.html'

    def get_produccion(self):
        """Devuelve la producción a editar; las subclases deciden si es nueva o existente."""
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        """Muestra el formulario vacío o con los datos actuales de la producción."""
        produccion = self.get_produccion()
        return self._responder(ProduccionForm(instance=produccion),
                               DetalleMaterialFormSet(instance=produccion), produccion)

    def post(self, request, *args, **kwargs):
        """Valida y guarda la producción junto con su lista de materiales."""
        produccion = self.get_produccion()
        form = ProduccionForm(request.POST, instance=produccion)
        formset = DetalleMaterialFormSet(request.POST, instance=produccion)

        if form.is_valid() and formset.is_valid():
            # Guardar y, si la producción queda Terminada, ingresar sus unidades al inventario:
            # todo en una sola transacción. Si el ingreso falla, no se guarda nada.
            # Así nunca queda una producción marcada como terminada sin sus unidades en el inventario.
            try:
                with transaction.atomic():
                    produccion = form.save()
                    formset.save()
                    movimiento = None
                    if produccion.estado == EstadoProduccion.TERMINADA:
                        movimiento = finalizar_produccion(produccion, request.user)
            except ErrorMovimiento as error:
                form.add_error(None, str(error))
            else:
                mensaje = f'Producción #{produccion.pk} guardada.'
                if movimiento is not None:
                    mensaje += (
                        f' Se ingresaron {movimiento.cantidad} {produccion.producto_terminado.unidad_medida} '
                        f'de "{produccion.producto_terminado.nombre}" al inventario.'
                    )
                messages.success(request, mensaje)
                return redirect(reverse('inventario:produccion_detalle', args=[produccion.pk]))

        return self._responder(form, formset, produccion)

    def _responder(self, form, formset, produccion):
        """Renderiza la plantilla con el formulario, el formset y las sugerencias de productos."""
        return render(self.request, self.template_name, {
            'form': form,
            'formset': formset,
            'produccion': produccion if produccion.pk else None,
            'titulo': f'Editar producción #{produccion.pk}' if produccion.pk else 'Nueva producción',
            # Sugerencias para el campo de producto terminado (datalist).
            'productos_terminados': Producto.objects.filter(
                tipo=TipoProducto.PRODUCTO_TERMINADO,
            ).order_by('nombre').values_list('nombre', flat=True),
        })


# Estados en los que la producción ya no admite consumos: su material ya quedó cerrado.
CONSUMO_CERRADO = (EstadoProduccion.TERMINADA, EstadoProduccion.CANCELADA)


class ProduccionConsumoView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """
    Registra de una vez el material utilizado en una producción.
    Una sola pantalla con una casilla por material, en lugar de una salida por cada insumo.
    """

    permission_required = 'inventario.add_movimientoinventario'
    form_class = ConsumoProduccionForm
    template_name = 'inventario/produccion_consumo.html'

    def get_produccion(self):
        """Busca la producción una sola vez por petición y la guarda en caché."""
        if not hasattr(self, '_produccion'):
            self._produccion = get_object_or_404(
                Produccion.objects.select_related('producto_terminado'), pk=self.kwargs['pk'],
            )
        return self._produccion

    def get(self, request, *args, **kwargs):
        """Muestra la pantalla de consumo, salvo que la producción ya esté cerrada."""
        if self.get_produccion().estado in CONSUMO_CERRADO:
            messages.info(request, 'Esta producción ya está cerrada; no admite más consumos.')
            return redirect(reverse('inventario:produccion_detalle', args=[self.kwargs['pk']]))
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        """Pasa al formulario los materiales de esta producción."""
        kwargs = super().get_form_kwargs()
        kwargs['materiales'] = self.get_produccion().detalles.select_related('producto').order_by('producto__nombre')
        return kwargs

    def get_context_data(self, **kwargs):
        """Une cada material con su casilla para que la plantilla muestre valor y errores juntos."""
        context = super().get_context_data(**kwargs)
        form = context['form']
        # Cada material con su casilla ya enlazada (para mostrar el valor y los errores).
        context['produccion'] = self.get_produccion()
        context['filas'] = [
            (material, form[form.nombre_campo(material)]) for material in form.materiales
        ]
        return context

    def form_valid(self, form):
        """Registra los consumos; el servicio rechaza los que excedan el stock o lo requerido."""
        try:
            registrados = registrar_consumo_produccion(
                self.get_produccion(), self.request.user, form.consumos(),
            )
        except ErrorMovimiento as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        messages.success(self.request, f'Consumo registrado: {len(registrados)} material(es) actualizado(s).')
        return redirect(reverse('inventario:produccion_detalle', args=[self.kwargs['pk']]))


@login_required
@permission_required('inventario.change_produccion', raise_exception=True)
@require_POST
def produccion_terminar(request, pk):
    """
    Marca la producción como Terminada e ingresa sus unidades al inventario.
    Un solo botón: no hay que volver a cargar el producto ni la cantidad.
    """
    produccion = get_object_or_404(Produccion.objects.select_related('producto_terminado'), pk=pk)
    if produccion.estado in CONSUMO_CERRADO:
        messages.info(request, 'Esta producción ya está cerrada.')
        return redirect(reverse('inventario:produccion_detalle', args=[pk]))

    # El cambio de estado y el ingreso al inventario van en una transacción:
    # si el ingreso falla, la producción vuelve a su estado anterior.
    try:
        with transaction.atomic():
            produccion.estado = EstadoProduccion.TERMINADA
            produccion.save(update_fields=['estado'])
            movimiento = finalizar_produccion(produccion, request.user)
    except ErrorMovimiento as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f'Producción terminada. {movimiento.cantidad} {produccion.producto_terminado.unidad_medida} '
            f'de "{produccion.producto_terminado.nombre}" ya están en el inventario.',
        )
    return redirect(reverse('inventario:produccion_detalle', args=[pk]))


class ProduccionCrearView(ProduccionFormularioView):
    """Formulario para registrar una producción nueva (requiere permiso de creación)."""

    permission_required = 'inventario.add_produccion'

    def get_produccion(self):
        """Crea una producción sin guardar, asignada al usuario que la registra."""
        # El responsable es quien registra la producción; no se puede elegir en el formulario.
        return Produccion(usuario=self.request.user)


class ProduccionEditarView(ProduccionFormularioView):
    """Formulario para editar una producción existente (requiere permiso de edición)."""

    permission_required = 'inventario.change_produccion'

    def get_produccion(self):
        """Busca la producción por su pk en la URL; responde 404 si no existe."""
        return get_object_or_404(Produccion, pk=self.kwargs['pk'])

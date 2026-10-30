from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from .models import (
    DetalleMaterial,
    EstadoProducto,
    Produccion,
    Producto,
    TipoMovimiento,
    TipoProducto,
)
from .reportes import TIPOS_REPORTE


class ProduccionForm(forms.ModelForm):
    """Datos generales de una producción (la lista de materiales va en DetalleMaterialFormSet)."""

    class Meta:
        model = Produccion
        fields = ['tipo', 'descripcion', 'cantidad_solicitada', 'fecha_inicio', 'fecha_entrega', 'estado']
        labels = {
            'tipo': 'Tipo de producción',
            'descripcion': 'Descripción',
            'cantidad_solicitada': 'Cantidad a producir',
            'fecha_inicio': 'Fecha de inicio',
            'fecha_entrega': 'Fecha de entrega',
            'estado': 'Estado',
        }
        help_texts = {
            'tipo': 'Por ejemplo: Confección, Reparación o Muestra.',
            'cantidad_solicitada': 'Número de prendas o piezas.',
        }
        widgets = {
            'tipo': forms.TextInput(attrs={'placeholder': 'Ej. Confección', 'list': 'tipos-produccion'}),
            'descripcion': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ej. 20 camisas básicas talla M'}),
            'cantidad_solicitada': forms.NumberInput(attrs={'min': '1', 'step': '1'}),
            # format fija el formato ISO (AAAA-MM-DD) que exige el input type="date".
            # Sin esto, el idioma español renderiza 10/01/2026 y el campo se muestra vacío al editar.
            'fecha_inicio': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'fecha_entrega': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Una producción nueva empieza como "Pendiente"; el estado se cambia al editar.
        if self.instance.pk is None:
            self.fields.pop('estado')

    def clean_descripcion(self):
        return ' '.join(self.cleaned_data['descripcion'].split())


class DetalleMaterialForm(forms.ModelForm):
    """Una fila de la lista de materiales: insumo y cantidad requerida."""

    class Meta:
        model = DetalleMaterial
        fields = ['producto', 'cantidad_requerida']
        labels = {'producto': 'Insumo', 'cantidad_requerida': 'Cantidad requerida'}
        widgets = {
            'cantidad_requerida': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01', 'inputmode': 'decimal'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo insumos activos. Si la fila ya tiene un insumo que luego se desactivó, se mantiene.
        insumos = Producto.objects.filter(tipo=TipoProducto.INSUMO)
        if self.instance.pk and self.instance.producto_id:
            insumos = insumos.filter(Q(estado=EstadoProducto.ACTIVO) | Q(pk=self.instance.producto_id))
        else:
            insumos = insumos.filter(estado=EstadoProducto.ACTIVO)
        self.fields['producto'].queryset = insumos.order_by('nombre')
        self.fields['producto'].label_from_instance = lambda p: f'{p.nombre} ({p.unidad_medida})'

    def clean(self):
        # Nota: las filas marcadas para quitar se revisan en BaseDetalleMaterialFormSet,
        # porque Django ignora los errores de las filas que se van a borrar.
        cleaned = super().clean()

        requerida = cleaned.get('cantidad_requerida')
        if (
            requerida is not None
            and self.instance.pk
            and requerida < self.instance.cantidad_utilizada
        ):
            self.add_error(
                'cantidad_requerida',
                f'No puede ser menor a lo ya utilizado ({self.instance.cantidad_utilizada}).',
            )
        return cleaned


class BaseDetalleMaterialFormSet(BaseInlineFormSet):
    """Reglas que dependen de varias filas a la vez."""

    def clean(self):
        # Se revisa antes de super().clean(), que de lo contrario muestra el mensaje genérico
        # de Django por el índice de unicidad.
        vistos = set()
        for form in self.forms:
            datos = getattr(form, 'cleaned_data', None) or {}

            if datos.get('DELETE'):
                # Un material con consumo registrado no se puede quitar: el historial depende de él.
                if form.instance.pk and form.instance.cantidad_utilizada > 0:
                    raise ValidationError(
                        f'"{form.instance.producto.nombre}" ya tiene {form.instance.cantidad_utilizada} '
                        'utilizados en esta producción. No se puede quitar.'
                    )
                continue

            producto = datos.get('producto')
            if producto is None:
                continue
            if producto.pk in vistos:
                raise ValidationError(
                    'Un mismo insumo no puede aparecer dos veces. Usa una sola fila con la cantidad total.'
                )
            vistos.add(producto.pk)

        super().clean()


DetalleMaterialFormSet = inlineformset_factory(
    Produccion,
    DetalleMaterial,
    form=DetalleMaterialForm,
    formset=BaseDetalleMaterialFormSet,
    extra=1,
    can_delete=True,
)


class SelectConStock(forms.Select):
    """
    Lista desplegable que añade el stock disponible a cada opción (data-disponible).
    El navegador usa ese dato para limitar la cantidad antes de enviar el formulario.
    """

    def __init__(self, *args, **kwargs):
        self.stock = {}  # pk del producto -> (cantidad disponible, unidad)
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        pk = getattr(value, 'value', value)
        if pk in self.stock:
            cantidad, unidad = self.stock[pk]
            option['attrs']['data-disponible'] = str(cantidad)
            option['attrs']['data-unidad'] = unidad
        return option


class ReporteFiltroForm(forms.Form):
    """
    Filtros de los reportes. La misma validación la usan la pantalla y las
    exportaciones CSV/PDF, así un enlace de exportación nunca exporta datos
    que la pantalla no mostraría.
    """

    tipo = forms.ChoiceField(
        label='Reporte',
        required=False,
        choices=list(TIPOS_REPORTE.items()),
        initial='existencias',
    )
    q = forms.CharField(
        label='Producto',
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Nombre o descripción', 'type': 'search'}),
    )
    tipo_material = forms.ChoiceField(
        label='Tipo de material',
        required=False,
        choices=[('', 'Todos')] + list(TipoProducto.choices),
    )
    estado = forms.ChoiceField(
        label='Estado',
        required=False,
        choices=[('', 'Todos')] + list(EstadoProducto.choices),
    )
    desde = forms.DateField(label='Desde', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    hasta = forms.DateField(label='Hasta', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean_tipo(self):
        return self.cleaned_data.get('tipo') or 'existencias'

    def clean(self):
        cleaned = super().clean()
        desde = cleaned.get('desde')
        hasta = cleaned.get('hasta')
        if desde and hasta and desde > hasta:
            self.add_error('hasta', 'La fecha final no puede ser anterior a la inicial.')
        return cleaned


class HistorialFiltroForm(forms.Form):
    """
    Filtros del historial de movimientos (RF09).
    Todos son opcionales; se pueden combinar.
    """

    q = forms.CharField(
        label='Producto',
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Nombre del producto', 'type': 'search'}),
    )
    tipo_material = forms.ChoiceField(
        label='Tipo de material',
        required=False,
        choices=[('', 'Todos')] + list(TipoProducto.choices),
    )
    tipo_movimiento = forms.ChoiceField(
        label='Movimiento',
        required=False,
        choices=[('', 'Entradas y salidas')] + list(TipoMovimiento.choices),
    )
    desde = forms.DateField(
        label='Desde',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    hasta = forms.DateField(
        label='Hasta',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def clean(self):
        cleaned = super().clean()
        desde = cleaned.get('desde')
        hasta = cleaned.get('hasta')
        if desde and hasta and desde > hasta:
            self.add_error('hasta', 'La fecha final no puede ser anterior a la inicial.')
        return cleaned


class MovimientoForm(forms.Form):
    """
    Formulario de entrada o salida. Las existencias las valida el servicio
    (inventario/services.py); aquí solo se ayuda al usuario.
    """

    producto = forms.ModelChoiceField(
        queryset=Producto.objects.none(),
        label='Producto',
        empty_label='Elige un producto',
        widget=SelectConStock,
    )
    cantidad = forms.DecimalField(
        label='Cantidad',
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'min': '0.01', 'step': '0.01', 'inputmode': 'decimal'}),
    )
    motivo = forms.CharField(
        label='Motivo',
        max_length=255,
    )
    produccion = forms.ModelChoiceField(
        queryset=Produccion.objects.none(),
        required=False,
        label='Producción relacionada (opcional)',
        empty_label='Ninguna',
        help_text='Si el material es para una producción, selecciónala para llevar el consumo.',
    )

    MOTIVOS_SUGERIDOS = {
        TipoMovimiento.ENTRADA: 'Ej. Compra a proveedor, factura 123',
        TipoMovimiento.SALIDA: 'Ej. Consumo en corte del lote 5',
    }

    def __init__(self, *args, tipo, **kwargs):
        self.tipo = tipo
        super().__init__(*args, **kwargs)

        # Solo productos activos. En una salida se muestra el stock disponible.
        productos = Producto.objects.filter(estado=EstadoProducto.ACTIVO).order_by('nombre')
        self.fields['producto'].queryset = productos
        self.fields['producto'].label_from_instance = self._etiqueta_producto
        self.fields['producto'].widget.stock = {
            p.pk: (p.cantidad_actual, p.unidad_medida) for p in productos
        }

        self.fields['produccion'].queryset = Produccion.objects.order_by('-fecha_inicio')
        self.fields['motivo'].widget.attrs['placeholder'] = self.MOTIVOS_SUGERIDOS.get(tipo, '')

    @staticmethod
    def _etiqueta_producto(producto):
        return f'{producto.nombre} (disponible: {producto.cantidad_actual} {producto.unidad_medida})'

    def clean(self):
        cleaned = super().clean()
        producto = cleaned.get('producto')
        cantidad = cleaned.get('cantidad')

        # Aviso temprano: sin el servicio, la salida se rechazaría igual.
        if (
            self.tipo == TipoMovimiento.SALIDA
            and producto is not None
            and cantidad is not None
            and cantidad > producto.cantidad_actual
        ):
            self.add_error(
                'cantidad',
                f'Solo hay {producto.cantidad_actual} {producto.unidad_medida} disponibles '
                f'de "{producto.nombre}". No puedes sacar más de lo que hay.',
            )
        return cleaned


class ProductoForm(forms.ModelForm):
    """
    Formulario para registrar y modificar insumos y productos terminados.

    La cantidad actual no aparece aquí: solo cambia con entradas y salidas (Fase 4).
    """

    class Meta:
        model = Producto
        fields = ['nombre', 'tipo', 'unidad_medida', 'stock_minimo', 'descripcion', 'estado']
        labels = {
            'nombre': 'Nombre del producto',
            'tipo': 'Tipo',
            'unidad_medida': 'Unidad de medida',
            'stock_minimo': 'Stock mínimo',
            'descripcion': 'Descripción (opcional)',
            'estado': 'Estado',
        }
        help_texts = {
            'stock_minimo': 'Cuando las existencias lleguen a esta cantidad, el sistema mostrará una alerta.',
            'unidad_medida': 'Por ejemplo: metros, conos, unidades, rollos o kilos.',
            'tipo': 'Insumo: se usa para confeccionar. Producto terminado: prenda lista para vender.',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Ej. Tela algodón blanca', 'autofocus': True}),
            'unidad_medida': forms.TextInput(attrs={'placeholder': 'Ej. metros, conos, unidades'}),
            'stock_minimo': forms.NumberInput(attrs={'min': '0', 'step': '0.01', 'inputmode': 'decimal'}),
            'descripcion': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Color, referencia, proveedor, talla...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Un producto nuevo empieza activo; el estado se cambia desde el listado o la edición.
        if self.instance.pk is None:
            self.fields.pop('estado')

    def clean_nombre(self):
        # Quita espacios sobrantes y evita nombres repetidos sin importar mayúsculas.
        nombre = ' '.join(self.cleaned_data['nombre'].split())
        if len(nombre) < 2:
            raise forms.ValidationError('El nombre debe tener al menos 2 caracteres.')

        existe = (
            Producto.objects.filter(nombre__iexact=nombre)
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if existe:
            raise forms.ValidationError('Ya existe un producto con este nombre.')
        return nombre

    def clean_unidad_medida(self):
        return self.cleaned_data['unidad_medida'].strip().lower()

    def clean(self):
        cleaned = super().clean()
        # En clean() la instancia todavía tiene el tipo guardado en la base de datos.
        tipo_nuevo = cleaned.get('tipo')
        if (
            self.instance.pk
            and self.instance.tipo == TipoProducto.INSUMO
            and tipo_nuevo == TipoProducto.PRODUCTO_TERMINADO
            and self.instance.usos_en_produccion.exists()
        ):
            self.add_error(
                'tipo',
                'Este insumo se usa en producciones, así que no puede convertirse en producto terminado.',
            )
        return cleaned

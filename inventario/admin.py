from django.contrib import admin

from .models import DetalleMaterial, MovimientoInventario, Producto, Produccion


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    """Administración de productos e insumos en el panel de Django."""

    list_display = ('nombre', 'tipo', 'unidad_medida', 'cantidad_actual', 'stock_minimo', 'estado')
    list_filter = ('tipo', 'estado')
    search_fields = ('nombre', 'descripcion')
    # La cantidad solo cambia con movimientos de entrada o salida.
    readonly_fields = ('cantidad_actual',)

    def has_delete_permission(self, request, obj=None):
        # Los productos no se borran: se desactivan cambiando su estado.
        return False


class DetalleMaterialInline(admin.TabularInline):
    """Tabla editable de materiales dentro de la página de una producción."""

    model = DetalleMaterial
    extra = 1
    autocomplete_fields = ('producto',)


@admin.register(Produccion)
class ProduccionAdmin(admin.ModelAdmin):
    """Administración de producciones, con sus materiales editables en la misma página."""

    list_display = ('id', 'tipo', 'cantidad_solicitada', 'fecha_inicio', 'fecha_entrega', 'estado', 'usuario')
    list_filter = ('estado', 'tipo')
    search_fields = ('descripcion', 'tipo')
    list_select_related = ('usuario',)
    inlines = [DetalleMaterialInline]


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    """Historial de solo lectura: los movimientos no se crean, editan ni borran desde el admin."""

    list_display = ('fecha', 'producto', 'tipo_movimiento', 'cantidad', 'usuario', 'produccion')
    list_filter = ('tipo_movimiento', 'fecha')
    search_fields = ('producto__nombre', 'motivo')
    list_select_related = ('producto', 'usuario', 'produccion')
    date_hierarchy = 'fecha'

    def get_readonly_fields(self, request, obj=None):
        """Marca todos los campos como solo lectura."""
        return [f.name for f in self.model._meta.fields]

    # Los tres métodos siguientes quitan los botones de crear, editar y borrar.
    # Aunque alguien llegue por URL, Django niega la acción.
    def has_add_permission(self, request):
        """Nunca permite crear movimientos a mano: deben pasar por registrar_movimiento()."""
        return False

    def has_change_permission(self, request, obj=None):
        """Nunca permite editar un movimiento ya registrado."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Nunca permite borrar un movimiento del historial."""
        return False

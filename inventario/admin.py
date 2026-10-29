from django.contrib import admin

from .models import DetalleMaterial, MovimientoInventario, Producto, Produccion


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'unidad_medida', 'cantidad_actual', 'stock_minimo', 'estado')
    list_filter = ('tipo', 'estado')
    search_fields = ('nombre', 'descripcion')
    # La cantidad solo cambia con movimientos de entrada o salida.
    readonly_fields = ('cantidad_actual',)

    def has_delete_permission(self, request, obj=None):
        # Los productos no se borran: se desactivan cambiando su estado.
        return False


class DetalleMaterialInline(admin.TabularInline):
    model = DetalleMaterial
    extra = 1
    autocomplete_fields = ('producto',)


@admin.register(Produccion)
class ProduccionAdmin(admin.ModelAdmin):
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
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

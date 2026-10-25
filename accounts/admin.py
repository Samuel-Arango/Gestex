from django.contrib import admin

from .models import Rol, Usuario


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('id_rol', 'nombre_rol', 'descripcion')
    search_fields = ('nombre_rol',)


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    # El hash de la contraseña nunca se muestra ni se edita desde el admin.
    fields = ('nombre', 'correo', 'id_rol', 'estado')
    list_display = ('id_usuario', 'nombre', 'correo', 'id_rol', 'estado')
    list_filter = ('estado', 'id_rol')
    search_fields = ('nombre', 'correo')
    ordering = ('id_usuario',)

    def has_add_permission(self, request):
        # Las cuentas se crean con el registro o con createsuperuser, nunca sin contraseña.
        return False

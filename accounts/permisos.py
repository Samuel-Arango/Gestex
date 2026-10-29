"""
Roles y permisos de Gestex.

- Administrador: puede hacer todo, incluida la gestión de usuarios.
- Operario: registra y consulta el inventario. No borra registros
  y no administra usuarios.

Los permisos del Operario se listan aquí de forma explícita. Así, un módulo
nuevo queda bloqueado para el Operario hasta que se agregue a esta lista.
Los nombres siguen el formato de Django: 'app.accion_modelo'.
"""

ROL_ADMINISTRADOR = 'Administrador'
ROL_OPERARIO = 'Operario'

PERMISOS_OPERARIO = frozenset({
    # Productos (insumos y terminados): registrar, consultar y modificar. No borrar.
    'inventario.view_producto',
    'inventario.add_producto',
    'inventario.change_producto',
    # Producciones y sus materiales.
    'inventario.view_produccion',
    'inventario.add_produccion',
    'inventario.change_produccion',
    'inventario.view_detallematerial',
    'inventario.add_detallematerial',
    'inventario.change_detallematerial',
    # Movimientos: registrar y consultar. El historial no se edita ni se borra.
    'inventario.view_movimientoinventario',
    'inventario.add_movimientoinventario',
})


def tiene_permiso_por_rol(nombre_rol, permiso, esta_activo=True):
    """Decide si un rol concede un permiso ('app.accion_modelo')."""
    if not esta_activo:
        return False
    if nombre_rol == ROL_ADMINISTRADOR:
        return True
    if nombre_rol == ROL_OPERARIO:
        return permiso in PERMISOS_OPERARIO
    return False


def tiene_permisos_de_app(nombre_rol, app_label, esta_activo=True):
    """Indica si el rol tiene algún permiso sobre una app (para la pantalla de módulos)."""
    if not esta_activo:
        return False
    if nombre_rol == ROL_ADMINISTRADOR:
        return True
    if nombre_rol == ROL_OPERARIO:
        return any(p.startswith(f'{app_label}.') for p in PERMISOS_OPERARIO)
    return False

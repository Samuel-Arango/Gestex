from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _registrar_funciones_sqlite(sender, connection, **kwargs):
    """Cada conexión a SQLite recibe la función de normalización de texto."""
    if connection.vendor != 'sqlite':
        return
    from .busqueda import NOMBRE_FUNCION_SQLITE, normalizar_texto

    connection.connection.create_function(
        NOMBRE_FUNCION_SQLITE, 1, normalizar_texto, deterministic=True,
    )


class InventarioConfig(AppConfig):
    default_auto_field = 'django.db.models.AutoField'
    name = 'inventario'
    verbose_name = 'Inventario'

    def ready(self):
        connection_created.connect(_registrar_funciones_sqlite)

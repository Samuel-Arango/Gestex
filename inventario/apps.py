from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _registrar_funciones_sqlite(sender, connection, **kwargs):
    """Cada conexión a SQLite recibe la función de normalización de texto."""
    if connection.vendor != 'sqlite':
        return
    # El import va dentro de la función para no cargar busqueda.py al iniciar Django
    # si la conexión no es SQLite.
    from .busqueda import NOMBRE_FUNCION_SQLITE, normalizar_texto

    # SQLite no tiene funciones de normalización de tildes; se registra una en Python.
    # deterministic=True permite a SQLite usarla en índices y consultas optimizadas.
    connection.connection.create_function(
        NOMBRE_FUNCION_SQLITE, 1, normalizar_texto, deterministic=True,
    )


class InventarioConfig(AppConfig):
    """Configuración de la aplicación 'inventario' (nombre que ve el usuario: Inventario)."""

    default_auto_field = 'django.db.models.AutoField'
    name = 'inventario'
    verbose_name = 'Inventario'

    def ready(self):
        """Se llama al arrancar Django: conecta la función SQLite a cada nueva conexión."""
        # Se conecta aquí y no al importar el módulo, para que Django ya esté listo.
        connection_created.connect(_registrar_funciones_sqlite)

"""
Búsqueda de texto que ignora mayúsculas y tildes.

SQLite solo compara sin distinguir mayúsculas en letras sin tilde.
Por eso "ALGODÓN" no encontraría "algodón". Para resolverlo:

1. Se registra una función propia en SQLite llamada gestex_normalizar
   (ver inventario/apps.py). Quita tildes y pasa a minúsculas.
2. La búsqueda aplica esa misma normalización al texto de la base de datos
   y al texto que escribe el usuario.
"""
import unicodedata

from django.db.models import CharField, F, Func

NOMBRE_FUNCION_SQLITE = 'gestex_normalizar'


def normalizar_texto(texto):
    """Devuelve el texto en minúsculas y sin tildes. Ej.: 'Algodón' -> 'algodon'."""
    if texto is None:
        return ''
    descompuesto = unicodedata.normalize('NFD', texto)
    # 'Mn' = marcas diacríticas (tildes, diéresis). Se eliminan; las letras se conservan.
    sin_tildes = ''.join(c for c in descompuesto if unicodedata.category(c) != 'Mn')
    return sin_tildes.lower()


def campo_normalizado(nombre_campo):
    """Expresión SQL que aplica normalizar_texto a un campo de la base de datos."""
    return Func(F(nombre_campo), function=NOMBRE_FUNCION_SQLITE, output_field=CharField())

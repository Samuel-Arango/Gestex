"""
Renombra el rol 'Usuario' a 'Operario' (requisito de la Fase 2).

Si el rol 'Operario' ya existe, los usuarios de 'Usuario' se pasan a él
y el rol antiguo se elimina. Así la migración no falla en ningún caso.
"""
from django.db import migrations

DESCRIPCION_OPERARIO = 'Registra y consulta el inventario.'


def usuario_a_operario(apps, schema_editor):
    Rol = apps.get_model('accounts', 'Rol')
    Usuario = apps.get_model('accounts', 'Usuario')

    antiguo = Rol.objects.filter(nombre_rol='Usuario').first()
    if antiguo is None:
        return

    nuevo = Rol.objects.filter(nombre_rol='Operario').first()
    if nuevo is None:
        antiguo.nombre_rol = 'Operario'
        antiguo.descripcion = DESCRIPCION_OPERARIO
        antiguo.save()
        return

    # Ya existe 'Operario': se reasignan los usuarios y se elimina el rol antiguo.
    Usuario.objects.filter(id_rol=antiguo).update(id_rol=nuevo)
    antiguo.delete()


def operario_a_usuario(apps, schema_editor):
    Rol = apps.get_model('accounts', 'Rol')
    Rol.objects.filter(nombre_rol='Operario').update(
        nombre_rol='Usuario', descripcion='Acceso básico al sistema.',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_roles_base'),
    ]

    operations = [
        migrations.RunPython(usuario_a_operario, operario_a_usuario),
    ]

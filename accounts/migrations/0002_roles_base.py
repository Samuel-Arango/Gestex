from django.db import migrations

ROLES_BASE = [
    ('Administrador', 'Control total del sistema: usuarios, inventario y configuración.'),
    ('Usuario', 'Acceso básico al sistema para registrar movimientos de inventario.'),
]


def crear_roles_base(apps, schema_editor):
    Rol = apps.get_model('accounts', 'Rol')
    for nombre, descripcion in ROLES_BASE:
        Rol.objects.get_or_create(
            nombre_rol=nombre,
            defaults={'descripcion': descripcion},
        )


def eliminar_roles_base(apps, schema_editor):
    Rol = apps.get_model('accounts', 'Rol')
    Rol.objects.filter(nombre_rol__in=[n for n, _ in ROLES_BASE]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear_roles_base, eliminar_roles_base),
    ]

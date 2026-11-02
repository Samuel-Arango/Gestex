"""
Pruebas de roles, permisos y protección de vistas.

Comprueban qué puede hacer cada rol, que las vistas protegidas rechacen a
quien no corresponde y que las reglas de gestión de usuarios se cumplan.
"""
from django.test import TestCase
from django.urls import reverse

from .forms import UsuarioEditarForm
from .models import ROL_ADMINISTRADOR, ROL_OPERARIO, Rol, Usuario

# Contraseña de prueba que cumple las validaciones. No se usa fuera de las pruebas.
PASSWORD = 'Clave-Segura-2026'


def rol(nombre):
    """Devuelve el objeto Rol con ese nombre (los roles se crean en la migración)."""
    return Rol.objects.get(nombre_rol=nombre)


def crear(correo, nombre, nombre_rol):
    """Crea un usuario activo con el rol indicado y la contraseña de prueba."""
    return Usuario.objects.create_user(correo, nombre, PASSWORD, id_rol=rol(nombre_rol))


class PermisosPorRolTests(TestCase):
    """Comprueba los permisos de Administrador y Operario según permisos.py."""

    def setUp(self):
        self.admin = crear('admin@taller.co', 'Admin', ROL_ADMINISTRADOR)
        self.operario = crear('operario@taller.co', 'Operario', ROL_OPERARIO)

    def test_administrador_tiene_todos_los_permisos(self):
        self.assertTrue(self.admin.has_perm('inventario.delete_producto'))
        self.assertTrue(self.admin.has_perm('accounts.change_usuario'))
        self.assertTrue(self.admin.is_staff)

    def test_operario_puede_registrar_y_consultar_inventario(self):
        self.assertTrue(self.operario.has_perm('inventario.view_producto'))
        self.assertTrue(self.operario.has_perm('inventario.add_producto'))
        self.assertTrue(self.operario.has_perm('inventario.add_movimientoinventario'))

    def test_operario_no_puede_borrar_ni_editar_movimientos(self):
        self.assertFalse(self.operario.has_perm('inventario.delete_producto'))
        self.assertFalse(self.operario.has_perm('inventario.delete_movimientoinventario'))
        self.assertFalse(self.operario.has_perm('inventario.change_movimientoinventario'))

    def test_operario_no_administra_usuarios_ni_panel_django(self):
        self.assertFalse(self.operario.has_perm('accounts.view_usuario'))
        self.assertFalse(self.operario.has_perm('accounts.change_usuario'))
        self.assertFalse(self.operario.is_staff)

    def test_permiso_nuevo_queda_bloqueado_para_el_operario(self):
        # Un permiso que no está en la lista del operario no se concede por defecto.
        self.assertFalse(self.operario.has_perm('inventario.reportes_avanzados'))

    def test_has_perms_exige_todos_los_permisos(self):
        self.assertTrue(self.operario.has_perms(['inventario.view_producto', 'inventario.add_producto']))
        self.assertFalse(self.operario.has_perms(['inventario.view_producto', 'inventario.delete_producto']))

    def test_has_module_perms_por_app(self):
        self.assertTrue(self.operario.has_module_perms('inventario'))
        self.assertFalse(self.operario.has_module_perms('accounts'))
        self.assertTrue(self.admin.has_module_perms('accounts'))

    def test_usuario_inactivo_no_tiene_permisos(self):
        """Una cuenta desactivada no tiene permisos, aunque su rol sea Administrador."""
        self.admin.estado = False
        self.admin.save()
        self.assertFalse(self.admin.has_perm('inventario.view_producto'))
        self.assertFalse(self.admin.has_module_perms('inventario'))


class ProteccionDeVistasTests(TestCase):
    """Comprueba que solo los administradores acceden a la gestión de usuarios y al panel de Django."""

    def setUp(self):
        self.admin = crear('admin@taller.co', 'Admin', ROL_ADMINISTRADOR)
        self.operario = crear('operario@taller.co', 'Operario', ROL_OPERARIO)
        self.otro = crear('otro@taller.co', 'Otro', ROL_OPERARIO)
        self.url_lista = reverse('accounts:usuarios')
        self.url_editar = reverse('accounts:usuario_editar', args=[self.otro.pk])

    def test_visitante_anonimo_va_al_login(self):
        r = self.client.get(self.url_lista)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('accounts:login'), r['Location'])

    def test_operario_recibe_403_en_gestion_de_usuarios(self):
        self.client.force_login(self.operario)
        self.assertEqual(self.client.get(self.url_lista).status_code, 403)
        self.assertEqual(self.client.get(self.url_editar).status_code, 403)

    def test_operario_no_puede_cambiar_roles_por_post(self):
        """Aunque el operario envíe datos a mano (POST), no puede cambiar a otro usuario."""
        self.client.force_login(self.operario)
        r = self.client.post(self.url_editar, {'nombre': 'Hackeado', 'id_rol': rol(ROL_ADMINISTRADOR).pk, 'estado': True})
        self.assertEqual(r.status_code, 403)
        self.otro.refresh_from_db()
        self.assertEqual(self.otro.nombre, 'Otro')
        self.assertFalse(self.otro.es_administrador)

    def test_administrador_puede_ver_la_lista(self):
        self.client.force_login(self.admin)
        r = self.client.get(self.url_lista)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'otro@taller.co')

    def test_operario_no_puede_entrar_al_panel_django(self):
        self.client.force_login(self.operario)
        r = self.client.get('/admin/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/admin/login/', r['Location'])


class GestionDeUsuariosTests(TestCase):
    """Comprueba que el administrador puede editar usuarios y que las reglas de seguridad se cumplen."""

    def setUp(self):
        self.admin = crear('admin@taller.co', 'Admin', ROL_ADMINISTRADOR)
        self.otro = crear('otro@taller.co', 'Otro', ROL_OPERARIO)
        self.client.force_login(self.admin)

    def _editar(self, pk, **datos):
        """Envía el formulario de edición del usuario 'pk' con los datos indicados."""
        return self.client.post(reverse('accounts:usuario_editar', args=[pk]), datos)

    def test_administrador_puede_cambiar_rol_y_estado(self):
        r = self._editar(self.otro.pk, nombre='Otro', id_rol=rol(ROL_ADMINISTRADOR).pk, estado=True)
        self.assertRedirects(r, reverse('accounts:usuarios'))
        self.otro.refresh_from_db()
        self.assertTrue(self.otro.es_administrador)

    def test_administrador_puede_desactivar_a_otro_usuario(self):
        self._editar(self.otro.pk, nombre='Otro', id_rol=rol(ROL_OPERARIO).pk)  # sin estado = inactivo
        self.otro.refresh_from_db()
        self.assertFalse(self.otro.estado)
        self.assertFalse(self.otro.is_active)

    def test_administrador_no_puede_desactivarse_a_si_mismo(self):
        r = self._editar(self.admin.pk, nombre='Admin', id_rol=rol(ROL_ADMINISTRADOR).pk)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'No puedes desactivar tu propia cuenta.')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.estado)

    def test_administrador_no_puede_quitarse_su_propio_rol(self):
        r = self._editar(self.admin.pk, nombre='Admin', id_rol=rol(ROL_OPERARIO).pk, estado=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'No puedes quitarte tu propio rol de administrador.')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.es_administrador)

    def test_no_se_puede_dejar_el_sistema_sin_administrador_activo(self):
        # Caso límite: el último administrador activo no puede dejar de serlo.
        ultimo = crear('ultimo@taller.co', 'Último', ROL_ADMINISTRADOR)
        Usuario.objects.filter(pk=self.admin.pk).update(estado=False)
        operario = self.otro
        form = UsuarioEditarForm(
            data={'nombre': ultimo.nombre, 'id_rol': rol(ROL_OPERARIO).pk, 'estado': True},
            instance=ultimo,
            solicitante=operario,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('al menos un administrador activo', str(form.non_field_errors()))

    def test_formulario_nunca_incluye_la_contrasena(self):
        """El formulario de edición solo tiene nombre, rol y estado; la contraseña no se edita aquí."""
        form = UsuarioEditarForm(instance=self.otro, solicitante=self.admin)
        self.assertNotIn('password', form.fields)
        self.assertEqual(set(form.fields), {'nombre', 'id_rol', 'estado'})


class NavegacionPorRolTests(TestCase):
    """Comprueba qué opciones del menú de inicio ve cada rol y que el registro asigna Operario."""

    def setUp(self):
        self.admin = crear('admin@taller.co', 'Admin', ROL_ADMINISTRADOR)
        self.operario = crear('operario@taller.co', 'Operario', ROL_OPERARIO)

    def test_administrador_ve_opciones_de_administracion(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('dashboard:home'))
        self.assertContains(r, 'Usuarios y roles')
        self.assertContains(r, 'Panel Django Admin')

    def test_operario_no_ve_opciones_de_administracion(self):
        self.client.force_login(self.operario)
        r = self.client.get(reverse('dashboard:home'))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'Usuarios y roles')
        self.assertNotContains(r, 'Panel Django Admin')
        self.assertNotContains(r, 'Configuración')

    def test_usuario_nuevo_por_registro_es_operario(self):
        r = self.client.post(reverse('accounts:register'), {
            'nombre': 'Nueva Persona',
            'correo': 'nueva@taller.co',
            'password1': 'Otra-Clave-Segura-2026',
            'password2': 'Otra-Clave-Segura-2026',
        })
        self.assertRedirects(r, reverse('accounts:login'))
        self.assertEqual(Usuario.objects.get(correo='nueva@taller.co').id_rol.nombre_rol, ROL_OPERARIO)

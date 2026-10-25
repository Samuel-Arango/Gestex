from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ROL_ADMINISTRADOR, ROL_USUARIO, Rol, Usuario

PASSWORD = 'Tela-Segura-2026'


class UsuarioModelTests(TestCase):

    def test_roles_base_se_crean_con_la_migracion(self):
        self.assertTrue(Rol.objects.filter(nombre_rol=ROL_ADMINISTRADOR).exists())
        self.assertTrue(Rol.objects.filter(nombre_rol=ROL_USUARIO).exists())

    def test_la_contrasena_se_guarda_como_hash(self):
        usuario = Usuario.objects.create_user('ana@taller.co', 'Ana Ruiz', PASSWORD)
        usuario.refresh_from_db()
        self.assertNotEqual(usuario.password, PASSWORD)
        self.assertNotIn(PASSWORD, usuario.password)
        self.assertTrue(usuario.password.startswith('argon2'))
        self.assertTrue(usuario.check_password(PASSWORD))
        self.assertFalse(usuario.check_password('otra-clave'))

    def test_el_correo_se_guarda_en_minusculas(self):
        usuario = Usuario.objects.create_user('  Ana@Taller.CO ', 'Ana Ruiz', PASSWORD)
        self.assertEqual(usuario.correo, 'ana@taller.co')

    def test_correo_duplicado_no_se_permite(self):
        from django.db import IntegrityError, transaction
        Usuario.objects.create_user('ana@taller.co', 'Ana', PASSWORD)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.create_user('ANA@taller.co', 'Otra', PASSWORD)

    def test_rol_por_defecto_es_usuario(self):
        usuario = Usuario.objects.create_user('luis@taller.co', 'Luis Mora', PASSWORD)
        self.assertEqual(usuario.id_rol.nombre_rol, ROL_USUARIO)
        self.assertFalse(usuario.is_staff)

    def test_superusuario_es_administrador(self):
        admin = Usuario.objects.create_superuser('admin@taller.co', 'Admin', PASSWORD)
        self.assertEqual(admin.id_rol.nombre_rol, ROL_ADMINISTRADOR)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_correo_y_nombre_son_obligatorios(self):
        with self.assertRaises(ValueError):
            Usuario.objects.create_user('', 'Ana', PASSWORD)
        with self.assertRaises(ValueError):
            Usuario.objects.create_user('ana@taller.co', '', PASSWORD)


@override_settings(LOGIN_MAX_INTENTOS=3)
class InicioSesionTests(TestCase):

    def setUp(self):
        cache.clear()
        self.url = reverse('accounts:login')
        self.usuario = Usuario.objects.create_user('ana@taller.co', 'Ana Ruiz', PASSWORD)

    def test_login_correcto_redirige_al_dashboard(self):
        r = self.client.post(self.url, {'username': 'ana@taller.co', 'password': PASSWORD})
        self.assertRedirects(r, reverse('dashboard:home'))

    def test_correo_con_mayusculas_tambien_inicia_sesion(self):
        r = self.client.post(self.url, {'username': 'ANA@Taller.co', 'password': PASSWORD})
        self.assertRedirects(r, reverse('dashboard:home'))

    def test_contrasena_incorrecta_no_inicia_sesion(self):
        r = self.client.post(self.url, {'username': 'ana@taller.co', 'password': 'mala'})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(r, 'Correo o contraseña incorrectos.')

    def test_usuario_inactivo_no_inicia_sesion(self):
        self.usuario.estado = False
        self.usuario.save()
        r = self.client.post(self.url, {'username': 'ana@taller.co', 'password': PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_inyeccion_sql_en_el_correo_no_funciona(self):
        payloads = ["' OR '1'='1", "admin@taller.co' --", "' OR 1=1 --"]
        for payload in payloads:
            r = self.client.post(self.url, {'username': payload, 'password': 'x'})
            self.assertEqual(r.status_code, 200)
            self.assertNotIn('_auth_user_id', self.client.session)

    def test_bloqueo_tras_varios_intentos_fallidos(self):
        for _ in range(3):
            self.client.post(self.url, {'username': 'ana@taller.co', 'password': 'mala'})

        # Aunque la contraseña sea correcta, el acceso queda bloqueado temporalmente.
        r = self.client.post(self.url, {'username': 'ana@taller.co', 'password': PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(r, 'Demasiados intentos fallidos')

    def test_login_correcto_limpia_el_contador(self):
        for _ in range(2):
            self.client.post(self.url, {'username': 'ana@taller.co', 'password': 'mala'})
        r = self.client.post(self.url, {'username': 'ana@taller.co', 'password': PASSWORD})
        self.assertRedirects(r, reverse('dashboard:home'))

    def test_redireccion_abierta_bloqueada(self):
        r = self.client.post(
            self.url + '?next=https://sitio-malicioso.example',
            {'username': 'ana@taller.co', 'password': PASSWORD},
        )
        self.assertRedirects(r, reverse('dashboard:home'), fetch_redirect_response=False)


class RegistroTests(TestCase):

    def setUp(self):
        cache.clear()
        self.url = reverse('accounts:register')
        self.datos = {
            'nombre': 'María Pérez',
            'correo': 'maria@taller.co',
            'password1': PASSWORD,
            'password2': PASSWORD,
        }

    def test_pagina_de_registro_carga(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="password1"')

    def test_registro_valido_crea_usuario_y_redirige_al_login(self):
        r = self.client.post(self.url, self.datos)
        self.assertRedirects(r, reverse('accounts:login'))
        usuario = Usuario.objects.get(correo='maria@taller.co')
        self.assertEqual(usuario.nombre, 'María Pérez')
        self.assertTrue(usuario.check_password(PASSWORD))
        self.assertEqual(usuario.id_rol.nombre_rol, ROL_USUARIO)

    def test_despues_de_registrarse_puede_iniciar_sesion(self):
        self.client.post(self.url, self.datos)
        r = self.client.post(reverse('accounts:login'),
                             {'username': 'maria@taller.co', 'password': PASSWORD})
        self.assertRedirects(r, reverse('dashboard:home'))

    def test_correo_duplicado_se_rechaza(self):
        Usuario.objects.create_user('maria@taller.co', 'Otra', PASSWORD)
        r = self.client.post(self.url, {**self.datos, 'correo': 'MARIA@taller.co'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Usuario.objects.filter(correo='maria@taller.co').count(), 1)

    def test_contrasenas_distintas_se_rechazan(self):
        r = self.client.post(self.url, {**self.datos, 'password2': 'Otra-Clave-2026'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.filter(correo='maria@taller.co').exists())
        self.assertContains(r, 'Las contraseñas no coinciden.')

    def test_contrasena_debil_se_rechaza(self):
        r = self.client.post(self.url, {**self.datos, 'password1': '12345678', 'password2': '12345678'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.filter(correo='maria@taller.co').exists())

    def test_contrasena_similar_al_correo_se_rechaza(self):
        r = self.client.post(self.url, {
            **self.datos,
            'password1': 'maria@taller.co',
            'password2': 'maria@taller.co',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.filter(correo='maria@taller.co').exists())

    def test_correo_invalido_se_rechaza(self):
        r = self.client.post(self.url, {**self.datos, 'correo': 'no-es-correo'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.exists())

    def test_usuario_autenticado_no_ve_el_registro(self):
        usuario = Usuario.objects.create_user('ana@taller.co', 'Ana', PASSWORD)
        self.client.force_login(usuario)
        r = self.client.get(self.url)
        self.assertRedirects(r, reverse('dashboard:home'))


class ProteccionDeRutasTests(TestCase):

    def setUp(self):
        cache.clear()
        self.usuario = Usuario.objects.create_user('ana@taller.co', 'Ana', PASSWORD)

    def test_dashboard_requiere_sesion(self):
        r = self.client.get(reverse('dashboard:home'))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('accounts:login'), r['Location'])

    def test_dashboard_visible_con_sesion(self):
        self.client.force_login(self.usuario)
        r = self.client.get(reverse('dashboard:home'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Ana')

    def test_logout_solo_acepta_post(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse('accounts:logout')).status_code, 405)

    def test_logout_por_post_redirige_al_login(self):
        self.client.force_login(self.usuario)
        r = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(r, reverse('accounts:login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_usuario_inactivo_pierde_acceso_a_sesiones_existentes(self):
        self.client.force_login(self.usuario)
        self.usuario.estado = False
        self.usuario.save()
        r = self.client.get(reverse('dashboard:home'))
        self.assertEqual(r.status_code, 302)

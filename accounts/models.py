from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

ROL_ADMINISTRADOR = 'Administrador'
ROL_USUARIO = 'Usuario'


class Rol(models.Model):
    """Define los permisos de cada usuario (tabla Roles)."""

    id_rol = models.AutoField(primary_key=True, db_column='Id_rol')
    nombre_rol = models.CharField(
        'nombre del rol', max_length=30, unique=True, db_column='Nombre_rol',
    )
    descripcion = models.CharField(max_length=150, blank=True, db_column='descripcion')

    class Meta:
        db_table = 'Roles'
        verbose_name = 'rol'
        verbose_name_plural = 'roles'

    def __str__(self):
        return self.nombre_rol


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear_usuario(self, correo, nombre, password, id_rol, **extra_fields):
        if not correo:
            raise ValueError('El correo es obligatorio.')
        if not nombre:
            raise ValueError('El nombre es obligatorio.')

        correo = self.normalize_email(correo).strip().lower()
        if id_rol is None:
            id_rol, _ = Rol.objects.get_or_create(
                nombre_rol=ROL_USUARIO,
                defaults={'descripcion': 'Acceso básico al sistema.'},
            )

        usuario = self.model(correo=correo, nombre=nombre, id_rol=id_rol, **extra_fields)
        usuario.set_password(password)  # Guarda solo el hash, nunca el texto plano.
        usuario.save(using=self._db)
        return usuario

    def create_user(self, correo, nombre, password=None, id_rol=None, **extra_fields):
        extra_fields.setdefault('estado', True)
        return self._crear_usuario(correo, nombre, password, id_rol, **extra_fields)

    def create_superuser(self, correo, nombre, password=None, **extra_fields):
        rol, _ = Rol.objects.get_or_create(
            nombre_rol=ROL_ADMINISTRADOR,
            defaults={'descripcion': 'Control total del sistema.'},
        )
        extra_fields.setdefault('estado', True)
        return self._crear_usuario(correo, nombre, password, rol, **extra_fields)


class Usuario(AbstractBaseUser):
    """Usuarios que ingresan al sistema (tabla Usuarios)."""

    id_usuario = models.AutoField(primary_key=True, db_column='Id_usuario')
    nombre = models.CharField(max_length=100, db_column='nombre')
    correo = models.EmailField(max_length=100, unique=True, db_column='correo')
    # Hash de la contraseña (Argon2/PBKDF2). 128 caracteres para cubrir hashes largos.
    password = models.CharField(
        'contraseña', max_length=128, db_column='Contraseña_hash',
    )
    id_rol = models.ForeignKey(
        Rol,
        on_delete=models.PROTECT,  # No se puede borrar un rol con usuarios asignados.
        db_column='Id_rol',
        related_name='usuarios',
    )
    estado = models.BooleanField(default=True, db_column='estado')

    objects = UsuarioManager()

    USERNAME_FIELD = 'correo'
    EMAIL_FIELD = 'correo'
    REQUIRED_FIELDS = ['nombre']

    class Meta:
        db_table = 'Usuarios'
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    def save(self, *args, **kwargs):
        # El correo se guarda siempre en minúsculas para que la unicidad no dependa de mayúsculas.
        if self.correo:
            self.correo = self.correo.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre or self.correo

    # ---- Compatibilidad con el sistema de autenticación de Django ----

    @property
    def is_active(self):
        return self.estado

    @property
    def is_staff(self):
        return self.id_rol.nombre_rol == ROL_ADMINISTRADOR

    @property
    def is_superuser(self):
        return self.is_staff

    def has_perm(self, perm, obj=None):
        return self.is_active and self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_active and self.is_superuser

    def get_full_name(self):
        return self.nombre

    def get_short_name(self):
        return self.nombre.split(' ')[0] if self.nombre else self.correo

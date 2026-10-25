# Gestex

Sistema web para controlar el inventario de un **taller de confección textil**: telas, hilos, avíos, botones y accesorios, junto con compras, cortes y salidas.

Está hecho con **Python 3.14** y **Django 6.1**.

---

## Contenido

- [Qué incluye](#qué-incluye)
- [Requisitos](#requisitos)
- [Instalación rápida](#instalación-rápida)
- [Uso](#uso)
- [Variables de entorno](#variables-de-entorno)
- [Pruebas](#pruebas)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Modelo de datos](#modelo-de-datos)
- [Seguridad](#seguridad)
- [Estado del proyecto](#estado-del-proyecto)

---

## Qué incluye

| Módulo | Descripción |
|---|---|
| **Acceso** (`accounts/`) | Inicio de sesión con correo, registro de usuarios, cierre de sesión y bloqueo temporal tras varios intentos fallidos. |
| **Dashboard** (`dashboard/`) | Pantalla principal para usuarios con sesión iniciada. Actualmente muestra el diseño base; los datos de inventario aún no están conectados. |
| **Panel de administración** (`/admin/`) | Panel de Django para gestionar roles y usuarios. |

---

## Requisitos

- Python 3.14
- Git (opcional, para clonar el repositorio)

Las demás dependencias están en `requirements.txt`.

---

## Instalación rápida

Los comandos son para **Windows (PowerShell)**. En Linux/macOS, cambia `venv\Scripts\...` por `venv/bin/...`.

```powershell
# 1. Entrar a la carpeta del proyecto
cd "ruta\a\Gestex"

# 2. Crear el entorno virtual
python -m venv venv

# 3. Activarlo
.\venv\Scripts\activate

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Crear las tablas de la base de datos
python manage.py migrate

# 6. Crear el primer administrador
python manage.py createsuperuser

# 7. Iniciar el servidor de desarrollo
python manage.py runserver
```

`migrate` crea las tablas y carga los roles base (`Administrador` y `Usuario`).

---

## Uso

Con el servidor activo, abre en el navegador:

| Página | Dirección | Acceso |
|---|---|---|
| Inicio de sesión | http://127.0.0.1:8000/cuenta/login/ | Público |
| Registro | http://127.0.0.1:8000/cuenta/registro/ | Público |
| Dashboard | http://127.0.0.1:8000/dashboard/ | Requiere sesión |
| Panel de administración | http://127.0.0.1:8000/admin/ | Solo administradores |

La dirección `/` redirige al inicio de sesión.

### Flujo de acceso

1. Un visitante se **registra** con nombre, correo y contraseña. Por defecto recibe el rol `Usuario`.
2. Inicia sesión con su **correo** y contraseña.
3. Tras entrar, llega al **dashboard**.
4. Para cerrar sesión usa el botón correspondiente (solo funciona por POST).

Si se equivoca de contraseña 5 veces seguidas desde el mismo equipo, el acceso queda bloqueado 15 minutos para ese correo.

---

## Variables de entorno

En desarrollo no necesitas configurar nada. Para producción define estas variables:

| Variable | Para qué sirve | Valor de desarrollo |
|---|---|---|
| `DJANGO_DEBUG` | `1` activa el modo de depuración, `0` lo desactiva | `1` (por defecto) |
| `DJANGO_SECRET_KEY` | Clave secreta de Django. **Obligatoria si `DJANGO_DEBUG=0`** | Se usa una clave interna |
| `DJANGO_ALLOWED_HOSTS` | Dominios permitidos, separados por coma | `localhost,127.0.0.1` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Servidor de correo SMTP (solo en producción) | No aplica |

Ejemplo en PowerShell:

```powershell
$env:DJANGO_DEBUG = "0"
$env:DJANGO_SECRET_KEY = "cambia-esta-clave-por-una-larga-y-aleatoria"
$env:DJANGO_ALLOWED_HOSTS = "gestex.midominio.com"
```

---

## Pruebas

```powershell
python manage.py test accounts dashboard
```

Las pruebas cubren:

- Creación de usuarios y cifrado de contraseñas.
- Correos únicos sin distinguir mayúsculas.
- Registro, validaciones y contraseñas débiles.
- Inicio de sesión, cuentas inactivas y bloqueo por intentos fallidos.
- Protección contra inyección SQL y redirecciones externas.
- Acceso restringido al dashboard y cierre de sesión solo por POST.

---

## Estructura del proyecto

```text
Gestex/
├── accounts/                 # Acceso: modelos, formularios, vistas y pruebas
│   ├── migrations/           # Esquema y roles base
│   ├── admin.py              # Administración de Roles y Usuarios
│   ├── forms.py              # Formularios de inicio de sesión y registro
│   ├── models.py             # Modelos Rol y Usuario
│   ├── tests.py              # Pruebas automáticas
│   ├── urls.py               # Rutas de /cuenta/
│   └── views.py              # Inicio de sesión, registro y límite de intentos
├── config/                   # Configuración del proyecto
│   ├── settings.py           # Ajustes generales y de seguridad
│   └── urls.py               # Rutas principales
├── dashboard/                # Pantalla principal del sistema
├── static/
│   ├── css/                  # Estilos
│   └── js/                   # Comportamiento del formulario de registro
├── templates/
│   ├── accounts/             # Inicio de sesión y registro
│   └── dashboard/            # Plantilla base y dashboard
├── manage.py
├── requirements.txt
└── README.md
```

---

## Modelo de datos

**Roles** — define los permisos de cada usuario.

| Campo | Tipo | Notas |
|---|---|---|
| `Id_rol` | INT, PK | |
| `Nombre_rol` | VARCHAR(30) | Único |
| `descripcion` | VARCHAR(150) | |

**Usuarios** — personas que ingresan al sistema.

| Campo | Tipo | Notas |
|---|---|---|
| `Id_usuario` | INT, PK | |
| `nombre` | VARCHAR(100) | |
| `correo` | VARCHAR(100) | Único, sin distinguir mayúsculas. Es el usuario de inicio de sesión. |
| `Contraseña_hash` | VARCHAR(128) | Hash Argon2. Nunca se guarda la contraseña en texto plano. |
| `Id_rol` | INT, FK | Apunta a `Roles`. |
| `estado` | BOOLEAN | `False` impide iniciar sesión. |

Django añade el campo `last_login` a la tabla de usuarios, necesario para su sistema de autenticación.

---

## Seguridad

- Contraseñas con **Argon2**, validación de fortaleza de Django y comparación con el nombre y correo del usuario.
- **Bloqueo temporal** tras 5 intentos fallidos (15 minutos).
- Consultas solo mediante el ORM de Django, sin SQL escrito a mano.
- Cookies de sesión y CSRF con `HttpOnly` y `SameSite=Lax`; sesión de 8 horas como máximo.
- En producción (`DJANGO_DEBUG=0`): HTTPS obligatorio, HSTS y cookies `Secure`.
- El panel de administración no muestra ni edita contraseñas y no permite crear usuarios sin contraseña.

Para revisar la configuración de producción:

```powershell
$env:DJANGO_DEBUG = "0"
$env:DJANGO_SECRET_KEY = "una-clave-larga-y-aleatoria"
python manage.py check --deploy
```

---

## Estado del proyecto

- [x] Modelos de Roles y Usuarios según el diseño de base de datos
- [x] Inicio de sesión, registro y cierre de sesión
- [x] Pruebas automáticas
- [ ] Inventario: telas, hilos, avíos y productos terminados
- [ ] Movimientos: compras, cortes y salidas
- [ ] Datos reales en el dashboard
- [ ] Gestión de usuarios y roles desde la aplicación (hoy se hace desde el panel de administración)

---

## Autor

Samuel Arango — Trabajo de grado

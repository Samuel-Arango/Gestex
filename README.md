# Gestex - Plataforma de Gestión de Inventario para Talleres de Confección Textil

Gestex es un sistema web desarrollado con **Python** y **Django** pensado para optimizar el control de inventario en talleres unipersonales o pequeños talleres de confección textil.

## Características principales

- **Módulo de autenticación separado** (`accounts/`) con login personalizado, limpio y atractivo.
- **Dashboard** modular (`dashboard/`) con vista general del taller.
- **Panel de Administración de Django** (`/admin/`) para gestión completa de datos.
- **Enfoque textil**: pensado para control de telas, hilos, avíos, botones, accesorios, compras, cortes y salidas.
- **Interfaz moderna** con CSS personalizado y plantillas HTML.
- **Redirecciones seguras** tras login/logout.

## Tecnologías

- Python 3.14
- Django 6.1
- HTML5, CSS3
- Bootstrap Icons
- SQLite3 (por defecto)

## Estructura del proyecto

```text
Gestex/
├── accounts/        # Módulo de autenticación independiente
├── config/          # Configuración del proyecto (settings, urls, wsgi/asgi)
├── dashboard/       # Dashboard principal del sistema
├── static/          # Archivos estáticos (CSS, JS, imágenes)
├── templates/       # Plantillas HTML
├── manage.py
└── db.sqlite3       # Base de datos (no se recomienda subir a producción)
```

## Instalación y ejecución

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd Gestex
```

### 2. Crear y activar entorno virtual

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\activate
```

**Linux/macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

Si no existe `requirements.txt`, instalar Django:

```bash
pip install Django>=6.1
pip freeze > requirements.txt
```

### 4. Aplicar migraciones

```bash
python manage.py migrate
```

### 5. Crear superusuario

```bash
python manage.py createsuperuser
```

### 6. Ejecutar servidor de desarrollo

```bash
python manage.py runserver
```

Acceder a:
- Login: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- Dashboard: [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/)
- Admin Django: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

## Flujo de autenticación

- `/` → redirige a `/cuenta/login/`
- Tras iniciar sesión con credenciales válidas → redirige a `/dashboard/`
- Cierre de sesión (POST) → redirige a `/cuenta/login/`

## Notas

- El login es independiente al panel de administración.
- Los archivos estáticos se encuentran en `static/` y las plantillas en `templates/`.
- Para producción, configurar `DEBUG=False`, `ALLOWED_HOSTS`, `SECRET_KEY` segura y servidor web adecuado.

## Autor

Samuel Arango - Trabajo de Grado

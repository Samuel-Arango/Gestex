# Gestex

Plataforma web para controlar el inventario de un **taller de confección textil**: telas, hilos, avíos y botones (insumos), prendas terminadas, órdenes de producción, entradas y salidas, historial y reportes.

Desarrollada con **Python 3.14** y **Django 6.1**, con base de datos **SQLite**.

---

## Contenido

1. [Qué hace el sistema](#qué-hace-el-sistema)
2. [Requisitos](#requisitos)
3. [Instalación paso a paso](#instalación-paso-a-paso)
4. [Uso del sistema](#uso-del-sistema)
5. [Roles y permisos](#roles-y-permisos)
6. [Reglas de negocio](#reglas-de-negocio)
7. [Pruebas](#pruebas)
8. [Variables de entorno (producción)](#variables-de-entorno-producción)
9. [Estructura del proyecto](#estructura-del-proyecto)
10. [Modelo de datos](#modelo-de-datos)
11. [Seguridad](#seguridad)
12. [Limitaciones conocidas](#limitaciones-conocidas)

---

## Qué hace el sistema

| Módulo | Para qué sirve |
|---|---|
| **Acceso** (`accounts`) | Iniciar sesión con correo, registrarse, cerrar sesión y gestionar usuarios (solo administrador). |
| **Dashboard** (`dashboard`) | Resumen del taller: insumos, productos terminados, stock bajo, movimientos de hoy y producciones en curso. |
| **Inventario** (`inventario`) | Registrar y buscar productos, editar datos, activar o desactivar. |
| **Movimientos** | Registrar entradas y salidas, y consultar el historial con filtros. |
| **Producciones** | Órdenes de confección con su lista de materiales y avance de consumo. |
| **Reportes** | Existencias, movimientos por producto y catálogo; exportación a CSV y PDF. |
| **Panel de Django** (`/admin/`) | Administración técnica de roles, usuarios y datos. |

---

## Requisitos

- **Python 3.14** (o 3.11+)
- **Windows, Linux o macOS**
- Un navegador moderno (Chrome, Edge, Firefox, Safari)

Las dependencias están fijadas en `requirements.txt`.

---

## Instalación paso a paso

Los comandos son para **Windows PowerShell**. En Linux o macOS, usa `source venv/bin/activate` en lugar de `.\venv\Scripts\activate`.

### 1. Entrar a la carpeta del proyecto

```powershell
cd "C:\ruta\a\Gestex"
```

### 2. Crear el entorno virtual

```powershell
python -m venv venv
```

### 3. Activarlo

```powershell
.\venv\Scripts\activate
```

Verás `(venv)` al inicio de la línea.

### 4. Instalar las dependencias

```powershell
python -m pip install -r requirements.txt
```

### 5. Crear las tablas de la base de datos

```powershell
python manage.py migrate
```

Este paso también carga los roles `Administrador` y `Operario`.

### 6. Crear el primer administrador

```powershell
python manage.py createsuperuser
```

Te pedirá correo, nombre y contraseña. La contraseña no se muestra mientras la escribes.

### 7. (Opcional) Cargar datos de prueba

```powershell
python manage.py cargar_datos_prueba
```

Crea 5 insumos, 2 productos terminados y una producción de ejemplo. Puedes ejecutarlo varias veces sin duplicar datos. Requiere que exista al menos un administrador activo.

### 8. Iniciar el servidor

```powershell
python manage.py runserver
```

Abre **http://127.0.0.1:8000/** en el navegador.

---

## Uso del sistema

| Página | Dirección | Quién puede entrar |
|---|---|---|
| Inicio de sesión | `/cuenta/login/` | Público |
| Registro | `/cuenta/registro/` | Público |
| Dashboard | `/dashboard/` | Con sesión iniciada |
| Inventario | `/inventario/` | Con permiso de productos |
| Nuevo producto | `/inventario/nuevo/` | Con permiso de crear productos |
| Entrada de material | `/inventario/movimientos/entrada/` | Con permiso de movimientos |
| Salida de material | `/inventario/movimientos/salida/` | Con permiso de movimientos |
| Historial | `/inventario/movimientos/` | Con permiso de ver movimientos |
| Producciones | `/inventario/producciones/` | Con permiso de producciones |
| Reportes | `/inventario/reportes/` | Con permiso de productos |
| Usuarios y roles | `/cuenta/usuarios/` | Solo administrador |
| Panel de Django | `/admin/` | Solo administrador |

La dirección `/` redirige al inicio de sesión.

### Flujo típico

1. Un visitante se **registra** en `/cuenta/registro/`. Por defecto recibe el rol **Operario**.
2. Inicia sesión con su correo y contraseña. Tras entrar llega al **dashboard**.
3. Registra productos en **Inventario → Nuevo producto**. Las existencias empiezan en 0.
4. Registra la **entrada** de material que compra. Las existencias suben.
5. Crea una **producción** con sus materiales y registra la **salida** desde la ficha de la producción.
6. Revisa el **historial** o descarga un **reporte** en CSV o PDF.

Si se equivoca de contraseña 5 veces seguidas, el acceso queda bloqueado 15 minutos para ese correo.

---

## Roles y permisos

| Acción | Administrador | Operario |
|---|:---:|:---:|
| Ver y crear productos, editar datos | ✔ | ✔ |
| Activar o desactivar productos | ✔ | ✔ |
| Borrar productos | ✘ (no existe la función) | ✘ |
| Registrar entradas y salidas | ✔ | ✔ |
| Ver historial de movimientos | ✔ | ✔ |
| Editar o borrar movimientos | ✘ (son inmutables) | ✘ |
| Crear y editar producciones | ✔ | ✔ |
| Ver reportes y exportarlos | ✔ | ✔ |
| Gestionar usuarios y roles | ✔ | ✘ |
| Entrar al panel de Django | ✔ | ✘ |

Los permisos de cada rol están en `accounts/permisos.py`. Si agregas un módulo nuevo, el Operario no tendrá acceso hasta que lo añadas a la lista.

---

## Reglas de negocio

- **Existencias nunca negativas.** Una salida mayor a lo disponible se rechaza con un mensaje claro. La comprobación se hace en el servidor, aunque el navegador ya la haya validado.
- **Las existencias solo cambian con movimientos.** Ni los formularios ni las vistas suman o restan directamente; todo pasa por `inventario/services.py`.
- **Cada movimiento es atómico.** El cambio de existencias y el registro del historial se guardan juntos o no se guarda nada.
- **El historial es inmutable.** Un movimiento no se edita ni se borra. Para corregir un error se registra un movimiento nuevo.
- **Los productos no se borran.** Se desactivan, y su historial se conserva.
- **Alerta de stock bajo.** Un producto activo con existencias menores o iguales a su stock mínimo se marca en el listado, el dashboard y los reportes.
- **Salidas ligadas a una producción** suman al material utilizado de esa producción.
- **Lista de materiales:** un insumo aparece una sola vez por producción, solo se pueden usar insumos activos, y no se puede quitar un material que ya tiene consumo.

---

## Pruebas

```powershell
python manage.py test accounts dashboard inventario
```

Son **233 pruebas** que cubren:

- Creación de usuarios y cifrado de contraseñas.
- Registro, inicio de sesión, bloqueo por intentos fallidos y cierre de sesión.
- Roles, permisos y protección de vistas (incluye 403 para usuarios sin permiso).
- CRUD de productos, búsqueda sin tildes y validaciones.
- Entradas y salidas: reglas de stock, atomicidad y stock desactualizado.
- Historial: filtros, fechas, paginación y número de consultas.
- Reportes: cálculos, filtros, exportación CSV (protección contra fórmulas) y PDF.
- Producciones: formularios, formsets, progreso y permisos.
- Dashboard: datos mostrados según el rol.

Para revisar que el proyecto no tenga errores de configuración ni migraciones pendientes:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

---

## Variables de entorno (producción)

En desarrollo no necesitas configurar nada. Para producción define estas variables antes de iniciar el servidor:

| Variable | Qué hace | Ejemplo |
|---|---|---|
| `DJANGO_DEBUG` | `0` desactiva el modo de depuración | `0` |
| `DJANGO_SECRET_KEY` | Clave secreta de Django. **Obligatoria si `DEBUG=0`** | Cadena larga y aleatoria |
| `DJANGO_ALLOWED_HOSTS` | Dominios permitidos, separados por coma | `gestex.midominio.com` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Servidor SMTP para correos | Según tu proveedor |

Ejemplo en PowerShell:

```powershell
$env:DJANGO_DEBUG = "0"
$env:DJANGO_SECRET_KEY = "una-clave-larga-y-aleatoria-de-al-menos-50-caracteres"
$env:DJANGO_ALLOWED_HOSTS = "gestex.midominio.com"
python manage.py check --deploy
```

Con `DEBUG=0` se activan HTTPS obligatorio, HSTS, cookies seguras y redirección a HTTPS. Para publicar la aplicación se necesita además un servidor web (por ejemplo, Nginx con Gunicorn o un proveedor de hosting); `runserver` es solo para desarrollo.

---

## Estructura del proyecto

```text
Gestex/
├── accounts/                  # Acceso y usuarios
│   ├── migrations/            # Esquema de usuarios y roles base
│   ├── forms.py               # Login, registro y edición de usuarios
│   ├── models.py              # Modelos Rol y Usuario
│   ├── permisos.py             # Permisos de cada rol (fuente de verdad)
│   ├── views.py               # Login con bloqueo, registro, gestión de usuarios
│   └── test_roles.py          # Pruebas de roles y permisos
├── config/                    # Configuración del proyecto
│   ├── settings.py            # Ajustes generales y de seguridad
│   └── urls.py                # Rutas principales
├── dashboard/                 # Pantalla de inicio
├── inventario/                # Núcleo del sistema
│   ├── management/commands/   # cargar_datos_prueba
│   ├── migrations/            # Productos, producciones, movimientos
│   ├── busqueda.py            # Búsqueda sin tildes
│   ├── exportacion.py         # CSV y PDF
│   ├── forms.py               # Formularios de productos, movimientos, reportes y producciones
│   ├── models.py              # Modelos del inventario
│   ├── reportes.py            # Cálculo de reportes
│   ├── services.py            # Entradas y salidas (única vía para cambiar existencias)
│   ├── views.py               # Vistas del inventario
│   └── test_*.py              # Pruebas por módulo
├── static/
│   ├── css/                   # dashboard.css, login_accounts.css, pulido.css, ...
│   └── js/                    # Comportamiento de formularios
├── templates/
│   ├── accounts/              # Login, registro y gestión de usuarios
│   ├── dashboard/             # Plantilla base y dashboard
│   └── inventario/            # Productos, movimientos, reportes y producciones
├── manage.py
├── requirements.txt
└── README.md
```

---

## Modelo de datos

**Roles** (`Roles`)

| Campo | Tipo | Notas |
|---|---|---|
| `Id_rol` | INT, PK | |
| `Nombre_rol` | VARCHAR(30) | Único: `Administrador` u `Operario` |
| `descripcion` | VARCHAR(150) | |

**Usuarios** (`Usuarios`)

| Campo | Tipo | Notas |
|---|---|---|
| `Id_usuario` | INT, PK | |
| `nombre` | VARCHAR(100) | |
| `correo` | VARCHAR(100) | Único, sin distinguir mayúsculas. Es el usuario de acceso. |
| `Contraseña_hash` | VARCHAR(128) | Hash Argon2. Nunca se guarda la contraseña. |
| `Id_rol` | INT, FK | Apunta a `Roles` |
| `estado` | BOOLEAN | `False` impide iniciar sesión |

**Producto** (`inventario_producto`): nombre, descripción, tipo (insumo o producto terminado), unidad de medida, existencias actuales (nunca negativas), stock mínimo y estado (activo o inactivo).

**Producción** (`inventario_produccion`): tipo, descripción, cantidad a producir, fechas de inicio y entrega, estado (Pendiente, En proceso, Terminada o Cancelada) y responsable.

**Material de producción** (`inventario_detallematerial`): producción, insumo, cantidad requerida y cantidad utilizada. Un insumo aparece una sola vez por producción.

**Movimiento** (`inventario_movimientoinventario`): producto, usuario, tipo (entrada o salida), cantidad (mayor que cero), fecha, motivo y producción relacionada (opcional). Es inmutable.

Django añade `last_login` a la tabla de usuarios para su sistema de autenticación.

---

## Seguridad

- **Contraseñas** con Argon2, validación de fortaleza de Django y comparación con el nombre y el correo del usuario.
- **Bloqueo temporal** tras 5 intentos fallidos, por combinación de dirección IP y correo.
- **Consultas solo con el ORM** de Django, sin SQL escrito a mano.
- **Protección contra fórmulas en CSV:** los nombres escritos por el usuario no pueden ejecutarse en Excel.
- **Textos escapados** en las plantillas y en los PDF.
- **Cookies** de sesión y CSRF con `HttpOnly` y `SameSite=Lax`; sesión de 8 horas como máximo.
- **Cierre de sesión solo por POST**, para que un enlace externo no pueda cerrar la sesión.
- **Permisos verificados en el servidor** en cada vista y en cada exportación.
- **Panel de Django** sin acceso a hashes de contraseña y sin alta de usuarios sin contraseña.

Para revisar la configuración de producción, consulta la sección de variables de entorno.

---

## Limitaciones conocidas

- **Bloqueo de intentos en caché local.** Con varios servidores o procesos hay que usar Redis o Memcached para que el contador sea compartido.
- **Bloqueo de filas en SQLite.** `select_for_update` no tiene efecto en SQLite. La protección de existencias se basa en una actualización condicional y en una restricción `CHECK` de la base de datos, que funcionan en cualquier motor. Con MySQL o PostgreSQL, el bloqueo también aplica.
- **Búsqueda sin tildes** con una función propia de SQLite. Si cambias de motor de base de datos habrá que adaptar `inventario/busqueda.py`.
- **Interfaz con CSS propio.** Usa iconos de Bootstrap Icons y un diseño propio, sin el framework Bootstrap 5.
- **Versión de Django.** El proyecto usa Django 6.1 (la versión instalada y probada), no la 5.x sugerida inicialmente.
- **Sin recuperación de contraseña por correo.** El administrador restablece el acceso desde el panel de usuarios.
- **Sin módulo de compras ni de proveedores.** Las entradas se registran con el motivo como texto libre.
- **Exportación limitada a los reportes actuales.** No hay exportación del historial completo a CSV ni PDF.

---

## Autor

Samuel Arango — Trabajo de grado

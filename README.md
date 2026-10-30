# SIGECI Univalle — Backend

Backend del sistema de gestión de una conferencia científica, desarrollado como parte del proyecto académico de Desarrollo de Software I.

## 1. Tecnologías del entorno local

| Tecnología | Versión |
|---|---|
| Python | 3.14.8 |
| Django | 5.2.18 |
| Django REST Framework | 3.18.3 |
| PostgreSQL | 18.6 |
| Psycopg | 3.3.6 |
| Node.js | 24.21.0 |
| npm | 11.19.0 |
| Git | 2.55.0.windows.2 |

Las versiones corresponden al entorno local verificado durante la configuración inicial. La configuración definitiva del equipo deberá mantenerse sincronizada con los acuerdos del proyecto.

## 2. Requisitos previos

- Python 3.14.8.
- Git.
- PostgreSQL 18.
- Node.js 24 LTS, para las herramientas del frontend.
- Visual Studio Code u otro editor compatible.

## 3. Preparación del entorno de Python

Desde la raíz del proyecto, crear un entorno virtual:

```powershell
py -3.14 -m venv .venv
```

Activarlo en Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Actualizar pip:

```powershell
python -m pip install --upgrade pip
```

Instalar las dependencias registradas:

```powershell
python -m pip install -r requirements.txt
```

## 4. Verificación de dependencias y configuración

Comprobar la versión de Python:

```powershell
python --version
```

Comprobar la instalación de Django:

```powershell
python -m django --version
```

Verificar las dependencias:

```powershell
python -m pip check
```

### Variables de entorno

Crear el archivo `.env` en la raíz del proyecto tomando como referencia `.env.example`.

Para desarrollo local, configurar:

```env
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
```

En producción, establecer `DJANGO_DEBUG=False` y configurar `DJANGO_ALLOWED_HOSTS` con los dominios autorizados para acceder a la aplicación.

No se debe utilizar `DEBUG=True` ni el comodín `*` en producción.

Comprobar la configuración de Django:

```powershell
python manage.py check
```

Aplicar las migraciones iniciales:

```powershell
python manage.py migrate
```

Iniciar el servidor de desarrollo:

```powershell
python manage.py runserver
```

La aplicación estará disponible localmente en `http://127.0.0.1:8000/`.

## 5. Archivos del repositorio

- `.gitignore`: excluye el entorno virtual y archivos locales o sensibles.
- `requirements.txt`: registra las dependencias de Python.
- `README.md`: documenta la preparación del entorno.
- `manage.py`: permite ejecutar tareas administrativas de Django.
- `config/`: contiene la configuración principal del proyecto Django.

## 6. Estado de configuración

La instalación inicial de las herramientas y la preparación del entorno virtual se encuentran verificadas en el equipo de desarrollo.

El proyecto Django fue inicializado y se configuró la conexión con PostgreSQL. La ejecución de las migraciones iniciales permitió preparar las tablas internas requeridas por Django.

La implementación de endpoints y funcionalidades de negocio se desarrollará posteriormente de acuerdo con el cronograma del proyecto.

Las credenciales de conexión a la base de datos deben mantenerse fuera del repositorio y no deben publicarse en GitHub.

## 7. Proyecto académico

Asignatura: Desarrollo de Software I
Proyecto: Sistema de gestión de una conferencia científica
Universidad del Valle

## 8. API de autenticación local

El endpoint de login de SCRUM-18 está disponible en:

```text
POST /api/auth/login
GET /health
```

Configura estas variables en .env, ubicado en la raíz del proyecto, antes de iniciar el servidor:

```env
DJANGO_SECRET_KEY=clave-local-de-desarrollo
FRONTEND_ORIGIN=http://localhost:5173
RECAPTCHA_SECRET_KEY=clave-secreta-de-Google
DEMO_USER_EMAIL=demo@sigeci.local
DEMO_USER_PASSWORD=DemoPass123!
```

`RECAPTCHA_SECRET_KEY` solo se utiliza en el backend. El frontend debe usar
únicamente la clave pública (`VITE_RECAPTCHA_SITE_KEY`). Las credenciales
`DEMO_USER_*` son temporales para pruebas locales, hasta integrar el sistema de
usuarios real.
# Reglas Estrictas de Backend para Agentes IA — SIGECI (`sigeci_backend`)

Estas reglas son **obligatorias** para cualquier agente de IA que escriba o modifique código en `sigeci_backend`. El objetivo es mantener un estándar único en todo el equipo sin arquitecturas aisladas.

## 1. Fuente Única de Verdad: `deploy/schema.sql`
1. **Revisión obligatoria:** Antes de tocar cualquier endpoint, consulta SQL o modelo, **lee siempre `deploy/schema.sql`**.
2. **Prohibido inventar columnas o tablas:** No agregues campos ni tablas que no existan en `deploy/schema.sql`.
3. **Si consideras necesario un campo nuevo:**
   - **DETENTE y pregunta primero al usuario** explicando la necesidad.
   - Solo si el usuario lo aprueba explícitamente, créalo y **documéntalo inmediatamente en `deploy/schema.sql`** siguiendo el estándar `<tabla>_<campo>`, `<tabla>_active`, `<tabla>_delete` y auditoría (`_created_by`, `_created_at`, `_updated_by`, `_updated_at`).

## 2. Contrato Estricto y Cero Fallbacks
1. **PROHIBIDO usar fallbacks o alias** para aceptar múltiples nombres de campos (ej. `data.get("article_subject") or data.get("title")`, `data.get("refresh_token") or data.get("refresh")`).
2. Los nombres de entrada y salida deben ser **exactamente** los de `deploy/schema.sql`.
3. Para tokens JWT, los **únicos** nombres válidos en todo el proyecto son `token` y `refresh_token` (**prohibido** `access` y `refresh`).

## 3. Arquitectura Estándar de Vistas y Permisos (Referencia: `article/`)
Toma siempre `article/views.py`, `article/urls.py` y `util/auth_service.py` como plantilla obligatoria:

1. **Enrutamiento:** Todo módulo se publica bajo `path('api/v1/', include('<modulo>.urls'))` en `config/urls.py` usando `re_path` con `/?$`.
2. **Permisos y Autenticación (`util/auth_service.py`):**
   - **Funciones:** usar `@require_permission(endpoint="<modulo>", action="<accion>")`.
   - **Clases DRF:** heredar **siempre** de `SigeciAPIView` (`from util.auth_service import SigeciAPIView, require_permission_drf`) y decorar cada método (`get`, `post`, `put`, `patch`, `delete`) con `@require_permission_drf(endpoint="<modulo>", action="<accion>")`.
   - **PROHIBIDO:** usar `APIView` crudo con `AllowAny`/`IsAuthenticated`, `ModelViewSet`, o crear clases de autenticación/permisos paralelas.
   - `request.user` contiene `{"user_id": ..., "profile_id": ..., "user_seed_token": ...}`.
3. **Consultas SQL:** Usar `queryDB(sql, params)` de `util.utilDB` y segmentar por `str(request.user.get("profile_id"))` (`"1"` Admin, `"2"` Reviewer, `"3"` Author) tal como en `article/views.py`.
4. **Respuesta JSON estándar:**
   ```python
   {"success": True, "message": "...", "data": ...}
   ```

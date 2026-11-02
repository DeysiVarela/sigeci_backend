# Contratos de la API – Autenticación y usuarios (SCRUM-15, 16, 61, 62)

Base: `/api`. Formato JSON. Autenticación: `Authorization: Bearer <access>` (JWT).
Errores comunes: `401` sin token o token inválido · `403` sin permiso (`"No tienes permiso para realizar esta acción."`) · `429` límite de peticiones.

## 1. Autenticación

### `POST /api/auth/login` (también con `/` final)
Cuerpo: `{ "identifier": "correo", "password": "...", "captchaToken": "..." }`
(`email` se acepta como alias de `identifier`). Límite: 10/min.

| Código | Respuesta |
|---|---|
| 200 | `{ access, refresh, user }` donde `user` = `{ id, name, lastname, email, provider, profile, profile_name, active, created_at, updated_at, permissions }` |
| 400 | Campo faltante (`{"identifier": [...]}`) o CAPTCHA inválido/ausente (`{"detail": "Verificación CAPTCHA inválida o vencida."}`) |
| 401 | `{"detail": "Credenciales inválidas."}` (mismo mensaje para correo inexistente, cuenta inactiva/borrada o clave incorrecta) |
| 503 | CAPTCHA obligatorio pero `RECAPTCHA_SECRET_KEY` no configurada |

El CAPTCHA se valida con Google (`RECAPTCHA_SECRET_KEY`, misma verificación que `auth_api`) **antes** de revisar credenciales. Es obligatorio salvo `CAPTCHA_REQUIRED=False` en desarrollo; con `DEBUG` apagado no se puede desactivar.

### `POST /api/auth/refresh/`
`{ "refresh": "..." }` → `200 { access }` · `401 {"detail": "Token inválido o vencido."}`.
Vigencias: access 30 min, refresh 1 día.

### `GET /api/auth/me/`
→ `200` mismo objeto `user` del login (con `permissions`).

### `POST /api/auth/password/forgot/` – paso 1
`{ "email": "..." }` → **siempre** `200 {"detail": "Si el correo corresponde a una cuenta activa, recibirás un PIN para restablecer tu contraseña."}`,
exista o no la cuenta, esté o no activa y aunque falle el envío (no permite distinguir correos registrados). `400` solo por formato de correo inválido. Límite: 5/min.

### `POST /api/auth/password/reset/` – paso 2
`{ "email": "...", "pin": "123456", "password": "NuevaClave1!" }`

| Código | Respuesta |
|---|---|
| 200 | `{"detail": "Contraseña actualizada. Ya puedes iniciar sesión."}` |
| 400 | `{"detail": "PIN inválido, vencido o ya utilizado."}` (PIN incorrecto, vencido, usado, de otra cuenta o con intentos agotados) o errores de campo (formato de PIN, regla de contraseña) |

## 2. Parámetros del PIN y reglas de contraseña (CA-06)
**Valores propuestos; pendientes de aprobación del Product Owner** (ver `aprobaciones-po.md`). Se definen en `config/settings.py` (`PASSWORD_RESET_*`).

| Parámetro | Valor |
|---|---|
| Longitud | 6 dígitos |
| Vigencia | 10 minutos |
| Intentos fallidos por PIN | 5 (luego se invalida) |
| Reenvío | 1 solicitud cada 60 s por cuenta; un PIN nuevo invalida el anterior |
| Uso | Un solo uso; se guarda hasheado |
| Contraseña | ≥ 8 caracteres, mayúscula, minúscula, número y carácter especial (`@$!%*?&._-#^()+=`) + validadores de Django (longitud mínima, contraseñas comunes, solo numéricas) |
| Envío | `notifications.send_recovery_pin_email` (SendGrid); en desarrollo sin credenciales el correo se imprime en la consola del servidor |

## 3. Usuarios
Requieren autenticación y permiso según la matriz (sección 4). Los usuarios con borrado lógico no aparecen en ningún endpoint.

### `GET /api/users/` — permiso `user:view`
Query: `page` (1), `page_size` (10, máx. 100), `profile` (id numérico de rol), `active` (`true`|`false`). Los filtros son independientes y, usados juntos, se combinan con **Y**. Sin filtros: todos los usuarios no borrados, ordenados por id.
`200 { count, next, previous, results: [user] }` · `400` si `profile` no es numérico o `active` no es `true`/`false`.

### `POST /api/users/` — permiso `user:create`
`{ name (≤60), lastname (≤60), email (≤120, único sin distinguir mayúsculas), password, profile (id de rol activo), active (opcional, true) }`
`201` → `user` (sin contraseña) · `400` errores por campo; si falla no se persiste nada.

### `GET /api/users/{id}/` — permiso `user:view`
`200 user` · `404` si no existe o está borrado.

### `PATCH|PUT /api/users/{id}/` — permiso `user:update`
Campos: `name`, `lastname`, `email`, `profile`, `active`. La contraseña no se edita aquí (se usa la recuperación).
- Cambiar `profile` exige además `user_role:update`; cambiar `active` exige `user:active` / `user:inactive`.
- No se puede cambiar el propio rol ni desactivarse a sí mismo, ni quitar el rol o desactivar al único ADMIN activo (`400`).
- `200 user` · `403` sin autorización · `400` validación (sin cambios parciales).

### `DELETE /api/users/{id}/` — permiso `user:delete`
**Borrado lógico**: `user_delete = true` y `user_active = false`. No se elimina la fila, por lo que se respeta la integridad referencial (p. ej. `article_reviewer.user_id`). El usuario deja de poder iniciar sesión.
`204` · `400` si es la propia cuenta o el único ADMIN activo · `404`.

### `GET /api/profiles/` — permiso `user:view`
`200 [ { id, name } ]` (roles activos, para los selectores).

## 4. Matriz de permisos inicial (`seed_accounts`)
Recursos de este alcance: `user` y `user_role`. Los de `article`, `event` y `application` son **supuestos provisionales** de otros módulos.

| Perfil | user | user_role | article | event | application |
|---|---|---|---|---|---|
| ADMIN | view, create, update, delete, active, inactive | update | todos | view, create, update, delete, active, inactive | todos |
| MEMBER | — | — | view, download | view | view |
| AUTHOR | — | — | view, create, update, download | view | view, create, update |

La autorización se valida en el servidor en cada endpoint (`HasProfilePermission`); los permisos que el frontend lee de `/auth/me/` son solo informativos.

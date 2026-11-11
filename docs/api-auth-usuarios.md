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

### `POST /api/auth/register/` – registro público (SCRUM-120)
Público (no requiere token; funciona con o sin `/` final). Límite: 5/min por IP.
Cuerpo: `{ "name", "lastname", "email", "password", "captchaToken" }`: los mismos datos que crear usuario, sin el rol, más el token del CAPTCHA. La confirmación de contraseña se valida en la pantalla; cualquier otro campo (incluido `confirmPassword`) se ignora.
**El rol no se elige: siempre se crea con rol `AUTHOR`.** Si la petición trae un valor en `profile`, `profile_id`, `profile_name`, `role`, `role_id`, `rol`, `perfil` o `user_role`, se rechaza con `400` (nunca se usa).

| Código | Respuesta |
|---|---|
| 201 | `{ "detail": "Cuenta creada. Ya puedes iniciar sesión.", "user": { id, name, lastname, email, provider, profile, profile_name, active, created_at, updated_at } }` (no devuelve tokens: el usuario inicia sesión después) |
| 400 | Errores por campo (nombre/apellido vacíos o > 60, correo inválido, contraseña que no cumple las reglas, rol indicado) o `{"detail": "Verificación CAPTCHA inválida o vencida."}` |
| 409 | `{"detail": "Este correo ya está registrado.", "email": [...]}` (sin distinguir mayúsculas; no se duplica ni se modifica la cuenta existente) |
| 503 | CAPTCHA obligatorio sin clave configurada, o no existe el perfil `AUTHOR` (ejecutar `seed_accounts`) |

El correo de una cuenta eliminada (borrado lógico) sigue contando como registrado.
Orden de las comprobaciones: validar datos → CAPTCHA → correo duplicado → crear. Un error de formulario no consume el token de CAPTCHA, y un correo registrado solo se revela a quien pasó el CAPTCHA.
La contraseña se cifra con el hash de Django (**PBKDF2-SHA256**, el mismo de todo el sistema) y nunca se devuelve ni se registra en claro.

### `POST /api/auth/refresh/`
`{ "refresh": "..." }` → `200 { access }` · `401 {"detail": "Token inválido o vencido."}`.
Vigencias: access 30 min, refresh 1 día.

### `GET /api/auth/me/`
→ `200` mismo objeto `user` del login (con `permissions`).

### `POST /api/auth/password/forgot/` – paso 1
**Espera entre solicitudes: 60 s por correo** (se aplica igual exista o no la cuenta, y sin distinguir mayúsculas). Dentro de ese tiempo responde `429 {"detail": "Espera N segundos para solicitar un nuevo PIN.", "retry_after": N}` con la cabecera `Retry-After`, y no se envía nada. El PIN solo se genera y envía si el correo pertenece a una cuenta registrada y activa.
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
| Reenvío | 1 solicitud cada 60 s por correo (`429` con `retry_after` si se repite antes); un PIN nuevo invalida el anterior |
| Uso | Un solo uso; se guarda hasheado |
| Contraseña | ≥ 8 caracteres, mayúscula, minúscula, número y carácter especial (`@$!%*?&._-#^()+=`) + validadores de Django (longitud mínima, contraseñas comunes, solo numéricas) |
| Envío | `notifications.send_recovery_pin_email` (SendGrid); en desarrollo sin credenciales el correo se imprime en la consola del servidor |

## 3. Usuarios
Requieren autenticación y permiso según la matriz (sección 4). Los usuarios con borrado lógico no aparecen en ningún endpoint.

### `GET /api/users/` — permiso `user:view`
Query: `page` (1), `page_size` (10, máx. 100), `profile` (id numérico de rol), `active` (`true`|`false`). Los filtros son independientes y, usados juntos, se combinan con **Y**. Sin filtros: todos los usuarios no borrados, ordenados por id.
`200 { count, next, previous, results: [user] }` · `400` si `profile` no es numérico o `active` no es `true`/`false`.

### `POST /api/users/` — permiso `user:create`
Un usuario que no es ADMIN (p. ej. MEMBER, el comité científico) no puede crear usuarios con rol ADMIN (`403`).
`{ name (≤60), lastname (≤60), email (≤120, único sin distinguir mayúsculas), password, profile (id de rol activo), active (opcional, true) }`
`201` → `user` (sin contraseña) · `400` errores por campo; si falla no se persiste nada.

### `GET /api/users/{id}/` — permiso `user:view`
`200 user` · `404` si no existe o está borrado.

### `PATCH|PUT /api/users/{id}/` — permiso `user:update`
Campos: `name`, `lastname`, `email`, `profile`, `active`. La contraseña no se edita aquí (se usa la recuperación).
- Cambiar `profile` exige además `user_role:update`; cambiar `active` exige `user:active` / `user:inactive`.
- Solo un ADMIN puede asignar el rol ADMIN, y solo un ADMIN puede modificar cuentas de administradores (`403`).
- No se puede cambiar el propio rol ni desactivarse a sí mismo, ni quitar el rol o desactivar al único ADMIN activo (`400`).
- `200 user` · `403` sin autorización · `400` validación (sin cambios parciales).

### `DELETE /api/users/{id}/` — permiso `user:delete`
**Borrado lógico**: `user_delete = true` y `user_active = false`. No se elimina la fila, por lo que se respeta la integridad referencial (p. ej. `article_reviewer.user_id`). El usuario pierde el acceso: no puede iniciar sesión, sus tokens dejan de servir, no recibe PIN de recuperación y desaparece de todos los endpoints. Su correo sigue reservado.
`204` · `400` si es la propia cuenta o el único ADMIN activo · `403` si la cuenta es de un administrador y quien elimina no lo es · `404`.

### `GET /api/profiles/` — permiso `user:view`
`200 [ { id, name } ]` (roles activos, para los selectores).

### `GET /api/users/me` y `PATCH /api/users/me` — mi perfil (SCRUM-125)
Requieren estar autenticado, **no** piden permisos de la matriz (cada usuario gestiona su propio perfil) y solo operan sobre el usuario de la sesión: no reciben ningún id. Funcionan con o sin `/` final. `PUT` y `DELETE` responden `405`.
- `GET` → `200` con la misma forma que `/api/auth/me/`: `{ id, name, lastname, email, provider, profile, profile_name, active, created_at, updated_at, permissions }`.
- `PATCH` (parcial) acepta `name` (≤60), `lastname` (≤60) y `email` (≤120, único sin distinguir mayúsculas; se puede enviar el propio). **El rol, el estado, el proveedor y la contraseña no se pueden cambiar aquí: esas claves se descartan.** → `200` con el usuario actualizado (misma forma que el `GET`, incluidos los permisos) · `400` errores por campo.
- La pantalla de perfil solo maneja nombre, apellido y correo, que son los datos que guarda el modelo.

### `PUT /api/users/me/password/` — cambiar mi contraseña (SCRUM-125)
Cuerpo: `{ "currentPassword", "newPassword" }`. La confirmación se valida en la pantalla; si llega `confirmPassword`, se ignora. Límite: 5 intentos por minuto por usuario (`429`).

| Código | Respuesta |
|---|---|
| 200 | `{"detail": "Contraseña actualizada."}` |
| 400 | `currentPassword` incorrecta (es **400 y no 401** para que el frontend no cierre la sesión), `newPassword` que no cumple las reglas o igual a la actual, o cuenta sin contraseña propia (proveedor distinto de ACCOUNT) |
| 401 | sin token válido |

Efectos: la contraseña se cifra con el hash de Django (PBKDF2-SHA256) y los PIN de recuperación pendientes dejan de servir. Los tokens ya emitidos siguen vigentes hasta su vencimiento (no hay lista de revocación).

## 4. Matriz de permisos inicial (`seed_accounts`)
Recursos de este alcance: `user` y `user_role`. Los de `article`, `event` y `application` son **supuestos provisionales** de otros módulos.

| Perfil | user | user_role | article | event | application |
|---|---|---|---|---|---|
| ADMIN | view, create, update, delete, active, inactive | update | todos | view, create, update, delete, active, inactive | todos |
| MEMBER (comité científico) | view, create, update, delete, active, inactive (no sobre administradores ni rol ADMIN) | update | view, download | view | view |
| AUTHOR | — | — | view, create, update, download | view | view, create, update |

La autorización se valida en el servidor en cada endpoint (`HasProfilePermission`); los permisos que el frontend lee de `/auth/me/` son solo informativos.

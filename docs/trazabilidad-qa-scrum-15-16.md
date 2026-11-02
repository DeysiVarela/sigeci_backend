# Trazabilidad QA – SCRUM-15 y SCRUM-16

Estados: **Auto** = prueba automatizada que pasa · **Simulada** = automatizada pero con servicio externo simulado · **Pendiente** = falta evidencia o decisión.
Pruebas: `python manage.py test accounts notifications auth_api`.
Archivos: `accounts/tests.py` (T), `accounts/tests_qa.py` (Q), `accounts/tests_captcha_live.py` (L, contra Google, se activa con `RUN_LIVE_CAPTCHA_TESTS=1`).

## SCRUM-15 – Inicio de sesión y recuperación en dos pasos
| CA | Criterio | Pruebas | Estado |
|---|---|---|---|
| 01 | Credenciales válidas autentican; inválidas dan error controlado | T `AuthTests.test_login_ok_and_bad`, T `LoginContractTests` (identifier, con/sin `/`, alias `email`, campo faltante, ruta real = JWT) | Auto |
| 02 | CAPTCHA validado antes de conceder acceso | T `LoginContractTests.test_captcha_*` (desactivado, obligatorio, sin clave → 503, rechazado/aceptado); L pruebas contra Google | **Simulada** – falta ejecutar L y la prueba manual con claves reales |
| 03 | PIN temporal para cuenta elegible, asociado a la solicitud, enviado por el servicio de correo; respuesta no revela si el correo existe | T `PasswordRecoveryTests.test_full_flow_and_pin_single_use` (respuestas idénticas), `test_email_failure_does_not_leak`; `notifications.tests` | Simulada – envío real por SendGrid pendiente de evidencia |
| 04 | PIN solo sirve para su cuenta/solicitud; incorrecto, vencido o usado se rechaza | T `test_wrong_pin_and_attempt_limit`, T `test_full_flow_and_pin_single_use` (usado); Q `test_expired_pin_is_rejected`, `test_pin_is_valid_before_expiry`, `test_pin_of_another_account_is_rejected`, `test_resend_after_cooldown_invalidates_previous_pin` | Auto |
| 05 | Nueva clave hasheada, PIN inutilizable, login solo con la nueva | T `test_full_flow_and_pin_single_use`, T `test_pin_stored_hashed`; Q `test_weak_password_is_rejected_without_consuming_pin` | Auto |
| 06 | Longitud/vigencia del PIN, intentos, reenvío y reglas de clave documentados y aplicados | Documentado en `api-auth-usuarios.md` §2. Aplicados: Q `test_pin_lifetime_and_length_follow_settings`, `test_resend_within_cooldown_*`, T `test_wrong_pin_and_attempt_limit`, T `test_create_validations_and_unique_email` (reglas de clave) | Auto – **valores pendientes de aprobación del PO** (`aprobaciones-po.md` A) |
| 07 | Contratos documentados y evidencia de login exitoso/fallido, recuperación exitosa, rechazo de PIN incorrecto/vencido/reutilizado; sin exponer claves ni PIN | Contratos: `api-auth-usuarios.md` §1; pruebas anteriores; T `test_login_response_has_no_secrets`; Q `test_responses_never_expose_secrets` | Auto + documentado. Falta adjuntar salida de pruebas/capturas (ver abajo) |

## SCRUM-16 – CRUD de usuarios con control por roles (HU 61 y 62)
| CA | Criterio | Pruebas | Estado |
|---|---|---|---|
| 01 | Operaciones documentadas (crear, listar, detalle, actualizar, eliminar) | `api-auth-usuarios.md` §3 | Documentado |
| 02 | Validación de obligatorios, formatos y unicidad; sin cambios parciales | T `test_create_validations_and_unique_email`; Q `test_update_with_duplicate_email_is_rejected_and_not_persisted` | Auto |
| 03 | Dos filtros (rol y estado), por separado y combinados; sin filtros lista lo permitido | T `UserCrudTests.test_list_pagination_and_filters` | Auto – filtros pendientes de confirmar con el PO |
| 04 | Autenticación y autorización en el servidor según matriz | T `AuthTests.test_requires_token`, T `test_member_is_forbidden_even_calling_endpoint_directly`; Q `test_role_change_requires_explicit_permission` | Auto – **matriz pendiente de aprobación del PO** |
| 05 | Eliminación según lo acordado, respetando integridad referencial | T `test_soft_delete_and_self_delete_blocked` (borrado lógico, 404 posterior, no puede entrar) | Auto – comportamiento pendiente de confirmar con el PO |
| 06 | Sin contraseñas/hashes/PIN en respuestas; cambios de rol solo con autorización explícita | Q `test_responses_never_expose_secrets`, Q `test_role_change_requires_explicit_permission`, T `test_update_role_and_status` | Auto |
| 07 | Evidencia de CRUD, uso individual y combinado de filtros, validación y rechazo sin permiso | Pruebas anteriores + capturas | Auto – falta adjuntar salida/capturas |

## Evidencia a adjuntar (siguiendo la numeración E0x que ya usa `docs/`)
1. Salida de pruebas: `python manage.py test accounts notifications auth_api -v 2` (sin `.env` ni claves).
2. Salida de `RUN_LIVE_CAPTCHA_TESTS=1 python manage.py test accounts.tests_captcha_live` con las claves reales.
3. Capturas del navegador: login exitoso (respuesta con `access`/`refresh`), login fallido, CAPTCHA no resuelto, recuperación completa con el correo recibido, PIN incorrecto/vencido/reutilizado, CRUD y filtros.
4. Decisiones firmadas del PO (`aprobaciones-po.md`).

## Pendientes abiertos
- Aprobación del PO: parámetros del PIN, matriz de permisos, filtros y eliminación.
- Verificación real de reCAPTCHA y del envío por SendGrid.
- `docs/recaptcha.md` describe el login de demostración de `auth_api`; `/api/auth/login` es ahora el login real (JWT). Coordinar con quien lo mantiene.

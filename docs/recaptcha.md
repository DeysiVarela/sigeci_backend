
# Contrato de verificación de CAPTCHA — SCRUM-14

## 1. Objetivo

Definir el contrato de verificación de Google reCAPTCHA v2 en el backend de SIGECI, para evitar que el inicio de sesión dependa únicamente de una validación realizada en el navegador.

## 2. Proveedor y modalidad

- **Proveedor:** Google reCAPTCHA.
- **Modalidad:** reCAPTCHA v2.
- **Verificación:** servidor a servidor.
- **URL del proveedor:** `https://www.google.com/recaptcha/api/siteverify`.
- **Variable de entorno:** `RECAPTCHA_SECRET_KEY`.

La clave secreta debe configurarse en el entorno del backend. No debe incluirse en el frontend, el repositorio ni los registros de diagnóstico.

## 3. Endpoint protegido

- **Método:** `POST`.
- **Ruta:** `/api/auth/login`.
- **Formato:** JSON.
- **Operación protegida:** inicio de sesión.

## 4. Solicitud del cliente

El cliente debe enviar el identificador, la contraseña y el token de CAPTCHA:

```json
{
  "identifier": "usuario@ejemplo.com",
  "password": "CONTRASEÑA",
  "captchaToken": "TOKEN_GENERADO_POR_RECAPTCHA"
}
```

### Campos

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `identifier` | String | Sí | Identificador del usuario. |
| `password` | String | Sí | Contraseña del usuario. |
| `captchaToken` | String | Sí | Token generado por reCAPTCHA en el cliente. |

El token no sustituye la autenticación del usuario ni demuestra por sí solo que sus credenciales sean correctas.

## 5. Proceso de verificación

1. El backend recibe la solicitud de inicio de sesión.
2. Comprueba que estén presentes el identificador, la contraseña y el token.
3. Obtiene `RECAPTCHA_SECRET_KEY` de las variables de entorno.
4. Envía el token y la clave secreta al endpoint de verificación de Google mediante una solicitud HTTP POST.
5. Espera la respuesta del proveedor, con un tiempo máximo de espera de 10 segundos.
6. Si Google devuelve `success: true`, el backend continúa con la validación de las credenciales.
7. Si el CAPTCHA es rechazado o la verificación no puede completarse, el backend rechaza la operación.

La aplicación no debe aceptar como prueba suficiente un indicador de éxito enviado únicamente por el navegador.

## 6. Respuestas del backend

Las respuestas siguientes describen el comportamiento actual de `POST /api/auth/login`.

| Estado HTTP | Situación | Mensaje esperado |
|---|---|---|
| `200 OK` | CAPTCHA válido y credenciales aceptadas | `Inicio de sesión exitoso.` |
| `400 Bad Request` | Faltan datos obligatorios | `Correo, contraseña y CAPTCHA son obligatorios.` |
| `400 Bad Request` | CAPTCHA inválido o verificación fallida | `La verificación CAPTCHA no es válida. Inténtalo nuevamente.` |
| `401 Unauthorized` | Credenciales incorrectas | `Las credenciales no son válidas.` |
| `503 Service Unavailable` | Falta la clave secreta | `El servicio de autenticación no está disponible.` |
| `405 Method Not Allowed` | Método HTTP no permitido | `Método no permitido.` |

Si Google no responde o se produce un error de comunicación, la aplicación rechaza el CAPTCHA con un mensaje controlado, sin exponer detalles internos.

## 7. Configuración del entorno

El backend requiere la siguiente variable:

```text
RECAPTCHA_SECRET_KEY=<clave_secreta_configurada_en_el_entorno>
```

La clave real debe mantenerse fuera del control de versiones y no debe compartirse en documentación pública, capturas de pantalla ni respuestas de la API.

La clave pública o *site key* corresponde al frontend y es independiente de la clave secreta del servidor.

## 8. Pruebas automatizadas

Las pruebas de `auth_api/tests.py` cubren los siguientes escenarios:

| Escenario | Resultado esperado |
|---|---|
| Endpoint de salud | Respuesta `200 OK`. |
| Solicitud sin datos obligatorios | Respuesta `400`. |
| CAPTCHA rechazado | Respuesta `400`. |
| CAPTCHA válido y credenciales correctas | Respuesta `200`. |
| Proveedor no disponible | Respuesta `400` controlada. |
| Clave secreta ausente | Respuesta `503`. |
| Token CAPTCHA ausente | Respuesta `400`. |

Las pruebas automatizadas simulan la respuesta de Google. Por tanto, sus resultados no sustituyen una prueba de integración con credenciales reales.

## 9. Evidencias pendientes

Para completar el criterio de aceptación CA-06, se deben conservar evidencias de:

- [ ] Token válido.
- [ ] Token ausente.
- [ ] Token rechazado o inválido.
- [ ] Proveedor no disponible.

Se pueden utilizar los resultados de las pruebas automatizadas y complementarlos con evidencias de la integración real cuando esté configurada.

## 10. Alcance y limitaciones

Esta historia cubre la validación de CAPTCHA en el backend para el inicio de sesión.

La presentación del widget en el navegador corresponde a SCRUM-18.

La incorporación de CAPTCHA a otras operaciones protegidas queda pendiente de definición por el equipo.

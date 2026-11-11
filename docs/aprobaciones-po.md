# Aprobaciones pendientes del Product Owner – SCRUM-15 y SCRUM-16

Estado: **pendiente**. Los valores de abajo fueron propuestos por desarrollo; ninguno está aprobado todavía.
Cuando se decida, completar la columna de decisión y enlazar este archivo en el PR/ticket.

## A. Parámetros del PIN de recuperación (SCRUM-15, CA-06)
| Parámetro | Propuesta | Decisión (☐ Aprobado / ☐ Cambio) | Valor final |
|---|---|---|---|
| Longitud | 6 dígitos | ☐ / ☐ | |
| Vigencia | 10 minutos | ☐ / ☐ | |
| Intentos fallidos | 5 por PIN | ☐ / ☐ | |
| Reenvío | cada 60 s; el nuevo PIN invalida el anterior | ☐ / ☐ | |
| Uso | un solo uso, guardado hasheado | ☐ / ☐ | |
| Reglas de contraseña | ≥ 8, mayúscula, minúscula, número y especial | ☐ / ☐ | |

## B. Matriz de permisos (SCRUM-16, CA-04)
Solo `user` y `user_role` corresponden a este alcance; el resto es provisional y debe definirse con cada módulo.
| Perfil | user | user_role | article | event | application |
|---|---|---|---|---|---|
| ADMIN | view, create, update, delete, active, inactive | update | todos | view, create, update, delete, active, inactive | todos |
| MEMBER (comité científico) | view, create, update, delete, active, inactive (no sobre administradores ni rol ADMIN) | update | view, download | view | view |
| AUTHOR | — | — | view, create, update, download | view | view, create, update |

Decisión: ☐ Aprobada ☐ Con cambios: ____________________

## C. Otras decisiones de SCRUM-16 a confirmar
| Tema | Propuesta | Decisión |
|---|---|---|
| Filtros del listado | rol (`profile`) y estado (`active`) | ☐ |
| Eliminación | borrado lógico (el usuario pierde el acceso y su registro se conserva); no se puede eliminar la propia cuenta ni al único ADMIN activo | ☐ |
| Campos editables | nombre, apellido, correo, rol y estado (la contraseña solo por recuperación) | ☐ |
| Comité científico (rol MEMBER) | gestiona usuarios; no crea ni modifica administradores ni asigna el rol ADMIN | ☐ |
| Consulta y edición propia | pendiente: la regla del PO dice que todos consultan y cada usuario edita sus propios datos; hoy solo ADMIN y MEMBER (comité) consultan | ☐ |
| Espera de reenvío del PIN | 60 s por correo, visible para el usuario (`429` con `retry_after`) | ☐ |
| Registro público (SCRUM-120) | rol AUTHOR siempre; un rol en la petición se rechaza (400); correo repetido responde 409 con mensaje claro (revela que el correo existe) | ☐ |
| Hash de contraseñas (CA-07 de SCRUM-120) | el criterio dice bcrypt o argon2; el equipo decidió mantener el hash de Django (PBKDF2-SHA256) para todo el sistema | ☐ |
| Verificación de correo | el registro NO exige confirmar el correo: la cuenta queda activa al crearse | ☐ |
| Mi perfil (SCRUM-125) | cada usuario edita solo su nombre, apellido y correo; el rol, el estado y el proveedor no se editan; el correo se cambia sin verificación | ☐ |
| Cambio de contraseña | pide la contraseña actual; no cierra las demás sesiones (los tokens ya emitidos siguen vigentes hasta vencer) | ☐ |
| Vigencia de sesión | access 30 min, refresh 1 día | ☐ |

Aprobado por: ______________________  Fecha: ____________

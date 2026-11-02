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
| MEMBER | — | — | view, download | view | view |
| AUTHOR | — | — | view, create, update, download | view | view, create, update |

Decisión: ☐ Aprobada ☐ Con cambios: ____________________

## C. Otras decisiones de SCRUM-16 a confirmar
| Tema | Propuesta | Decisión |
|---|---|---|
| Filtros del listado | rol (`profile`) y estado (`active`) | ☐ |
| Eliminación | borrado lógico; no se puede eliminar la propia cuenta ni al único ADMIN activo | ☐ |
| Campos editables | nombre, apellido, correo, rol y estado (la contraseña solo por recuperación) | ☐ |
| Vigencia de sesión | access 30 min, refresh 1 día | ☐ |

Aprobado por: ______________________  Fecha: ____________

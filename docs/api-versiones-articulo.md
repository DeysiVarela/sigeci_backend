# API · Versiones del artículo y avales (SCRUM-30 / SCRUM-31)

Base: `/api/articles/{id}/...` (sin `/v1`). Autenticación: `Authorization: Bearer <access>`.
Cada ruta exige **tres cosas**, todas en el servidor: sesión válida (401), permiso de la matriz `profile_action` (403) y una regla sobre el artículo (403). El frontend solo oculta botones.

| Ruta | Matriz | Regla sobre el artículo |
|---|---|---|
| `GET  corrected-version/` | `article:view` | autor del artículo, comité (ADMIN/MEMBER) o evaluador asignado activo |
| `POST corrected-version/` | `article:update` | solo el **autor dueño** |
| `POST final-submission/` | `article:update` | solo el **autor dueño** |
| `POST aval-presentation/` | `evaluation:update` | comité o evaluador asignado; **no** el autor |
| `POST aval-publication/` | `evaluation:update` | comité o evaluador asignado activo; **no** el autor |

Los permisos se leen con `User.has_perm_on` (consideran todos los roles). Sin fila en la matriz = 403.

## GET corrected-version
`200` → `{article_id, article_subject, article_description, article_copyright_url, corrected_version, versions}`.
`corrected_version` es la versión más reciente (o `null`); `versions`, el historial. Las URLs llegan **firmadas y vencen** (1 h).

## POST corrected-version (multipart)
Campo `corrected_pdf`: PDF real, máx. 10 MB (se valida el contenido `%PDF-`, no solo la extensión).
`201` `{detail, corrected_version}` · `400` archivo inválido · `401` · `403` · `404`.

## POST final-submission (multipart)
Campos `final_pdf` (PDF) y `copyright_pdf` (PDF, JPG o PNG), máx. 10 MB c/u, validados por contenido.
`201` `{detail, copyright_url}`.

## POST aval-presentation (JSON `{ "comment"?: string ≤ 1000 }`)
`200` → PDF "Constancia de Aval". `409` si el estado es `REJECTED` o `FOR_PUBLICATION`. Un comité no asignado crea su propia fila de evaluación sin tocar la de otros.

## POST aval-publication
Exige que el autor ya haya subido el copyright (`400` si no). `409` si la evaluación está `REJECTED`. `200` → PDF "Certificado de Publicación" con el `verification_code` (UUID único por artículo, estable entre emisiones).

## Almacenamiento
Los archivos van al bucket S3/Supabase de `util.uploads` (`SUPABASE_S3_*`). En la BD se guarda la **llave** (`corrected_versions/<uuid>.pdf`, `final_versions/…`, `copyrights/…`); el cliente no elige ruta ni extensión.

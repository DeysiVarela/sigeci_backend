"""
Almacenamiento de las versiones del artículo (SCRUM-30/31).

Usa el mismo bucket S3/Supabase de `util.uploads` (credenciales SUPABASE_S3_*), así que las URLs se
firman igual que el resto de adjuntos de `main`. En la BD se guarda la LLAVE (p. ej.
"corrected_versions/<uuid>.pdf"); la URL firmada se genera al consultar (`generate_download_url`).
"""
import uuid

from django.conf import settings

from util.uploads import uploads as storage

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def upload_version_file(file, folder, ext):
    """Sube `file` a <folder>/<uuid><ext> y devuelve la llave. `ext` ya viene validada (no la manda el cliente)."""
    ext = ext.lower()
    if ext not in CONTENT_TYPES:
        raise ValueError("Extensión no permitida.")
    key = f"{folder}/{uuid.uuid4()}{ext}"
    file.seek(0)
    storage.s3.upload_fileobj(
        file, settings.SUPABASE_BUCKET, key, ExtraArgs={"ContentType": CONTENT_TYPES[ext]}
    )
    return key


def download_url(key):
    """Llave -> URL firmada temporal. Las URLs absolutas se devuelven tal cual."""
    return storage.generate_download_url(key)

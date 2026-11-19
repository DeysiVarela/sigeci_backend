import os
import uuid
from django.core.files.storage import default_storage
from django.conf import settings

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def upload_file(file, folder: str) -> str:
    """
    Sube un archivo a Supabase Storage (Plan A) o lo guarda localmente (Plan B).
    Retorna la URL del archivo para guardarla en la base de datos.
    """
    file_extension = file.name.split('.')[-1]
    file_name = f"{folder}/{uuid.uuid4()}.{file_extension}"

    if SUPABASE_URL and SUPABASE_KEY:
        # --- PLAN A: SUPABASE (Cuando Bolivar pase las llaves) ---
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        file_content = file.read()
        supabase.storage.from_("sigeci_files").upload(
            file=file_content,
            path=file_name,
            file_options={"content-type": file.content_type}
        )
        return supabase.storage.from_("sigeci_files").get_public_url(file_name)
    else:
        # --- PLAN B: LOCAL (Para que programes HOY) ---
        print(f"⚠️ Guardando archivo localmente en /media/{file_name}")
        saved_path = default_storage.save(file_name, file)
        # Retorna la URL local (ej: /media/final_versions/123.pdf)
        return f"{settings.MEDIA_URL}{saved_path}"
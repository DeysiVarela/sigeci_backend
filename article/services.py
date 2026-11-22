import os
from django.conf import settings
from django.core.files.storage import FileSystemStorage

# Esta es una implementación básica. En el futuro se
# conectarán esto con Supabase Storage.
def upload_file(file, folder="uploads"):
    fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, folder))
    filename = fs.save(file.name, file)
    return fs.url(filename)
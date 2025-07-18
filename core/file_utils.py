import uuid
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

def upload_file(file, path_prefix='uploads/'):
    """
    Uploads a file to the default storage (S3 in production, local in dev).
    Returns the file URL.
    """
    ext = file.name.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = f"{path_prefix}{filename}"
    saved_path = default_storage.save(file_path, ContentFile(file.read()))
    return default_storage.url(saved_path) 
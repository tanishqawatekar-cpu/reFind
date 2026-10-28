"""
Secure Image Upload Service
Validates file extensions, magic-byte image headers, sanitizes filenames,
and assigns unique UUIDv4 prefixes before saving to `static/uploads/`.
"""

import os
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename
from config import Config

# Valid image magic bytes signatures (PNG, JPEG, WEBP)
MAGIC_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",       # JPEG / JPG
    b"RIFF",               # WEBP (starts with RIFF....WEBP)
)


def allowed_file(filename: str) -> bool:
    """Check if the filename has an allowed image extension."""
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in Config.ALLOWED_EXTENSIONS


def is_valid_image_header(file_storage) -> bool:
    """Inspect the first 12 bytes of the uploaded stream to verify image signature."""
    header = file_storage.stream.read(12)
    file_storage.stream.seek(0)
    if not header:
        return False
    if header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith(b"\xff\xd8\xff"):
        return True
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return True
    return False


def save_uploaded_image(file_storage, prefix: str = "item") -> str | None:
    """
    Validate and save an optional uploaded image.
    Returns the relative path under `static/` (e.g., `uploads/lost_a1b2c3d4_airpods.jpg`)
    for storage in MySQL, or None if no file was uploaded.
    Raises ValueError if the file is invalid.
    """
    if not file_storage or not file_storage.filename:
        return None

    original_name = secure_filename(file_storage.filename)
    if not allowed_file(original_name):
        raise ValueError("Invalid image format. Allowed formats: PNG, JPG, JPEG, WEBP.")

    if not is_valid_image_header(file_storage):
        raise ValueError("Uploaded file failed image signature validation.")

    ext = original_name.rsplit(".", 1)[1].lower()
    stem = Path(original_name).stem[:40] or "image"
    unique_filename = f"{prefix}_{uuid.uuid4().hex[:10]}_{stem}.{ext}"

    upload_dir = Path(Config.UPLOAD_FOLDER)
    upload_dir.mkdir(parents=True, exist_ok=True)

    full_path = upload_dir / unique_filename
    file_storage.save(str(full_path))

    return f"uploads/{unique_filename}"

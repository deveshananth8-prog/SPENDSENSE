"""Avatar upload validation, sanitization, and safe storage via Pillow."""

from __future__ import annotations

import io
import secrets
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
AVATAR_SIZE = (256, 256)


class AvatarValidationError(ValueError):
    pass


def process_and_save_avatar(raw_bytes: bytes, upload_dir: Path | None = None) -> str:
    """Validate image bytes with Pillow, strip metadata, center-crop 256x256, and save with random filename."""
    if not raw_bytes:
        raise AvatarValidationError("Please choose an image file to upload.")
    if len(raw_bytes) > MAX_AVATAR_BYTES:
        raise AvatarValidationError("Profile picture must be 2 MB or smaller.")

    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img_format = (img.format or "").upper()
            if img_format not in ALLOWED_IMAGE_FORMATS:
                raise AvatarValidationError("Only JPEG, PNG, or WebP images are allowed.")
            img.verify()

        with Image.open(io.BytesIO(raw_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            mode = "RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB"
            converted = img.convert(mode)
            fitted = ImageOps.fit(converted, AVATAR_SIZE, method=Image.Resampling.LANCZOS)
            # Reconstruct image purely from raw pixel bytes to strip all EXIF/text metadata
            clean = Image.frombytes(fitted.mode, AVATAR_SIZE, fitted.tobytes())
    except AvatarValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AvatarValidationError("That file does not appear to be a valid JPEG, PNG, or WebP image.") from exc

    target_dir = upload_dir or settings.avatar_upload_path
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_hex(16)}.webp"
    target_path = target_dir / filename
    clean.save(target_path, format="WEBP", quality=88, method=6)
    return filename


def delete_avatar_file(filename: str | None, upload_dir: Path | None = None) -> None:
    if not filename:
        return
    # Guard against path traversal
    safe_name = Path(filename).name
    target_dir = upload_dir or settings.avatar_upload_path
    path = target_dir / safe_name
    if path.is_file():
        path.unlink(missing_ok=True)

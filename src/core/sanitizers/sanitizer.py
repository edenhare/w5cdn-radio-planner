"""Data sanitization utilities for frequencies, text inputs, and file paths."""

from __future__ import annotations

import re
from pathlib import Path


class DataSanitizer:
    """Security and formatting sanitization for user inputs, CSV cells, and file operations."""

    CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")
    UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

    @classmethod
    def sanitize_text(cls, text: str, max_length: int = 255) -> str:
        """Strip control characters, sanitize whitespace, and enforce max length."""
        if not text:
            return ""
        # Remove control characters
        cleaned = cls.CONTROL_CHARS_PATTERN.sub("", text)
        # Collapse multiple whitespace to single space
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:max_length]

    @classmethod
    def sanitize_frequency(
        cls, freq: float | str, min_mhz: float = 1.0, max_mhz: float = 1300.0
    ) -> float:
        """Parse, validate, and clamp frequency in MHz."""
        try:
            val = float(freq)
        except (ValueError, TypeError) as err:
            raise ValueError(
                f"Invalid frequency value '{freq}': must be numeric."
            ) from err

        if val < min_mhz or val > max_mhz:
            raise ValueError(
                f"Frequency {val:.5f} MHz out of valid operational range [{min_mhz}, {max_mhz}] MHz."
            )
        return round(val, 5)

    @classmethod
    def validate_safe_path(
        cls, path_str: str | Path, base_dir: Path | None = None
    ) -> Path:
        """Protect against path traversal attacks and ensure target path resolves safely."""
        raw = Path(path_str)
        # Check for null bytes or suspicious characters
        if "\x00" in str(path_str):
            raise ValueError("Path contains illegal null bytes.")

        resolved = raw.resolve()
        if base_dir is not None:
            base_resolved = base_dir.resolve()
            try:
                resolved.relative_to(base_resolved)
            except ValueError as err:
                raise PermissionError(
                    f"Path traversal detected: {resolved} is outside {base_resolved}"
                ) from err

        return resolved

    @classmethod
    def sanitize_filename(cls, filename: str, fallback: str = "export") -> str:
        """Sanitize a filename by removing illegal filesystem characters."""
        cleaned = cls.UNSAFE_FILENAME_CHARS.sub("_", filename).strip(" ._")
        return cleaned if cleaned else fallback

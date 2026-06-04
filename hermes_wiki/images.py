from __future__ import annotations

import base64
import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BASE64_RE = re.compile(r"!\[([^\]]*)\]\(data:image/([^;]+);base64,([^)]+)\)")
_RELATIVE_RE = re.compile(r"!\[([^\]]*)\]\((?!https?://|data:)([^)]+)\)")
_MIN_IMAGE_DIM = 32
_MIN_VISIBLE_BBOX_AREA = 1.0


def _has_visible_bbox(block: dict[str, Any]) -> bool:
    """Return True when an image block occupies visible page area."""
    bbox = block.get("bbox")
    if not bbox or len(bbox) != 4:
        return False

    try:
        x0, y0, x1, y1 = (float(value) for value in bbox)
    except (TypeError, ValueError):
        return False

    width = x1 - x0
    height = y1 - y0
    if width <= 0 or height <= 0:
        return False

    return (width * height) >= _MIN_VISIBLE_BBOX_AREA


def load_pymupdf():
    try:
        import pymupdf
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyMuPDF is required for PDF ingest. Install pymupdf in the runtime environment."
        ) from exc
    return pymupdf


def _save_pdf_pixmap_image(
    pymupdf: Any,
    pix: Any,
    doc_name: str,
    images_dir: Path,
    page_num: int,
    image_counter: int,
) -> tuple[str, int]:
    """Save a PyMuPDF pixmap as PNG and return its wiki Markdown reference."""
    colorspace_channels = getattr(getattr(pix, "colorspace", None), "n", 0)
    # Some PDF JPEGs are 4-channel CMYK without alpha; PyMuPDF can decode them
    # but cannot encode them directly as PNG until we convert them to RGB.
    if pix.n > 4 or colorspace_channels == 4:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    image_counter += 1
    filename = f"p{page_num}_img{image_counter}.png"
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / filename).write_bytes(pix.tobytes("png"))
    pix = None
    return f"![image](sources/images/{doc_name}/{filename})", image_counter


def _extract_page_resource_images(
    page: Any,
    doc_name: str,
    images_dir: Path,
    page_num: int,
    image_counter: int,
) -> tuple[list[str], int, int]:
    """Extract page image resources when text-dictionary blocks omit them."""
    pymupdf = load_pymupdf()
    document = getattr(page, "parent", None)
    if document is None:
        return [], image_counter, 0

    refs: list[str] = []
    saved_images = 0
    for image_info in page.get_images(full=True):
        if len(image_info) < 4:
            continue
        xref = int(image_info[0])
        width = int(image_info[2] or 0)
        height = int(image_info[3] or 0)
        if width < _MIN_IMAGE_DIM or height < _MIN_IMAGE_DIM:
            continue

        try:
            pix = pymupdf.Pixmap(document, xref)
            ref, image_counter = _save_pdf_pixmap_image(pymupdf, pix, doc_name, images_dir, page_num, image_counter)
            refs.append(ref)
            saved_images += 1
        except Exception:
            logger.warning("Failed to save image resource on page %d", page_num)

    return refs, image_counter, saved_images


def extract_pdf_page_markdown(
    page: Any,
    doc_name: str,
    images_dir: Path,
    page_num: int,
    image_counter: int,
) -> tuple[str, int, int]:
    """Extract one PDF page as Markdown and save large embedded images.

    The returned Markdown uses the wiki source-image convention so the same
    content can be written to `wiki/sources/*.md` or PageIndex JSONL records.
    """
    pymupdf = load_pymupdf()

    parts: list[str] = []
    saved_images = 0

    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") == 0:
            lines = []
            for line in block.get("lines", []):
                spans_text = "".join(str(span.get("text", "")) for span in line.get("spans", []))
                if spans_text:
                    lines.append(spans_text)
            if lines:
                parts.append("\n".join(lines))
            continue

        if block.get("type") != 1:
            continue

        width = block.get("width", 0)
        height = block.get("height", 0)
        if width < _MIN_IMAGE_DIM or height < _MIN_IMAGE_DIM:
            continue
        if not _has_visible_bbox(block):
            continue

        image_bytes = block.get("image")
        if not image_bytes:
            continue

        try:
            pix = pymupdf.Pixmap(image_bytes)
            ref, image_counter = _save_pdf_pixmap_image(pymupdf, pix, doc_name, images_dir, page_num, image_counter)
            saved_images += 1
            parts.append(ref)
        except Exception:
            logger.warning("Failed to save image block on page %d", page_num)

    if saved_images == 0:
        refs, image_counter, resource_images = _extract_page_resource_images(
            page,
            doc_name,
            images_dir,
            page_num,
            image_counter,
        )
        parts.extend(refs)
        saved_images += resource_images

    return "\n".join(parts).strip(), image_counter, saved_images


def convert_pdf_with_images(pdf_path: Path, doc_name: str, images_dir: Path) -> str:
    """Convert a short PDF to Markdown while copying embedded images locally."""
    pymupdf = load_pymupdf()

    images_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    image_counter = 0

    with pymupdf.open(str(pdf_path)) as document:
        for page_index in range(len(document)):
            page = document[page_index]
            page_num = page_index + 1
            page_markdown, image_counter, _saved_images = extract_pdf_page_markdown(
                page,
                doc_name,
                images_dir,
                page_num,
                image_counter,
            )
            if page_markdown:
                parts.append(page_markdown)

    return "\n\n".join(parts)


def extract_base64_images(markdown: str, doc_name: str, images_dir: Path) -> str:
    counter = 0
    result = markdown

    for match in _BASE64_RE.finditer(markdown):
        alt, ext, b64_data = match.group(1), match.group(2), match.group(3)
        try:
            image_bytes = base64.b64decode(b64_data, validate=True)
        except Exception:
            logger.warning("Failed to decode base64 image alt=%r ext=%r", alt, ext)
            continue

        counter += 1
        filename = f"img_{counter:03d}.{ext}"
        dest = images_dir / filename
        images_dir.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(image_bytes)
        new_ref = f"![{alt}](sources/images/{doc_name}/{filename})"
        result = result.replace(match.group(0), new_ref, 1)

    return result


def copy_relative_images(markdown: str, source_dir: Path, doc_name: str, images_dir: Path) -> str:
    result = markdown
    source_root = source_dir.resolve()

    for match in _RELATIVE_RE.finditer(markdown):
        alt, relative_path = match.group(1), match.group(2)
        source_path = (source_dir / relative_path).resolve()
        if not source_path.is_relative_to(source_root):
            logger.warning("Image path escapes source dir: %s", relative_path)
            continue
        if not source_path.exists():
            logger.warning("Relative image not found: %s", source_path)
            continue

        filename = source_path.name
        dest = images_dir / filename
        images_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest)
        new_ref = f"![{alt}](sources/images/{doc_name}/{filename})"
        result = result.replace(match.group(0), new_ref, 1)

    return result

from __future__ import annotations

import base64
from pathlib import Path

from hermes_wiki.images import _save_pdf_pixmap_image, copy_relative_images, extract_base64_images


def test_copy_relative_images_rewrites_and_copies(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    images_dir = tmp_path / "wiki-images"
    source_dir.mkdir()
    (source_dir / "diagram.png").write_bytes(b"png-bytes")

    markdown = "See ![diagram](diagram.png) here."
    rewritten = copy_relative_images(markdown, source_dir, "doc", images_dir)

    assert rewritten == "See ![diagram](sources/images/doc/diagram.png) here."
    assert (images_dir / "diagram.png").read_bytes() == b"png-bytes"


def test_copy_relative_images_skips_escape_path(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    images_dir = tmp_path / "wiki-images"
    source_dir.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")

    markdown = "Bad ![escape](../outside.png) reference."
    rewritten = copy_relative_images(markdown, source_dir, "doc", images_dir)

    assert rewritten == markdown
    assert not images_dir.exists()


def test_extract_base64_images_rewrites_embedded_images(tmp_path: Path) -> None:
    images_dir = tmp_path / "wiki-images"
    encoded = base64.b64encode(b"fake-image-bytes").decode("ascii")
    markdown = f"Inline ![chart](data:image/png;base64,{encoded}) image."

    rewritten = extract_base64_images(markdown, "doc", images_dir)

    assert rewritten == "Inline ![chart](sources/images/doc/img_001.png) image."
    assert (images_dir / "img_001.png").read_bytes() == b"fake-image-bytes"


def test_save_pdf_pixmap_image_converts_four_channel_colorspace_before_png_export(tmp_path: Path) -> None:
    class FakeColorSpace:
        def __init__(self, channels: int) -> None:
            self.n = channels

    class FakePixmap:
        def __init__(self, channels: int, payload: bytes = b"png-bytes") -> None:
            self.n = channels
            self.colorspace = FakeColorSpace(channels)
            self._payload = payload

        def tobytes(self, image_format: str) -> bytes:
            assert image_format == "png"
            if self.colorspace.n == 4:
                raise ValueError("unsupported colorspace for 'png'")
            return self._payload

    class FakePyMuPDF:
        csRGB = object()

        def __init__(self) -> None:
            self.converted: list[FakePixmap] = []

        def Pixmap(self, colorspace: object, pix: FakePixmap) -> FakePixmap:
            assert colorspace is self.csRGB
            self.converted.append(pix)
            return FakePixmap(3)

    pymupdf = FakePyMuPDF()
    ref, image_counter = _save_pdf_pixmap_image(
        pymupdf,
        FakePixmap(4),
        "doc",
        tmp_path / "wiki-images",
        1,
        0,
    )

    assert ref == "![image](sources/images/doc/p1_img1.png)"
    assert image_counter == 1
    assert len(pymupdf.converted) == 1
    assert (tmp_path / "wiki-images" / "p1_img1.png").read_bytes() == b"png-bytes"

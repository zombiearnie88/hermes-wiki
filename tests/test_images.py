from __future__ import annotations

import base64
from pathlib import Path

import hermes_wiki.images as images_module
from hermes_wiki.images import _save_pdf_pixmap_image, copy_relative_images, extract_base64_images, extract_pdf_page_markdown


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


def test_extract_pdf_page_markdown_skips_degenerate_image_block_and_uses_resource_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class FakePixmap:
        def __init__(self, payload: bytes) -> None:
            self.n = 3
            self.colorspace = type("FakeColorSpace", (), {"n": 3})()
            self._payload = payload

        def tobytes(self, image_format: str) -> bytes:
            assert image_format == "png"
            return self._payload

    class FakePyMuPDF:
        csRGB = object()

        def Pixmap(self, *args):
            if len(args) == 1:
                return FakePixmap(b"block-image")
            if len(args) == 2:
                document, xref = args
                assert document is fake_document
                assert xref == 77
                return FakePixmap(b"resource-image")
            raise AssertionError("Unexpected Pixmap call")

    class FakePage:
        parent = None

        def get_text(self, mode: str) -> dict:
            assert mode == "dict"
            return {
                "blocks": [
                    {
                        "type": 0,
                        "lines": [{"spans": [{"text": "Visible text"}]}],
                    },
                    {
                        "type": 1,
                        "width": 793,
                        "height": 1121,
                        "bbox": (0.0, 0.0, 594.75, 0.0),
                        "image": b"degenerate-image",
                    },
                ]
            }

        def get_images(self, *, full: bool):
            assert full is True
            return [(77, 0, 96, 64)]

    fake_document = object()
    fake_page = FakePage()
    fake_page.parent = fake_document
    monkeypatch.setattr(images_module, "load_pymupdf", lambda: FakePyMuPDF())

    markdown, image_counter, saved_images = extract_pdf_page_markdown(
        fake_page,
        "doc",
        tmp_path / "wiki-images",
        5,
        0,
    )

    assert markdown == "Visible text\n![image](sources/images/doc/p5_img1.png)"
    assert image_counter == 1
    assert saved_images == 1
    assert (tmp_path / "wiki-images" / "p5_img1.png").read_bytes() == b"resource-image"


def test_extract_pdf_page_markdown_saves_visible_image_block(monkeypatch, tmp_path: Path) -> None:
    class FakePixmap:
        def __init__(self, payload: bytes) -> None:
            self.n = 3
            self.colorspace = type("FakeColorSpace", (), {"n": 3})()
            self._payload = payload

        def tobytes(self, image_format: str) -> bytes:
            assert image_format == "png"
            return self._payload

    class FakePyMuPDF:
        csRGB = object()

        def Pixmap(self, image_bytes: bytes) -> FakePixmap:
            assert image_bytes == b"real-image"
            return FakePixmap(image_bytes)

    class FakePage:
        parent = object()

        def get_text(self, mode: str) -> dict:
            assert mode == "dict"
            return {
                "blocks": [
                    {
                        "type": 1,
                        "width": 160,
                        "height": 120,
                        "bbox": (12.0, 20.0, 140.0, 116.0),
                        "image": b"real-image",
                    },
                ]
            }

        def get_images(self, *, full: bool):
            assert full is True
            return []

    monkeypatch.setattr(images_module, "load_pymupdf", lambda: FakePyMuPDF())

    markdown, image_counter, saved_images = extract_pdf_page_markdown(
        FakePage(),
        "doc",
        tmp_path / "wiki-images",
        2,
        0,
    )

    assert markdown == "![image](sources/images/doc/p2_img1.png)"
    assert image_counter == 1
    assert saved_images == 1
    assert (tmp_path / "wiki-images" / "p2_img1.png").read_bytes() == b"real-image"

import os
import tempfile
from typing import List, Literal

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image, ImageOps
from PyPDF2 import PdfMerger, PdfReader


PageFormat = Literal["A4", "original", "fit"]


class PDFService:
    """
    Central PDF engine:
    - images -> PDF
    - PDF + images -> PDF
    - page format handling
    """

    # ===================== PUBLIC API =====================

    @staticmethod
    def build_pdf(
        items: List[dict],
        output_path: str,
        page_format: PageFormat = "A4",
    ):
        """
        items: [
            {
                "file_path": str,
                "file_type": "pdf" | "image"
            }
        ]
        """
        if not items:
            raise ValueError("No items to build PDF")

        # only one PDF → copy as is
        if len(items) == 1 and items[0]["file_type"] == "pdf":
            PDFService._copy_pdf(items[0]["file_path"], output_path)
            return

        temp_pdfs: List[str] = []

        try:
            for item in items:
                if item["file_type"] == "pdf":
                    temp_pdfs.append(item["file_path"])
                else:
                    tmp = PDFService._image_to_pdf(
                        item["file_path"],
                        page_format=page_format
                    )
                    temp_pdfs.append(tmp)

            PDFService._merge_pdfs(temp_pdfs, output_path)

        finally:
            # cleanup temp image PDFs
            for p in temp_pdfs:
                if p.startswith(tempfile.gettempdir()):
                    try:
                        os.remove(p)
                    except FileNotFoundError:
                        pass

    # ===================== IMAGE → PDF =====================

    @staticmethod
    def _image_to_pdf(
        image_path: str,
        page_format: PageFormat
    ) -> str:
        """
        Converts ONE image to PDF
        Returns temp PDF path
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(image_path)

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(tmp_fd)

        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")

            if page_format == "original":
                page_size = img.size
            else:
                page_size = A4

            c = canvas.Canvas(tmp_path, pagesize=page_size)

            if page_format == "fit":
                PDFService._draw_fit(c, img, page_size)
            else:
                PDFService._draw_centered(c, img, page_size)

            c.showPage()
            c.save()

        return tmp_path

    # ===================== DRAW HELPERS =====================

    @staticmethod
    def _draw_centered(c: canvas.Canvas, img: Image.Image, page_size):
        page_w, page_h = page_size
        w, h = img.size

        scale = min(page_w / w, page_h / h)
        new_w = w * scale
        new_h = h * scale

        x = (page_w - new_w) / 2
        y = (page_h - new_h) / 2

        c.drawInlineImage(img, x, y, new_w, new_h)

    @staticmethod
    def _draw_fit(c: canvas.Canvas, img: Image.Image, page_size):
        page_w, page_h = page_size
        c.drawInlineImage(img, 0, 0, page_w, page_h)

    # ===================== PDF HELPERS =====================

    @staticmethod
    def _merge_pdfs(paths: List[str], output: str):
        merger = PdfMerger()
        try:
            for path in paths:
                if os.path.exists(path):
                    merger.append(path)
            merger.write(output)
        finally:
            merger.close()

    @staticmethod
    def _copy_pdf(src: str, dst: str):
        reader = PdfReader(src)
        merger = PdfMerger()
        try:
            merger.append(reader)
            merger.write(dst)
        finally:
            merger.close()

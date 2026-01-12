import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image, ImageOps
from PyPDF2 import PdfMerger


class PDFService:

    # ===================== IMAGES → PDF =====================

    @staticmethod
    def images_to_pdf(images: list[str], output: str):
        """
        Конвертирует изображения в PDF (A4),
        корректно обрабатывает:
        - PNG / JPG / CMYK
        - EXIF orientation
        - масштабирование и центрирование
        """
        if not images:
            raise ValueError("No images provided")

        c = canvas.Canvas(output, pagesize=A4)
        page_w, page_h = A4

        for img_path in images:
            if not os.path.exists(img_path):
                continue

            with Image.open(img_path) as img:
                # исправление ориентации (EXIF)
                img = ImageOps.exif_transpose(img)

                # гарантируем RGB
                img = img.convert("RGB")

                w, h = img.size
                scale = min(page_w / w, page_h / h)

                new_w = w * scale
                new_h = h * scale

                x = (page_w - new_w) / 2
                y = (page_h - new_h) / 2

                # drawInlineImage безопаснее, чем drawImage(path)
                c.drawInlineImage(img, x, y, new_w, new_h)
                c.showPage()

        c.save()

    # ===================== MERGE PDFs =====================

    @staticmethod
    def merge_pdfs(pdf_paths: list[str], output: str):
        """
        Объединяет несколько PDF в один
        """
        if len(pdf_paths) < 2:
            raise ValueError("Need at least two PDFs to merge")

        merger = PdfMerger()

        try:
            for path in pdf_paths:
                if not os.path.exists(path):
                    continue
                merger.append(path)

            merger.write(output)
        finally:
            merger.close()

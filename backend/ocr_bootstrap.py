"""PaddleOCR model bake used by the Modal worker image.

Kept as a top-level module so ``Image.run_function`` can import it without
re-evaluating ``modal_app`` image construction.
"""


def download_ocr_models() -> None:
    """Initialize English PaddleOCR so weights are stored in the image."""
    from paddleocr import PaddleOCR

    try:
        PaddleOCR(lang="en", use_angle_cls=False, show_log=False)
    except TypeError:
        PaddleOCR(lang="en", use_angle_cls=False)

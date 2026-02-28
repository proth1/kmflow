"""Platform-specific OCR engine for VCE screen text extraction.

Priority:
  1. macOS — Vision framework via pyobjc
  2. Windows — Windows.Media.Ocr via pythonnet
  3. Fallback — pytesseract if installed

The engine returns the raw extracted text. PII redaction is applied by
the caller (redactor.py) before any text is stored or transmitted.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import platform
import sys

logger = logging.getLogger(__name__)

_SYSTEM = platform.system()


def _try_import(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


class OCREngine:
    """Async OCR engine with platform-specific backends."""

    async def extract_text(self, image_bytes: bytes) -> str:
        """Extract text from a PNG image using the best available backend.

        Args:
            image_bytes: PNG-encoded screen capture bytes (memory-only).

        Returns:
            Raw extracted text string, or empty string on failure.
        """
        try:
            if _SYSTEM == "Darwin":
                return await self._extract_macos(image_bytes)
            elif _SYSTEM == "Windows":
                return await self._extract_windows(image_bytes)
            else:
                return await self._extract_tesseract(image_bytes)
        except Exception as exc:
            logger.warning("OCR extraction failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # macOS: Vision framework via pyobjc
    # ------------------------------------------------------------------

    async def _extract_macos(self, image_bytes: bytes) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_macos_sync, image_bytes)

    @staticmethod
    def _extract_macos_sync(image_bytes: bytes) -> str:
        try:
            import Quartz  # pyobjc-framework-Quartz
            from Vision import VNImageRequestHandler, VNRecognizeTextRequest  # type: ignore[import]
            import objc  # type: ignore[import]

            data = objc.lookUpClass("NSData").dataWithBytes_length_(image_bytes, len(image_bytes))
            handler = VNImageRequestHandler.alloc().initWithData_options_(data, {})
            request = VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(1)  # accurate
            handler.performRequests_error_([request], None)

            observations = request.results() or []
            texts = [obs.topCandidates_(1)[0].string() for obs in observations if obs.topCandidates_(1)]
            return "\n".join(texts)
        except Exception as exc:
            logger.debug("macOS Vision OCR failed: %s", exc)
            return OCREngine._extract_tesseract_sync(image_bytes)

    # ------------------------------------------------------------------
    # Windows: Windows.Media.Ocr via pythonnet
    # ------------------------------------------------------------------

    async def _extract_windows(self, image_bytes: bytes) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_windows_sync, image_bytes)

    @staticmethod
    def _extract_windows_sync(image_bytes: bytes) -> str:
        try:
            import clr  # pythonnet  # type: ignore[import]
            clr.AddReference("Windows")  # type: ignore[attr-defined]
            from Windows.Media.Ocr import OcrEngine  # type: ignore[import]
            from Windows.Graphics.Imaging import BitmapDecoder, SoftwareBitmap  # type: ignore[import]
            import System  # type: ignore[import]
            from System.IO import MemoryStream  # type: ignore[import]

            stream = MemoryStream(list(image_bytes))
            decoder = BitmapDecoder.CreateAsync(stream).GetAwaiter().GetResult()
            bitmap = decoder.GetSoftwareBitmapAsync().GetAwaiter().GetResult()

            engine = OcrEngine.TryCreateFromUserProfileLanguages()
            if engine is None:
                raise RuntimeError("Windows OCR engine not available")

            result = engine.RecognizeAsync(bitmap).GetAwaiter().GetResult()
            return result.Text
        except Exception as exc:
            logger.debug("Windows OCR failed: %s", exc)
            return OCREngine._extract_tesseract_sync(image_bytes)

    # ------------------------------------------------------------------
    # Fallback: pytesseract
    # ------------------------------------------------------------------

    async def _extract_tesseract(self, image_bytes: bytes) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_tesseract_sync, image_bytes)

    @staticmethod
    def _extract_tesseract_sync(image_bytes: bytes) -> str:
        try:
            import pytesseract  # type: ignore[import]
            from PIL import Image  # type: ignore[import]
            import io

            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img)
        except Exception as exc:
            logger.debug("Tesseract OCR failed: %s", exc)
            return ""

import logging
import re
from datetime import datetime
from typing import Dict, Optional

log = logging.getLogger(__name__)

class OCREngine:
    """
    High-Assurance OCR Engine for M-Pesa statements/screenshots.
    
    ======================================================================
    PROFESSIONAL ADVICE & ARCHITECTURAL PATH (Authored by AI Architect)
    ======================================================================
    For M-Pesa screenshots (AIP-2), I strongly advise against using local, 
    free options like Tesseract (`pytesseract`). Mobile screenshots suffer 
    from extreme variability:
      - Glare, screen cracks, poor lighting
      - Font scaling issues / Dark Mode inversion
      - Heavy compression artifacts from WhatsApp forwards
    
    Tesseract will fail frequently on these, leading to silent data 
    corruption or high support load.
    
    **Architectural Recommendation:**
    We must use an Enterprise AI Vision model. 
    1. **Primary**: Google Cloud Vision API. It is the gold standard for 
       OCR on noisy, real-world field images. It detects structured blocks 
       flawlessly.
    2. **Fallback**: AWS Textract (slightly more expensive, better for tables).
    
    **Current Status**: 
    As per Phase 3 directives, this engine is currently implemented as a 
    Mock/Placeholder until we provision a Google Cloud Service Account and 
    install `google-cloud-vision`.
    ======================================================================
    """
    
    def __init__(self, mode: str = "mock"):
        self.mode = mode
        
    def process_image(self, image_bytes: bytes) -> Optional[Dict]:
        """
        Processes an M-Pesa screenshot and extracts core transaction fields.
        Returns a dictionary or None if parsing fails.
        """
        log.info("ocr_processing_started", mode=self.mode, bytes=len(image_bytes))
        
        if self.mode == "mock":
            return self._mock_extract(image_bytes)
        elif self.mode == "gcv":
            raise NotImplementedError("Google Cloud Vision requires billing and service account.")
        else:
            log.error("ocr_unknown_mode", mode=self.mode)
            return None

    def _mock_extract(self, image_bytes: bytes) -> Dict:
        """
        Stubbed OCR extraction for development and testing.
        """
        log.warning("ocr_using_mock_engine", status="AWAITING_GCV_CREDENTIALS")
        return {
            "mpesa_ref": "QWE123RTY4",
            "amount": 1050.00,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "sender_name": "JOHN DOE OCR TEST",
            "transaction_type": "C2B"
        }

# Singleton instance
ocr_engine = OCREngine(mode="mock")

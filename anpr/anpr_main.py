"""
anpr/anpr_main.py
YOLOv8 + fast_plate_ocr ANPR edge script — ITB Jatinangor Parking Gate.

Key improvements:
  1. aiohttp + asyncio  → HTTP POST runs in background; OpenCV loop never blocks.
  2. Confidence fix     → YOLO confidence (object detection) is separate from
                          OCR confidence (text accuracy). Backend threshold (85%)
                          applies to OCR vote consistency, not YOLO detection score.
  3. Environment variables → no secrets in source code.
  4. Configurable direction (ENTRY / EXIT) via env var.

Usage:
    GATE_DIRECTION=entry GATE_ID=G1 python anpr_main.py
    GATE_DIRECTION=exit  GATE_ID=EXIT1 python anpr_main.py
"""
import os
import re
import time
import asyncio
import logging
import threading
from collections import Counter, deque
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import aiohttp
import cv2
from fast_plate_ocr import LicensePlateRecognizer
from ultralytics import YOLO

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("anpr")

# =============================================================================
# CONFIGURATION
# =============================================================================
API_ENDPOINT   = os.environ.get("API_ENDPOINT",   "http://localhost:8000/api/v1/gate/trigger")
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "REPLACE_WITH_REAL_JWT_TOKEN")

GATE_ID        = os.environ.get("GATE_ID",        "G1")
GATE_DIRECTION = os.environ.get("GATE_DIRECTION", "entry")
CAMERA_INDEX   = int(os.environ.get("CAMERA_INDEX", "0"))

FRAME_WIDTH    = 1280
FRAME_HEIGHT   = 720
MIN_BOX_W      = 80
MIN_BOX_H      = 30
VOTE_THRESHOLD = 5       # Number of consistent OCR readings before triggering

# ── Confidence strategy ────────────────────────────────────────────────────────
# YOLO confidence = object detection score (is this a plate box?) → typically 0.3–0.7
# OCR confidence  = computed from vote consistency → passed to backend
# Backend CONF_THRESHOLD (0.85) checks OCR confidence, NOT YOLO score.
#
# OCR confidence formula:
#   best_count / total_history  (e.g. 8/10 readings agree → 0.80)
#   + bonus if YOLO score is high
# This gives the backend an honest signal about OCR reliability.
YOLO_MIN_CONF  = 0.25    # Minimum YOLO detection score to process a box

# =============================================================================
# REGEX — Indonesian plate (normalized: no spaces)
# =============================================================================
PLATE_PATTERN = re.compile(r"^[A-Z]{1,2}\d{1,4}[A-Z]{1,3}$")

# =============================================================================
# MODELS
# =============================================================================
log.info("Loading YOLO model...")
yolo = YOLO(
    "https://huggingface.co/wuriyanto/yolo8-indonesian-license-plate-detection/resolve/main/model.pt"
)

log.info("Loading fast_plate_ocr model...")
ocr_model = LicensePlateRecognizer("cct-s-v2-global-model")

# =============================================================================
# ASYNC HTTP — background event loop
# =============================================================================
_http_session: Optional[aiohttp.ClientSession] = None
_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()

def _start_event_loop():
    asyncio.set_event_loop(_loop)
    _loop.run_forever()

threading.Thread(target=_start_event_loop, daemon=True).start()


async def _get_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {API_SECRET_KEY}"},
            timeout=aiohttp.ClientTimeout(total=3.0, connect=1.0),
        )
    return _http_session


async def _send_trigger_async(plate: str, ocr_confidence: float) -> None:
    """
    Send gate trigger POST with OCR-based confidence score.
    ocr_confidence is computed from vote consistency (0.0–1.0), NOT YOLO score.
    """
    session = await _get_session()
    payload = {
        "plate_number": plate,
        "gate_id":      GATE_ID,
        "confidence":   ocr_confidence,   # OCR vote consistency — backend checks ≥ 0.85
        "direction":    GATE_DIRECTION,
    }
    try:
        async with session.post(API_ENDPOINT, json=payload) as resp:
            body = await resp.json()
            action = body.get("action", "unknown")

            if action == "open_gate":
                log.info(
                    "✅ GATE %s OPENED | plate=%s | owner=%s | fee=%s",
                    GATE_ID, plate, body.get("owner", "–"), body.get("fee", "–"),
                )
            elif action == "cooldown":
                log.info("⏱  Cooldown active for %s — skipped.", plate)
            elif action == "low_confidence":
                log.warning(
                    "🟡 Low OCR confidence for %s (%.0f%%) — gate held.",
                    plate, ocr_confidence * 100,
                )
            elif action == "deny_access":
                log.warning(
                    "🔴 Access denied for %s | reason: %s",
                    plate, body.get("reason", "unknown"),
                )
            else:
                log.warning("🔴 Unexpected action '%s' for %s", action, plate)

    except aiohttp.ClientConnectorError:
        log.error("❌ Cannot reach backend at %s — is the server running?", API_ENDPOINT)
    except asyncio.TimeoutError:
        log.error("❌ Backend timeout for plate %s.", plate)
    except Exception as exc:
        log.error("❌ Trigger error: %s", exc)


def send_trigger_nonblocking(plate: str, ocr_confidence: float) -> None:
    """
    Schedule the HTTP trigger on the background loop.
    Returns immediately — OpenCV loop is never blocked.
    """
    asyncio.run_coroutine_threadsafe(
        _send_trigger_async(plate, ocr_confidence), _loop
    )
    log.info(
        "→ Trigger dispatched | plate=%s | dir=%s | gate=%s | ocr_conf=%.0f%%",
        plate, GATE_DIRECTION, GATE_ID, ocr_confidence * 100,
    )


# =============================================================================
# OCR HELPER
# =============================================================================
def run_ocr(crop) -> str:
    """
    Run fast_plate_ocr on the cropped plate image.
    Returns normalized text (uppercase, no spaces/special chars).
    Handles both list and single-object return types from the OCR model.
    """
    prediction = ocr_model.run(crop)

    raw_text = ""
    if isinstance(prediction, list) and len(prediction) > 0:
        raw_text = getattr(prediction[0], "plate",
                   getattr(prediction[0], "text", str(prediction[0])))
    else:
        raw_text = getattr(prediction, "plate",
                   getattr(prediction, "text", str(prediction)))

    # Strip everything except letters and digits
    clean = re.sub(r"[^A-Z0-9]", "", raw_text.upper())

    # Extract Indonesian plate pattern (ignore surrounding tax digits etc.)
    match = re.search(r"([A-Z]{1,2}\d{1,4}[A-Z]{1,3})", clean)
    result = match.group(1) if match else clean

    log.debug("OCR raw='%s' → clean='%s' → result='%s'", raw_text, clean, result)
    return result


# =============================================================================
# OCR CONFIDENCE — computed from vote history, NOT YOLO score
# =============================================================================
def compute_ocr_confidence(history: deque, best_plate: str) -> float:
    """
    Compute how confident the OCR is based on vote consistency.

    Formula:
      base = (count of best_plate in history) / len(history)
      → e.g. 9 out of 10 readings = 0.90

    This value is what we send to the backend as `confidence`.
    The backend threshold is 0.85 — so we need 85%+ of readings to agree.

    Why this is correct:
      - YOLO score measures "is there a plate here?" (typically 0.3–0.7)
      - OCR vote consistency measures "how sure are we of the text?" (0.0–1.0)
      - The backend CONF_THRESHOLD (0.85) was designed for OCR confidence
    """
    counts = Counter(history)
    best_count = counts[best_plate]
    total = len(history)
    return round(best_count / total, 3) if total > 0 else 0.0


# =============================================================================
# STATE
# =============================================================================
history:           deque = deque(maxlen=10)
last_trigger_time: float = 0.0
last_plate:        str   = ""
COOLDOWN_SECS:     float = 5.0

# =============================================================================
# CAMERA SETUP
# =============================================================================
cap = cv2.VideoCapture(CAMERA_INDEX)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

cv2.namedWindow("ALPR — ITB Jatinangor", cv2.WINDOW_NORMAL)
cv2.resizeWindow("ALPR — ITB Jatinangor", FRAME_WIDTH, FRAME_HEIGHT)

log.info(
    "ANPR started | gate=%s | dir=%s | camera=%d | endpoint=%s",
    GATE_ID, GATE_DIRECTION, CAMERA_INDEX, API_ENDPOINT,
)
log.info("Press ESC to exit.")

# =============================================================================
# MAIN CAPTURE LOOP
# =============================================================================
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            log.error("Failed to read frame from camera %d.", CAMERA_INDEX)
            break

        results = yolo(frame, verbose=False)

        for r in results:
            if r.boxes is None or len(r.boxes) == 0:
                continue

            for box_tensor, conf_tensor in zip(r.boxes.xyxy, r.boxes.conf):
                yolo_conf = float(conf_tensor.item())

                # Skip low-confidence YOLO detections (noise/false positives)
                if yolo_conf < YOLO_MIN_CONF:
                    continue

                x1, y1, x2, y2 = map(int, box_tensor.tolist())
                crop = frame[y1:y2, x1:x2]

                if crop.shape[0] < MIN_BOX_H or crop.shape[1] < MIN_BOX_W:
                    continue

                # ── OCR ───────────────────────────────────────────────────────
                text = run_ocr(crop)
                log.info("YOLO conf=%.2f | OCR → '%s'", yolo_conf, text)

                box_color = (0, 0, 255)  # Red = not yet valid

                # ── Regex validation + voting ─────────────────────────────────
                if PLATE_PATTERN.match(text):
                    history.append(text)
                    box_color = (0, 255, 0)  # Green = valid format

                    if len(history) >= VOTE_THRESHOLD:
                        best_plate  = Counter(history).most_common(1)[0][0]
                        ocr_conf    = compute_ocr_confidence(history, best_plate)
                        now         = time.time()

                        plate_changed = best_plate != last_plate
                        cooldown_ok   = (now - last_trigger_time) > COOLDOWN_SECS

                        if plate_changed or cooldown_ok:
                            log.info(
                                "🔒 Plate locked: %s | ocr_conf=%.0f%% | yolo_conf=%.0f%%",
                                best_plate, ocr_conf * 100, yolo_conf * 100,
                            )
                            # Send with OCR-based confidence (not YOLO score)
                            send_trigger_nonblocking(best_plate, ocr_conf)

                            last_plate        = best_plate
                            last_trigger_time = now
                            history.clear()

                # ── Draw bounding box + text ──────────────────────────────────
                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                if text:
                    cv2.putText(frame, text, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.85, box_color, 2)
                    cv2.putText(frame, f"YOLO:{yolo_conf:.0%}", (x1, y2 + 18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        # ── HUD ───────────────────────────────────────────────────────────────
        cv2.putText(frame, f"GATE: {GATE_ID} | DIR: {GATE_DIRECTION.upper()}",
                    (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Last locked: {last_plate or 'None'}",
                    (10, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 1)

        cv2.imshow("ALPR — ITB Jatinangor", frame)

        if cv2.waitKey(1) == 27:
            log.info("ESC — shutting down.")
            break

finally:
    cap.release()
    cv2.destroyAllWindows()

    async def _cleanup():
        global _http_session
        if _http_session and not _http_session.closed:
            await _http_session.close()

    asyncio.run_coroutine_threadsafe(_cleanup(), _loop).result(timeout=2)
    _loop.call_soon_threadsafe(_loop.stop)
    log.info("ANPR shutdown complete.")

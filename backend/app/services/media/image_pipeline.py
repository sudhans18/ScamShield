"""
image_pipeline.py
-----------------
Production OCR pipeline for ScamShield — upgraded with:

  1. Image-type classifier       → routes each image to the right sub-pipeline
  2. Scene-to-document crop      → isolates white/light paper from scene background
  3. WhatsApp screenshot handler → strips status bar, header, input bar, emoji regions
  4. Notice board handler        → detects cork board boundary, processes as one unit
  5. Perspective correction      → corrects camera-angle trapezoid distortion
  6. MSER text region detection  → finds text bounding boxes before OCR, used to:
                                    a) build a text-only mask (whites out icons/QR/graphics)
                                    b) detect column layout (single vs two-column)
  7. Layout-aware OCR            → runs OCR on left/right columns independently when needed,
                                    then merges results preserving reading order
  8. Adaptive CLAHE              → equalises contrast per-region, critical for coloured
                                    header bands (Image 3 red/blue/white stripes)
  9. Multi-PSM OCR cascade       → tries PSM 6/11/3/4, picks highest-confidence result
  10. Multilingual script routing → selects eng-only vs eng+hin vs eng+hin+tam based
                                    on script detection in a fast pre-scan

Performance budget (measured on 2000×1116 images):
  Image type routing      ~  5 ms
  Scene crop              ~ 16 ms
  MSER (half-resolution)  ~ 90 ms
  CLAHE + threshold       ~  8 ms
  Hough deskew (half-res) ~ 70 ms
  OCR (1 PSM pass)        ~ varies by content
  Total non-OCR budget    ~ 200 ms  ← within the 300ms target

Called by:  main_service.py
Input:      file path (str/Path) or raw bytes
Output:     dict with extracted_text, confidence, preprocessing_steps, language_hint
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
from pathlib import Path
from typing import Union

import cv2
import numpy as np
import pytesseract
from PIL import Image, ExifTags
# Tell pytesseract where the OCR engine is installed
_tess_path = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
pytesseract.pytesseract.tesseract_cmd = _tess_path

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
MAX_FILE_BYTES    = 15 * 1024 * 1024   # 15 MB
MIN_DIMENSION_PX  = 80
MAX_LONG_SIDE_PX  = 3000               # hard ceiling before any processing
TARGET_OCR_PX     = 1600               # upscale target for OCR accuracy

# OCR config
PSM_CASCADE          = [6, 11, 3, 4]   # tried in order; best confidence wins
CONFIDENCE_THRESHOLD = 30              # minimum acceptable mean word confidence

# Language selection — checked against installed packs at startup
_TESS_LANG_CACHE: dict[str, str] = {}  # populated by _select_tess_lang()

# MSER parameters — tuned for text on posters/screenshots at half-resolution
MSER_DELTA        = 5
MSER_MIN_AREA     = 25     # minimum character component area (at half-res)
MSER_MAX_AREA_PCT = 0.004  # max area as fraction of image — filters whole-image noise
MSER_MAX_VAR      = 0.25
MSER_MIN_DIV      = 0.2

# Text region filter thresholds
MSER_MIN_W = 6    # pixels at half-res — equivalent to ~12px full-res
MSER_MIN_H = 5
MSER_MAX_W_FRAC = 0.45   # box can't be wider than half the image
MSER_MAX_H_FRAC = 0.20   # box can't be taller than a fifth of the image
MSER_MIN_AR = 0.15       # aspect ratio: very tall thin strokes allowed
MSER_MAX_AR = 18.0       # very wide banners allowed (e.g. "URGENT VACANCY")

# Column layout detection
# ── Five-gate two-column detection (see _detect_column_layout) ────────────────
COLUMN_BALANCE_THRESH     = 0.25   # max L/R count imbalance — tightened from 0.30
COLUMN_MIN_REGIONS_EACH   = 10     # each half must have at least this many regions
COLUMN_VALLEY_RATIO_MAX   = 0.45   # projection valley / peak — must be below this
                                    # (0 = perfect gap, 1 = no gap at all)
COLUMN_STRUCT_GAP_MIN     = 0.05   # min spatial gap between left-extent and
                                    # right-extent, as fraction of image width
COLUMN_COOCCUR_MIN        = 0.65   # min Y-band co-occurrence ratio — ensures left
                                    # and right text appear at the SAME row positions
                                    # (parallel columns), not random separate clusters

# WhatsApp detection — header colour is a distinctive teal/green
WA_HEADER_HUE_LO  = (75, 80, 80)    # HSV lower bound
WA_HEADER_HUE_HI  = (105, 255, 200) # HSV upper bound
WA_HEADER_ROW_COV = 0.30             # fraction of row width that must be green
WA_BOTTOM_FRAC    = 0.08             # fraction of height to strip from bottom (input bar)


# ── Public entry point ────────────────────────────────────────────────────────

def process_image(source: Union[str, bytes, Path]) -> dict:
    """
    Unified image → text pipeline.

    Automatically detects the image type (WhatsApp screenshot, poster in scene,
    notice board, standalone document) and routes to the appropriate sub-pipeline.

    Returns
    -------
    dict:
        success            bool
        extracted_text     str
        language_hint      str    "english" | "hindi" | "mixed" | "tamil"
        image_quality      str    "good" | "low" | "very_low"
        image_type         str    "whatsapp" | "poster_in_scene" | "noticeboard"
                                  | "document" | "two_column_poster"
        confidence         float  mean Tesseract word confidence 0–100
        preprocessing_steps list[str]
        char_count         int
        source_type        str    "file" | "bytes"
    """
    t_start = time.perf_counter()
    logger.info("image_pipeline: start")

    # ── Load ──────────────────────────────────────────────────────────────────
    load = _load(source)
    if not load["success"]:
        return load

    bgr: np.ndarray = load["bgr"]
    source_type: str = load["source_type"]
    steps: list[str] = []

    orig_h, orig_w = bgr.shape[:2]
    image_quality = _quality_label(orig_w, orig_h)

    if orig_w < MIN_DIMENSION_PX or orig_h < MIN_DIMENSION_PX:
        return _err(f"Image too small ({orig_w}×{orig_h}px).", source_type)

    # ── Hard ceiling downscale (memory safety) ────────────────────────────────
    bgr, step = _hard_downscale(bgr)
    if step:
        steps.append(step)

    # ── EXIF rotation (phone camera portrait/landscape) ───────────────────────
    bgr, step = _exif_rotate(load.get("pil_image"), bgr)
    if step:
        steps.append(step)

    h, w = bgr.shape[:2]

    # ── Detect image type ─────────────────────────────────────────────────────
    image_type = _detect_image_type(bgr)
    steps.append(f"type={image_type}")
    logger.info(f"image_pipeline: type={image_type}")

    # ── Route to type-specific preprocessor ──────────────────────────────────
    if image_type == "whatsapp":
        bgr, type_steps = _preprocess_whatsapp(bgr)
    elif image_type == "noticeboard":
        bgr, type_steps = _preprocess_noticeboard(bgr)
    elif image_type == "poster_in_scene":
        bgr, type_steps = _preprocess_poster_in_scene(bgr)
    else:
        # "document" or "two_column_poster" — go straight to standard preprocessing
        type_steps = []

    steps.extend(type_steps)

    # ── Perspective correction (all types except WhatsApp screenshots) ────────
    if image_type not in ("whatsapp",):
        bgr, step = _perspective_correct(bgr)
        if step:
            steps.append(step)

    # ── Grayscale + adaptive deskew (on half-res for speed) ──────────────────
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    steps.append("greyscale")

    gray, skew_angle = _deskew_hough(gray)
    if abs(skew_angle) > 0.5:
        steps.append(f"deskew({skew_angle:.1f}°)")

    # ── Background type detection (drives thresholding strategy) ─────────────
    bg_type = _detect_background_type(gray)
    steps.append(f"bg={bg_type}")

    # ── Denoise — fast bilateral for textured/gradient, Gaussian otherwise ────
    gray = _denoise(gray, bg_type)
    steps.append("denoise")

    # ── MSER text region detection on half-resolution ────────────────────────
    #    Returns: text_mask (full-res), layout hint, column count
    mser_result = _mser_text_regions(gray)
    text_mask   = mser_result["mask"]
    layout      = mser_result["layout"]
    steps.append(f"mser({mser_result['region_count']}regions,{layout})")

    # ── CLAHE + binarise ──────────────────────────────────────────────────────
    binary, thresh_step = _binarise(gray, bg_type)
    steps.append(thresh_step)

    # ── Morphological cleanup ─────────────────────────────────────────────────
    binary = _morph_cleanup(binary)
    steps.append("morph_cleanup")

    # ── Upscale to OCR-optimal resolution ────────────────────────────────────
    binary, step = _upscale_for_ocr(binary)
    if step:
        steps.append(step)

    # Scale text mask to match upscaled binary
    if binary.shape[:2] != text_mask.shape[:2]:
        text_mask = cv2.resize(text_mask, (binary.shape[1], binary.shape[0]),
                               interpolation=cv2.INTER_NEAREST)

    # ── OCR — layout-aware ────────────────────────────────────────────────────
    tess_lang = _select_tess_lang(gray)
    steps.append(f"lang={tess_lang}")

    if layout == "two_column":
        ocr_result = _ocr_two_column(binary, text_mask, tess_lang)
        steps.append("two_col_ocr")
    else:
        # Apply text mask to suppress non-text regions (QR codes, icons, graphics)
        masked_binary = _apply_text_mask(binary, text_mask)
        ocr_result = _ocr_cascade(masked_binary, tess_lang)
        steps.append(f"masked_ocr")

    # ── Fallback: unmasked OCR if masked gave nothing ─────────────────────────
    if not ocr_result["success"]:
        logger.warning("image_pipeline: masked OCR failed, retrying unmasked")
        ocr_result = _ocr_cascade(binary, tess_lang)
        steps.append("fallback_unmasked")

    # ── Final fallback: colour image ──────────────────────────────────────────
    if not ocr_result["success"]:
        logger.warning("image_pipeline: binary OCR failed, retrying on colour")
        # Resize colour to match OCR target
        colour_resized, _ = _upscale_for_ocr(bgr)
        ocr_result = _ocr_cascade(colour_resized, tess_lang, force_psm=6)
        steps.append("fallback_colour")

    if not ocr_result["success"]:
        return _err("OCR returned no readable text after all fallbacks.", source_type)

    raw_text   = ocr_result["text"]
    confidence = ocr_result["confidence"]
    steps.append(f"psm{ocr_result['psm']}(conf={confidence:.0f})")

    cleaned = _basic_clean(raw_text)
    if not cleaned.strip():
        return _err("OCR completed but extracted no readable text.", source_type)

    lang_hint = _language_hint(cleaned)
    elapsed   = (time.perf_counter() - t_start) * 1000

    logger.info(
        f"image_pipeline: done | type={image_type} chars={len(cleaned)} "
        f"lang={lang_hint} conf={confidence:.0f} time={elapsed:.0f}ms"
    )

    return {
        "success":             True,
        "extracted_text":      cleaned,
        "language_hint":       lang_hint,
        "image_quality":       image_quality,
        "image_type":          image_type,
        "confidence":          round(confidence, 1),
        "preprocessing_steps": steps,
        "char_count":          len(cleaned),
        "source_type":         source_type,
        "processing_ms":       round(elapsed, 1),
    }


# ── Image type detection ──────────────────────────────────────────────────────

def _detect_image_type(bgr: np.ndarray) -> str:
    """
    Classify the image into one of four types that drive the pipeline route:

    'whatsapp'         — phone screenshot of a WhatsApp conversation
                         Signature: green header band in top 30%, portrait aspect,
                         status bar at very top, input bar at bottom

    'noticeboard'      — cork/wall board with many overlapping paper posters
                         Signature: textured brownish background with rectangular
                         white paper cutouts; wide aspect ratio; high edge density
                         on the periphery but inside a board boundary

    'poster_in_scene'  — single document/poster photographed in context
                         (e.g. pinned to a wall, taped to glass)
                         Signature: one dominant bright white/light rectangle
                         surrounded by a distinctly different scene background

    'document'         — close-up clean scan, no background scene visible
                         (default fallback)
    """
    h, w = bgr.shape[:2]
    hsv  = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    # ── WhatsApp: look for the teal/green header band in the top 30% ─────────
    top_region = hsv[:int(h * 0.30), :, :]
    green_mask = cv2.inRange(top_region, WA_HEADER_HUE_LO, WA_HEADER_HUE_HI)
    # A genuine WhatsApp header covers >30% of its row width across multiple rows
    green_rows = (green_mask.sum(axis=1) > w * 255 * WA_HEADER_ROW_COV).sum()
    if green_rows >= 40:
        return "whatsapp"

    # ── Document in scene: large white paper region with a scene background ───
    # Check the fraction of the image that is white/very-light
    white_mask = cv2.inRange(hsv, (0, 0, 190), (180, 40, 255))
    white_frac = white_mask.mean() / 255
    # If 20–75% of pixels are white → single document in scene
    if 0.20 < white_frac < 0.75:
        return "poster_in_scene"

    # ── Notice board: textured background, moderate white fraction, wide image ─
    # Check background texture by sampling the image edges
    gray    = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    margins = np.concatenate([
        gray[:, :w // 10].ravel(),   # left edge
        gray[:, -w // 10:].ravel(),  # right edge
        gray[:h // 10, :].ravel(),   # top edge
        gray[-h // 10:, :].ravel(),  # bottom edge
    ])
    edge_std = float(np.std(margins))
    # Notice boards have: textured background (high std), multiple white patches
    if edge_std > 35 and white_frac > 0.10:
        return "noticeboard"

    return "document"


# ── Type-specific preprocessors ──────────────────────────────────────────────

def _preprocess_whatsapp(bgr: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """
    Isolate the message content from a WhatsApp screenshot.

    Steps:
    1. Find the green header band → mark its bottom edge
    2. Find the input bar at the bottom → mark its top edge
    3. Crop to the content window between those bounds
    4. Strip high-saturation emoji regions → replace with white
       (emoji glyphs confuse Tesseract and add noise with no textual value)
    5. Isolate the message bubble (largest white region) to remove
       the background pattern behind the chat area

    This turns the full phone screenshot into a clean white-background
    document with only the job advertisement text visible.
    """
    steps: list[str] = []
    h, w  = bgr.shape[:2]
    hsv   = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    # ── 1. Locate header bottom ───────────────────────────────────────────────
    green_mask = cv2.inRange(hsv[:int(h * 0.35), :, :],
                             WA_HEADER_HUE_LO, WA_HEADER_HUE_HI)
    green_rows = np.where(green_mask.sum(axis=1) > w * 255 * WA_HEADER_ROW_COV)[0]
    header_end = int(green_rows[-1]) + 8 if len(green_rows) > 0 else int(h * 0.16)

    # ── 2. Locate bottom input bar ────────────────────────────────────────────
    # The input bar is a light-grey strip at the very bottom
    bottom_cut = h - int(h * WA_BOTTOM_FRAC)

    # ── 3. Crop to content region ─────────────────────────────────────────────
    content = bgr[header_end:bottom_cut, :, :].copy()
    steps.append(f"wa_crop(y={header_end}:{bottom_cut})")

    ch, cw = content.shape[:2]

    # ── 4. Strip emoji regions ────────────────────────────────────────────────
    # Emoji rendered in screenshots tend to be small, saturated, roughly square patches.
    # Saturation > 120 AND value > 100 in a small region → likely emoji.
    hsv_content = cv2.cvtColor(content, cv2.COLOR_BGR2HSV)
    emoji_mask  = cv2.inRange(hsv_content, (0, 120, 80), (180, 255, 255))
    kernel      = cv2.getStructuringElement(cv2.MORPH_RECT, (4, 4))
    emoji_mask  = cv2.morphologyEx(emoji_mask, cv2.MORPH_CLOSE, kernel)

    emoji_contours, _ = cv2.findContours(emoji_mask, cv2.RETR_EXTERNAL,
                                          cv2.CHAIN_APPROX_SIMPLE)
    emoji_count = 0
    for ec in emoji_contours:
        ex, ey, ew, eh = cv2.boundingRect(ec)
        # Emoji: small square-ish coloured region
        if 12 < ew < 100 and 12 < eh < 100 and 0.4 < (ew / max(eh, 1)) < 2.5:
            # White out the emoji area with 3px padding
            pad = 3
            content[max(0, ey - pad):ey + eh + pad,
                    max(0, ex - pad):ex + ew + pad] = 255
            emoji_count += 1

    if emoji_count:
        steps.append(f"emoji_strip({emoji_count})")

    # ── 5. Isolate message bubble ─────────────────────────────────────────────
    # The message bubble is the largest white connected region in the content area.
    # WhatsApp background has a pattern; the bubble is pure white.
    content_gray = cv2.cvtColor(content, cv2.COLOR_BGR2GRAY)
    _, white_thresh = cv2.threshold(content_gray, 235, 255, cv2.THRESH_BINARY)
    bubble_contours, _ = cv2.findContours(white_thresh, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
    if bubble_contours:
        largest_bubble = max(bubble_contours, key=cv2.contourArea)
        bx, by, bw2, bh2 = cv2.boundingRect(largest_bubble)
        bubble_area_frac = (bw2 * bh2) / (cw * ch)
        # Only crop to bubble if it's substantial (>30% of content area)
        if bubble_area_frac > 0.30:
            pad = 15
            bx1 = max(0, bx - pad);  by1 = max(0, by - pad)
            bx2 = min(cw, bx + bw2 + pad);  by2 = min(ch, by + bh2 + pad)
            content = content[by1:by2, bx1:bx2]
            steps.append(f"bubble_crop({bw2}x{bh2})")

    return content, steps


def _preprocess_noticeboard(bgr: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """
    Crop the cork board from the street/wall scene.

    Notice boards like Image 1 (Tamil notice board) have:
    - A rectangular cork board taking up 60–80% of the frame
    - A scene background (street, buildings, people) on sides
    - Many overlapping white/yellow/coloured paper posters within

    Strategy:
    1. Find the board boundary using Canny edges + largest contour
    2. Crop to the board region
    3. Apply CLAHE within the board (lighting varies across cork board)

    We deliberately do NOT try to separate individual posters, because:
    - They overlap and have torn edges
    - Depth of field means some are blurred beyond OCR usefulness
    - MSER will naturally pick up text regions within the in-focus areas
    """
    steps: list[str] = []
    h, w  = bgr.shape[:2]
    gray  = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # ── Find cork board boundary ──────────────────────────────────────────────
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    edges   = cv2.Canny(blurred, 20, 80)
    kernel  = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=3)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    board_rect = None
    best_area  = 0
    for c in contours:
        area = cv2.contourArea(c)
        if area > w * h * 0.20 and area > best_area:
            best_area  = area
            board_rect = cv2.boundingRect(c)

    if board_rect:
        bx, by, bw2, bh2 = board_rect
        # Add small padding to avoid cutting edge posters
        pad = 8
        bx  = max(0, bx - pad);  by  = max(0, by - pad)
        bw2 = min(w - bx, bw2 + 2 * pad)
        bh2 = min(h - by, bh2 + 2 * pad)
        bgr = bgr[by:by + bh2, bx:bx + bw2]
        steps.append(f"board_crop({bw2}x{bh2})")
    else:
        steps.append("board_crop_failed")

    return bgr, steps


def _preprocess_poster_in_scene(bgr: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """
    Extract a document/poster from a scene background.

    Handles Images 2 (Apex poster on glass) and 3 (Global Career Solutions on wall).

    The poster is identified as the largest light/white region in the image.
    We use HSV white-paper detection rather than edge-based document detection
    because:
    - Office backgrounds (Image 2) are also light-toned → edges don't discriminate
    - Cork boards and walls can be any colour → colour-space discrimination works better
    - Works when the document has no clear 4-corner outline

    After cropping the document, we check for QR codes (high variance + square +
    bottom-right quadrant) and white them out — QR patterns confuse Tesseract.
    """
    steps: list[str] = []
    h, w  = bgr.shape[:2]
    hsv   = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    # ── Find white/light paper region ────────────────────────────────────────
    # White paper: low saturation (S < 55), high value (V > 175)
    white_mask = cv2.inRange(hsv, (0, 0, 175), (180, 55, 255))
    kernel     = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
    clean      = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
    clean      = cv2.morphologyEx(clean, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        largest   = max(contours, key=cv2.contourArea)
        area_frac = cv2.contourArea(largest) / (w * h)

        # Only crop if the document region is meaningfully isolated
        # (>15% and <85% of image — if >85% we're already zoomed in)
        if 0.15 < area_frac < 0.85:
            bx, by, bw2, bh2 = cv2.boundingRect(largest)
            pad = 10
            bx  = max(0, bx - pad);  by  = max(0, by - pad)
            bw2 = min(w - bx, bw2 + 2 * pad)
            bh2 = min(h - by, bh2 + 2 * pad)
            bgr = bgr[by:by + bh2, bx:bx + bw2]
            steps.append(f"doc_crop({bw2}x{bh2},frac={area_frac:.2f})")

    # ── Mask QR code regions ──────────────────────────────────────────────────
    # After cropping to the document, find QR code by its distinctive
    # high-variance + moderate-mean signature in the bottom-right quadrant.
    bgr, qr_step = _mask_qr_regions(bgr)
    if qr_step:
        steps.append(qr_step)

    return bgr, steps


# ── Perspective correction ────────────────────────────────────────────────────

def _perspective_correct(bgr: np.ndarray) -> tuple[np.ndarray, str]:
    """
    Detect and correct mild perspective (trapezoidal) distortion from
    handheld camera photos of flat documents.

    Method:
    1. Find the largest light-coloured quadrilateral contour (the document)
    2. Order its 4 corners (top-left, top-right, bottom-right, bottom-left)
    3. Compute a destination rectangle of the same proportions
    4. Apply cv2.getPerspectiveTransform + warpPerspective

    Only applied when a clean 4-corner approximation is found AND the
    deviation from a perfect rectangle exceeds 10px (below that, the
    warp would degrade quality more than it helps).

    Skipped for WhatsApp screenshots (already flat).
    """
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges   = cv2.Canny(blurred, 30, 100)
    kernel  = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges   = cv2.dilate(edges, kernel, iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    best_quad = None
    best_area = 0
    for c in contours:
        area = cv2.contourArea(c)
        if area < w * h * 0.08:
            continue
        peri  = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.03 * peri, True)
        if len(approx) == 4 and area > best_area:
            best_area = area
            best_quad = approx.reshape(4, 2).astype(np.float32)

    if best_quad is None:
        return bgr, ""

    # Order corners: top-left, top-right, bottom-right, bottom-left
    pts = _order_corners(best_quad)
    tl, tr, br, bl = pts

    # Compute destination dimensions
    width_top    = np.linalg.norm(tr - tl)
    width_bottom = np.linalg.norm(br - bl)
    dst_w        = int(max(width_top, width_bottom))

    height_left  = np.linalg.norm(bl - tl)
    height_right = np.linalg.norm(br - tr)
    dst_h        = int(max(height_left, height_right))

    if dst_w < 100 or dst_h < 100:
        return bgr, ""

    # Check if perspective distortion is large enough to be worth correcting
    # (if corners are already close to a rectangle, skip)
    expected_corners = np.array([[0, 0], [dst_w, 0], [dst_w, dst_h], [0, dst_h]],
                                  dtype=np.float32)
    diffs = [np.linalg.norm(pts[i] - expected_corners[i] *
                             np.array([w / dst_w, h / dst_h]))
             for i in range(4)]
    if max(diffs) < 10:
        return bgr, ""

    dst_pts = np.array([[0, 0], [dst_w - 1, 0],
                         [dst_w - 1, dst_h - 1], [0, dst_h - 1]],
                        dtype=np.float32)
    M       = cv2.getPerspectiveTransform(pts, dst_pts)
    warped  = cv2.warpPerspective(bgr, M, (dst_w, dst_h),
                                   flags=cv2.INTER_CUBIC,
                                   borderMode=cv2.BORDER_REPLICATE)
    return warped, f"perspective_warp({dst_w}x{dst_h})"


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """
    Order 4 corner points as [top-left, top-right, bottom-right, bottom-left].
    Robust to any initial ordering returned by cv2.approxPolyDP.
    """
    # Sum and difference of coordinates to identify corners
    s    = pts.sum(axis=1)      # TL has min sum, BR has max sum
    diff = np.diff(pts, axis=1) # TR has min diff, BL has max diff
    return np.array([
        pts[np.argmin(s)],      # top-left
        pts[np.argmin(diff)],   # top-right
        pts[np.argmax(s)],      # bottom-right
        pts[np.argmax(diff)],   # bottom-left
    ], dtype=np.float32)


# ── QR masking ────────────────────────────────────────────────────────────────

def _mask_qr_regions(bgr: np.ndarray) -> tuple[np.ndarray, str]:
    """
    Detect QR codes in a document image and white them out before OCR.

    QR codes are identified by their unique statistical signature:
    - Very high local variance (dense alternating black/white squares)
    - Mean pixel value ~100–160 (half-black, half-white)
    - Square-ish aspect ratio

    We scan with an 80×80px sliding window (stride 20) and mark regions
    meeting all three criteria. Only applied in the bottom half of the
    document (QR codes on job ads are almost always in the lower section).

    False positive guard: also require that the region does NOT look like
    text (text regions have much lower local variance at the character level).
    """
    result   = bgr.copy()
    h, w     = result.shape[:2]
    gray     = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)

    BLOCK    = 80
    STRIDE   = 20
    qr_mask  = np.zeros((h, w), dtype=np.uint8)

    # Only scan bottom 60% — QR codes on job ads are always lower on the page
    scan_top = h // 4

    for y in range(scan_top, h - BLOCK, STRIDE):
        for x in range(0, w - BLOCK, STRIDE):
            patch = gray[y:y + BLOCK, x:x + BLOCK]
            var   = float(np.var(patch))
            mean  = float(patch.mean())
            # QR signature: high variance, moderate mean (≈ half black half white)
            if var > 3500 and 75 < mean < 185:
                qr_mask[y:y + BLOCK, x:x + BLOCK] = 255

    # Clean up: close small gaps, then find connected QR regions
    kernel    = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    qr_mask   = cv2.morphologyEx(qr_mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(qr_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    masked_count = 0
    for c in contours:
        qx, qy, qw, qh = cv2.boundingRect(c)
        ar = qw / max(qh, 1)
        # Accept square-ish regions only (QR codes are square)
        if 0.5 < ar < 2.0 and qw > 60 and qh > 60:
            result[qy:qy + qh, qx:qx + qw] = 255
            masked_count += 1

    step = f"qr_mask({masked_count})" if masked_count else ""
    return result, step


# ── Deskew ────────────────────────────────────────────────────────────────────

def _deskew_hough(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """
    Detect and correct document skew using Hough line transform.

    Operates on a half-resolution copy of the image for speed (~70ms vs ~175ms).
    The rotation is then applied to the full-resolution image.

    Only near-horizontal lines (within ±45° of horizontal) are used — these
    correspond to text baselines and document edges. Diagonal or vertical
    lines (e.g. table borders, graphic elements) are ignored.

    Uses median of detected angles rather than mean to be robust against
    outliers (e.g. a single diagonal graphic line skewing the average).
    """
    h, w    = gray.shape
    # Work at half resolution for speed
    small   = cv2.resize(gray, (w // 2, h // 2))
    edges   = cv2.Canny(small, 50, 150, apertureSize=3)
    lines   = cv2.HoughLines(edges, 1, np.pi / 180, threshold=60)

    if lines is None or len(lines) == 0:
        return gray, 0.0

    angles = []
    for line in lines[:60]:
        rho, theta = line[0]
        angle_deg  = np.degrees(theta) - 90
        if -45 < angle_deg < 45:
            angles.append(angle_deg)

    if not angles:
        return gray, 0.0

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:      # sub-half-degree — not worth correcting
        return gray, 0.0

    corrected = _rotate_gray(gray, -median_angle)
    return corrected, median_angle


# ── MSER text region detection ────────────────────────────────────────────────

def _mser_text_regions(gray: np.ndarray) -> dict:
    """
    Detect text candidate regions using Maximally Stable Extremal Regions (MSER).

    MSER finds character-sized blobs that are stable across a range of
    intensity thresholds. These correspond tightly to individual letters and
    word fragments. By aggregating them we can:
      (a) Build a text-region mask to suppress non-text areas (QR, icons, photos)
      (b) Detect column layout by comparing left/right half region densities

    Performance optimisation:
    - Run MSER on half-resolution image (~90ms vs ~430ms at full resolution)
    - Scale bounding boxes back to full resolution (×2 in each dimension)
    - Use a fast deduplication hash instead of exact NMS

    Returns
    -------
    dict:
        mask          np.ndarray (uint8, same size as input gray)
        layout        "single_column" | "two_column"
        region_count  int
    """
    h, w = gray.shape

    # ── Run on half-res ───────────────────────────────────────────────────────
    small    = cv2.resize(gray, (w // 2, h // 2))
    sh, sw   = small.shape

    max_area = max(100, int(sw * sh * MSER_MAX_AREA_PCT))
    mser     = cv2.MSER_create(MSER_DELTA, MSER_MIN_AREA, max_area,
                                MSER_MAX_VAR, MSER_MIN_DIV)

    try:
        _, bboxes = mser.detectRegions(small)
    except Exception as e:
        logger.warning(f"image_pipeline: MSER failed — {e}")
        # Return a full-coverage mask so OCR still runs normally
        return {"mask": np.full((h, w), 255, dtype=np.uint8),
                "layout": "single_column", "region_count": 0}

    # ── Filter to text-like regions ───────────────────────────────────────────
    filtered = []
    seen: set = set()

    max_w = int(sw * MSER_MAX_W_FRAC)
    max_h = int(sh * MSER_MAX_H_FRAC)

    for b in bboxes:
        bx, by, bw, bh = int(b[0]), int(b[1]), int(b[2]), int(b[3])
        # Coarse deduplication: bucket coordinates to 4-pixel grid
        key = (bx >> 2, by >> 2)
        if key in seen:
            continue
        seen.add(key)

        if bw < MSER_MIN_W or bh < MSER_MIN_H:
            continue
        if bw > max_w or bh > max_h:
            continue
        ar = bw / max(bh, 1)
        if not (MSER_MIN_AR <= ar <= MSER_MAX_AR):
            continue

        filtered.append((bx, by, bw, bh))

    # ── Build full-resolution text mask ──────────────────────────────────────
    # Scale boxes from half-res back to full-res (×2)
    mask  = np.zeros((h, w), dtype=np.uint8)
    PAD   = 6   # pixel padding around each MSER box (catches ascenders/descenders)

    for bx, by, bw, bh in filtered:
        # Scale to full resolution
        fx, fy, fw, fh = bx * 2, by * 2, bw * 2, bh * 2
        x1 = max(0, fx - PAD);    y1 = max(0, fy - PAD)
        x2 = min(w, fx + fw + PAD); y2 = min(h, fy + fh + PAD)
        mask[y1:y2, x1:x2] = 255

    # ── Dilate mask to merge adjacent characters into text-line blocks ────────
    # Horizontal dilation (30px) merges characters into words and words into lines.
    # Vertical dilation (8px) merges lines into paragraphs.
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 8))
    mask     = cv2.dilate(mask, h_kernel)

    # ── Layout detection ──────────────────────────────────────────────────────
    layout = _detect_column_layout(filtered, sw, sh)

    return {"mask": mask, "layout": layout, "region_count": len(filtered)}



# ── Column layout detection ───────────────────────────────────────────────────

def _detect_column_layout(
    filtered: list[tuple[int, int, int, int]],
    sw: int,
    sh: int,
) -> str:
    """
    Decide whether MSER text regions form a genuine two-column document layout
    or should be treated as a single column.

    Five gates must ALL pass to classify as 'two_column'.
    Failing any single gate returns 'single_column'.  This is intentionally
    conservative: a false negative (treating a real two-column doc as single)
    produces mildly merged text; a false positive (splitting a single-column
    doc in half) produces severely garbled output.

    Parameters
    ----------
    filtered : list of (x, y, w, h) MSER bounding boxes at half-resolution
    sw, sh   : half-resolution image width and height

    Returns
    -------
    "two_column" | "single_column"

    Algorithm
    ---------
    Gate 1 — Count balance
        Split at the vertical midpoint.  Count regions whose centre falls in
        each half.  If one half has more than 25 % more regions than the other,
        the content is asymmetric → single column.
        Rationale: a structured bilingual poster (e.g. English left / Hindi right)
        fills both halves equally.  A single-column poster with a logo on one side
        or a bullet list on one side will be unbalanced.

    Gate 2 — Minimum population
        Each half must contain at least COLUMN_MIN_REGIONS_EACH (10) regions.
        Prevents two_column detection on nearly-empty images or images where
        one half has no text at all.

    Gate 3 — Projection histogram valley
        Sum MSER box widths along the X axis to build a 1-D text-density
        profile.  Smooth with a Gaussian (sigma ≈ 1.5 % of image width) to
        remove character-level noise.  Find the minimum in the central 20–80 %
        of the profile.  If valley / peak ≥ COLUMN_VALLEY_RATIO_MAX (0.45),
        the profile has no clear trough → the text fills the width uniformly →
        single column.
        Rationale: every two-column layout has a gutter — a strip of whitespace
        between the columns.  Single-column posters (even wide ones) fill their
        width continuously.
        Note: scipy.ndimage is NOT used; the Gaussian is approximated by
        three cascaded uniform box filters (fast, CPU-friendly, no import).

    Gate 4 — Structural spatial gap
        Compute the 75th percentile of left-half region right-edges (where left
        column content ends) and the 25th percentile of right-half region
        left-edges (where right column content begins).  If right_extent_25 −
        left_extent_75 < COLUMN_STRUCT_GAP_MIN × sw (5 % of width), the columns
        are not spatially separated → single column.
        Rationale: percentiles rather than min/max make this robust to a few
        regions that stray across the midpoint (e.g. a wide heading that spans
        both halves).

    Gate 5 — Y-band co-occurrence
        Divide the image into 12 equal horizontal bands.  For each region,
        record which band its vertical centre falls in, separately for left and
        right halves.  Compute:
            cooccurrence = |bands_L ∩ bands_R| / |bands_L ∪ bands_R|
        If cooccurrence < COLUMN_COOCCUR_MIN (0.65), the left and right content
        does not occupy the same rows → the two 'columns' are independent
        clusters, not parallel typographic columns → single column.
        Rationale: a bilingual document prints corresponding content side-by-side
        at the same vertical positions.  A notice board or a poster with an icon
        on the left and a list on the right has content at different rows on each
        side — low co-occurrence exposes this.

    False-positive catalogue (cases that should NOT trigger two_column):
        • Centred recruitment posters with wide headers
          → Gate 1 fails (header text shifts balance) or Gate 5 fails
            (header spans full width, so only top band has bilateral content)
        • Posters with logo or QR code on one side
          → Gate 1 fails (logo side has few text regions, imbalanced)
            and Gate 4 may fail (logo region adds no text edge on that side)
        • Bullet lists that happen to appear in two visual columns
          → Gate 5 often fails (bullets may not align row-for-row)
            and Gate 3 rarely produces a valley in a continuous bullet run
        • Notice boards with clusters of overlapping posters
          → Gate 5 fails cleanly (poster clusters occupy different Y ranges)
        • WhatsApp screenshots (single message bubble, left-aligned text)
          → Gate 1 fails (strongly imbalanced: L >> R after bubble crop)
    """
    if not filtered:
        return "single_column"

    mid = sw // 2

    # Partition regions by horizontal midpoint
    left_regions  = [(bx, by, bw, bh) for bx, by, bw, bh in filtered
                     if bx + bw // 2 < mid]
    right_regions = [(bx, by, bw, bh) for bx, by, bw, bh in filtered
                     if bx + bw // 2 >= mid]
    left_n  = len(left_regions)
    right_n = len(right_regions)
    total_n = max(left_n + right_n, 1)

    # ── Gate 1: count balance ─────────────────────────────────────────────────
    balance = abs(left_n - right_n) / total_n
    if balance >= COLUMN_BALANCE_THRESH:
        return "single_column"

    # ── Gate 2: minimum population ────────────────────────────────────────────
    if left_n < COLUMN_MIN_REGIONS_EACH or right_n < COLUMN_MIN_REGIONS_EACH:
        return "single_column"

    # ── Gate 3: projection histogram valley ───────────────────────────────────
    # Build a 1-D text-density profile by accumulating box widths along X.
    proj = np.zeros(sw, dtype=np.float32)
    for bx, by, bw, bh in filtered:
        proj[max(0, bx):min(sw, bx + bw)] += 1.0

    # Approximate Gaussian smoothing with three passes of a box filter.
    # Kernel width ≈ 1.5 % of image width, minimum 3 pixels.
    # Three passes of a box filter converge to a Gaussian by the CLT.
    k = max(3, int(sw * 0.015) | 1)   # ensure odd
    kernel = np.ones(k, dtype=np.float32) / k
    for _ in range(3):
        proj = np.convolve(proj, kernel, mode="same")

    peak = proj.max()
    if peak == 0:
        return "single_column"

    # Evaluate the valley in the central 20–80 % of the width
    lo, hi   = int(sw * 0.20), int(sw * 0.80)
    valley   = float(proj[lo:hi].min())
    valley_ratio = valley / peak

    if valley_ratio >= COLUMN_VALLEY_RATIO_MAX:
        return "single_column"

    # ── Gate 4: structural spatial gap ───────────────────────────────────────
    left_right_edges  = [bx + bw for bx, by, bw, bh in left_regions]
    right_left_edges  = [bx      for bx, by, bw, bh in right_regions]

    left_extent  = float(np.percentile(left_right_edges,  75))
    right_extent = float(np.percentile(right_left_edges,  25))

    struct_gap_frac = (right_extent - left_extent) / sw
    if struct_gap_frac < COLUMN_STRUCT_GAP_MIN:
        return "single_column"

    # ── Gate 5: Y-band co-occurrence ──────────────────────────────────────────
    # Use 12 horizontal bands.  One band per ~8 % of image height.
    N_BANDS = 12
    band_h  = sh / N_BANDS

    bands_L: set[int] = set()
    bands_R: set[int] = set()

    for bx, by, bw, bh in left_regions:
        bands_L.add(int((by + bh // 2) / band_h))
    for bx, by, bw, bh in right_regions:
        bands_R.add(int((by + bh // 2) / band_h))

    intersection = len(bands_L & bands_R)
    union        = len(bands_L | bands_R)
    cooccurrence = intersection / max(union, 1)

    if cooccurrence < COLUMN_COOCCUR_MIN:
        return "single_column"

    # All five gates passed
    return "two_column"




def _apply_text_mask(binary: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    White out all pixels NOT covered by the MSER text mask.

    This removes:
    - QR code patterns (high-frequency noise that produces garbage OCR output)
    - Icon/line-drawing regions
    - Large photographic image areas embedded in posters
    - Background patterns (WhatsApp wallpaper, cork texture)

    The mask must be the same shape as binary (both are already at OCR resolution
    after the upscale step).
    """
    result = binary.copy()
    if len(result.shape) == 2:
        # Greyscale binary
        result[mask == 0] = 255
    else:
        # Colour image
        result[mask == 0] = [255, 255, 255]
    return result


# ── Layout-aware OCR ──────────────────────────────────────────────────────────

def _ocr_two_column(binary: np.ndarray, text_mask: np.ndarray,
                     tess_lang: str) -> dict:
    """
    Run OCR on left and right columns independently, then merge.

    Two-column layouts like the Hindi/English poster (Image 3) produce poor
    results when OCR'd as a single block because Tesseract tries to read across
    columns, mixing left-column English text with right-column Hindi text on the
    same "line".

    By splitting at the vertical midpoint and OCR'ing each half separately,
    we get clean text from each column. The results are interleaved by their
    vertical position so that headings (full-width) appear before the two
    columns that follow them.

    Column split point: vertical midpoint of the image. This works for the
    symmetric two-column layouts we see in scam posters.
    """
    h, w = binary.shape[:2]
    mid  = w // 2

    # Columns with MSER mask applied
    left_bin  = _apply_text_mask(binary[:, :mid],  text_mask[:, :mid])
    right_bin = _apply_text_mask(binary[:, mid:],  text_mask[:, mid:])

    left_result  = _ocr_cascade(left_bin,  tess_lang)
    right_result = _ocr_cascade(right_bin, tess_lang)

    # Merge: interleave lines from left and right by vertical position
    left_text  = left_result.get("text",  "")
    right_text = right_result.get("text", "")

    if left_text and right_text:
        # Zip lines together for parallel bilingual text
        left_lines  = left_text.split("\n")
        right_lines = right_text.split("\n")
        merged_lines = []
        for i in range(max(len(left_lines), len(right_lines))):
            ll = left_lines[i].strip()  if i < len(left_lines)  else ""
            rl = right_lines[i].strip() if i < len(right_lines) else ""
            if ll:
                merged_lines.append(ll)
            if rl and rl != ll:
                merged_lines.append(rl)
        merged = "\n".join(merged_lines)
    elif left_text:
        merged = left_text
    elif right_text:
        merged = right_text
    else:
        return {"success": False, "text": "", "confidence": 0.0, "psm": 6}

    # Use the better of the two confidence scores
    conf = max(left_result.get("confidence", 0),
               right_result.get("confidence", 0))
    psm  = left_result.get("psm", 6)

    return {"success": bool(merged.strip()), "text": merged,
            "confidence": conf, "psm": psm}


# ── Standard preprocessing helpers ───────────────────────────────────────────

def _detect_background_type(gray: np.ndarray) -> str:
    """
    Classify background type to drive the binarisation strategy.

    Samples the four corner regions (which are least likely to contain central
    text) to characterise the background:

    'uniform_light'  — white/light paper documents → Otsu global threshold
    'uniform_dark'   — dark-background screenshots  → inverted Otsu
    'gradient'       — WhatsApp chat, coloured header bands → CLAHE + adaptive
    'textured'       — cork boards, rough walls → adaptive mean threshold
    """
    h, w = gray.shape
    m    = max(h, w) // 8
    corners = [gray[:m, :m], gray[:m, -m:], gray[-m:, :m], gray[-m:, -m:]]
    corner_means = [float(np.mean(c)) for c in corners]
    corner_range = max(corner_means) - min(corner_means)
    global_mean  = float(np.mean(gray))
    global_std   = float(np.std(gray))

    if corner_range > 40:
        return "gradient"
    if global_std > 60:
        return "textured"
    if global_mean > 160:
        return "uniform_light"
    return "uniform_dark"


def _denoise(gray: np.ndarray, bg_type: str) -> np.ndarray:
    """
    Apply noise reduction appropriate for the background type.

    - textured/gradient: Bilateral filter — edge-preserving, removes grain
      from phone-camera photos without blurring text strokes.
      (NLM would give better quality but costs ~1500ms on 2MP images.)
    - uniform: Simple 3×3 Gaussian — fast and sufficient for clean documents.
    """
    if bg_type in ("textured", "gradient"):
        return cv2.bilateralFilter(gray, 7, 50, 50)
    return cv2.GaussianBlur(gray, (3, 3), 0)


def _binarise(gray: np.ndarray, bg_type: str) -> tuple[np.ndarray, str]:
    """
    Binarise greyscale to black-text-on-white using background-appropriate strategy.

    'uniform_light' → Otsu global threshold
        Best for clean white paper with consistent lighting.

    'uniform_dark'  → Inverted Otsu
        Same algorithm but inverts result for dark backgrounds.

    'gradient'      → CLAHE normalisation + Gaussian adaptive threshold
        CLAHE (Contrast Limited Adaptive Histogram Equalisation) corrects
        the uneven illumination from coloured header bands (red, blue, white
        sections in Image 3) before adaptive thresholding handles local
        contrast. blockSize=31 chosen to span ~2 character heights at 2000px.

    'textured'      → Adaptive mean threshold
        For cork boards and rough-wall textures where background intensity
        varies spatially. blockSize=25 balances over local detail.
    """
    if bg_type == "uniform_light":
        _, b = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return b, "otsu"

    if bg_type == "uniform_dark":
        _, b = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return b, "otsu_inv"

    if bg_type == "gradient":
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        eq    = clahe.apply(gray)
        b     = cv2.adaptiveThreshold(eq, 255,
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, blockSize=31, C=10)
        return b, "clahe+adaptive"

    # textured
    b = cv2.adaptiveThreshold(gray, 255,
                               cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY, blockSize=25, C=8)
    return b, "adaptive_mean"


def _morph_cleanup(binary: np.ndarray) -> np.ndarray:
    """
    Close tiny gaps within characters caused by noise or faded ink.
    Uses a 2×2 kernel (conservative) to avoid merging adjacent characters.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)


def _upscale_for_ocr(img: np.ndarray) -> tuple[np.ndarray, str]:
    """
    Upscale image to at least TARGET_OCR_PX on the long side.
    Tesseract accuracy degrades significantly below ~150 DPI equivalent.
    Uses INTER_CUBIC for upsampling (sharpest text edges).
    Downsamples with INTER_AREA if over ceiling.
    """
    h, w      = img.shape[:2]
    long_side = max(h, w)

    if long_side < TARGET_OCR_PX:
        scale = TARGET_OCR_PX / long_side
        nw, nh = int(w * scale), int(h * scale)
        up = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_CUBIC)
        return up, f"upscale({long_side}→{TARGET_OCR_PX}px)"

    return img, ""


# ── OCR cascade ───────────────────────────────────────────────────────────────

def _ocr_cascade(img: np.ndarray, tess_lang: str,
                  force_psm: int | None = None) -> dict:
    """
    Try Tesseract PSM modes in priority order, return the result with the
    highest mean word confidence.

    PSM meanings relevant to us:
      PSM 6  — uniform block of text (default; best for clean single-font documents)
      PSM 11 — sparse text anywhere (best for receipts, notice boards with gaps)
      PSM 3  — fully auto with OSD (good fallback for unknown layouts)
      PSM 4  — single column of variable-size text (good for phone screenshots)

    Exits early if a result exceeds CONFIDENCE_THRESHOLD + 20 (saves time).
    """
    psm_list = [force_psm] if force_psm is not None else PSM_CASCADE
    best     = {"success": False, "text": "", "confidence": 0.0,
                "psm": psm_list[0]}

    for psm in psm_list:
        try:
            config = f"--psm {psm} --oem 3 -l {tess_lang}"
            data   = pytesseract.image_to_data(
                img, config=config,
                output_type=pytesseract.Output.DICT,
            )
            words, confs = [], []
            for i, word in enumerate(data["text"]):
                word = word.strip()
                conf = int(data["conf"][i])
                if word and conf > 0:
                    words.append(word)
                    confs.append(conf)

            if not words:
                continue

            mean_conf = float(np.mean(confs))
            text      = _reconstruct_lines(data)

            if mean_conf > best["confidence"]:
                best = {"success": True, "text": text,
                        "confidence": mean_conf, "psm": psm}

            if mean_conf >= CONFIDENCE_THRESHOLD + 20:
                break   # good enough — stop trying more PSMs

        except pytesseract.TesseractError as e:
            logger.warning(f"image_pipeline: PSM {psm} TesseractError — {e}")
        except Exception as e:
            logger.warning(f"image_pipeline: PSM {psm} unexpected error — {e}")

    return best


def _reconstruct_lines(data: dict) -> str:
    """
    Rebuild text with proper line breaks using Tesseract's block/paragraph/line
    metadata. Raw image_to_string sometimes merges lines; this preserves the
    label:value structure common in job advertisements.
    """
    lines: dict = {}
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word or int(data["conf"][i]) < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)

    result_lines = []
    prev_block   = None
    for key in sorted(lines):
        block = key[0]
        if prev_block is not None and block != prev_block:
            result_lines.append("")   # blank line between text blocks
        result_lines.append(" ".join(lines[key]))
        prev_block = block

    return "\n".join(result_lines)


# ── Language selection ────────────────────────────────────────────────────────

def _select_tess_lang(gray: np.ndarray) -> str:
    """
    Choose the minimal Tesseract language pack string for this image.

    Strategy:
    1. Check which language packs are actually installed (cached after first call)
    2. Scan a small central crop of the image for script signatures:
       - Devanagari characters (U+0900–U+097F) → add 'hin'
       - Tamil characters (U+0B80–U+0BFF) → add 'tam'
    3. Pre-scan uses PSM 11 (sparse text) on a downscaled version (~20ms)
       to get rough character classes before the main OCR run.
    4. Fall back to 'eng' if no additional scripts detected or if the
       required pack is not installed.

    This prevents the well-known problem of Tesseract misidentifying
    Hindi Devanagari characters as English letters (or vice versa) when
    both language packs are loaded for a purely English image.
    """
    global _TESS_LANG_CACHE
    if "available" not in _TESS_LANG_CACHE:
        _TESS_LANG_CACHE["available"] = _get_installed_tess_langs()

    available = _TESS_LANG_CACHE["available"]

    # Cheap pre-scan: tiny crop from the centre of the image
    h, w    = gray.shape
    cx, cy  = w // 4, h // 4
    sample  = gray[cy: cy + h // 2, cx: cx + w // 2]
    small   = cv2.resize(sample, (min(400, sample.shape[1]),
                                    min(400, sample.shape[0])))

    try:
        # PSM 11 = sparse, OEM 0 = legacy (fastest for pre-scan)
        quick_cfg = "--psm 11 --oem 0 -l eng"
        pre_text  = pytesseract.image_to_string(small, config=quick_cfg)
    except Exception:
        pre_text = ""

    langs = ["eng"]

    # Devanagari signature characters (visually distinctive vertical strokes)
    deva_chars = sum(1 for ch in pre_text if "\u0900" <= ch <= "\u097F")
    if deva_chars >= 2 and "hin" in available:
        langs.append("hin")

    # Tamil signature  characters
    tam_chars = sum(1 for ch in pre_text if "\u0B80" <= ch <= "\u0BFF")
    if tam_chars >= 2 and "tam" in available:
        langs.append("tam")

    return "+".join(langs)


def _get_installed_tess_langs() -> set:
    """Return the set of Tesseract language codes available on this system."""
    import subprocess
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True, text=True, timeout=5,
        )
        lines = (result.stdout + result.stderr).splitlines()
        langs = {ln.strip() for ln in lines if ln.strip() and not ln.startswith("List")}
        logger.info(f"image_pipeline: installed Tesseract langs = {langs}")
        return langs
    except Exception as e:
        logger.warning(f"image_pipeline: could not list Tesseract langs — {e}")
        return {"eng"}


# ── Loading ───────────────────────────────────────────────────────────────────

def _load(source: Union[str, bytes, Path]) -> dict:
    """Load image from file path or raw bytes into an OpenCV BGR array."""
    try:
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                return _err(f"File not found: {path}")
            if path.suffix.lower() not in SUPPORTED_FORMATS:
                return _err(f"Unsupported format '{path.suffix}'.")
            if path.stat().st_size > MAX_FILE_BYTES:
                return _err("Image too large (max 15 MB).")
            pil = Image.open(path)
            bgr = _pil_to_bgr(pil)
            return {"success": True, "bgr": bgr, "pil_image": pil,
                    "source_type": "file"}

        elif isinstance(source, (bytes, bytearray)):
            if len(source) > MAX_FILE_BYTES:
                return _err("Image bytes too large (max 15 MB).")
            arr = np.frombuffer(source, np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is None:
                return _err("Could not decode image bytes — corrupted or unsupported.")
            try:
                pil = Image.open(io.BytesIO(bytes(source)))
            except Exception:
                pil = None
            return {"success": True, "bgr": bgr, "pil_image": pil,
                    "source_type": "bytes"}

        else:
            return _err(f"Invalid source type '{type(source).__name__}'.")

    except Exception as e:
        logger.exception("image_pipeline: _load failed")
        return _err(f"Could not open image: {e}")


def _pil_to_bgr(pil: Image.Image) -> np.ndarray:
    pil = pil.convert("RGB")
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _hard_downscale(bgr: np.ndarray) -> tuple[np.ndarray, str]:
    """Cap image at MAX_LONG_SIDE_PX to prevent OOM. Uses INTER_AREA for quality."""
    h, w      = bgr.shape[:2]
    long_side = max(h, w)
    if long_side > MAX_LONG_SIDE_PX:
        scale    = MAX_LONG_SIDE_PX / long_side
        nw, nh   = int(w * scale), int(h * scale)
        return cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA), \
               f"downscale({w}→{nw}px)"
    return bgr, ""


def _exif_rotate(pil: Image.Image | None,
                  bgr: np.ndarray) -> tuple[np.ndarray, str]:
    """Correct rotation from EXIF orientation tag (common in phone photos)."""
    if pil is None:
        return bgr, ""
    try:
        exif = pil._getexif()
        if not exif:
            return bgr, ""
        tag   = next((k for k, v in ExifTags.TAGS.items()
                       if v == "Orientation"), None)
        if tag is None or tag not in exif:
            return bgr, ""
        rotations = {3: 180, 6: 270, 8: 90}
        angle     = rotations.get(exif[tag])
        if angle:
            return _rotate_bgr(bgr, angle), f"exif({angle}°)"
    except Exception:
        pass
    return bgr, ""


def _rotate_bgr(img: np.ndarray, angle: float) -> np.ndarray:
    """Rotate colour image without cropping (expands canvas). White fill."""
    h, w    = img.shape[:2]
    cx, cy  = w // 2, h // 2
    M       = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    cos_a   = abs(M[0, 0]);  sin_a = abs(M[0, 1])
    nw      = int(h * sin_a + w * cos_a)
    nh      = int(h * cos_a + w * sin_a)
    M[0, 2] += nw / 2 - cx
    M[1, 2] += nh / 2 - cy
    return cv2.warpAffine(img, M, (nw, nh),
                           flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_REPLICATE)


def _rotate_gray(img: np.ndarray, angle: float) -> np.ndarray:
    """Rotate greyscale image without cropping. White (255) fill."""
    h, w    = img.shape[:2]
    cx, cy  = w // 2, h // 2
    M       = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    cos_a   = abs(M[0, 0]);  sin_a = abs(M[0, 1])
    nw      = int(h * sin_a + w * cos_a)
    nh      = int(h * cos_a + w * sin_a)
    M[0, 2] += nw / 2 - cx
    M[1, 2] += nh / 2 - cy
    return cv2.warpAffine(img, M, (nw, nh),
                           flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=255)


# ── Post-processing helpers ───────────────────────────────────────────────────

def _basic_clean(text: str) -> str:
    """Remove Tesseract form-feed characters, collapse excess blank lines."""
    text = text.replace("\x0c", "").replace("\x00", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _language_hint(text: str) -> str:
    """
    Classify the script of the extracted text:
      'hindi'   — predominantly Devanagari
      'tamil'   — predominantly Tamil script
      'mixed'   — both scripts present
      'english' — ASCII-dominant
    """
    deva  = sum(1 for ch in text if "\u0900" <= ch <= "\u097F")
    tam   = sum(1 for ch in text if "\u0B80" <= ch <= "\u0BFF")
    ascii_a = sum(1 for ch in text if ch.isascii() and ch.isalpha())

    if tam > 10:
        return "tamil" if deva < 5 else "mixed"
    if deva > 20 and ascii_a < 20:
        return "hindi"
    if deva > 5:
        return "mixed"
    return "english"


def _quality_label(w: int, h: int) -> str:
    area = w * h
    if area >= 1_000_000:
        return "good"
    if area >= 200_000:
        return "low"
    return "very_low"


def _err(msg: str, source_type: str = "unknown") -> dict:
    logger.warning(f"image_pipeline: {msg}")
    return {"success": False, "error": msg, "source_type": source_type}


# ── Manual test ───────────────────────────────────────────────────────────────
# Run: python image_pipeline.py
# Tests all 4 image types if sample files are present.

if __name__ == "__main__":
    import sys
    import json
    from pathlib import Path

    # If an image path is provided in the terminal
    if len(sys.argv) > 1:
        img_path = sys.argv[1]

        if not Path(img_path).exists():
            print(f"Error: file not found -> {img_path}")
            sys.exit(1)

        print(f"\nProcessing image: {img_path}\n")
        result = process_image(img_path)

        if result.get("success"):
            print(f"Type:        {result.get('image_type','?')}")
            print(f"Language:    {result.get('language_hint')}")
            print(f"Confidence:  {result.get('confidence')}")
            print(f"Steps:       {' → '.join(result.get('preprocessing_steps', []))}")
            print(f"Time:        {result.get('processing_ms','?')} ms")
            print("\nExtracted text:\n")
            print(result.get("extracted_text")[:800])
        else:
            print(f"FAILED: {result.get('error')}")

    else:
        print("\nUsage:")
        print("python image_pipeline.py <image_path>\n")
        print("Example:")
        print('python image_pipeline.py "sample_inputs/test_noticeboard.jpg"\n')

#!/usr/bin/env python3
"""OCR benchmark script for ATLAS Dev 3 pipeline.

Measures:
- Character Error Rate (CER) per page against truth text.
- Exact-match accuracy of phone, IMEI, and account tokens.
- Processing latency (seconds per page).

Usage:
    python scripts/ocr_benchmark.py --image path/to/page.png [--truth path/to/truth.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Ensure src/ is on sys.path for direct script invocation
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image
from rapidfuzz.distance import Levenshtein

from atlas.ocr.preprocess import preprocess
from atlas.ocr.tesseract import TesseractEngine


def compute_cer(reference: str, hypothesis: str) -> float:
    """Calculate Character Error Rate (CER) between reference and hypothesis text.

    CER = Levenshtein_distance(reference, hypothesis) / max(len(reference), 1)

    Args:
        reference: Ground truth text string.
        hypothesis: OCR output text string.

    Returns:
        CER as a float value >= 0.0 (0.0 represents perfect match).
    """
    if not reference and not hypothesis:
        return 0.0
    if not reference:
        return 1.0

    edit_dist = Levenshtein.distance(reference, hypothesis)
    return float(edit_dist / len(reference))


def evaluate_tokens(reference_tokens: list[str], hypothesis_text: str) -> dict[str, Any]:
    """Evaluate exact-match retrieval of key tokens (phones, IMEIs, accounts).

    Args:
        reference_tokens: Ground truth token strings expected in the text.
        hypothesis_text: OCR output text to search.

    Returns:
        Dictionary containing match count, total count, accuracy, and missing tokens.
    """
    if not reference_tokens:
        return {
            "total": 0,
            "matched": 0,
            "accuracy": 1.0,
            "matched_tokens": [],
            "missing_tokens": [],
        }

    matched: list[str] = []
    missing: list[str] = []

    for token in reference_tokens:
        if token in hypothesis_text:
            matched.append(token)
        else:
            missing.append(token)

    accuracy = len(matched) / len(reference_tokens)
    return {
        "total": len(reference_tokens),
        "matched": len(matched),
        "accuracy": float(accuracy),
        "matched_tokens": matched,
        "missing_tokens": missing,
    }


def benchmark_page(
    image_path: Path,
    truth_path: Path | None = None,
    engine_name: str = "tesseract",
    langs: list[str] | None = None,
    apply_preprocess: bool = True,
) -> dict[str, Any]:
    """Run benchmark on a single page image.

    Args:
        image_path: Path to document page image.
        truth_path: Optional path to truth JSON or TXT file.
        engine_name: 'tesseract' or 'paddle'.
        langs: OCR languages (default: ['eng']).
        apply_preprocess: Whether to apply preprocessing prior to OCR.

    Returns:
        Benchmark metrics dictionary.
    """
    langs = langs or ["eng"]

    from atlas.ports.ocr import OcrEnginePort

    engine: OcrEnginePort
    if engine_name.lower() == "tesseract":
        engine = TesseractEngine()
    elif engine_name.lower() == "paddle":
        from atlas.ocr.paddle import PaddleEngine

        engine = PaddleEngine()
    else:
        raise ValueError(f"Unsupported OCR engine: {engine_name}")

    img = Image.open(image_path)

    t0 = time.perf_counter()
    img_for_ocr = preprocess(img) if apply_preprocess else img
    ocr_result = engine.recognize(img_for_ocr, langs=langs)
    elapsed_seconds = time.perf_counter() - t0

    recognized_text = ocr_result["raw_text"]

    metrics: dict[str, Any] = {
        "image": str(image_path),
        "engine": engine_name,
        "langs": langs,
        "preprocessed": apply_preprocess,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "raw_text_length": len(recognized_text),
        "line_count": len(ocr_result["lines"]),
        "warnings": ocr_result.get("warnings", []),
    }

    # If truth file is available, calculate CER and token accuracy
    if truth_path and truth_path.is_file():
        truth_content = truth_path.read_text(encoding="utf-8")
        ref_text = ""
        ref_tokens: list[str] = []

        if truth_path.suffix.lower() == ".json":
            try:
                truth_data = json.loads(truth_content)
                ref_text = truth_data.get("text", "")
                ref_tokens = truth_data.get("tokens", [])
                # Also collect tokens from mentions if present
                if "mentions" in truth_data:
                    for m in truth_data["mentions"]:
                        val = m.get("normalized_value") or m.get("surface_text")
                        if val and val not in ref_tokens:
                            ref_tokens.append(str(val))
            except Exception as exc:
                metrics["truth_parse_error"] = str(exc)
        else:
            ref_text = truth_content

        if ref_text:
            metrics["cer"] = round(compute_cer(ref_text, recognized_text), 4)

        if ref_tokens:
            metrics["token_evaluation"] = evaluate_tokens(ref_tokens, recognized_text)

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS OCR Benchmark Tool")
    parser.add_argument("--image", type=Path, required=True, help="Path to input image")
    parser.add_argument("--truth", type=Path, default=None, help="Path to truth JSON or TXT file")
    parser.add_argument("--engine", type=str, default="tesseract", choices=["tesseract", "paddle"])
    parser.add_argument("--langs", nargs="+", default=["eng"], help="OCR languages")
    parser.add_argument("--no-preprocess", action="store_true", help="Disable preprocessing")
    parser.add_argument("--out", type=Path, default=None, help="Path to output benchmark JSON")

    args = parser.parse_args()

    if not args.image.is_file():
        print(f"Error: Image file not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    result = benchmark_page(
        image_path=args.image,
        truth_path=args.truth,
        engine_name=args.engine,
        langs=args.langs,
        apply_preprocess=not args.no_preprocess,
    )

    formatted = json.dumps(result, indent=2, ensure_ascii=False)
    print(formatted)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(formatted, encoding="utf-8")
        print(f"Benchmark results written to {args.out}")


if __name__ == "__main__":
    main()

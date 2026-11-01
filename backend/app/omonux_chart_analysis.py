import base64
import json
import os
import re

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/api/v1/trading", tags=["Omonux Trading"])
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

@router.post("/chart-scan")
async def scan_chart(chart: UploadFile = File(...)):
    if chart.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Upload a JPEG, PNG or WebP chart image.")
    image = await chart.read(MAX_IMAGE_BYTES + 1)
    if not image:
        raise HTTPException(400, "Chart image is empty.")
    if len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Chart image must be 8 MB or smaller.")

    base = os.getenv("AI_BASE_URL", "").rstrip("/")
    key = os.getenv("AI_API_KEY", "")
    model = os.getenv("AI_MODEL", "")
    if not (base and key and model):
        raise HTTPException(503, "AI chart analysis is unavailable. Configure the AI provider in the private hosting environment.")

    prompt = (
        "Analyze the supplied cryptocurrency chart image. Return one JSON object only with keys: "
        "trend (bullish, bearish, sideways, or unclear), signal (BUY, SELL, HOLD, or UNCLEAR), "
        "confidence (integer 0-100), possibleEntry (number or null), stopLoss (number or null), "
        "takeProfit (number or null), riskReward (number or null), visibleElements (array of strings), "
        "reason (short string), limitations (array of strings). Do not invent unreadable prices or "
        "indicators. Use null when a value cannot be read. Never promise profit or present this as "
        "personalized financial advice."
    )
    data_url = "data:" + chart.content_type + ";base64," + base64.b64encode(image).decode("ascii")
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                base + "/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "max_tokens": 700,
                    "messages": [
                        {"role": "system", "content": "You are a cautious chart-image analysis assistant. Return valid JSON only."},
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ]},
                    ],
                },
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
        if isinstance(raw, list):
            raw = "".join(part.get("text", "") for part in raw if isinstance(part, dict))
        match = re.search(r"\{.*\}", str(raw), re.DOTALL)
        if not match:
            raise ValueError("The AI provider did not return structured chart analysis.")
        analysis = json.loads(match.group(0))
        if analysis.get("signal") not in {"BUY", "SELL", "HOLD", "UNCLEAR"}:
            analysis["signal"] = "UNCLEAR"
        confidence = analysis.get("confidence", 0)
        analysis["confidence"] = max(0, min(100, int(confidence))) if isinstance(confidence, (int, float)) else 0
        return {
            "provider": "configured AI provider",
            "analysis": analysis,
            "disclaimer": "Image-based educational analysis only. Chart images can be incomplete or misleading; verify all values independently. This is not financial advice and does not place orders.",
        }
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"AI provider returned HTTP {exc.response.status_code}. Check the configured model and provider access.")
    except (httpx.RequestError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(502, "Chart analysis failed or the AI provider returned an invalid response.")

import base64, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .omonux_integrations import secret_or_env

router = APIRouter(prefix="/api/v1/images", tags=["Image AI"])
PROVIDER = os.getenv("IMAGE_PROVIDER", "openai").lower()

def image_config():
    key = secret_or_env("image_api_key", "IMAGE_API_KEY")
    model = secret_or_env("image_model", "IMAGE_MODEL", "gpt-image-1")
    base = secret_or_env("image_base_url", "IMAGE_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    return key, model, base
DB = Path(os.getenv("DATABASE_PATH", "./agentforge.db"))
STORE = Path(os.getenv("IMAGE_STORAGE_DIR", "./storage/generated_images")).resolve()
MAX_BYTES = int(os.getenv("IMAGE_MAX_UPLOAD_BYTES", "12000000"))

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS image_assets(
      id TEXT PRIMARY KEY, prompt TEXT NOT NULL, model TEXT NOT NULL,
      size TEXT NOT NULL, quality TEXT NOT NULL, filename TEXT NOT NULL,
      created TEXT NOT NULL, revised_prompt TEXT)""")
    c.commit()
    return c

class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    size: str = Field(default="1024x1024", pattern="^(1024x1024|1536x1024|1024x1536)$")
    quality: str = Field(default="medium", pattern="^(low|medium|high)$")
    count: int = Field(default=1, ge=1, le=4)

@router.get("/status")
def image_status():
    key, model, base = image_config()
    return {"configured": bool(key) and PROVIDER == "openai", "provider": PROVIDER,
            "model": model, "key_present": bool(key), "max_batch": 4}

@router.get("/assets")
def image_assets():
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT id,prompt,model,size,quality,created,revised_prompt FROM image_assets ORDER BY created DESC LIMIT 100")]

@router.post("/generations")
async def generate_images(req: GenerateRequest):
    if PROVIDER != "openai":
        raise HTTPException(503, "This build currently supports IMAGE_PROVIDER=openai.")
    key, model, base = image_config()
    if not key:
        raise HTTPException(503, "Image generation is not configured. Open Connect API and add an image provider key.")
    STORE.mkdir(parents=True, exist_ok=True)
    results = []
    payload = {"model": model, "prompt": req.prompt, "size": req.size,
               "quality": req.quality, "n": req.count}
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(base + "/images/generations",
                headers={"Authorization": "Bearer " + key},
                json=payload)
        if response.status_code >= 400:
            # Never return provider response bodies: they can contain sensitive diagnostics.
            raise HTTPException(502, f"Image provider rejected the request (HTTP {response.status_code}). Check model access and API billing.")
        data = response.json().get("data", [])
        if len(data) != req.count:
            raise HTTPException(502, "Image provider returned an unexpected number of images.")
        with connect() as c:
            for item in data:
                encoded = item.get("b64_json")
                if not encoded:
                    raise HTTPException(502, "Image provider did not return image data.")
                raw = base64.b64decode(encoded, validate=True)
                if len(raw) > 25_000_000:
                    raise HTTPException(502, "Generated image exceeded the storage safety limit.")
                ident = str(uuid.uuid4())
                filename = ident + ".png"
                (STORE / filename).write_bytes(raw)
                created = datetime.now(timezone.utc).isoformat()
                revised = item.get("revised_prompt")
                c.execute("INSERT INTO image_assets VALUES(?,?,?,?,?,?,?,?)",
                    (ident, req.prompt, model, req.size, req.quality, filename, created, revised))
                results.append({"id": ident, "prompt": req.prompt, "model": model,
                    "size": req.size, "quality": req.quality, "created": created,
                    "revised_prompt": revised})
            c.commit()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, "Image generation failed. Check provider availability and backend logs.")
    return {"created": len(results), "assets": results}

@router.get("/assets/{asset_id}/file")
def image_file(asset_id: str):
    from fastapi.responses import FileResponse
    with connect() as c:
        row = c.execute("SELECT filename FROM image_assets WHERE id=?", (asset_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Image not found.")
    path = (STORE / row["filename"]).resolve()
    if path.parent != STORE or not path.is_file():
        raise HTTPException(404, "Image file is unavailable.")
    return FileResponse(path, media_type="image/png", filename=row["filename"])

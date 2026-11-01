import os
from datetime import datetime, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .main import db, stamp

router = APIRouter(prefix="/api/v1/trading/integrations", tags=["OMONUX Integrations"])
ALLOWED_SECRET_NAMES = {"binance_api_key", "binance_api_secret", "bybit_api_key", "bybit_api_secret", "binance_live_api_key", "binance_live_api_secret", "bybit_live_api_key", "bybit_live_api_secret", "telegram_bot_token", "telegram_chat_id"}


def cipher():
    key = os.getenv("SECRET_ENCRYPTION_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Secret storage is not configured. Set SECRET_ENCRYPTION_KEY in the private server environment.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise HTTPException(503, "SECRET_ENCRYPTION_KEY must be a valid Fernet key.")


def ensure_table():
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS integration_secrets (name TEXT PRIMARY KEY, ciphertext BLOB NOT NULL, updated TEXT NOT NULL)")


def store_secret(name: str, value: str):
    encrypted = cipher().encrypt(value.encode("utf-8"))
    ensure_table()
    with db() as conn:
        conn.execute(
            "INSERT INTO integration_secrets(name,ciphertext,updated) VALUES(?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET ciphertext=excluded.ciphertext,updated=excluded.updated",
            (name, encrypted, stamp()),
        )


def read_secret(name: str):
    ensure_table()
    with db() as conn:
        row = conn.execute("SELECT ciphertext FROM integration_secrets WHERE name=?", (name,)).fetchone()
    if not row:
        return None
    try:
        return cipher().decrypt(bytes(row["ciphertext"])).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError):
        raise HTTPException(503, "A stored integration secret cannot be decrypted. Check SECRET_ENCRYPTION_KEY; do not overwrite it until the original key is restored.")


class SecretInput(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=4096)


class TelegramTestInput(BaseModel):
    message: str = Field(default="AgentForge Telegram connection test: your bot is connected.", min_length=1, max_length=1000)


@router.get("/status")
def integration_status():
    ensure_table()
    with db() as conn:
        present = {row["name"] for row in conn.execute("SELECT name FROM integration_secrets")}
    return {
        "encryption_configured": bool(os.getenv("SECRET_ENCRYPTION_KEY", "").strip()),
        "secrets": {name: name in present for name in sorted(ALLOWED_SECRET_NAMES)},
        "telegram_ready": {"telegram_bot_token", "telegram_chat_id"}.issubset(present),
        "exchange_credentials_saved": any(name in present for name in ("binance_api_key", "bybit_api_key")),
    }


@router.put("/secrets")
def set_integration_secret(item: SecretInput):
    if item.name not in ALLOWED_SECRET_NAMES:
        raise HTTPException(400, "Unsupported secret name.")
    if not item.value.strip():
        raise HTTPException(400, "Secret value cannot be blank.")
    store_secret(item.name, item.value.strip())
    return {"saved": True, "name": item.name, "value_returned": False}


@router.delete("/secrets/{name}")
def delete_integration_secret(name: str):
    if name not in ALLOWED_SECRET_NAMES:
        raise HTTPException(400, "Unsupported secret name.")
    ensure_table()
    with db() as conn:
        conn.execute("DELETE FROM integration_secrets WHERE name=?", (name,))
    return {"deleted": True, "name": name}


@router.post("/telegram/test")
async def test_telegram():
    token = read_secret("telegram_bot_token")
    chat_id = read_secret("telegram_chat_id")
    if not token or not chat_id:
        raise HTTPException(409, "Save the Telegram bot token and chat ID first.")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "AgentForge Telegram connection test: your bot is connected."},
            )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise HTTPException(502, "Telegram rejected the test message. Check the bot token, chat ID and bot permissions.")
        return {"sent": True, "message": "Telegram test message sent."}
    except httpx.HTTPStatusError:
        raise HTTPException(502, "Telegram returned an error. Check the bot token, chat ID and bot permissions.")
    except httpx.RequestError:
        raise HTTPException(502, "Could not reach Telegram. Check the server network and try again.")

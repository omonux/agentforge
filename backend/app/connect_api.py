"""Central credential vault and connection diagnostics for AgentForge.

Credentials are encrypted at rest using the existing SECRET_ENCRYPTION_KEY.
Only presence/status metadata is returned to the browser; plaintext values never
leave this module after a save operation.
"""
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .omonux_integrations import ALLOWED_SECRET_NAMES, read_secret, store_secret, secret_or_env
from .main import db

router = APIRouter(prefix="/api/v1/connect-api", tags=["Connect API"])

SERVICES = [
    {"id":"ai","name":"AI Agent Provider","group":"Core AI","description":"Powers the five specialist agents, research, writing and task execution.","testable":True,"fields":[
        {"name":"ai_api_key","label":"AI API key","kind":"secret","required":True,"help":"OpenAI or an OpenAI-compatible provider key."},
        {"name":"ai_base_url","label":"API base URL","kind":"text","required":True,"help":"Example: https://api.openai.com/v1"},
        {"name":"ai_model","label":"Chat model","kind":"text","required":True,"help":"The exact model enabled for your API account."}]},
    {"id":"images","name":"Image AI Studio","group":"Media generation","description":"Creates and stores original images through the OpenAI Images API.","testable":True,"fields":[
        {"name":"image_api_key","label":"Image API key","kind":"secret","required":True,"help":"Can be the same provider key as your AI Agent key; save it here too."},
        {"name":"image_base_url","label":"Image API base URL","kind":"text","required":True,"help":"Example: https://api.openai.com/v1"},
        {"name":"image_model","label":"Image model","kind":"text","required":True,"help":"Example: gpt-image-1"}]},
    {"id":"video","name":"AI Video Generation","group":"Media generation","description":"Renders original video from approved scripts. A compatible Replicate model is required.","testable":True,"fields":[
        {"name":"replicate_api_token","label":"Replicate API token","kind":"secret","required":True,"help":"Create a token in your Replicate account."},
        {"name":"replicate_model","label":"Replicate model slug","kind":"text","required":True,"help":"Format owner/model. The model must accept a prompt and return a video."}]},
    {"id":"youtube","name":"YouTube & Google OAuth","group":"Publishing and analytics","description":"Connects your channel for trend discovery, approval-gated uploads and permitted channel analytics.","testable":True,"fields":[
        {"name":"youtube_client_id","label":"Google OAuth client ID","kind":"secret","required":True,"help":"Create an OAuth Web application in Google Cloud Console. Grant YouTube Data API and YouTube Analytics API access."},
        {"name":"youtube_client_secret","label":"Google OAuth client secret","kind":"secret","required":True,"help":"Keep this private; never paste it into chat. Reconnect the channel after granting the added Analytics scopes."},
        {"name":"youtube_redirect_uri","label":"OAuth redirect URI","kind":"text","required":True,"help":"Must exactly match your Google Cloud OAuth redirect URI. Include the deployed host URL."},
        {"name":"youtube_region","label":"Trend region code","kind":"text","required":False,"help":"Example: NG"}]},
    {"id":"telegram","name":"Telegram Notifications","group":"Publishing and alerts","description":"Sends approval, render, publishing and supported channel-metric notifications to your Telegram chat.","testable":True,"fields":[
        {"name":"telegram_bot_token","label":"Telegram bot token","kind":"secret","required":True,"help":"Create a bot with BotFather."},
        {"name":"telegram_chat_id","label":"Telegram chat ID","kind":"text","required":True,"help":"Start your bot and obtain your private chat ID."}]},
    {"id":"voice","name":"AI Voice Generation","group":"Media generation","description":"Optional voice narration for video drafts using ElevenLabs.","testable":True,"fields":[
        {"name":"elevenlabs_api_key","label":"ElevenLabs API key","kind":"secret","required":True,"help":"Your ElevenLabs API key."},
        {"name":"elevenlabs_voice_id","label":"Voice ID","kind":"text","required":True,"help":"The voice you have permission to use."},
        {"name":"elevenlabs_model","label":"Voice model","kind":"text","required":False,"help":"Default: eleven_multilingual_v2"}]},
    {"id":"payments","name":"Payments","group":"Business services","description":"Paystack and OPay hosted checkout. Checkout remains disabled until BILLING_ENABLED is deliberately enabled in server settings after sandbox verification.","testable":True,"fields":[
        {"name":"paystack_secret_key","label":"Paystack secret key","kind":"secret","required":False,"help":"Use a test key for sandbox validation; never enable live billing until reviewed."},
        {"name":"paystack_public_key","label":"Paystack public key","kind":"secret","required":False,"help":"Public checkout identifier; optional for the current hosted flow."},\n        {"name":"paystack_pro_monthly_plan_code","label":"Paystack Pro plan code","kind":"text","required":False,"help":"Optional recurring plan code."},\n        {"name":"paystack_business_monthly_plan_code","label":"Paystack Business plan code","kind":"text","required":False,"help":"Optional recurring plan code."},
        {"name":"opay_public_key","label":"OPay public key","kind":"secret","required":False,"help":"Merchant credential from your approved OPay account."},
        {"name":"opay_secret_key","label":"OPay secret key","kind":"secret","required":False,"help":"Keep private. OPay signing must be validated against your merchant docs."},
        {"name":"opay_merchant_id","label":"OPay merchant ID","kind":"text","required":False,"help":"Merchant identifier supplied by OPay."},
        {"name":"opay_api_base_url","label":"OPay API base URL","kind":"text","required":False,"help":"Use the sandbox URL until merchant approval."},\n        {"name":"opay_country","label":"OPay country code","kind":"text","required":False,"help":"Default: NG."},\n        {"name":"opay_currency","label":"OPay currency","kind":"text","required":False,"help":"Default: NGN."}]},
    {"id":"trading","name":"Exchange Credentials (Restricted)","group":"Business services","description":"Credentials are stored encrypted. This does not turn on live trading; use testnet and keep live execution disabled.","testable":False,"fields":[
        {"name":"binance_api_key","label":"Binance testnet API key","kind":"secret","required":False,"help":"Use testnet credentials with withdrawals disabled."},
        {"name":"binance_api_secret","label":"Binance testnet API secret","kind":"secret","required":False,"help":"Never use a withdrawal-enabled key."},
        {"name":"bybit_api_key","label":"Bybit testnet API key","kind":"secret","required":False,"help":"Use testnet credentials only."},
        {"name":"bybit_api_secret","label":"Bybit testnet API secret","kind":"secret","required":False,"help":"Never use a withdrawal-enabled key."}]},
]

ENV_FALLBACKS = {
    "ai_api_key":"AI_API_KEY","ai_base_url":"AI_BASE_URL","ai_model":"AI_MODEL",
    "image_api_key":"IMAGE_API_KEY","image_base_url":"IMAGE_BASE_URL","image_model":"IMAGE_MODEL",
    "replicate_api_token":"VIDEO_API_KEY","replicate_model":"VIDEO_MODEL",
    "youtube_client_id":"YOUTUBE_CLIENT_ID","youtube_client_secret":"YOUTUBE_CLIENT_SECRET",
    "youtube_redirect_uri":"YOUTUBE_REDIRECT_URI","youtube_region":"YOUTUBE_REGION",
    "telegram_bot_token":"","telegram_chat_id":"",
    "elevenlabs_api_key":"","elevenlabs_voice_id":"","elevenlabs_model":"",
    "paystack_secret_key":"PAYSTACK_SECRET_KEY","paystack_public_key":"",\n    "paystack_pro_monthly_plan_code":"PAYSTACK_PRO_MONTHLY_PLAN_CODE","paystack_business_monthly_plan_code":"PAYSTACK_BUSINESS_MONTHLY_PLAN_CODE",
    "opay_public_key":"OPAY_PUBLIC_KEY","opay_secret_key":"OPAY_SECRET_KEY",
    "opay_merchant_id":"OPAY_MERCHANT_ID","opay_api_base_url":"OPAY_API_BASE_URL",\n    "opay_country":"OPAY_COUNTRY","opay_currency":"OPAY_CURRENCY",
    "binance_api_key":"","binance_api_secret":"","bybit_api_key":"","bybit_api_secret":"",
}

class SecretInput(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=4096)

def _present(name: str) -> bool:
    env = ENV_FALLBACKS.get(name, "")
    return bool(secret_or_env(name, env) if env else read_secret(name))

def _ensure_checks():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS integration_checks(
            service TEXT PRIMARY KEY, status TEXT NOT NULL, message TEXT NOT NULL,
            checked_at TEXT NOT NULL)""")

def _save_check(service: str, status: str, message: str):
    _ensure_checks()
    with db() as conn:
        conn.execute("""INSERT INTO integration_checks(service,status,message,checked_at)
            VALUES(?,?,?,?) ON CONFLICT(service) DO UPDATE SET
            status=excluded.status,message=excluded.message,checked_at=excluded.checked_at""",
            (service,status,message,datetime.now(timezone.utc).isoformat()))

@router.get("")
def list_connections():
    _ensure_checks()
    with db() as conn:
        checks = {r["service"]: {"status":r["status"],"message":r["message"],"checked_at":r["checked_at"]}
                  for r in conn.execute("SELECT service,status,message,checked_at FROM integration_checks").fetchall()}
    groups = []
    for service in SERVICES:
        fields = []
        for field in service["fields"]:
            fields.append({**field,"configured":_present(field["name"])})
        required = [f for f in fields if f["required"]]
        configured = all(f["configured"] for f in required) if required else any(f["configured"] for f in fields)
        groups.append({**service,"configured":configured,"fields":fields,
                       "check":checks.get(service["id"])})
    return {"encryption_ready":bool(os.getenv("SECRET_ENCRYPTION_KEY","").strip()),
            "services":groups,
            "security":{"secrets_encrypted_at_rest":True,"secret_values_returned":False,
                        "live_trading_enabled":False}}

@router.put("/secrets")
def save_connection_secret(item: SecretInput):
    if item.name not in ALLOWED_SECRET_NAMES:
        raise HTTPException(400,"This credential is not in the supported Connect API registry.")
    if not item.value.strip():
        raise HTTPException(400,"Credential cannot be blank.")
    store_secret(item.name,item.value.strip())
    return {"saved":True,"name":item.name,"value_returned":False}

@router.delete("/secrets/{name}")
def remove_connection_secret(name: str):
    if name not in ALLOWED_SECRET_NAMES:
        raise HTTPException(400,"This credential is not in the supported Connect API registry.")
    from .omonux_integrations import ensure_table
    ensure_table()
    with db() as conn:
        conn.execute("DELETE FROM integration_secrets WHERE name=?",(name,))
    return {"deleted":True,"name":name}

@router.post("/test/{service_id}")
async def test_connection(service_id: str):
    service = next((x for x in SERVICES if x["id"]==service_id),None)
    if not service:
        raise HTTPException(404,"Unknown integration.")
    if not service["testable"]:
        _save_check(service_id,"manual","Credentials are stored encrypted. This integration is restricted to testnet/manual verification.")
        return {"service":service_id,"status":"manual","message":"Credentials saved. This service is not activated by a credential test."}
    try:
        if service_id=="ai":
            base=secret_or_env("ai_base_url","AI_BASE_URL").rstrip("/")
            key=secret_or_env("ai_api_key","AI_API_KEY")
            model=secret_or_env("ai_model","AI_MODEL")
            if not (base and key and model): raise HTTPException(409,"Add the AI API key, base URL and model first.")
            async with httpx.AsyncClient(timeout=45) as client:
                response=await client.post(base+"/chat/completions",headers={"Authorization":"Bearer "+key},
                    json={"model":model,"messages":[{"role":"user","content":"Reply with exactly: AgentForge connection successful."}],"temperature":0})
            if response.status_code>=400: raise HTTPException(502,f"AI provider rejected the test (HTTP {response.status_code}). Check model access and billing.")
            if not response.json().get("choices"): raise HTTPException(502,"AI provider returned an unexpected response.")
            message="AI chat request succeeded."
        elif service_id=="images":
            base=secret_or_env("image_base_url","IMAGE_BASE_URL","https://api.openai.com/v1").rstrip("/")
            key=secret_or_env("image_api_key","IMAGE_API_KEY")
            if not key: raise HTTPException(409,"Add the image API key first.")
            async with httpx.AsyncClient(timeout=30) as client:
                response=await client.get(base+"/models",headers={"Authorization":"Bearer "+key})
            if response.status_code>=400: raise HTTPException(502,f"Image provider rejected the credentials (HTTP {response.status_code}).")
            message="Image provider credentials accepted. This test does not generate or charge for an image."
        elif service_id=="video":
            token=secret_or_env("replicate_api_token","VIDEO_API_KEY")
            if not token: raise HTTPException(409,"Add the Replicate API token first.")
            async with httpx.AsyncClient(timeout=30) as client:
                response=await client.get("https://api.replicate.com/v1/account",headers={"Authorization":"Bearer "+token})
            if response.status_code>=400: raise HTTPException(502,"Replicate did not accept the token.")
            message="Replicate account authentication succeeded."
        elif service_id=="youtube":
            client_id=secret_or_env("youtube_client_id","YOUTUBE_CLIENT_ID")
            client_secret=secret_or_env("youtube_client_secret","YOUTUBE_CLIENT_SECRET")
            if not (client_id and client_secret): raise HTTPException(409,"Add the Google OAuth client ID and secret first.")
            message="Google OAuth credentials are present. Use Connect channel to complete the consent flow."
        elif service_id=="telegram":
            token=read_secret("telegram_bot_token"); chat_id=read_secret("telegram_chat_id")
            if not (token and chat_id): raise HTTPException(409,"Add the Telegram bot token and chat ID first.")
            async with httpx.AsyncClient(timeout=15) as client:
                response=await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id":chat_id,"text":"AgentForge connection test: Telegram notifications are connected."})
            if response.status_code>=400 or not response.json().get("ok"):
                raise HTTPException(502,"Telegram rejected the test. Check bot token, chat ID and bot permissions.")
            message="Telegram test message sent successfully."
        elif service_id=="voice":
            key=read_secret("elevenlabs_api_key")
            if not key: raise HTTPException(409,"Add the ElevenLabs API key first.")
            async with httpx.AsyncClient(timeout=20) as client:
                response=await client.get("https://api.elevenlabs.io/v1/user",headers={"xi-api-key":key})
            if response.status_code>=400: raise HTTPException(502,"ElevenLabs did not accept the API key.")
            message="ElevenLabs account authentication succeeded."
        elif service_id=="payments":
            paystack=read_secret("paystack_secret_key")
            if paystack:
                async with httpx.AsyncClient(timeout=20) as client:
                    response=await client.get("https://api.paystack.co/balance",headers={"Authorization":"Bearer "+paystack})
                if response.status_code>=400: raise HTTPException(502,"Paystack did not accept the secret key.")
                message="Paystack authentication succeeded. OPay still requires merchant-specific sandbox verification."
            else:
                if not all(read_secret(k) for k in ("opay_public_key","opay_secret_key","opay_merchant_id")):
                    raise HTTPException(409,"Add Paystack or the complete OPay merchant credentials first.")
                message="OPay credentials are saved. Complete the merchant-specific sandbox checkout test before enabling billing."
        else:
            raise HTTPException(400,"No test is available for this service.")
        _save_check(service_id,"configured" if service_id=="youtube" else ("manual" if service_id=="payments" and not read_secret("paystack_secret_key") else "connected"),message)
        return {"service":service_id,"status":"configured" if service_id=="youtube" else ("manual" if service_id=="payments" and not read_secret("paystack_secret_key") else "connected"),"message":message}
    except HTTPException as exc:
        _save_check(service_id,"error",str(exc.detail))
        raise
    except (httpx.RequestError,ValueError,KeyError):
        _save_check(service_id,"error","Connection test failed. Check provider settings and server network.")
        raise HTTPException(502,"Connection test failed. Check provider settings and server network.")

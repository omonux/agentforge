"""Central credential vault and connection diagnostics for AgentForge.

Credentials are encrypted at rest using the existing SECRET_ENCRYPTION_KEY.
Only presence/status metadata is returned to the browser; plaintext values never
leave this module after a save operation.
"""
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .omonux_integrations import ALLOWED_SECRET_NAMES, read_secret, store_secret, secret_or_env, cipher
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
        {"name":"replicate_model","label":"Replicate model slug","kind":"text","required":True,"help":"Format owner/model. The model must accept a prompt and return a video."},
        {"name":"replicate_input_json","label":"Video model input JSON","kind":"text","required":False,"help":"Optional model-specific inputs. Suggested vertical 30-second defaults: {\"aspect_ratio\":\"9:16\",\"duration\":30}. Adjust keys to match your chosen model."}]},
    {"id":"youtube","name":"YouTube & Google OAuth","group":"Publishing and analytics","description":"Connects your channel for trend discovery, approval-gated uploads and permitted channel analytics.","testable":True,"fields":[
        {"name":"youtube_client_id","label":"Google OAuth client ID","kind":"secret","required":True,"help":"Create an OAuth Web application in Google Cloud Console. Grant YouTube Data API and YouTube Analytics API access."},
        {"name":"youtube_client_secret","label":"Google OAuth client secret","kind":"secret","required":True,"help":"Keep this private; never paste it into chat. Reconnect the channel after granting the added Analytics scopes."},
        {"name":"youtube_redirect_uri","label":"OAuth redirect URI","kind":"text","required":True,"help":"Must exactly match your Google Cloud OAuth redirect URI. Include the deployed host URL."},
        {"name":"youtube_region","label":"Trend region code","kind":"text","required":False,"help":"Example: NG"}]},
    {"id":"telegram","name":"Telegram Notifications","group":"Publishing and alerts","description":"Sends private customer inquiry and workspace alerts to your Telegram chat. It does not collect or process payments.","testable":True,"fields":[
        {"name":"telegram_bot_token","label":"Telegram bot token","kind":"secret","required":True,"help":"Create a bot with BotFather."},
        {"name":"telegram_chat_id","label":"Telegram chat ID","kind":"text","required":True,"help":"Start your bot and obtain your private chat ID."}]},
    {"id":"voice","name":"AI Voice Generation","group":"Media generation","description":"Optional voice narration for video drafts using ElevenLabs.","testable":True,"fields":[
        {"name":"elevenlabs_api_key","label":"ElevenLabs API key","kind":"secret","required":True,"help":"Your ElevenLabs API key."},
        {"name":"elevenlabs_voice_id","label":"Voice ID","kind":"text","required":True,"help":"The voice you have permission to use."},
        {"name":"elevenlabs_model","label":"Voice model","kind":"text","required":False,"help":"Default: eleven_multilingual_v2"}]},
    {"id":"commerce_search","name":"Product Discovery Search","group":"Commerce Agent","description":"Searches the web for supplier and product leads. Results are research leads, not proof of stock, pricing or resale rights.","testable":True,"fields":[
        {"name":"tavily_api_key","label":"Tavily Search API key","kind":"secret","required":True,"help":"Used by the Commerce Agent to search for current product and supplier pages."}]},
    {"id":"commerce_cj","name":"CJ Dropshipping Supplier","group":"Commerce Agent","description":"Searches CJ's supplier catalog and checks reported warehouse inventory. Freight, destination eligibility, resale terms and payment must still be verified.","testable":True,"fields":[
        {"name":"cj_api_key","label":"CJ API key","kind":"secret","required":True,"help":"Create an API key in your CJ account under Personal Center → API. AgentForge exchanges it for server-stored access tokens."}]},
    {"id":"commerce_shopify","name":"Shopify Store","group":"Commerce Agent","description":"Connect a Shopify app for a store you own. Product drafts are created only when you click the action in Commerce Agent.","testable":True,"fields":[
        {"name":"shopify_client_id","label":"Shopify app client ID","kind":"secret","required":True,"help":"From your Shopify Dev Dashboard app settings."},
        {"name":"shopify_client_secret","label":"Shopify app client secret","kind":"secret","required":True,"help":"Encrypted by AgentForge. Never paste it into chat."},
        {"name":"shopify_redirect_uri","label":"Shopify OAuth redirect URL","kind":"text","required":True,"help":"Register this exact HTTPS URL in the app: https://agentforge-omonux.onrender.com/api/v1/commerce/shopify/oauth/callback"}]},
    {"id":"commerce_jumia","name":"Jumia Seller API","group":"Commerce Agent","description":"Store your account-issued Seller API details securely. Automated Jumia actions remain unavailable until the account API contract is verified.","testable":False,"fields":[
        {"name":"jumia_seller_api_key","label":"Jumia Seller API key","kind":"secret","required":False,"help":"Use only credentials issued by Jumia Seller Center."},
        {"name":"jumia_seller_api_base","label":"Jumia Seller API base URL","kind":"text","required":False,"help":"Enter the official URL given for your account. It is saved encrypted; requests are not sent yet."},
        {"name":"jumia_seller_id","label":"Jumia seller/account ID","kind":"text","required":False,"help":"Account identifier supplied by Seller Center."}]},
    {"id":"commerce_email","name":"Customer Reply Email","group":"Commerce Agent","description":"Send owner-reviewed replies to customer inquiries using your verified sending domain.","testable":True,"fields":[
        {"name":"resend_api_key","label":"Resend API key","kind":"secret","required":True,"help":"Create a Resend API key with email sending permission. Keep it private."},
        {"name":"commerce_sender_email","label":"Verified sender email","kind":"secret","required":True,"help":"Use an address on a domain verified in Resend."},
        {"name":"commerce_sender_name","label":"Sender name","kind":"text","required":True,"help":"Name customers will see, such as Omonux Store."}]},
    {"id":"payments","name":"Payments","group":"Business services","description":"Paystack and OPay hosted checkout. Checkout remains disabled until BILLING_ENABLED is deliberately enabled in server settings after sandbox verification.","testable":True,"fields":[
        {"name":"paystack_secret_key","label":"Paystack secret key","kind":"secret","required":False,"help":"Use a test key for sandbox validation; never enable live billing until reviewed."},
        {"name":"paystack_public_key","label":"Paystack public key","kind":"secret","required":False,"help":"Public checkout identifier; optional for the current hosted flow."},
        {"name":"paystack_pro_monthly_plan_code","label":"Paystack Pro plan code","kind":"text","required":False,"help":"Optional recurring plan code."},
        {"name":"paystack_business_monthly_plan_code","label":"Paystack Business plan code","kind":"text","required":False,"help":"Optional recurring plan code."},
        {"name":"opay_public_key","label":"OPay public key","kind":"secret","required":False,"help":"Merchant credential from your approved OPay account."},
        {"name":"opay_secret_key","label":"OPay secret key","kind":"secret","required":False,"help":"Keep private. OPay signing must be validated against your merchant docs."},
        {"name":"opay_merchant_id","label":"OPay merchant ID","kind":"text","required":False,"help":"Merchant identifier supplied by OPay."},
        {"name":"opay_api_base_url","label":"OPay API base URL","kind":"text","required":False,"help":"Use the sandbox URL until merchant approval."},
        {"name":"opay_country","label":"OPay country code","kind":"text","required":False,"help":"Default: NG."},
        {"name":"opay_currency","label":"OPay currency","kind":"text","required":False,"help":"Default: NGN."}]},
    {"id":"trading","name":"Crypto Exchange Connections","group":"Exchange APIs","description":"Connect Binance, Bybit and OKX. Credentials are encrypted. Production account checks are read-only and never place or manage orders.","testable":False,"fields":[
        {"name":"binance_api_key","label":"Binance testnet API key","kind":"secret","required":False,"help":"Testnet key only. No real funds."},
        {"name":"binance_api_secret","label":"Binance testnet API secret","kind":"secret","required":False,"help":"Testnet secret. Never enable withdrawals."},
        {"name":"binance_live_api_key","label":"Binance LIVE read-only API key","kind":"secret","required":False,"help":"Use account read permission only. Disable trading and withdrawals."},
        {"name":"binance_live_api_secret","label":"Binance LIVE read-only API secret","kind":"secret","required":False,"help":"Separate production read-only key; restrict by IP where possible."},
        {"name":"bybit_api_key","label":"Bybit testnet API key","kind":"secret","required":False,"help":"Testnet key only. No real funds."},
        {"name":"bybit_api_secret","label":"Bybit testnet API secret","kind":"secret","required":False,"help":"Testnet secret. Never enable withdrawals."},
        {"name":"bybit_live_api_key","label":"Bybit LIVE read-only API key","kind":"secret","required":False,"help":"Enable Read only only. Do not grant Trade or Withdraw."},
        {"name":"bybit_live_api_secret","label":"Bybit LIVE read-only API secret","kind":"secret","required":False,"help":"Separate production read-only secret; use IP restrictions."},
        {"name":"okx_live_api_key","label":"OKX LIVE read-only API key","kind":"secret","required":False,"help":"Enable Read permission only. Do not grant Trade or Withdraw."},
        {"name":"okx_live_api_secret","label":"OKX LIVE read-only API secret","kind":"secret","required":False,"help":"Separate production read-only secret; bind it to the service IP if supported."},
        {"name":"okx_live_api_passphrase","label":"OKX API passphrase","kind":"secret","required":False,"help":"The passphrase created with this OKX API key; store it only in this encrypted connection form."}]},
]

ENV_FALLBACKS = {
    "ai_api_key":"AI_API_KEY","ai_base_url":"AI_BASE_URL","ai_model":"AI_MODEL",
    "image_api_key":"IMAGE_API_KEY","image_base_url":"IMAGE_BASE_URL","image_model":"IMAGE_MODEL",
    "replicate_api_token":"VIDEO_API_KEY","replicate_model":"VIDEO_MODEL","replicate_input_json":"VIDEO_INPUT_JSON",
    "youtube_client_id":"YOUTUBE_CLIENT_ID","youtube_client_secret":"YOUTUBE_CLIENT_SECRET",
    "youtube_redirect_uri":"YOUTUBE_REDIRECT_URI","youtube_region":"YOUTUBE_REGION",
    "telegram_bot_token":"","telegram_chat_id":"",
    "elevenlabs_api_key":"","elevenlabs_voice_id":"","elevenlabs_model":"",
    "tavily_api_key":"","shopify_client_id":"","shopify_redirect_uri":"",
    "cj_api_key":"",
    "jumia_seller_api_key":"","jumia_seller_api_base":"","jumia_seller_id":"",
    "paystack_secret_key":"PAYSTACK_SECRET_KEY","paystack_public_key":"",
    "paystack_pro_monthly_plan_code":"PAYSTACK_PRO_MONTHLY_PLAN_CODE","paystack_business_monthly_plan_code":"PAYSTACK_BUSINESS_MONTHLY_PLAN_CODE",
    "opay_public_key":"OPAY_PUBLIC_KEY","opay_secret_key":"OPAY_SECRET_KEY",
    "opay_merchant_id":"OPAY_MERCHANT_ID","opay_api_base_url":"OPAY_API_BASE_URL",
    "opay_country":"OPAY_COUNTRY","opay_currency":"OPAY_CURRENCY",
    "binance_api_key":"","binance_api_secret":"","bybit_api_key":"","bybit_api_secret":"",
    "binance_live_api_key":"","binance_live_api_secret":"","bybit_live_api_key":"","bybit_live_api_secret":"",
    "okx_live_api_key":"","okx_live_api_secret":"","okx_live_api_passphrase":"",
}

class SecretInput(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=4096)

def _encryption_ready() -> bool:
    try:
        cipher()
        return True
    except HTTPException:
        return False

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
    return {"encryption_ready":_encryption_ready(),
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
    email_domain_verified=None
    try:
        if service_id=="ai":
            base=secret_or_env("ai_base_url","AI_BASE_URL").rstrip("/")
            key=secret_or_env("ai_api_key","AI_API_KEY")
            model=secret_or_env("ai_model","AI_MODEL")
            if not (base and key and model): raise HTTPException(409,"Add the AI API key, base URL and model first.")
            async with httpx.AsyncClient(timeout=45) as client:
                response=await client.post(base+"/chat/completions",headers={"Authorization":"Bearer "+key},
                    json={"model":model,"messages":[{"role":"user","content":"Reply with exactly: AgentForge connection successful."}],"temperature":0})
            if response.status_code>=400:
                category = None
                try:
                    body = response.json()
                    err = body.get("error", {}) if isinstance(body, dict) else {}
                    if isinstance(err, dict):
                        category = err.get("code") or err.get("type")
                except (ValueError, TypeError):
                    pass
                if response.status_code == 429:
                    if category == "insufficient_quota":
                        detail = "OpenAI returned insufficient_quota (429). Check whether this API key belongs to the funded organization and project, and whether its quota is active."
                    elif category == "rate_limit_exceeded":
                        detail = "OpenAI returned rate_limit_exceeded (429). Reduce request frequency and check this model's project rate limits."
                    else:
                        detail = "OpenAI returned HTTP 429. Check the API key's project, model limits and billing; available organization credits alone do not confirm this key has access."
                elif response.status_code == 401:
                    detail = "AI provider rejected this API key (401). Check that the saved Connect API key is current."
                elif response.status_code == 403:
                    detail = "AI provider denied access (403). Check API project permissions and model access."
                elif response.status_code == 404:
                    detail = "AI provider model or endpoint not found (404). Verify the model and base URL."
                else:
                    detail = f"AI provider rejected the connection test (HTTP {response.status_code})."
                raise HTTPException(502, detail)
            if not response.json().get("choices"): raise HTTPException(502,"AI provider returned an unexpected response.")
            message="AI chat request succeeded."
        elif service_id=="images":
            base=secret_or_env("image_base_url","IMAGE_BASE_URL","https://api.openai.com/v1").rstrip("/")
            key=secret_or_env("image_api_key","IMAGE_API_KEY")
            if not key and base=="https://api.openai.com/v1":
                key=secret_or_env("ai_api_key","AI_API_KEY")
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
        elif service_id=="commerce_search":
            key=read_secret("tavily_api_key")
            if not key: raise HTTPException(409,"Add the Tavily Search API key first.")
            async with httpx.AsyncClient(timeout=20) as client:
                response=await client.post("https://api.tavily.com/search",headers={"Authorization":"Bearer "+key},
                    json={"query":"wholesale suppliers Nigeria test","search_depth":"basic","max_results":1,"include_answer":False})
            if response.status_code>=400: raise HTTPException(502,"Tavily rejected the search key or request.")
            message="Tavily search request succeeded. This test uses one search request."
        elif service_id=="commerce_cj":
            if not read_secret("cj_api_key"): raise HTTPException(409,"Add the CJ API key first.")
            from .commerce_agent import test_cj_connection
            result=await test_cj_connection()
            message=result["message"]
        elif service_id=="commerce_shopify":
            if not (read_secret("shopify_client_id") and read_secret("shopify_client_secret") and read_secret("shopify_redirect_uri")):
                raise HTTPException(409,"Add the Shopify app client ID, secret and redirect URL first.")
            from .commerce_agent import test_shopify
            result=await test_shopify()
            message="Shopify store connected: "+result["shop"]
        elif service_id=="commerce_jumia":
            message="Jumia details are saved encrypted. No API request was made because the account-specific API contract has not been verified."
        elif service_id=="commerce_email":
            key=read_secret("resend_api_key")
            sender=read_secret("commerce_sender_email")
            if not (key and sender): raise HTTPException(409,"Add the Resend key and verified sender email first.")
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",sender): raise HTTPException(409,"The sender email is not valid.")
            async with httpx.AsyncClient(timeout=20) as client:
                response=await client.get("https://api.resend.com/domains",headers={"Authorization":"Bearer "+key})
            if response.status_code>=400: raise HTTPException(502,"Resend rejected the API key.")
            domains=response.json().get("data",[])
            domain=sender.rsplit("@",1)[-1].lower()
            email_domain_verified=any(str(item.get("name","")).lower()==domain and item.get("status")=="verified" for item in domains)
            message="Resend API key accepted; sender domain verified." if email_domain_verified else "Resend API key accepted, but the sender domain is not yet verified. Verify it in Resend before sending replies."
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
        status="configured" if service_id=="youtube" else ("manual" if service_id=="commerce_jumia" or (service_id=="payments" and not read_secret("paystack_secret_key")) else "connected")
        if service_id=="commerce_email" and not email_domain_verified: status="needs_verification"
        _save_check(service_id,status,message)
        return {"service":service_id,"status":status,"message":message}
    except HTTPException as exc:
        _save_check(service_id,"error",str(exc.detail))
        raise
    except (httpx.RequestError,ValueError,KeyError):
        _save_check(service_id,"error","Connection test failed. Check provider settings and server network.")
        raise HTTPException(502,"Connection test failed. Check provider settings and server network.")

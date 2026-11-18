"""Private, approval-gated multi-channel commerce workspace."""
import json
import os
import hashlib
import hmac
import re
import secrets
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from urllib.parse import urlparse

import httpx
import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from starlette.responses import RedirectResponse

from .omonux_integrations import read_secret, secret_or_env, store_secret
from .main import db as sqlite_db, stamp

router = APIRouter(prefix="/api/v1/commerce", tags=["Commerce Agent"])
SHOPIFY_API_VERSION = "2026-10"


class _PostgresAdapter:
    def __init__(self, connection): self.connection=connection
    def execute(self, sql, params=()):
        sql=sql.replace("INSERT OR IGNORE INTO commerce_settings(id,updated) VALUES(1,?)",
                        "INSERT INTO commerce_settings(id,updated) VALUES(1,?) ON CONFLICT(id) DO NOTHING")
        sql=sql.replace("BEGIN IMMEDIATE", "BEGIN")
        return self.connection.execute(sql.replace("?", "%s"), params)


@contextmanager
def commerce_db():
    """Use Neon when configured; retain SQLite for local development."""
    dsn=os.getenv("DATABASE_URL","").strip()
    if dsn:
        if not dsn.startswith(("postgresql://","postgres://")) or "sslmode=disable" in dsn.lower():
            raise RuntimeError("Commerce storage requires a TLS-protected PostgreSQL DATABASE_URL.")
        with psycopg.connect(dsn,connect_timeout=8,row_factory=dict_row) as conn:
            yield _PostgresAdapter(conn)
    else:
        with sqlite_db() as conn: yield conn


def ensure_tables():
    with commerce_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS commerce_products (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'General', model TEXT NOT NULL DEFAULT 'dropshipping',
            supplier_name TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
            cost REAL, shipping REAL NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'NGN',
            marketplace_fee_pct REAL NOT NULL DEFAULT 0, payment_fee_pct REAL NOT NULL DEFAULT 0,
            target_margin_pct REAL NOT NULL DEFAULT 25, sale_price REAL, estimated_profit REAL,
            stock_status TEXT NOT NULL DEFAULT 'unknown', source_verified INTEGER NOT NULL DEFAULT 0,
            resale_authorized INTEGER NOT NULL DEFAULT 0, copy_json TEXT,
            status TEXT NOT NULL DEFAULT 'candidate', channel_ids_json TEXT NOT NULL DEFAULT '{}',
            created TEXT NOT NULL, updated TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS commerce_settings (
            id INTEGER PRIMARY KEY CHECK(id=1), currency TEXT NOT NULL DEFAULT 'NGN',
            target_margin_pct REAL NOT NULL DEFAULT 25, min_profit REAL NOT NULL DEFAULT 1000,
            daily_scan_enabled INTEGER NOT NULL DEFAULT 1, last_scan TEXT,
            auto_publish INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL)""")
        conn.execute("INSERT OR IGNORE INTO commerce_settings(id,updated) VALUES(1,?)", (stamp(),))
        conn.execute("""CREATE TABLE IF NOT EXISTS commerce_events (
            id TEXT PRIMARY KEY, event_type TEXT NOT NULL, product_id TEXT, message TEXT NOT NULL,
            created TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS commerce_shopify_oauth_states (
            state_hash TEXT PRIMARY KEY, shop TEXT NOT NULL, expires_at INTEGER NOT NULL, created TEXT NOT NULL)""")


def event(event_type: str, message: str, product_id: str | None = None):
    with commerce_db() as conn:
        conn.execute("INSERT INTO commerce_events(id,event_type,product_id,message,created) VALUES(?,?,?,?,?)",
                     (str(uuid.uuid4()), event_type, product_id, message[:500], stamp()))


def _row_product(row):
    item = dict(row)
    item["source_verified"] = bool(item["source_verified"])
    item["resale_authorized"] = bool(item["resale_authorized"])
    item["channel_ids"] = json.loads(item.pop("channel_ids_json") or "{}")
    raw_copy = item.pop("copy_json", None)
    item["listing_copy"] = json.loads(raw_copy) if raw_copy else None
    return item


def _shopify_config():
    shop = secret_or_env("shopify_shop_domain", "").strip().lower()
    token = read_secret("shopify_admin_token")
    if shop and not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", shop):
        raise HTTPException(400, "Enter the canonical store-name.myshopify.com domain.")
    return shop, token


class ProductInput(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=8000)
    category: str = Field(default="General", min_length=1, max_length=100)
    model: str = Field(default="dropshipping", pattern="^(dropshipping|affiliate|freelance|resale)$")
    supplier_name: str = Field(default="", max_length=160)
    source_url: str = Field(default="", max_length=1000)
    cost: Decimal | None = Field(default=None, ge=0, le=Decimal("1000000000"))
    shipping: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("1000000000"))
    currency: str = Field(default="NGN", pattern="^(NGN|USD|GBP|EUR)$")
    marketplace_fee_pct: Decimal = Field(default=Decimal("0"), ge=0, le=50)
    payment_fee_pct: Decimal = Field(default=Decimal("0"), ge=0, le=20)
    target_margin_pct: Decimal = Field(default=Decimal("25"), ge=1, le=80)
    stock_status: str = Field(default="unknown", pattern="^(unknown|available|unavailable|affiliate)$")
    source_verified: bool = False
    resale_authorized: bool = False

    @field_validator("source_url")
    @classmethod
    def valid_source_url(cls, value):
        value = value.strip()
        if value and (urlparse(value).scheme not in ("http", "https") or not urlparse(value).hostname):
            raise ValueError("Supplier/source URL must be a valid http or https address.")
        return value


class SettingsInput(BaseModel):
    currency: str = Field(default="NGN", pattern="^(NGN|USD|GBP|EUR)$")
    target_margin_pct: Decimal = Field(default=Decimal("25"), ge=1, le=80)
    min_profit: Decimal = Field(default=Decimal("1000"), ge=0, le=Decimal("1000000000"))
    daily_scan_enabled: bool = True
    auto_publish: bool = False


class DiscoveryInput(BaseModel):
    query: str = Field(default="", max_length=180)


class ShopifyConnectInput(BaseModel):
    shop: str = Field(min_length=1, max_length=100)

    @field_validator("shop")
    @classmethod
    def valid_shop(cls, value):
        value=value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com",value):
            raise ValueError("Enter your store-name.myshopify.com domain.")
        return value


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_CEILING))


def _price(cost, shipping, marketplace_fee_pct, payment_fee_pct, target_margin_pct, min_profit=0):
    if cost is None:
        return None, None
    c, s = Decimal(str(cost)), Decimal(str(shipping))
    fees = Decimal(str(marketplace_fee_pct)) + Decimal(str(payment_fee_pct))
    margin = Decimal(str(target_margin_pct))
    if fees + margin >= Decimal("90"):
        raise HTTPException(422, "Fees plus target profit margin must stay below 90% of the sale price.")
    margin_price=(c+s)/(Decimal("1")-(fees+margin)/Decimal("100"))
    floor_price=(c+s+Decimal(str(min_profit)))/(Decimal("1")-fees/Decimal("100"))
    sale=max(margin_price,floor_price).quantize(Decimal("0.01"),rounding=ROUND_CEILING)
    profit = sale * (Decimal("1") - fees / Decimal("100")) - c - s
    return float(sale), float(profit.quantize(Decimal("0.01")))


@router.get("/overview")
def overview():
    ensure_tables()
    shop, token = _shopify_config()
    tavily = bool(read_secret("tavily_api_key"))
    with commerce_db() as conn:
        settings = dict(conn.execute("SELECT * FROM commerce_settings WHERE id=1").fetchone())
        products = conn.execute("SELECT * FROM commerce_products ORDER BY updated DESC LIMIT 100").fetchall()
        events = conn.execute("SELECT * FROM commerce_events ORDER BY created DESC LIMIT 30").fetchall()
        conn.execute("CREATE TABLE IF NOT EXISTS integration_checks(service TEXT PRIMARY KEY,status TEXT NOT NULL,message TEXT NOT NULL,checked_at TEXT NOT NULL)")
        checks = {row["service"]: row["status"] for row in conn.execute("SELECT service,status FROM integration_checks WHERE service IN ('commerce_shopify','commerce_jumia')").fetchall()}
    all_products = [_row_product(row) for row in products]
    return {
        "settings": {**settings, "daily_scan_enabled": bool(settings["daily_scan_enabled"]), "auto_publish": bool(settings["auto_publish"])},
        "products": all_products,
        "events": [dict(row) for row in events],
        "storage_mode": "neon_postgres" if os.getenv("DATABASE_URL","").strip() else "local_sqlite",
        "channels": [
            {"id": "shopify", "name": "Shopify", "status": "configured" if checks.get("commerce_shopify")=="connected" else ("credentials_saved" if shop and token else "not_connected"), "shop": shop or None, "supported": True},
            {"id": "jumia", "name": "Jumia", "status": "manual_setup", "supported": False, "detail": "Credentials are saved for account-specific setup; automated listing is not yet verified." if read_secret("jumia_seller_api_key") else "Seller API setup is account-specific; no credentials are connected yet."},
            {"id": "jiji", "name": "Jiji", "status": "manual_setup", "supported": False, "detail": "Use copy-ready listings until an approved seller API is available."},
            {"id": "affiliate", "name": "Affiliate networks", "status": "not_connected", "supported": False},
            {"id": "freelance", "name": "Freelance marketplaces", "status": "not_connected", "supported": False},
        ],
        "discovery_ready": tavily,
        "shopify_app_ready": bool(read_secret("shopify_client_id") and read_secret("shopify_client_secret") and read_secret("shopify_redirect_uri")),
        "ready_count": sum(1 for p in all_products if p["status"] == "ready"),
        "published_count": sum(1 for p in all_products if p["status"] in ("shopify_draft", "published")),
    }


@router.put("/settings")
def update_settings(item: SettingsInput):
    ensure_tables()
    with commerce_db() as conn:
        conn.execute("""UPDATE commerce_settings SET currency=?,target_margin_pct=?,min_profit=?,daily_scan_enabled=?,
          auto_publish=?,updated=? WHERE id=1""",
          (item.currency, float(item.target_margin_pct), float(item.min_profit), int(item.daily_scan_enabled),
           int(item.auto_publish), stamp()))
    event("settings_updated", "Commerce pricing and discovery settings updated.")
    return {"saved": True}


@router.post("/products")
def create_product(item: ProductInput):
    ensure_tables()
    with commerce_db() as conn:
        settings = conn.execute("SELECT target_margin_pct,currency,min_profit FROM commerce_settings WHERE id=1").fetchone()
    target_margin = item.target_margin_pct if item.target_margin_pct is not None else Decimal(str(settings["target_margin_pct"]))
    sale, profit = _price(item.cost, item.shipping, item.marketplace_fee_pct, item.payment_fee_pct, target_margin, settings["min_profit"])
    now, ident = stamp(), str(uuid.uuid4())
    status = "candidate"
    with commerce_db() as conn:
        conn.execute("""INSERT INTO commerce_products(id,title,description,category,model,supplier_name,source_url,cost,shipping,
        currency,marketplace_fee_pct,payment_fee_pct,target_margin_pct,sale_price,estimated_profit,stock_status,source_verified,
        resale_authorized,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ident,item.title.strip(),item.description.strip(),item.category.strip(),item.model,item.supplier_name.strip(),item.source_url,
         float(item.cost) if item.cost is not None else None,float(item.shipping),item.currency,float(item.marketplace_fee_pct),
         float(item.payment_fee_pct),float(target_margin),sale,profit,item.stock_status,int(item.source_verified),int(item.resale_authorized),status,now,now))
    event("product_added", f"Added {item.title.strip()} to product research.", ident)
    with commerce_db() as conn: row=conn.execute("SELECT * FROM commerce_products WHERE id=?",(ident,)).fetchone()
    return _row_product(row)


@router.patch("/products/{product_id}")
def update_product(product_id: str, item: ProductInput):
    ensure_tables()
    with commerce_db() as conn:
        old = conn.execute("SELECT status FROM commerce_products WHERE id=?",(product_id,)).fetchone()
        settings=conn.execute("SELECT min_profit FROM commerce_settings WHERE id=1").fetchone()
    if not old: raise HTTPException(404,"Product was not found.")
    if old["status"] in ("shopify_draft","published"): raise HTTPException(409,"This product has already been sent to a channel. Pause it there before editing the source record.")
    sale, profit = _price(item.cost,item.shipping,item.marketplace_fee_pct,item.payment_fee_pct,item.target_margin_pct,settings["min_profit"])
    with commerce_db() as conn:
        conn.execute("""UPDATE commerce_products SET title=?,description=?,category=?,model=?,supplier_name=?,source_url=?,cost=?,shipping=?,
        currency=?,marketplace_fee_pct=?,payment_fee_pct=?,target_margin_pct=?,sale_price=?,estimated_profit=?,stock_status=?,source_verified=?,
        resale_authorized=?,status='candidate',updated=? WHERE id=?""",
        (item.title.strip(),item.description.strip(),item.category.strip(),item.model,item.supplier_name.strip(),item.source_url,
         float(item.cost) if item.cost is not None else None,float(item.shipping),item.currency,float(item.marketplace_fee_pct),
         float(item.payment_fee_pct),float(item.target_margin_pct),sale,profit,item.stock_status,int(item.source_verified),int(item.resale_authorized),stamp(),product_id))
    event("product_updated",f"Updated {item.title.strip()}.",product_id)
    with commerce_db() as conn: row=conn.execute("SELECT * FROM commerce_products WHERE id=?",(product_id,)).fetchone()
    return _row_product(row)


@router.delete("/products/{product_id}")
def delete_product(product_id: str):
    ensure_tables()
    with commerce_db() as conn:
        changed=conn.execute("DELETE FROM commerce_products WHERE id=? AND status NOT IN ('shopify_draft','published')",(product_id,))
    if changed.rowcount != 1: raise HTTPException(404,"Product was not found or is already listed on a channel.")
    event("product_removed","Removed a product research record.",product_id)
    return {"deleted":True}


@router.post("/products/{product_id}/approve")
def approve_product(product_id: str):
    ensure_tables()
    with commerce_db() as conn:
        product=conn.execute("SELECT * FROM commerce_products WHERE id=?",(product_id,)).fetchone()
        settings=conn.execute("SELECT min_profit FROM commerce_settings WHERE id=1").fetchone()
    if not product: raise HTTPException(404,"Product was not found.")
    if product["model"] in ("affiliate", "freelance"):
        raise HTTPException(409,"Affiliate and freelance opportunities can be researched and drafted, but automated channel approval is not available until their network-specific terms and publishing API are connected.")
    if not product["source_verified"]: raise HTTPException(409,"Verify the supplier/source, stock and product facts first.")
    if product["model"] not in ("affiliate",) and not product["resale_authorized"]: raise HTTPException(409,"Confirm that the supplier permits resale before approving this product.")
    if product["model"] != "affiliate" and product["stock_status"] != "available": raise HTTPException(409,"Confirm current stock before approving this product.")
    if product["sale_price"] is None or product["estimated_profit"] is None: raise HTTPException(409,"Add product cost and shipping before approving it.")
    if float(product["estimated_profit"]) < float(settings["min_profit"]): raise HTTPException(409,"Estimated profit is below your minimum-profit setting.")
    with commerce_db() as conn:
        conn.execute("UPDATE commerce_products SET status='ready',updated=? WHERE id=?",(stamp(),product_id))
    event("product_approved",f"Approved {product['title']} for a channel draft.",product_id)
    return {"id":product_id,"status":"ready","message":"Product approved for an explicit channel action."}


@router.post("/discovery/run")
async def run_discovery(item: DiscoveryInput):
    ensure_tables()
    key=read_secret("tavily_api_key")
    if not key: raise HTTPException(409,"Add the Tavily Search API key in Connect API to enable online product discovery.")
    query=item.query.strip() or "trending products suppliers wholesale dropshipping available Nigeria online store"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.post("https://api.tavily.com/search",headers={"Authorization":"Bearer "+key},json={
                "query":query,"search_depth":"basic","max_results":8,"include_answer":False,"include_raw_content":False})
        if response.status_code >= 400: raise HTTPException(502,"Product search provider rejected the request. Check the saved key and provider plan.")
        payload=response.json()
    except httpx.RequestError:
        raise HTTPException(502,"Could not reach the product search provider.")
    found=[]
    for result in payload.get("results",[])[:8]:
        title=str(result.get("title") or "").strip()[:180]
        url=str(result.get("url") or "").strip()[:1000]
        if not title or not url or urlparse(url).scheme not in ("http","https"): continue
        with commerce_db() as conn:
            duplicate=conn.execute("SELECT id FROM commerce_products WHERE source_url=?",(url,)).fetchone()
            if duplicate: continue
            ident=str(uuid.uuid4()); now=stamp()
            description=str(result.get("content") or "").strip()[:1800]
            conn.execute("""INSERT INTO commerce_products(id,title,description,category,model,supplier_name,source_url,currency,
              target_margin_pct,stock_status,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (ident,title,description,"Research result","dropshipping","",url,"NGN",25,"unknown","candidate",now,now))
        event("source_found",f"Found a product/source to review: {title}.",ident)
        found.append({"id":ident,"title":title,"url":url,"snippet":description,"score":result.get("score")})
    with commerce_db() as conn:
        conn.execute("UPDATE commerce_settings SET last_scan=?,updated=? WHERE id=1",(stamp(),stamp()))
    event("discovery_completed",f"Product discovery found {len(found)} new sources. Supplier terms, price and stock need verification.")
    return {"query":query,"found":found,"count":len(found),"message":"Search results are leads only. Verify supplier terms, product price, stock and image rights before listing."}


@router.post("/products/{product_id}/copy")
async def generate_copy(product_id: str):
    ensure_tables()
    with commerce_db() as conn: row=conn.execute("SELECT * FROM commerce_products WHERE id=?",(product_id,)).fetchone()
    if not row: raise HTTPException(404,"Product was not found.")
    if row["model"] not in ("dropshipping", "resale"):
        raise HTTPException(409,"Shopify draft creation is available only for verified physical products. Affiliate and freelance flows need their own platform integration.")
    facts={key:row[key] for key in ("title","description","category","supplier_name","source_url","sale_price","currency")}
    facts["description"]=(facts["description"] or "")[:3000]
    facts["source_url"]=(facts["source_url"] or "")[:500]
    from .main import ask
    prompt=("Write original marketplace listing copy using only the supplied facts. Do not invent specifications, certifications, stock, shipping promises, warranties, discounts, or reviews. "
            "Return valid JSON with keys title, description, promo_caption. Keep title under 110 characters and promo_caption under 500 characters. "
            "If facts are insufficient, mark those details as not provided instead of guessing.\nFACTS:\n"+json.dumps(facts,ensure_ascii=False))
    raw=await ask("sales",prompt)
    try:
        clean=raw.strip()
        if clean.startswith("```"): clean=clean.strip("`").removeprefix("json").strip()
        content=json.loads(clean)
        if not all(isinstance(content.get(k),str) for k in ("title","description","promo_caption")): raise ValueError()
    except (ValueError,TypeError): raise HTTPException(502,"AI returned listing copy in an unexpected format. Try again.")
    with commerce_db() as conn: conn.execute("UPDATE commerce_products SET copy_json=?,updated=? WHERE id=?",(json.dumps(content),stamp(),product_id))
    event("copy_generated",f"Generated listing copy for {row['title']}.",product_id)
    return content


async def _shopify_graphql(query: str, variables: dict | None = None):
    shop,token=_shopify_config()
    if not shop or not token: raise HTTPException(409,"Connect Shopify first using a store domain and an Admin API token with product read/write access.")
    url=f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"
    try:
        async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
            response=await client.post(url,headers={"X-Shopify-Access-Token":token,"Content-Type":"application/json"},json={"query":query,"variables":variables or {}})
        if response.status_code in (301,302,307,308): raise HTTPException(400,"Shopify store domain redirected. Enter the canonical myshopify.com domain.")
        if response.status_code in (401,403): raise HTTPException(502,"Shopify rejected the token or its access scopes.")
        if response.status_code >= 400: raise HTTPException(502,f"Shopify API returned HTTP {response.status_code}.")
        body=response.json()
    except httpx.RequestError: raise HTTPException(502,"Could not reach Shopify.")
    if body.get("errors"): raise HTTPException(502,"Shopify GraphQL request failed. Check the token scopes and API version.")
    return body.get("data",{})


@router.post("/shopify/test")
async def test_shopify():
    data=await _shopify_graphql("query { shop { name myshopifyDomain } }")
    shop=data.get("shop") or {}
    if not shop.get("myshopifyDomain"): raise HTTPException(502,"Shopify did not return a store identity.")
    event("shopify_connected",f"Connected Shopify store {shop['myshopifyDomain']}.")
    return {"connected":True,"shop":shop["myshopifyDomain"],"name":shop.get("name")}


@router.post("/shopify/oauth/start")
def start_shopify_oauth(item: ShopifyConnectInput):
    ensure_tables()
    client_id=read_secret("shopify_client_id")
    redirect_uri=read_secret("shopify_redirect_uri")
    if not client_id or not read_secret("shopify_client_secret"):
        raise HTTPException(409,"Add the Shopify app client ID and secret in Connect API first.")
    parsed=urlparse(redirect_uri or "")
    if parsed.scheme!="https" or not parsed.hostname or parsed.path!="/api/v1/commerce/shopify/oauth/callback":
        raise HTTPException(409,"Set the HTTPS Shopify redirect URL to https://your-agentforge-host/api/v1/commerce/shopify/oauth/callback and register that exact URL in your Shopify app.")
    state=secrets.token_urlsafe(32)
    now=int(time.time())
    with commerce_db() as conn:
        conn.execute("DELETE FROM commerce_shopify_oauth_states WHERE expires_at<?",(now,))
        conn.execute("INSERT INTO commerce_shopify_oauth_states(state_hash,shop,expires_at,created) VALUES(?,?,?,?)",
                     (hashlib.sha256(state.encode()).hexdigest(),item.shop,now+600,stamp()))
    from urllib.parse import urlencode
    params=urlencode({"client_id":client_id,"scope":"read_products,write_products","redirect_uri":redirect_uri,"state":state})
    return {"authorization_url":f"https://{item.shop}/admin/oauth/authorize?{params}","shop":item.shop,
            "message":"Shopify will ask you to approve product access before connecting."}


@router.get("/shopify/oauth/callback")
async def shopify_oauth_callback(request: Request):
    ensure_tables()
    params=request.query_params
    if len(set(params.keys()))!=len(params): raise HTTPException(400,"Duplicate Shopify callback parameters are not allowed.")
    supplied_hmac=params.get("hmac","")
    state=params.get("state","")
    shop=(params.get("shop","") or "").lower()
    code=params.get("code","")
    timestamp=params.get("timestamp","")
    client_id=read_secret("shopify_client_id")
    client_secret=read_secret("shopify_client_secret")
    redirect_uri=read_secret("shopify_redirect_uri")
    if not (supplied_hmac and state and shop and code and timestamp and client_id and client_secret and redirect_uri):
        raise HTTPException(400,"Shopify authorization callback is incomplete. Start the connection again.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com",shop): raise HTTPException(400,"Shopify returned an invalid store domain.")
    try:
        if abs(int(time.time())-int(timestamp))>300: raise HTTPException(400,"Shopify authorization callback expired. Start the connection again.")
    except ValueError: raise HTTPException(400,"Shopify callback timestamp is invalid.")
    message="&".join(f"{key}={params.get(key,'')}" for key in sorted(k for k in params.keys() if k not in ("hmac","signature")))
    expected=hmac.new(client_secret.encode(),message.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,supplied_hmac): raise HTTPException(400,"Shopify callback signature did not verify.")
    state_hash=hashlib.sha256(state.encode()).hexdigest()
    now=int(time.time())
    with commerce_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row=conn.execute("SELECT shop,expires_at FROM commerce_shopify_oauth_states WHERE state_hash=?",(state_hash,)).fetchone()
        if not row or int(row["expires_at"])<=now or row["shop"]!=shop:
            raise HTTPException(400,"Shopify connection state is missing, expired or mismatched. Start again from AgentForge.")
        conn.execute("DELETE FROM commerce_shopify_oauth_states WHERE state_hash=?",(state_hash,))
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response=await client.post(f"https://{shop}/admin/oauth/access_token",json={"client_id":client_id,"client_secret":client_secret,"code":code})
        if response.status_code>=400: raise HTTPException(502,"Shopify did not complete the token exchange. Check the app setup and retry.")
        token_data=response.json()
    except httpx.RequestError: raise HTTPException(502,"Could not reach Shopify to finish connecting the store.")
    access_token=token_data.get("access_token")
    if not isinstance(access_token,str) or not access_token: raise HTTPException(502,"Shopify returned no access token.")
    store_secret("shopify_shop_domain",shop)
    store_secret("shopify_admin_token",access_token)
    with commerce_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS integration_checks(service TEXT PRIMARY KEY,status TEXT NOT NULL,message TEXT NOT NULL,checked_at TEXT NOT NULL)")
        conn.execute("INSERT INTO integration_checks(service,status,message,checked_at) VALUES('commerce_shopify','connected',?,?) ON CONFLICT(service) DO UPDATE SET status=excluded.status,message=excluded.message,checked_at=excluded.checked_at",
                     (f"Shopify authorization completed for {shop}.",stamp()))
    event("shopify_connected",f"Shopify authorization completed for {shop}.")
    return RedirectResponse(url="/?commerce=shopify_connected",status_code=303)


@router.post("/products/{product_id}/shopify-draft")
async def create_shopify_draft(product_id: str):
    ensure_tables()
    with commerce_db() as conn:
        row=conn.execute("SELECT * FROM commerce_products WHERE id=?",(product_id,)).fetchone()
        settings=conn.execute("SELECT min_profit FROM commerce_settings WHERE id=1").fetchone()
    if not row: raise HTTPException(404,"Product was not found.")
    if row["status"] != "ready": raise HTTPException(409,"Approve the verified product before creating a Shopify draft.")
    if not row["source_verified"] or (row["model"] != "affiliate" and not row["resale_authorized"]): raise HTTPException(409,"Verify the product source and resale permission first.")
    if row["sale_price"] is None or row["estimated_profit"] is None or row["estimated_profit"] < settings["min_profit"]: raise HTTPException(409,"The calculated selling price does not meet your minimum-profit rule.")
    if row["model"] != "affiliate" and row["stock_status"] != "available": raise HTTPException(409,"Confirm stock is currently available before creating a listing.")
    channels=json.loads(row["channel_ids_json"] or "{}")
    if channels.get("shopify"): raise HTTPException(409,"A Shopify draft already exists for this product.")
    copy=json.loads(row["copy_json"] or "{}")
    title=(copy.get("title") or row["title"])[:255]
    description=copy.get("description") or row["description"]
    data=await _shopify_graphql("""mutation createProduct($product: ProductCreateInput!) {
      productCreate(product: $product) { product { id title status variants(first:1) { nodes { id } } } userErrors { field message } }
    }""",{"product":{"title":title,"descriptionHtml":description,"productType":row["category"],"status":"DRAFT"}})
    result=data.get("productCreate") or {}
    errors=result.get("userErrors") or []
    product=result.get("product")
    if errors or not product: raise HTTPException(502,"Shopify could not create a draft. Review the returned product fields and token scopes.")
    variant=(product.get("variants") or {}).get("nodes") or []
    variant_id=variant[0].get("id") if variant else None
    if not variant_id: raise HTTPException(502,"Shopify created a draft but returned no variant to price; review the draft in Shopify before retrying.")
    price=f"{float(row['sale_price']):.2f}"
    priced=await _shopify_graphql("""mutation priceVariant($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) { productVariants { id price } userErrors { field message } }
    }""",{"productId":product["id"],"variants":[{"id":variant_id,"price":price}]})
    price_result=priced.get("productVariantsBulkUpdate") or {}
    if price_result.get("userErrors"):
        raise HTTPException(502,"Shopify draft was created but its variant price was not confirmed. Open Shopify and set the price before publishing.")
    channels["shopify"]={"product_id":product["id"],"status":"DRAFT","price":price}
    with commerce_db() as conn:
        conn.execute("UPDATE commerce_products SET status='shopify_draft',channel_ids_json=?,updated=? WHERE id=?",(json.dumps(channels),stamp(),product_id))
    event("shopify_draft_created",f"Created Shopify draft for {title} at {row['currency']} {price}. It is not published.",product_id)
    return {"created":True,"status":"DRAFT","product_id":product["id"],"price":price,"message":"Shopify draft created. Review and publish it from your Shopify account when ready."}


async def scheduled_discovery_scan():
    ensure_tables()
    with commerce_db() as conn: settings=conn.execute("SELECT daily_scan_enabled,last_scan FROM commerce_settings WHERE id=1").fetchone()
    if not settings or not settings["daily_scan_enabled"] or not read_secret("tavily_api_key"): return False
    try:
        last=datetime.fromisoformat(settings["last_scan"].replace("Z","+00:00")) if settings["last_scan"] else None
    except (ValueError,AttributeError): last=None
    if last and datetime.now(timezone.utc)-last < timedelta(hours=23): return False
    with commerce_db() as conn: conn.execute("UPDATE commerce_settings SET last_scan=?,updated=? WHERE id=1",(stamp(),stamp()))
    try:
        await run_discovery(DiscoveryInput(query="trending products suppliers wholesale dropshipping available Nigeria online store"))
    except Exception as exc:
        event("discovery_failed", "Scheduled product search failed. Check the search API connection and activity journal.")
        raise exc
    return True

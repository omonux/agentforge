"""Owner-approved Meta Page and Instagram commerce publishing.

Uses owner-provided Meta Page access token and IG professional account ID.
Never automatically publishes; every channel requires a distinct approval.
"""
import json
import re
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .commerce_agent import commerce_db, ensure_tables, event
from .omonux_integrations import read_secret
from .main import stamp

router = APIRouter(prefix="/api/v1/commerce/meta", tags=["Commerce Meta Publishing"])
GRAPH = "https://graph.facebook.com/v23.0"


def tables():
    ensure_tables()
    with commerce_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS commerce_meta_posts (
            id TEXT PRIMARY KEY, product_id TEXT NOT NULL, channel TEXT NOT NULL,
            caption TEXT NOT NULL, image_url TEXT, status TEXT NOT NULL,
            remote_id TEXT, created TEXT NOT NULL, updated TEXT NOT NULL,
            UNIQUE(product_id, channel, id))""")


class Draft(BaseModel):
    product_id: str = Field(min_length=1, max_length=100)
    channel: str
    caption: str = Field(min_length=10, max_length=2200)
    image_url: str | None = Field(default=None, max_length=2000)


def _image(url):
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password and parsed.hostname.lower() not in ("localhost", "127.0.0.1", "::1")


def _product(conn, product_id):
    row = conn.execute("SELECT * FROM commerce_products WHERE id=?", (product_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Product not found.")
    if row["status"] not in ("ready", "shopify_draft") or not row["source_verified"] or (row["model"] != "affiliate" and not row["resale_authorized"]):
        raise HTTPException(409, "Product must be approved with verified source and resale rights.")
    if row["model"] != "affiliate" and row["stock_status"] != "available":
        raise HTTPException(409, "Verify stock before advertising.")
    if row["sale_price"] is None:
        raise HTTPException(409, "Set a selling price before advertising.")
    return row


@router.post("/drafts")
def create_meta_draft(item: Draft):
    tables()
    if item.channel not in ("facebook", "instagram"):
        raise HTTPException(400, "Choose facebook or instagram.")
    if item.channel == "instagram" and not _image(item.image_url):
        raise HTTPException(400, "Instagram requires a publicly accessible HTTPS product image.")
    if item.image_url and not _image(item.image_url):
        raise HTTPException(400, "Image must have a valid HTTPS URL.")
    with commerce_db() as conn:
        _product(conn, item.product_id)
        post_id = str(uuid.uuid4())
        conn.execute("INSERT INTO commerce_meta_posts(id,product_id,channel,caption,image_url,status,created,updated) VALUES(?,?,?,?,?,'draft',?,?)",
                     (post_id,item.product_id,item.channel,item.caption,item.image_url,stamp(),stamp()))
    event("meta_draft_created", "Created private "+item.channel+" product campaign draft.", item.product_id)
    return {"id":post_id,"status":"draft","published":False,"approval_required":True}


@router.get("/drafts")
def list_meta_drafts():
    tables()
    with commerce_db() as conn:
        rows=conn.execute("SELECT id,product_id,channel,caption,image_url,status,remote_id,created,updated FROM commerce_meta_posts ORDER BY created DESC LIMIT 100").fetchall()
    return {"posts":[dict(r) for r in rows]}


@router.post("/drafts/{post_id}/approve")
def approve_meta_draft(post_id: str):
    tables()
    with commerce_db() as conn:
        row=conn.execute("SELECT * FROM commerce_meta_posts WHERE id=?",(post_id,)).fetchone()
        if not row: raise HTTPException(404,"Campaign not found.")
        if row["status"]!="draft": raise HTTPException(409,"Only drafts can be approved.")
        _product(conn,row["product_id"])
        conn.execute("UPDATE commerce_meta_posts SET status='approved',updated=? WHERE id=?",(stamp(),post_id))
    event("meta_draft_approved","Owner approved "+row["channel"]+" campaign.",row["product_id"])
    return {"id":post_id,"status":"approved","published":False}


@router.post("/drafts/{post_id}/publish")
async def publish_meta_draft(post_id: str):
    tables()
    # The unique publish state is claimed before contacting Meta, preventing duplicate posts
    # on repeated clicks. An uncertain response is never retried automatically.
    with commerce_db() as conn:
        row=conn.execute("SELECT * FROM commerce_meta_posts WHERE id=?",(post_id,)).fetchone()
        if not row: raise HTTPException(404,"Campaign not found.")
        if row["status"]!="approved": raise HTTPException(409,"Owner approval is required before publishing.")
        _product(conn,row["product_id"])
    token=read_secret("meta_page_access_token")
    page_id=read_secret("meta_page_id")
    ig_id=read_secret("meta_instagram_account_id")
    target=page_id if row["channel"]=="facebook" else ig_id
    if not token or not target or not re.fullmatch(r"[0-9]+",target):
        raise HTTPException(409,"Configure Meta Page token, Page ID and Instagram professional account ID in the encrypted integration vault.")
    with commerce_db() as conn:
        changed=conn.execute("UPDATE commerce_meta_posts SET status='submitting',updated=? WHERE id=? AND status='approved'",(stamp(),post_id))
        if changed.rowcount!=1: raise HTTPException(409,"Campaign is already being submitted.")
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            if row["channel"]=="facebook":
                endpoint=f"{GRAPH}/{target}/photos" if row["image_url"] else f"{GRAPH}/{target}/feed"
                payload={"url":row["image_url"],"caption":row["caption"]} if row["image_url"] else {"message":row["caption"]}
                resp=await client.post(endpoint,data=payload,headers={"Authorization":"Bearer "+token})
                resp.raise_for_status()
                remote=resp.json().get("post_id") or resp.json().get("id")
            else:
                resp=await client.post(f"{GRAPH}/{target}/media",data={"image_url":row["image_url"],"caption":row["caption"]},headers={"Authorization":"Bearer "+token})
                resp.raise_for_status()
                creation_id=resp.json().get("id")
                if not creation_id: raise ValueError("No Instagram container ID")
                # Container processing is asynchronous; do not publish until READY.
                status=await client.get(f"{GRAPH}/{creation_id}",params={"fields":"status_code"},headers={"Authorization":"Bearer "+token})
                status.raise_for_status()
                if status.json().get("status_code")!="FINISHED":
                    with commerce_db() as conn:
                        conn.execute("UPDATE commerce_meta_posts SET status='processing',remote_id=?,updated=? WHERE id=?",(creation_id,stamp(),post_id))
                    return {"id":post_id,"status":"processing","published":False,"message":"Instagram is processing the image. Use the resume endpoint once ready."}
                resp=await client.post(f"{GRAPH}/{target}/media_publish",data={"creation_id":creation_id},headers={"Authorization":"Bearer "+token})
                resp.raise_for_status()
                remote=resp.json().get("id")
        if not remote: raise ValueError("Meta returned no publication ID")
    except (httpx.HTTPError, ValueError, KeyError):
        with commerce_db() as conn:
            conn.execute("UPDATE commerce_meta_posts SET status='uncertain',updated=? WHERE id=?",(stamp(),post_id))
        raise HTTPException(502,"Meta submission could not be confirmed. Check Meta before retrying; automatic retry is disabled.")
    with commerce_db() as conn:
        conn.execute("UPDATE commerce_meta_posts SET status='published',remote_id=?,updated=? WHERE id=?",(remote,stamp(),post_id))
    event("meta_campaign_published","Published approved "+row["channel"]+" campaign.",row["product_id"])
    return {"id":post_id,"status":"published","remote_id":remote,"published":True}


@router.post("/drafts/{post_id}/resume")
async def resume_instagram(post_id: str):
    tables()
    with commerce_db() as conn:
        row=conn.execute("SELECT * FROM commerce_meta_posts WHERE id=?",(post_id,)).fetchone()
    if not row or row["channel"]!="instagram" or row["status"]!="processing":
        raise HTTPException(409,"No Instagram container is awaiting completion.")
    token=read_secret("meta_page_access_token")
    ig_id=read_secret("meta_instagram_account_id")
    if not token or not ig_id or not re.fullmatch(r"[0-9]+",ig_id):
        raise HTTPException(409,"Meta credentials are not configured.")
    async with httpx.AsyncClient(timeout=25) as client:
        check=await client.get(f"{GRAPH}/{row['remote_id']}",params={"fields":"status_code"},headers={"Authorization":"Bearer "+token})
        if check.status_code>=400: raise HTTPException(502,"Instagram container status could not be verified.")
        if check.json().get("status_code")!="FINISHED":
            return {"id":post_id,"status":"processing","published":False}
        with commerce_db() as conn:
            changed=conn.execute("UPDATE commerce_meta_posts SET status='submitting',updated=? WHERE id=? AND status='processing'",(stamp(),post_id))
            if changed.rowcount!=1: raise HTTPException(409,"Already being submitted.")
        try:
            response=await client.post(f"{GRAPH}/{ig_id}/media_publish",data={"creation_id":row["remote_id"]},headers={"Authorization":"Bearer "+token})
            response.raise_for_status()
            remote=response.json()["id"]
        except (httpx.HTTPError,KeyError,ValueError):
            with commerce_db() as conn:
                conn.execute("UPDATE commerce_meta_posts SET status='uncertain',updated=? WHERE id=?",(stamp(),post_id))
            raise HTTPException(502,"Publication confirmation is uncertain; verify in Instagram.")
    with commerce_db() as conn:
        conn.execute("UPDATE commerce_meta_posts SET status='published',remote_id=?,updated=? WHERE id=?",(remote,stamp(),post_id))
    event("meta_campaign_published","Published approved Instagram campaign.",row["product_id"])
    return {"id":post_id,"status":"published","published":True,"remote_id":remote}

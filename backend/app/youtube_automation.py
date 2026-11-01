import os, sqlite3, uuid, secrets, json, urllib.parse, asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

router=APIRouter(prefix="/api/v1/youtube",tags=["YouTube Automation"])
DB=Path(os.getenv("DATABASE_PATH","./agentforge.db"))
CLIENT=os.getenv("YOUTUBE_CLIENT_ID","")
SECRET=os.getenv("YOUTUBE_CLIENT_SECRET","")
REDIRECT=os.getenv("YOUTUBE_REDIRECT_URI","http://localhost:8000/api/v1/youtube/oauth/callback")
REGION=os.getenv("YOUTUBE_REGION","NG")
AI_BASE=os.getenv("AI_BASE_URL","").rstrip("/")
AI_KEY=os.getenv("AI_API_KEY","")
AI_MODEL=os.getenv("AI_MODEL","")
VIDEO_KEY=os.getenv("VIDEO_API_KEY","")
VIDEO_MODEL=os.getenv("VIDEO_MODEL","")
VIDEO_PROVIDER=os.getenv("VIDEO_PROVIDER","replicate").lower()
VIDEO_DIR=Path(os.getenv("YOUTUBE_STORAGE_DIR","./storage/youtube")).resolve()
SCOPES="https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"

def now(): return datetime.now(timezone.utc).isoformat()
def conn():
 DB.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 c.execute("""CREATE TABLE IF NOT EXISTS yt_settings(id INTEGER PRIMARY KEY CHECK(id=1),access_token TEXT,refresh_token TEXT,expires_at TEXT,channel_title TEXT,channel_id TEXT)""")
 c.execute("""CREATE TABLE IF NOT EXISTS yt_drafts(id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,script TEXT NOT NULL,topic TEXT NOT NULL,video_path TEXT,thumbnail_path TEXT,status TEXT NOT NULL,privacy TEXT NOT NULL,created TEXT NOT NULL,published_url TEXT,published_at TEXT,error TEXT)""")
 c.execute("""CREATE TABLE IF NOT EXISTS yt_oauth_states(state TEXT PRIMARY KEY,created TEXT NOT NULL)""")
 c.commit(); return c

class Discover(BaseModel):
 query:str=Field(default="AI",min_length=1,max_length=100)
 max_results:int=Field(default=12,ge=1,le=25)
class Draft(BaseModel):
 topic:str=Field(min_length=4,max_length=300)
 style:str=Field(default="engaging educational short",max_length=120)
 duration_seconds:int=Field(default=45,ge=15,le=180)
 privacy:str=Field(default="private",pattern="^(private|unlisted|public)$")
class Approve(BaseModel):
 confirmed:bool
 privacy:str=Field(default="private",pattern="^(private|unlisted|public)$")

def token_row():
 with conn() as c: return c.execute("SELECT * FROM yt_settings WHERE id=1").fetchone()
async def access_token():
 row=token_row()
 if not row or not row["refresh_token"]: raise HTTPException(409,"Connect your YouTube channel first.")
 if row["access_token"] and row["expires_at"] and datetime.fromisoformat(row["expires_at"])>datetime.now(timezone.utc)+timedelta(seconds=60): return row["access_token"]
 if not CLIENT or not SECRET: raise HTTPException(503,"Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in backend environment.")
 async with httpx.AsyncClient(timeout=30) as h:
  r=await h.post("https://oauth2.googleapis.com/token",data={"client_id":CLIENT,"client_secret":SECRET,"refresh_token":row["refresh_token"],"grant_type":"refresh_token"})
 if r.status_code>=400: raise HTTPException(502,"YouTube authorization expired. Reconnect the channel.")
 d=r.json(); expiry=(datetime.now(timezone.utc)+timedelta(seconds=int(d.get("expires_in",3600)))).isoformat()
 with conn() as c: c.execute("UPDATE yt_settings SET access_token=?,expires_at=? WHERE id=1",(d["access_token"],expiry))
 return d["access_token"]

@router.get("/status")
def status():
 row=token_row()
 return {"configured":bool(CLIENT and SECRET),"connected":bool(row and row["refresh_token"]),"channel":row["channel_title"] if row else None,"region":REGION,"video_generation_configured":bool(VIDEO_KEY and VIDEO_MODEL),"video_provider":VIDEO_PROVIDER}
@router.get("/oauth/start")
def oauth_start():
 if not CLIENT or not SECRET: raise HTTPException(503,"Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in backend environment.")
 state=secrets.token_urlsafe(32)
 with conn() as c:
  c.execute("DELETE FROM yt_oauth_states WHERE created<?",((datetime.now(timezone.utc)-timedelta(minutes=20)).isoformat(),))
  c.execute("INSERT INTO yt_oauth_states VALUES(?,?)",(state,now()))
 params={"client_id":CLIENT,"redirect_uri":REDIRECT,"response_type":"code","scope":SCOPES,"access_type":"offline","prompt":"consent","state":state}
 return {"authorization_url":"https://accounts.google.com/o/oauth2/v2/auth?"+urllib.parse.urlencode(params)}
@router.get("/oauth/callback")
async def oauth_callback(code:str="",state:str="",error:str=""):
 if error: raise HTTPException(400,"YouTube authorization was not granted.")
 with conn() as c:
  valid=c.execute("SELECT state FROM yt_oauth_states WHERE state=?",(state,)).fetchone()
  if not valid: raise HTTPException(400,"OAuth state is invalid or expired. Start connection again.")
  c.execute("DELETE FROM yt_oauth_states WHERE state=?",(state,))
 if not code: raise HTTPException(400,"Missing OAuth authorization code.")
 async with httpx.AsyncClient(timeout=30) as h:
  r=await h.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":CLIENT,"client_secret":SECRET,"redirect_uri":REDIRECT,"grant_type":"authorization_code"})
 if r.status_code>=400: raise HTTPException(502,"Could not exchange YouTube authorization code.")
 d=r.json(); token=d["access_token"]
 async with httpx.AsyncClient(timeout=30) as h:
  q=await h.get("https://www.googleapis.com/youtube/v3/channels",params={"part":"snippet","mine":"true"},headers={"Authorization":"Bearer "+token})
 if q.status_code>=400: raise HTTPException(502,"Could not read the connected YouTube channel.")
 items=q.json().get("items",[])
 if not items: raise HTTPException(502,"No YouTube channel was found on this Google account.")
 channel=items[0]
 old=token_row(); refresh=d.get("refresh_token") or (old["refresh_token"] if old else None)
 expires=(datetime.now(timezone.utc)+timedelta(seconds=int(d.get("expires_in",3600)))).isoformat()
 with conn() as c:
  c.execute("INSERT OR REPLACE INTO yt_settings(id,access_token,refresh_token,expires_at,channel_title,channel_id) VALUES(1,?,?,?,?,?)",(token,refresh,expires,channel["snippet"]["title"],channel["id"]))
 return RedirectResponse("/?youtube=connected",status_code=303)

@router.post("/trends")
async def trends(req:Discover):
 tok=await access_token()
 async with httpx.AsyncClient(timeout=35) as h:
  r=await h.get("https://www.googleapis.com/youtube/v3/videos",params={"part":"snippet,statistics,contentDetails","chart":"mostPopular","regionCode":REGION,"maxResults":req.max_results},headers={"Authorization":"Bearer "+tok})
 if r.status_code>=400: raise HTTPException(502,"YouTube trend discovery failed. Check Data API quota and channel permissions.")
 rows=[]
 for v in r.json().get("items",[]):
  sn=v["snippet"]; st=v.get("statistics",{})
  rows.append({"id":v["id"],"title":sn["title"],"channel":sn["channelTitle"],"description":sn.get("description","")[:350],"published_at":sn.get("publishedAt"),"views":int(st.get("viewCount",0)),"likes":int(st.get("likeCount",0)),"url":"https://www.youtube.com/watch?v="+v["id"]})
 q=req.query.lower()
 if q not in ("","all","ai"):
  rows=[x for x in rows if q in (x["title"]+" "+x["description"]+" "+x["channel"]).lower()]
 return {"region":REGION,"items":rows,"notice":"Popular videos are discovery signals, not a guarantee of future trends. Create original videos; do not re-upload other creators' work."}

@router.post("/drafts")
async def create_draft(req:Draft):
 if not (AI_BASE and AI_KEY and AI_MODEL): raise HTTPException(503,"Configure AI_BASE_URL, AI_API_KEY and AI_MODEL for script generation.")
 prompt=f"Create an original YouTube video package. Topic: {req.topic}. Style: {req.style}. Target duration: {req.duration_seconds} seconds. Return valid JSON only with keys title, description, script. Script must be original, paced for voice narration, include a strong opening hook and clear ending. Do not copy other videos or claim unverified facts."
 async with httpx.AsyncClient(timeout=90) as h:
  r=await h.post(AI_BASE+"/chat/completions",headers={"Authorization":"Bearer "+AI_KEY},json={"model":AI_MODEL,"temperature":0.7,"response_format":{"type":"json_object"},"messages":[{"role":"system","content":"You are a careful YouTube producer. Produce original content, never plagiarize."},{"role":"user","content":prompt}]})
 if r.status_code>=400: raise HTTPException(502,"AI could not create the video script package.")
 try: package=json.loads(r.json()["choices"][0]["message"]["content"])
 except Exception: raise HTTPException(502,"AI returned an invalid video package.")
 ident=str(uuid.uuid4()); created=now()
 with conn() as c:
  c.execute("INSERT INTO yt_drafts(id,title,description,script,topic,status,privacy,created) VALUES(?,?,?,?,?,'script_ready',?,?)",(ident,str(package["title"])[:100],str(package["description"])[:5000],str(package["script"])[:30000],req.topic,req.privacy,created))
 return {"id":ident,"title":package["title"],"description":package["description"],"script":package["script"],"status":"script_ready","message":"Script package created. A rendered video is still required before approval and upload."}

@router.post("/drafts/{draft_id}/render")
async def render_draft(draft_id:str):
 if VIDEO_PROVIDER!="replicate" or not (VIDEO_KEY and VIDEO_MODEL): raise HTTPException(503,"Configure VIDEO_PROVIDER=replicate, VIDEO_API_KEY and VIDEO_MODEL. Video rendering is not yet configured.")
 with conn() as c: row=c.execute("SELECT * FROM yt_drafts WHERE id=?",(draft_id,)).fetchone()
 if not row: raise HTTPException(404,"Draft not found.")
 # Replicate model slug format: owner/model. It returns prediction output, which may be a video URL.
 if "/" not in VIDEO_MODEL: raise HTTPException(503,"VIDEO_MODEL must be a Replicate model slug in owner/model format.")
 async with httpx.AsyncClient(timeout=60) as h:
  r=await h.post("https://api.replicate.com/v1/models/"+VIDEO_MODEL+"/predictions",headers={"Authorization":"Bearer "+VIDEO_KEY,"Prefer":"wait=60","Content-Type":"application/json"},json={"input":{"prompt":row["script"]}})
 if r.status_code>=400: raise HTTPException(502,"Video provider rejected the render request. Check model input schema and account limits.")
 pred=r.json()
 if pred.get("status") not in ("succeeded",) or not pred.get("output"):
  return {"id":draft_id,"render_status":pred.get("status","starting"),"prediction_url":pred.get("urls",{}).get("get"),"message":"Render is still processing. Poll the prediction URL or retry after provider completion."}
 output=pred["output"]; url=output[0] if isinstance(output,list) else output
 if not isinstance(url,str) or not url.startswith("https://"): raise HTTPException(502,"Video provider returned an invalid output URL.")
 VIDEO_DIR.mkdir(parents=True,exist_ok=True); path=VIDEO_DIR/(draft_id+".mp4")
 async with httpx.AsyncClient(timeout=180,follow_redirects=True) as h:
  v=await h.get(url)
 if v.status_code>=400 or not v.content.startswith(b"\x00\x00\x00") and b"ftyp" not in v.content[:32]: raise HTTPException(502,"Provider output was not a valid MP4 video.")
 if len(v.content)>500_000_000: raise HTTPException(502,"Rendered video exceeded the 500 MB safety limit.")
 path.write_bytes(v.content)
 with conn() as c: c.execute("UPDATE yt_drafts SET video_path=?,status='ready_for_approval' WHERE id=?",(str(path),draft_id))
 return {"id":draft_id,"status":"ready_for_approval","bytes":len(v.content)}

@router.get("/drafts")
def drafts():
 with conn() as c: rows=c.execute("SELECT id,title,description,script,topic,status,privacy,created,published_url,published_at,error,video_path FROM yt_drafts ORDER BY created DESC LIMIT 100").fetchall()
 return [{**{k:r[k] for k in r.keys() if k!="video_path"},"has_video":bool(r["video_path"])} for r in rows]
@router.get("/drafts/{draft_id}/video")
def draft_video(draft_id:str):
 from fastapi.responses import FileResponse
 with conn() as c: row=c.execute("SELECT video_path,status FROM yt_drafts WHERE id=?",(draft_id,)).fetchone()
 if not row or not row["video_path"] or row["status"] not in ("ready_for_approval","published"): raise HTTPException(404,"Rendered video not found.")
 p=Path(row["video_path"]).resolve()
 if p.parent!=VIDEO_DIR or not p.is_file(): raise HTTPException(404,"Video file unavailable.")
 return FileResponse(p,media_type="video/mp4",filename=draft_id+".mp4")
@router.post("/drafts/{draft_id}/approve-publish")
async def approve_publish(draft_id:str,req:Approve):
 if req.confirmed is not True: raise HTTPException(400,"Explicit approval is required.")
 with conn() as c: row=c.execute("SELECT * FROM yt_drafts WHERE id=?",(draft_id,)).fetchone()
 if not row: raise HTTPException(404,"Draft not found.")
 if row["status"]!="ready_for_approval" or not row["video_path"] or not Path(row["video_path"]).is_file(): raise HTTPException(409,"Only a fully rendered video can be approved for upload.")
 tok=await access_token()
 metadata={"snippet":{"title":row["title"][:100],"description":row["description"]+"\n\n"+row["script"][:3500],"categoryId":"28"},"status":{"privacyStatus":req.privacy,"selfDeclaredMadeForKids":False}}
 async with httpx.AsyncClient(timeout=60) as h:
  init=await h.post("https://www.googleapis.com/upload/youtube/v3/videos",params={"uploadType":"resumable","part":"snippet,status"},headers={"Authorization":"Bearer "+tok,"Content-Type":"application/json; charset=UTF-8","X-Upload-Content-Type":"video/mp4"},json=metadata)
 if init.status_code>=400: raise HTTPException(502,"YouTube could not start the upload. Check channel verification, API quota and upload permissions.")
 upload_url=init.headers.get("Location")
 if not upload_url: raise HTTPException(502,"YouTube did not provide an upload session.")
 file=Path(row["video_path"])
 async with httpx.AsyncClient(timeout=600) as h:
  up=await h.put(upload_url,content=file.read_bytes(),headers={"Content-Type":"video/mp4","Content-Length":str(file.stat().st_size)})
 if up.status_code not in (200,201): raise HTTPException(502,"YouTube upload failed. The draft remains saved; check upload status before retrying to avoid duplicates.")
 vid=up.json()["id"]; link="https://www.youtube.com/watch?v="+vid
 with conn() as c: c.execute("UPDATE yt_drafts SET status='published',privacy=?,published_url=?,published_at=?,error=NULL WHERE id=?",(req.privacy,now(),link,draft_id))
 return {"status":"published","video_id":vid,"url":link,"privacy":req.privacy}

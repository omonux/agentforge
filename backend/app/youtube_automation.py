import os, sqlite3, uuid, secrets, json, urllib.parse, asyncio, re, subprocess, shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from .omonux_integrations import secret_or_env, read_secret, store_secret, send_telegram_message
from . import main as app_main

router=APIRouter(prefix="/api/v1/youtube",tags=["YouTube Automation"])
def cfg(name, env, default=""):
 return secret_or_env(name, env, default)

def youtube_config():
 return (cfg("youtube_client_id","YOUTUBE_CLIENT_ID"),
         cfg("youtube_client_secret","YOUTUBE_CLIENT_SECRET"),
         cfg("youtube_redirect_uri","YOUTUBE_REDIRECT_URI","http://localhost:8000/api/v1/youtube/oauth/callback"),
         cfg("youtube_region","YOUTUBE_REGION","NG"))

def ai_config():
 return (cfg("ai_base_url","AI_BASE_URL").rstrip("/"),
         cfg("ai_api_key","AI_API_KEY"),cfg("ai_model","AI_MODEL"))

def video_config():
 return (cfg("replicate_api_token","VIDEO_API_KEY"),
         cfg("replicate_model","VIDEO_MODEL"),
         os.getenv("VIDEO_PROVIDER","replicate").lower())
VIDEO_DIR=Path(os.getenv("YOUTUBE_STORAGE_DIR","./storage/youtube")).resolve()
SCOPES="https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly https://www.googleapis.com/auth/yt-analytics-monetary.readonly"

def now(): return datetime.now(timezone.utc).isoformat()
def conn():
 db_path=Path(os.getenv("DATABASE_PATH",str(app_main.DB)))
 db_path.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(db_path); c.row_factory=sqlite3.Row
 c.execute("""CREATE TABLE IF NOT EXISTS yt_settings(id INTEGER PRIMARY KEY CHECK(id=1),access_token TEXT,refresh_token TEXT,expires_at TEXT,channel_title TEXT,channel_id TEXT)""")
 c.execute("""CREATE TABLE IF NOT EXISTS yt_drafts(id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,script TEXT NOT NULL,topic TEXT NOT NULL,video_path TEXT,thumbnail_path TEXT,status TEXT NOT NULL,privacy TEXT NOT NULL,created TEXT NOT NULL,published_url TEXT,published_at TEXT,error TEXT)""")
 c.execute("""CREATE TABLE IF NOT EXISTS yt_oauth_states(state TEXT PRIMARY KEY,created TEXT NOT NULL)""")
 columns={r["name"] for r in c.execute("PRAGMA table_info(yt_drafts)").fetchall()}
 for name,definition in (("voice_path","TEXT"),("captions_path","TEXT"),("render_prediction_url","TEXT"),("telegram_daily_report_enabled","INTEGER NOT NULL DEFAULT 0"),("last_telegram_report_at","TEXT")):
  if name not in columns: c.execute(f"ALTER TABLE yt_drafts ADD COLUMN {name} {definition}")
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
class DailyReportIn(BaseModel):
 enabled:bool

def token_row():
 with conn() as c: row=c.execute("SELECT * FROM yt_settings WHERE id=1").fetchone()
 if row and (row["access_token"] or row["refresh_token"]):
  if row["access_token"]: store_secret("youtube_access_token",row["access_token"])
  if row["refresh_token"]: store_secret("youtube_refresh_token",row["refresh_token"])
  with conn() as c: c.execute("UPDATE yt_settings SET access_token=NULL,refresh_token=NULL WHERE id=1")
  with conn() as c: row=c.execute("SELECT * FROM yt_settings WHERE id=1").fetchone()
 return row
async def access_token():
 row=token_row()
 refresh_token=read_secret("youtube_refresh_token")
 access_token_value=read_secret("youtube_access_token")
 if not row or not refresh_token: raise HTTPException(409,"Connect your YouTube channel first.")
 if access_token_value and row["expires_at"] and datetime.fromisoformat(row["expires_at"])>datetime.now(timezone.utc)+timedelta(seconds=60): return access_token_value
 client_id,client_secret,redirect_uri,_region=youtube_config()
 if not client_id or not client_secret: raise HTTPException(503,"Open Connect API and add the Google OAuth client ID and secret.")
 async with httpx.AsyncClient(timeout=30) as h:
  r=await h.post("https://oauth2.googleapis.com/token",data={"client_id":client_id,"client_secret":client_secret,"refresh_token":refresh_token,"grant_type":"refresh_token"})
 if r.status_code>=400: raise HTTPException(502,"YouTube authorization expired. Reconnect the channel.")
 d=r.json(); expiry=(datetime.now(timezone.utc)+timedelta(seconds=int(d.get("expires_in",3600)))).isoformat()
 store_secret("youtube_access_token",d["access_token"])
 with conn() as c: c.execute("UPDATE yt_settings SET access_token=NULL,refresh_token=NULL,expires_at=? WHERE id=1",(expiry,))
 return d["access_token"]

@router.get("/status")
def status():
 row=token_row()
 client_id,client_secret,_redirect,region=youtube_config()
 video_key,video_model,video_provider=video_config()
 voice_key,voice_id,_voice_model=voice_config()
 return {"configured":bool(client_id and client_secret),"connected":bool(row and read_secret("youtube_refresh_token")),"channel":row["channel_title"] if row else None,"region":region,"video_generation_configured":bool(video_key and video_model),"video_provider":video_provider,"voice_generation_configured":bool(voice_key and voice_id)}
@router.get("/oauth/start")
def oauth_start():
 client_id,client_secret,redirect_uri,_region=youtube_config()
 if not client_id or not client_secret: raise HTTPException(503,"Open Connect API and add the Google OAuth client ID and secret.")
 state=secrets.token_urlsafe(32)
 with conn() as c:
  c.execute("DELETE FROM yt_oauth_states WHERE created<?",((datetime.now(timezone.utc)-timedelta(minutes=20)).isoformat(),))
  c.execute("INSERT INTO yt_oauth_states VALUES(?,?)",(state,now()))
 params={"client_id":client_id,"redirect_uri":redirect_uri,"response_type":"code","scope":SCOPES,"access_type":"offline","prompt":"consent","state":state}
 return {"authorization_url":"https://accounts.google.com/o/oauth2/v2/auth?"+urllib.parse.urlencode(params)}
@router.get("/oauth/callback")
async def oauth_callback(code:str="",state:str="",error:str=""):
 client_id,client_secret,redirect_uri,_region=youtube_config()
 if error: raise HTTPException(400,"YouTube authorization was not granted.")
 with conn() as c:
  valid=c.execute("SELECT state FROM yt_oauth_states WHERE state=?",(state,)).fetchone()
  if not valid: raise HTTPException(400,"OAuth state is invalid or expired. Start connection again.")
  c.execute("DELETE FROM yt_oauth_states WHERE state=?",(state,))
 if not code: raise HTTPException(400,"Missing OAuth authorization code.")
 async with httpx.AsyncClient(timeout=30) as h:
  r=await h.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":client_id,"client_secret":client_secret,"redirect_uri":redirect_uri,"grant_type":"authorization_code"})
 if r.status_code>=400: raise HTTPException(502,"Could not exchange YouTube authorization code.")
 d=r.json(); token=d["access_token"]
 async with httpx.AsyncClient(timeout=30) as h:
  q=await h.get("https://www.googleapis.com/youtube/v3/channels",params={"part":"snippet","mine":"true"},headers={"Authorization":"Bearer "+token})
 if q.status_code>=400: raise HTTPException(502,"Could not read the connected YouTube channel.")
 items=q.json().get("items",[])
 if not items: raise HTTPException(502,"No YouTube channel was found on this Google account.")
 channel=items[0]
 refresh=d.get("refresh_token") or read_secret("youtube_refresh_token")
 if not refresh: raise HTTPException(502,"Google did not issue a refresh token. Remove AgentForge access from your Google account and reconnect with consent.")
 store_secret("youtube_access_token",token); store_secret("youtube_refresh_token",refresh)
 expires=(datetime.now(timezone.utc)+timedelta(seconds=int(d.get("expires_in",3600)))).isoformat()
 with conn() as c:
  c.execute("INSERT OR REPLACE INTO yt_settings(id,access_token,refresh_token,expires_at,channel_title,channel_id) VALUES(1,NULL,NULL,?,?,?)",(expires,channel["snippet"]["title"],channel["id"]))
 return RedirectResponse("/?youtube=connected",status_code=303)

@router.post("/trends")
async def trends(req:Discover):
 tok=await access_token()
 async with httpx.AsyncClient(timeout=35) as h:
  r=await h.get("https://www.googleapis.com/youtube/v3/videos",params={"part":"snippet,statistics,contentDetails","chart":"mostPopular","regionCode":youtube_config()[3],"maxResults":req.max_results},headers={"Authorization":"Bearer "+tok})
 if r.status_code>=400: raise HTTPException(502,"YouTube trend discovery failed. Check Data API quota and channel permissions.")
 rows=[]
 for v in r.json().get("items",[]):
  sn=v["snippet"]; st=v.get("statistics",{})
  rows.append({"id":v["id"],"title":sn["title"],"channel":sn["channelTitle"],"description":sn.get("description","")[:350],"published_at":sn.get("publishedAt"),"views":int(st.get("viewCount",0)),"likes":int(st.get("likeCount",0)),"url":"https://www.youtube.com/watch?v="+v["id"]})
 q=req.query.lower()
 if q not in ("","all","ai"):
  rows=[x for x in rows if q in (x["title"]+" "+x["description"]+" "+x["channel"]).lower()]
 return {"region":youtube_config()[3],"items":rows,"notice":"Popular videos are discovery signals, not a guarantee of future trends. Create original videos; do not re-upload other creators' work."}


async def fetch_channel_analytics(days:int=28):
 tok=await access_token()
 end=(datetime.now(timezone.utc).date()-timedelta(days=2))
 start=end-timedelta(days=days-1)
 base_params={"ids":"channel==MINE","startDate":start.isoformat(),"endDate":end.isoformat(),"dimensions":"day","sort":"day"}
 headers={"Authorization":"Bearer "+tok}
 async with httpx.AsyncClient(timeout=35) as h:
  channel=await h.get("https://www.googleapis.com/youtube/v3/channels",params={"part":"statistics","mine":"true"},headers=headers)
  if channel.status_code>=400: raise HTTPException(502,"YouTube channel statistics could not be loaded.")
  channel_items=channel.json().get("items",[])
  subscriber_count=int(channel_items[0].get("statistics",{}).get("subscriberCount",0)) if channel_items else None
  params={**base_params,"metrics":"views,subscribersGained,subscribersLost,estimatedRevenue"}
  response=await h.get("https://youtubeanalytics.googleapis.com/v2/reports",params=params,headers=headers)
  revenue_available=response.status_code<400
  if not revenue_available:
   params["metrics"]="views,subscribersGained,subscribersLost"
   response=await h.get("https://youtubeanalytics.googleapis.com/v2/reports",params=params,headers=headers)
  if response.status_code>=400: raise HTTPException(502,"YouTube Analytics is unavailable. Reconnect with YouTube Analytics permissions and check channel access.")
 data=response.json(); rows_data=data.get("rows",[])
 headers_meta=[x.get("name") for x in data.get("columnHeaders",[])]
 totals={"views":0,"subscribers_gained":0,"subscribers_lost":0,"estimated_revenue":None}
 for row in rows_data:
  values=dict(zip(headers_meta,row))
  totals["views"]+=int(values.get("views",0) or 0)
  totals["subscribers_gained"]+=int(values.get("subscribersGained",0) or 0)
  totals["subscribers_lost"]+=int(values.get("subscribersLost",0) or 0)
  if revenue_available:
   totals["estimated_revenue"]=(totals["estimated_revenue"] or 0)+float(values.get("estimatedRevenue",0) or 0)
 return {"period_days":days,"start_date":start.isoformat(),"end_date":end.isoformat(),
         "subscriber_count":subscriber_count,"totals":totals,"currency":"USD",
         "revenue_available":revenue_available,
         "notice":"YouTube Analytics data can be delayed. Estimated revenue is available only for eligible monetized channels with monetary analytics permission."}

@router.get("/analytics")
async def channel_analytics(days:int=28):
 if days<7 or days>90: raise HTTPException(400,"days must be between 7 and 90.")
 return await fetch_channel_analytics(days)


@router.get("/notifications/daily")
def daily_report_status():
 row=token_row()
 with conn() as c:
  settings=c.execute("SELECT telegram_daily_report_enabled,last_telegram_report_at FROM yt_settings WHERE id=1").fetchone()
 return {"enabled":bool(settings and settings["telegram_daily_report_enabled"]),"last_sent_at":settings["last_telegram_report_at"] if settings else None,
         "youtube_connected":bool(row and read_secret("youtube_refresh_token")),
         "telegram_configured":bool(read_secret("telegram_bot_token") and read_secret("telegram_chat_id"))}

@router.put("/notifications/daily")
def set_daily_report(req:DailyReportIn):
 if req.enabled and not (read_secret("telegram_bot_token") and read_secret("telegram_chat_id")):
  raise HTTPException(409,"Configure and test Telegram in Connect API before enabling daily reports.")
 if req.enabled and not read_secret("youtube_refresh_token"):
  raise HTTPException(409,"Connect your YouTube channel before enabling daily analytics reports.")
 with conn() as c:
  c.execute("UPDATE yt_settings SET telegram_daily_report_enabled=? WHERE id=1",(1 if req.enabled else 0,))
 return {"enabled":req.enabled,"message":"Daily Telegram analytics enabled." if req.enabled else "Daily Telegram analytics disabled."}

async def maybe_send_daily_analytics_report():
 row=token_row()
 if not row or not read_secret("youtube_refresh_token"): return False
 with conn() as c: settings=c.execute("SELECT telegram_daily_report_enabled,last_telegram_report_at FROM yt_settings WHERE id=1").fetchone()
 if not settings or not settings["telegram_daily_report_enabled"]: return False
 last=settings["last_telegram_report_at"]
 if last:
  try:
   if datetime.fromisoformat(last)>datetime.now(timezone.utc)-timedelta(hours=24): return False
  except ValueError: pass
 if not (read_secret("telegram_bot_token") and read_secret("telegram_chat_id")): return False
 report=await fetch_channel_analytics(28); totals=report["totals"]
 revenue=("Estimated revenue: $"+format(totals["estimated_revenue"],".2f")) if report["revenue_available"] else "Estimated revenue: unavailable for this channel/permission"
 message=("AgentForge daily YouTube report ("+report["start_date"]+" to "+report["end_date"]+")\n"
          +"Views: "+str(totals["views"])+"\n"
          +"Subscribers gained: "+str(totals["subscribers_gained"])+"\n"
          +"Subscribers lost: "+str(totals["subscribers_lost"])+"\n"
          +"Net subscriber change: "+str(totals["subscribers_gained"]-totals["subscribers_lost"])+"\n"
          +revenue)
 sent=await send_telegram_message(message)
 if sent:
  with conn() as c: c.execute("UPDATE yt_settings SET last_telegram_report_at=? WHERE id=1",(now(),))
 return bool(sent)

@router.post("/analytics/send-telegram")
async def send_analytics_to_telegram(days:int=28):
 if days<7 or days>90: raise HTTPException(400,"days must be between 7 and 90.")
 report=await fetch_channel_analytics(days)
 totals=report["totals"]
 revenue=("Estimated revenue: $"+format(totals["estimated_revenue"],".2f")) if report["revenue_available"] else "Estimated revenue: not available (check monetization and Google Analytics permission)"
 message=("AgentForge YouTube report ("+report["start_date"]+" to "+report["end_date"]+")\n"
          +"Views: "+str(totals["views"])+"\n"
          +"Subscribers gained: "+str(totals["subscribers_gained"])+"\n"
          +"Subscribers lost: "+str(totals["subscribers_lost"])+"\n"
          +"Net subscriber change: "+str(totals["subscribers_gained"]-totals["subscribers_lost"])+"\n"
          +revenue)
 sent=await send_telegram_message(message)
 if not sent: raise HTTPException(409,"Configure and test Telegram in Connect API first.")
 return {"sent":True,"message":"YouTube analytics report sent to Telegram."}

@router.post("/drafts")
async def create_draft(req:Draft):
 ai_base,ai_key,ai_model=ai_config()
 if not (ai_base and ai_key and ai_model): raise HTTPException(503,"Open Connect API and configure the AI provider before generating scripts.")
 prompt=f"Create an original YouTube video package. Topic: {req.topic}. Style: {req.style}. Target duration: {req.duration_seconds} seconds. Return valid JSON only with keys title, description, script. Script must be original, paced for voice narration, include a strong opening hook and clear ending. Do not copy other videos or claim unverified facts."
 async with httpx.AsyncClient(timeout=90) as h:
  r=await h.post(ai_base+"/chat/completions",headers={"Authorization":"Bearer "+ai_key},json={"model":ai_model,"temperature":0.7,"response_format":{"type":"json_object"},"messages":[{"role":"system","content":"You are a careful YouTube producer. Produce original content, never plagiarize."},{"role":"user","content":prompt}]})
 if r.status_code>=400: raise HTTPException(502,"AI could not create the video script package.")
 try: package=json.loads(r.json()["choices"][0]["message"]["content"])
 except Exception: raise HTTPException(502,"AI returned an invalid video package.")
 ident=str(uuid.uuid4()); created=now()
 with conn() as c:
  c.execute("INSERT INTO yt_drafts(id,title,description,script,topic,status,privacy,created) VALUES(?,?,?,?,?,'script_ready',?,?)",(ident,str(package["title"])[:100],str(package["description"])[:5000],str(package["script"])[:30000],req.topic,req.privacy,created))
 await send_telegram_message("AgentForge: a new YouTube script draft is ready for review: "+str(package["title"])[:180])
 return {"id":ident,"title":package["title"],"description":package["description"],"script":package["script"],"status":"script_ready","message":"Script package created. A rendered video is still required before approval and upload."}


def voice_config():
 return (cfg("elevenlabs_api_key","ELEVENLABS_API_KEY"),
         cfg("elevenlabs_voice_id","ELEVENLABS_VOICE_ID"),
         cfg("elevenlabs_model","ELEVENLABS_MODEL","eleven_multilingual_v2"))

def _srt_time(seconds:float):
 millis=max(0,int(seconds*1000))
 hours,millis=divmod(millis,3600000)
 minutes,millis=divmod(millis,60000)
 secs,millis=divmod(millis,1000)
 return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def _captions(script:str):
 sentences=[x.strip() for x in re.split(r"(?<=[.!?])\s+",script) if x.strip()]
 if not sentences: sentences=[script.strip()]
 total_words=sum(max(1,len(x.split())) for x in sentences)
 duration=max(8.0,total_words/2.35)
 cursor=0.0; parts=[]
 for index,sentence in enumerate(sentences):
  span=duration*max(1,len(sentence.split()))/total_words
  parts.append(f"{index+1}\n{_srt_time(cursor)} --> {_srt_time(cursor+span)}\n{sentence}\n")
  cursor+=span
 return "\n".join(parts)

@router.post("/drafts/{draft_id}/voice")
async def generate_voice(draft_id:str):
 with conn() as c: row=c.execute("SELECT * FROM yt_drafts WHERE id=?",(draft_id,)).fetchone()
 if not row: raise HTTPException(404,"Draft not found.")
 voice_key,voice_id,voice_model=voice_config()
 if not voice_key or not voice_id: raise HTTPException(409,"Add ElevenLabs API key and voice ID in Connect API first.")
 try:
  async with httpx.AsyncClient(timeout=180) as h:
   response=await h.post("https://api.elevenlabs.io/v1/text-to-speech/"+urllib.parse.quote(voice_id,safe=""),
    headers={"xi-api-key":voice_key,"Accept":"audio/mpeg","Content-Type":"application/json"},
    json={"text":row["script"][:12000],"model_id":voice_model,"voice_settings":{"stability":0.48,"similarity_boost":0.72}})
  if response.status_code>=400: raise HTTPException(502,"ElevenLabs rejected the narration request. Check voice access and account limits.")
  audio=response.content
  if len(audio)<1000 or not (audio.startswith(b"ID3") or audio[:1]==b"\xff"):
   raise HTTPException(502,"Voice provider did not return valid MP3 audio.")
  if len(audio)>30_000_000: raise HTTPException(502,"Generated narration exceeded the 30 MB safety limit.")
 except httpx.RequestError:
  raise HTTPException(502,"Could not reach the voice provider.")
 VIDEO_DIR.mkdir(parents=True,exist_ok=True)
 voice_path=VIDEO_DIR/(draft_id+".mp3")
 caption_path=VIDEO_DIR/(draft_id+".srt")
 voice_path.write_bytes(audio)
 caption_path.write_text(_captions(row["script"]),encoding="utf-8")
 with conn() as c:
  c.execute("UPDATE yt_drafts SET voice_path=?,captions_path=? WHERE id=?",(str(voice_path),str(caption_path),draft_id))
 await send_telegram_message("AgentForge: AI narration is ready for YouTube draft "+row["title"][:160])
 return {"id":draft_id,"voice_ready":True,"captions_ready":True,"audio_bytes":len(audio),
         "message":"Narration and draft SRT captions created. Caption timing is estimated; review before publishing."}

@router.get("/drafts/{draft_id}/captions")
def draft_captions(draft_id:str):
 from fastapi.responses import FileResponse
 with conn() as c: row=c.execute("SELECT captions_path FROM yt_drafts WHERE id=?",(draft_id,)).fetchone()
 if not row or not row["captions_path"]: raise HTTPException(404,"Captions are not available.")
 p=Path(row["captions_path"]).resolve()
 if p.parent!=VIDEO_DIR or not p.is_file(): raise HTTPException(404,"Caption file unavailable.")
 return FileResponse(p,media_type="application/x-subrip",filename=draft_id+".srt")

async def save_rendered_video(draft_id:str,output,row):
 url=output[0] if isinstance(output,list) and output else output
 if isinstance(url,dict): url=url.get("url") or url.get("video")
 if not isinstance(url,str): raise HTTPException(502,"Video provider returned an invalid output URL.")
 parsed_output=urllib.parse.urlparse(url)
 if parsed_output.scheme!="https" or not ((parsed_output.hostname or "")=="replicate.delivery" or (parsed_output.hostname or "").endswith(".replicate.delivery")): raise HTTPException(502,"Video provider returned an untrusted output host.")
 VIDEO_DIR.mkdir(parents=True,exist_ok=True)
 path=VIDEO_DIR/(draft_id+".mp4")
 async with httpx.AsyncClient(timeout=240,follow_redirects=True) as h:
  video=await h.get(url)
 if video.status_code>=400 or b"ftyp" not in video.content[:64]: raise HTTPException(502,"Provider output was not a valid MP4 video.")
 if len(video.content)>500_000_000: raise HTTPException(502,"Rendered video exceeded the 500 MB safety limit.")
 path.write_bytes(video.content)
 if row["voice_path"]:
  if not Path(row["voice_path"]).is_file(): raise HTTPException(502,"The saved narration file is missing; regenerate the voice track.")
  if not shutil.which("ffmpeg"): raise HTTPException(503,"FFmpeg is required to combine narration with the generated video.")
  muxed=VIDEO_DIR/(draft_id+".mux.mp4")
  try:
   result=subprocess.run(["ffmpeg","-y","-i",str(path),"-i",row["voice_path"],"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",str(muxed)],capture_output=True,text=True,timeout=240)
   if result.returncode!=0 or not muxed.is_file(): raise HTTPException(502,"FFmpeg could not combine the narration and video. Check the generated media files.")
   os.replace(muxed,path)
  except subprocess.TimeoutExpired:
   raise HTTPException(504,"Video and narration processing timed out.")
 with conn() as c:
  c.execute("UPDATE yt_drafts SET video_path=?,status='ready_for_approval',render_prediction_url=NULL,error=NULL WHERE id=?",(str(path),draft_id))
 await send_telegram_message("AgentForge: rendered video is ready for your approval: "+row["title"][:160])
 return {"id":draft_id,"status":"ready_for_approval","bytes":path.stat().st_size,"has_voice":bool(row["voice_path"])}

@router.post("/drafts/{draft_id}/render")
async def render_draft(draft_id:str):
 video_key,video_model,video_provider=video_config()
 if video_provider!="replicate" or not (video_key and video_model): raise HTTPException(503,"Open Connect API and configure Replicate video credentials.")
 if "/" not in video_model: raise HTTPException(503,"Replicate model slug must use owner/model format.")
 with conn() as c:
  row=c.execute("SELECT * FROM yt_drafts WHERE id=?",(draft_id,)).fetchone()
  if not row: raise HTTPException(404,"Draft not found.")
  changed=c.execute("UPDATE yt_drafts SET status='rendering',error=NULL WHERE id=? AND status IN ('script_ready','render_failed')",(draft_id,))
  if changed.rowcount!=1: raise HTTPException(409,"This draft is not available to start a new render.")
 try:
  async with httpx.AsyncClient(timeout=75) as h:
   response=await h.post("https://api.replicate.com/v1/models/"+video_model+"/predictions",
    headers={"Authorization":"Bearer "+video_key,"Prefer":"wait=60","Content-Type":"application/json"},
    json={"input":{"prompt":row["script"]}})
  if response.status_code>=400: raise HTTPException(502,"Video provider rejected the render request. Check model input schema and account limits.")
  prediction=response.json()
  if prediction.get("status")=="succeeded" and prediction.get("output"):
   return await save_rendered_video(draft_id,prediction["output"],row)
  prediction_url=prediction.get("urls",{}).get("get")
  if not prediction_url: raise HTTPException(502,"Video provider did not return a prediction status URL.")
  with conn() as c: c.execute("UPDATE yt_drafts SET render_prediction_url=? WHERE id=?",(prediction_url,draft_id))
  return {"id":draft_id,"status":"rendering","message":"Video rendering has started. Use Check render status to retrieve the finished video."}
 except HTTPException as exc:
  with conn() as c: c.execute("UPDATE yt_drafts SET status='render_failed',error=? WHERE id=?",(str(exc.detail)[:500],draft_id))
  raise
 except httpx.RequestError:
  with conn() as c: c.execute("UPDATE yt_drafts SET status='render_failed',error='Video provider request failed.' WHERE id=?",(draft_id,))
  raise HTTPException(502,"Could not reach the video provider.")

@router.get("/drafts/{draft_id}/render-status")
async def render_status(draft_id:str):
 video_key,video_model,video_provider=video_config()
 if not video_key: raise HTTPException(503,"Configure Replicate in Connect API.")
 with conn() as c: row=c.execute("SELECT * FROM yt_drafts WHERE id=?",(draft_id,)).fetchone()
 if not row: raise HTTPException(404,"Draft not found.")
 if row["status"]!="rendering" or not row["render_prediction_url"]:
  return {"id":draft_id,"status":row["status"],"has_video":bool(row["video_path"])}
 parsed_prediction=urllib.parse.urlparse(row["render_prediction_url"])
 if parsed_prediction.scheme!="https" or parsed_prediction.hostname!="api.replicate.com": raise HTTPException(502,"Saved render status URL is not a trusted Replicate endpoint.")
 try:
  async with httpx.AsyncClient(timeout=45) as h:
   response=await h.get(row["render_prediction_url"],headers={"Authorization":"Bearer "+video_key})
  if response.status_code>=400: raise HTTPException(502,"Could not retrieve the video render status.")
  prediction=response.json()
  if prediction.get("status") in ("starting","processing"):
   return {"id":draft_id,"status":"rendering","message":"Video is still rendering. Check again shortly."}
  if prediction.get("status")!="succeeded" or not prediction.get("output"):
   with conn() as c: c.execute("UPDATE yt_drafts SET status='render_failed',error='Video provider reported a failed render.',render_prediction_url=NULL WHERE id=?",(draft_id,))
   await send_telegram_message("AgentForge: video rendering failed for draft "+row["title"][:160])
   return {"id":draft_id,"status":"render_failed","message":"Video provider reported a failed render. Review the model settings and try a new draft."}
  return await save_rendered_video(draft_id,prediction["output"],row)
 except HTTPException as exc:
  if exc.status_code>=500:
   with conn() as c: c.execute("UPDATE yt_drafts SET status='render_failed',error=? WHERE id=? AND status='rendering'",(str(exc.detail)[:500],draft_id))
  raise
 except httpx.RequestError:
  raise HTTPException(502,"Could not reach the video provider to check render status.")

@router.get("/drafts")
def drafts():
 with conn() as c:
  records=c.execute("SELECT id,title,description,script,topic,status,privacy,created,published_url,published_at,error,video_path,voice_path,captions_path FROM yt_drafts ORDER BY created DESC LIMIT 100").fetchall()
 return [{**{k:r[k] for k in r.keys() if k not in ("video_path","voice_path","captions_path")},
          "has_video":bool(r["video_path"]),"has_voice":bool(r["voice_path"]),
          "has_captions":bool(r["captions_path"])} for r in records]

@router.get("/drafts/{draft_id}/voice")
def draft_voice(draft_id:str):
 from fastapi.responses import FileResponse
 with conn() as c: row=c.execute("SELECT voice_path FROM yt_drafts WHERE id=?",(draft_id,)).fetchone()
 if not row or not row["voice_path"]: raise HTTPException(404,"Narration is not available.")
 p=Path(row["voice_path"]).resolve()
 if p.parent!=VIDEO_DIR or not p.is_file(): raise HTTPException(404,"Narration file unavailable.")
 return FileResponse(p,media_type="audio/mpeg",filename=draft_id+".mp3")
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
 if row["status"]!="ready_for_approval" or not row["video_path"] or not Path(row["video_path"]).is_file():
  raise HTTPException(409,"Only a fully rendered video awaiting approval can be uploaded.")
 tok=await access_token()
 metadata={"snippet":{"title":row["title"][:100],"description":row["description"]+"\n\n"+row["script"][:3500],"categoryId":"28"},"status":{"privacyStatus":req.privacy,"selfDeclaredMadeForKids":False}}
 with conn() as c:
  changed=c.execute("UPDATE yt_drafts SET status='uploading',error=NULL WHERE id=? AND status='ready_for_approval'",(draft_id,))
  if changed.rowcount!=1: raise HTTPException(409,"This draft is already being uploaded or has already been processed.")
 try:
  async with httpx.AsyncClient(timeout=60) as h:
   init=await h.post("https://www.googleapis.com/upload/youtube/v3/videos",params={"uploadType":"resumable","part":"snippet,status"},headers={"Authorization":"Bearer "+tok,"Content-Type":"application/json; charset=UTF-8","X-Upload-Content-Type":"video/mp4"},json=metadata)
  if init.status_code>=400:
   with conn() as c: c.execute("UPDATE yt_drafts SET status='ready_for_approval',error='YouTube rejected upload initialization.' WHERE id=? AND status='uploading'",(draft_id,))
   raise HTTPException(502,"YouTube could not start the upload. Check channel verification, API quota and upload permissions.")
  upload_url=init.headers.get("Location")
  if not upload_url:
   with conn() as c: c.execute("UPDATE yt_drafts SET status='ready_for_approval',error='YouTube did not return an upload session.' WHERE id=? AND status='uploading'",(draft_id,))
   raise HTTPException(502,"YouTube did not provide an upload session.")
  file=Path(row["video_path"])
  async with httpx.AsyncClient(timeout=600) as h:
   upload=await h.put(upload_url,content=file.read_bytes(),headers={"Content-Type":"video/mp4","Content-Length":str(file.stat().st_size)})
  if upload.status_code not in (200,201):
   with conn() as c: c.execute("UPDATE yt_drafts SET status='upload_unknown',error='Upload response was inconclusive; verify the channel before retrying.' WHERE id=? AND status='uploading'",(draft_id,))
   raise HTTPException(502,"YouTube upload outcome is uncertain. Check YouTube Studio before attempting another upload; AgentForge has blocked automatic retries to prevent duplicates.")
  video_id=upload.json()["id"]; link="https://www.youtube.com/watch?v="+video_id
  with conn() as c:
   c.execute("UPDATE yt_drafts SET status='published',privacy=?,published_url=?,published_at=?,error=NULL WHERE id=? AND status='uploading'",(req.privacy,link,now(),draft_id))
  await send_telegram_message("AgentForge: approved YouTube video published: "+link)
  return {"status":"published","video_id":video_id,"url":link,"privacy":req.privacy}
 except httpx.RequestError:
  with conn() as c: c.execute("UPDATE yt_drafts SET status='upload_unknown',error='Network failure during upload; verify YouTube Studio before retrying.' WHERE id=? AND status='uploading'",(draft_id,))
  raise HTTPException(502,"Upload outcome is uncertain after a network failure. Check YouTube Studio before retrying to prevent duplicate uploads.")

"""AgentForge API.

Real work is only reported after a configured model/provider returns a result.
External side effects (sending messages, publishing, live trades) are not enabled
by this starter API; integrations must be added with explicit user approval.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

DB_PATH = Path(os.getenv("DATABASE_PATH", "./agentforge.db"))
AI_BASE_URL = os.getenv("AI_BASE_URL", "").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "")
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]

AGENT_TYPES = {
    "support": ("Customer Support", "Resolve customer questions using supplied knowledge. Never invent policy, refunds, order status, or account facts. Escalate uncertainty."),
    "sales": ("Sales Assistant", "Research and qualify prospects from user-provided or authorized sources. Draft personalized outreach only; never send without approval."),
    "content": ("Content Studio", "Research a topic from supplied sources, propose original short-form scripts, captions, and shot lists. Do not claim a post was published."),
    "automation": ("Workflow Assistant", "Turn a requested workflow into a clear, reviewable plan. Do not execute external side effects or access credentials."),
    "research": ("Research Analyst", "Analyze supplied material, distinguish facts from assumptions, cite supplied URLs when present, and state limitations."),
}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with connect_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, agent_type TEXT NOT NULL, title TEXT NOT NULL,
            prompt TEXT NOT NULL, status TEXT NOT NULL, result TEXT,
            error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS paper_trades (
            id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
            quantity REAL NOT NULL, entry_price REAL NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL
        )""")

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="AgentForge API",
    version="0.1.0",
    description="API for AI workspaces, task execution and paper-trading experiments.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

class TaskCreate(BaseModel):
    agent_type: Literal["support", "sales", "content", "automation", "research"]
    title: str = Field(min_length=2, max_length=120)
    prompt: str = Field(min_length=3, max_length=12000)

class TaskOut(BaseModel):
    id: str
    agent_type: str
    title: str
    prompt: str
    status: str
    result: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str

class PaperTradeCreate(BaseModel):
    symbol: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9._-]+$")
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, le=1_000_000)
    reference_price: float = Field(gt=0, le=100_000_000, description="User-supplied simulated price; not a live quote.")

async def run_model(agent_type: str, prompt: str) -> str:
    if not (AI_BASE_URL and AI_API_KEY and AI_MODEL):
        raise HTTPException(
            status_code=503,
            detail="AI provider is not configured. Add AI_BASE_URL, AI_API_KEY and AI_MODEL to backend/.env.",
        )
    label, instructions = AGENT_TYPES[agent_type]
    payload = {
        "model": AI_MODEL,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": f"You are {label} for AgentForge. {instructions} Be concise, practical, and transparent."},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"AI provider returned HTTP {exc.response.status_code}.") from exc
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="AI provider request failed or returned an invalid response.") from exc

@app.get("/health")
async def health():
    return {"status": "ok", "service": "agentforge-api", "time": now_iso(), "ai_configured": bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)}

@app.get("/api/v1/agents")
async def list_agents():
    return [{"id": key, "name": value[0], "description": value[1]} for key, value in AGENT_TYPES.items()]

@app.post("/api/v1/tasks", response_model=TaskOut)
async def create_task(payload: TaskCreate):
    task_id = str(uuid.uuid4())
    created = now_iso()
    with connect_db() as db:
        db.execute(
            "INSERT INTO tasks (id, agent_type, title, prompt, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, payload.agent_type, payload.title, payload.prompt, "running", created, created),
        )
    try:
        result = await run_model(payload.agent_type, payload.prompt)
        status, error = "completed", None
    except HTTPException as exc:
        result, status, error = None, "failed", str(exc.detail)
        with connect_db() as db:
            db.execute("UPDATE tasks SET status=?, error=?, updated_at=? WHERE id=?", (status, error, now_iso(), task_id))
        raise
    with connect_db() as db:
        db.execute("UPDATE tasks SET status=?, result=?, updated_at=? WHERE id=?", (status, result, now_iso(), task_id))
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return dict(row)

@app.get("/api/v1/tasks", response_model=list[TaskOut])
async def list_tasks(limit: int = 50):
    limit = max(1, min(limit, 100))
    with connect_db() as db:
        rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]

@app.get("/api/v1/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str):
    with connect_db() as db:
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found.")
    return dict(row)

@app.get("/api/v1/trading/paper/positions")
async def paper_positions():
    with connect_db() as db:
        rows = db.execute("SELECT * FROM paper_trades ORDER BY created_at DESC LIMIT 100").fetchall()
    return {"mode": "paper", "live_trading_enabled": False, "positions": [dict(row) for row in rows]}

@app.post("/api/v1/trading/paper/trades")
async def create_paper_trade(payload: PaperTradeCreate):
    """Record a simulated trade using a user-supplied reference price only."""
    trade_id = str(uuid.uuid4())
    created = now_iso()
    with connect_db() as db:
        db.execute(
            "INSERT INTO paper_trades (id, symbol, side, quantity, entry_price, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trade_id, payload.symbol.upper(), payload.side, payload.quantity, payload.reference_price, "simulated", created),
        )
    return {
        "id": trade_id, "symbol": payload.symbol.upper(), "side": payload.side,
        "quantity": payload.quantity, "reference_price": payload.reference_price,
        "status": "simulated", "mode": "paper", "created_at": created,
        "notice": "Simulation only. No broker was contacted and no real order was placed.",
    }

@app.get("/api/v1/trading")
async def trading_status():
    return {
        "product": "Omonux Trading",
        "mode": "paper_only",
        "live_trading_enabled": False,
        "message": "Research, watchlists and paper trading can be developed here. Live execution requires separate broker integration, explicit authorization, risk limits and compliance review.",
    }

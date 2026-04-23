from pathlib import Path
import json
import logging
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from src.config import settings
from src.indexing.vector_store import LocalVectorStore
from src.rag.llm import LLMClient
from src.rag.pipeline import RagPipeline
from src.rag.retriever import Retriever
import src.db as db

logger = logging.getLogger("faa_ai")

app = FastAPI(title="AirWise — Aviation Regulations", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    top_k: int | None = None


class CompliancePlanRequest(BaseModel):
    renovation_request: str
    tcds_text: str
    governing_body_hint: str | None = None
    session_id: str | None = None


store = LocalVectorStore(settings.index_dir)


def ensure_index_loaded() -> None:
    if store.embeddings is not None:
        return
    store.load()


@app.on_event("startup")
async def startup() -> None:
    try:
        store.load()
    except Exception:
        pass
    try:
        await db.get_pool()
    except Exception:
        logger.warning("Could not connect to database on startup — will retry on first request.")


@app.on_event("shutdown")
async def shutdown() -> None:
    await db.close_pool()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Session endpoints ──────────────────────────────────────────────────────────

@app.post("/sessions")
async def create_session() -> dict:
    try:
        session_id = await db.create_session()
        return {"session_id": session_id}
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/sessions/{session_id}/history")
async def get_history(session_id: str) -> dict:
    try:
        if not await db.session_exists(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        messages = await db.get_history(session_id, limit=50)
        return {"session_id": session_id, "messages": messages}
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


# ── Chat endpoint ──────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(payload: ChatRequest) -> dict:
    logger.info("QUESTION: %s", payload.question)
    try:
        ensure_index_loaded()

        # Resolve or create session
        session_id = payload.session_id
        if session_id:
            if not await db.session_exists(session_id):
                session_id = await db.create_session()
        else:
            session_id = await db.create_session()

        # Load conversation history for follow-up context (last 6 turns = 3 exchanges)
        history = await db.get_history(session_id, limit=6)
        # Pass only role+content to LLM (strip DB metadata)
        llm_history = [{"role": m["role"], "content": m["content"]} for m in history]

        retriever = Retriever(store)
        llm = LLMClient()
        pipeline = RagPipeline(retriever, llm)
        result = await pipeline.answer_async(payload.question, history=llm_history)

        # Persist both turns
        await db.save_message(session_id, "user", payload.question)
        await db.save_message(
            session_id,
            "assistant",
            result.answer,
            citations=result.citations,
            confidence=result.confidence,
        )

        return {
            "answer": result.answer,
            "citations": result.citations,
            "confidence": result.confidence,
            "grounded": result.grounded,
            "session_id": session_id,
            "error": None,
        }
    except Exception as exc:
        traceback.print_exc()
        return {
            "answer": "The model request failed. Please try again.",
            "citations": [],
            "confidence": 0.0,
            "grounded": False,
            "session_id": payload.session_id,
            "error": str(exc),
        }


@app.post("/chat/stream")
async def chat_stream(payload: ChatRequest):
    try:
        ensure_index_loaded()

        session_id = payload.session_id
        if session_id:
            if not await db.session_exists(session_id):
                session_id = await db.create_session()
        else:
            session_id = await db.create_session()

        history = await db.get_history(session_id, limit=6)
        llm_history = [{"role": m["role"], "content": m["content"]} for m in history]

        retriever = Retriever(store)
        llm = LLMClient()
        pipeline = RagPipeline(retriever, llm)

        async def generate():
            full_text: list[str] = []
            try:
                async for chunk_type, data in pipeline.stream_answer_async(
                    payload.question, history=llm_history
                ):
                    if chunk_type == "text":
                        full_text.append(data)
                        yield f"data: {json.dumps({'type': 'text', 'text': data})}\n\n"
                    elif chunk_type == "done":
                        answer = "".join(full_text)
                        await db.save_message(session_id, "user", payload.question)
                        await db.save_message(
                            session_id, "assistant", answer,
                            citations=data["citations"],
                            confidence=data["confidence"],
                        )
                        event = {
                            "type": "done",
                            "citations": data["citations"],
                            "confidence": data["confidence"],
                            "grounded": data["grounded"],
                            "session_id": session_id,
                        }
                        yield f"data: {json.dumps(event)}\n\n"
                    elif chunk_type == "error":
                        yield f"data: {json.dumps({'type': 'error', 'message': data})}\n\n"
            except Exception as exc:
                traceback.print_exc()
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/compliance-plan")
async def compliance_plan(payload: CompliancePlanRequest) -> dict:
    try:
        ensure_index_loaded()
        retriever = Retriever(store)
        llm = LLMClient()
        pipeline = RagPipeline(retriever, llm)
        result = await pipeline.compliance_plan_async(
            renovation_request=payload.renovation_request,
            tcds_text=payload.tcds_text,
            governing_body_hint=payload.governing_body_hint,
        )
        return {
            "answer": result.answer,
            "citations": result.citations,
            "confidence": result.confidence,
            "grounded": result.grounded,
            "error": None,
        }
    except Exception as exc:
        traceback.print_exc()
        return {
            "answer": "The compliance plan request failed. Please try again.",
            "citations": [],
            "confidence": 0.0,
            "grounded": False,
            "error": str(exc),
        }

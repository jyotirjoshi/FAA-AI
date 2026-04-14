from pathlib import Path
import logging
import traceback

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from src.config import settings
from src.indexing.vector_store import LocalVectorStore
from src.rag.llm import LLMClient
from src.rag.pipeline import RagPipeline
from src.rag.retriever import Retriever

logger = logging.getLogger("faa_ai")

app = FastAPI(title="AirWise — Aviation Regulations", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class ChatRequest(BaseModel):
    question: str
    top_k: int | None = None


class CompliancePlanRequest(BaseModel):
    renovation_request: str
    tcds_text: str
    governing_body_hint: str | None = None


store = LocalVectorStore(settings.index_dir)


def ensure_index_loaded() -> None:
    if store.embeddings is not None:
        return
    store.load()


@app.on_event("startup")
def startup() -> None:
    try:
        store.load()
    except Exception:
        # API can still start; endpoints will retry load and return a clear error if needed.
        pass


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat")
def chat(payload: ChatRequest) -> dict:
    logger.info("QUESTION: %s", payload.question)
    try:
        ensure_index_loaded()
        retriever = Retriever(store)
        llm = LLMClient()
        pipeline = RagPipeline(retriever, llm)
        result = pipeline.answer(payload.question)
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
            "answer": "I cannot answer right now because the model request failed. Check API key/base URL/model settings.",
            "citations": [],
            "confidence": 0.0,
            "grounded": False,
            "error": str(exc),
        }


@app.post("/compliance-plan")
def compliance_plan(payload: CompliancePlanRequest) -> dict:
    try:
        ensure_index_loaded()
        retriever = Retriever(store)
        llm = LLMClient()
        pipeline = RagPipeline(retriever, llm)
        result = pipeline.compliance_plan(
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
            "answer": "I cannot build a compliance plan right now because the model request failed. Check API key/base URL/model settings.",
            "citations": [],
            "confidence": 0.0,
            "grounded": False,
            "error": str(exc),
        }

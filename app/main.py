from dotenv import load_dotenv
load_dotenv()

import os
import logging

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "API is running"}

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity

from app.services import get_rep_explanation
from app.llm import LLM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="IC Compensation Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = LLM()

rag = None
try:
    from rag.pipeline import RAGSystem
    rag = RAGSystem()
    rag.load_or_build()   # <-- YOU MUST IMPLEMENT THIS
    logger.info("RAG ready: %s vectors", rag.total_vectors)
except Exception as e:
    logger.warning("RAG disabled: %s", str(e))


adapter_settings = BotFrameworkAdapterSettings(
    app_id=os.getenv("MICROSOFT_APP_ID"),
    app_password=os.getenv("MICROSOFT_APP_PASSWORD"),
)
adapter = BotFrameworkAdapter(adapter_settings)


class AskRequest(BaseModel):
    query: str
    rep_id: str


class AskResponse(BaseModel):
    text: str
    status: str = "success"


async def handle_teams_message(turn_context: TurnContext):
    try:
        message = turn_context.activity.text

        if not message:
            await turn_context.send_activity("Empty message received.")
            return

        rep_id = (turn_context.activity.channel_data or {}).get("rep_id")

        if not rep_id:
            await turn_context.send_activity(
                "rep_id missing. Configure Teams payload."
            )
            return

        reply = get_rep_explanation(rep_id, message, rag, llm)

        clean = reply.strip()[:2000]
        await turn_context.send_activity(clean)

    except Exception as e:
        logger.error("Teams handler error: %s", str(e), exc_info=True)
        await turn_context.send_activity("Error processing request.")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "rag_enabled": rag is not None,
        "rag_vectors": rag.total_vectors if rag else 0,
    }


@app.post("/api/messages")
async def messages(req: Request):
    try:
        body = await req.json()
        auth_header = req.headers.get("Authorization", "")
        activity = Activity().deserialize(body)

        response = await adapter.process_activity(
            activity,
            auth_header,
            handle_teams_message,
        )
        return response or Response(status_code=201)

    except Exception as e:
        logger.error("Bot endpoint error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Bot failed")


@app.post("/ask", response_model=AskResponse)
def ask(data: AskRequest):
    try:
        if not data.rep_id or not data.query:
            raise HTTPException(status_code=400, detail="rep_id and query required")

        # Delegate intent routing to backend explicit module
        result = get_rep_explanation(data.rep_id, data.query, rag, llm)

        # Clean result (strip excessive whitespace but keep newlines)
        clean = result.strip()

        return AskResponse(text=clean)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ask error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")
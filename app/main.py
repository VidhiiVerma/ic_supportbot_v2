from dotenv import load_dotenv
load_dotenv()

import os
import logging

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

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

# ================= APP =================
app = FastAPI(title="IC Compensation Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= ENV =================
MICROSOFT_APP_ID = os.getenv("MICROSOFT_APP_ID")
MICROSOFT_APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD")
MICROSOFT_APP_TENANT_ID = os.getenv("MICROSOFT_APP_TENANT_ID")

# ================= LLM =================
llm = LLM()

# ================= RAG =================
rag = None
try:
    from rag.pipeline import RAGSystem
    rag = RAGSystem()
    rag.load_or_build()
    logger.info("RAG ready: %s vectors", rag.total_vectors)
except Exception as e:
    logger.warning("RAG disabled: %s", str(e))

# ================= BOT ADAPTER =================
adapter_settings = BotFrameworkAdapterSettings(
    app_id=MICROSOFT_APP_ID,
    app_password=MICROSOFT_APP_PASSWORD,
    channel_auth_tenant=MICROSOFT_APP_TENANT_ID,
    oauth_scope="https://api.botframework.com/.default"   # 🔥 critical fix
)

adapter = BotFrameworkAdapter(adapter_settings)

# ================= REQUEST MODELS =================
class AskRequest(BaseModel):
    query: str
    rep_id: str

class AskResponse(BaseModel):
    text: str
    status: str = "success"

# ================= TEAMS HANDLER =================
async def handle_teams_message(turn_context: TurnContext):
    try:
        message = (turn_context.activity.text or "").strip()

        if not message:
            await turn_context.send_activity("Please send a message.")
            return

        # 🔥 FIXED: use Teams AAD ID (string, not int)
        rep_id = turn_context.activity.from_property.aad_object_id

        if not rep_id:
            await turn_context.send_activity("User ID not found.")
            return

        reply = get_rep_explanation(rep_id, message, rag, llm)

        await turn_context.send_activity(reply.strip()[:2000])

    except Exception as e:
        logger.error("Teams handler error: %s", str(e), exc_info=True)
        await turn_context.send_activity("Error processing your request.")

# ================= ROUTES =================
@app.get("/")
def root():
    return {"message": "IC Compensation Chatbot is running"}

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

        result = get_rep_explanation(data.rep_id, data.query, rag, llm)

        return AskResponse(text=result.strip())

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ask error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")
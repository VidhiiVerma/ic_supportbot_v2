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
from botframework.connector.auth import MicrosoftAppCredentials

import msal

from app.services.router import get_rep_explanation
from app.llm import LLM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ENV
MICROSOFT_APP_ID = os.getenv("MICROSOFT_APP_ID")
MICROSOFT_APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD")
MICROSOFT_APP_TENANT_ID = os.getenv("MICROSOFT_APP_TENANT_ID")

logger.info(f"APP_ID: {MICROSOFT_APP_ID}")
logger.info(f"TENANT: {MICROSOFT_APP_TENANT_ID}")
logger.info(f"PASSWORD LENGTH: {len(MICROSOFT_APP_PASSWORD)}")

# MSAL FIX
def _fixed_get_access_token(self):
    app = msal.ConfidentialClientApplication(
        client_id=MICROSOFT_APP_ID,
        client_credential=MICROSOFT_APP_PASSWORD,
        authority=f"https://login.microsoftonline.com/{MICROSOFT_APP_TENANT_ID}",
    )

    result = app.acquire_token_for_client(
        scopes=["https://api.botframework.com/.default"]
    )

    if "access_token" not in result:
        raise Exception(f"TOKEN FAILED: {result}")

    return result["access_token"]

# Override SDK broken method
MicrosoftAppCredentials.get_access_token = _fixed_get_access_token

# APP
app = FastAPI(title="IC Compensation Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ADAPTER
adapter_settings = BotFrameworkAdapterSettings(
    app_id=MICROSOFT_APP_ID,
    app_password=MICROSOFT_APP_PASSWORD,
    channel_auth_tenant=MICROSOFT_APP_TENANT_ID,
)

adapter = BotFrameworkAdapter(adapter_settings)

# LLM
llm = LLM()

# RAG
rag = None
try:
    from rag.pipeline import RAGSystem
    rag = RAGSystem()
    rag.load_or_build()
    logger.info(f"RAG ready: {rag.total_vectors} vectors")
except Exception as e:
    logger.warning(f"RAG disabled: {str(e)}")

# MODELS
class AskRequest(BaseModel):
    query: str
    rep_id: str

class AskResponse(BaseModel):
    text: str
    status: str = "success"

# TEAMS HANDLER
async def handle_teams_message(turn_context: TurnContext):
    try:
        message = (turn_context.activity.text or "").strip()

        if not message:
            await turn_context.send_activity("Send a message.")
            return

        # HARDCODED FOR TESTING
        rep_id = "1150"

        reply = get_rep_explanation(rep_id, message, rag, llm)

        await turn_context.send_activity(reply[:2000])

    except Exception as e:
        logger.error("Teams error", exc_info=True)
        await turn_context.send_activity("Error occurred.")

# ROUTES
@app.get("/")
def root():
    return {"message": "API running"}

@app.get("/health")
def health():
    return {"status": "ok"}

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
        logger.error("Bot error", exc_info=True)
        raise HTTPException(status_code=500, detail="Bot failed")

@app.post("/ask", response_model=AskResponse)
def ask(data: AskRequest):
    try:
        result = get_rep_explanation(data.rep_id, data.query, rag, llm)
        return AskResponse(text=result.strip())
    except Exception as e:
        logger.error("Ask error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")
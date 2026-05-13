from dotenv import load_dotenv
load_dotenv()

import os
import re
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
from botbuilder.schema import Activity, ActivityTypes, TextFormatTypes
from botframework.connector.auth import MicrosoftAppCredentials

import msal

from app.services.router import get_rep_explanation
from app.llm import LLM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ENV 

MICROSOFT_APP_ID       = os.getenv("MICROSOFT_APP_ID")
MICROSOFT_APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD")
MICROSOFT_APP_TENANT_ID = os.getenv("MICROSOFT_APP_TENANT_ID")

logger.info("Microsoft credentials loaded successfully")

# MSAL

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

#  ADAPTER 

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
    query:   str
    rep_id:  str
    user_id: str = "api-user"   
class AskResponse(BaseModel):
    text:   str
    status: str = "success"

# HELPERS

def _strip_html(text: str) -> str:
    """Strip HTML tags and decode common entities that Teams injects."""
    if not text:
        return ""
    # Remove HTML tags
    clean_text = re.sub(r'<[^>]+>', '', text)
    # Decode common entities
    clean_text = clean_text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return clean_text.strip()

#  TEAMS HANDLER 

async def handle_teams_message(turn_context: TurnContext):
    try:
        logger.info("===== NEW TEAMS MESSAGE =====")
        user_name = turn_context.activity.from_property.name   
        user_id   = turn_context.activity.from_property.id    

        message = _strip_html(turn_context.activity.text or "")

        logger.info(f"User Name : {user_name}")
        logger.info(f"User ID   : {user_id}")
        logger.info(f"Message   : {message}")

        if not message:
            await turn_context.send_activity("Send a message.")
            return

        rep_id = "1150"

        logger.info(f"Rep ID    : {rep_id}")
        logger.info("Calling get_rep_explanation")

        reply = get_rep_explanation(
            rep_id=rep_id,
            question=message,
            rag=rag,
            llm=llm,
            user_id=user_id,      
            rep_name=user_name,   
        )

        logger.info(f"Bot Reply : {reply}")

        # Explicitly send as plain text to avoid <div> injection in Teams UI
        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.message,
                text=reply,
                text_format=TextFormatTypes.plain
            )
        )

        logger.info("Response sent successfully")

    except Exception as e:
        logger.error("Teams error", exc_info=True)
        await turn_context.send_activity("An error occurred. Please try again.")


@app.get("/")
def root():
    return {"message": "API running"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/messages")
async def messages(req: Request):
    try:
        body        = await req.json()
        auth_header = req.headers.get("Authorization", "")
        activity    = Activity().deserialize(body)

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
    """
    REST endpoint for testing outside Teams.
    Pass a stable user_id so conversation memory works across calls.

    Example:
        curl -X POST /ask -d '{"query":"what is my payout","rep_id":"1150","user_id":"test-alex"}'
        curl -X POST /ask -d '{"query":"why?","rep_id":"1150","user_id":"test-alex"}'
        # Second call will correctly resolve "why?" from the first call's context.
    """
    try:
        result = get_rep_explanation(
            rep_id=data.rep_id,
            question=data.query,
            rag=rag,
            llm=llm,
            user_id=data.user_id,   
            rep_name=data.user_id,    
        )
        return AskResponse(text=result.strip())

    except Exception as e:
        logger.error("Ask error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")

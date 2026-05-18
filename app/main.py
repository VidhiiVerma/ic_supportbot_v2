from dotenv import load_dotenv
load_dotenv()

import os
import re
import logging
import asyncio
import time
from contextlib import asynccontextmanager

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

# MSAL Cache Singleton & Thread Pool
from concurrent.futures import ThreadPoolExecutor

sync_executor = ThreadPoolExecutor(max_workers=20)

class TeamsAuthCache:
    def __init__(self):
        self._app = None
    
    @property
    def app(self):
        if self._app is None:
            if not MICROSOFT_APP_ID or not MICROSOFT_APP_PASSWORD or not MICROSOFT_APP_TENANT_ID:
                logger.warning("Microsoft app credentials or tenant ID missing. TeamsAuthCache will run in mock/local mode.")
                return None
            self._app = msal.ConfidentialClientApplication(
                client_id=MICROSOFT_APP_ID,
                client_credential=MICROSOFT_APP_PASSWORD,
                authority=f"https://login.microsoftonline.com/{MICROSOFT_APP_TENANT_ID}",
            )
        return self._app
    
    def get_access_token(self):
        app = self.app
        if app is None:
            logger.warning("get_access_token called but MSAL is unconfigured. Returning mock token.")
            return "mock-access-token"
        # ConfidentialClientApplication handles internal memory caching by default.
        # Reusing the application instance ensures we hit the cache.
        result = app.acquire_token_for_client(
            scopes=["https://api.botframework.com/.default"]
        )
        if "access_token" not in result:
            raise Exception(f"TOKEN FAILED: {result}")
        return result["access_token"]

auth_cache = TeamsAuthCache()

def _fixed_get_access_token(self):
    return auth_cache.get_access_token()

MicrosoftAppCredentials.get_access_token = _fixed_get_access_token

# APP STATE & LIFESPAN

rag = None
rag_status = "uninitialized"

async def keep_databricks_warm():
    """Background task to keep Databricks warehouse warm by querying it every 5 minutes."""
    from app.db import fetch_df
    while True:
        try:
            logger.info("Sending keep-alive ping to Databricks...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(sync_executor, fetch_df, "SELECT 1")
            logger.info("Databricks keep-alive successful.")
        except Exception as e:
            logger.warning(f"Databricks keep-alive failed: {e}")
        await asyncio.sleep(300) # Sleep for 5 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag, rag_status
    rag_status = "initializing"
    logger.info("Starting background RAG initialization...")
    
    def init_rag():
        try:
            from rag.pipeline import RAGSystem
            r = RAGSystem()
            r.load_or_build()
            return r, "ready"
        except Exception as e:
            logger.warning(f"RAG disabled: {str(e)}")
            return None, f"error: {str(e)}"

    # Run the heavy RAG building in a background thread so it doesn't block startup
    task = asyncio.create_task(asyncio.to_thread(init_rag))
    
    def _on_rag_done(t):
        global rag, rag_status
        try:
            rag, rag_status = t.result()
            logger.info(f"RAG background task completed. Status: {rag_status}")
        except Exception as e:
            rag_status = f"error: {str(e)}"
            logger.error(f"RAG background task failed: {e}")
            
    task.add_done_callback(_on_rag_done)
    
    # Start background warm-up keep-alive loop
    keepalive_task = asyncio.create_task(keep_databricks_warm())
    
    yield
    
    # Clean up keepalive task on shutdown
    keepalive_task.cancel()
    try:
        await keepalive_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="IC Compensation Chatbot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"Incoming Request: {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"Response: {response.status_code} | Time: {process_time:.4f}s")
        return response
    except Exception as e:
        logger.error(f"Unhandled Exception in Request: {e}", exc_info=True)
        raise

@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "pong"}

#  ADAPTER 

adapter_settings = BotFrameworkAdapterSettings(
    app_id=MICROSOFT_APP_ID,
    app_password=MICROSOFT_APP_PASSWORD,
    channel_auth_tenant=MICROSOFT_APP_TENANT_ID,
)
adapter = BotFrameworkAdapter(adapter_settings)

# LLM 

llm = LLM()

# RAG is now initialized asynchronously in the lifespan context manager

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
    # Decode common entities FIRST
    clean_text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    # THEN Remove HTML tags
    clean_text = re.sub(r'<[^>]+>', '', clean_text)
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

        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(
            sync_executor,
            get_rep_explanation,
            rep_id,
            message,
            rag,
            llm,
            user_id,
            user_name,
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
    return {"status": "ok", "rag_status": rag_status}

@app.post("/api/messages")
async def messages(req: Request):
    try:
        body_bytes  = await req.body()
        logger.info(f"Raw Teams Payload: {body_bytes.decode('utf-8')}")
        
        body        = await req.json()
        auth_header = req.headers.get("Authorization", "")
        
        logger.info(f"Auth Header Present: {bool(auth_header)}")
        
        activity    = Activity().deserialize(body)

        response = await adapter.process_activity(
            activity,
            auth_header,
            handle_teams_message,
        )

        return response or Response(status_code=201)

    except Exception as e:
        logger.error(f"Bot Framework Adapter Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Bot adapter failed to process activity")


@app.post("/ask", response_model=AskResponse)
async def ask(data: AskRequest):
    """
    REST endpoint for testing outside Teams.
    Pass a stable user_id so conversation memory works across calls.

    Example:
        curl -X POST /ask -d '{"query":"what is my payout","rep_id":"1150","user_id":"test-alex"}'
        curl -X POST /ask -d '{"query":"why?","rep_id":"1150","user_id":"test-alex"}'
        # Second call will correctly resolve "why?" from the first call's context.
    """
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            sync_executor,
            get_rep_explanation,
            data.rep_id,
            data.query,
            rag,
            llm,
            data.user_id,
            data.user_id,
        )
        return AskResponse(text=result.strip())

    except Exception as e:
        logger.error("Ask error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")

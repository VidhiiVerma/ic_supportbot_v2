from dotenv import load_dotenv
load_dotenv()

import os
import re
import logging
import asyncio
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)

from botbuilder.core.teams import TeamsInfo

from botbuilder.schema import (
    Activity,
    ActivityTypes,
    TextFormatTypes,
    Attachment,
)

from botframework.connector.auth import MicrosoftAppCredentials

import msal

from app.services.router import get_rep_explanation
from app.llm import LLM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

QUICK_REPLY_QUESTIONS = [
    "Show my IC payout for this quarter.",
    "Explain my eligibility for the current period.",
    "Show my credits by product.",
    "Share my current IC plan document.",
]

MICROSOFT_APP_ID        = os.getenv("MICROSOFT_APP_ID")
MICROSOFT_APP_PASSWORD  = os.getenv("MICROSOFT_APP_PASSWORD")
MICROSOFT_APP_TENANT_ID = os.getenv("MICROSOFT_APP_TENANT_ID")

logger.info("Microsoft credentials loaded successfully")

sync_executor = ThreadPoolExecutor(max_workers=10)

_email_cache: dict = {}


# ---------------- MSAL AUTH ---------------- #

class TeamsAuthCache:

    def __init__(self):
        self._app = None

    @property
    def app(self):
        if self._app is None:
            if (
                not MICROSOFT_APP_ID
                or not MICROSOFT_APP_PASSWORD
                or not MICROSOFT_APP_TENANT_ID
            ):
                logger.warning("Microsoft credentials missing. Running in mock mode.")
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
            logger.warning("MSAL not configured.")
            return "mock-access-token"

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

rag        = None
rag_status = "uninitialized"


# ---------------- KEEP-ALIVE ---------------- #

async def keep_databricks_warm():
    from app.db import fetch_df

    while True:
        try:
            logger.info("Sending keep-alive ping to Databricks...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(sync_executor, fetch_df, "SELECT 1")
            logger.info("Databricks keep-alive successful.")

        except Exception as e:
            logger.warning(f"Databricks keep-alive failed: {e}")

        # 8 minutes — set your Databricks warehouse Auto Stop to 10+ minutes
        await asyncio.sleep(8 * 60)


# ---------------- LIFESPAN ---------------- #

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

    task = asyncio.create_task(asyncio.to_thread(init_rag))

    def on_rag_done(t):
        global rag, rag_status
        try:
            rag, rag_status = t.result()
            logger.info(f"RAG background task completed. Status: {rag_status}")
        except Exception as e:
            rag_status = f"error: {str(e)}"
            logger.error(f"RAG background task failed: {e}")

    task.add_done_callback(on_rag_done)

    keepalive_task = asyncio.create_task(keep_databricks_warm())

    yield

    keepalive_task.cancel()
    try:
        await keepalive_task
    except asyncio.CancelledError:
        pass


# ---------------- APP ---------------- #

app = FastAPI(
    title="IC Compensation Chatbot",
    lifespan=lifespan,
)

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
        response     = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"Response: {response.status_code} | Time: {process_time:.4f}s")
        return response

    except Exception as e:
        logger.error(f"Unhandled Exception in Request: {e}", exc_info=True)
        raise


@app.get("/")
def root():
    return {"message": "API running"}


@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "pong"}


@app.get("/health")
def health():
    return {"status": "ok", "rag_status": rag_status}


# ---------------- BOT ADAPTER ---------------- #

adapter_settings = BotFrameworkAdapterSettings(
    app_id=MICROSOFT_APP_ID,
    app_password=MICROSOFT_APP_PASSWORD,
    channel_auth_tenant=MICROSOFT_APP_TENANT_ID,
)

adapter = BotFrameworkAdapter(adapter_settings)
llm     = LLM()


# ---------------- REQUEST / RESPONSE MODELS ---------------- #

class AskRequest(BaseModel):
    query:   str
    rep_id:  str
    user_id: str = "api-user"


class AskResponse(BaseModel):
    text:   str
    status: str = "success"


# ---------------- HELPERS ---------------- #

def _strip_html(text: str) -> str:
    if not text:
        return ""

    clean_text = (
        text.replace("&nbsp;", " ")
            .replace("&lt;",   "<")
            .replace("&gt;",   ">")
            .replace("&amp;",  "&")
            .replace("&quot;", '"')
            .replace("&#39;",  "'")
    )

    clean_text = re.sub(r"</?[a-zA-Z][^>]*>", "", clean_text)
    return clean_text.strip()


# ---------------- TEAMS HANDLER ---------------- #

async def handle_teams_message(turn_context: TurnContext):
    try:
        logger.info("NEW TEAMS MESSAGE")

        user_name = turn_context.activity.from_property.name
        user_id   = turn_context.activity.from_property.id

        # Resolve email (cached)
        if user_id not in _email_cache:
            member = await TeamsInfo.get_member(turn_context, user_id)
            _email_cache[user_id] = member.email
            logger.info(f"Email fetched and cached for user {user_id}: {member.email}")
        else:
            logger.info(f"Email cache HIT for user {user_id}")

        email   = _email_cache[user_id]
        message = _strip_html(turn_context.activity.text or "")

        logger.info(f"User Name : {user_name}")
        logger.info(f"User ID   : {user_id}")
        logger.info(f"User Email: {email}")
        logger.info(f"Message   : {message}")

        if not message:
            await turn_context.send_activity("Send a message.")
            return

        # FIX: Use fetch_user_identity (role-aware) instead of fetch_rep_id_by_email
        from app.db import fetch_user_identity

        loop     = asyncio.get_running_loop()
        identity = await loop.run_in_executor(
            sync_executor,
            fetch_user_identity,
            email,
        )

        if not identity:
            logger.warning(f"No identity found for email: {email}")
            await turn_context.send_activity(
                f"Sorry {user_name}, your account isn't set up in the IC system yet. "
                "Please contact your IC administrator."
            )
            return

        rep_id    = identity.get("rep_id", "")
        role      = identity.get("role", "TBM").upper().strip()
        region_id = identity.get("region_id", "")
        rep_name  = identity.get("rep_name") or user_name

        logger.info(f"Resolved rep_id={rep_id} role={role} region_id={region_id} for {email}")

        if not rep_id:
            logger.warning(f"Empty rep_id for email: {email}")
            await turn_context.send_activity(
                f"Sorry {user_name}, your account isn't set up in the IC system yet. "
                "Please contact your IC administrator."
            )
            return

        msg_lower = message.lower().strip()
        GREETINGS = {"hi", "hello", "hey", "start", "help"}

        if msg_lower in GREETINGS:
            from app.db import fetch_payout_data

            payout       = await loop.run_in_executor(sync_executor, fetch_payout_data, int(rep_id))
            display_name = (payout or {}).get("rep_name") or rep_name

            welcome_msg = (
                f"Hello {display_name}! "
                f"How can I help you with your incentive compensation today?"
            )

            adaptive_card_content = {
                "type":    "AdaptiveCard",
                "version": "1.4",

                "body": [
                    {
                        "type": "TextBlock",
                        "text": welcome_msg,
                        "wrap": True,
                        "size": "Medium",
                    }
                ],

                "actions": [
                    {
                        "type":  "Action.Submit",
                        "title": "Show my IC payout for this quarter.",
                        "data":  {
                            "msteams": {
                                "type":  "imBack",
                                "value": "Show my IC payout for this quarter.",
                            }
                        },
                    },
                    {
                        "type":  "Action.Submit",
                        "title": "Explain my eligibility for the current period.",
                        "data":  {
                            "msteams": {
                                "type":  "imBack",
                                "value": "Explain my eligibility for the current period.",
                            }
                        },
                    },
                    {
                        "type":  "Action.Submit",
                        "title": "Show my credits by product.",
                        "data":  {
                            "msteams": {
                                "type":  "imBack",
                                "value": "Show my credits by product.",
                            }
                        },
                    },
                    {
                        "type":  "Action.Submit",
                        "title": "Share my current IC plan document.",
                        "data":  {
                            "msteams": {
                                "type":  "imBack",
                                "value": "Share my current IC plan document.",
                            }
                        },
                    },
                ],
            }

            attachment = Attachment(
                content_type="application/vnd.microsoft.card.adaptive",
                content=adaptive_card_content,
            )

            await turn_context.send_activity(
                Activity(
                    type=ActivityTypes.message,
                    attachments=[attachment],
                )
            )
            return

        logger.info(f"Rep ID: {rep_id} | Role: {role}")
        logger.info("Calling get_rep_explanation")

        # Send typing indicator immediately
        try:
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))
        except Exception:
            pass  # best-effort

        try:
            reply = await asyncio.wait_for(
                loop.run_in_executor(
                    sync_executor,
                    get_rep_explanation,
                    rep_id,
                    message,
                    rag,
                    llm,
                    user_id,
                    rep_name,   # FIX: resolved from identity
                    role,       # FIX: passed so RBD routing works in Teams too
                    region_id,  # FIX: passed so RBD routing works in Teams too
                ),
                timeout=150,
            )
        except asyncio.TimeoutError:
            logger.error("get_rep_explanation timed out after 150s")
            reply = "Your request took too long to process. Please try again."

        logger.info(f"Bot Reply: {reply}")

        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.message,
                text=reply,
                text_format=TextFormatTypes.markdown,
            )
        )

        logger.info("Response sent successfully")

    except Exception as e:
        logger.error("Teams error", exc_info=True)
        await turn_context.send_activity("An error occurred. Please try again.")


# ---------------- TEAMS WEBHOOK ---------------- #

@app.post("/api/messages")
async def messages(req: Request):
    try:
        body_bytes  = await req.body()
        logger.info(f"Raw Teams Payload: {body_bytes.decode('utf-8')}")

        body        = await req.json()
        auth_header = req.headers.get("Authorization", "")

        logger.info(f"Auth Header Present: {bool(auth_header)}")

        activity = Activity().deserialize(body)

        response = await adapter.process_activity(
            activity,
            auth_header,
            handle_teams_message,
        )

        return response or Response(status_code=201)

    except Exception as e:
        logger.error(f"Bot Framework Adapter Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Bot adapter failed to process activity",
        )


# ---------------- REST /ask ENDPOINT ---------------- #

@app.post("/ask", response_model=AskResponse)
async def ask(data: AskRequest):
    """
    FIX: Now resolves full user identity (role, region_id, rep_name) via
         fetch_user_identity when user_id looks like an email address.
         This ensures RBD users hitting /ask are routed to the RBD handler,
         not the TBM handler.
    """
    try:
        loop = asyncio.get_running_loop()

        from app.db import fetch_user_identity

        identity = {}

        # Resolve identity if user_id is an email (typical REST API usage)
        if "@" in (data.user_id or ""):
            identity = await loop.run_in_executor(
                sync_executor,
                fetch_user_identity,
                data.user_id,
            )

        if not identity:
            # Fallback: no email or identity lookup failed.
            # Use rep_id directly and assume TBM role.
            logger.warning(
                f"No identity resolved for user_id={data.user_id}. "
                "Falling back to TBM flow with provided rep_id."
            )
            identity = {
                "rep_id":    data.rep_id,
                "role":      "TBM",
                "region_id": "",
                "rep_name":  "",
            }

        rep_id    = identity.get("rep_id") or data.rep_id
        role      = str(identity.get("role") or "TBM").strip().upper()
        region_id = str(identity.get("region_id") or "").strip()
        rep_name  = str(identity.get("rep_name") or "").strip()

        if not rep_id:
            raise HTTPException(status_code=404, detail="User identity not found")

        logger.info(
            f"Ask endpoint: rep_id={rep_id} role={role} region_id={region_id}"
        )

        result = await loop.run_in_executor(
            sync_executor,
            get_rep_explanation,
            rep_id,
            data.query,
            rag,
            llm,
            data.user_id,
            rep_name,   # FIX: resolved from identity
            role,       # FIX: passed so RBD routing works
            region_id,  # FIX: passed so RBD routing works
        )

        return AskResponse(text=result.strip())

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ask error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")
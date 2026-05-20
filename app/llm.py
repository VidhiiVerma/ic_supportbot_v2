from openai import AzureOpenAI
import os
import logging
import time

logger = logging.getLogger(__name__)


class LLM:
    def __init__(self):
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        self._create_client()

    def _create_client(self):
        """
        Recreate client to avoid stale connections after long inactivity.
        """
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version="2024-12-01-preview",

            # MUCH safer timeout for Teams bots
            timeout=30.0,

            # SDK-level retry
            max_retries=3,
        )

    def generate(self, prompt: str):

        max_attempts = 3

        for attempt in range(1, max_attempts + 1):

            start_time = time.time()

            try:
                logger.info(f"LLM request started (attempt {attempt})")

                response = self.client.chat.completions.create(
                    model=self.deployment,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Be precise. "
                                "Do not guess. "
                                "If information is unavailable, say so clearly."
                            ),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    temperature=0,
                    max_tokens=2500,
                )

                elapsed = round(time.time() - start_time, 2)

                logger.info(f"LLM response received in {elapsed}s")

                if not response.choices:
                    logger.warning("No choices returned from LLM")
                    raise Exception("Empty choices")

                message = response.choices[0].message

                if not message or not message.content:
                    logger.warning("LLM returned empty content")
                    raise Exception("Empty content")

                finish_reason = response.choices[0].finish_reason

                if finish_reason == "length":
                    logger.warning("LLM output truncated due to token limit")

                return message.content.strip()

            except Exception as e:

                elapsed = round(time.time() - start_time, 2)

                logger.error(
                    f"LLM failure on attempt {attempt} "
                    f"after {elapsed}s: {str(e)}",
                    exc_info=True,
                )

                # VERY IMPORTANT:
                # recreate client to avoid stale dead sessions
                self._create_client()

                if attempt < max_attempts:

                    wait_time = attempt * 2

                    logger.info(
                        f"Retrying LLM request in {wait_time}s..."
                    )

                    time.sleep(wait_time)

                else:
                    logger.error("All LLM attempts failed")

                    return (
                        "The AI service is temporarily unavailable. "
                        "Please try again in a few moments."
                    )
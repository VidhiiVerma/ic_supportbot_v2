from openai import AzureOpenAI
import os
import logging
import time

logger = logging.getLogger(__name__)

class LLM:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version="2024-12-01-preview",
            timeout=90.0,           # HTTP-level timeout prevents infinite hangs
            max_retries=2,           # Auto-retry on transient 429/5xx from Azure
        )
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    def generate(self, prompt: str):
        max_attempts = 2

        for attempt in range(1, max_attempts + 1):
            try:
                res = self.client.chat.completions.create(
                    model=self.deployment,
                    messages=[
                        {"role": "system", "content": "Be precise. No guessing."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0,
                    max_tokens=4096,     # Prevent silent truncation by Azure defaults
                )

                content = res.choices[0].message.content
                finish_reason = res.choices[0].finish_reason

                if finish_reason == "length":
                    logger.warning("LLM response was truncated due to max_tokens limit.")

                if not content or not content.strip():
                    logger.warning(f"LLM returned empty response (attempt {attempt})")
                    if attempt < max_attempts:
                        time.sleep(1)
                        continue
                    return "I'm sorry, I couldn't generate a response. Please try again."

                return content.strip()

            except Exception as e:
                logger.error(f"LLM generation failed (attempt {attempt}): {e}", exc_info=True)
                if attempt < max_attempts:
                    time.sleep(2)
                    continue
                return "I'm temporarily unable to process your request. Please try again in a moment."
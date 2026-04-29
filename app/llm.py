from openai import AzureOpenAI
import os

class LLM:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version="2024-12-01-preview"
        )
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    def generate(self, prompt: str):
        res = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": "Be precise. No guessing."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        return res.choices[0].message.content.strip()
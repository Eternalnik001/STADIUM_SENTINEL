import asyncio
import json
import logging
from typing import Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from google.api_core.exceptions import ResourceExhausted

from app.config import settings

log = logging.getLogger("agent.llm")

genai.configure(api_key=settings.GEMINI_API_KEY)

# Map model name — strip trailing "-001" suffix if present (safer for Google AI Studio API)
_model_name = settings.GEMINI_MODEL
if _model_name.endswith("-001") and "gemini" in _model_name:
    _model_name = "-".join(_model_name.split("-")[:-1])

log.info("LLM configured: model=%s", _model_name)


async def call_structured(
    system_prompt: str,
    user_prompt: str,
    response_schema: dict[str, Any],
    temperature: float = 0.2,
    max_output_tokens: int = 1024,
    max_retries: int = 4,
) -> dict[str, Any]:
    """Forces the model to return JSON matching response_schema.
    Retries with exponential backoff on 429 ResourceExhausted errors."""
    config = GenerationConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json",
        response_schema=response_schema,
    )

    model_with_sys = genai.GenerativeModel(
        model_name=_model_name,
        system_instruction=system_prompt,
    )

    backoff = 5.0  # seconds — start conservative for free tier
    for attempt in range(max_retries + 1):
        try:
            response = await model_with_sys.generate_content_async(
                user_prompt,
                generation_config=config,
            )
            try:
                return json.loads(response.text)
            except (json.JSONDecodeError, AttributeError) as e:
                raise ValueError(f"model returned invalid JSON: {e}")

        except ResourceExhausted as e:
            if attempt == max_retries:
                raise
            wait = backoff * (2 ** attempt)
            log.warning(
                "429 ResourceExhausted (attempt %d/%d) — backing off %.1fs: %s",
                attempt + 1, max_retries, wait, str(e)[:120],
            )
            await asyncio.sleep(wait)

import json
import re
from pathlib import Path
from typing import Any, Protocol, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.errors import AppError

T = TypeVar("T", bound=BaseModel)


class ChatModelProvider(Protocol):
    model: str

    async def generate_text(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        **kwargs: Any,
    ) -> T: ...


class OpenAICompatibleChatProvider:
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        selected_model = model or settings.llm_model
        if not settings.llm_base_url or not settings.llm_api_key or not selected_model:
            raise AppError(
                "MODEL_PROVIDER_ERROR",
                "尚未配置 LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL",
                status_code=503,
            )
        self.model = selected_model
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    async def generate_text(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                **kwargs,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise AppError(
                "MODEL_PROVIDER_ERROR",
                "模型调用失败",
                status_code=502,
                details={"reason": str(exc)},
            ) from exc

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        **kwargs: Any,
    ) -> T:
        schema_instruction = (
            "\n只输出一个 JSON 对象，不要使用 Markdown。必须严格符合此 JSON Schema：\n"
            + json.dumps(response_model.model_json_schema(), ensure_ascii=False)
        )
        working = [*messages]
        working[-1] = {
            **working[-1],
            "content": working[-1]["content"] + schema_instruction,
        }
        last_error = ""
        for attempt in range(2):
            raw = await self.generate_text(
                working,
                response_format={"type": "json_object"},
                **kwargs,
            )
            try:
                return response_model.model_validate_json(self._extract_json(raw))
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)
                if attempt == 0:
                    working.extend(
                        [
                            {"role": "assistant", "content": raw},
                            {
                                "role": "user",
                                "content": (
                                    "上一个 JSON 校验失败。仅修复结构和类型，不新增事实。"
                                    f"校验错误：{last_error}"
                                ),
                            },
                        ]
                    )
        raise AppError(
            "MODEL_PROVIDER_ERROR",
            "模型结构化输出连续两次校验失败",
            status_code=502,
            details={"validation_error": last_error},
        )

    @staticmethod
    def _extract_json(raw: str) -> str:
        text = raw.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        return fenced.group(1) if fenced else text


def load_prompt(name: str) -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / name
    return path.read_text(encoding="utf-8")

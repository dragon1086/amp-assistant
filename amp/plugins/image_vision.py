"""Image Vision plugin — analyze images using GPT-4o Vision."""
import base64
import io
import logging

from amp.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class ImageVisionPlugin(BasePlugin):
    name = "image_vision"
    description = "이미지 분석 (GPT-4o Vision)"
    enabled_by_default = True

    def can_handle(self, update) -> bool:
        return bool(update.message and update.message.photo)

    async def handle(self, update, context, config: dict, user_config: dict) -> str | None:
        try:
            plugin_config = config.get("plugins", {}).get("image_vision", {})
            provider = plugin_config.get("provider", "openai")

            # Highest resolution photo
            photo = update.message.photo[-1]
            caption = update.message.caption or ""

            # Download to memory
            photo_file = await context.bot.get_file(photo.file_id)
            buf = io.BytesIO()
            await photo_file.download_to_memory(buf)
            buf.seek(0)
            image_b64 = base64.b64encode(buf.read()).decode("utf-8")

            if provider == "openai":
                return await self._analyze_openai(image_b64, caption)
            else:
                return f"❌ 지원하지 않는 provider: {provider}"

        except Exception as e:
            logger.error(f"ImageVision error: {e}", exc_info=True)
            return f"❌ 이미지 분석 실패: {str(e)[:200]}"

    async def _analyze_openai(self, image_b64: str, caption: str) -> str:
        import os

        import openai

        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        prompt_text = caption if caption else "이 이미지를 자세히 분석해주세요."

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
            max_tokens=1000,
        )
        return response.choices[0].message.content

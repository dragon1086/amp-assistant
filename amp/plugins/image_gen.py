"""Image generation plugin — DALL-E 3, local Stable Diffusion, or Replicate.

Commands:
  /imagine <prompt> — generate an image from text

Config (config.yaml):
  plugins:
    image_gen:
      backend: dalle3       # dalle3 | local | replicate
      local_url: http://localhost:7860
"""
import asyncio
import base64
import logging

from amp.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class ImageGenPlugin(BasePlugin):
    name = "image_gen"
    description = "이미지 생성 (/imagine <프롬프트>)"
    enabled_by_default = True

    def can_handle(self, update) -> bool:
        return bool(
            update.message
            and update.message.text
            and update.message.text.lower().startswith("/imagine")
        )

    async def handle(self, update, context, config: dict, user_config: dict) -> str | None:
        text = update.message.text or ""
        prompt = text[len("/imagine"):].strip()

        if not prompt:
            await update.message.reply_text(
                "사용법: `/imagine <이미지 설명>`\n예: `/imagine 한국 산의 일출`",
                parse_mode="Markdown",
            )
            return None

        plugin_config = config.get("plugins", {}).get("image_gen", {})
        backend = plugin_config.get("backend", "dalle3")

        try:
            if backend == "dalle3":
                image_bytes = await self._dalle3(prompt)
            elif backend == "local":
                local_url = plugin_config.get("local_url", "http://localhost:7860")
                image_bytes = await self._local_sd(prompt, local_url)
            elif backend == "replicate":
                image_bytes = await self._replicate(prompt)
            else:
                await update.message.reply_text(f"❌ 알 수 없는 backend: `{backend}`", parse_mode="Markdown")
                return None

            await update.message.reply_photo(
                photo=image_bytes,
                caption=f"🎨 {prompt[:200]}",
            )
        except Exception as e:
            logger.error(f"ImageGen error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ 이미지 생성 실패: {str(e)[:200]}")

        return None

    async def _dalle3(self, prompt: str) -> bytes:
        import os

        import httpx
        import openai

        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.get(image_url)
            resp.raise_for_status()
            return resp.content

    async def _local_sd(self, prompt: str, local_url: str) -> bytes:
        """Automatic1111 / ComfyUI compatible endpoint."""
        import httpx

        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.post(
                f"{local_url}/sdapi/v1/txt2img",
                json={"prompt": prompt, "steps": 20, "width": 512, "height": 512},
            )
            resp.raise_for_status()
            data = resp.json()
            return base64.b64decode(data["images"][0])

    async def _replicate(self, prompt: str) -> bytes:
        """Replicate API — SDXL model."""
        import os

        import httpx

        token = os.environ.get("REPLICATE_API_TOKEN", "")
        if not token:
            raise ValueError("REPLICATE_API_TOKEN 환경변수가 설정되지 않았습니다")

        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }
        # SDXL model version
        version = "39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b"

        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers,
                json={"version": version, "input": {"prompt": prompt}},
            )
            resp.raise_for_status()
            prediction = resp.json()
            poll_url = prediction["urls"]["get"]

            for _ in range(60):
                await asyncio.sleep(2)
                poll = await http.get(poll_url, headers=headers)
                pred = poll.json()
                if pred["status"] == "succeeded":
                    image_url = pred["output"][0]
                    img_resp = await http.get(image_url)
                    img_resp.raise_for_status()
                    return img_resp.content
                elif pred["status"] == "failed":
                    raise RuntimeError(f"Replicate 실패: {pred.get('error')}")

        raise TimeoutError("Replicate 예측 시간 초과")

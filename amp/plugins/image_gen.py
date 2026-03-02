"""Image generation plugin — Nano Banana 2 (Gemini), DALL-E 3, local SD, or Replicate.

Commands:
  /imagine <prompt> — generate an image from text

Config (config.yaml):
  plugins:
    image_gen:
      backend: nanonbanana2   # nanonbanana2 | dalle3 | local | replicate
      local_url: http://localhost:7860  # for backend: local
      gemini_model: gemini-3.1-flash-image-preview  # Nano Banana 2 model ID

Nano Banana 2 = Google Gemini 3.1 Flash Image (출시: 2026-02-26)
  - 모델 ID: gemini-3.1-flash-image-preview
  - 최대 4K 해상도, 3× 빠른 생성 속도
  - 필요: GOOGLE_API_KEY (유료 tier, ~$0.10/장)
  - SDK: pip install google-generativeai
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
            if backend in ("nanonbanana2", "gemini", "nano_banana"):
                gemini_model = plugin_config.get("gemini_model", "gemini-3.1-flash-image-preview")
                image_bytes = await self._nanonbanana2(prompt, gemini_model)
                caption_tag = "🍌 나노바나나2"
            elif backend == "dalle3":
                image_bytes = await self._dalle3(prompt)
                caption_tag = "🎨 DALL-E 3"
            elif backend == "local":
                local_url = plugin_config.get("local_url", "http://localhost:7860")
                image_bytes = await self._local_sd(prompt, local_url)
                caption_tag = "🖥️ 로컬 SD"
            elif backend == "replicate":
                image_bytes = await self._replicate(prompt)
                caption_tag = "☁️ Replicate"
            else:
                await update.message.reply_text(f"❌ 알 수 없는 backend: `{backend}`", parse_mode="Markdown")
                return None

            await update.message.reply_photo(
                photo=image_bytes,
                caption=f"{caption_tag} | {prompt[:180]}",
            )
        except Exception as e:
            logger.error(f"ImageGen error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ 이미지 생성 실패: {str(e)[:200]}")

        return None

    async def _nanonbanana2(self, prompt: str, model_id: str = "gemini-3.1-flash-image-preview") -> bytes:
        """Nano Banana 2 — Google Gemini 3.1 Flash Image (출시: 2026-02-26).

        - 최대 4K 해상도, 3× 생성 속도 향상
        - 필요: GOOGLE_API_KEY (유료 tier)
        - pip install google-generativeai
        """
        import os

        import google.generativeai as genai

        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY 또는 GEMINI_API_KEY 환경변수가 설정되지 않았습니다\n"
                "Google AI Studio에서 API 키를 발급받으세요: https://aistudio.google.com\n"
                "⚠️ 이미지 생성은 유료 tier 필요 (~$0.10/장)"
            )

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_id)

        # Run in thread since google-generativeai is sync
        def _generate() -> bytes:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )
            # Extract image bytes from response parts
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    return part.inline_data.data  # raw bytes
            raise RuntimeError("응답에서 이미지를 찾을 수 없습니다. 프롬프트를 수정해보세요.")

        return await asyncio.to_thread(_generate)

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

import os
from pathlib import Path

from google import genai


class llm_agent:
	def __init__(self, prompt: list, USER_PROMPT: str, mode: int) -> None:
		self.prompt = prompt
		self.USER_PROMPT = USER_PROMPT
		self.mode = mode

	def generate_response(self, USER_PROMPT: str, mode: int) -> str:
		api_key = os.getenv("GEMINI_API_KEY")
		if not api_key:
			raise RuntimeError("GEMINI_API_KEY is not configured")

		system_prompt_path = Path(__file__).with_name("system_prompt.txt")
		system_prompt = system_prompt_path.read_text(encoding="utf-8")
		client = genai.Client(api_key=api_key)
		response = client.models.generate_content(
			model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
			contents=USER_PROMPT,
			config={"system_instruction": system_prompt},
		)
		return response.text or ""

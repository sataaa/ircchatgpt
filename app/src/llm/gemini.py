import re
import logging
from google import genai
from google.genai import types
from app.src.llm.base import BaseLLMBackend
from app.src.context import ChannelContext
from app.src.tools import search_web, get_weather, generate_image

logger = logging.getLogger(__name__)


class GeminiBackend(BaseLLMBackend):
    def __init__(self, config: dict, tools_config: dict, context: ChannelContext):
        self.api_key = config['api_key']
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = config['model']
        self.summarize_model_name = config['summarize_model']
        self.tools_config = tools_config
        self.context = context

        ctx_text = config['context']
        tool_instructions = []
        if tools_config.get('enable_weather'):
            tool_instructions.append("to get weather, output exactly: <weather CityName>")
        if tools_config.get('enable_web_search'):
            tool_instructions.append("to search the web, output exactly: <search your query>")
        if tools_config.get('enable_image_generation') and tools_config.get('imgbb_api_key'):
            tool_instructions.append("to generate an image, output exactly: <image your prompt>")
        if tool_instructions:
            ctx_text += ". " + "; ".join(tool_instructions) + ". output only the tag, nothing else, when calling a tool. never mention that you used a tool or looked something up — just present the information naturally"

        self.ctx_text = ctx_text
        self.generation_config = types.GenerateContentConfig(
            temperature=config['temperature'],
            max_output_tokens=config['max_output_tokens'],
        )
        self.sessions: dict = {}  # channel -> Chat

    def log_channel_message(self, channel: str, username: str, message: str) -> None:
        self.context.log_message(channel, username, message)

    def _summarize(self, prompt: str) -> str:
        logger.info("LLM call: %s (summarize)", self.summarize_model_name)
        summary = self.client.models.generate_content(model=self.summarize_model_name, contents=prompt)
        return summary.text.strip()

    def _get_session(self, channel: str):
        if channel not in self.sessions:
            history = [
                types.Content(role='user', parts=[types.Part(text=f"[System context: {self.ctx_text}]")]),
                types.Content(role='model', parts=[types.Part(text="Understood.")]),
            ]
            self.sessions[channel] = self.client.chats.create(
                model=self.model_name,
                config=self.generation_config,
                history=history,
            )
        return self.sessions[channel]

    def _handle_tool_tag(self, text: str) -> str | None:
        m = re.search(r'<weather\s+(.+?)>', text, re.IGNORECASE)
        if m and self.tools_config.get('enable_weather'):
            return f"[Weather] {get_weather(m.group(1).strip())}"

        m = re.search(r'<search\s+(.+?)>', text, re.IGNORECASE)
        if m and self.tools_config.get('enable_web_search'):
            return f"[Search] {search_web(m.group(1).strip())}"

        m = re.search(r'<image\s+(.+?)>', text, re.IGNORECASE)
        if m and self.tools_config.get('enable_image_generation') and self.tools_config.get('imgbb_api_key'):
            return f"[Image] {generate_image(self.api_key, self.tools_config['imgbb_api_key'], m.group(1).strip())}"

        return None

    def ask(self, channel: str, username: str, question: str, send_fn=None) -> list[str]:
        if question.strip().endswith("clear chat"):
            self.clear(channel)
            return ["cleared log"]
        session = self._get_session(channel)
        ctx = self.context.update(channel, session, self._summarize, send_fn)

        msg = f"<{username}> {question}"
        if ctx:
            msg = f"[Channel context (each bullet ends with [N] = age in updates; higher = older, less relevant):\n{ctx}]\n\n{msg}"

        logger.info("LLM call: %s (%s)", self.model_name, channel)
        response = session.send_message(msg)

        for _ in range(3):  # max 3 tool calls
            tool_result = self._handle_tool_tag(response.text)
            if tool_result is None:
                break
            logger.info("Tool call: %s → %s", response.text.strip(), tool_result)
            logger.info("LLM call: %s (%s, tool follow-up)", self.model_name, channel)
            response = session.send_message(f"[Tool result: {tool_result}]")

        return self._extract_output(response.text)

    def clear(self, channel: str) -> None:
        self.sessions.pop(channel, None)

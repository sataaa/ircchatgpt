from openai import OpenAI
from app.src.llm.base import BaseLLMBackend


class OpenAIBackend(BaseLLMBackend):
    def __init__(self, config: dict, tools_config: dict):
        self.client = OpenAI(api_key=config['api_key'])
        self.model = config['model']
        self.context = config['context']
        self.temperature = config['temperature']
        self.max_tokens = config['max_tokens']
        self.messages: dict[str, list] = {}

    def _get_messages(self, channel: str) -> list:
        if channel not in self.messages:
            self.messages[channel] = [{'role': 'system', 'content': self.context}]
        return self.messages[channel]

    def ask(self, channel: str, username: str, question: str, send_fn=None) -> list[str]:
        if question.strip().endswith("clear chat"):
            self.clear(channel)
            return ["cleared log"]
        msgs = self._get_messages(channel)
        msgs.append({'role': 'user', 'content': f'<{username}> {question}'})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=msgs,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        content = response.choices[0].message.content
        msgs.append({'role': 'assistant', 'content': content})
        return self._extract_output(content)

    def clear(self, channel: str) -> None:
        self.messages.pop(channel, None)

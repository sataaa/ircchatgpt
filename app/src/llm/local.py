import requests
from app.src.llm.base import BaseLLMBackend


class LocalBackend(BaseLLMBackend):
    def __init__(self, config: dict):
        self.url = f"http://{config['target_ip']}:{config['local_port']}{config['mapping']}"
        self.headers = {'Content-Type': 'application/json'}
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
        payload = {
            'messages': msgs,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'stream': False,
        }
        response = requests.post(self.url, headers=self.headers, json=payload)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        msgs.append({'role': 'assistant', 'content': content})
        return self._extract_output(content)

    def clear(self, channel: str) -> None:
        self.messages.pop(channel, None)

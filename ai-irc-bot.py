import os
import re
import socket
import ssl
import time
import configparser
import requests
from google import genai
from google.genai import types
from openai import OpenAI
import threading
import logging
from tools import search_web, get_weather, generate_image

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self, path='chat.conf'):
        config = configparser.ConfigParser()
        config.read(path)
        self.config = config

    def get_irc_config(self):
        return {
            'server': self.config.get('irc', 'server'),
            'port': self.config.getint('irc', 'port'),
            'ssl': self.config.getboolean('irc', 'ssl'),
            'channels': self.config.get('irc', 'channels').split(','),
            'nickname': self.config.get('irc', 'nickname'),
            'ident': self.config.get('irc', 'ident'),
            'realname': self.config.get('irc', 'realname'),
            'password': self.config.get('irc', 'password')
        }

    def get_provider(self) -> str:
        return self.config.get('provider', 'backend')

    def get_gemini_config(self) -> dict:
        return {
            'api_key': self.config.get('gemini', 'api_key'),
            'model': self.config.get('gemini', 'model'),
            'context': self.config.get('gemini', 'context'),
            'max_output_tokens': self.config.getint('gemini', 'max_output_tokens'),
            'temperature': self.config.getfloat('gemini', 'temperature'),
        }

    def get_openai_config(self) -> dict:
        return {
            'api_key': self.config.get('openai', 'api_key'),
            'model': self.config.get('openai', 'model'),
            'context': self.config.get('openai', 'context'),
            'max_tokens': self.config.getint('openai', 'max_tokens'),
            'temperature': self.config.getfloat('openai', 'temperature'),
        }

    def get_local_config(self) -> dict:
        return {
            'target_ip': self.config.get('localserver', 'target_ip'),
            'local_port': self.config.get('localserver', 'local_port'),
            'mapping': self.config.get('localserver', 'mapping'),
            'context': self.config.get('localserver', 'context'),
            'max_tokens': self.config.getint('localserver', 'max_tokens'),
            'temperature': self.config.getfloat('localserver', 'temperature'),
        }

    def get_tools_config(self) -> dict:
        return {
            'enable_web_search': self.config.getboolean('tools', 'enable_web_search'),
            'enable_weather': self.config.getboolean('tools', 'enable_weather'),
            'enable_image_generation': self.config.getboolean('tools', 'enable_image_generation'),
            'imgbb_api_key': self.config.get('tools', 'imgbb_api_key'),
        }


class IRCClient:
    def __init__(self, config: dict):
        self.server: str = config['server']
        self.port: str = config['port']
        self.usessl: bool = config['ssl']
        self.channels: list[str] = config['channels']
        self.nickname: str = config['nickname']
        self.ident: str = config['ident']
        self.realname: str = config['realname']
        self.password: str = config['password']
        self.socket: socket = None
        self._buffer: str = ""
        self.joined: bool = False

    def connect(self):
        self.joined = False
        while True:
            try:
                logger.info(f"Connecting to: {self.server}:{self.port}")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((self.server, self.port))
                if self.usessl:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    sock = context.wrap_socket(sock, server_hostname=self.server)
                self.socket = sock

                if self.password:
                    self.send(f"PASS {self.password}")
                self.send(f"USER {self.ident} 0 * :{self.realname}")
                self.send(f"NICK {self.nickname}")
                self.send("CAP REQ :message-tags")
                self.send("CAP REQ :echo-message")
                self.send("CAP END")
                logger.info("Connected successfully.")
                return
            except Exception as e:
                logger.error(f"Connection failed: {e}. Retrying in 5 seconds...")
                time.sleep(5)

    def send(self, msg):
        logger.debug("> %s", msg)
        self.socket.send(bytes(msg + "\n", "UTF-8"))

    def receive(self) -> list[str]:
        try:
            raw = self.socket.recv(8192).decode("UTF-8")
        except UnicodeDecodeError:
            return []
        self._buffer += raw
        lines = self._buffer.split("\n")
        self._buffer = lines[-1]
        return [line.strip() for line in lines[:-1] if line.strip()]


class BaseLLMBackend:
    def ask(self, channel: str, username: str, question: str, send_fn=None) -> list[str]:
        raise NotImplementedError

    def clear(self, channel: str) -> None:
        raise NotImplementedError

    def log_channel_message(self, channel: str, username: str, message: str) -> None:
        pass

    def _extract_output(self, content: str) -> list[str]:
        output, thought, inside_think = [], [], False
        for line in content.split('\n'):
            if '<think>' in line:
                inside_think = True
            if inside_think:
                thought.append(line)
                if '</think>' in line:
                    inside_think = False
                continue
            output.append(line)
        if thought:
            logger.debug("Thought: %s", '\n'.join(thought))
        return output


class GeminiBackend(BaseLLMBackend):
    def __init__(self, config: dict, tools_config: dict):
        self.api_key = config['api_key']
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = config['model']
        self.tools_config = tools_config
        os.makedirs("tmp", exist_ok=True)

        context = config['context']
        tool_instructions = []
        if tools_config.get('enable_weather'):
            tool_instructions.append("to get weather, output exactly: <weather CityName>")
        if tools_config.get('enable_web_search'):
            tool_instructions.append("to search the web, output exactly: <search your query>")
        if tools_config.get('enable_image_generation') and tools_config.get('imgbb_api_key'):
            tool_instructions.append("to generate an image, output exactly: <image your prompt>")
        if tool_instructions:
            context += ". " + "; ".join(tool_instructions) + ". output only the tag, nothing else, when calling a tool. after using a tool result, briefly mention you looked it up"

        self.context = context
        self.generation_config = types.GenerateContentConfig(
            temperature=config['temperature'],
            max_output_tokens=config['max_output_tokens'],
        )
        self.sessions: dict = {}  # channel -> Chat

    def _log_path(self, channel: str) -> str:
        return f"tmp/{channel}.log"

    def _ctx_path(self, channel: str) -> str:
        return f"tmp/{channel}.ctx"

    def _cursor_path(self, channel: str) -> str:
        return f"tmp/{channel}.cursor"

    def log_channel_message(self, channel: str, username: str, message: str) -> None:
        log_path = self._log_path(channel)
        with open(log_path, 'a') as f:
            f.write(f"{username}: {message}\n")
        with open(log_path) as f:
            lines = f.readlines()
        if len(lines) > 1000:
            with open(log_path, 'w') as f:
                f.writelines(lines[-1000:])

    def _update_channel_context(self, channel: str, session, send_fn=None) -> str:
        log_path = self._log_path(channel)
        ctx_path = self._ctx_path(channel)
        cursor_path = self._cursor_path(channel)

        if not os.path.exists(log_path):
            return ""

        with open(log_path) as f:
            log_lines = f.readlines()

        cursor = 0
        if os.path.exists(cursor_path):
            try:
                cursor = int(open(cursor_path).read().strip())
            except ValueError:
                cursor = 0
        if cursor >= len(log_lines):
            cursor = max(0, len(log_lines) - 150)

        diff = log_lines[cursor:]
        if not diff:
            return open(ctx_path).read().strip() if os.path.exists(ctx_path) else ""

        if len(diff) > 150:
            catchup = session.send_message(
                "(you have a large backlog of channel messages to read before answering — "
                "tell the channel you're catching up, one short sentence, stay in character)"
            )
            if send_fn:
                send_fn(catchup.text.strip())
            diff = diff[-150:]

        ctx = open(ctx_path).read().strip() if os.path.exists(ctx_path) else ""
        diff_text = "".join(diff).strip()

        prompt = (
            "Summarize this IRC channel conversation into a bullet list of max 10 short phrases. "
            "Fade out older topics, emphasize recent ones. Output ONLY the bullet list, nothing else.\n\n"
            f"Current context:\n{ctx}\n\nNew messages:\n{diff_text}"
        )
        summary = self.client.models.generate_content(model=self.model_name, contents=prompt)
        new_ctx = summary.text.strip()

        with open(ctx_path, 'w') as f:
            f.write(new_ctx)
        with open(cursor_path, 'w') as f:
            f.write(str(len(log_lines)))

        logger.info("Channel context updated for %s (%d new lines)", channel, len(diff))
        return new_ctx

    def _get_session(self, channel: str):
        if channel not in self.sessions:
            # Inject context as a user/model history pair — works for all models
            # including gemma which doesn't support system_instruction
            history = [
                types.Content(role='user', parts=[types.Part(text=f"[System context: {self.context}]")]),
                types.Content(role='model', parts=[types.Part(text="Understood.")]),
            ]
            self.sessions[channel] = self.client.chats.create(
                model=self.model_name,
                config=self.generation_config,
                history=history,
            )
        return self.sessions[channel]

    def _handle_tool_tag(self, text: str) -> str | None:
        """If text contains a tool tag, call the tool and return the result. Else None."""
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
        ctx = self._update_channel_context(channel, session, send_fn)

        msg = f"<{username}> {question}"
        if ctx:
            msg = f"[Channel context:\n{ctx}]\n\n{msg}"

        response = session.send_message(msg)

        for _ in range(3):  # max 3 tool calls
            tool_result = self._handle_tool_tag(response.text)
            if tool_result is None:
                break
            logger.info("Tool call: %s → %s", response.text.strip(), tool_result)
            response = session.send_message(f"[Tool result: {tool_result}]")

        return self._extract_output(response.text)

    def clear(self, channel: str) -> None:
        self.sessions.pop(channel, None)


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

    def ask(self, channel: str, username: str, question: str) -> list[str]:
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

    def ask(self, channel: str, username: str, question: str) -> list[str]:
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


class LLMClient:
    """Factory — reads provider and returns the appropriate backend instance."""
    def __new__(cls, provider: str, config: dict, tools_config: dict):
        if provider == 'gemini':
            return GeminiBackend(config, tools_config)
        elif provider == 'openai':
            return OpenAIBackend(config, tools_config)
        elif provider == 'local':
            return LocalBackend(config)
        raise ValueError(f"Unknown provider: {provider}")


class MessageHandler:
    def __init__(self, irc_client: IRCClient, llm_client):
        self.irc = irc_client
        self.llm = llm_client
        self.active_threads: set[str] = set()

    def send_typing_active(self, channel: str, stop_event):
      while not stop_event.is_set():
          self.irc.send(f"@+typing=active TAGMSG {channel}")
          stop_event.wait(5)

    def handle(self, line: str):
        if line.startswith("PING"):
            self.irc.send("PONG " + line.split()[1])
            if not self.irc.joined:
                self.irc.send("JOIN " + ",".join(self.irc.channels))
                self.irc.joined = True
            return

        if "KICK" in line and self.irc.nickname in line:
            channel = line.split()[2]
            self.irc.send(f"JOIN {channel}")
            return

        if "PRIVMSG" not in line:
            return

        parts = line.split()
        if line.startswith("@"):
            raw_tags = parts[0][1:]
            tag_dict = {k.lstrip("+"): v for tag in raw_tags.split(";") if "=" in tag for k, v in [tag.split("=", 1)]}
        else:
            tag_dict = {}

        reply_to = tag_dict.get("draft/reply")
        incoming_msgid = tag_dict.get("msgid")

        # Echo-message: server sends back our own messages with their server-assigned msgid.
        # Track those so replies to the bot's messages are also detected as in_bot_thread.
        if f":{self.irc.nickname}!" in line:
            if incoming_msgid:
                self.active_threads.add(incoming_msgid)
            return

        # Log all incoming channel messages for context tracking
        channel_idx = 3 if line.startswith("@") else 2
        log_channel = parts[channel_idx]
        log_username = line.split('!')[0].split()[-1].lstrip(':')
        msg_split = line.split(f"PRIVMSG {log_channel} :", 1)
        if len(msg_split) > 1:
            self.llm.log_channel_message(log_channel, log_username, msg_split[1].strip())

        directly_addressed = f":{self.irc.nickname}:" in line
        in_bot_thread = reply_to is not None and reply_to in self.active_threads

        if not (directly_addressed or in_bot_thread):
            return

        channel = log_channel
        username = line.split('!')[0].split()[-1][1:]

        if directly_addressed:
            question = line.split(f":{self.irc.nickname}:", 1)[1].strip()
        else:
            question = line.split(f"PRIVMSG {channel} :", 1)[1].strip()

        thread_id = reply_to or incoming_msgid

        # send "typing" event every 5 seconds
        stop_typing = threading.Event()
        typing_thread = threading.Thread(target=self.send_typing_active, args=(channel, stop_typing))
        typing_thread.start()

        responses = self.llm.ask(
            channel, username, question,
            send_fn=lambda text: self.irc.send(f"PRIVMSG {channel} :{text}")
        )

        # halt typing event and send typing=done
        stop_typing.set()
        typing_thread.join()
        self.irc.send(f"@+typing=done TAGMSG {channel}")

        prefix = f"@+draft/reply={thread_id} " if thread_id else ""
        for response in responses:
            while response:
                if len(response) <= 392:
                    self.irc.send(f"{prefix}PRIVMSG {channel} :{response}")
                    break
                split_idx = response[:392].rfind(" ")
                if split_idx == -1:
                    split_idx = 392
                self.irc.send(f"{prefix}PRIVMSG {channel} :{response[:split_idx]}")
                response = response[split_idx:].lstrip()

        # Track this thread so future replies to it also trigger the bot
        if incoming_msgid:
            self.active_threads.add(incoming_msgid)
        if thread_id:
            self.active_threads.add(thread_id)


class Bot:
    def __init__(self):
        self.config_loader = ConfigLoader()
        irc_config: dict = self.config_loader.get_irc_config()
        provider: str = self.config_loader.get_provider()
        provider_config: dict = getattr(self.config_loader, f'get_{provider}_config')()
        tools_config: dict = self.config_loader.get_tools_config()

        self.irc = IRCClient(irc_config)
        self.llm = LLMClient(provider, provider_config, tools_config)
        self.handler = MessageHandler(self.irc, self.llm)

    def run(self):
        self.irc.connect()
        while True:
            for line in self.irc.receive():
                logger.debug(line)
                self.handler.handle(line)
            time.sleep(1)


if __name__ == "__main__":
    bot = Bot()
    try:
        bot.run()
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        try:
            bot.irc.send(f"QUIT :{type(e).__name__}: {e}")
        except Exception:
            pass
        raise

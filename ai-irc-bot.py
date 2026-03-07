import socket
import ssl
import time
import configparser
import requests
import openai
import threading

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

    def get_openai_config(self):
        return {
            'api_key': self.config.get('openai', 'api_key'),
            'model': self.config.get('chatcompletion', 'model'),
            'context': self.config.get('chatcompletion', 'context'),
            'temperature': self.config.getfloat('chatcompletion', 'temperature'),
            'max_tokens': self.config.getint('chatcompletion', 'max_tokens'),
            'top_p': self.config.getint('chatcompletion', 'top_p'),
            'frequency_penalty': self.config.getint('chatcompletion', 'frequency_penalty'),
            'presence_penalty': self.config.getint('chatcompletion', 'presence_penalty'),
            'request_timeout': self.config.getint('chatcompletion', 'request_timeout')
        }

    def get_local_server_config(self):
        return {
            'target_ip': self.config.get('localserver', 'target_ip'),
            'local_port': self.config.get('localserver', 'local_port'),
            'mapping': self.config.get('localserver', 'mapping'),
            'use_local_server': self.config.getboolean('localserver', 'use_local_server'),
            'url': self.config.get('localserver', 'url', fallback=None),
            'api_key': self.config.get('localserver', 'api_key', fallback=None),
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

    def connect(self):
        while True:
            try:
                print(f"Connecting to: {self.server}:{self.port}")
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
                self.send("CAP END")
                print("Connected successfully.")
                return
            except Exception as e:
                print(f"Connection failed: {e}. Retrying in 5 seconds...")
                time.sleep(5)

    def send(self, msg):
        print(">", msg)
        self.socket.send(bytes(msg + "\n", "UTF-8"))

    def receive(self):
        try:
            return self.socket.recv(8192).decode("UTF-8")
        except UnicodeDecodeError:
            return None


class LLMClient:
    def __init__(self, config: dict, local_config: dict):
        self.use_local: bool = local_config['use_local_server']
        self.context: str = config['context']
        self.model: str = config['model']
        self.messages: list[dict[str:str]] = [{'role': 'system', 'content': self.context}]
        self.temperature: float = config['temperature']
        self.max_tokens: int = config['max_tokens']
        self.top_p: int = config['top_p']
        self.freq_penalty: int = config['frequency_penalty']
        self.pres_penalty: int = config['presence_penalty']
        self.timeout: int = config['request_timeout']

        if not self.use_local:
            openai.api_key = config['api_key']
        else:
            if local_config.get('url'):
                self.url = local_config['url']
            else:
                self.url = f"http://{local_config['target_ip']}:{local_config['local_port']}{local_config['mapping']}"
            self.headers = {'Content-Type': 'application/json'}
            if local_config.get('api_key'):
                self.headers['Authorization'] = f"Bearer {local_config['api_key']}"

    def ask(self, username: str, question: str):
        if question.endswith("clear chat"):
            self.messages = [{'role': 'system', 'content': self.context}]
            return ["cleared log"]

        user_message = {'role': 'user', 'content': f'<{username}> {question}'}
        self.messages.append(user_message)

        if self.use_local:
            payload = {
                'messages': self.messages,
                'temperature': self.temperature,
                'max_tokens': self.max_tokens,
                'stream': False
            }
            response = requests.post(self.url, headers=self.headers, json=payload)
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
        else:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=self.messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=self.top_p,
                frequency_penalty=self.freq_penalty,
                presence_penalty=self.pres_penalty,
                request_timeout=self.timeout
            )
            content = response.choices[0].message.content

        self.messages.append({'role': 'assistant', 'content': content})
        return self._extract_output(content)

    def _extract_output(self, content: str):
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
            print("Thought:", '\n'.join(thought))
        return output


class MessageHandler:
    def __init__(self, irc_client: IRCClient, llm_client: LLMClient):
        self.irc = irc_client
        self.llm = llm_client
    
    def send_typing_active(self, channel: str, stop_event):
      while not stop_event.is_set():
          self.irc.send(f"@+typing=active TAGMSG {channel}")
          stop_event.wait(1)

    def handle(self, line: str):
        if line.startswith("PING"):
            self.irc.send("PONG " + line.split()[1])
            self.irc.send("JOIN " + ",".join(self.irc.channels))
            return

        if "PRIVMSG" in line and f":{self.irc.nickname}:" in line:
            parts = line.split()
            channel = parts[3]
            username = line.split('!')[0].split()[1][1:]
            question = line.split(f":{self.irc.nickname}:", 1)[1].strip()
            tag_dict = dict(tag.split("=", 1) for tag in parts[0][2:].split(" ", 1)[0].split(";") if "=" in tag)
            msgid = tag_dict.get("draft/reply") or tag_dict.get("msgid")

            # send "typing" event every 5 seconds
            stop_typing = threading.Event()
            typing_thread = threading.Thread(target=self.send_typing_active, args=(channel, stop_typing))
            typing_thread.start()

            responses = self.llm.ask(username, question)

            # halt typing event and send typing=done
            stop_typing.set()
            typing_thread.join()
            self.irc.send(f"@+typing=done TAGMSG {channel}")

            for response in responses:
                while response:
                    if len(response) <= 392:
                        self.irc.send(f"@+draft/reply={msgid} PRIVMSG {channel} :{response}")
                        break
                    split_idx = response[:392].rfind(" ")
                    if split_idx == -1:
                        split_idx = 392
                    self.irc.send(f"@+draft/reply={msgid} PRIVMSG {channel} :{response[:split_idx]}")
                    response = response[split_idx:].lstrip()


class Bot:
    def __init__(self):
        self.config_loader = ConfigLoader()
        irc_config: dict = self.config_loader.get_irc_config()
        openai_config: dict = self.config_loader.get_openai_config()
        local_config: dict = self.config_loader.get_local_server_config()

        self.irc = IRCClient(irc_config)
        self.llm = LLMClient(openai_config, local_config)
        self.handler = MessageHandler(self.irc, self.llm)

    def run(self):
        self.irc.connect()
        while True:
            data = self.irc.receive()
            if not data:
                continue
            for line in data.split("\n"):
                line = line.strip()
                if line:
                    print(line)
                    self.handler.handle(line)
            time.sleep(1)


if __name__ == "__main__":
    Bot().run()
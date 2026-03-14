import socket
import ssl
import time
import logging

logger = logging.getLogger(__name__)


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
        self.private_channels: set[str] = config.get('private_channels', set())
        self.order_trusted_nicks: set[str] = config.get('order_trusted_nicks', set())
        self.members: dict[str, set[str]] = {}
        self.socket: socket = None
        self._buffer: str = ""
        self.joined: bool = False

    def channel_has_nick(self, channel: str, nick: str) -> bool:
        return nick.lower() in {n.lower() for n in self.members.get(channel, set())}

    def connect(self):
        self.joined = False
        while True:
            try:
                logger.info(f"Connecting to: {self.server}:{self.port}")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
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
        except (UnicodeDecodeError, TimeoutError):
            return []
        self._buffer += raw
        lines = self._buffer.split("\n")
        self._buffer = lines[-1]
        return [line.strip() for line in lines[:-1] if line.strip()]

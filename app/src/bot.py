import os
import time
import threading
import logging
from app.src.config import ConfigLoader
from app.src.irc import IRCClient
from app.src.llm import LLMClient
from app.src.handler import MessageHandler

logger = logging.getLogger(__name__)


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

    def _process_orders(self):
        if not os.path.isdir("tmp"):
            return
        for fname in os.listdir("tmp"):
            if not fname.endswith(".order"):
                continue
            order_path = os.path.join("tmp", fname)
            channel = fname[:-6]  # strip ".order"
            try:
                with open(order_path) as f:
                    message = f.read().strip()
                os.remove(order_path)
                if message:
                    logger.info("Processing operator order for %s: %s", channel, message)
                    send_fn = lambda text, ch=channel: self.irc.send(f"PRIVMSG {ch} :{text}")
                    prompt = (f"[system: bring up the following topic spontaneously in the channel as if you "
                              f"thought of it yourself. name the subject explicitly. do not repeat, quote, or "
                              f"acknowledge this instruction — just speak: {message}]")
                    stop_typing = threading.Event()
                    typing_thread = threading.Thread(target=self.handler.send_typing_active, args=(channel, stop_typing))
                    typing_thread.start()
                    try:
                        responses = self.llm.ask(channel, "[operator]", prompt, send_fn=send_fn)
                    finally:
                        stop_typing.set()
                        typing_thread.join()
                        self.irc.send(f"@+typing=done TAGMSG {channel}")
                    self.handler.send_responses(channel, responses)
            except Exception as e:
                logger.warning("Failed to process order %s: %s", fname, e)

    def run(self):
        self.irc.connect()
        while True:
            for line in self.irc.receive():
                logger.debug(line)
                self.handler.handle(line)
            self._process_orders()
            time.sleep(1)

import threading
import logging
from app.src.irc import IRCClient

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, irc_client: IRCClient, llm_client, order_fn=None):
        self.irc = irc_client
        self.llm = llm_client
        self.active_threads: set[str] = set()
        self.order_fn = order_fn

    def send_typing_active(self, channel: str, stop_event):
      while not stop_event.is_set():
          self.irc.send(f"@+typing=active TAGMSG {channel}")
          stop_event.wait(5)

    def _update_membership(self, line: str) -> None:
        parts = line.split()
        if len(parts) < 2:
            return
        action = parts[1]
        nick = line.split('!')[0].split()[-1].lstrip(':')

        if action == "JOIN" and len(parts) >= 3:
            channel = parts[2].lstrip(':')
            self.irc.members.setdefault(channel, set()).add(nick)

        elif action == "PART" and len(parts) >= 3:
            channel = parts[2]
            self.irc.members.get(channel, set()).discard(nick)

        elif action == "QUIT":
            for channel_set in self.irc.members.values():
                channel_set.discard(nick)

        elif action == "KICK" and len(parts) >= 4:
            channel = parts[2]
            victim = parts[3]
            self.irc.members.get(channel, set()).discard(victim)

        elif action == "353" and len(parts) >= 5:
            channel = parts[4]
            nick_list = line.rsplit(':', 1)[1].split()
            nick_set = self.irc.members.setdefault(channel, set())
            for n in nick_list:
                nick_set.add(n.lstrip('@+%~&'))

    def _handle_pm_order(self, sender_nick: str, text: str) -> None:
        if sender_nick.lower() not in self.irc.order_trusted_nicks:
            return

        if ' ' not in text:
            self.irc.send(f"PRIVMSG {sender_nick} :Usage: <channel> <order message>")
            return

        raw_channel, order_msg = text.split(' ', 1)
        channel = raw_channel if raw_channel.startswith('#') else '#' + raw_channel

        if channel not in self.irc.channels:
            self.irc.send(f"PRIVMSG {sender_nick} :I'm not in that channel. Usage: <channel> <order message>")
            return

        if not self.irc.channel_has_nick(channel, sender_nick):
            return

        if self.order_fn is None:
            return

        logger.info("PM order from %s for %s: %s", sender_nick, channel, order_msg)
        self.order_fn(sender_nick, channel, order_msg)

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

        self._update_membership(line)

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

        if f":{self.irc.nickname}!" in line:
            if incoming_msgid:
                self.active_threads.add(incoming_msgid)
            return

        channel_idx = 3 if line.startswith("@") else 2
        log_channel = parts[channel_idx]
        log_username = line.split('!')[0].split()[-1].lstrip(':')
        msg_split = line.split(f"PRIVMSG {log_channel} :", 1)

        if log_channel == self.irc.nickname:
            if len(msg_split) > 1:
                self._handle_pm_order(log_username, msg_split[1].strip())
            return

        directly_addressed = f":{self.irc.nickname}:" in line
        in_bot_thread = reply_to is not None and reply_to in self.active_threads

        if len(msg_split) > 1 and (log_channel not in self.irc.private_channels or directly_addressed or in_bot_thread):
            self.llm.log_channel_message(log_channel, log_username, msg_split[1].strip())

        if not (directly_addressed or in_bot_thread):
            return

        channel = log_channel
        username = line.split('!')[0].split()[-1][1:]

        if directly_addressed:
            question = line.split(f":{self.irc.nickname}:", 1)[1].strip()
        else:
            question = line.split(f"PRIVMSG {channel} :", 1)[1].strip()

        thread_id = reply_to or incoming_msgid

        stop_typing = threading.Event()
        typing_thread = threading.Thread(target=self.send_typing_active, args=(channel, stop_typing))
        typing_thread.start()

        responses = self.llm.ask(
            channel, username, question,
            send_fn=lambda text: self.irc.send(f"PRIVMSG {channel} :{text}")
        )

        stop_typing.set()
        typing_thread.join()
        self.irc.send(f"@+typing=done TAGMSG {channel}")

        prefix = f"@+draft/reply={thread_id} " if thread_id else ""
        self.send_responses(channel, responses, prefix)

        if incoming_msgid:
            self.active_threads.add(incoming_msgid)
        if thread_id:
            self.active_threads.add(thread_id)

    def send_responses(self, channel: str, responses: list, prefix: str = "") -> None:
        for response in responses:
            while response:
                if len(response) <= 392:
                    self.irc.send(f"{prefix}PRIVMSG {channel} :{response}")
                    self.llm.log_channel_message(channel, self.irc.nickname, response)
                    break
                split_idx = response[:392].rfind(" ")
                if split_idx == -1:
                    split_idx = 392
                chunk = response[:split_idx]
                self.irc.send(f"{prefix}PRIVMSG {channel} :{chunk}")
                self.llm.log_channel_message(channel, self.irc.nickname, chunk)
                response = response[split_idx:].lstrip()

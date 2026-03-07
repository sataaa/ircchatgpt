import threading
from app.src.irc import IRCClient


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

        if f":{self.irc.nickname}!" in line:
            if incoming_msgid:
                self.active_threads.add(incoming_msgid)
            return

        channel_idx = 3 if line.startswith("@") else 2
        log_channel = parts[channel_idx]
        log_username = line.split('!')[0].split()[-1].lstrip(':')
        msg_split = line.split(f"PRIVMSG {log_channel} :", 1)

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
                    break
                split_idx = response[:392].rfind(" ")
                if split_idx == -1:
                    split_idx = 392
                self.irc.send(f"{prefix}PRIVMSG {channel} :{response[:split_idx]}")
                response = response[split_idx:].lstrip()

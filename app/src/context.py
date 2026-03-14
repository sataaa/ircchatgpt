import os
import logging

logger = logging.getLogger(__name__)


class ChannelContext:
    def __init__(self, bot_nick: str = ""):
        self.bot_nick = bot_nick
        os.makedirs("tmp", exist_ok=True)

    def log_path(self, channel: str) -> str:
        return f"tmp/{channel}.log"

    def ctx_path(self, channel: str) -> str:
        return f"tmp/{channel}.ctx"

    def cursor_path(self, channel: str) -> str:
        return f"tmp/{channel}.cursor"

    def log_message(self, channel: str, username: str, message: str) -> None:
        lp = self.log_path(channel)
        with open(lp, 'a') as f:
            f.write(f"{username}: {message}\n")
        with open(lp) as f:
            lines = f.readlines()
        if len(lines) > 1000:
            with open(lp, 'w') as f:
                f.writelines(lines[-1000:])

    def update(self, channel: str, session, summarize_fn, send_fn=None) -> str:
        lp = self.log_path(channel)
        cp = self.ctx_path(channel)
        cur_p = self.cursor_path(channel)

        if not os.path.exists(lp):
            return ""

        with open(lp) as f:
            log_lines = f.readlines()

        cursor = 0
        if os.path.exists(cur_p):
            try:
                cursor = int(open(cur_p).read().strip())
            except ValueError:
                cursor = 0
        if cursor >= len(log_lines):
            cursor = max(0, len(log_lines) - 150)

        diff = log_lines[cursor:]
        if not diff:
            return open(cp).read().strip() if os.path.exists(cp) else ""

        if len(diff) > 150:
            catchup = session.send_message(
                "(you have a large backlog of channel messages to read before answering — "
                "tell the channel you're catching up, one short sentence, stay in character)"
            )
            if send_fn:
                send_fn(catchup.text.strip())
            diff = diff[-150:]

        ctx = open(cp).read().strip() if os.path.exists(cp) else ""
        diff_text = "".join(diff).strip()

        nick_hint = f" You are '{self.bot_nick}' in this conversation." if self.bot_nick else ""
        prompt = (
            f"Update this IRC channel context summary.{nick_hint}\n"
            "Rules:\n"
            "- Each bullet ends with [N] where N is its age (number of updates since it was introduced).\n"
            "- Increment every existing bullet's age by 1.\n"
            "- Add new bullets (age [1]) for topics from the new messages not already covered.\n"
            "- Keep max 10 bullets total; drop the oldest/least relevant first.\n"
            "- Output ONLY the bullet list, nothing else.\n\n"
            f"Current context:\n{ctx}\n\nNew messages:\n{diff_text}"
        )
        new_ctx = summarize_fn(prompt)

        with open(cp, 'w') as f:
            f.write(new_ctx)
        with open(cur_p, 'w') as f:
            f.write(str(len(log_lines)))

        logger.info("Channel context updated for %s (%d new lines)", channel, len(diff))
        return new_ctx

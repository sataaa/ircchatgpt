import logging

logger = logging.getLogger(__name__)


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

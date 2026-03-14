import os
import signal
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)
logging.getLogger("google_genai.client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

from app.src.bot import Bot

if __name__ == "__main__":
    os.umask(0o000)
    bot = Bot()

    def _shutdown(signum, frame):
        try:
            bot.irc.send("QUIT :restarting...")
        except Exception:
            pass
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)

    try:
        bot.run()
    except KeyboardInterrupt:
        try:
            bot.irc.send("QUIT :restarting...")
        except Exception:
            pass
    except Exception as e:
        logging.getLogger(__name__).critical("Fatal error: %s", e, exc_info=True)
        try:
            bot.irc.send(f"QUIT :{type(e).__name__}: {e}")
        except Exception:
            pass
        raise

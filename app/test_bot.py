"""
Unit tests for the ircchatgpt bot.

Run inside the container or in an environment with requirements installed:
    python -m pytest app/test_bot.py -v
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.src.llm.base import BaseLLMBackend
from app.src.llm.gemini import GeminiBackend
from app.src.handler import MessageHandler
from app.src.context import ChannelContext

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
_GEMINI_CONFIG = {
    'api_key': 'fake-key',
    'model': 'fake-model',
    'context': 'You are a test bot.',
    'max_output_tokens': 100,
    'temperature': 0.5,
}
_TOOLS_OFF = {
    'enable_weather': False,
    'enable_web_search': False,
    'enable_image_generation': False,
    'imgbb_api_key': '',
}
_TOOLS_ALL = {
    'enable_weather': True,
    'enable_web_search': True,
    'enable_image_generation': True,
    'imgbb_api_key': 'fake-imgbb',
}


def make_backend(tools_config=None, tmpdir=None):
    cfg = tools_config if tools_config is not None else _TOOLS_OFF
    with patch("google.genai.Client"), patch("os.makedirs"):
        ctx = ChannelContext.__new__(ChannelContext)
        b = GeminiBackend(_GEMINI_CONFIG, cfg, ctx)
    if tmpdir:
        ctx.log_path = lambda ch: os.path.join(tmpdir, f"{ch}.log")
        ctx.ctx_path = lambda ch: os.path.join(tmpdir, f"{ch}.ctx")
        ctx.cursor_path = lambda ch: os.path.join(tmpdir, f"{ch}.cursor")
    return b


# ===========================================================================
# BaseLLMBackend._extract_output
# ===========================================================================
class TestExtractOutput(unittest.TestCase):
    def setUp(self):
        self.b = BaseLLMBackend()

    def test_plain_text(self):
        self.assertEqual(self.b._extract_output("hello\nworld"), ["hello", "world"])

    def test_strips_think_block(self):
        content = "<think>\ninner thought\n</think>\nreal answer"
        result = self.b._extract_output(content)
        self.assertNotIn("<think>", result)
        self.assertNotIn("inner thought", result)
        self.assertIn("real answer", result)

    def test_no_think_tags(self):
        self.assertEqual(self.b._extract_output("simple"), ["simple"])

    def test_empty_string(self):
        self.assertEqual(self.b._extract_output(""), [""])

    def test_think_block_inline_with_text(self):
        content = "before <think>\nhidden\n</think>\nafter"
        result = self.b._extract_output(content)
        self.assertIn("after", result)
        self.assertNotIn("hidden", result)


# ===========================================================================
# GeminiBackend._handle_tool_tag
# ===========================================================================
class TestHandleToolTag(unittest.TestCase):
    def setUp(self):
        self.b = make_backend(_TOOLS_ALL)

    def test_no_tag_returns_none(self):
        self.assertIsNone(self.b._handle_tool_tag("just a normal answer"))

    def test_weather_tag_detected(self):
        with patch("app.src.llm.gemini.get_weather", return_value="15°C cloudy"):
            result = self.b._handle_tool_tag("<weather London>")
        self.assertIsNotNone(result)
        self.assertIn("15°C cloudy", result)

    def test_search_tag_detected(self):
        with patch("app.src.llm.gemini.search_web", return_value="result text"):
            result = self.b._handle_tool_tag("<search python tips>")
        self.assertIsNotNone(result)
        self.assertIn("result text", result)

    def test_image_tag_detected(self):
        with patch("app.src.llm.gemini.generate_image", return_value="http://img.example/1.png"):
            result = self.b._handle_tool_tag("<image a cute cat>")
        self.assertIsNotNone(result)
        self.assertIn("http://img.example/1.png", result)

    def test_disabled_weather_returns_none(self):
        b = make_backend(_TOOLS_OFF)
        self.assertIsNone(b._handle_tool_tag("<weather London>"))

    def test_disabled_search_returns_none(self):
        b = make_backend(_TOOLS_OFF)
        self.assertIsNone(b._handle_tool_tag("<search query>"))

    def test_case_insensitive_weather(self):
        with patch("app.src.llm.gemini.get_weather", return_value="sunny"):
            result = self.b._handle_tool_tag("<Weather Paris>")
        self.assertIsNotNone(result)

    def test_image_requires_imgbb_key(self):
        cfg = {**_TOOLS_ALL, 'imgbb_api_key': ''}
        b = make_backend(cfg)
        self.assertIsNone(b._handle_tool_tag("<image a dog>"))


# ===========================================================================
# ChannelContext path helpers
# ===========================================================================
class TestPathHelpers(unittest.TestCase):
    def setUp(self):
        with patch("os.makedirs"):
            self.ctx = ChannelContext()

    def test_log_path(self):
        self.assertEqual(self.ctx.log_path("#chan"), "tmp/#chan.log")

    def test_ctx_path(self):
        self.assertEqual(self.ctx.ctx_path("#chan"), "tmp/#chan.ctx")

    def test_cursor_path(self):
        self.assertEqual(self.ctx.cursor_path("#chan"), "tmp/#chan.cursor")


# ===========================================================================
# ChannelContext.log_message
# ===========================================================================
class TestLogChannelMessage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.b = make_backend(tmpdir=self.tmpdir)

    def test_creates_and_appends(self):
        self.b.log_channel_message("#ch", "alice", "hello")
        self.b.log_channel_message("#ch", "bob", "world")
        with open(self.b.context.log_path("#ch")) as f:
            lines = f.readlines()
        self.assertEqual(lines, ["alice: hello\n", "bob: world\n"])

    def test_format_is_nick_colon_message(self):
        self.b.log_channel_message("#ch", "user", "test message")
        with open(self.b.context.log_path("#ch")) as f:
            content = f.read()
        self.assertEqual(content, "user: test message\n")

    def test_trims_to_1000_lines(self):
        log_path = self.b.context.log_path("#ch")
        with open(log_path, 'w') as f:
            for i in range(1001):
                f.write(f"user: line {i}\n")
        self.b.log_channel_message("#ch", "user", "trigger trim")
        with open(log_path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1000)
        self.assertIn("trigger trim", lines[-1])

    def test_separate_channels_separate_files(self):
        self.b.log_channel_message("#a", "alice", "msg in a")
        self.b.log_channel_message("#b", "bob", "msg in b")
        with open(self.b.context.log_path("#a")) as f:
            self.assertIn("msg in a", f.read())
        with open(self.b.context.log_path("#b")) as f:
            self.assertIn("msg in b", f.read())


# ===========================================================================
# ChannelContext.update
# ===========================================================================
class TestUpdateChannelContext(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.b = make_backend(tmpdir=self.tmpdir)
        summary = MagicMock()
        summary.text = "• topic A\n• topic B"
        self.b.client.models.generate_content.return_value = summary

    def _write_log(self, channel, lines):
        with open(self.b.context.log_path(channel), 'w') as f:
            for line in lines:
                f.write(line + "\n")

    def test_no_log_file_returns_empty(self):
        result = self.b.context.update("#ch", MagicMock(), self.b._summarize)
        self.assertEqual(result, "")

    def test_empty_log_returns_existing_ctx(self):
        open(self.b.context.log_path("#ch"), 'w').close()
        with open(self.b.context.ctx_path("#ch"), 'w') as f:
            f.write("• old context")
        result = self.b.context.update("#ch", MagicMock(), self.b._summarize)
        self.assertEqual(result, "• old context")

    def test_empty_log_no_ctx_returns_empty(self):
        open(self.b.context.log_path("#ch"), 'w').close()
        result = self.b.context.update("#ch", MagicMock(), self.b._summarize)
        self.assertEqual(result, "")

    def test_new_lines_generate_summary(self):
        self._write_log("#ch", ["alice: hello", "bob: world"])
        result = self.b.context.update("#ch", MagicMock(), self.b._summarize)
        self.assertEqual(result, "• topic A\n• topic B")

    def test_cursor_advanced_after_update(self):
        self._write_log("#ch", ["alice: hello", "bob: world"])
        self.b.context.update("#ch", MagicMock(), self.b._summarize)
        with open(self.b.context.cursor_path("#ch")) as f:
            self.assertEqual(f.read(), "2")

    def test_ctx_file_written(self):
        self._write_log("#ch", ["alice: hello"])
        self.b.context.update("#ch", MagicMock(), self.b._summarize)
        with open(self.b.context.ctx_path("#ch")) as f:
            self.assertEqual(f.read(), "• topic A\n• topic B")

    def test_large_backlog_calls_send_fn(self):
        self._write_log("#ch", [f"user: message {i}" for i in range(200)])
        mock_session = MagicMock()
        mock_session.send_message.return_value = MagicMock(text="catching up!")
        send_fn = MagicMock()
        self.b.context.update("#ch", mock_session, self.b._summarize, send_fn=send_fn)
        send_fn.assert_called_once_with("catching up!")

    def test_small_backlog_does_not_call_send_fn(self):
        self._write_log("#ch", [f"user: message {i}" for i in range(10)])
        send_fn = MagicMock()
        self.b.context.update("#ch", MagicMock(), self.b._summarize, send_fn=send_fn)
        send_fn.assert_not_called()


# ===========================================================================
# MessageHandler — logging and routing
# ===========================================================================
class TestMessageHandlerLogging(unittest.TestCase):
    def setUp(self):
        self.irc = MagicMock()
        self.irc.nickname = "TestBot"
        self.irc.channels = ["#test"]
        self.llm = MagicMock()
        self.llm.ask.return_value = []
        self.handler = MessageHandler(self.irc, self.llm)

    def test_logs_ordinary_privmsg(self):
        line = ":alice!alice@host PRIVMSG #test :hello world"
        self.handler.handle(line)
        self.llm.log_channel_message.assert_called_once_with("#test", "alice", "hello world")

    def test_does_not_log_bot_echo(self):
        line = ":TestBot!bot@host PRIVMSG #test :something I said"
        self.handler.handle(line)
        self.llm.log_channel_message.assert_not_called()

    def test_addressed_bot_calls_ask_with_send_fn(self):
        line = ":alice!alice@host PRIVMSG #test :TestBot: hello"
        self.handler.handle(line)
        self.llm.ask.assert_called_once()
        args, kwargs = self.llm.ask.call_args
        self.assertEqual(args[0], "#test")
        self.assertEqual(args[1], "alice")
        self.assertIn("send_fn", kwargs)
        self.assertIsNotNone(kwargs["send_fn"])

    def test_unaddressed_message_does_not_call_ask(self):
        line = ":alice!alice@host PRIVMSG #test :just chatting"
        self.handler.handle(line)
        self.llm.ask.assert_not_called()
        self.llm.log_channel_message.assert_called_once()

    def test_non_privmsg_not_logged(self):
        line = ":server.irc.net 001 TestBot :Welcome to IRC"
        self.handler.handle(line)
        self.llm.log_channel_message.assert_not_called()

    def test_ping_not_logged(self):
        self.handler.handle("PING :server.irc.net")
        self.llm.log_channel_message.assert_not_called()

    def test_tagged_privmsg_logged(self):
        line = "@msgid=abc :alice!alice@host PRIVMSG #test :hello"
        self.handler.handle(line)
        self.llm.log_channel_message.assert_called_once_with("#test", "alice", "hello")

    def test_send_fn_sends_to_correct_channel(self):
        line = ":alice!alice@host PRIVMSG #test :TestBot: hello"
        self.handler.handle(line)
        _, kwargs = self.llm.ask.call_args
        send_fn = kwargs["send_fn"]
        send_fn("test response")
        self.irc.send.assert_called_with("PRIVMSG #test :test response")


# ===========================================================================
# tools
# ===========================================================================
from app.src.tools import search_web, get_weather


class TestSearchWeb(unittest.TestCase):
    @patch("app.src.tools.DDGS")
    def test_returns_formatted_results(self, mock_ddgs):
        mock_ddgs.return_value.text.return_value = [
            {"title": "Python", "body": "A great language"},
            {"title": "Docs", "body": "Full documentation"},
        ]
        result = search_web("python")
        self.assertIn("Python", result)
        self.assertIn("A great language", result)
        self.assertIn("Docs", result)

    @patch("app.src.tools.DDGS")
    def test_no_results(self, mock_ddgs):
        mock_ddgs.return_value.text.return_value = []
        self.assertEqual(search_web("nothing here"), "No results found.")

    @patch("app.src.tools.DDGS")
    def test_exception_returns_error_string(self, mock_ddgs):
        mock_ddgs.return_value.text.side_effect = Exception("network error")
        result = search_web("query")
        self.assertIn("Search failed", result)

    @patch("app.src.tools.DDGS")
    def test_results_separated_by_pipe(self, mock_ddgs):
        mock_ddgs.return_value.text.return_value = [
            {"title": "A", "body": "body A"},
            {"title": "B", "body": "body B"},
        ]
        result = search_web("test")
        self.assertIn(" | ", result)


class TestGetWeather(unittest.TestCase):
    @patch("app.src.tools.requests.get")
    def test_city_not_found(self, mock_get):
        mock_get.return_value.json.return_value = {"results": []}
        result = get_weather("Faketown")
        self.assertIn("not found", result)

    @patch("app.src.tools.requests.get")
    def test_returns_weather_string(self, mock_get):
        geo = MagicMock()
        geo.json.return_value = {
            "results": [{"name": "London", "country": "GB", "latitude": 51.5, "longitude": -0.1}]
        }
        wx = MagicMock()
        wx.json.return_value = {
            "current": {
                "temperature_2m": 15.0,
                "apparent_temperature": 13.0,
                "relative_humidity_2m": 70,
                "wind_speed_10m": 20.0,
                "weather_code": 3,
            }
        }
        mock_get.side_effect = [geo, wx]
        result = get_weather("London")
        self.assertIn("London", result)
        self.assertIn("15.0°C", result)
        self.assertIn("Overcast", result)
        self.assertIn("70%", result)

    @patch("app.src.tools.requests.get")
    def test_unknown_weather_code_shows_code(self, mock_get):
        geo = MagicMock()
        geo.json.return_value = {
            "results": [{"name": "X", "country": "Y", "latitude": 0, "longitude": 0}]
        }
        wx = MagicMock()
        wx.json.return_value = {
            "current": {
                "temperature_2m": 20.0,
                "apparent_temperature": 20.0,
                "relative_humidity_2m": 50,
                "wind_speed_10m": 10.0,
                "weather_code": 999,
            }
        }
        mock_get.side_effect = [geo, wx]
        result = get_weather("X")
        self.assertIn("Code 999", result)

    @patch("app.src.tools.requests.get")
    def test_exception_returns_error_string(self, mock_get):
        mock_get.side_effect = Exception("timeout")
        result = get_weather("Anywhere")
        self.assertIn("failed", result)


if __name__ == "__main__":
    unittest.main()

# ircchatgpt

An IRC bot that connects to LLM APIs (Gemini, OpenAI, or local servers) to answer
questions in IRC channels. Mention the bot's nickname to get a response.

## Prerequisites

- [Podman](https://podman.io/getting-started/installation) (recommended) or [Docker](https://docs.docker.com/get-docker/)
- A [Gemini API key](https://aistudio.google.com/app/apikey) (free tier is sufficient)

## Configuration

Copy the example config and fill in your details:

    cp example-chat.conf chat.conf

Edit `chat.conf` — minimum required fields:

| Section | Key | Description |
|---------|-----|-------------|
| `[provider]` | `backend` | `gemini`, `openai`, or `local` |
| `[gemini]` | `api_key` | Your Gemini API key |
| `[gemini]` | `model` | e.g. `gemma-3-27b-it` |
| `[irc]` | `server` | IRC server hostname |
| `[irc]` | `channels` | Comma-separated channel list |
| `[irc]` | `nickname` | Bot's IRC nickname |

See `example-chat.conf` for all available options.

## Running

The recommended way is `run.sh`, which stops any existing container, rebuilds
the image, and starts it in the background:

    ./run.sh

Channel logs and context files are written to `tmp/` in the working directory
and can be read while the bot is running:

    tail -f tmp/'#yourchannel.log'   # raw message log
    cat  tmp/'#yourchannel.ctx'      # current context summary
    cat  tmp/'#yourchannel.cursor'   # line count at last context update

### Manual Podman

    podman build -t ircchatgpt .
    podman run -d --name ircchatgpt --restart unless-stopped \
      -v $(pwd)/chat.conf:/app/chat.conf \
      -v $(pwd)/tmp:/app/tmp \
      ircchatgpt

    podman logs -f ircchatgpt

### Docker

    docker build -t ircchatgpt .
    docker run -d --name ircchatgpt --restart unless-stopped \
      -v $(pwd)/chat.conf:/app/chat.conf \
      -v $(pwd)/tmp:/app/tmp \
      ircchatgpt

## Interaction

The bot responds when you mention its nickname in a channel:

    10:31:12 <knrd1> MyBot: hello, how are you?
    10:31:14 <MyBot> Hi! I'm doing well, thanks. How about you?

    10:35:56 <knrd1> MyBot: what is the capital of Brazil?
    10:35:59 <MyBot> The capital of Brazil is Brasília.

The bot also passively reads all channel messages and maintains a rolling
context summary, so it understands ongoing conversations even when not addressed.

To reset the conversation history for the current channel:

    <knrd1> MyBot: clear chat

## Tools

Optional tools can be enabled in `[tools]`. When active, the bot can look up
weather, search the web, and generate images on request.

| Tool | Config key | Requires |
|------|-----------|---------|
| Weather | `enable_weather = true` | nothing (open-meteo) |
| Web search | `enable_web_search = true` | nothing (DuckDuckGo) |
| Image generation | `enable_image_generation = true` | `imgbb_api_key` + Gemini |

When a tool is used, the bot presents the result naturally without announcing it.

## Tests

    # Inside the container
    podman exec ircchatgpt /app/venv/bin/python -m pytest test_bot.py -v

    # Or locally with requirements installed
    pip install -r requirements.txt
    python -m pytest test_bot.py -v

## Configuration Reference

### [provider]
| Key | Values |
|-----|--------|
| `backend` | `gemini` \| `openai` \| `local` |

### [gemini]
| Key | Description |
|-----|-------------|
| `api_key` | Gemini API key from Google AI Studio |
| `model` | Model for chat responses (e.g. `gemini-2.0-flash`) |
| `summarize_model` | Model for background context summarization (e.g. `gemma-3-27b-it`) |
| `context` | System prompt / bot personality |
| `max_output_tokens` | Max tokens in response (default: `1000`) |
| `temperature` | Randomness 0.0–1.0 (default: `0.8`) |

### [openai]
| Key | Description |
|-----|-------------|
| `api_key` | OpenAI API key |
| `model` | Model name (e.g. `gpt-4o-mini`) |
| `context` | System prompt |
| `max_tokens` | Max tokens in response |
| `temperature` | Randomness 0.0–1.0 |

### [localserver]
| Key | Description |
|-----|-------------|
| `target_ip` | Local server IP (e.g. `127.0.0.1`) |
| `local_port` | Port (e.g. `55511`) |
| `mapping` | API path (e.g. `/v1/chat/completions`) |
| `context` | System prompt |
| `max_tokens` | Max tokens in response |
| `temperature` | Randomness 0.0–1.0 |

### [irc]
| Key | Description |
|-----|-------------|
| `server` | IRC server hostname |
| `port` | Port (default: `6667`) |
| `ssl` | `true` or `false` |
| `channels` | Comma-separated list (e.g. `#linux,#chat`) |
| `nickname` | Bot's nick |
| `ident` | Ident string |
| `realname` | Real name string |
| `password` | Server password (leave blank if none) |
| `private_channels` | Comma-separated channels to exclude from passive logging |

### [tools]
| Key | Description |
|-----|-------------|
| `enable_web_search` | `true` / `false` — DuckDuckGo search |
| `enable_weather` | `true` / `false` — current weather via open-meteo |
| `enable_image_generation` | `true` / `false` — image gen via Gemini + imgbb |
| `imgbb_api_key` | [imgbb](https://api.imgbb.com/) API key (required for image gen) |

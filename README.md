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

## Running with Podman (recommended)

Podman runs rootless with no background daemon — ideal for Linux and WSL2.

    # Install on Ubuntu/Debian (including WSL)
    sudo apt install podman

    # Build
    podman build -t ircchatgpt .

    # Run (foreground)
    podman run -it --rm -v $(pwd)/chat.conf:/app/chat.conf ircchatgpt

    # Run in background
    podman run -d --name ircchatgpt --restart unless-stopped \
      -v $(pwd)/chat.conf:/app/chat.conf ircchatgpt

## Running with Docker

    docker build -t ircchatgpt .
    docker run -it --rm -v $(pwd)/chat.conf:/app/chat.conf ircchatgpt

    # Background
    docker run -d --name ircchatgpt --restart unless-stopped \
      -v $(pwd)/chat.conf:/app/chat.conf ircchatgpt

## Interaction

The bot responds when you mention its nickname in a channel:

    10:31:12 <knrd1> MyBot: hello, how are you?
    10:31:14 <MyBot> Hi! I'm doing well, thanks. How about you?

    10:35:56 <knrd1> MyBot: what is the capital of Brazil?
    10:35:59 <MyBot> The capital of Brazil is Brasília.

To reset the conversation history for the current channel:

    <knrd1> MyBot: clear chat

## Configuration Reference

### [provider]
| Key | Values | Default |
|-----|--------|---------|
| `backend` | `gemini` \| `openai` \| `local` | `gemini` |

### [gemini]
| Key | Description |
|-----|-------------|
| `api_key` | Gemini API key from Google AI Studio |
| `model` | Model name (e.g. `gemma-3-27b-it`) |
| `context` | System prompt for the bot's personality |
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

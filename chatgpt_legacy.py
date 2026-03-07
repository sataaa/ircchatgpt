# =============================================================================
# LEGACY FILE — Do not use, do not add features here.
# Superseded by ai-irc-bot.py (formerly refactoredircchatgpt.py).
# Kept temporarily as reference for DALL-E and completion model logic.
# Will be deleted after feature parity is confirmed in ai-irc-bot.py.
# =============================================================================
import openai
import socket
import ssl
import time
import configparser
import pyshorteners
import requests
import json
import re
from typing import Union, Tuple

# Read configuration from file
config = configparser.ConfigParser()
config.read('chat.conf')

# Set up local server
target_ip = config.get('localserver', 'target_ip')
local_port = config.get('localserver', 'local_port')
mapping = config.get('localserver', 'mapping')
use_local_server = config.getboolean('localserver', 'use_local_server')
url = f"http://{target_ip}:{local_port}{mapping}"

# Set up OpenAI API key
if not use_local_server:
    openai.api_key = config.get('openai', 'api_key')

# Set up ChatCompletion parameters
model = config.get('chatcompletion', 'model')
role = config.get('chatcompletion', 'role')
temperature =  config.getfloat('chatcompletion', 'temperature')
max_tokens = config.getint('chatcompletion', 'max_tokens')
top_p = config.getint('chatcompletion', 'top_p')
frequency_penalty = config.getint('chatcompletion', 'frequency_penalty')
presence_penalty = config.getint('chatcompletion', 'presence_penalty')
request_timeout = config.getint('chatcompletion', 'request_timeout')
context = config.get('chatcompletion', 'context')

# Set up IRC connection settings
server = config.get('irc', 'server')
port = config.getint('irc', 'port')
usessl = config.getboolean('irc', 'ssl')
channels = config.get('irc', 'channels').split(',')
nickname = config.get('irc', 'nickname')
ident = config.get('irc', 'ident')
realname = config.get('irc', 'realname')
password = config.get('irc', 'password')

# Define the list of models
completion_models = ["gpt-3.5-turbo-instruct", "babbage-002", "davinci-002"]
chatcompletion_models = ["gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-4-turbo", "gpt-4-turbo-preview", "gpt-3.5-turbo"]
images_models = ["dall-e-2", "dall-e-3"]

def sendirc(irc, servercommand):
    print("> " + servercommand)
    irc.send(bytes(servercommand, "UTF-8"))
    return

# Connect to IRC server
def connect(server, port, usessl, password, ident, realname, nickname, channels):
    while True:
        try:
            print("Connecting to: " + server)
            irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            irc.connect((server, port))
            if usessl:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                irc = context.wrap_socket(irc, server_hostname=server)
            if password:
                sendirc(irc, "PASS " + password + "\n")
            sendirc(irc, "USER " + ident + " 0 * :" + realname + "\n")
            sendirc(irc, "NICK " + nickname + "\n")
            sendirc(irc, "CAP REQ :message-tags\n")
            sendirc(irc, "CAP END\n")
            print("Connected to: " + server)

            return irc
        except:
            print("Connection failed. Retrying in 5 seconds...")
            time.sleep(5)

irc = connect(server, port, usessl, password, ident, realname, nickname, channels)

accumulated_messages = [{'role': 'system', 'content': context }]
local_data = {
    'messages': accumulated_messages, 
    'temperature': temperature,
    'max_tokens': max_tokens,
    'stream': False
}
headers = { 'Content-Type': 'application/json' }

def get_llm_response(username, question):
    if (question.endswith("clear chat")):
        local_data["messages"] = [{'role': 'system', 'content': context }]
        return ["cleared log"]
    local_data["messages"].append({'role':'user', 'content': f'<{username}> {question}'})
    print("sending json:" + json.dumps(local_data))
    response = requests.post(url, headers=headers, json=local_data, stream=False)
    response.raise_for_status()
    
    content = response.json()['choices'][0]['message']['content']
    local_data["messages"].append({'role':'assistant', 'content': content})
    output = extract_output_print_thought(content)
    return output

def extract_output_print_thought(content):
    inside_think = False
    output = []
    thought = []
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
        print("Thought: " + '\n'.join(thought))
    return output



# Listen for messages from users and answer questions
while True:
    try:
        data = irc.recv(8192).decode("UTF-8")
        if data:
            print(data)
    except UnicodeDecodeError:
        continue
    except:
        print("Connection lost. Reconnecting...")
        time.sleep(5)
        irc = connect(server, port, usessl, password, ident, realname, nickname, channels)
    serverlines = data.split("\n")
    for server_line in serverlines:
        chunk = server_line.split()
        print("--- Looking at line: " + server_line)
        if len(chunk) > 0:
            if server_line.startswith(":"):
                command = chunk[1]
            elif server_line.startswith("@") and chunk[1].startswith(":"):
                command = chunk[2]
            else:
                command = chunk[0]
            if command == "PING":
                sendirc(irc, "PONG " + chunk[1] + "\n")
                sendirc(irc, "JOIN " + ",".join(channels) + "\n")
            elif command == "ERROR":
                print("Received ERROR from server. Reconnecting...")
                time.sleep(5)
                irc = connect(server, port, usessl, password, ident, realname, nickname, channels)
            elif command == "471" or command == "473" or command == "474" or command == "475":
                print("Unable to join " + chunk[3] + ": Channel can be full, invite only, bot is banned or needs a key.")
            elif command == "KICK" and chunk[3] == nickname:
                irc.send(bytes("JOIN " + chunk[2] + "\n", "UTF-8"))
                print("Kicked from channel " + chunk[2] + ". Rejoining...")
            elif command == "INVITE":
                if server_line.split(" :")[1].strip() in channels:
                    sendirc(irc, "JOIN " + server_line.split(" :")[1].strip() + "\n")
                    print("Invited into channel " + server_line.split(" :")[1].strip() + ". Joining...")
            elif command == "PRIVMSG" and chunk[3].startswith("#") and chunk[4] == ":" + nickname + ":":
                if use_local_server:
                    channel = chunk[3].strip()
                    question = server_line.split(nickname + ":")[1].strip()
                    username = server_line.split('!')[0].split()[1][1:]
                    sendirc(irc, "@+typing=active TAGMSG " + channel + "\n")
                    response = get_llm_response(username, question)
                    sendirc(irc, "@+typing=done TAGMSG " + channel + "\n")
                    tags_part = chunk[0][2:].split(" ", 1)[0]
                    tag_dict = dict(tag.split("=", 1) for tag in tags_part.split(";") if "=" in tag)
                    msgid = tag_dict.get("draft/reply") or tag_dict.get("msgid")
                    for answer in response:
                        if len(answer) <= 392:
                            sendirc(irc, "@+draft/reply=" + msgid + " PRIVMSG " + channel + " :" + answer + "\n")
                            answer = ""
                        else:
                            last_space_index = answer[:392].rfind(" ")
                            if last_space_index == -1:
                                last_space_index = 392
                            sendirc(irc, "@+draft/reply=" + msgid + " PRIVMSG " + channel + " :" + answer[:last_space_index] + "\n")
                            answer = answer[last_space_index:].lstrip()
                else:
                    channel = chunk[2].strip()
                    question = server_line.split(nickname + ":")[1].strip()
                    if model in chatcompletion_models:
                        try:
                            response = openai.ChatCompletion.create(
                                model=model,
                                messages=[{"role": "system", "content": context}, {"role": "user", "content": question}],
                                temperature=temperature,
                                max_tokens=max_tokens,
                                top_p=top_p,
                                frequency_penalty=frequency_penalty,
                                presence_penalty=presence_penalty,
                                request_timeout=request_timeout
                            )
                            answers = [x.strip() for x in response.choices[0].message.content.strip().split('\n')]
                            for answer in answers:
                                while len(answer) > 0:
                                    if len(answer) <= 392:
                                        sendirc(irc, "PRIVMSG " + channel + " :" + answer + "\n")
                                        answer = ""
                                    else:
                                        last_space_index = answer[:392].rfind(" ")
                                        if last_space_index == -1:
                                            last_space_index = 392
                                        sendirc(irc, "PRIVMSG " + channel + " :" + answer[:last_space_index] + "\n")
                                        answer = answer[last_space_index:].lstrip()
                        except openai.error.Timeout as e:
                            print("Error: " + str(e))
                            sendirc(irc, "PRIVMSG " + channel + " :API call timed out. Try again later.\n")
                        except openai.error.OpenAIError as e:
                            print("Error: " + str(e))
                            sendirc(irc, f"PRIVMSG {channel} :API call failed. {str(e)}\n")
                        except Exception as e:
                            print("Error: " + str(e))
                            sendirc(irc, f"PRIVMSG {channel} :An unexpected error occurred. {str(e)}\n")
                    elif model in completion_models:
                        try:
                            response = openai.Completion.create(
                                model=model,
                                prompt="Q: " + question + "\nA:",
                                temperature=temperature,
                                max_tokens=max_tokens,
                                top_p=top_p,
                                frequency_penalty=frequency_penalty,
                                presence_penalty=presence_penalty,
                                request_timeout=request_timeout
                            )
                            answers = [x.strip() for x in response.choices[0].text.strip().split('\n')]
                            for answer in answers:
                                while len(answer) > 0:
                                    if len(answer) <= 392:
                                        sendirc(irc, "PRIVMSG " + channel + " :" + answer + "\n")
                                        answer = ""
                                    else:
                                        last_space_index = answer[:392].rfind(" ")
                                        if last_space_index == -1:
                                            last_space_index = 392
                                        sendirc(irc, "PRIVMSG " + channel + " :" + answer[:last_space_index] + "\n")
                                        answer = answer[last_space_index:].lstrip()
                        except openai.error.Timeout as e:
                            print("Error: " + str(e))
                            sendirc(irc, "PRIVMSG " + channel + " :API call timed out. Try again later.\n")
                        except openai.error.OpenAIError as e:
                            print("Error: " + str(e))
                            sendirc(irc, f"PRIVMSG {channel} :API call failed. {str(e)}\n")
                        except Exception as e:
                            print("Error: " + str(e))
                            sendirc(irc, f"PRIVMSG {channel} :An unexpected error occurred. {str(e)}\n")
                    elif model in images_models:
                        try:
                            response = openai.Image.create(
                            prompt="Q: " + question + "\nA:",
                            n=1,
                            size="1024x1024"
                            )
                            long_url = response.server_line[0].url
                            type_tiny = pyshorteners.Shortener()
                            short_url = type_tiny.tinyurl.short(long_url)
                            sendirc(irc, "PRIVMSG " + channel + " :" + short_url + "\n")
                        except openai.error.Timeout as e:
                            print("Error: " + str(e))
                            sendirc(irc, "PRIVMSG " + channel + " :API call timed out. Try again later.\n")
                        except openai.error.OpenAIError as e:
                            print("Error: " + str(e))
                            sendirc(irc, f"PRIVMSG {channel} :API call failed. {str(e)}\n")
                        except Exception as e:
                            print("Error: " + str(e))
                            sendirc(irc, f"PRIVMSG {channel} :An unexpected error occurred. {str(e)}\n")
                    else:
                        print("Invalid model.")
                        sendirc(irc, "PRIVMSG " + channel + " :Invalid model.\n")
                        continue
        else:
            continue
    time.sleep(1)

import configparser


class ConfigLoader:
    def __init__(self, path='chat.conf'):
        config = configparser.ConfigParser()
        config.read(path)
        self.config = config

    def get_irc_config(self):
        return {
            'server': self.config.get('irc', 'server'),
            'port': self.config.getint('irc', 'port'),
            'ssl': self.config.getboolean('irc', 'ssl'),
            'channels': self.config.get('irc', 'channels').split(','),
            'nickname': self.config.get('irc', 'nickname'),
            'ident': self.config.get('irc', 'ident'),
            'realname': self.config.get('irc', 'realname'),
            'password': self.config.get('irc', 'password'),
            'private_channels': {c.strip() for c in self.config.get('irc', 'private_channels', fallback='').split(',') if c.strip()},
            'order_trusted_nicks': {n.strip().lower() for n in self.config.get('irc', 'order_trusted_nicks', fallback='').split(',') if n.strip()},
        }

    def get_provider(self) -> str:
        return self.config.get('provider', 'backend')

    def get_gemini_config(self) -> dict:
        return {
            'api_key': self.config.get('gemini', 'api_key'),
            'model': self.config.get('gemini', 'model'),
            'summarize_model': self.config.get('gemini', 'summarize_model'),
            'context': self.config.get('gemini', 'context'),
            'max_output_tokens': self.config.getint('gemini', 'max_output_tokens'),
            'temperature': self.config.getfloat('gemini', 'temperature'),
        }

    def get_openai_config(self) -> dict:
        return {
            'api_key': self.config.get('openai', 'api_key'),
            'model': self.config.get('openai', 'model'),
            'context': self.config.get('openai', 'context'),
            'max_tokens': self.config.getint('openai', 'max_tokens'),
            'temperature': self.config.getfloat('openai', 'temperature'),
        }

    def get_local_config(self) -> dict:
        return {
            'target_ip': self.config.get('localserver', 'target_ip'),
            'local_port': self.config.get('localserver', 'local_port'),
            'mapping': self.config.get('localserver', 'mapping'),
            'context': self.config.get('localserver', 'context'),
            'max_tokens': self.config.getint('localserver', 'max_tokens'),
            'temperature': self.config.getfloat('localserver', 'temperature'),
        }

    def get_tools_config(self) -> dict:
        return {
            'enable_web_search': self.config.getboolean('tools', 'enable_web_search'),
            'enable_weather': self.config.getboolean('tools', 'enable_weather'),
            'enable_image_generation': self.config.getboolean('tools', 'enable_image_generation'),
            'imgbb_api_key': self.config.get('tools', 'imgbb_api_key'),
        }

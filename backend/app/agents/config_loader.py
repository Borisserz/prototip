import os

import yaml
from pydantic import BaseModel


class AgentConfig(BaseModel):
    role: str
    goal: str
    rules: str
    few_shot: str | None = ""

class ConfigLoader:
    def __init__(self, config_path: str = None):
        if not config_path:
            # Assuming this script is in app/agents/
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "agents.yaml")
        self.config_path = config_path
        self._cache = {}
        self._last_mtime = 0.0

    def load_config(self) -> dict:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
            
        current_mtime = os.path.getmtime(self.config_path)
        if current_mtime > self._last_mtime or not self._cache:
            with open(self.config_path, encoding='utf-8') as f:
                self._cache = yaml.safe_load(f)
            self._last_mtime = current_mtime
            
        return self._cache

    def get_agent_config(self, agent_name: str) -> AgentConfig:
        config = self.load_config()
        if agent_name not in config:
            raise KeyError(f"Agent '{agent_name}' not found in configuration.")
        return AgentConfig(**config[agent_name])

# Global instance for easy import
config_loader = ConfigLoader()

def get_agent_config(agent_name: str) -> AgentConfig:
    return config_loader.get_agent_config(agent_name)

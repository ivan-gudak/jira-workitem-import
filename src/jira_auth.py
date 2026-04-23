"""
Jira authentication module.
Reads .jira.config from the current working directory (project root).
"""

import os
from jira import JIRA


class JiraAuth:
    """Handles Jira authentication using .jira.config or environment variables."""

    def __init__(self, config_file: str = None):
        if config_file is None:
            config_file = os.path.join(os.getcwd(), ".jira.config")

        self.config_file = os.path.abspath(config_file)
        self._load_config()

    def _load_config(self):
        self.token = os.getenv("JIRA_TOKEN")
        self.server = os.getenv("JIRA_SERVER")
        self.email = os.getenv("JIRA_EMAIL")

        if not all([self.token, self.server, self.email]):
            self._read_config_file()

    def _read_config_file(self):
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(
                f"Jira config file not found: {self.config_file}\n"
                "Create .jira.config in the project root or set env vars:\n"
                "  JIRA_SERVER, JIRA_EMAIL, JIRA_TOKEN"
            )

        with open(self.config_file, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("SERVER:"):
                    self.server = line.split("SERVER:", 1)[1].strip()
                elif line.startswith("EMAIL:"):
                    self.email = line.split("EMAIL:", 1)[1].strip()
                elif line.startswith("TOKEN:"):
                    self.token = line.split("TOKEN:", 1)[1].strip()

        if not all([self.token, self.server, self.email]):
            raise ValueError("Incomplete .jira.config. Required: SERVER, EMAIL, TOKEN")

    def get_jira_client(self) -> JIRA:
        return JIRA(server=self.server, basic_auth=(self.email, self.token))

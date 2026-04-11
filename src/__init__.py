"""Package initialisation: shared HTTP session, logging, and environment config."""

import logging
import os

from curl_cffi import requests
from curl_cffi.requests.impersonate import DEFAULT_CHROME
from github import Github

session = requests.Session(impersonate=DEFAULT_CHROME)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

gh = Github(GITHUB_TOKEN) if GITHUB_TOKEN else Github()

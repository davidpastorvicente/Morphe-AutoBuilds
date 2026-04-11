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
REPOSITORY = os.getenv("GITHUB_REPOSITORY")
ENDPOINT_URL = os.getenv("ENDPOINT_URL")
ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BUCKET_NAME = os.getenv("BUCKET_NAME")

BASE_URL = "https://www.apkmirror.com"
gh = Github(GITHUB_TOKEN) if GITHUB_TOKEN else Github()

#!/usr/bin/env python3

import base64
import datetime
import json
import logging
import math
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' is not installed. Run: pip install requests")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('alive')



ANCHOR_DATE = datetime.date(2012, 9, 9)


def base_commits(days_since_anchor: int, day_of_week: int) -> int:
    t = days_since_anchor / 7.0
    d = day_of_week

    w1 = math.sin(2 * math.pi * t / 26 + 0.0)
    w2 = math.sin(2 * math.pi * t / 13 + 1.5)
    w3 = math.sin(2 * math.pi * t / 52 + 0.8)
    w4 = math.sin(2 * math.pi * d / 7 + t * 0.4)
    w5 = math.sin(2 * math.pi * (t * 1.3 + d) / 9)

    combined = w1 * 0.40 + w2 * 0.20 + w3 * 0.15 + w4 * 0.15 + w5 * 0.10
    count = round(3 + (combined + 1) * 18.5)
    return max(1, min(40, count))


def get_base_commits(today: datetime.date) -> int:
    days = (today - ANCHOR_DATE).days
    dow = today.isoweekday() % 7
    return base_commits(days, dow)



def load_config() -> dict:
    config = {
        'github_token': '',
        'github_user': '',
        'alive_repo': 'alive',
        'alive_repo_owner': '',
    }

    script_dir = Path(__file__).parent
    config_path = script_dir / 'config.json'
    if config_path.exists():
        with open(config_path) as f:
            file_config = json.load(f)
        config.update(file_config)
        log.debug(f"Loaded config from {config_path}")

    token = os.environ.get('ALIVE_GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        config['github_token'] = token

    for env_key, cfg_key in [('GITHUB_USER', 'github_user'), ('GITHUB_REPO', 'alive_repo')]:
        if os.environ.get(env_key):
            config[cfg_key] = os.environ[env_key]
    if os.environ.get('ALIVE_REPO_OWNER'):
        config['alive_repo_owner'] = os.environ['ALIVE_REPO_OWNER']

    if not config['github_token']:
        log.error("Missing GITHUB_TOKEN.")
        sys.exit(1)
    if not config['github_user']:
        log.error("Missing GITHUB_USER.")
        sys.exit(1)

    return config



class GitHubAPI:

    BASE = 'https://api.github.com'

    def __init__(self, token: str, user: str, user_id: int | None = None, repo_owner: str | None = None):
        self.user = user
        self.repo_owner = repo_owner or user
        self.user_id = user_id
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })

    def get_user_id(self) -> int:
        if self.user_id:
            return self.user_id
        data = self._get('/user')
        self.user_id = data['id']
        return self.user_id

    def get_noreply_email(self) -> str:
        uid = self.get_user_id()
        return f'{uid}+{self.user}@users.noreply.github.com'

    def _get(self, path: str, params: dict = None, extra_headers: dict = None) -> dict | list:
        url = f'{self.BASE}{path}'
        headers = {}
        if extra_headers:
            headers.update(extra_headers)
        resp = self.session.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: dict) -> dict:
        url = f'{self.BASE}{path}'
        resp = self.session.put(url, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def count_real_commits(self, date_str: str, alive_repo: str) -> int:
        query = f'author:{self.user} committer-date:{date_str}'
        params = {'q': query, 'per_page': 1}
        extra_headers = {'Accept': 'application/vnd.github.cloak-preview+json'}
        try:
            data = self._get('/search/commits', params=params, extra_headers=extra_headers)
            return data.get('total_count', 0)
        except requests.HTTPError:
            return 0

    def get_file(self, repo: str, file_path: str) -> dict:
        return self._get(f'/repos/{self.repo_owner}/{repo}/contents/{file_path}')

    def create_or_update_file(
        self,
        repo: str,
        file_path: str,
        content: str,
        message: str,
        sha: str | None,
        author_date: str,
    ) -> dict:
        encoded = base64.b64encode(content.encode()).decode()
        noreply = self.get_noreply_email()
        data = {
            'message': message,
            'content': encoded,
            'committer': {
                'name': self.user,
                'email': noreply,
                'date': author_date,
            },
            'author': {
                'name': self.user,
                'email': noreply,
                'date': author_date,
            },
        }
        if sha:
            data['sha'] = sha
        return self._put(f'/repos/{self.repo_owner}/{repo}/contents/{file_path}', data)



def make_commits(api: GitHubAPI, repo: str, count: int, date_str: str) -> None:
    log.info(f"Making {count} commit(s) to {api.repo_owner}/{repo} for {date_str}...")

    base_dt = datetime.datetime.strptime(date_str, '%Y-%m-%d').replace(
        hour=0, minute=0, second=0
    )

    existing = api.get_file(repo, 'alive.md')
    current_sha = existing.get('sha')

    for i in range(count):
        minutes = int(i * 1440 / count)
        commit_dt = base_dt + datetime.timedelta(minutes=minutes)
        ts = commit_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        content = f"alive: {date_str} #{i + 1}"
        message = f"alive: {date_str} #{i + 1}"

        result = api.create_or_update_file(
            repo=repo,
            file_path='alive.md',
            content=content,
            message=message,
            sha=current_sha,
            author_date=ts,
        )

        new_content = result.get('content', {})
        current_sha = new_content.get('sha', current_sha)

        log.info(f"  [{i + 1}/{count}] {message}")

        if i < count - 1:
            time.sleep(0.5)



def main():
    log.info("=== github-alive starting ===")

    config = load_config()
    token = config['github_token']
    user = config['github_user']
    repo = config['alive_repo']

    log.info(f"User: {user}  |  Repo: {repo}")

    today = datetime.date.today()
    date_str = today.isoformat()

    base = get_base_commits(today)
    log.info(f"Today: {date_str}  |  Pattern target: {base} commits")

    api = GitHubAPI(token=token, user=user, repo_owner=config.get('alive_repo_owner') or user)

    real = api.count_real_commits(date_str, repo)
    log.info(f"Commits today (all repos, incl. {repo}): {real}")

    delta = max(0, base - real)
    log.info(f"Commits to make: {delta}")

    if delta == 0:
        log.info("Already at or above pattern target. Nothing to do.")
        return

    make_commits(api, repo, delta, date_str)
    log.info(f"=== Done! Made {delta} commit(s). ===")


if __name__ == '__main__':
    main()

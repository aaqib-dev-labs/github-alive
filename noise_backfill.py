#!/usr/bin/env python3

import base64
import datetime
import json
import logging
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
log = logging.getLogger('noise_backfill')

NOISE_DAYS = {2, 4, 6, 7}
START_DATE = datetime.date(2025, 3, 6)
END_DATE = datetime.date(2026, 3, 4)



def noise_count(d: datetime.date) -> int:
    h = (d.toordinal() * 2654435761 + 1234567) & 0xFFFFFFFF
    return 1 + (h % 3)


def load_config() -> dict:
    config = {'github_token': '', 'github_user': '', 'alive_repo': 'alive'}
    cfg_path = Path(__file__).parent / 'config.json'
    if cfg_path.exists():
        with open(cfg_path) as f:
            config.update(json.load(f))
    token = os.environ.get('ALIVE_GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        config['github_token'] = token
    for env_key, cfg_key in [('GITHUB_USER', 'github_user'), ('GITHUB_REPO', 'alive_repo')]:
        if os.environ.get(env_key):
            config[cfg_key] = os.environ[env_key]
    if not config['github_token']:
        sys.exit(1)
    if not config['github_user']:
        sys.exit(1)
    return config



class GitHubAPI:
    BASE = 'https://api.github.com'

    def __init__(self, token: str, user: str):
        self.user = user
        self._user_id: int | None = None
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })

    def get_user_id(self) -> int:
        if self._user_id:
            return self._user_id
        resp = self.session.get(f'{self.BASE}/user', timeout=30)
        resp.raise_for_status()
        self._user_id = resp.json()['id']
        return self._user_id

    def get_noreply_email(self) -> str:
        return f'{self.get_user_id()}+{self.user}@users.noreply.github.com'

    def get_file(self, repo: str, path: str) -> dict:
        resp = self.session.get(
            f'{self.BASE}/repos/{self.user}/{repo}/contents/{path}', timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def put_file(self, repo: str, path: str, data: dict) -> dict:
        resp = self.session.put(
            f'{self.BASE}/repos/{self.user}/{repo}/contents/{path}',
            json=data, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()



def main():
    config = load_config()
    api = GitHubAPI(config['github_token'], config['github_user'])
    repo = config['alive_repo']
    user = config['github_user']

    sys.exit(1)

    noreply = api.get_noreply_email()

    file_info = api.get_file(repo, 'alive.md')
    current_sha = file_info['sha']

    total_days = 0
    total_commits = 0
    d = START_DATE

    while d <= END_DATE:
        if d.isoweekday() in NOISE_DAYS:
            count = noise_count(d)
            date_str = d.isoformat()
            log.info(f"  {date_str} ({d.strftime('%a')}) → {count} commit(s)")

            base_dt = datetime.datetime.strptime(date_str, '%Y-%m-%d').replace(
                hour=9, minute=0, second=0
            )

            for i in range(count):
                commit_dt = base_dt + datetime.timedelta(hours=i * 3)
                ts = commit_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                content = f"alive: {date_str} #{i + 1}\n"
                encoded = base64.b64encode(content.encode()).decode()

                data = {
                    'message': f'alive: {date_str} #{i + 1}',
                    'content': encoded,
                    'sha': current_sha,
                    'author': {
                        'name': user,
                        'email': noreply,
                        'date': ts,
                    },
                    'committer': {
                        'name': user,
                        'email': noreply,
                        'date': ts,
                    },
                }

                try:
                    result = api.put_file(repo, 'alive.md', data)
                    current_sha = result['content']['sha']
                    total_commits += 1
                    time.sleep(0.5)
                except Exception:
                    try:
                        time.sleep(2)
                        current_sha = api.get_file(repo, 'alive.md')['sha']
                        log.info(f"    Refreshed SHA: {current_sha}")
                    except Exception as e2:
                        log.error(f"    Failed to refresh SHA: {e2}")

            total_days += 1

        d += datetime.timedelta(days=1)



if __name__ == '__main__':
    main()

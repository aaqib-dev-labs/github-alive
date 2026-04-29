#!/usr/bin/env python3

import argparse
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
log = logging.getLogger('backfill')



ANCHOR_DATE = datetime.date(2012, 9, 9)


def base_commits(days_since_anchor: int, day_of_week: int) -> int:
    t = days_since_anchor / 7.0
    d = day_of_week

    w1 = math.sin(2 * math.pi * t / 26 + 0.0)
    w2 = math.sin(2 * math.pi * t / 13 + 1.5)
    w3 = math.sin(2 * math.pi * t / 52 + 0.8)
    w4 = math.sin(2 * math.pi * d / 7 + t * 0.4)
    w5 = math.sin(2 * math.pi * (t * 1.3 + d) / 9)

    combined = w1 * 0.35 + w2 * 0.25 + w3 * 0.15 + w4 * 0.15 + w5 * 0.10
    count = round(3 + (combined + 1) * 18.5)
    return max(1, min(40, count))


def get_base_commits(d: datetime.date) -> int:
    days = (d - ANCHOR_DATE).days
    dow = d.isoweekday() % 7
    return base_commits(days, dow)



def load_config() -> dict:
    config = {'github_token': '', 'github_user': '', 'alive_repo': 'alive', 'alive_repo_owner': ''}
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
    if os.environ.get('ALIVE_REPO_OWNER'):
        config['alive_repo_owner'] = os.environ['ALIVE_REPO_OWNER']
    if not config['github_token']:
        sys.exit(1)
    if not config['github_user']:
        sys.exit(1)
    return config



class GitHubAPI:
    BASE = 'https://api.github.com'

    def __init__(self, token: str, user: str, repo_owner: str | None = None):
        self.user = user
        self.repo_owner = repo_owner or user
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
            f'{self.BASE}/repos/{self.repo_owner}/{repo}/contents/{path}', timeout=30
        )
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    def put_file(self, repo: str, path: str, data: dict) -> dict:
        resp = self.session.put(
            f'{self.BASE}/repos/{self.repo_owner}/{repo}/contents/{path}',
            json=data, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='2012-09-09', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', default='2026-03-10', help='End date YYYY-MM-DD')
    parser.add_argument('--dry-run', action='store_true', help='Print plan without committing')
    args = parser.parse_args()

    start_date = datetime.date.fromisoformat(args.start)
    end_date = datetime.date.fromisoformat(args.end)

    config = load_config()
    api = GitHubAPI(config['github_token'], config['github_user'], config.get('alive_repo_owner') or config['github_user'])
    repo = config['alive_repo']
    user = config['github_user']

    log.info(f"=== backfill starting ===")
    log.info(f"User: {user}  |  Repo: {repo}")
    noreply = api.get_noreply_email()
    log.info(f"Email: {noreply}")
    log.info(f"Range: {start_date} → {end_date}" + ("  [DRY RUN]" if args.dry_run else ""))

    if not args.dry_run:
        file_info = api.get_file(repo, 'alive.md')
        current_sha = file_info.get('sha')
        log.info(f"Starting SHA: {current_sha}")
    else:
        current_sha = None

    total_days = 0
    total_commits = 0
    d = start_date

    while d <= end_date:
        count = get_base_commits(d)
        date_str = d.isoformat()

        if args.dry_run:
            log.info(f"  {date_str} ({d.strftime('%a')}) → {count} commit(s)  [dry]")
            total_days += 1
            total_commits += count
            d += datetime.timedelta(days=1)
            continue

        log.info(f"  {date_str} ({d.strftime('%a')}) → {count} commit(s)")

        base_dt = datetime.datetime.strptime(date_str, '%Y-%m-%d').replace(
            hour=0, minute=0, second=0
        )

        for i in range(count):
            minutes = int(i * 1440 / count)
            commit_dt = base_dt + datetime.timedelta(minutes=minutes)
            ts = commit_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            content = f"alive: {date_str} #{i + 1}\n"
            encoded = base64.b64encode(content.encode()).decode()

            data = {
                'message': f'alive: {date_str} #{i + 1}',
                'content': encoded,
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
            if current_sha:
                data['sha'] = current_sha

            try:
                result = api.put_file(repo, 'alive.md', data)
                current_sha = result['content']['sha']
                total_commits += 1
                time.sleep(0.5)
            except Exception as e:
                log.error(f"    ERROR on {date_str} #{i + 1}: {e}")
                try:
                    time.sleep(2)
                    current_sha = api.get_file(repo, 'alive.md').get('sha', current_sha)
                    log.info(f"    Refreshed SHA: {current_sha}")
                except Exception as e2:
                    log.error(f"    Failed to refresh SHA: {e2}")

        total_days += 1
        d += datetime.timedelta(days=1)

    log.info(f"=== Done! {total_days} days, {total_commits} commits. ===")


if __name__ == '__main__':
    main()

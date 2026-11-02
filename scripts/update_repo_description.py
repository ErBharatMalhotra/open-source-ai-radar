"""Update GitHub repository description ('About' section) with live repo count."""

from __future__ import annotations

import os
import requests
from radar.storage.database import Database


def main() -> None:
    token = os.environ.get("REPO_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("No token available to update repo description")
        return

    db = Database()
    total_repos = db.get_repo_count()
    rounded = (total_repos // 100) * 100
    new_desc = f"Scores {rounded:,}+ open-source AI repos on Impact / Velocity / Health - refreshed 6x daily."

    repo = os.environ.get("GITHUB_REPOSITORY", "ErBharatMalhotra/open-source-ai-radar")
    url = f"https://api.github.com/repos/{repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        resp = requests.patch(url, json={"description": new_desc}, headers=headers)
        if resp.status_code == 200:
            print(f"Successfully updated repo description to: {new_desc}")
        else:
            print(f"Failed to update repo description: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Error updating repo description: {e}")


if __name__ == "__main__":
    main()

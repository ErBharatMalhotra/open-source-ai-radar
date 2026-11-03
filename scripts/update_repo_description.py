"""Update GitHub repository description ('About' section) with live repo count.

Uses only the standard library (urllib) so it runs without extra dependencies
in the GitHub Actions pipeline.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from radar.storage.database import Database


def main() -> None:
    token = os.environ.get("REPO_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("No token available to update repo description")
        return

    db = Database()
    total_repos = db.get_repo_count()
    rounded = (total_repos // 100) * 100
    new_desc = (
        f"Scores {rounded:,}+ open-source AI repos on Impact / Velocity / Health "
        "- refreshed 6x daily."
    )

    repo = os.environ.get("GITHUB_REPOSITORY", "ErBharatMalhotra/open-source-ai-radar")
    url = f"https://api.github.com/repos/{repo}"
    payload = json.dumps({"description": new_desc}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "open-source-ai-radar",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                print(f"Successfully updated repo description to: {new_desc}")
            else:
                print(f"Unexpected status updating repo description: {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        print(f"Failed to update repo description: {e.code} {body}")
    except Exception as e:
        # Cosmetic metadata only — never break the data pipeline for this.
        print(f"Error updating repo description: {e}")


if __name__ == "__main__":
    main()

"""Save a file to the GitHub repository from the app (for the owner, with a token).

The app on Streamlit Community Cloud has no disk of its own: a change meant for everyone
(the injury list, for instance) has to become a commit. This uses the GitHub contents
API with a fine-grained token that can write to the repository's contents, kept in the
app's secrets, never in the code.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "xMercato",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (fixed host)
        return json.load(response)


def save_file(
    repo: str, path: str, content: str, message: str, token: str, branch: str = "main"
) -> str:
    """Create or replace ``path`` on ``branch``; returns the URL of the new commit."""
    url = f"{API}/repos/{repo}/contents/{urllib.parse.quote(path)}"
    try:
        sha = _request("GET", f"{url}?ref={urllib.parse.quote(branch)}", token).get("sha")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        sha = None
    body = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    answer = _request("PUT", url, token, body)
    return answer.get("commit", {}).get("html_url", "")

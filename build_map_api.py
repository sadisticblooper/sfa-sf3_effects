import base64
import json
import os
import urllib.request

TOKEN = os.environ["GH_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "effect-map-builder",
}


def api(url, method="GET", data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


lines = []
for game in ("SF3", "SFA"):
    page = 1
    while True:
        items = api(
            f"https://api.github.com/repos/{REPO}/contents/{game}"
            f"?per_page=100&page={page}"
        )
        if not items:
            break
        for item in items:
            if item.get("type") == "dir":
                lines.append(
                    f"{item['name']} | "
                    f"https://github.com/{REPO}/tree/main/{game}/{item['name']}"
                )
        if len(items) < 100:
            break
        page += 1

content = "\n".join(lines) + "\n"
print(f"map.txt: {len(lines)} lines")

sha = None
try:
    sha = api(
        f"https://api.github.com/repos/{REPO}/contents/map.txt?ref=main"
    )["sha"]
except Exception:
    pass

data = {
    "message": "docs: update map.txt",
    "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    "branch": "main",
}
if sha:
    data["sha"] = sha

api(f"https://api.github.com/repos/{REPO}/contents/map.txt", "PUT", data)
print("committed map.txt")

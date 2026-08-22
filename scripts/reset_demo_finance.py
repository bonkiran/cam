from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("CRICKANALYSIS_BASE_URL", "https://crickanalysis.onrender.com").rstrip("/")


def request(method: str, path: str, payload=None, *, retries: int = 5):
    url = BASE_URL + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"User-Agent": "CrickAnalysis-Demo-Finance-Reset/2.0"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=40) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last = RuntimeError(f"{method} {path} -> HTTP {exc.code}: {body}")
            if exc.code < 500 and exc.code != 404:
                raise last
        except Exception as exc:
            last = exc
        if attempt < retries:
            time.sleep(3 * attempt)
    raise RuntimeError(f"{method} {path} failed after {retries} attempts: {last}")


def wait_for_cleanup_api():
    # Render free deployments can queue/spin up slowly, especially when several
    # commits land close together. Wait up to 20 minutes for the deployment that
    # contains the cleanup endpoint rather than racing the web-service rollout.
    for attempt in range(1, 121):
        try:
            storage = request("GET", "/api/system/storage")
            if storage and storage.get("database") == "postgresql":
                result = request(
                    "POST",
                    "/api/cam/demo-data/cleanup-finance",
                    {"confirm": "RESET_DEMO_FINANCE"},
                    retries=1,
                )
                print("DEMO_FINANCE_CLEANUP_COMPLETE")
                print(json.dumps(result, indent=2))
                return result
            print(f"cleanup readiness attempt {attempt}: storage={storage}")
        except Exception as exc:
            print(f"cleanup endpoint readiness attempt {attempt}: {exc}")
        time.sleep(10)
    raise RuntimeError("DEMO finance cleanup endpoint did not become available within 20 minutes")


def main():
    return wait_for_cleanup_api()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DEMO_FINANCE_CLEANUP_FAILED: {exc}", file=sys.stderr)
        raise

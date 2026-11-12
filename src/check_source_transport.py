"""Read-only live smoke check for source discovery from an Actions runner."""
import argparse
import json
import re
from urllib.parse import quote

import requests

from prehrajto_search import search
from resolve_stream import GOOGLEBOT_HEADERS, resolve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detail-url", required=True)
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    try:
        detail = resolve(args.detail_url, timeout=15, max_retries=0)
        print(json.dumps({"detail_ok": bool(detail.videos), "transport": detail.fetch_via,
                          "video_id": detail.video_id, "variants": len(detail.videos)}), flush=True)
        results = search(args.query, timeout=15, retries=1, min_interval=0)
        print(json.dumps({"search_ok": bool(results), "results": len(results)}), flush=True)
        if not results:
            page = requests.get("https://prehraj.to/hledej/" + quote(args.query),
                                headers=GOOGLEBOT_HEADERS, timeout=15)
            title = re.search(r"<title>(.*?)</title>", page.text, re.S | re.I)
            print(json.dumps({"search_diagnostic_status": page.status_code,
                              "bytes": len(page.content), "video_markers": page.text.count("video-wrapper"),
                              "page_title": title[1].strip()[:120] if title else None}), flush=True)
        return 0 if detail.videos and results else 1
    except Exception as error:
        print(json.dumps({"transport_check_failed": type(error).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

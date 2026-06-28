from datetime import datetime, timezone
import html
import json
import os
import re
import traceback
from urllib.request import Request, urlopen


RESULTS_DIR = "results"
SCHOLAR_ID = os.environ["GOOGLE_SCHOLAR_ID"]
PROFILE_URL = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def fetch_profile_html() -> str:
    request = Request(PROFILE_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_citation_count(page_html: str) -> int:
    decoded = html.unescape(page_html)
    patterns = [
        r"Cited by\s+([\d,]+)",
        r'<td class="gsc_rsb_std">([\d,]+)</td>',
    ]

    for pattern in patterns:
        match = re.search(pattern, decoded)
        if match:
            return int(match.group(1).replace(",", ""))

    raise ValueError("Could not find citation count in Google Scholar profile.")


def write_json(filename: str, data: dict) -> None:
    with open(os.path.join(RESULTS_DIR, filename), "w") as outfile:
        json.dump(data, outfile, ensure_ascii=False)


os.makedirs(RESULTS_DIR, exist_ok=True)
updated = datetime.now(timezone.utc).isoformat()

try:
    profile_html = fetch_profile_html()
    citedby = extract_citation_count(profile_html)

    write_json(
        "gs_data.json",
        {
            "updated": updated,
            "scholar_id": SCHOLAR_ID,
            "profile_url": PROFILE_URL,
            "citedby": citedby,
        },
    )

    shieldio_data = {
        "schemaVersion": 1,
        "label": "citations",
        "message": str(citedby),
        "color": "9cf",
    }
except Exception:
    error = traceback.format_exc()
    fallback = os.environ.get("FALLBACK_CITATIONS", "unavailable")
    print(error)

    with open(os.path.join(RESULTS_DIR, "gs_error.txt"), "w") as outfile:
        outfile.write(error)

    write_json(
        "gs_data.json",
        {
            "updated": updated,
            "scholar_id": SCHOLAR_ID,
            "profile_url": PROFILE_URL,
            "error": error,
        },
    )

    shieldio_data = {
        "schemaVersion": 1,
        "label": "citations",
        "message": fallback,
        "color": "lightgrey" if fallback == "unavailable" else "9cf",
    }

write_json("gs_data_shieldsio.json", shieldio_data)

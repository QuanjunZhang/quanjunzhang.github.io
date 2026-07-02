from datetime import datetime, timezone
import html
import json
import os
import re
import traceback
from urllib.parse import urlencode
from urllib.request import Request, urlopen


RESULTS_DIR = "results"
SCHOLAR_ID = os.environ["GOOGLE_SCHOLAR_ID"]
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY")
PROFILE_URL = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en"
SERPAPI_URL = "https://serpapi.com/search"
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


def fetch_serpapi_profile() -> dict:
    if not SERPAPI_API_KEY:
        raise RuntimeError("SERPAPI_API_KEY is not configured.")

    query = urlencode(
        {
            "engine": "google_scholar_author",
            "author_id": SCHOLAR_ID,
            "hl": "en",
            "api_key": SERPAPI_API_KEY,
        }
    )
    request = Request(f"{SERPAPI_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8", errors="replace")

    data = json.loads(payload)
    if data.get("error"):
        raise RuntimeError(f"SerpAPI returned error: {data['error']}")

    status = data.get("search_metadata", {}).get("status")
    if status and status != "Success":
        raise RuntimeError(f"SerpAPI search did not succeed: {status}")

    data.get("search_parameters", {}).pop("api_key", None)
    return data


def extract_serpapi_citation_count(data: dict) -> int:
    cited_by = data.get("cited_by", {})
    for row in cited_by.get("table", []):
        citations = row.get("citations")
        if isinstance(citations, dict) and citations.get("all") is not None:
            return int(str(citations["all"]).replace(",", ""))

    raise ValueError("SerpAPI response does not include total citations.")


def fetch_with_serpapi(updated: str) -> dict:
    data = fetch_serpapi_profile()
    citedby = extract_serpapi_citation_count(data)
    data.update(
        {
            "updated": updated,
            "scholar_id": SCHOLAR_ID,
            "profile_url": PROFILE_URL,
            "fetch_method": "serpapi",
            "citedby": citedby,
        }
    )
    return data


def normalize_publications(publications: list[dict]) -> dict:
    normalized = {}
    for publication in publications:
        author_pub_id = publication.get("author_pub_id")
        if author_pub_id:
            normalized[author_pub_id] = publication
    return normalized


def fetch_with_scholarly(updated: str) -> dict:
    from scholarly import ProxyGenerator, scholarly

    proxy_generator = ProxyGenerator()
    proxy_generator._TIMEOUT = 1
    if not proxy_generator.FreeProxies():
        raise RuntimeError("Could not configure scholarly free proxies.")

    scholarly.use_proxy(proxy_generator)
    author = scholarly.search_author_id(SCHOLAR_ID)
    scholarly.fill(author, sections=["basics", "indices", "counts", "publications"])
    author["updated"] = updated
    author["fetch_method"] = "scholarly_free_proxies"
    author["publications"] = normalize_publications(author.get("publications", []))
    return author


def fetch_with_direct_request(updated: str) -> dict:
    profile_html = fetch_profile_html()
    citedby = extract_citation_count(profile_html)
    return {
        "updated": updated,
        "scholar_id": SCHOLAR_ID,
        "profile_url": PROFILE_URL,
        "source": "AUTHOR_PROFILE_PAGE",
        "fetch_method": "direct_request",
        "citedby": citedby,
    }


def read_json(filename: str) -> dict | None:
    path = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(path):
        return None

    try:
        with open(path) as infile:
            return json.load(infile)
    except (OSError, json.JSONDecodeError):
        return None


def write_json(filename: str, data: dict) -> None:
    with open(os.path.join(RESULTS_DIR, filename), "w") as outfile:
        json.dump(data, outfile, ensure_ascii=False)


def write_error(error: str) -> None:
    with open(os.path.join(RESULTS_DIR, "gs_error.txt"), "w") as outfile:
        outfile.write(error)


def clear_error() -> None:
    error_path = os.path.join(RESULTS_DIR, "gs_error.txt")
    if os.path.exists(error_path):
        os.remove(error_path)


def citation_count(author: dict) -> int:
    citedby = author.get("citedby")
    if citedby is None:
        raise ValueError("Google Scholar response does not include citedby.")
    return int(citedby)


def shieldio_payload(citedby: int) -> dict:
    return {
        "schemaVersion": 1,
        "label": "citations",
        "message": str(citedby),
        "color": "9cf",
    }


def preserve_previous_data(updated: str, error: str) -> None:
    write_error(error)

    previous_data = read_json("gs_data.json")
    previous_shield = read_json("gs_data_shieldsio.json")
    if previous_data and previous_shield:
        previous_data["last_failed_update"] = updated
        previous_data["last_error"] = error
        write_json("gs_data.json", previous_data)
        print("Citation fetch failed; preserved previous citation badge data.")
        return

    write_json(
        "gs_data.json",
        {
            "updated": updated,
            "scholar_id": SCHOLAR_ID,
            "profile_url": PROFILE_URL,
            "error": error,
        },
    )
    write_json(
        "gs_data_shieldsio.json",
        {
            "schemaVersion": 1,
            "label": "citations",
            "message": "unavailable",
            "color": "lightgrey",
        },
    )


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    updated = datetime.now(timezone.utc).isoformat()
    errors = []

    for fetcher in (fetch_with_serpapi, fetch_with_scholarly, fetch_with_direct_request):
        try:
            author = fetcher(updated)
            citedby = citation_count(author)
            write_json("gs_data.json", author)
            write_json("gs_data_shieldsio.json", shieldio_payload(citedby))
            clear_error()
            print(f"Updated Google Scholar citations to {citedby}.")
            return
        except Exception:
            errors.append(f"{fetcher.__name__} failed:\n{traceback.format_exc()}")

    error = "\n\n".join(errors)
    print(error)
    preserve_previous_data(updated, error)


if __name__ == "__main__":
    main()

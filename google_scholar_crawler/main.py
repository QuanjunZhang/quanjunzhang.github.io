from scholarly import scholarly, ProxyGenerator
import json
from datetime import datetime
import os
import traceback

os.makedirs('results', exist_ok=True)

try:
    # Setup proxy
    pg = ProxyGenerator()
    pg.FreeProxies()  # Use free rotating proxies
    scholarly.use_proxy(pg)

    author: dict = scholarly.search_author_id(os.environ['GOOGLE_SCHOLAR_ID'])
    scholarly.fill(author, sections=['basics', 'indices', 'counts', 'publications'])
    author['updated'] = str(datetime.now())
    author['publications'] = {v['author_pub_id']: v for v in author['publications']}
    print(json.dumps(author, indent=2))

    with open('results/gs_data.json', 'w') as outfile:
        json.dump(author, outfile, ensure_ascii=False)

    shieldio_data = {
        "schemaVersion": 1,
        "label": "citations",
        "message": f"{author['citedby']}",
        "color": "9cf",
    }
except Exception:
    error = traceback.format_exc()
    print(error)
    with open('results/gs_error.txt', 'w') as outfile:
        outfile.write(error)

    shieldio_data = {
        "schemaVersion": 1,
        "label": "citations",
        "message": os.environ.get('FALLBACK_CITATIONS', 'unavailable'),
        "color": "lightgrey",
    }

    with open('results/gs_data.json', 'w') as outfile:
        json.dump({
            "updated": str(datetime.now()),
            "error": error,
            "publications": {},
        }, outfile, ensure_ascii=False)

with open('results/gs_data_shieldsio.json', 'w') as outfile:
    json.dump(shieldio_data, outfile, ensure_ascii=False)

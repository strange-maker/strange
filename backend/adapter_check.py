"""One-shot live adapter validation; never records a crawl success in the database."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from adapters.registry import build_adapter, get_adapter_definition


def check(name: str, url: str) -> dict:
    adapter=build_adapter(name,url)
    try:
        items=adapter.fetch_list()
        return {"source_name":name,"ok":bool(items),"http_status":adapter.last_http_status,"valid_items":len(items),**({"error":"no valid items extracted"} if not items else {})}
    except Exception as exc:
        return {"source_name":name,"ok":False,"http_status":adapter.last_http_status,"error":f"{type(exc).__name__}: {exc}"[:500]}


if __name__ == "__main__":
    sources=json.loads((Path(__file__).resolve().parents[1]/"public"/"sources.yaml").read_text("utf-8"))
    runnable=[x for x in sources if get_adapter_definition(x["source_name"],x["source_url"],x)]
    urls={x["source_name"]:x["source_url"] for x in runnable}; results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(check,name,url):name for name,url in urls.items()}
        for future in as_completed(futures): results.append(future.result())
    results.sort(key=lambda x:x["source_name"])
    print(json.dumps({"checked":len(results),"passed":sum(x["ok"] for x in results),"results":results},ensure_ascii=False,indent=2))

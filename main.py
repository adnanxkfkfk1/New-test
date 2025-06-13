from fastapi import FastAPI, Request, Query
from fastapi.responses import Response, PlainTextResponse, StreamingResponse
import requests
import re
import random
from typing import Optional
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow all CORS (if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0)",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
]

def HEADERS():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Origin": "https://re.fredflix.fun",
        "Referer": "https://re.fredflix.fun/",
    }

@app.get("/bypass")
async def bypass(url: str = Query(...)):
    try:
        r = requests.get(url, headers=HEADERS(), timeout=5)
    except requests.RequestException as e:
        return PlainTextResponse(f"Error fetching source page: {e}", status_code=500)

    m3u8_match = re.search(r"source:\s*['\"](https.*?playlist\.m3u8[^'\"]*)['\"]", r.text)
    if not m3u8_match:
        return PlainTextResponse("No .m3u8 found", status_code=404)

    m3u8_url = m3u8_match.group(1)

    try:
        r2 = requests.get(m3u8_url, headers=HEADERS(), timeout=5)
    except requests.RequestException as e:
        return PlainTextResponse(f"Failed to fetch .m3u8: {e}", status_code=500)

    if r2.status_code != 200:
        return PlainTextResponse("Failed to fetch .m3u8", status_code=500)

    base = m3u8_url.split('?')[0]
    query = m3u8_url.split('?')[1] if '?' in m3u8_url else ""

    lines = []
    for line in r2.text.splitlines():
        if line.strip().startswith('#') or line.strip() == "":
            lines.append(line)
        elif "segment=" in line:
            segment_id = re.search(r"segment=([\w\d]+)", line)
            if segment_id:
                full_url = f"/ts?base={base}&seg={segment_id.group(1)}&{query}"
                lines.append(full_url)
            else:
                lines.append(line)
        elif ".ts" in line:
            full_url = f"/ts?url={line}"
            lines.append(full_url)
        else:
            lines.append(line)

    fixed_m3u8 = '\n'.join(lines)
    return Response(content=fixed_m3u8, media_type='application/vnd.apple.mpegurl')


@app.get("/ts")
async def ts_proxy(
    url: Optional[str] = Query(None),
    base: Optional[str] = Query(None),
    seg: Optional[str] = Query(None),
    request: Request = None
):
    if url:
        target_url = url
    else:
        if not base or not seg:
            return PlainTextResponse("Missing parameters", status_code=400)
        query_params = dict(request.query_params)
        query_params.pop("base", None)
        query_params.pop("seg", None)
        query = "&".join([f"{k}={v}" for k, v in query_params.items()])
        target_url = f"{base}?segment={seg}"
        if query:
            target_url += f"&{query}"

    try:
        resp = requests.get(target_url, headers=HEADERS(), stream=True, timeout=5)
    except requests.RequestException as e:
        return PlainTextResponse(f"Failed to fetch TS segment: {e}", status_code=502)

    if resp.status_code != 200:
        return PlainTextResponse(f"Failed to fetch TS: {resp.status_code}", status_code=502)

    return StreamingResponse(resp.iter_content(chunk_size=4096), media_type=resp.headers.get("Content-Type", "video/MP2T"))

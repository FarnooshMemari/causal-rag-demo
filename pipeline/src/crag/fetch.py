"""Download sources, keep original bytes, extract text, write the corpus manifest.

Raw downloads are cached in data/raw/<doc_id>.<ext>; rerunning does not re-download.
"""
import hashlib
import json
import os
import time
import re
from datetime import date, datetime, timezone

import requests
from bs4 import BeautifulSoup

from .common import CORPUS, ET, RAW, USER_AGENT, available_at, cutoff, load, write_json, write_jsonl

SESSION = requests.Session()
SESSION.headers["User-Agent"] = USER_AGENT
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " + USER_AGENT


SEC_CONTACT = os.environ.get("CRAG_SEC_CONTACT", "")  # SEC fair-access policy asks for a contact address


def _get(url):
    sec = "sec.gov" in url
    headers = {"User-Agent": f"{USER_AGENT} {SEC_CONTACT}".strip()} if sec else None
    for attempt in range(4):
        if sec:
            time.sleep(1.0 + 5 * attempt)  # stay far below SEC's 10 req/s limit; back off when blocked
        r = SESSION.get(url, timeout=60, headers=headers)
        if r.status_code == 403 and not sec:  # bls.gov rejects non-browser agents
            r = SESSION.get(url, timeout=60, headers={"User-Agent": BROWSER_UA})
        if sec and "Undeclared Automated Tool" in r.text[:3000]:
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"SEC blocked {url}; set CRAG_SEC_CONTACT='Name email@domain' and retry")


def _download(src):
    """Return (raw_bytes, ext, resolved_url, extra_metadata)."""
    extra = {}
    if src["format"] == "edgar":
        acc = src["accession"]
        base = f"https://www.sec.gov/Archives/edgar/data/{src['cik']}/{acc.replace('-', '')}/"
        idx_url = base + f"{acc}-index.htm"
        idx = _get(idx_url).text
        accepted = re.search(r'Accepted</div>\s*<div class="info">([^<]+)</div>', idx).group(1).strip()
        # EDGAR displays Eastern time on the index page
        extra["edgar_accepted_et"] = accepted
        extra["edgar_index_url"] = idx_url
        soup = BeautifulSoup(idx, "lxml")
        href = None
        for tr in soup.select("table.tableFile tr"):
            tds = tr.find_all("td")
            if len(tds) >= 4 and tds[3].get_text(strip=True).upper().startswith("EX-99.1"):
                href = tds[2].find("a")["href"]
                break
        if href is None:
            raise RuntimeError(f"No EX-99.1 in {idx_url}")
        url = "https://www.sec.gov" + href.replace("/ix?doc=", "")
        return _get(url).content, "htm", url, extra
    r = _get(src["url"])
    extra["http_last_modified"] = r.headers.get("Last-Modified")
    return r.content, src["format"], src["url"], extra


def _pdf_text(path, max_pages):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[: max_pages or len(pdf.pages)]
        return "\n\n".join((p.extract_text() or "") for p in pages)


def _html_text(raw, url):
    soup = BeautifulSoup(raw, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "noscript", "form"]):
        t.decompose()
    node = None
    if "federalreserve.gov" in url:
        node = soup.select_one("#article") or soup.select_one("#content")
    elif "bls.gov" in url:
        pres = soup.find_all("pre")
        if pres:
            return "\n\n".join(p.get_text("\n") for p in pres)
        node = soup.select_one("#bodytext")
    elif "philadelphiafed.org" in url:
        node = soup.select_one("main") or soup.select_one("article")
    node = node or soup.body or soup
    # one line per table row ("cell | cell"), so tables don't explode into one token per line
    for tr in node.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c and c not in ("$", "%", ")")]
        tr.replace_with(soup.new_string("\n" + " | ".join(cells) + "\n"))
    for b in node.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "br"]):
        b.insert_before(soup.new_string("\n"))
    lines = [re.sub(r"\s+", " ", l).strip() for l in node.get_text().split("\n")]
    return "\n".join(l for l in lines if l)


BOILERPLATE = re.compile(r"(Private Securities Litigation Reform Act|forward-looking statements (speak|are based|involve)|cautionary statement)", re.I)


def _clean(text):
    """Whitespace normalisation + removal of legal safe-harbour paragraphs (documented
    cleaning rule; the raw original is kept unmodified in data/raw)."""
    text = "\n".join(l for l in text.split("\n") if not (len(l) > 400 and BOILERPLATE.search(l)))
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _date_mentioned(text, d: date):
    """Is the publication date printed in the document (sanity check on the timestamp)?"""
    variants = [d.strftime("%B %-d, %Y"), d.strftime("%B %d, %Y"), d.strftime("%b. %-d, %Y"), d.strftime("%B %-d")]
    low = text.lower()
    return any(v.lower() in low for v in variants)


def run(refresh=False):
    srcs = load("sources.json")["sources"]
    cut = cutoff()
    (CORPUS / "text").mkdir(parents=True, exist_ok=True)
    rows, failures = [], []
    for s in srcs:
        did = s["doc_id"]
        cached = list(RAW.glob(f"{did}.*"))
        meta_path = RAW / f"{did}.meta.json"
        if cached and meta_path.exists() and not refresh:
            meta = json.loads(meta_path.read_text())
            raw_path = RAW / meta["raw_file"]
        else:
            try:
                raw, ext, url, extra = _download(s)
            except Exception as e:  # recorded, never silently substituted
                failures.append({"doc_id": did, "error": str(e)[:300]})
                print(f"FAIL {did}: {str(e)[:120]}")
                continue
            raw_path = RAW / f"{did}.{ext}"
            raw_path.write_bytes(raw)
            meta = {"raw_file": raw_path.name, "resolved_url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra}
            meta_path.write_text(json.dumps(meta, indent=1))
        raw = raw_path.read_bytes()
        if raw_path.suffix == ".pdf":
            text = _pdf_text(raw_path, s.get("max_pages"))
        else:
            text = _html_text(raw, meta["resolved_url"])
        text = _clean(text)
        full_len = len(text)
        if s.get("max_chars") and len(text) > s["max_chars"]:
            text = text[: s["max_chars"]]
        (CORPUS / "text" / f"{did}.txt").write_text(text)

        avail = available_at(s["published_at"], s["timestamp_precision"])
        ts_checks = {"date_printed_in_text": _date_mentioned(text[:6000], avail.date())}
        if "edgar_accepted_et" in meta:
            acc = datetime.strptime(meta["edgar_accepted_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
            ts_checks["edgar_accepted_matches_config"] = acc == avail
        rows.append({
            "doc_id": did,
            "title": s["title"],
            "publisher": s["publisher"],
            "doc_type": s["doc_type"],
            "url": meta["resolved_url"],
            "published_at": s["published_at"],
            "timestamp_precision": s["timestamp_precision"],
            "available_at_et": avail.isoformat(),
            "timestamp_evidence": s["timestamp_evidence"],
            "timestamp_checks": ts_checks,
            "retrieved_at_utc": meta["retrieved_at"],
            "http_last_modified": meta.get("http_last_modified"),
            "edgar_accepted_et": meta.get("edgar_accepted_et"),
            "role": s["role"],
            "available_before_cutoff": avail <= cut,
            "raw_file": f"data/raw/{raw_path.name}",
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "text_file": f"data/corpus/text/{did}.txt",
            "text_chars": len(text),
            "text_chars_before_truncation": full_len,
            "truncated": len(text) < full_len,
        })
        flag = "OK " if rows[-1]["available_before_cutoff"] == (s["role"] == "corpus") else "!! "
        print(f"{flag}{did:34s} {len(text):6d} chars  avail={avail.isoformat()}  checks={ts_checks}")
    write_jsonl(CORPUS / "manifest.jsonl", rows)
    write_json(CORPUS / "fetch_failures.json", failures)
    bad = [r["doc_id"] for r in rows if r["available_before_cutoff"] != (r["role"] == "corpus")]
    if bad:
        raise SystemExit(f"Role/timestamp mismatch for {bad}")
    print(f"wrote {len(rows)} docs to {CORPUS/'manifest.jsonl'}")

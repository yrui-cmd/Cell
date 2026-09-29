#!/usr/bin/env python3
"""Probe DOI registry metadata without turning transport failures into success.

Python 3.10+ standard library only. A ``verified`` result means that a registry
returned a matching DOI record; it does not verify the paper's claims,
publication notices, or the caller's bibliography fields.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
PROVIDERS = (
    ("crossref", "https://api.crossref.org/works/{}"),
    ("datacite", "https://api.datacite.org/dois/{}"),
)
Opener = Callable[..., Any]


def checked_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_doi(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("DOI must be text")
    doi = value.strip()
    lowered = doi.casefold()
    for prefix in (
        "https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
        "http://dx.doi.org/", "doi:",
    ):
        if lowered.startswith(prefix):
            doi = doi[len(prefix):].strip()
            break
    doi = doi.rstrip(".,; ").casefold()
    if not DOI_RE.fullmatch(doi) or any(char.isspace() for char in doi):
        raise ValueError(f"Invalid DOI: {value!r}")
    return doi


def _year_from_parts(value: Any) -> int | None:
    if isinstance(value, dict):
        parts = value.get("date-parts")
        if (isinstance(parts, list) and parts and isinstance(parts[0], list)
                and parts[0] and type(parts[0][0]) is int):
            return parts[0][0]
    return None


def _crossref_metadata(payload: Any) -> dict[str, Any]:
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        raise ValueError("Crossref response has no message object")
    titles = message.get("title")
    title = titles[0].strip() if isinstance(titles, list) and titles and isinstance(titles[0], str) else None
    authors = []
    for author in message.get("author", []) if isinstance(message.get("author"), list) else []:
        if not isinstance(author, dict):
            continue
        name = " ".join(str(author.get(key, "")).strip() for key in ("given", "family")).strip()
        if name:
            authors.append(name)
    year = None
    for key in ("published-print", "published-online", "issued"):
        year = _year_from_parts(message.get(key))
        if year is not None:
            break
    return {"identifier": message.get("DOI"), "title": title,
            "authors": authors, "year": year}


def _datacite_metadata(payload: Any) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    attrs = data.get("attributes") if isinstance(data, dict) else None
    if not isinstance(attrs, dict):
        raise ValueError("DataCite response has no data.attributes object")
    title = None
    titles = attrs.get("titles")
    if isinstance(titles, list) and titles and isinstance(titles[0], dict):
        candidate = titles[0].get("title")
        title = candidate.strip() if isinstance(candidate, str) else None
    authors = []
    for creator in attrs.get("creators", []) if isinstance(attrs.get("creators"), list) else []:
        if isinstance(creator, dict) and isinstance(creator.get("name"), str):
            authors.append(creator["name"].strip())
    year = attrs.get("publicationYear")
    if type(year) is not int:
        year = None
    return {"identifier": attrs.get("doi") or data.get("id"), "title": title,
            "authors": authors, "year": year}


def _fetch(url: str, *, opener: Opener, timeout: float, user_agent: str) -> tuple[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": user_agent})
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read()
        return "found", json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return "not_found", "HTTP 404"
        return "unavailable", f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        return "unavailable", f"{type(exc).__name__}: {exc}"


def resolve_doi(
        value: str, *, opener: Opener = urlopen, timeout: float = 15.0,
        mailto: str | None = None) -> dict[str, Any]:
    """Return verified/not_found/unavailable with a transparent attempt log."""
    doi = normalize_doi(value)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    user_agent = "Cell-Skills/metadata-probe (+https://github.com/yrui-cmd/Cell)"
    if mailto:
        user_agent += f" mailto:{mailto.strip()}"
    attempts: list[dict[str, str]] = []
    unavailable = False
    for provider, template in PROVIDERS:
        url = template.format(quote(doi, safe=""))
        outcome, payload = _fetch(url, opener=opener, timeout=timeout, user_agent=user_agent)
        if outcome != "found":
            attempts.append({"provider": provider, "outcome": outcome, "detail": str(payload)})
            unavailable = unavailable or outcome == "unavailable"
            continue
        try:
            metadata = (_crossref_metadata(payload) if provider == "crossref"
                        else _datacite_metadata(payload))
            returned = normalize_doi(str(metadata.get("identifier", "")))
            if returned != doi:
                raise ValueError(f"registry returned a different DOI: {returned}")
        except (TypeError, ValueError) as exc:
            unavailable = True
            attempts.append({"provider": provider, "outcome": "unavailable",
                             "detail": f"invalid registry payload: {exc}"})
            continue
        attempts.append({"provider": provider, "outcome": "verified", "detail": "matching DOI record"})
        return {"doi": doi, "status": "verified", "provider": provider,
                "checked_at": checked_at(), "source": url, "metadata": metadata,
                "attempts": attempts,
                "scope": "Registry identity only; content and publication notices are not verified."}
    status = "unavailable" if unavailable else "not_found"
    return {"doi": doi, "status": status, "provider": None,
            "checked_at": checked_at(), "source": None, "metadata": None,
            "attempts": attempts,
            "scope": "Registry identity only; content and publication notices are not verified."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("doi", nargs="+", help="One or more DOI strings or doi.org URLs")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds per registry request")
    parser.add_argument("--mailto", help="Contact email included in the User-Agent for registry etiquette")
    parser.add_argument("--output", type=Path, help="Optional JSON output; replaced atomically")
    args = parser.parse_args(argv)
    results = []
    for value in args.doi:
        try:
            results.append(resolve_doi(value, timeout=args.timeout, mailto=args.mailto))
        except ValueError as exc:
            results.append({"input": value, "status": "invalid", "error": str(exc)})
    statuses = {name: sum(item.get("status") == name for item in results)
                for name in ("verified", "not_found", "unavailable", "invalid")}
    payload = {"results": results, "summary": statuses,
               "all_verified": statuses["verified"] == len(results)}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = args.output.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(target)
    print(rendered, end="")
    return 0 if payload["all_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

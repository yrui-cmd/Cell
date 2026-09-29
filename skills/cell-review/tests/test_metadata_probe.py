"""Offline DOI-registry tests; all HTTP behavior is synthetic."""
from __future__ import annotations

import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import metadata_probe as probe  # noqa: E402


class Response:
    def __init__(self, payload):
        self.stream = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.stream.read()


def crossref_payload(doi="10.1234/example"):
    return {"message": {
        "DOI": doi, "title": ["Synthetic article"],
        "author": [{"given": "Test", "family": "Author"}],
        "published-online": {"date-parts": [[2025, 1, 2]]},
    }}


class MetadataProbeTests(unittest.TestCase):
    def test_normalizes_common_doi_forms(self):
        self.assertEqual(probe.normalize_doi("https://doi.org/10.1234/Example."),
                         "10.1234/example")
        self.assertEqual(probe.normalize_doi("DOI:10.1234/EXAMPLE"), "10.1234/example")

    def test_rejects_invalid_identifier(self):
        for value in ("", "PMID:123", "https://example.test/paper", "10.12/x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                probe.normalize_doi(value)

    def test_crossref_success_is_verified(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return Response(crossref_payload())

        result = probe.resolve_doi("10.1234/example", opener=opener, timeout=3)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["provider"], "crossref")
        self.assertEqual(result["metadata"]["year"], 2025)
        self.assertIn("Cell-Skills", requests[0][0].get_header("User-agent"))

    def test_datacite_fallback_after_crossref_404(self):
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise HTTPError(request.full_url, 404, "missing", {}, None)
            return Response({"data": {"id": "10.1234/example", "attributes": {
                "doi": "10.1234/example", "titles": [{"title": "Dataset article"}],
                "creators": [{"name": "Test Author"}], "publicationYear": 2024,
            }}})

        result = probe.resolve_doi("10.1234/example", opener=opener)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["provider"], "datacite")
        self.assertEqual([attempt["outcome"] for attempt in result["attempts"]],
                         ["not_found", "verified"])

    def test_two_explicit_404s_are_not_found(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 404, "missing", {}, None)

        result = probe.resolve_doi("10.1234/example", opener=opener)
        self.assertEqual(result["status"], "not_found")

    def test_transport_failure_is_never_success(self):
        def opener(request, timeout):
            raise URLError("synthetic outage")

        result = probe.resolve_doi("10.1234/example", opener=opener)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["metadata"])

    def test_one_404_and_one_outage_remains_unavailable(self):
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise HTTPError(request.full_url, 404, "missing", {}, None)
            raise URLError("synthetic outage")

        self.assertEqual(probe.resolve_doi("10.1234/example", opener=opener)["status"],
                         "unavailable")

    def test_wrong_doi_payload_is_not_verified(self):
        def opener(request, timeout):
            return Response(crossref_payload("10.9999/other"))

        result = probe.resolve_doi("10.1234/example", opener=opener)
        self.assertEqual(result["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()

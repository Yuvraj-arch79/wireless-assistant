"""Offline tests: identity, corruption, bounded download and collection safety."""

from contextlib import redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import corpus


PDF = b"%PDF-1.7\nsynthetic test fixture, not a 3GPP source\n%%EOF\n"


def slow_worker(doc, destination, connection):
    time.sleep(10)


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, url):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest, self.manifest_hash = corpus.load_manifest(corpus.MANIFEST)
        self.doc = copy.deepcopy(self.manifest["documents"][0])
        self.doc.update(size_bytes=len(PDF), sha256=hashlib.sha256(PDF).hexdigest())
        self.small = {**self.manifest, "documents": [self.doc]}
        self.quiet = redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def save_manifest(self, value):
        path = self.root / "manifest.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def existing(self):
        path = self.root / "raw" / self.doc["filename"]
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(PDF)
        return path

    def test_manifest_has_exact_owner_inventory(self):
        self.assertEqual({d["spec"] for d in self.manifest["documents"]}, {
            "38.201", "38.202", "38.211", "38.212", "38.213", "38.214", "38.215",
            "38.300", "38.314", "38.321", "38.322", "38.323",
        })

    def test_rejects_duplicate_keys(self):
        p = self.root / "m.json"
        p.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(corpus.CorpusError):
            corpus.load_manifest(p)

    def test_rejects_non_object_manifest_and_entries(self):
        for value in [[], {**self.small, "documents": ["wrong"]}]:
            with self.subTest(value=value), self.assertRaises(corpus.CorpusError):
                corpus.load_manifest(self.save_manifest(value))

    def test_rejects_mixed_release_traversal_and_wrong_version_url(self):
        for field, value in [("version", "17.0.0"), ("filename", "../../escape.pdf"),
                             ("url", self.doc["url"].replace("180000", "180100"))]:
            with self.subTest(field=field):
                data = copy.deepcopy(self.small)
                data["documents"][0][field] = value
                with self.assertRaises(corpus.CorpusError):
                    corpus.load_manifest(self.save_manifest(data))

    def test_rejects_duplicate_documents(self):
        data = copy.deepcopy(self.small)
        data["documents"].append(copy.deepcopy(self.doc))
        with self.assertRaises(corpus.CorpusError):
            corpus.load_manifest(self.save_manifest(data))

    def test_rejects_non_official_and_insecure_urls(self):
        for url in ["http://www.etsi.org/deliver/etsi_ts/a.pdf",
                    "https://evil.example/deliver/etsi_ts/a.pdf",
                    "https://www.etsi.org@evil.example/deliver/etsi_ts/a.pdf",
                    "https://www.etsi.org/deliver/etsi_ts/a.pdf?redirect=1"]:
            with self.subTest(url=url), self.assertRaises(corpus.CorpusError):
                corpus.official_url(url)

    def test_off_host_redirect_rejected_before_following(self):
        with self.assertRaises(corpus.CorpusError):
            corpus.OfficialRedirects().redirect_request(None, None, 302, "", {}, "https://evil.example/a")

    def test_checks_bytes_and_detects_same_length_corruption(self):
        path = self.existing()
        corpus.check_file(path, self.doc)
        path.write_bytes(PDF.replace(b"synthetic", b"corrupted"))
        with self.assertRaisesRegex(corpus.CorpusError, "SHA-256"):
            corpus.check_file(path, self.doc)

    def test_missing_truncated_and_html_files_rejected(self):
        path = self.root / self.doc["filename"]
        with self.assertRaises(corpus.CorpusError):
            corpus.check_file(path, self.doc)
        for body in [PDF[:-1], b"<html>" + b" " * (len(PDF) - 6)]:
            path.write_bytes(body)
            with self.assertRaises(corpus.CorpusError):
                corpus.check_file(path, self.doc)

    def test_existing_corrupt_file_not_silently_replaced(self):
        path = self.existing()
        path.write_bytes(b"bad")
        with patch.object(corpus, "bounded_download") as download:
            with self.assertRaises(corpus.CorpusError):
                corpus.fetch_one(self.doc, path, time.monotonic() + 10)
            download.assert_not_called()
        self.assertEqual(path.read_bytes(), b"bad")

    def test_verified_file_reused_without_network(self):
        path = self.existing()
        with patch.object(corpus, "bounded_download") as download:
            corpus.fetch_one(self.doc, path, time.monotonic() + 10)
            download.assert_not_called()

    def test_stream_rejects_oversize_response(self):
        with patch.object(corpus.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = Response(PDF + b"extra", self.doc["url"])
            with self.assertRaisesRegex(corpus.CorpusError, "exceeds pinned size"):
                corpus.download_stream(self.doc, self.root / "download.part")

    def test_successful_stream_verifies_pdf(self):
        path = self.root / "download.part"
        with patch.object(corpus.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = Response(PDF, self.doc["url"])
            corpus.download_stream(self.doc, path)
        corpus.check_file(path, self.doc)

    def test_partial_download_not_published_and_retries_bounded(self):
        path = self.root / self.doc["filename"]

        def interrupted(doc, temporary, seconds):
            temporary.write_bytes(PDF[:10])
            return False, "network interrupted", True

        with patch.object(corpus, "bounded_download", side_effect=interrupted) as download:
            with patch.object(corpus.time, "sleep"):
                with self.assertRaises(corpus.CorpusError):
                    corpus.fetch_one(self.doc, path, time.monotonic() + 10)
            self.assertEqual(download.call_count, corpus.ATTEMPTS)
        self.assertFalse(path.exists())
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_nonretryable_failure_stops_once(self):
        with patch.object(corpus, "bounded_download", return_value=(False, "hash mismatch", False)) as download:
            with self.assertRaises(corpus.CorpusError):
                corpus.fetch_one(self.doc, self.root / self.doc["filename"], time.monotonic() + 10)
            self.assertEqual(download.call_count, 1)

    def test_success_promotes_verified_temporary_file(self):
        path = self.root / self.doc["filename"]

        def complete(doc, temporary, seconds):
            self.assertFalse(path.exists())
            temporary.write_bytes(PDF)
            return True, "", False

        with patch.object(corpus, "bounded_download", side_effect=complete):
            corpus.fetch_one(self.doc, path, time.monotonic() + 10)
        corpus.check_file(path, self.doc)
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_deadline_prevents_dispatch(self):
        with patch.object(corpus, "bounded_download") as download:
            with self.assertRaises(corpus.CorpusError):
                corpus.fetch_one(self.doc, self.root / self.doc["filename"], time.monotonic() - 1)
            download.assert_not_called()

    def test_hung_worker_is_terminated(self):
        start = time.monotonic()
        with patch.object(corpus, "download_worker", slow_worker):
            ok, message, retryable = corpus.bounded_download(self.doc, self.root / "part", 0.15)
        self.assertFalse(ok)
        self.assertTrue(retryable)
        self.assertIn("deadline", message)
        self.assertLess(time.monotonic() - start, 4)

    def test_all_verified_receipt_is_bound_to_manifest(self):
        self.existing()
        corpus.prepare(self.small, "manifest-identity", self.root, fetch=False)
        receipt = json.loads((self.root / "verified.json").read_text())
        self.assertEqual(receipt["manifest_sha256"], "manifest-identity")
        self.assertEqual(receipt["status"], "sources_verified_not_indexed")
        self.assertEqual(receipt["documents"][0]["sha256"], self.doc["sha256"])

    def test_failed_collection_removes_stale_receipt(self):
        self.existing()
        corpus.prepare(self.small, "old", self.root, fetch=False)
        (self.root / "raw" / self.doc["filename"]).unlink()
        with self.assertRaises(corpus.CorpusError):
            corpus.prepare(self.small, "new", self.root, fetch=False)
        self.assertFalse((self.root / "verified.json").exists())
        self.assertFalse((self.root / ".corpus.lock").exists())

    def test_concurrent_operation_rejected(self):
        with corpus.exclusive(self.root):
            with self.assertRaises(corpus.CorpusError):
                corpus.prepare(self.small, "hash", self.root, fetch=False)

    def test_symlink_file_rejected(self):
        target = self.root / "original.pdf"
        target.write_bytes(PDF)
        link = self.root / "linked.pdf"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("Symlink privilege unavailable")
        with self.assertRaises(corpus.CorpusError):
            corpus.check_file(link, self.doc)


if __name__ == "__main__":
    unittest.main()

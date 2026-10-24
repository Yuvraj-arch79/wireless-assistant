#!/usr/bin/env python3
"""Fetch/verify the pinned source PDFs. Python 3.10+; standard library only."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "corpus" / "manifest.json"
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_DOCUMENTS = 32
COMMAND_SECONDS = 600
ATTEMPT_SECONDS = 60
SOCKET_SECONDS = 15
ATTEMPTS = 2


class CorpusError(Exception):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CorpusError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def official_url(url):
    if not isinstance(url, str):
        raise CorpusError("Source URL must be text")
    p = urllib.parse.urlsplit(url)
    if (p.scheme != "https" or p.netloc not in {"www.etsi.org", "etsi.org"}
            or not p.path.startswith("/deliver/etsi_ts/") or p.query or p.fragment):
        raise CorpusError("Only HTTPS ETSI deliver URLs are allowed")
    return url


def load_manifest(path):
    if path.stat().st_size > 256 * 1024:
        raise CorpusError("Manifest exceeds 256 KiB")
    raw = path.read_bytes()
    data = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise CorpusError("Unsupported manifest schema")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,79}", data.get("corpus_id", "")):
        raise CorpusError("Invalid corpus ID")
    release = data.get("release")
    if type(release) is not int or release < 15:
        raise CorpusError("Invalid NR release")
    docs = data.get("documents")
    if not isinstance(docs, list) or not 1 <= len(docs) <= MAX_DOCUMENTS:
        raise CorpusError("Invalid document count")
    specs, filenames = set(), set()
    for doc in docs:
        if not isinstance(doc, dict):
            raise CorpusError("Each document must be a JSON object")
        spec, version = doc.get("spec"), doc.get("version")
        if not isinstance(spec, str) or not re.fullmatch(r"38\.\d{3}", spec):
            raise CorpusError("Invalid specification number")
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise CorpusError(f"Invalid version for {spec}")
        if int(version.split(".")[0]) != release:
            raise CorpusError(f"Release mismatch for {spec}")
        filename = f"ts_{spec.replace('.', '')}_v{version}.pdf"
        if doc.get("filename") != filename or spec in specs or filename in filenames:
            raise CorpusError("Duplicate entry or unsafe/noncanonical filename")
        specs.add(spec)
        filenames.add(filename)
        if type(doc.get("size_bytes")) is not int or not 1 <= doc["size_bytes"] <= MAX_FILE_BYTES:
            raise CorpusError(f"Invalid size for {spec}")
        if not re.fullmatch(r"[a-f0-9]{64}", doc.get("sha256", "")):
            raise CorpusError(f"Missing/invalid SHA-256 for {spec}")
        if not isinstance(doc.get("title"), str) or not doc["title"].strip():
            raise CorpusError(f"Missing title for {spec}")
        if type(doc.get("page_count")) is not int or not 1 <= doc["page_count"] <= 2000:
            raise CorpusError(f"Invalid page count for {spec}")
        official_url(doc.get("url"))
        number = "1" + spec.replace(".", "")
        group = number[:4] + "00_" + number[:4] + "99"
        digits = "".join(f"{int(v):02d}" for v in version.split("."))
        folder = ".".join(f"{int(v):02d}" for v in version.split(".")) + "_60"
        expected = f"/deliver/etsi_ts/{group}/{number}/{folder}/ts_{number}v{digits}p.pdf"
        if urllib.parse.urlsplit(doc["url"]).path != expected:
            raise CorpusError(f"URL does not match pinned specification/version: {spec}")
    return data, hashlib.sha256(raw).hexdigest()


def no_symlinks(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise CorpusError(f"Symlink is not allowed: {part}")


def check_file(path, doc):
    no_symlinks(path)
    if not path.is_file():
        raise CorpusError(f"Missing file: {doc['filename']}")
    if path.stat().st_size != doc["size_bytes"]:
        raise CorpusError(f"Size mismatch: {doc['filename']}; restore the pinned file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise CorpusError(f"Not a PDF: {doc['filename']}")
        stream.seek(0)
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    if digest.hexdigest() != doc["sha256"]:
        raise CorpusError(f"SHA-256 mismatch: {doc['filename']}; do not change the lock to accept it")


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_stream(doc, destination):
    """Write only a temporary file. Parent enforces wall-clock deadline."""
    request = urllib.request.Request(official_url(doc["url"]), headers={
        "User-Agent": "Mozilla/5.0 WirelessAssistant-Corpus/1.0",
        "Accept": "application/pdf", "Accept-Encoding": "identity",
    })
    opener = urllib.request.build_opener(OfficialRedirects())
    with opener.open(request, timeout=SOCKET_SECONDS) as response:
        official_url(response.geturl())
        if response.status != 200:
            raise CorpusError(f"Unexpected HTTP status: {response.status}")
        count = 0
        with destination.open("wb") as out:
            while block := response.read(65536):
                count += len(block)
                if count > doc["size_bytes"]:
                    raise CorpusError("Response exceeds pinned size; refusing replacement")
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
    check_file(destination, doc)


def download_worker(doc, destination, connection):
    try:
        download_stream(doc, destination)
        connection.send((True, "", False))
    except urllib.error.HTTPError as exc:
        connection.send((False, f"HTTP {exc.code}", exc.code in {408, 429, 500, 502, 503, 504}))
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        connection.send((False, f"Network failure: {str(exc)[:160]}", True))
    except Exception as exc:
        connection.send((False, f"{type(exc).__name__}: {str(exc)[:240]}", False))
    finally:
        connection.close()


def bounded_download(doc, temporary, seconds):
    ctx = multiprocessing.get_context("spawn")
    reader, writer = ctx.Pipe(duplex=False)
    worker = ctx.Process(target=download_worker, args=(doc, temporary, writer))
    worker.start()
    writer.close()
    try:
        worker.join(seconds)
        if worker.is_alive():
            return False, "Download wall-clock deadline exceeded", True
        if reader.poll():
            try:
                return reader.recv()
            except EOFError:
                pass
        return False, "Download process exited without a result", False
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(1)
        if worker.is_alive():
            worker.kill()
            worker.join(1)
        reader.close()
        if worker.is_alive():
            raise CorpusError("Cannot stop download worker; aborting without marking ready")
        worker.close()


def fetch_one(doc, path, deadline):
    no_symlinks(path)
    if path.exists():
        check_file(path, doc)
        print(f"Verified existing: {doc['spec']} v{doc['version']}", flush=True)
        return
    fd, name = tempfile.mkstemp(prefix=".download-", suffix=".part", dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        for attempt in range(ATTEMPTS):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CorpusError("Overall command deadline exceeded; rerun to reuse verified files")
            ok, error, retryable = bounded_download(doc, temporary, min(ATTEMPT_SECONDS, remaining))
            if ok:
                check_file(temporary, doc)
                os.replace(temporary, path)
                print(f"Downloaded and verified: {doc['spec']} v{doc['version']}", flush=True)
                return
            if not retryable or attempt + 1 == ATTEMPTS:
                raise CorpusError(f"{doc['spec']}: {error}. See corpus/README.md for manual recovery")
            if deadline - time.monotonic() <= 1:
                raise CorpusError("Overall command deadline exceeded")
            time.sleep(1)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def exclusive(root):
    no_symlinks(root)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".corpus.lock"
    try:
        with lock.open("x") as out:
            out.write(f"pid={os.getpid()}\n")
    except FileExistsError:
        raise CorpusError("Another operation or stale .corpus.lock exists; see corpus/README.md") from None
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def prepare(manifest, manifest_hash, root, fetch):
    deadline = time.monotonic() + COMMAND_SECONDS
    with exclusive(root):
        receipt = root / "verified.json"
        no_symlinks(receipt)
        receipt.unlink(missing_ok=True)
        raw = root / "raw"
        no_symlinks(raw)
        raw.mkdir(exist_ok=True)
        for doc in manifest["documents"]:
            if time.monotonic() >= deadline:
                raise CorpusError("Overall command deadline exceeded")
            path = raw / doc["filename"]
            if fetch:
                fetch_one(doc, path, deadline)
            else:
                check_file(path, doc)
                print(f"Verified: {doc['spec']} v{doc['version']}", flush=True)
        # Recheck the whole collection before writing the all-files receipt.
        for doc in manifest["documents"]:
            if time.monotonic() >= deadline:
                raise CorpusError("Overall command deadline exceeded")
            check_file(raw / doc["filename"], doc)
        record = {
            "corpus_id": manifest["corpus_id"], "manifest_sha256": manifest_hash,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "status": "sources_verified_not_indexed",
            "documents": [{k: d[k] for k in ("spec", "version", "filename", "sha256", "size_bytes")}
                          for d in manifest["documents"]],
        }
        fd, name = tempfile.mkstemp(prefix=".receipt-", suffix=".tmp", dir=root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(record, out, indent=2)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, receipt)
        finally:
            Path(name).unlink(missing_ok=True)
    print(f"Verified all {len(manifest['documents'])} PDFs. Receipt: {receipt}")
    print("Source acquisition only; parsing, indexing and chatbot acceptance are separate.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "fetch", "verify"))
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--output", type=Path, help="Collection directory; default: ignored data/corpus/<corpus_id>")
    args = parser.parse_args(argv)
    try:
        manifest, digest = load_manifest(args.manifest)
        if args.command == "list":
            print(f"{manifest['corpus_id']} | Release {manifest['release']} | manifest SHA-256 {digest}")
            for doc in manifest["documents"]:
                print(f"{doc['spec']} v{doc['version']} | {doc['size_bytes']} bytes | {doc['title']}")
            return 0
        root = args.output or REPO / "data" / "corpus" / manifest["corpus_id"]
        prepare(manifest, digest, root.absolute(), fetch=args.command == "fetch")
        return 0
    except (CorpusError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Canceled; verified completed files are reusable. No partial collection is ready.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

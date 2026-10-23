# Reproduce the source collection

[manifest.json](manifest.json) is the source lock for the owner's initial 12 specifications: seven PHY specifications, 38.300 as the overall description, and 38.314/38.321/38.322/38.323. It records exact versions, official PDF URLs, original 3GPP archive directories, publication months, SHA-256 hashes, byte sizes and page counts.

**Baseline:** `nr-l1-l2-rel18-2026-10-24`, Release 18. Each entry uses the highest Release 18 PDF version observed in its official ETSI directory on 24 October 2026. Downloads use the committed pins; they never resolve “latest.” Minor versions and publication dates differ because specifications evolve separately. This is a reproducible development source baseline, not a domain-reviewed release or proof that every cross-reference is covered.

ETSI publishes these 3GPP specifications under corresponding ETSI identifiers; each downloaded cover was checked for the exact 3GPP number, version and Release. The lock hashes the **ETSI PDF bytes**, not the 3GPP ZIP/Word edition. A matching specification version in another file format does not have the same checksum and cannot be substituted silently.

## Clone and prepare

Requires Git, Python 3.10+ and internet access to the official ETSI downloads. No Python packages, cloud API key, model, Git LFS or account are required by this source-acquisition tool. Python 3.12 was used for initial validation.

```bash
git clone https://github.com/Yuvraj-arch79/wireless-assistant.git
cd wireless-assistant
python scripts/corpus.py list
python scripts/corpus.py fetch
python scripts/corpus.py verify
```

Use `python3` or `py -3` if that is your platform's Python command. Run commands from the repository root. `list` validates the manifest and prints the inventory without network or filesystem writes. `fetch` downloads missing files and verifies every file. `verify` performs the same byte/hash checks without network access.

By default, files go into `data/corpus/nr-l1-l2-rel18-2026-10-24/raw/`. A successful full check writes `verified.json` next to `raw/`. It contains the manifest's SHA-256 and all checked file identities with status `sources_verified_not_indexed`. Both are ignored by Git through the existing `/data/` rule.

The pinned files total **21,038,039 bytes (about 20.1 MiB), 1,915 PDF pages**. Only metadata, this guide, the small downloader and offline tests are committed. Original PDFs, extracted content, embeddings, indexes and verification receipts stay local. Publisher notices remain in the unchanged PDFs.

Optional: `--output /path/to/local/corpus` selects another local collection directory; use the same option for `fetch` and `verify`. An output location inside the repository but outside `/data/` is not automatically ignored. `--manifest path/to/manifest.json` selects a reviewed alternative lock; normally use the committed default.

## Failure and recovery

- Verified existing files are reused without downloading them again. A corrupt or wrong-version existing file causes an error and is never silently overwritten. Move that file out of `raw/`, then rerun `fetch` to retrieve the pinned original.
- Downloads go to temporary files. Exact size, PDF signature and SHA-256 must all match before atomic promotion to the expected filename. An HTML error page or changed publisher file cannot become a verified PDF.
- Each download attempt has a 60-second wall-clock deadline and a 15-second socket timeout; there are at most two attempts per missing file and a 600-second overall command budget. Hung download processes are terminated, with bounded cleanup. There is no endless retry or automatic version substitution.
- A failed or canceled command exits nonzero. Previously completed PDFs remain reusable. An all-files receipt is written only after the entire collection is verified; an old receipt is removed before a new check begins. Consumers must reverify at ingestion time rather than treat an old receipt as permanent proof.
- Only one operation may use a collection directory at a time. After an abrupt crash, ensure no corpus process is running before manually removing that directory's `.corpus.lock` and leftover `.download-*.part` / `.receipt-*.tmp` files. Then rerun the command. Do not remove an active process's lock.
- If the official site is blocked or unavailable, use the **exact `url`** from the manifest in a browser, save the PDF with the manifest's `filename` into `raw/`, and run `verify`. Missing files still fail verification. Never use an unreviewed mirror or update a hash just to make a failed check pass.
- Files and collection directories reached through symlinks are rejected. Select a regular local path.

HTTPS is restricted to ETSI's deliver endpoint, including redirects. Checksums reproduce the files inspected when this repository revision was prepared; they are not publisher-issued signatures. Retain the Git commit ID alongside experiment results.

## Boundary with ingestion and the chatbot

This tool acquires source documents before runtime questions. It does not parse tables/formulas, create chunks or embeddings, activate a retrieval collection, or call A/B/C. Follow [the implementation handoff](../docs/design/implementation-guide.md) for those steps. A future corpus build must record this manifest hash together with parser, chunker and embedding configuration versions. Identical PDFs alone do not guarantee identical indexes.

The inventory follows the owner's initial list. It is not every 38-series specification or a claim of complete Layer-2 coverage: SDAP (38.324), RRC (38.331), capabilities (38.306), RAN interfaces and core-network specifications are not included. These documents can be referenced by the selected PDFs. Retrieval must report unavailable dependencies or coverage gaps; downloading this collection does not authorize invented answers about absent sources. Cross-reference expansion must remain within the prepared inventory unless a maintainer deliberately updates it.

## Updating the baseline

1. Open a focused PR explaining the specification/version change and the affected coverage. Preserve old pins in Git history; use a new `corpus_id` for a changed source set so it has a separate local directory.
2. Retrieve each proposed PDF directly from its official version-specific URL. Check its cover number, version and Release, title and publication date. Compute SHA-256 and byte count from the original downloaded bytes; check page count with a PDF reader. Never derive hashes from extracted text or a regenerated PDF.
3. Update the manifest, date and selection rationale. A release change needs an explicit scope/default-release decision, not an automatic download fallback.
4. Run the offline tests, then `fetch` into a clean collection and `verify`. Record the manifest hash and result in the PR. Do not attach source PDFs or generated data to the PR.
5. Before making the new source set active in the future chatbot, run parsing/retrieval and relevant answer-regression evaluations. Keep earlier evidence snapshots available for saved citations, as required by the LLD.

Roll back by using the manifest and tool from the previous reviewed Git revision and its separate local collection. Source acquisition is never part of a user question. Providers/models, retrieval evaluation and application acceptance remain separate decisions.

## Checks

```bash
python -m unittest discover -s tests -v
python docs/design/validate_design.py
```

Offline tests cover the 12-spec inventory, unsafe/mismatched paths and URLs, duplicate entries, mixed releases, corrupt/truncated/HTML files, reuse without network calls, oversized responses, retry limits, hung-process termination, concurrent operations, symlinks and failed-collection receipts. CI runs these without downloading standards. Live source acquisition is an explicit developer operation.

Initial source verification on 24 October 2026: all 12 PDFs were obtained from ETSI, their exact cover identities checked, and byte hashes/sizes/page counts recorded. This verifies source identity, not extraction quality, technical completeness or chatbot accuracy.

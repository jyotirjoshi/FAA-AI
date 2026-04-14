import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.indexing.chunker import SectionChunker
from src.ingest.ecfr_api_loader import ingest_ecfr_part25, ingest_ecfr_title14_full
from src.ingest.faa_scraper import crawl_source
from src.ingest.pdf_loader import file_url, ingest_pdf, save_pdf_docs
from src.ingest.sources import DEFAULT_SOURCES, ECFR_TITLE14_FULL_SOURCE
from src.models import SectionDocument


def load_jsonl_docs(path: Path) -> list[SectionDocument]:
    docs: list[SectionDocument] = []
    if not path.exists():
        return docs
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            docs.append(SectionDocument(**json.loads(line)))
    return docs


def resolve_sources(selected_source_ids: list[str]) -> list[dict]:
    if not selected_source_ids:
        return DEFAULT_SOURCES

    by_id = {source["id"]: source for source in DEFAULT_SOURCES}
    selected: list[dict] = []
    for source_id in selected_source_ids:
        source = by_id.get(source_id)
        if source is None:
            valid_ids = ", ".join(sorted(by_id))
            raise ValueError(f"Unknown source id: {source_id}. Valid values: {valid_ids}")
        selected.append(source)
    return selected


def main() -> None:
    print("Starting build_index")
    parser = argparse.ArgumentParser(description="Build regulation chatbot index")
    parser.add_argument("--skip-crawl", action="store_true", help="Use existing data/raw/*.jsonl")
    parser.add_argument(
        "--pdf",
        action="append",
        default=[],
        help="Optional PDF path to ingest. Can be repeated.",
    )
    parser.add_argument(
        "--pdf-dir",
        action="append",
        default=[],
        help="Optional directory to recursively ingest all PDFs. Can be repeated.",
    )
    parser.add_argument(
        "--website-only",
        action="store_true",
        help="Index only the configured websites and ignore PDF inputs.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete previous website raw files and current index artifacts before rebuilding.",
    )
    parser.add_argument(
        "--title14-full",
        action="store_true",
        help="Ingest full eCFR Title 14 by all Parts and Sections.",
    )
    parser.add_argument(
        "--title14-only",
        action="store_true",
        help="Index only eCFR Title 14 data and skip other website sources.",
    )
    parser.add_argument(
        "--title14-max-parts",
        type=int,
        default=0,
        help="Optional cap for Title 14 parts during testing. 0 means all parts.",
    )
    parser.add_argument(
        "--title14-history-limit",
        type=int,
        default=3,
        help="Number of Title 14 issue dates to ingest. 1 means current only; default is current + previous + older snapshot. 0 means all available historical snapshots.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help=(
            "Optional source id to include. Can be repeated. "
            "Valid ids: faa_far_part25, faa_advisory_circulars, faa_ecfr_part25_fallback, tc_car_525"
        ),
    )
    args = parser.parse_args()

    if args.title14_only and not args.title14_full:
        args.title14_full = True

    selected_sources = [] if args.title14_only else resolve_sources(args.source)

    settings.raw_dir.mkdir(parents=True, exist_ok=True)

    if args.reset:
        for source in selected_sources:
            p = settings.raw_dir / f"{source['id']}.jsonl"
            if p.exists():
                p.unlink()
        if args.title14_full:
            p = settings.raw_dir / f"{ECFR_TITLE14_FULL_SOURCE['id']}.jsonl"
            if p.exists():
                p.unlink()
            checkpoint = settings.raw_dir / f"{ECFR_TITLE14_FULL_SOURCE['id']}.checkpoint.json"
            if checkpoint.exists():
                checkpoint.unlink()
        if (settings.index_dir / "embeddings.npy").exists():
            (settings.index_dir / "embeddings.npy").unlink()
        if (settings.index_dir / "chunks.jsonl").exists():
            (settings.index_dir / "chunks.jsonl").unlink()
        print("Reset previous website raw/index artifacts")

    all_docs: list[SectionDocument] = []

    if not args.skip_crawl:
        for source in selected_sources:
            print(f"Crawling source: {source['id']}")
            if source["id"] == "faa_ecfr_part25_fallback":
                history_limit = args.title14_history_limit if args.title14_full else 10
                docs = ingest_ecfr_part25(settings.raw_dir, source=source, history_limit=history_limit)
            else:
                docs = crawl_source(source, settings.raw_dir)
            all_docs.extend(docs)
            print(f"Loaded from crawl {source['id']}: {len(docs)} docs")

        if args.title14_full:
            print(f"Crawling source: {ECFR_TITLE14_FULL_SOURCE['id']}")
            max_parts = args.title14_max_parts if args.title14_max_parts > 0 else None
            docs = ingest_ecfr_title14_full(
                settings.raw_dir,
                source=ECFR_TITLE14_FULL_SOURCE,
                max_parts=max_parts,
                history_limit=args.title14_history_limit,
            )
            all_docs.extend(docs)
            print(f"Loaded from crawl {ECFR_TITLE14_FULL_SOURCE['id']}: {len(docs)} docs")

    for source in selected_sources:
        docs = load_jsonl_docs(settings.raw_dir / f"{source['id']}.jsonl")
        all_docs.extend(docs)
        print(f"Loaded raw file {source['id']}: {len(docs)} docs")

    if args.title14_full:
        docs = load_jsonl_docs(settings.raw_dir / f"{ECFR_TITLE14_FULL_SOURCE['id']}.jsonl")
        all_docs.extend(docs)
        print(f"Loaded raw file {ECFR_TITLE14_FULL_SOURCE['id']}: {len(docs)} docs")

    if not args.website_only:
        for pdf_path in args.pdf:
            p = Path(pdf_path)
            if not p.exists():
                continue
            docs = ingest_pdf(p, source_id=f"pdf_{p.stem}", source_url=file_url(p))
            save_pdf_docs(docs, settings.raw_dir / f"pdf_{p.stem}.jsonl")
            all_docs.extend(docs)

        for folder in args.pdf_dir:
            folder_path = Path(folder)
            if not folder_path.exists() or not folder_path.is_dir():
                continue
            pdf_paths = {p.resolve() for p in folder_path.rglob("*.pdf")}
            pdf_paths.update({p.resolve() for p in folder_path.rglob("*.PDF")})
            for p in sorted(pdf_paths):
                docs = ingest_pdf(p, source_id=f"pdf_{p.stem}", source_url=file_url(p))
                save_pdf_docs(docs, settings.raw_dir / f"pdf_{p.stem}.jsonl")
                all_docs.extend(docs)

    deduped = {}
    for d in all_docs:
        key = (d.page_url, d.section_path, d.content[:200])
        deduped[key] = d

    docs_unique = list(deduped.values())

    chunker = SectionChunker(max_chars=1200, overlap=180)
    chunks = chunker.chunk(docs_unique)

    print("Initializing embedding model and vector store...")
    from src.indexing.vector_store import LocalVectorStore

    store = LocalVectorStore(settings.index_dir)
    store.build(chunks)

    print(f"Total loaded docs (pre-dedupe): {len(all_docs)}")
    print(f"Indexed docs: {len(docs_unique)}")
    print(f"Indexed chunks: {len(chunks)}")


if __name__ == "__main__":
    main()

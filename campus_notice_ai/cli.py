from __future__ import annotations

import argparse
import sys
from pathlib import Path

from campus_notice_ai.db import connect, init_db
from campus_notice_ai.embeddings import embed_notice_chunks
from campus_notice_ai.eval import load_eval_questions, run_rag_eval
from campus_notice_ai.notice_repository import (
    reindex_all_notices,
    reindex_notice_by_id_or_url,
    seed_notices,
)
from campus_notice_ai.rag import answer_question
from campus_notice_ai.search import build_extract_answer, search_chunks
from campus_notice_ai.server import crawl_and_store, run_server
from campus_notice_ai.validation import validate_real_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="campus-notice-ai",
        description="단국대학교 공지 RAG 데이터 기반 MVP CLI",
    )
    parser.add_argument(
        "--db",
        help="SQLite DB path. Defaults to data/campus_notice_ai.sqlite3.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Create or migrate the local SQLite DB.")
    subparsers.add_parser("seed-notices", help="Insert or update sample notices.")
    subparsers.add_parser("reindex-all", help="Recreate chunks for all notices.")
    embed = subparsers.add_parser("embed-all", help="Create embeddings for notice chunks.")
    embed.add_argument("--batch-size", type=int, default=32, help="Embedding request batch size.")
    embed.add_argument("--limit", type=int, help="Maximum chunks to embed.")
    embed.add_argument("--force", action="store_true", help="Recreate embeddings for all selected chunks.")
    crawl = subparsers.add_parser("crawl-dku", help="Crawl accessible public Dankook notice pages.")
    crawl.add_argument("--limit", type=int, default=3, help="Notices per source.")
    crawl.add_argument(
        "--source",
        action="append",
        help="Source key to crawl. Can be repeated. Defaults to all configured sources.",
    )
    validate = subparsers.add_parser(
        "validate-real-data",
        help="Crawl configured Dankook sources and summarize real-data ingestion quality.",
    )
    validate.add_argument("--limit", type=int, default=10, help="Notices per source.")
    validate.add_argument(
        "--source",
        action="append",
        help="Source key to validate. Can be repeated. Defaults to all configured sources.",
    )
    validate.add_argument(
        "--no-embed",
        action="store_true",
        help="Skip embedding generation during validation.",
    )

    eval_rag = subparsers.add_parser("eval-rag", help="Run source-retrieval RAG evaluation.")
    eval_rag.add_argument(
        "--eval-file",
        help="Path to evals/rag_questions.json. Defaults to the project eval file.",
    )
    eval_rag.add_argument("--limit", type=int, default=5, help="Sources to retrieve per question.")

    search = subparsers.add_parser("search", help="Search indexed notice chunks.")
    search.add_argument("query", help="Search query.")
    search.add_argument("--department", help="Optional department context.")
    search.add_argument("--grade", help="Optional grade context.")
    search.add_argument("--course-id", help="Optional course context.")
    search.add_argument("--limit", type=int, default=5)

    chat = subparsers.add_parser("chat", help="Ask a source-grounded RAG question.")
    chat.add_argument("query", help="Question to answer.")
    chat.add_argument("--department", help="Optional department context.")
    chat.add_argument("--grade", help="Optional grade context.")
    chat.add_argument("--course-id", help="Optional course context.")
    chat.add_argument("--limit", type=int, default=3)

    serve = subparsers.add_parser("serve", help="Run the local web MVP.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Do not seed/reindex automatically when the DB is empty.",
    )

    reindex_one = subparsers.add_parser(
        "reindex-one",
        help="Recreate chunks for one notice by id or original_url.",
    )
    reindex_one.add_argument("notice", help="Notice id or original_url.")

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.db).expanduser().resolve() if args.db else None

    if args.command == "validate-real-data":
        result = validate_real_data(
            db_path,
            limit=args.limit,
            source_keys=args.source,
            embed_after=not args.no_embed,
        )
        print("Real data validation results")
        print(f"- imported notices: {result['imported']}")
        embedding = result.get("embedding")
        if embedding:
            if embedding.get("error"):
                print(f"- embeddings created: 0 (error: {embedding['error']})")
            else:
                print(
                    f"- embeddings created: {embedding.get('embedded', 0)} / "
                    f"{embedding.get('total_selected', 0)}"
                )
        for source in result["sources"]:
            print(f"\nSource: {source['source']}")
            print(f"- crawled notices: {source['crawled_notices']}")
            print(f"- title extracted: {source['title_extracted']}/{source['crawled_notices']}")
            print(f"- body extracted: {source['body_extracted']}/{source['crawled_notices']}")
            print(f"- original_url present: {source['original_url_present']}/{source['crawled_notices']}")
            print(f"- attachments found: {source['attachments_found']}")
            print(f"- pdf parsed: {source['pdf_parsed']}/{source['pdf_total']}")
            print(f"- pdf failed: {source['pdf_failed']}")
            print(f"- images found: {source['images_found']}")
            print(f"- image cached: {source['image_cached']}/{source['images_found']}")
            print(f"- ocr available: {source['ocr_available']}/{source['images_found']}")
            print(f"- chunks created: {source['chunks_created']}")
            print(f"- embeddings created: {source['embeddings_created']}")
            print(f"- evidence ready checks: {source['evidence_ready']}")
            print(f"- failures: {source['failures']}")
            if source.get("error"):
                print(f"- error: {source['error']}")
        return 0

    with connect(db_path) as conn:
        init_db(conn)

        if args.command == "init-db":
            print(f"DB initialized: {conn.execute('PRAGMA database_list').fetchone()[2]}")
            return 0

        if args.command == "seed-notices":
            count = seed_notices(conn)
            print(f"Seed notices upserted: {count}")
            return 0

        if args.command == "crawl-dku":
            result = crawl_and_store(db_path, limit=args.limit, source_keys=args.source)
            print(f"Crawled notices imported: {result['imported']}")
            for source in result["sources"]:
                if "attachments" in source:
                    print(
                        f"- {source['source']}: {source['imported']} notices, "
                        f"{source['attachments']} attachments, "
                        f"{source['parsed_attachments']} parsed"
                    )
                else:
                    print(f"- {source['source']}: {source['imported']}")
            return 0

        if args.command == "reindex-all":
            result = reindex_all_notices(conn)
            total_chunks = sum(result.values())
            print(f"Reindexed notices: {len(result)}")
            print(f"Created chunks: {total_chunks}")
            return 0

        if args.command == "embed-all":
            result = embed_notice_chunks(
                conn,
                batch_size=args.batch_size,
                limit=args.limit,
                force=args.force,
            )
            print(f"Embedded chunks: {result['embedded']} / {result['total_selected']}")
            print(f"Embedding model: {result['model']}")
            if result["dimensions"]:
                print(f"Embedding dimensions: {result['dimensions']}")
            return 0

        if args.command == "reindex-one":
            notice_id, chunk_count = reindex_notice_by_id_or_url(conn, args.notice)
            print(f"Reindexed notice: {notice_id}")
            print(f"Created chunks: {chunk_count}")
            return 0

        if args.command == "search":
            results = search_chunks(
                conn,
                args.query,
                department=args.department,
                grade=args.grade,
                course_id=args.course_id,
                limit=args.limit,
            )
            print(build_extract_answer(args.query, results))
            for index, result in enumerate(results, start=1):
                metadata = result["metadata"]
                print(f"\n{index}. {result['title']} (score {result['score']})")
                print(f"   게시일: {metadata.get('published_at') or '-'}")
                print(f"   마감일: {metadata.get('deadline_at') or '-'}")
                print(f"   출처: {metadata.get('original_url') or '-'}")
                print(f"   {result['snippet']}")
            return 0

        if args.command == "chat":
            response = answer_question(
                conn,
                args.query,
                department=args.department,
                grade=args.grade,
                course_id=args.course_id,
                limit=args.limit,
            )
            print(response["answer"])
            print(f"\nmode: {response['mode']}")
            print(f"confidence: {response['confidence']}")
            for index, source in enumerate(response["sources"], start=1):
                print(f"\n{index}. {source['title']}")
                print(f"   작성자: {source.get('publisher') or '-'}")
                print(f"   게시일: {source.get('published_at') or '-'}")
                print(f"   마감일: {source.get('deadline_at') or '-'}")
                print(f"   출처: {source.get('original_url') or '-'}")
                print(f"   근거: {source.get('matched_text') or '-'}")
            return 0

        if args.command == "eval-rag":
            questions = load_eval_questions(args.eval_file)
            result = run_rag_eval(conn, questions, limit=args.limit)
            print("RAG eval results")
            print(f"- total: {result['total']}")
            print(f"- passed: {result['passed']}")
            print(f"- failed: {result['failed']}")
            print(f"- pass_rate: {result['pass_rate']}%")
            for item in result["results"]:
                status = "PASS" if item["passed"] else "FAIL"
                print(f"{status} {item['id']}: {item['query']}")
                if item["failures"]:
                    print(f"  - {'; '.join(item['failures'])}")
                if item["top_source"]:
                    print(f"  - top: {item['top_source']} ({item['top_chunk_type'] or 'body'})")
            return 0

        if args.command == "serve":
            counts = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
            if counts == 0 and not args.no_bootstrap:
                seed_notices(conn)
                reindex_all_notices(conn)
            run_server(args.host, args.port, db_path)
            return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

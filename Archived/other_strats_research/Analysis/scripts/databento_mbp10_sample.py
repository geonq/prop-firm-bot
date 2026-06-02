"""Request or inspect a small Databento GLBX.MDP3 MBP-10 sample.

This script reads DATABENTO_API_KEY from the environment or local .env file.
It never prints the key.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_OUTPUT_DIR = Path("TVExports/mbp10_sample")


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit/download a Databento MBP-10 batch sample.")
    parser.add_argument("--symbol", default="MNQ.FUT", help="Parent or raw symbol. Default: MNQ.FUT.")
    parser.add_argument("--start", help="Start timestamp for --submit, e.g. 2026-04-27T13:30:00Z.")
    parser.add_argument("--end", help="End timestamp for --submit, e.g. 2026-04-27T20:00:00Z.")
    parser.add_argument("--encoding", default="dbn", choices=("dbn", "csv", "json"), help="Flat-file encoding.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Download directory.")
    parser.add_argument("--submit", action="store_true", help="Submit a new batch request.")
    parser.add_argument("--download-job", help="Download an existing Databento batch job id.")
    parser.add_argument("--stype-in", default="parent", help="Databento symbol type. Parent futures use ROOT.FUT, e.g. MNQ.FUT.")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        raise SystemExit("DATABENTO_API_KEY is not set. Add it to .env first.")

    import databento as db

    client = db.Historical(api_key)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.submit:
        if not args.start or not args.end:
            raise SystemExit("--submit requires --start and --end.")
        job = client.batch.submit_job(
            dataset="GLBX.MDP3",
            symbols=args.symbol,
            schema="mbp-10",
            start=args.start,
            end=args.end,
            encoding=args.encoding,
            compression="zstd",
            split_duration="day",
            stype_in=args.stype_in,
        )
        print(f"Submitted job: {job['id'] if isinstance(job, dict) and 'id' in job else job}")
        print("Wait until it is Ready in Databento Download center, then rerun with --download-job JOB_ID.")

    if args.download_job:
        paths = client.batch.download(job_id=args.download_job, output_dir=output_dir)
        print("Downloaded files:")
        for path in paths:
            print(path)

    if not args.submit and not args.download_job:
        print("No action requested. Use --submit or --download-job JOB_ID.")


if __name__ == "__main__":
    main()

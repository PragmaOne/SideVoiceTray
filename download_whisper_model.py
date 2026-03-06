from __future__ import annotations

import argparse
from pathlib import Path

from faster_whisper.utils import download_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a faster-whisper model into a local release folder.")
    parser.add_argument("--model", default="large-v3", help="Whisper model id or size name.")
    parser.add_argument(
        "--output-dir",
        default="dist\\models",
        help="Directory where the local model folder should be stored.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = download_model(
        args.model,
        output_dir=str(output_dir),
        cache_dir=str(output_dir),
        local_files_only=False,
    )
    print(f"Downloaded model to: {Path(model_path).resolve()}")


if __name__ == "__main__":
    main()

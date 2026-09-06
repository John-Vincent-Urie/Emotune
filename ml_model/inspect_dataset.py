#!/usr/bin/env python3
"""Inspect and clean the EmoTune custom dataset."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_local_venv  # noqa: E402

ensure_local_venv('pandas')

from data_pipeline import (  # noqa: E402
    DATASET_PATH,
    ensure_artifacts_dir,
    load_custom_dataset,
    clean_dataset,
    resolve_dataset_path,
    write_json,
)


def main():
    artifacts_dir = ensure_artifacts_dir()
    dataset_path = resolve_dataset_path(DATASET_PATH)
    cleaned_output_path = dataset_path.with_name(
        f'{dataset_path.stem}.cleaned.csv'
    )
    report_output_path = artifacts_dir / 'data_quality_report.json'

    raw_df = load_custom_dataset(dataset_path)
    cleaned_df, report = clean_dataset(raw_df)
    report['dataset_path'] = str(dataset_path)
    report['cleaned_dataset_path'] = str(cleaned_output_path)

    cleaned_df.to_csv(cleaned_output_path, index=False)
    write_json(report_output_path, report)

    print("Dataset inspection complete.")
    print(f"Source dataset: {dataset_path}")
    print(f"Cleaned dataset: {cleaned_output_path}")
    print(f"Data quality report: {report_output_path}")
    print("Label distribution:")
    for label, count in report['label_distribution'].items():
        print(f"  {label}: {count}")


if __name__ == '__main__':
    main()

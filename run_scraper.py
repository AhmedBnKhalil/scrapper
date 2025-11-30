import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List

import pandas as pd
from tqdm import tqdm

from scraper import (
    ScraperConfig,
    load_list_from_file,
    scrape_one_category_location,
    combine_outputs,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Instashop cross-location/category scraper (Playwright + parallel)."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="scraper_config.yaml",
        help="Path to scraper_config.yaml",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cfg_path = Path(args.config).resolve()
    config = ScraperConfig.from_yaml(cfg_path)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)

    categories = load_list_from_file(config.category_file)
    locations = load_list_from_file(config.locations_file)

    if not categories:
        print(f"❌ No categories found in {config.category_file}")
        return
    if not locations:
        print(f"❌ No locations found in {config.locations_file}")
        return

    # Build all (category, location) combinations
    combos = [(cat, loc) for cat in categories for loc in locations]
    total = len(combos)
    print(f"🧮 Total combos to scrape: {total}")
    print(f"🧵 Using {config.workers} workers\n")

    parquet_files: List[Path] = []

    # Run in parallel
    with ProcessPoolExecutor(max_workers=config.workers) as executor:
        future_to_combo = {
            executor.submit(scrape_one_category_location, cat, loc, config): (cat, loc)
            for (cat, loc) in combos
        }

        for future in tqdm(
            as_completed(future_to_combo),
            total=total,
            desc="Scraping combos",
            unit="combo",
        ):
            cat, loc = future_to_combo[future]
            try:
                _cat, _loc, out_path = future.result()
                if out_path and out_path.exists():
                    parquet_files.append(out_path)
                else:
                    print(f"⚠️ No data saved for combo: {cat} @ {loc}")
            except Exception as e:
                print(f"❌ Error in combo {cat} @ {loc}: {e}")

    if not parquet_files:
        print("❌ No parquet outputs found from workers; aborting combine.")
        return

    # Combine all parquet into a single Excel
    combined_xlsx = combine_outputs(parquet_files, config)

    # Simple summary (optional)
    try:
        df = pd.read_excel(combined_xlsx, sheet_name="All_Data")
        summary = (
            df.groupby(["location_used"])
            .agg(
                total_products=("name", "count"),
                unique_names=("name", "nunique"),
                discounted_items=("discount_percent", lambda x: x.notna().sum()),
                out_of_stock=("out_of_stock", lambda x: (x == True).sum()),
            )
            .reset_index()
        )

        with pd.ExcelWriter(combined_xlsx, engine="openpyxl", mode="a", if_sheet_exists="replace") as xl:
            summary.to_excel(xl, index=False, sheet_name="Summary_by_Location")
        print("📊 Summary sheet 'Summary_by_Location' added.")
    except Exception as e:
        print(f"⚠️ Could not add summary sheet: {e}")

    print("\n🎉 DONE. Final combined file:")
    print(combined_xlsx)


if __name__ == "__main__":
    main()

import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

import pandas as pd
import yaml
from tqdm import tqdm
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, Page


# ==============================
# CONFIG DATACLASS & LOADER
# ==============================

@dataclass
class ScraperConfig:
    output_dir: Path
    combined_filename: str
    max_scroll_cycles: int
    rounds_stable: int
    scroll_delay_min: float
    scroll_delay_max: float
    workers: int
    category_file: Path
    locations_file: Path
    user_agents: List[str]
    log_dir: Path

    @classmethod
    def from_yaml(cls, path: Path) -> "ScraperConfig":
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        base = path.parent

        return cls(
            output_dir=(base / cfg["output_dir"]).resolve(),
            combined_filename=cfg["combined_filename"],
            max_scroll_cycles=cfg["max_scroll_cycles"],
            rounds_stable=cfg["rounds_stable"],
            scroll_delay_min=float(cfg["scroll_delay_min"]),
            scroll_delay_max=float(cfg["scroll_delay_max"]),
            workers=int(cfg["workers"]),
            category_file=(base / cfg["category_file"]).resolve(),
            locations_file=(base / cfg["locations_file"]).resolve(),
            user_agents=cfg.get("user_agents", []),
            log_dir=(base / cfg.get("log_dir", "logs")).resolve(),
        )


# ==============================
# INPUT LOADING
# ==============================

def load_list_from_file(path: Path) -> List[str]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            items.append(line)
    return items


# ==============================
# PLAYWRIGHT HELPERS
# ==============================

def build_browser_context_kwargs(config: ScraperConfig) -> Dict[str, Any]:
    ua = random.choice(config.user_agents) if config.user_agents else None
    # Random viewport to look less like a bot
    width = random.randint(1200, 1600)
    height = random.randint(700, 1000)

    kwargs: Dict[str, Any] = {
        "viewport": {"width": width, "height": height},
    }
    if ua:
        kwargs["user_agent"] = ua
    return kwargs


def accept_cookies_if_any(page: Page):
    # We try a few selectors that might be cookie banners. Ignore errors.
    selectors = [
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel)
            if el.is_visible(timeout=3000):
                el.click()
                time.sleep(1)
                return
        except Exception:
            continue


def set_location(page: Page, address: str):
    """
    Tries to set delivery location using the search box:
    'Search for a place'
    """
    try:
        # Might need to open address dialog first
        # Try clicking the address bar
        addr_sel = "div.mat-ripple.address.desktopWidth"
        btn_sel = "button.btn.appearance-filled"

        if page.locator(addr_sel).is_visible(timeout=4000):
            page.locator(addr_sel).click()
            time.sleep(1)

        if page.locator(btn_sel).is_visible(timeout=4000):
            page.locator(btn_sel).click()
            time.sleep(1)

        inp = page.locator("input[placeholder='Search for a place']")
        inp.wait_for(timeout=5000)
        print(f"📍 Setting location: {address}")
        inp.fill(address)
        time.sleep(1.0 + random.random())
        inp.press("ArrowDown")
        time.sleep(0.5)
        inp.press("Enter")
        time.sleep(0.5)
        inp.press("Enter")
        time.sleep(3.0 + random.random())
    except Exception:
        # If anything fails, we just continue with default location.
        print("⚠️ Could not reliably set location (continuing anyway).")


def click_all_items_filter(page: Page):
    """
    Tries to click "All Items" filter if present.
    """
    xpaths = [
        "//label[.//span[normalize-space()='All Items']]",
        "//span[normalize-space()='All Items']",
    ]
    for xp in xpaths:
        try:
            el = page.locator(f"xpath={xp}")
            if el.first.is_visible(timeout=4000):
                el.first.click()
                time.sleep(1 + random.random())
                return
        except Exception:
            continue


def human_like_scroll(page: Page, config: ScraperConfig) -> None:
    """
    Scrolls until no new products appear or a safety cap is reached.
    """
    last_count = 0
    stable_rounds = 0

    for cycle in range(1, config.max_scroll_cycles + 1):
        # Scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")

        delay = random.uniform(config.scroll_delay_min, config.scroll_delay_max)
        print(f"⏱️ Scroll cycle {cycle}: waiting ~{delay:.1f}s")
        time.sleep(delay)

        # Count product cards
        count = page.evaluate(
            "Array.from(document.querySelectorAll('div.product.mb-4.ng-star-inserted')).length"
        )

        if count == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_count = count

        # small upward scroll to trigger lazy load
        if stable_rounds == 1:
            page.evaluate("window.scrollBy(0, -Math.floor(window.innerHeight * 0.4));")

        if stable_rounds >= config.rounds_stable:
            print(f"✅ No new products for {stable_rounds} cycles. Stopping scroll.")
            break


def extract_products(page: Page, category_url: str, location: str) -> pd.DataFrame:
    """
    Extracts product data from the DOM into a DataFrame.
    """
    cards = page.evaluate(
        """
() => {
  const cards = Array.from(
    document.querySelectorAll('div.product.mb-4.ng-star-inserted')
  );
  return cards.map((el, idx) => {
    const getText = (sel) => {
      const node = el.querySelector(sel);
      return node ? node.textContent.trim() : "";
    };

    const name = getText("div.product-title");
    const qty  = getText("div.product-packaging-string");
    const priceContainer = el.querySelector("div.price-container");
    let price = "";
    let oldPrice = "";
    if (priceContainer) {
      const curr = priceContainer.querySelector(".price, .new-price");
      const old  = priceContainer.querySelector(".old-price");
      price = curr ? curr.textContent.trim() : priceContainer.textContent.trim();
      oldPrice = old ? old.textContent.trim() : "";
    }

    const imgEl = el.querySelector("img");
    const imgUrl = imgEl ? imgEl.src : "";

    const outOfStock = !!el.querySelector(".out-of-stock, .product-out-of-stock");

    // Some Instashop pages embed data-id / product-id
    const skuAttr = el.getAttribute("data-id") || el.getAttribute("data-product-id") || "";

    return {
      seen_order: idx + 1,
      name,
      quantity: qty,
      price,
      old_price: oldPrice,
      image_url: imgUrl,
      out_of_stock: outOfStock,
      sku: skuAttr
    };
  });
}
"""
    )

    df = pd.DataFrame(cards)
    if df.empty:
        return df

    # Add extra context columns
    df["category_url"] = category_url
    df["location_used"] = location
    df["timestamp"] = datetime.now().isoformat(timespec="seconds")

    return df


def get_vendor_name(page: Page, category_url: str) -> str:
    try:
        el = page.locator(".client-title")
        if el.is_visible(timeout=3000):
            return el.inner_text().strip()
    except Exception:
        pass

    # Fallback: parse from URL path
    path = urlparse(category_url).path.split("/")
    # Example: /en-eg/client/sarai-market-al-ekbal/category/XXXX
    vendor_slug = ""
    if len(path) >= 4:
        vendor_slug = path[3]
    return vendor_slug.replace("-", " ").title() if vendor_slug else "UnknownVendor"


# ==============================
# CORE SCRAPING FUNCTION
# ==============================

def scrape_one_category_location(
    category_url: str,
    location: str,
    config: ScraperConfig,
) -> Tuple[str, str, Path]:
    """
    Scrapes a single (category_url, location) pair.
    Returns (category_url, location, output_file_path)
    """
    print(f"\n====== SCRAPING ======\nURL: {category_url}\nLocation: {location}\n")

    # One browser per call (to be used safely in parallel)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # you requested visible mode
        context_kwargs = build_browser_context_kwargs(config)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            # 1) Go to locale homepage (optional) to set cookies/location
            # Derive locale from URL if possible, else just open category directly
            try:
                path_parts = urlparse(category_url).path.split("/")
                if len(path_parts) > 1 and path_parts[1]:
                    locale = path_parts[1]  # e.g. "en-eg"
                else:
                    locale = "en-eg"
            except Exception:
                locale = "en-eg"

            base_url = f"https://instashop.com/{locale}"
            page.goto(base_url, wait_until="domcontentloaded")
            time.sleep(2 + random.random())

            accept_cookies_if_any(page)
            set_location(page, location)

            # 2) Open category page
            page.goto(category_url, wait_until="domcontentloaded")
            time.sleep(3 + random.random())

            click_all_items_filter(page)

            # 3) Scroll to load all products
            human_like_scroll(page, config)

            # 4) Extract products
            df = extract_products(page, category_url, location)
            if df.empty:
                print("⚠️ No products found for this combo.")
            vendor = get_vendor_name(page, category_url)
        finally:
            context.close()
            browser.close()

    if df.empty:
        # Return a dummy path
        return category_url, location, Path()

    # 5) Save
    config.output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_vendor = (
        "".join(ch if ch.isalnum() or ch in " _-" else "_" for ch in vendor)
        .strip()
        .replace(" ", "_")
    )
    safe_loc = "".join(ch if ch.isalnum() or ch in " _-" else "_" for ch in location).strip().replace(" ", "_")

    out_name = f"{safe_vendor}__{safe_loc}__{ts}.parquet"
    out_path = config.output_dir / out_name

    df.to_parquet(out_path, index=False)
    print(f"💾 Saved {len(df)} rows to {out_path}")

    return category_url, location, out_path


# ==============================
# COMBINER
# ==============================

def combine_outputs(parquet_files: List[Path], config: ScraperConfig) -> Path:
    if not parquet_files:
        print("⚠️ No parquet files to combine.")
        return config.output_dir / config.combined_filename

    print("\n📦 Combining all parquet outputs...")
    dfs = []
    for p in tqdm(parquet_files, desc="Reading parquet files"):
        try:
            df = pd.read_parquet(p)
            dfs.append(df)
        except Exception as e:
            print(f"⚠️ Failed to read {p}: {e}")

    if not dfs:
        print("⚠️ No valid dataframes read.")
        return config.output_dir / config.combined_filename

    full = pd.concat(dfs, ignore_index=True)

    # Basic cleaning / dedup:
    full.drop_duplicates(
        subset=["category_url", "location_used", "name", "quantity", "price"],
        keep="first",
        inplace=True,
    )

    # Simple discount % calculation
    def parse_price(s):
        if not isinstance(s, str):
            return None
        digits = "".join(ch if ch.isdigit() or ch in ".,-" else "" for ch in s)
        if not digits:
            return None
        try:
            return float(digits.replace(",", "."))
        except ValueError:
            return None

    full["price_numeric"] = full["price"].apply(parse_price)
    full["old_price_numeric"] = full["old_price"].apply(parse_price)
    full["discount_percent"] = (
        (full["old_price_numeric"] - full["price_numeric"])
        / full["old_price_numeric"]
        * 100
    ).where(
        (full["old_price_numeric"].notna())
        & (full["price_numeric"].notna())
        & (full["old_price_numeric"] > 0),
        None,
    )

    # Summary sheet (optional) will be done in run_scraper

    out_xlsx = config.output_dir / config.combined_filename
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as xl:
        full.to_excel(xl, index=False, sheet_name="All_Data")

    print(f"✅ Combined Excel saved to: {out_xlsx}")
    return out_xlsx

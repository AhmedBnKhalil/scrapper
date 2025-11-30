# 🛒 Instashop Multi-Location Scraper

### **Playwright + Multiprocessing + Visible Browser + Combined Excel Output**

This scraper collects product data from Instashop category pages across multiple delivery locations.
It uses:

* **Playwright** (visible mode)
* **8 parallel workers**
* **Random user agents**
* **Human-like scrolling**
* **Anti-bot behavior**
* **Per-combo parquet files**
* **Final combined Excel output**
* **Summary sheet**

---

## 📦 1. Project Structure

Your folder should contain:

```
scraper/
│
├── scraper.py               # Main scraper logic (Playwright)
├── run_scraper.py           # CLI launcher (parallel execution)
│
├── scraper_config.yaml      # Settings file
├── categories.txt           # Category URLs (one per line)
├── locations.txt            # Delivery locations (one per line)
│
├── instashop_output/        # Auto-created output folder
└── instashop_logs/          # Auto-created logs folder
```

---

## ⚙️ 2. Installation

### 2.1 Install dependencies

```bash
pip install playwright pandas openpyxl tqdm
```

### 2.2 Install Playwright browsers

```bash
playwright install
```

---

## 📝 3. Configuration (scraper_config.yaml)

Example config:

```yaml
output_dir: "instashop_output"
combined_filename: "Instashop_Combined.xlsx"

max_scroll_cycles: 350
rounds_stable: 5

scroll_delay_min: 8
scroll_delay_max: 22

workers: 8

category_file: "categories.txt"
locations_file: "locations.txt"

log_dir: "instashop_logs"

user_agents:
  - "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
  - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
  - "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
  - "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
```

---

## 📑 4. Input Files

### **categories.txt**

Each category URL on a new line:

```
https://instashop.com/en-eg/client/sarai-market-al-ekbal/category/gp5IFnJ4YP
```

### **locations.txt**

Each location on a new line:

```
Maadi, Egypt
New Cairo City, Egypt
Alexandria, Egypt
North Coast, Egypt
```

---

## ▶️ 5. Running the Scraper

Run:

```bash
python run_scraper.py
```

The script:

1. Loads all category URLs
2. Loads all locations
3. Generates combinations (category × location)
4. Launches **8 Playwright browsers in parallel**
5. Scrapes each combination
6. Saves `.parquet` files to `instashop_output/`
7. Merges everything into:

```
Instashop_Combined.xlsx
```

8. Adds summary sheet with:

   * Total products
   * Unique product names
   * Discounted items
   * Out-of-stock items

---

## 📂 6. Output Files

### Per-category-location parquet:

```
VendorName__Location__YYYYMMDD_HHMMSS.parquet
```

### Final combined Excel:

```
Instashop_Combined.xlsx
```

Contains:

| Sheet                   | Description             |
| ----------------------- | ----------------------- |
| **All_Data**            | Full cleaned dataset    |
| **Summary_by_Location** | Stats for each location |

---

## 📊 7. Extracted Fields

Each product row contains:

* `name`
* `quantity`
* `price`
* `old_price`
* `discount_percent`
* `out_of_stock`
* `image_url`
* `sku`
* `category_url`
* `location_used`
* `timestamp`
* `seen_order`

---

## 🧠 8. How It Works

1. Launches visible browser
2. Opens Instashop home
3. Sets delivery location
4. Opens category
5. Accepts cookies if required
6. Applies **All Items** filter
7. Scrolls until no more products load
8. Extracts product cards via JavaScript
9. Saves raw parquet
10. Repeats for all combinations
11. Produces final cleaned Excel file

---

## 🛠 9. Troubleshooting

### ❗ ImportError: ScraperConfig

Remove cache:

```bash
rm -rf __pycache__
```

### ❗ Browser won't open

Run:

```bash
playwright install
```

### ❗ Empty output

Check that:

* The category URL is public
* Instashop is not blocking your IP
* Locations.txt contains valid cities

---

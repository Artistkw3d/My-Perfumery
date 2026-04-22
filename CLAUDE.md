# CLAUDE.md

## Project Overview
My Perfumery v3 - Flask web application for managing perfume formulations, materials, IFRA compliance, MSDS reports, and a perfumer's notebook with olfactive profiles. Single-file Flask app (`app.py` ~4000 lines) with SQLite database. Rebranded from "Perfume Vault"; legacy seeded company names are auto-corrected on startup. Ships as an offline Windows `.exe` via `launcher.py` + PyInstaller (WebView2 desktop shell).

## Tech Stack
- **Backend:** Python Flask, SQLite3
- **Frontend:** Bootstrap 5 (RTL), Chart.js (polar area charts), Select2, jQuery, Bootstrap Icons
- **Deployment:** Docker (docker-compose), and PyInstaller single-file Windows `.exe` built via GitHub Actions (`.github/workflows/build-windows.yml`) and attached to the rolling `latest` release
- **Templates:** Jinja2 (Arabic RTL interface)

## Key Architecture
- `app.py` contains everything: routes, API endpoints, DB init/migrations, IFRA import, external data fetching
- All templates extend `base.html` (fixed sidebar on desktop, off-canvas on mobile, floating Auto/Desktop/Mobile view-mode toggle persisted in `localStorage`)
- Database auto-creates on first run (`init_db()`); column migrations run via `ALTER TABLE … ADD COLUMN` guarded by pragma checks
- IFRA standards auto-import from `data/ifra_standards.xlsx` on startup (`import_ifra_standards()`)
- External data fetched via urllib (PubChem REST API, TGSC HTML scraping, Scentree API + scraping)

## Database Tables
- `materials` - Raw materials with physical/chemical properties
- `material_msds` - GHS/MSDS data per material
- `material_olfactive` - 14-axis olfactive profile per material
- `formulas` - Formulations with IFRA category selection + `card_settings` JSON + `status` (draft/testing/final)
- `formula_ingredients` - Ingredients with weight, dilution, diluent, `ifra_override` (manual per-row IFRA limit override)
- `formula_drafts` / `formula_draft_ingredients` - Versioned drafts per formula for compare/approve workflow
- `formula_notes` - Notes per formula
- `notebook_entries` - Journal entries (title, category, tags, body, `profile` JSON of the 14 olfactive axes, created_at, updated_at)
- `ifra_standards` - 263 IFRA regulated materials with 18 category limits
- `ifra_cas_lookup` - CAS to IFRA standard mapping
- `families`, `suppliers`, `users`, `company_info`, `production_orders`

## IFRA System
- 18 categories: cat1-cat4, cat5a-cat5d, cat6, cat7a-cat7b, cat8, cat9, cat10a-cat10b, cat11a-cat11b, cat12
- Values: positive float = max %, 0 = prohibited, -1 = no restriction, NULL = not applicable
- Formula ingredients calculation uses category-specific limits from `ifra_standards` table
- Falls back to manual `ifra_limit` field in materials if no IFRA standard found by CAS
- Per-ingredient `formula_ingredients.ifra_override` takes highest priority over both above
- Bulk reset endpoint (`action=reset_ifra` on `POST /api/formula/<fid>/ingredients`) clears all overrides for a formula
- IFRA certificate (`/api/ifra-certificate/<fid>`): per-category computed limit is capped at 100% (anything higher becomes "No Restriction"); Composition table lists only IFRA-regulated materials (CAS hit in `ifra_standards` or manual `ifra_limit > 0`)
- MSDS report (`/api/msds/<fid>`): Section 3 lists only ingredients with GHS data (H/P codes, pictograms, or signal word); percentages remain computed from the full formula

## Formula Page Layout (`formula.html`)
- 3-column grid on wide screens (>1500px): `[right sidebar (minmax 260-300px)] [main table (1fr)] [left side panel (minmax 300-340px)]`
  - Right sidebar: big highlighted "حد IFRA النهائي" (E3) readout, Olfactive Profile polar chart (240×240), Dilution key
  - Main column: ingredients table (with per-row IFRA override input + reset-all button), review card, notes
  - Left side panel: formula form (name/status/category), IFRA results box (J2/N3/E3), IFRA legend
- Collapses to 2 columns under 1500px (right sidebar stacks horizontally above) and single column under 1100px
- Ingredients table has 15 columns total; the 5 derived helper columns (H، N، M، J، K) carry class `.adv-col` and are hidden by default. Toggle button in the card footer (`toggleAdvCols()`) adds/removes `.show-adv` on `.e-table`; state persists in `localStorage` under key `formulaShowAdvCols`. Default-visible columns: #, material, diluent (C), dilution (E), IFRA (F), oil weight (G), net weight (I), final IFRA (L), cost, delete.

## Laptop / compact density
- Global media-query block in `base.html` between 769px and 1400px viewport tightens padding, font sizes, and table-row height (`.table th`, `.table td` → 0.35rem padding, 0.85rem font). No layout changes — purely visual density.
- Excluded when `body.force-mobile` is active so the mobile-view toggle still wins.
- Desktop sidebar (right nav) has a chevron button on its inner edge that collapses it entirely; state persists under `localStorage.sidebarCollapsed`.

## Formula Card (`formula_card.html`)
- Customize panel persists to `formulas.card_settings` JSON: brand name, header/footer text, logo data URL, date, code, and `customFamilies[]`
- Custom fragrance families are added via a dropdown sourced from the `families` table (icon + name imported automatically; only percentage is user-entered)
- Total-weight stat was removed from the footer per user preference; only ingredient count remains

## Notebook (`notebook.html`)
- Journal at `/notebook` for perfumer stories, ideas, observations, daily logs. Three-column RTL layout on wide screens: `[200px categories/tags sidebar] [300px notes list] [1fr editor]`, collapses to single column under 900px.
- Each entry carries a 14-axis olfactive profile (same axes/keys as `material_olfactive`) rendered as a polar-area chart (max 320px square) plus 0–10 sliders. Icons per axis mirror the emoji icons in the `families` table (🍋 حمضي، 🌿 أروماتيك، 🍃 أخضر، 🌊 مائي، 🌸 زهري، 🍑 فاكهي، 🌶️ توابل، 🍶 بلسمي، 🪵 خشبي، 💎 عنبري، 🫧 مسكي، 🧳 جلدي، 🐾 حيواني، ✨ ألدهيدي).
- Five presets embody classic color-theory schemes from the reference wheel — `منعش` analogous, `زهري` split-complementary, `شرقي` complementary, `خشبي` analogous-deep, `حلو` triadic — so the chart itself visibly demonstrates the scheme. Axis colors stay with the warm brand palette (do not swap them to wheel hues; rejected 2026-04-22).
- CRUD via action-based `POST /api/notebook/entries` (create/update/delete/duplicate) + `GET` for the list, matching the materials/formulas API style. Auto-save is debounced at 500 ms on the client.

## Desktop build (Windows `.exe`)
- `launcher.py` picks a free TCP port (tries 8000–8099, else OS-assigned), starts Flask in a daemon thread on `127.0.0.1`, waits for readiness, then opens a pywebview (WebView2) window.
- `app.py` detects `sys.frozen` to: (a) resolve read-only assets from `sys._MEIPASS`, (b) store the DB + backups under `%APPDATA%\MyPerfumery\database\`, (c) disable Flask debug and the reloader. Port/host/debug are controlled by env vars (`MYPERFUMERY_PORT`, `MYPERFUMERY_HOST`, `MYPERFUMERY_DEBUG`).
- `build.bat` is the local one-click build; `.github/workflows/build-windows.yml` produces the same `.exe` on every main push and attaches it to the rolling `latest` release.

## Development Commands
```bash
# Run locally (Flask dev server)
pip install -r requirements.txt
python app.py

# Run locally inside a pywebview window (how the .exe runs)
python launcher.py

# Build the Windows single-file .exe locally
build.bat                       # → dist\MyPerfumery.exe

# Docker
docker-compose up -d --build

# Docker rebuild (after code changes)
docker-compose down && docker-compose build --no-cache && docker-compose up -d
```

## Important Notes
- Always push after every commit (user's standing instruction)
- UI is in Arabic (RTL) - keep text direction consistent; user prefers English replies in chat because of mixed RTL/LTR rendering
- Dilution field: 1 = pure/100%, 0.1 = 10%, 0.5 = 50% (NOT percentage, it's a fraction)
- Chart.js polar area charts use custom `polarLabelsPlugin` for family name labels
- XLSX parsing uses zipfile + xml.etree (no openpyxl dependency)
- Column conversion for XLSX: multi-letter columns (AA=26, AB=27, etc.) need special handling
- On Windows/Git: CRLF line-ending warnings on `*.html` are expected and safe

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
- **IFRA limit lookup priority** (highest → lowest):
  1. `formula_ingredients.ifra_override` — per-row override, always wins
  2. `materials.manual_ifra_cats[cat_key]` — per-category manual value, edited via the "IFRA يدوي" tab in the materials modal. Stored as a JSON dict on the materials row (e.g. `{"cat4": 2.5, "cat8": 0.1}`).
  3. `materials.ifra_limit` (> 0) — legacy blanket value. The UI input was removed on 2026-04-23; a hidden form field preserves existing values on round-trip but new materials won't get this set.
  4. IFRA standards table by CAS + category
  5. IFRA contributions (constituents of naturals / Schiff bases)
- Use case for the manual layers: IFRA publishes an amendment before the local `ifra_standards.xlsx` is refreshed, or a material isn't in IFRA standards at all.
- Form plumbing: the materials modal has a dedicated **IFRA يدوي** tab next to the read-only **IFRA** tab with a table of 18 per-category inputs (`manual_ifra_cat1` … `manual_ifra_cat12`). Submit collects them into a JSON blob in `materials.manual_ifra_cats`.

## Material file attachments
- Every material has a **الملفات** tab in the modal (right after IFRA يدوي). Users attach PDFs, images, Word/Excel docs, etc. up to 50 MB total per request.
- Files are stored as BLOBs in a new table `material_files (id, material_id, filename, mime_type, size, content BLOB, uploaded_at)` with `ON DELETE CASCADE` style cleanup also firing in the material delete handlers (and delete_all_unused) since we don't enable SQLite foreign-key enforcement.
- API: `GET/POST /api/materials/<mid>/files` (list + upload/delete via `action=upload|delete`), `GET /api/materials/<mid>/files/<fid>[?inline=1]` serves the BLOB with a proper `Content-Disposition` (UTF-8 filename support for Arabic filenames).
- The Files tab is disabled (shows a "احفظ المادة أولاً" hint) until the material has an id — new-material flow must save first to get one. Image files get a 44×44 thumbnail, non-images show a typed Bootstrap-icon glyph.

## Import (materials.xlsx)
- Auto-guess field mapping was expanded on 2026-04-23 to cover all 31 system fields — previously many columns (Synonyms, Lot, Strength Odor, Vapor Pressure, Effect, خصائص, In Stock, سعر القرام/الجرام) fell through to "تجاهل" because their headers weren't recognised.
- New system field `price_per_gram` (سعر الجرام (القرام)) is importable directly. If the user maps a "price per gram" column, it's used verbatim; otherwise `ppg = purchase_price / purchase_quantity` as before.
- Bulk reset endpoint (`action=reset_ifra` on `POST /api/formula/<fid>/ingredients`) clears all overrides for a formula
- IFRA certificate (`/api/ifra-certificate/<fid>`): per-category computed limit is capped at 100% (anything higher becomes "No Restriction"); Composition table lists only IFRA-regulated materials (CAS hit in `ifra_standards` or manual `ifra_limit > 0`)
- MSDS report (`/api/msds/<fid>`): Section 3 lists only ingredients with GHS data (H/P codes, pictograms, or signal word); percentages remain computed from the full formula

## Formula print / PDF export (`formula_print.html`, `GET /formula/<id>/print`)
- Standalone A4-portrait print page opened in a new tab from the "طباعة PDF" button in the formula header (next to MSDS). The button is always available regardless of formula status — unlike IFRA/MSDS reports which are gated to Final.
- `@page { size: A4; margin: 12mm }` + Tajawal font + no shadows/backgrounds on screen's print media. On-screen a yellow action bar shows "طباعة / حفظ PDF" (calls `window.print()`) and a "رجوع" link. Bar is hidden via `@media print`.
- Page auto-invokes `window.print()` 700ms after ingredients finish loading (browser Save-as-PDF handles the conversion, no server-side PDF library).
- Sections (empty ones are skipped): Header (name + status pill + IFRA category name + company brand + date) → 5-stat strip (ingredients / total weight / pure weight / active ratio J2 / total cost) → Ingredients table (9-col compact: #, material+CAS, C, E, F, G, I, L, cost) → IFRA-final (E3) big readout + Olfactive polar chart side-by-side (collapses to single panel if only one has data) → Review card (server-rendered with Arabic labels for gender/season/age) → Notes list. Over-limit L cells are styled red.
- Client-side fetches `/api/formula/<id>/ingredients` (reuses the live IFRA calc + aggregate olfactive profile). `formula`, `notes`, `company`, and IFRA category label are passed server-side from the route.

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
- Journal at `/notebook` for perfumer stories, ideas, observations, daily logs. Two-column RTL layout on wide screens: `[320px merged sidebar: search + category chips + notes list + collapsible tags] [1fr editor]`, collapses to single column under 900px. (Was 3 columns until 2026-04-23 — category list and notes list were merged to reclaim ~200px of editor width on 1366px laptop screens, where the olfactive-profile polar chart used to visually crowd the axis sliders.)
- Olfactive-profile chart is capped at 280×280 (down from 320) and the profile grid drops to a single column under 1400px (was 1280) so the chart stacks below the sliders earlier on laptops.
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

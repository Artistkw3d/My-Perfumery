# CLAUDE.md

## Project Overview
My Perfumery v3 - Flask web application for managing perfume formulations, materials, IFRA compliance, and MSDS reports. Single-file Flask app (`app.py` ~3900 lines) with SQLite database. Rebranded from "Perfume Vault"; legacy seeded company names are auto-corrected on startup.

## Tech Stack
- **Backend:** Python Flask, SQLite3
- **Frontend:** Bootstrap 5 (RTL), Chart.js (polar area charts), Select2, jQuery, Bootstrap Icons
- **Deployment:** Docker (docker-compose)
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
- 3-column grid on wide screens (>1280px): `[right sidebar 280px] [main table] [left side panel 320px]`
  - Right sidebar: big highlighted "حد IFRA النهائي" (E3) readout, Olfactive Profile polar chart (240×240), Dilution key
  - Main column: ingredients table (with per-row IFRA override input + reset-all button), review card, notes
  - Left side panel: formula form (name/status/category), IFRA results box (J2/N3/E3), IFRA legend
- Collapses to 2 columns under 1280px (right sidebar stacks horizontally) and single column under 1024px

## Formula Card (`formula_card.html`)
- Customize panel persists to `formulas.card_settings` JSON: brand name, header/footer text, logo data URL, date, code, and `customFamilies[]`
- Custom fragrance families are added via a dropdown sourced from the `families` table (icon + name imported automatically; only percentage is user-entered)
- Total-weight stat was removed from the footer per user preference; only ingredient count remains

## Development Commands
```bash
# Run locally
pip install flask
python app.py

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

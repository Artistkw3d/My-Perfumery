# CLAUDE.md

## Project Overview
Perfume Vault v3 - Flask web application for managing perfume formulations, materials, IFRA compliance, and MSDS reports. Single-file Flask app (`app.py` ~3000 lines) with SQLite database.

## Tech Stack
- **Backend:** Python Flask, SQLite3
- **Frontend:** Bootstrap 5, Chart.js (polar area charts), Select2, jQuery
- **Deployment:** Docker (docker-compose)
- **Templates:** Jinja2 (Arabic RTL interface)

## Key Architecture
- `app.py` contains everything: routes, API endpoints, DB init, IFRA import, external data fetching
- All templates extend `base.html`
- Database auto-creates on first run (`init_db()`)
- IFRA standards auto-import from `data/ifra_standards.xlsx` on startup (`import_ifra_standards()`)
- External data fetched via urllib (PubChem REST API, TGSC HTML scraping, Scentree API + scraping)

## Database Tables
- `materials` - Raw materials with physical/chemical properties
- `material_msds` - GHS/MSDS data per material
- `material_olfactive` - 14-axis olfactive profile per material
- `formulas` - Formulations with IFRA category selection
- `formula_ingredients` - Ingredients with weight, dilution, diluent
- `formula_notes` - Notes per formula
- `ifra_standards` - 263 IFRA regulated materials with 18 category limits
- `ifra_cas_lookup` - CAS to IFRA standard mapping
- `families`, `suppliers`, `users`, `company_info`, `production_orders`

## IFRA System
- 18 categories: cat1-cat4, cat5a-cat5d, cat6, cat7a-cat7b, cat8, cat9, cat10a-cat10b, cat11a-cat11b, cat12
- Values: positive float = max %, 0 = prohibited, -1 = no restriction, NULL = not applicable
- Formula ingredients calculation uses category-specific limits from `ifra_standards` table
- Falls back to manual `ifra_limit` field in materials if no IFRA standard found by CAS

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
- UI is in Arabic (RTL) - keep text direction consistent
- Dilution field: 1 = pure/100%, 0.1 = 10%, 0.5 = 50% (NOT percentage, it's a fraction)
- Chart.js polar area charts use custom `polarLabelsPlugin` for family name labels
- XLSX parsing uses zipfile + xml.etree (no openpyxl dependency)
- Column conversion for XLSX: multi-letter columns (AA=26, AB=27, etc.) need special handling

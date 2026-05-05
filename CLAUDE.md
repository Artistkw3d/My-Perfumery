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

## Material composition (mixtures / blends)
- Some materials are themselves blends (a pre-made base, an in-house accord, a commercial captive). They get a **التركيب** tab in the material modal between "IFRA يدوي" and "الملفات" where you list sub-components by picking other materials and assigning each a weight-percent inside the parent. Sum can be < 100% — the remainder is treated as unspecified carrier and not weighted into rollups.
- Stored in a new table `material_composition (id, parent_material_id, component_material_id, pct, note)` with cascade delete on parent removal (also fired in the material delete handler and `delete_all_unused`).
- API: `GET /api/materials/<mid>/composition` returns the rows joined with the component's name/CAS/ifra/ppg; `POST /api/materials/<mid>/composition` with `action=save` accepts `components=<JSON array of {component_id, pct, note}>` and **fully replaces** the list. Self-references are silently dropped; cycles (A → B → A direct or transitive) are rejected with a 400 + Arabic message.
- **Effects in the formula calc** (`api_formula_ingredients`):
  - **Per-row IFRA limit (folds into E3/N3).** When an ingredient is a mixture without its own IFRA source (no manual override, no CAS hit, no annex contribution match), `_resolve_material_ifra_for_cat()` derives a per-category limit from composition: `limit = MIN over components of (component_limit / (component_pct_in_mixture / 100))`. This becomes the row's `ifra_cat_limit` with `ifra_std_type='composition'` and `ifra_std_name="Mix: <binding_component>"`, so the row's L value naturally enters `l_values`/`n_values` and the formula's headline E3/N3 shrinks. Without this, a mixture row would have no per-row limit and the formula could silently violate IFRA.
  - **Unrestricted when derived > 100%.** A derived limit greater than 100% is mathematically meaningless (you can never use more than 100% of a mixture in a formula), so `_derive_mixture_ifra_limits()` and `_resolve_material_ifra_for_cat()` collapse it to IFRA's "-1" (No Restriction) sentinel. UI renders "غير مقيّد" in green; placeholder becomes `→ غير مقيّد`.
  - **Cumulative CAS constraint folded into E3/N3.** Critical for multi-mixture cases — if Iso E Super (or any regulated CAS) appears in three mixtures at different concentrations, each mixture's per-row L might look fine individually, but the cumulative total could still violate the IFRA limit. After `contribution_map` is built and limit-checked, each regulated constituent with `total_pct > 0` contributes a `cumulative_L = ifra_limit / (total_pct / 100)` to `l_values` and `n_values`. Prohibited CAS with any presence appends `0` (forces E3 to 0). Order: per-row loop → contribution_map build → limit check + cumulative-L fold-in → **then** `ifra_final_limit = min(l_values) × 0.99` is computed. This closes the case where the warnings card showed a red cumulative violation while the headline E3 was still green.
  - **IFRA contributions map** — `_expand_mixture_components()` walks the composition tree (capped at 5 levels, cycle-protected) and adds each component's effective formula-% into the same `contribution_map` used by the natural-source contributions, tagged `source_type='mixture'`. Downstream limit checks then enforce IFRA against the merged total (direct usage + naturals + mixture components).
  - **Cost roll-up** — `_effective_ppg()` returns the material's own `price_per_gram` if > 0, otherwise the weighted average of component ppg from composition (recursive). The ingredient `cost` line uses this effective ppg instead of the raw column. Result row carries `effective_ppg` for diagnostic display.
- **Materials modal feedback** — `GET /api/materials?action=get` includes `derived_ifra_limits` (per-cat `{limit, binding_name, binding_cas, prohibited}`) when the material has composition. The IFRA tab renders an extra "محسوب من التركيب" table showing each cat's derived limit + the binding component, and the IFRA يدوي tab uses the same data as ghost placeholders inside each empty input (`→ 4.7 (مشتق)` or `⛔ محظور`) so users see what they'd be overriding.
- UI surface: a small green "خليط" badge appears next to the material name in both the card view and the table view of the materials page when `composition_count > 0`. List endpoint adds `composition_count` per row.

## Quick-dilute (crystalline / strong-impact materials → pre-diluted form)
- Crystalline raw materials (vanillin, aldehyde C-12, etc.) are usually pre-diluted before bench use. Conceptually a "Vanillin 10% in DPG" is just a 2-component mixture: parent CAS @ 10% + solvent @ 90%. The composition system already handles all the IFRA / cumulative-CAS / cost logic; this feature is the fast on-ramp.
- **Button**: "تخفيف سريع" on the materials page header (next to "إضافة مادة"). Opens a small modal: pick parent material, concentration %, solvent (auto-suggests DPG/IPM/ethanol if present), optional name override. Defaults to 10% concentration.
- **Endpoint**: `POST /api/materials/quick-dilute` with `parent_id`, `concentration` (0 < x < 100), optional `solvent_id`, `name`, `name_ar`, `note`. Creates a new material row inheriting the parent's family / profile / supplier / odor description / olfactive profile, then writes 2 composition rows (`parent @ concentration%`, `solvent @ remainder`). If no solvent picked, only the parent row is written and the remainder is "unspecified carrier" exactly as the composition system already supports.
- **Why this is the right model (not a per-row dilution)**: the diluted form is a stable inventory item that the perfumer weighs out as-is. The formula-row `dilution` field stays at `1` (the material *is* the diluted form). All IFRA derivation flows through composition: derived per-cat limit, "Mix: Vanillin" subtitle on the L cell, cumulative-CAS protection across multiple mixture rows, weighted cost roll-up. Ghost placeholders in the manual-IFRA tab show the derived value before override.
- Auto-generated name format: `{ParentName} {pct}% in {SolventName}` (English) and Arabic equivalent.

## Scale modal print
- The Scale modal (`showScaleModal()` on formula.html) renders a multi-column table of ingredient amounts at user-chosen quantities (1000g/100g/50g/20g/5g by default), in either J% (production) or H% (design) mode.
- A **"طباعة النتائج"** button next to the type/equation line at the top of the results prints the rendered table.
- **Implementation: hidden iframe, not `window.open`.** pywebview/WebView2 (the desktop `.exe` shell) blocks `window.open` as a popup. The print path writes a self-contained HTML doc into an off-screen iframe (`#scalePrintFrame`), then calls `iframe.contentWindow.print()`. Works identically in browsers and in the desktop build, no popup-blocker prompts. The print doc is RTL Arabic, A4, with formula name + calc type (J/H) + today's date as a header above the table. The original `/formula/<id>/print` A4 page is unchanged and unrelated.

## Materials advanced filter
- Materials page has a collapsible "فلتر متقدم" panel (toggle button next to the search box; badge shows active-filter count). Filters: family multi-select, profile (Top/Heart/Base) multi-select, supplier, stock (in/out), price-per-gram min/max, IFRA presence (has/none), mixture vs atomic, CAS presence. Active-filter chips render above with × to remove individual filters and a "مسح الكل" button.
- All filter logic is pure client-side over the loaded `materials` array — no server changes. Each rendered card / table row carries `data-mat-id` so `filterMaterials()` can show/hide without re-rendering. View-toggle (card ↔ table) re-applies filters automatically.

## Material file attachments
- Every material has a **الملفات** tab in the modal (right after IFRA يدوي). Users attach PDFs, images, Word/Excel docs, etc. up to 50 MB per request.
- **Storage layout (changed 2026-05-05):** files live on disk under `USER_DIR/attachments/<file_id>.bin`. The DB row in `material_files (id, material_id, filename, mime_type, size, content BLOB, uploaded_at)` now carries metadata only — `content` is `NULL` for new uploads. The BLOB column is kept for two reasons: it's the legacy fallback when restoring a pre-2026-05-05 `.db` backup, and the migration uses it to find rows that still need moving to disk.
- **Migration** runs in `bootstrap()` via `_migrate_attachments_to_disk()`: any row with `content IS NOT NULL` gets its bytes written to disk first, then the BLOB is nulled, then `VACUUM` reclaims pages. Crash-safe (disk before BLOB clear), idempotent, and auto-creates a `pre_attachment_migration` backup the first time it finds work.
- **Upload path** inserts the metadata row first to mint an id, then writes bytes to `_attachment_path(fid)`; if the disk write fails the row is rolled back so we never leak orphan rows pointing at nonexistent files.
- **Read path** (`api_material_file_serve`): tries disk first via `_read_attachment_bytes(fid, blob_fallback)`, falls back to the BLOB only if the disk file is missing. Inline rendering is restricted to `_SAFE_INLINE_MIMES` (image/* except svg, pdf, text/plain); everything else is forced `Content-Disposition: attachment` with `X-Content-Type-Options: nosniff` so user-uploaded HTML/SVG can't XSS as same-origin content.
- **Orphan-keep policy on delete (intentional):** row deletes (single file, material delete, `delete_all_unused`) do **not** unlink the disk file. This preserves restore-from-backup correctness — backups are `.db`-only and don't include attachments, so an older backup that references file ids deleted in the meantime still resolves. Disk usage grows monotonically; an explicit "Clean orphan attachments" action can be added later if it ever matters.
- API: `GET/POST /api/materials/<mid>/files` (list + upload/delete via `action=upload|delete`), `GET /api/materials/<mid>/files/<fid>[?inline=1]` serves the bytes with UTF-8 filename support for Arabic filenames.
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

## Mixture visibility in formula ingredients table
- When a row's `ifra_std_type === 'composition'` (meaning the per-row IFRA limit came from composition derivation), the L cell renders a small gray subtitle under the L number with the binding-component name ("Mix: Geraniol" etc.). Users can see WHY the L is what it is without opening the warnings card.

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

## Auth + session secret
- **Password storage (added 2026-05-05):** `users.password` is hashed with `werkzeug.security.generate_password_hash` (default scrypt). Migration `_migrate_plaintext_passwords()` runs in `bootstrap()` and detects plaintext rows by negation against the hash-prefix oracle (`scrypt:` / `pbkdf2:` / `argon2`). First run that finds plaintext auto-creates a `pre_hash_migration` backup, then rewrites every plaintext row in place. Idempotent. Login still works with the same plaintext password the user remembers — `check_password_hash` validates it against the new hash.
- **Login fallback:** if a stored value somehow still looks plaintext at login time (e.g. migration was skipped), the route does a `hmac.compare_digest` and, on success, hashes the password before completing login. So plaintext can never persist past one successful login.
- **Restore safety:** `restore_backup()` already preserves the live admin row across a restore, so even restoring an old plaintext-era backup keeps your hashed credentials at `id=1`. The migration on next startup will hash any *other* user rows pulled in from the restored backup.
- **Per-install random `secret_key` (added 2026-05-05):** `_load_or_create_secret_key()` reads/creates `USER_DIR/secret.key` (64 random bytes). Replaces the previous hardcoded `'perfume_vault_2024_v3'` literal — sessions are now uniquely scoped per install. The file is in `.gitignore`. If the file can't be written, falls back to an in-memory key (sessions still work for the running process).

## Backups
- Live `.db` is at `USER_DIR/database/perfume.db`; backups under `USER_DIR/database/backups/` named `backup_<YYYYMMDD>_<HHMMSS>_<reason>.db`. `MAX_BACKUPS=20` rolling window. Reasons in use: `auto`, `manual`, `login` (auto-on-login), `pre_restore`, `pre_hash_migration`, `pre_attachment_migration`, `uploaded`.
- **Filename validator** (`_is_safe_backup_filename`, added 2026-05-05): strict regex `^backup_\d{8}_\d{6}_[a-z_]+\.db$` plus rejects `..`, `/`, `\`. Reused by every backup endpoint that takes a filename param (download, restore, delete) so all of them have one source of truth for what's a legal name.
- **Download** (added 2026-05-05): `GET /api/settings/backup/<filename>` streams the `.db` as `attachment` with `nosniff`. UI: gold "تحميل" button per row in `templates/settings.html`. Works inside the pywebview/WebView2 desktop shell because it's a same-origin navigation, not `window.open` (which the shell blocks).
- **Upload** (added 2026-05-05): `POST /api/settings` with `action=upload_backup` accepts an external `.db` (≤ 50 MB), validates the SQLite magic header (`SQLite format 3\x00`) and runs `PRAGMA integrity_check` on it before saving as `backup_<ts>_uploaded.db`. The upload writes to a hidden `.upload_<uuid>.db` temp name on the same volume first; only renames after validation passes. **Restore stays a separate click** so the existing `pre_restore` safety snapshot still runs.
- The 20-slot rotation can erase manual/pre-restore backups if logins flood the buffer (auto-on-login uses one slot per login). Known limitation, deferred.

## Desktop build (Windows `.exe`)
- `launcher.py` picks a free TCP port (tries 8000–8099, else OS-assigned), starts Flask in a daemon thread on `127.0.0.1`, waits for readiness, then opens a pywebview (WebView2) window.
- `app.py` detects `sys.frozen` to: (a) resolve read-only assets from `sys._MEIPASS`, (b) store the DB + backups under `%APPDATA%\MyPerfumery\database\`, attachments under `%APPDATA%\MyPerfumery\attachments\`, and the random session key as `%APPDATA%\MyPerfumery\secret.key`, (c) disable Flask debug and the reloader. Port/host/debug are controlled by env vars (`MYPERFUMERY_PORT`, `MYPERFUMERY_HOST`, `MYPERFUMERY_DEBUG`).
- **Default bind is `127.0.0.1`** (changed 2026-05-05). Inside Docker (detected via existing `/app` heuristic, same as `_user_data_dir()`) the default flips to `0.0.0.0` so docker-compose port-forward keeps working. `MYPERFUMERY_HOST` env var overrides either way. The frozen `.exe` is unaffected because `launcher.py` already pins `HOST=127.0.0.1`.
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

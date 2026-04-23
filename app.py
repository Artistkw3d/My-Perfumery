#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""My Perfumery v3 - نظام إدارة التركيبات العطرية مع MSDS و IFRA"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, make_response
import sqlite3
import os
import sys
import re
import json
import glob
import shutil
import zipfile
import xml.etree.ElementTree as ET
import tempfile
import uuid
from datetime import datetime
from functools import wraps

# --- Path resolution: dev script, Docker, and PyInstaller-frozen desktop build ---
IS_FROZEN = getattr(sys, 'frozen', False)

def _asset_dir():
    """Directory that contains read-only bundled assets (templates/, static/, data/)."""
    if IS_FROZEN:
        return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))

def _user_data_dir():
    """Writable per-user directory for the DB + backups."""
    if os.path.exists('/app'):
        return '/app'
    if IS_FROZEN:
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
        return os.path.join(base, 'MyPerfumery')
    return os.path.dirname(os.path.abspath(__file__))

ASSET_DIR = _asset_dir()
USER_DIR = _user_data_dir()

app = Flask(
    __name__,
    template_folder=os.path.join(ASSET_DIR, 'templates'),
    static_folder=os.path.join(ASSET_DIR, 'static'),
)
app.secret_key = 'perfume_vault_2024_v3'

DB_PATH = os.path.join(USER_DIR, 'database', 'perfume.db')
BACKUP_DIR = os.path.join(USER_DIR, 'database', 'backups')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

MAX_BACKUPS = 20  # Keep last 20 backups

def create_backup(reason='auto'):
    """Create a backup of the database"""
    if not os.path.exists(DB_PATH):
        return None
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"backup_{timestamp}_{reason}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    shutil.copy2(DB_PATH, backup_path)
    # Cleanup old backups
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, 'backup_*.db')))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))
    log(f"[BACKUP] Created: {backup_name}")
    return backup_name

def list_backups():
    """List all available backups"""
    backups = []
    for f in sorted(glob.glob(os.path.join(BACKUP_DIR, 'backup_*.db')), reverse=True):
        name = os.path.basename(f)
        size = os.path.getsize(f)
        # Parse timestamp from filename: backup_20260412_215443_auto.db
        parts = name.replace('backup_', '').replace('.db', '').split('_')
        if len(parts) >= 3:
            date_str = parts[0]
            time_str = parts[1]
            reason = '_'.join(parts[2:])
            try:
                dt = datetime.strptime(f"{date_str}_{time_str}", '%Y%m%d_%H%M%S')
                formatted = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                formatted = name
        else:
            formatted = name
            reason = 'unknown'
        backups.append({
            'filename': name,
            'date': formatted,
            'reason': reason,
            'size_kb': round(size / 1024, 1)
        })
    return backups

def restore_backup(filename):
    """Restore database from backup, keeping admin credentials"""
    backup_path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(backup_path):
        return False, 'Backup not found'
    # Save current admin credentials
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    admin = conn.execute("SELECT username, password, name, role FROM users WHERE id=1").fetchone()
    admin_data = dict(admin) if admin else None
    conn.close()
    # Create a safety backup before restore
    create_backup('pre_restore')
    # Restore
    shutil.copy2(backup_path, DB_PATH)
    # Re-apply admin credentials
    if admin_data:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE users SET username=?, password=?, name=?, role=? WHERE id=1",
            (admin_data['username'], admin_data['password'], admin_data['name'], admin_data['role']))
        conn.commit()
        conn.close()
    log(f"[BACKUP] Restored from: {filename}")
    return True, 'Restored successfully'

def log(msg):
    print(msg, file=sys.stdout, flush=True)

# ===== IFRA Categories من القالب =====
IFRA_CATEGORIES = [
    {'id': 'cat1', 'name': 'Category 1', 'desc': 'Products applied to the lips', 'limit': 0.019},
    {'id': 'cat2', 'name': 'Category 2', 'desc': 'Products applied to the axillae (armpit)', 'limit': 0.017},
    {'id': 'cat3', 'name': 'Category 3', 'desc': 'Products applied to the face/body using fingertips', 'limit': 0.017},
    {'id': 'cat4', 'name': 'Category 4', 'desc': 'Products related to fine fragrance', 'limit': 0.306},
    {'id': 'cat5a', 'name': 'Category 5A', 'desc': 'Body lotion products applied to the body using the hands (palms), primarily leave-on', 'limit': 0.083},
    {'id': 'cat5b', 'name': 'Category 5B', 'desc': 'Face moisturizer products applied to the face using the hands (palms), primarily leave-on', 'limit': 0.024},
    {'id': 'cat5c', 'name': 'Category 5C', 'desc': 'Hand cream products applied to the hands using the hands (palms), primarily leave-on', 'limit': 0.035},
    {'id': 'cat5d', 'name': 'Category 5D', 'desc': 'Baby Creams, baby Oils and baby talc', 'limit': 0.008},
    {'id': 'cat6', 'name': 'Category 6', 'desc': 'Products with oral and lip exposure', 'limit': 0.001},
    {'id': 'cat7a', 'name': 'Category 7A', 'desc': 'Rinse-off products applied to the hair with some hand contact', 'limit': 0.039},
    {'id': 'cat7b', 'name': 'Category 7B', 'desc': 'Leave-on products applied to the hair with some hand contact', 'limit': 0.039},
    {'id': 'cat8', 'name': 'Category 8', 'desc': 'Products with significant anogenital exposure', 'limit': 0.008},
    {'id': 'cat9', 'name': 'Category 9', 'desc': 'Products with body and hand exposure, primarily rinse off', 'limit': 0.114},
    {'id': 'cat10a', 'name': 'Category 10A', 'desc': 'Household care excluding aerosol products', 'limit': 0.114},
    {'id': 'cat10b', 'name': 'Category 10B', 'desc': 'Household aerosol/spray products', 'limit': 0.35},
    {'id': 'cat11a', 'name': 'Category 11A', 'desc': 'Products with intended skin contact but minimal transfer of fragrance to skin from inert substrate without UV exposure', 'limit': 0.008},
    {'id': 'cat11b', 'name': 'Category 11B', 'desc': 'Products with intended skin contact but minimal transfer of fragrance to skin from inert substrate with potential UV exposure', 'limit': 0.008},
    {'id': 'cat12', 'name': 'Category 12', 'desc': 'Products not intended for direct skin contact, minimal or insignificant transfer to skin', 'limit': None},
]

# ===== Olfactive Wheel Categories (14 axes) =====
OLFACTIVE_CATEGORIES = [
    'citrus', 'aldehydic', 'aromatic', 'green', 'marine', 'floral', 'fruity',
    'spicy', 'balsamic', 'woody', 'ambery', 'musky', 'leathery', 'animal'
]

OLFACTIVE_LABELS = {
    'citrus': 'Citrus', 'aldehydic': 'Aldehydic', 'aromatic': 'Aromatic',
    'green': 'Green', 'marine': 'Marine', 'floral': 'Floral', 'fruity': 'Fruity',
    'spicy': 'Spicy', 'balsamic': 'Balsamic', 'woody': 'Woody',
    'ambery': 'Ambery', 'musky': 'Musky', 'leathery': 'Leathery', 'animal': 'Animal'
}

# Keyword mapping for auto-classification (EN + AR)
ODOR_KEYWORD_MAP = {
    # CITRUS
    'citrus': ('citrus', 10), 'lemon': ('citrus', 9), 'lime': ('citrus', 9),
    'orange': ('citrus', 8), 'bergamot': ('citrus', 9), 'grapefruit': ('citrus', 9),
    'mandarin': ('citrus', 8), 'neroli': ('citrus', 7), 'petitgrain': ('citrus', 7),
    'yuzu': ('citrus', 9), 'citric': ('citrus', 8), 'zesty': ('citrus', 7),
    'حمضي': ('citrus', 10), 'حمضيات': ('citrus', 10), 'الحمضيات': ('citrus', 10),
    'ليمون': ('citrus', 9), 'برتقال': ('citrus', 8), 'الحمضية': ('citrus', 9),
    # ALDEHYDIC
    'aldehydic': ('aldehydic', 10), 'aldehyde': ('aldehydic', 10), 'waxy': ('aldehydic', 7),
    'soapy': ('aldehydic', 6), 'clean': ('aldehydic', 5), 'laundered': ('aldehydic', 6),
    'metallic': ('aldehydic', 6), 'شمعي': ('aldehydic', 7),
    # AROMATIC
    'aromatic': ('aromatic', 10), 'camphor': ('aromatic', 9), 'eucalyptus': ('aromatic', 9),
    'herbal': ('aromatic', 8), 'medicinal': ('aromatic', 7), 'terpenic': ('aromatic', 7),
    'terpene': ('aromatic', 7), 'rosemary': ('aromatic', 8), 'thyme': ('aromatic', 8),
    'lavender': ('aromatic', 8), 'sage': ('aromatic', 7), 'basil': ('aromatic', 7),
    'mint': ('aromatic', 7), 'minty': ('aromatic', 7), 'absinthe': ('aromatic', 7),
    'عشبي': ('aromatic', 8), 'كامفوري': ('aromatic', 9), 'أعشاب': ('aromatic', 8),
    'العشبية': ('aromatic', 8), 'نعناع': ('aromatic', 7), 'التربينية': ('aromatic', 7),
    'الكافورية': ('aromatic', 9),
    # GREEN
    'green': ('green', 10), 'galbanum': ('green', 10), 'grassy': ('green', 9),
    'leafy': ('green', 9), 'stem': ('green', 7), 'cortex': ('green', 6),
    'أخضر': ('green', 10), 'خضراء': ('green', 9), 'الخضراء': ('green', 9),
    # MARINE
    'marine': ('marine', 10), 'aquatic': ('marine', 10), 'watery': ('marine', 9),
    'ozonic': ('marine', 9), 'oceanic': ('marine', 9), 'مائي': ('marine', 10),
    'مائية': ('marine', 9), 'بحري': ('marine', 10),
    # FLORAL
    'floral': ('floral', 10), 'rose': ('floral', 9), 'rosy': ('floral', 9),
    'jasmine': ('floral', 9), 'jasmin': ('floral', 9), 'lily': ('floral', 8),
    'violet': ('floral', 8), 'peony': ('floral', 8), 'gardenia': ('floral', 8),
    'magnolia': ('floral', 8), 'hyacinth': ('floral', 8), 'tuberose': ('floral', 9),
    'narcissus': ('floral', 7), 'geranium': ('floral', 7), 'iris': ('floral', 8),
    'orris': ('floral', 8), 'mimosa': ('floral', 7), 'hawthorn': ('floral', 6),
    'زهري': ('floral', 10), 'وردي': ('floral', 9), 'أزهار': ('floral', 10),
    'الأزهار': ('floral', 10), 'زهر': ('floral', 9), 'الزهور': ('floral', 9),
    # FRUITY
    'fruity': ('fruity', 10), 'berry': ('fruity', 9), 'berries': ('fruity', 9),
    'apple': ('fruity', 8), 'tropical': ('fruity', 8), 'pear': ('fruity', 8),
    'peach': ('fruity', 9), 'strawberry': ('fruity', 9), 'raspberry': ('fruity', 9),
    'plum': ('fruity', 8), 'cherry': ('fruity', 8), 'coconut': ('fruity', 6),
    'pineapple': ('fruity', 9), 'melon': ('fruity', 8), 'lactonic': ('fruity', 6),
    'فاكهي': ('fruity', 10), 'فواكه': ('fruity', 9), 'توت': ('fruity', 9),
    'الفواكه': ('fruity', 9), 'الاستوائية': ('fruity', 8), 'فاكهة': ('fruity', 9),
    # SPICY
    'spicy': ('spicy', 10), 'pepper': ('spicy', 9), 'peppery': ('spicy', 9),
    'cinnamon': ('spicy', 9), 'clove': ('spicy', 9), 'nutmeg': ('spicy', 8),
    'ginger': ('spicy', 8), 'cardamom': ('spicy', 8), 'cumin': ('spicy', 7),
    'anise': ('spicy', 7), 'saffron': ('spicy', 8), 'mace': ('spicy', 7),
    'cubeb': ('spicy', 7), 'juniper': ('spicy', 6),
    'توابل': ('spicy', 10), 'التوابل': ('spicy', 10), 'حار': ('spicy', 8),
    # BALSAMIC
    'balsamic': ('balsamic', 10), 'resin': ('balsamic', 9), 'resinous': ('balsamic', 9),
    'vanilla': ('balsamic', 8), 'vanillic': ('balsamic', 8), 'tonka': ('balsamic', 8),
    'benzoin': ('balsamic', 9), 'incense': ('balsamic', 8), 'myrrh': ('balsamic', 8),
    'frankincense': ('balsamic', 8), 'coumarinic': ('balsamic', 8), 'coumarin': ('balsamic', 8),
    'sweet': ('balsamic', 4), 'powdery': ('balsamic', 5), 'styrene': ('balsamic', 7),
    'olibanum': ('balsamic', 8), 'caramellic': ('balsamic', 6),
    'بلسمي': ('balsamic', 10), 'البلسمي': ('balsamic', 10), 'البلسمية': ('balsamic', 10),
    'بلسم': ('balsamic', 9), 'الفانيليا': ('balsamic', 8), 'الكومارين': ('balsamic', 8),
    'الغورماند': ('balsamic', 7), 'الفانيليك': ('balsamic', 8), 'معسل': ('balsamic', 6),
    # WOODY
    'woody': ('woody', 10), 'cedar': ('woody', 9), 'cedarwood': ('woody', 9),
    'sandalwood': ('woody', 9), 'vetiver': ('woody', 9), 'patchouli': ('woody', 9),
    'oud': ('woody', 10), 'agarwood': ('woody', 10), 'pine': ('woody', 7),
    'guaiacwood': ('woody', 8), 'rosewood': ('woody', 7), 'driftwood': ('woody', 7),
    'birch': ('woody', 7), 'rooty': ('woody', 7), 'earthy': ('woody', 6),
    'moss': ('woody', 6), 'forest': ('woody', 7),
    'خشبي': ('woody', 10), 'أخشاب': ('woody', 9), 'الخشب': ('woody', 10),
    'الخشبية': ('woody', 10), 'خشب': ('woody', 9), 'الأرز': ('woody', 9),
    'الصندل': ('woody', 9), 'ترابي': ('woody', 6), 'طحلب': ('woody', 6),
    # AMBERY
    'amber': ('ambery', 10), 'ambery': ('ambery', 10), 'ambergris': ('ambery', 9),
    'ambrette': ('ambery', 8), 'ambroxan': ('ambery', 9), 'warm': ('ambery', 5),
    'honey': ('ambery', 6), 'honeyed': ('ambery', 6),
    'العنبر': ('ambery', 10), 'عنبر': ('ambery', 10),
    # MUSKY
    'musk': ('musky', 10), 'musky': ('musky', 10), 'المسك': ('musky', 10),
    'مسك': ('musky', 10), 'creamy': ('musky', 5), 'milky': ('musky', 5),
    'حليبي': ('musky', 5), 'النظيف': ('musky', 6),
    # LEATHERY
    'leather': ('leathery', 10), 'leathery': ('leathery', 10), 'suede': ('leathery', 9),
    'smoky': ('leathery', 7), 'tobacco': ('leathery', 8), 'phenolic': ('leathery', 6),
    'burnt': ('leathery', 7), 'tar': ('leathery', 8),
    'جلد': ('leathery', 10), 'جلدي': ('leathery', 10), 'دخاني': ('leathery', 7),
    'دخان': ('leathery', 7), 'الدخانية': ('leathery', 7), 'محترق': ('leathery', 7),
    # ANIMAL
    'animal': ('animal', 10), 'animalic': ('animal', 10), 'civet': ('animal', 10),
    'castoreum': ('animal', 10), 'fecal': ('animal', 9), 'indolic': ('animal', 8),
    'indole': ('animal', 8), 'costus': ('animal', 7),
    'حيوان': ('animal', 10), 'حيواني': ('animal', 10),
}

def auto_classify_odor(description):
    """تحليل وصف الرائحة وتحويله لقيم على عجلة الرائحة"""
    if not description:
        return {cat: 0 for cat in OLFACTIVE_CATEGORIES}

    # تنظيف النص وتقسيمه
    import re
    text = description.lower().strip()
    # فصل بـ > أو , أو مسافة
    tokens = re.split(r'[>,/\s]+', text)
    tokens = [t.strip() for t in tokens if t.strip()]

    scores = {cat: 0 for cat in OLFACTIVE_CATEGORIES}

    for token in tokens:
        if token in ODOR_KEYWORD_MAP:
            cat, intensity = ODOR_KEYWORD_MAP[token]
            scores[cat] = max(scores[cat], intensity)

    return scores

# ===== GHS Pictograms =====
GHS_PICTOGRAMS = [
    {'id': 'explosive', 'name': 'Explosive', 'name_ar': 'متفجر'},
    {'id': 'flammable', 'name': 'Flammable', 'name_ar': 'قابل للاشتعال'},
    {'id': 'oxidizing', 'name': 'Oxidizing', 'name_ar': 'مؤكسد'},
    {'id': 'compressed_gas', 'name': 'Compressed Gas', 'name_ar': 'غاز مضغوط'},
    {'id': 'corrosive', 'name': 'Corrosive', 'name_ar': 'آكل'},
    {'id': 'toxic', 'name': 'Toxic', 'name_ar': 'سام'},
    {'id': 'irritant', 'name': 'Irritant', 'name_ar': 'مهيج'},
    {'id': 'health_hazard', 'name': 'Health Hazard', 'name_ar': 'خطر صحي'},
    {'id': 'environmental', 'name': 'Environmentally Damaging', 'name_ar': 'ضار بالبيئة'},
]

# ===== GHS H-Codes (Hazard Statements) من القالب =====
GHS_H_CODES = [
    # Physical Hazards
    {'code': 'H200', 'desc': 'Unstable explosives', 'cat': 'Explosive'},
    {'code': 'H201', 'desc': 'Explosive; mass explosion hazard', 'cat': 'Explosive'},
    {'code': 'H202', 'desc': 'Explosive, severe projection hazard', 'cat': 'Explosive'},
    {'code': 'H203', 'desc': 'Explosive; fire, blast or projection hazard', 'cat': 'Explosive'},
    {'code': 'H204', 'desc': 'Fire or projection hazard', 'cat': 'Explosive'},
    {'code': 'H205', 'desc': 'May mass explode in fire', 'cat': 'Explosive'},
    {'code': 'H220', 'desc': 'Extremely flammable gas', 'cat': 'Flammable'},
    {'code': 'H221', 'desc': 'Flammable gas', 'cat': 'Flammable'},
    {'code': 'H222', 'desc': 'Extremely flammable aerosol', 'cat': 'Flammable'},
    {'code': 'H223', 'desc': 'Flammable aerosol', 'cat': 'Flammable'},
    {'code': 'H224', 'desc': 'Extremely flammable liquid and vapour', 'cat': 'Flammable'},
    {'code': 'H225', 'desc': 'Highly flammable liquid and vapour', 'cat': 'Flammable'},
    {'code': 'H226', 'desc': 'Flammable liquid and vapour', 'cat': 'Flammable'},
    {'code': 'H228', 'desc': 'Flammable solid', 'cat': 'Flammable'},
    {'code': 'H229', 'desc': 'Pressurised container: May burst if heated', 'cat': 'Flammable'},
    {'code': 'H240', 'desc': 'Heating may cause an explosion', 'cat': 'Flammable'},
    {'code': 'H241', 'desc': 'Heating may cause a fire or explosion', 'cat': 'Flammable'},
    {'code': 'H242', 'desc': 'Heating may cause a fire', 'cat': 'Flammable'},
    {'code': 'H250', 'desc': 'Catches fire spontaneously if exposed to air', 'cat': 'Flammable'},
    {'code': 'H251', 'desc': 'Self-heating: may catch fire', 'cat': 'Flammable'},
    {'code': 'H252', 'desc': 'Self-heating in large quantities; may catch fire', 'cat': 'Flammable'},
    {'code': 'H260', 'desc': 'In contact with water releases flammable gases which may ignite spontaneously', 'cat': 'Flammable'},
    {'code': 'H261', 'desc': 'In contact with water releases flammable gases', 'cat': 'Flammable'},
    {'code': 'H270', 'desc': 'May cause or intensify fire; oxidiser', 'cat': 'Oxidizing'},
    {'code': 'H271', 'desc': 'May cause fire or explosion; strong oxidiser', 'cat': 'Oxidizing'},
    {'code': 'H272', 'desc': 'May intensify fire; oxidiser', 'cat': 'Oxidizing'},
    {'code': 'H280', 'desc': 'Contains gas under pressure; may explode if heated', 'cat': 'Compressed Gas'},
    {'code': 'H281', 'desc': 'Contains refrigerated gas; may cause cryogenic burns or injury', 'cat': 'Compressed Gas'},
    {'code': 'H290', 'desc': 'May be corrosive to metals', 'cat': 'Corrosive'},
    # Health Hazards
    {'code': 'H300', 'desc': 'Fatal if swallowed', 'cat': 'Toxic'},
    {'code': 'H301', 'desc': 'Toxic if swallowed', 'cat': 'Toxic'},
    {'code': 'H302', 'desc': 'Harmful if swallowed', 'cat': 'Irritant'},
    {'code': 'H304', 'desc': 'May be fatal if swallowed and enters airways', 'cat': 'Health Hazard'},
    {'code': 'H310', 'desc': 'Fatal in contact with skin', 'cat': 'Toxic'},
    {'code': 'H311', 'desc': 'Toxic in contact with skin', 'cat': 'Toxic'},
    {'code': 'H312', 'desc': 'Harmful in contact with skin', 'cat': 'Irritant'},
    {'code': 'H314', 'desc': 'Causes severe skin burns and eye damage', 'cat': 'Corrosive'},
    {'code': 'H315', 'desc': 'Causes skin irritation', 'cat': 'Irritant'},
    {'code': 'H317', 'desc': 'May cause an allergic skin reaction', 'cat': 'Irritant'},
    {'code': 'H318', 'desc': 'Causes serious eye damage', 'cat': 'Corrosive'},
    {'code': 'H319', 'desc': 'Causes serious eye irritation', 'cat': 'Irritant'},
    {'code': 'H330', 'desc': 'Fatal if inhaled', 'cat': 'Toxic'},
    {'code': 'H331', 'desc': 'Toxic if inhaled', 'cat': 'Toxic'},
    {'code': 'H332', 'desc': 'Harmful if inhaled', 'cat': 'Irritant'},
    {'code': 'H334', 'desc': 'May cause allergy or asthma symptoms or breathing difficulties if inhaled', 'cat': 'Health Hazard'},
    {'code': 'H335', 'desc': 'May cause respiratory irritation', 'cat': 'Irritant'},
    {'code': 'H336', 'desc': 'May cause drowsiness or dizziness', 'cat': 'Irritant'},
    {'code': 'H340', 'desc': 'May cause genetic defects', 'cat': 'Health Hazard'},
    {'code': 'H341', 'desc': 'Suspected of causing genetic defects', 'cat': 'Health Hazard'},
    {'code': 'H350', 'desc': 'May cause cancer', 'cat': 'Health Hazard'},
    {'code': 'H351', 'desc': 'Suspected of causing cancer', 'cat': 'Health Hazard'},
    {'code': 'H360', 'desc': 'May damage fertility or the unborn child', 'cat': 'Health Hazard'},
    {'code': 'H361', 'desc': 'Suspected of damaging fertility or the unborn child', 'cat': 'Health Hazard'},
    {'code': 'H362', 'desc': 'May cause harm to breast-fed children', 'cat': 'Health Hazard'},
    {'code': 'H370', 'desc': 'Causes damage to organs', 'cat': 'Health Hazard'},
    {'code': 'H371', 'desc': 'May cause damage to organs', 'cat': 'Health Hazard'},
    {'code': 'H372', 'desc': 'Causes damage to organs through prolonged or repeated exposure', 'cat': 'Health Hazard'},
    {'code': 'H373', 'desc': 'May cause damage to organs through prolonged or repeated exposure', 'cat': 'Health Hazard'},
    # Environmental Hazards
    {'code': 'H400', 'desc': 'Very toxic to aquatic life', 'cat': 'Environmentally Damaging'},
    {'code': 'H410', 'desc': 'Very toxic to aquatic life with long lasting effects', 'cat': 'Environmentally Damaging'},
    {'code': 'H411', 'desc': 'Toxic to aquatic life with long lasting effects', 'cat': 'Environmentally Damaging'},
    {'code': 'H412', 'desc': 'Harmful to aquatic life with long lasting effects', 'cat': 'Environmentally Damaging'},
    {'code': 'H413', 'desc': 'May cause long lasting harmful effects to aquatic life', 'cat': 'Environmentally Damaging'},
    {'code': 'H420', 'desc': 'Harms public health and the environment by destroying ozone in the upper atmosphere', 'cat': 'Environmentally Damaging'},
    # Combined H-Codes
    {'code': 'H300+H310', 'desc': 'Fatal if swallowed or in contact with skin', 'cat': 'Toxic'},
    {'code': 'H300+H330', 'desc': 'Fatal if swallowed or if inhaled', 'cat': 'Toxic'},
    {'code': 'H310+H330', 'desc': 'Fatal in contact with skin or if inhaled', 'cat': 'Toxic'},
    {'code': 'H301+H311', 'desc': 'Toxic if swallowed or in contact with skin', 'cat': 'Toxic'},
    {'code': 'H302+H312', 'desc': 'Harmful if swallowed or in contact with skin', 'cat': 'Irritant'},
    {'code': 'H302+H332', 'desc': 'Harmful if swallowed or if inhaled', 'cat': 'Irritant'},
]

# ===== GHS P-Codes (Precautionary Statements) من القالب =====
GHS_P_CODES = [
    # General
    {'code': 'P101', 'desc': 'If medical advice is needed, have product container or label at hand', 'type': 'General'},
    {'code': 'P102', 'desc': 'Keep out of reach of children', 'type': 'General'},
    {'code': 'P103', 'desc': 'Read label before use', 'type': 'General'},
    # Prevention
    {'code': 'P201', 'desc': 'Obtain special instructions before use', 'type': 'Prevention'},
    {'code': 'P202', 'desc': 'Do not handle until all safety precautions have been read and understood', 'type': 'Prevention'},
    {'code': 'P210', 'desc': 'Keep away from heat, hot surface, sparks, open flames and other ignition sources - No smoking', 'type': 'Prevention'},
    {'code': 'P211', 'desc': 'Do not spray on an open flame or other ignition source', 'type': 'Prevention'},
    {'code': 'P220', 'desc': 'Keep away from clothing and other combustible materials', 'type': 'Prevention'},
    {'code': 'P221', 'desc': 'Take any precaution to avoid mixing with combustibles', 'type': 'Prevention'},
    {'code': 'P222', 'desc': 'Do not allow contact with air', 'type': 'Prevention'},
    {'code': 'P223', 'desc': 'Do not allow contact with water', 'type': 'Prevention'},
    {'code': 'P230', 'desc': 'Keep wetted with...', 'type': 'Prevention'},
    {'code': 'P231', 'desc': 'Handle under inert gas', 'type': 'Prevention'},
    {'code': 'P232', 'desc': 'Protect from moisture', 'type': 'Prevention'},
    {'code': 'P233', 'desc': 'Keep container tightly closed', 'type': 'Prevention'},
    {'code': 'P234', 'desc': 'Keep only in original container', 'type': 'Prevention'},
    {'code': 'P235', 'desc': 'Keep cool', 'type': 'Prevention'},
    {'code': 'P240', 'desc': 'Ground/bond container and receiving equipment', 'type': 'Prevention'},
    {'code': 'P241', 'desc': 'Use explosion-proof electrical/ventilating/lighting equipment', 'type': 'Prevention'},
    {'code': 'P242', 'desc': 'Use only non-sparking tools', 'type': 'Prevention'},
    {'code': 'P243', 'desc': 'Take precautionary measures against static discharge', 'type': 'Prevention'},
    {'code': 'P250', 'desc': 'Do not subject to grinding/shock/friction', 'type': 'Prevention'},
    {'code': 'P251', 'desc': 'Do not pierce or burn, even after use', 'type': 'Prevention'},
    {'code': 'P260', 'desc': 'Do not breathe dust/fume/gas/mist/vapors/spray', 'type': 'Prevention'},
    {'code': 'P261', 'desc': 'Avoid breathing dust/fume/gas/mist/vapors/spray', 'type': 'Prevention'},
    {'code': 'P262', 'desc': 'Do not get in eyes, on skin, or on clothing', 'type': 'Prevention'},
    {'code': 'P263', 'desc': 'Avoid contact during pregnancy/while nursing', 'type': 'Prevention'},
    {'code': 'P264', 'desc': 'Wash ... thoroughly after handling', 'type': 'Prevention'},
    {'code': 'P270', 'desc': 'Do not eat, drink or smoke when using this product', 'type': 'Prevention'},
    {'code': 'P271', 'desc': 'Use only outdoors or in a well-ventilated area', 'type': 'Prevention'},
    {'code': 'P272', 'desc': 'Contaminated work clothing should not be allowed out of the workplace', 'type': 'Prevention'},
    {'code': 'P273', 'desc': 'Avoid release to the environment', 'type': 'Prevention'},
    {'code': 'P280', 'desc': 'Wear protective gloves/protective clothing/eye protection/face protection', 'type': 'Prevention'},
    {'code': 'P281', 'desc': 'Use personal protective equipment as required', 'type': 'Prevention'},
    {'code': 'P282', 'desc': 'Wear cold insulating gloves/face shield/eye protection', 'type': 'Prevention'},
    {'code': 'P283', 'desc': 'Wear fire resistant or flame retardant clothing', 'type': 'Prevention'},
    {'code': 'P284', 'desc': 'Wear respiratory protection', 'type': 'Prevention'},
    # Response
    {'code': 'P301', 'desc': 'IF SWALLOWED:', 'type': 'Response'},
    {'code': 'P302', 'desc': 'IF ON SKIN:', 'type': 'Response'},
    {'code': 'P303', 'desc': 'IF ON SKIN (or hair):', 'type': 'Response'},
    {'code': 'P304', 'desc': 'IF INHALED:', 'type': 'Response'},
    {'code': 'P305', 'desc': 'IF IN EYES:', 'type': 'Response'},
    {'code': 'P306', 'desc': 'IF ON CLOTHING:', 'type': 'Response'},
    {'code': 'P307', 'desc': 'IF exposed:', 'type': 'Response'},
    {'code': 'P308', 'desc': 'IF exposed or concerned:', 'type': 'Response'},
    {'code': 'P310', 'desc': 'Immediately call a POISON CENTER or doctor', 'type': 'Response'},
    {'code': 'P311', 'desc': 'Call a POISON CENTER or doctor', 'type': 'Response'},
    {'code': 'P312', 'desc': 'Call a POISON CENTER or doctor if you feel unwell', 'type': 'Response'},
    {'code': 'P313', 'desc': 'Get medical advice/attention', 'type': 'Response'},
    {'code': 'P314', 'desc': 'Get medical advice/attention if you feel unwell', 'type': 'Response'},
    {'code': 'P315', 'desc': 'Get immediate medical advice/attention', 'type': 'Response'},
    {'code': 'P320', 'desc': 'Specific treatment is urgent', 'type': 'Response'},
    {'code': 'P321', 'desc': 'Specific treatment', 'type': 'Response'},
    {'code': 'P330', 'desc': 'Rinse mouth', 'type': 'Response'},
    {'code': 'P331', 'desc': 'Do NOT induce vomiting', 'type': 'Response'},
    {'code': 'P332', 'desc': 'IF SKIN irritation occurs:', 'type': 'Response'},
    {'code': 'P333', 'desc': 'IF SKIN irritation or rash occurs:', 'type': 'Response'},
    {'code': 'P334', 'desc': 'Immerse in cool water or wrap in wet bandages', 'type': 'Response'},
    {'code': 'P335', 'desc': 'Brush off loose particles from skin', 'type': 'Response'},
    {'code': 'P336', 'desc': 'Thaw frosted parts with lukewarm water. Do not rub affected area', 'type': 'Response'},
    {'code': 'P337', 'desc': 'IF eye irritation persists:', 'type': 'Response'},
    {'code': 'P338', 'desc': 'Remove contact lenses, if present and easy to do. Continue rinsing', 'type': 'Response'},
    {'code': 'P340', 'desc': 'Remove victim to fresh air and keep at rest in a position comfortable for breathing', 'type': 'Response'},
    {'code': 'P341', 'desc': 'If breathing is difficult, remove victim to fresh air and keep at rest', 'type': 'Response'},
    {'code': 'P342', 'desc': 'If experiencing respiratory symptoms:', 'type': 'Response'},
    {'code': 'P350', 'desc': 'Gently wash with plenty of soap and water', 'type': 'Response'},
    {'code': 'P351', 'desc': 'Rinse cautiously with water for several minutes', 'type': 'Response'},
    {'code': 'P352', 'desc': 'Wash with plenty of water', 'type': 'Response'},
    {'code': 'P353', 'desc': 'Rinse skin with water or shower', 'type': 'Response'},
    {'code': 'P360', 'desc': 'Rinse immediately contaminated clothing and skin with plenty of water before removing clothes', 'type': 'Response'},
    {'code': 'P361', 'desc': 'Take off immediately all contaminated clothing', 'type': 'Response'},
    {'code': 'P362', 'desc': 'Take off contaminated clothing', 'type': 'Response'},
    {'code': 'P363', 'desc': 'Wash contaminated clothing before reuse', 'type': 'Response'},
    {'code': 'P370', 'desc': 'In case of fire:', 'type': 'Response'},
    {'code': 'P371', 'desc': 'In case of major fire and large quantities:', 'type': 'Response'},
    {'code': 'P372', 'desc': 'Explosion risk', 'type': 'Response'},
    {'code': 'P373', 'desc': 'DO NOT fight fire when fire reaches explosives', 'type': 'Response'},
    {'code': 'P374', 'desc': 'Fight fire with normal precautions from a reasonable distance', 'type': 'Response'},
    {'code': 'P376', 'desc': 'Stop leak if safe to do so', 'type': 'Response'},
    {'code': 'P377', 'desc': 'Leaking gas fire: Do not extinguish, unless leak can be stopped safely', 'type': 'Response'},
    {'code': 'P378', 'desc': 'Use ... to extinguish', 'type': 'Response'},
    {'code': 'P380', 'desc': 'Evacuate area', 'type': 'Response'},
    {'code': 'P381', 'desc': 'In case of leakage, eliminate all ignition sources', 'type': 'Response'},
    {'code': 'P390', 'desc': 'Absorb spillage to prevent material damage', 'type': 'Response'},
    {'code': 'P391', 'desc': 'Collect spillage', 'type': 'Response'},
    # Combined Response codes
    {'code': 'P301+P310', 'desc': 'IF SWALLOWED: Immediately call a POISON CENTER or doctor', 'type': 'Response'},
    {'code': 'P301+P312', 'desc': 'IF SWALLOWED: call a POISON CENTER or doctor if you feel unwell', 'type': 'Response'},
    {'code': 'P301+P330+P331', 'desc': 'IF SWALLOWED: Rinse mouth. Do NOT induce vomiting', 'type': 'Response'},
    {'code': 'P302+P334', 'desc': 'IF ON SKIN: Immerse in cool water or wrap in wet bandages', 'type': 'Response'},
    {'code': 'P302+P350', 'desc': 'IF ON SKIN: Gently wash with plenty of soap and water', 'type': 'Response'},
    {'code': 'P302+P352', 'desc': 'IF ON SKIN: wash with plenty of water', 'type': 'Response'},
    {'code': 'P303+P361+P353', 'desc': 'IF ON SKIN (or hair): Take off immediately all contaminated clothing. Rinse skin with water', 'type': 'Response'},
    {'code': 'P304+P312', 'desc': 'IF INHALED: Call a POISON CENTER or doctor if you feel unwell', 'type': 'Response'},
    {'code': 'P304+P340', 'desc': 'IF INHALED: Remove person to fresh air and keep comfortable for breathing', 'type': 'Response'},
    {'code': 'P305+P351+P338', 'desc': 'IF IN EYES: Rinse cautiously with water for several minutes. Remove contact lenses if present', 'type': 'Response'},
    {'code': 'P308+P311', 'desc': 'IF exposed or concerned: Call a POISON CENTER or doctor', 'type': 'Response'},
    {'code': 'P308+P313', 'desc': 'IF exposed or concerned: Get medical advice/attention', 'type': 'Response'},
    {'code': 'P332+P313', 'desc': 'IF SKIN irritation occurs: Get medical advice/attention', 'type': 'Response'},
    {'code': 'P333+P313', 'desc': 'IF SKIN irritation or rash occurs: Get medical advice/attention', 'type': 'Response'},
    {'code': 'P337+P313', 'desc': 'IF eye irritation persists: Get medical advice/attention', 'type': 'Response'},
    {'code': 'P342+P311', 'desc': 'IF experiencing respiratory symptoms: Call a POISON CENTER or doctor', 'type': 'Response'},
    {'code': 'P370+P376', 'desc': 'In case of fire: Stop leak if safe to do so', 'type': 'Response'},
    {'code': 'P370+P378', 'desc': 'In case of fire: Use ... to extinguish', 'type': 'Response'},
    {'code': 'P370+P380', 'desc': 'In case of fire: Evacuate area', 'type': 'Response'},
    # Storage
    {'code': 'P401', 'desc': 'Store in accordance with...', 'type': 'Storage'},
    {'code': 'P402', 'desc': 'Store in a dry place', 'type': 'Storage'},
    {'code': 'P403', 'desc': 'Store in a well-ventilated place', 'type': 'Storage'},
    {'code': 'P404', 'desc': 'Store in a closed container', 'type': 'Storage'},
    {'code': 'P405', 'desc': 'Store locked up', 'type': 'Storage'},
    {'code': 'P406', 'desc': 'Store in corrosive resistant container with a resistant inner liner', 'type': 'Storage'},
    {'code': 'P407', 'desc': 'Maintain air gap between stacks or pallets', 'type': 'Storage'},
    {'code': 'P410', 'desc': 'Protect from sunlight', 'type': 'Storage'},
    {'code': 'P411', 'desc': 'Store at temperatures not exceeding...°C/...°F', 'type': 'Storage'},
    {'code': 'P412', 'desc': 'Do not expose to temperatures exceeding 50°C/122°F', 'type': 'Storage'},
    {'code': 'P413', 'desc': 'Store bulk masses greater than...kg/...lbs at temperatures not exceeding...°C/...°F', 'type': 'Storage'},
    {'code': 'P420', 'desc': 'Store separately', 'type': 'Storage'},
    {'code': 'P422', 'desc': 'Store contents under...', 'type': 'Storage'},
    {'code': 'P402+P404', 'desc': 'Store in a dry place. Store in a closed container', 'type': 'Storage'},
    {'code': 'P403+P233', 'desc': 'Store in a well-ventilated place. Keep container tightly closed', 'type': 'Storage'},
    {'code': 'P403+P235', 'desc': 'Store in a well-ventilated place. Keep cool', 'type': 'Storage'},
    {'code': 'P410+P403', 'desc': 'Protect from sunlight. Store in a well-ventilated place', 'type': 'Storage'},
    {'code': 'P410+P412', 'desc': 'Protect from sunlight. Do not expose to temperatures exceeding 50°C/122°F', 'type': 'Storage'},
    # Disposal
    {'code': 'P501', 'desc': 'Dispose of contents/container to...', 'type': 'Disposal'},
    {'code': 'P502', 'desc': 'Refer to manufacturer or supplier for information on recovery or recycling', 'type': 'Disposal'},
]

GHS_SIGNAL_WORDS = ['Warning', 'Danger']

GHS_CLASSIFICATIONS = ['Irritant', 'Oxidizing', 'Flammable', 'Environmentally Damaging', 'Corrosive', 'Toxic', 'Health Hazard', 'Compressed Gas', 'Explosive']

# ===== قاعدة البيانات =====
def get_db():
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # إنشاء جدول البروفايل العطري لو ما كان موجود
    conn.execute('''CREATE TABLE IF NOT EXISTS material_olfactive (
        material_id INTEGER PRIMARY KEY,
        citrus INTEGER DEFAULT 0, aldehydic INTEGER DEFAULT 0, aromatic INTEGER DEFAULT 0,
        green INTEGER DEFAULT 0, marine INTEGER DEFAULT 0, floral INTEGER DEFAULT 0,
        fruity INTEGER DEFAULT 0, spicy INTEGER DEFAULT 0, balsamic INTEGER DEFAULT 0,
        woody INTEGER DEFAULT 0, ambery INTEGER DEFAULT 0, musky INTEGER DEFAULT 0,
        leathery INTEGER DEFAULT 0, animal INTEGER DEFAULT 0,
        FOREIGN KEY (material_id) REFERENCES materials(id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS formula_notes (
        id INTEGER PRIMARY KEY,
        formula_id INTEGER,
        title TEXT,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (formula_id) REFERENCES formulas(id) ON DELETE CASCADE
    )''')
    # Migrate: add columns if missing
    existing = [row[1] for row in conn.execute("PRAGMA table_info(formulas)").fetchall()]
    for col in ['target_audience', 'age_group', 'gender', 'season', 'occasion', 'scent_type', 'review_notes', 'card_settings']:
        if col not in existing:
            conn.execute(f"ALTER TABLE formulas ADD COLUMN {col} TEXT DEFAULT ''")
    # Migrate: add ifra_override to formula_ingredients
    fi_cols = [row[1] for row in conn.execute("PRAGMA table_info(formula_ingredients)").fetchall()]
    if 'ifra_override' not in fi_cols:
        conn.execute("ALTER TABLE formula_ingredients ADD COLUMN ifra_override REAL DEFAULT NULL")
    # Draft system tables
    conn.execute('''CREATE TABLE IF NOT EXISTS formula_drafts (
        id INTEGER PRIMARY KEY,
        formula_id INTEGER,
        draft_number INTEGER,
        name TEXT,
        notes TEXT,
        is_final INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (formula_id) REFERENCES formulas(id) ON DELETE CASCADE
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS draft_ingredients (
        id INTEGER PRIMARY KEY,
        draft_id INTEGER,
        material_id INTEGER,
        weight REAL DEFAULT 0,
        dilution REAL DEFAULT 0,
        diluent TEXT DEFAULT '',
        diluent_other TEXT DEFAULT '',
        notes TEXT,
        ifra_override REAL DEFAULT NULL,
        FOREIGN KEY (draft_id) REFERENCES formula_drafts(id) ON DELETE CASCADE
    )''')
    return conn

def init_db():
    log("[DB] Initializing database...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, name TEXT, role TEXT DEFAULT 'user'
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS company_info (
        id INTEGER PRIMARY KEY, name TEXT, address TEXT, phone TEXT, email TEXT, website TEXT, logo_path TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY, name TEXT, country TEXT, email TEXT, phone TEXT, website TEXT, notes TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS families (
        id INTEGER PRIMARY KEY, name TEXT, name_ar TEXT, description TEXT, icon TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY, name TEXT, name_ar TEXT, cas_number TEXT,
        family_id INTEGER, profile TEXT DEFAULT 'Heart', supplier_id INTEGER,
        ifra_limit REAL, purchase_price REAL DEFAULT 0, purchase_quantity REAL DEFAULT 1,
        price_per_gram REAL DEFAULT 0, odor_description TEXT, notes TEXT,
        flash_point TEXT, specific_gravity TEXT, refractive_index TEXT,
        color TEXT, physical_state TEXT, ph TEXT, melting_point TEXT,
        boiling_point TEXT, solubility TEXT, vapor_density TEXT, appearance TEXT,
        synonyms TEXT, lot TEXT, strength_odor TEXT, vapor_pressure TEXT,
        effect TEXT, recommended_smell_pct TEXT, properties TEXT, in_stock REAL DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ifra_standards (
        id INTEGER PRIMARY KEY,
        ifra_key TEXT UNIQUE,
        name TEXT,
        cas_numbers TEXT,
        synonyms TEXT,
        standard_type TEXT,
        amendment INTEGER,
        year_published TEXT,
        risk_property TEXT,
        restriction_notes TEXT,
        specification_notes TEXT,
        contributions TEXT,
        cat1 REAL, cat2 REAL, cat3 REAL, cat4 REAL,
        cat5a REAL, cat5b REAL, cat5c REAL, cat5d REAL,
        cat6 REAL, cat7a REAL, cat7b REAL, cat8 REAL,
        cat9 REAL, cat10a REAL, cat10b REAL,
        cat11a REAL, cat11b REAL, cat12 REAL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS ifra_cas_lookup (
        id INTEGER PRIMARY KEY,
        cas_number TEXT,
        ifra_standard_id INTEGER,
        FOREIGN KEY (ifra_standard_id) REFERENCES ifra_standards(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS material_msds (
        id INTEGER PRIMARY KEY, material_id INTEGER UNIQUE,
        h_codes TEXT, p_codes TEXT, pictograms TEXT, signal_word TEXT, ghs_classification TEXT,
        FOREIGN KEY (material_id) REFERENCES materials(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS material_olfactive (
        material_id INTEGER PRIMARY KEY,
        citrus INTEGER DEFAULT 0, aldehydic INTEGER DEFAULT 0, aromatic INTEGER DEFAULT 0,
        green INTEGER DEFAULT 0, marine INTEGER DEFAULT 0, floral INTEGER DEFAULT 0,
        fruity INTEGER DEFAULT 0, spicy INTEGER DEFAULT 0, balsamic INTEGER DEFAULT 0,
        woody INTEGER DEFAULT 0, ambery INTEGER DEFAULT 0, musky INTEGER DEFAULT 0,
        leathery INTEGER DEFAULT 0, animal INTEGER DEFAULT 0,
        FOREIGN KEY (material_id) REFERENCES materials(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS formulas (
        id INTEGER PRIMARY KEY, name TEXT, description TEXT, ifra_category TEXT DEFAULT 'cat4',
        status TEXT DEFAULT 'draft', notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        active_ratio REAL DEFAULT 0.5, ifra_design_limit REAL DEFAULT 0,
        ifra_final_limit REAL DEFAULT 0, sample_weight REAL DEFAULT 1000,
        target_audience TEXT DEFAULT '', age_group TEXT DEFAULT '', gender TEXT DEFAULT '',
        season TEXT DEFAULT '', occasion TEXT DEFAULT '', scent_type TEXT DEFAULT '',
        review_notes TEXT DEFAULT ''
    )''')
    # Add review columns if they don't exist (for existing databases)
    for col in ['target_audience', 'age_group', 'gender', 'season', 'occasion', 'scent_type', 'review_notes']:
        try:
            c.execute(f"ALTER TABLE formulas ADD COLUMN {col} TEXT DEFAULT ''")
        except:
            pass
    
    c.execute('''CREATE TABLE IF NOT EXISTS formula_ingredients (
        id INTEGER PRIMARY KEY, formula_id INTEGER, material_id INTEGER,
        weight REAL DEFAULT 0, dilution REAL DEFAULT 0, 
        diluent TEXT DEFAULT '', diluent_other TEXT DEFAULT '',
        notes TEXT,
        FOREIGN KEY (formula_id) REFERENCES formulas(id) ON DELETE CASCADE
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS formula_notes (
        id INTEGER PRIMARY KEY,
        formula_id INTEGER,
        title TEXT,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (formula_id) REFERENCES formulas(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS formula_drafts (
        id INTEGER PRIMARY KEY,
        formula_id INTEGER,
        draft_number INTEGER,
        name TEXT,
        notes TEXT,
        is_final INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (formula_id) REFERENCES formulas(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS draft_ingredients (
        id INTEGER PRIMARY KEY,
        draft_id INTEGER,
        material_id INTEGER,
        weight REAL DEFAULT 0,
        dilution REAL DEFAULT 0,
        diluent TEXT DEFAULT '',
        diluent_other TEXT DEFAULT '',
        notes TEXT,
        ifra_override REAL DEFAULT NULL,
        FOREIGN KEY (draft_id) REFERENCES formula_drafts(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS production_orders (
        id INTEGER PRIMARY KEY, order_number TEXT, formula_id INTEGER, target_quantity REAL,
        scale_factor REAL DEFAULT 1, customer_name TEXT, batch_number TEXT,
        status TEXT DEFAULT 'pending', notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS ifra_contributions (
        id INTEGER PRIMARY KEY,
        source_type TEXT NOT NULL,
        ncs_cas TEXT NOT NULL,
        ncs_name TEXT,
        ncs_botanical TEXT,
        constituent_cas TEXT NOT NULL,
        constituent_name TEXT,
        concentration_pct REAL NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS notebook_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT DEFAULT '',
        category TEXT DEFAULT 'idea',
        tags TEXT DEFAULT '',
        body TEXT DEFAULT '',
        profile TEXT DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # بيانات افتراضية
    c.execute("INSERT OR IGNORE INTO users (username, password, name, role) VALUES ('admin', 'admin123', 'المدير', 'admin')")
    c.execute("INSERT OR IGNORE INTO company_info (id, name, address, phone, email) VALUES (1, 'My Perfumery', 'Kuwait', '+965 xxxx xxxx', 'info@myperfumery.com')")
    # Rebrand stale company name
    c.execute("UPDATE company_info SET name='My Perfumery' WHERE LOWER(TRIM(name)) IN ('perfume vault', 'perfumevault', 'perfume-vault')")
    
    # حذف العوائل القديمة وإعادة إضافتها بدون تكرار
    c.execute("DELETE FROM families")
    families = [
        ('Floral', 'زهري', '🌸'), ('Oriental', 'شرقي', '🌙'), ('Woody', 'خشبي', '🪵'),
        ('Fresh', 'منعش', '🌬️'), ('Citrus', 'حمضي', '🍋'), ('Aromatic', 'أروماتيك', '🌿'),
        ('Musk', 'مسك', '🫧'), ('Amber', 'عنبر', '💎'), ('Oud', 'عود', '🪘'), ('Spicy', 'توابل', '🌶️'),
        ('Fruity', 'فواكه', '🍑'), ('Green', 'أخضر', '🍃'), ('Aquatic', 'مائي', '🌊'),
        ('Gourmand', 'حلويات', '🍯'), ('Leather', 'جلد', '🧳'), ('Powdery', 'بودري', '✨'),
        ('Balsamic', 'بلسمي', '🍶'), ('Animalic', 'حيواني', '🐾'), ('Herbal', 'أعشاب', '🌱'),
        ('Resinous', 'راتنجي', '🫗'), ('Earthy', 'ترابي', '🌍'), ('Smoky', 'دخاني', '🔥')
    ]
    for i, (name, name_ar, icon) in enumerate(families, 1):
        c.execute("INSERT INTO families (id, name, name_ar, icon) VALUES (?, ?, ?, ?)", (i, name, name_ar, icon))
    
    conn.commit()
    
    # تحديث الجداول القديمة - إضافة أعمدة جديدة إذا لم تكن موجودة
    new_columns = [
        ('materials', 'flash_point', 'TEXT'),
        ('materials', 'specific_gravity', 'TEXT'),
        ('materials', 'refractive_index', 'TEXT'),
        ('materials', 'color', 'TEXT'),
        ('materials', 'physical_state', 'TEXT'),
        ('materials', 'ph', 'TEXT'),
        ('materials', 'melting_point', 'TEXT'),
        ('materials', 'boiling_point', 'TEXT'),
        ('materials', 'solubility', 'TEXT'),
        ('materials', 'vapor_density', 'TEXT'),
        ('materials', 'appearance', 'TEXT'),
        ('materials', 'synonyms', 'TEXT'),
        ('materials', 'lot', 'TEXT'),
        ('materials', 'strength_odor', 'TEXT'),
        ('materials', 'vapor_pressure', 'TEXT'),
        ('materials', 'effect', 'TEXT'),
        ('materials', 'recommended_smell_pct', 'TEXT'),
        ('materials', 'properties', 'TEXT'),
        ('materials', 'in_stock', 'REAL DEFAULT 0'),
        ('materials', 'manual_ifra_cats', 'TEXT'),
        ('material_msds', 'ghs_classification', 'TEXT'),
        ('families', 'icon', 'TEXT'),
        ('formula_ingredients', 'diluent', 'TEXT'),
        ('formula_ingredients', 'diluent_other', 'TEXT'),
        ('formulas', 'active_ratio', 'REAL'),
        ('formulas', 'ifra_design_limit', 'REAL'),
        ('formulas', 'ifra_final_limit', 'REAL'),
        ('formulas', 'sample_weight', 'REAL'),
    ]
    for table, column, dtype in new_columns:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {dtype}")
        except: pass
    
    conn.commit()
    conn.close()
    log("[DB] Database initialized!")

def import_ifra_standards():
    """Import IFRA standards from the downloaded XLSX file"""
    import zipfile
    import xml.etree.ElementTree as ET

    xlsx_path = os.path.join(ASSET_DIR, 'data', 'ifra_standards.xlsx')
    if not os.path.exists(xlsx_path):
        log("[IFRA] Standards file not found, skipping import")
        return

    conn = get_db()
    # Check if already imported correctly (verify a known entry has valid cat4 data)
    count = conn.execute("SELECT COUNT(*) FROM ifra_standards").fetchone()[0]
    if count > 0:
        # Verify data integrity - check if cat columns have data
        sample = conn.execute("SELECT cat4 FROM ifra_standards WHERE ifra_key='IFRA_STD_001'").fetchone()
        if sample and sample['cat4'] and sample['cat4'] > 0:
            conn.close()
            return
        # Data is corrupt (old bug), re-import
        log("[IFRA] Re-importing IFRA standards (fixing column mapping)...")
        conn.execute("DELETE FROM ifra_cas_lookup")
        conn.execute("DELETE FROM ifra_standards")
        conn.commit()

    log("[IFRA] Importing IFRA 51st Amendment standards...")

    try:
        zf = zipfile.ZipFile(xlsx_path)
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

        # Read shared strings
        shared = []
        try:
            ss_tree = ET.parse(zf.open('xl/sharedStrings.xml'))
            for si in ss_tree.findall('.//s:si', ns):
                parts = []
                for t in si.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'):
                    if t.text:
                        parts.append(t.text)
                shared.append(''.join(parts))
        except:
            pass

        # Read sheet1
        sheet_tree = ET.parse(zf.open('xl/worksheets/sheet1.xml'))
        rows = sheet_tree.findall('.//s:sheetData/s:row', ns)

        def cell_ref_to_col(ref):
            col = ''
            for ch in ref:
                if ch.isalpha():
                    col += ch
                else:
                    break
            result = 0
            for ch in col:
                result = result * 26 + (ord(ch) - ord('A') + 1)
            return result - 1  # A=0, B=1, ..., Z=25, AA=26, AB=27

        def get_cell_value(cell):
            t = cell.get('t', '')
            v_el = cell.find('s:v', ns)
            if v_el is None or v_el.text is None:
                return ''
            if t == 's':
                idx = int(v_el.text)
                return shared[idx] if idx < len(shared) else ''
            return v_el.text

        # Category column indices (T=19 through AK=36)
        cat_cols = {
            19: 'cat1', 20: 'cat2', 21: 'cat3', 22: 'cat4',
            23: 'cat5a', 24: 'cat5b', 25: 'cat5c', 26: 'cat5d',
            27: 'cat6', 28: 'cat7a', 29: 'cat7b', 30: 'cat8',
            31: 'cat9', 32: 'cat10a', 33: 'cat10b',
            34: 'cat11a', 35: 'cat11b', 36: 'cat12'
        }

        def parse_cat_value(val):
            """Parse category limit value to float or None"""
            if not val:
                return None
            val = val.strip()
            if not val or val.lower() in ('', 'none'):
                return None
            if 'no restriction' in val.lower():
                return -1  # -1 = no restriction
            if 'prohibited' in val.lower():
                return 0
            if 'see notebox' in val.lower():
                return None
            # Handle comma decimals (European format)
            val = val.replace(',', '.').strip("'").strip()
            # Extract first number
            m = re.match(r'(-?[\d.]+)', val)
            if m:
                try:
                    return float(m.group(1))
                except:
                    return None
            return None

        imported = 0
        for row_el in rows:
            row_num = int(row_el.get('r', '0'))
            if row_num < 4:  # Skip header rows
                continue

            cells = {}
            for cell in row_el.findall('s:c', ns):
                ref = cell.get('r', '')
                col_idx = cell_ref_to_col(ref)
                cells[col_idx] = get_cell_value(cell)

            ifra_key = cells.get(0, '').strip()
            if not ifra_key or not ifra_key.startswith('IFRA_STD'):
                continue

            name = cells.get(6, '').strip()
            cas_raw = cells.get(7, '').strip()
            amendment = cells.get(1, '')
            year_pub = cells.get(3, '')
            std_type = cells.get(10, '').strip()
            risk_prop = cells.get(11, '').strip()
            synonyms = cells.get(9, '').strip()
            restriction_notes = cells.get(15, '').strip()
            spec_notes = cells.get(16, '').strip()
            contributions = cells.get(17, '').strip()

            try:
                amendment = int(float(amendment)) if amendment else 0
            except:
                amendment = 0

            # Parse category limits
            cat_values = {}
            for col_idx, cat_name in cat_cols.items():
                cat_values[cat_name] = parse_cat_value(cells.get(col_idx, ''))

            conn.execute('''INSERT OR REPLACE INTO ifra_standards
                (ifra_key, name, cas_numbers, synonyms, standard_type, amendment, year_published,
                 risk_property, restriction_notes, specification_notes, contributions,
                 cat1, cat2, cat3, cat4, cat5a, cat5b, cat5c, cat5d,
                 cat6, cat7a, cat7b, cat8, cat9, cat10a, cat10b, cat11a, cat11b, cat12)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (ifra_key, name, cas_raw, synonyms, std_type, amendment, year_pub,
                 risk_prop, restriction_notes, spec_notes, contributions,
                 cat_values.get('cat1'), cat_values.get('cat2'), cat_values.get('cat3'), cat_values.get('cat4'),
                 cat_values.get('cat5a'), cat_values.get('cat5b'), cat_values.get('cat5c'), cat_values.get('cat5d'),
                 cat_values.get('cat6'), cat_values.get('cat7a'), cat_values.get('cat7b'), cat_values.get('cat8'),
                 cat_values.get('cat9'), cat_values.get('cat10a'), cat_values.get('cat10b'),
                 cat_values.get('cat11a'), cat_values.get('cat11b'), cat_values.get('cat12')))

            std_id = conn.execute("SELECT id FROM ifra_standards WHERE ifra_key=?", (ifra_key,)).fetchone()['id']

            # Insert CAS lookup entries
            cas_list = re.split(r'[\n\r\s]+', cas_raw)
            for cas in cas_list:
                cas = cas.strip()
                if cas and re.match(r'\d+-\d+-\d+', cas):
                    conn.execute("INSERT OR IGNORE INTO ifra_cas_lookup (cas_number, ifra_standard_id) VALUES (?,?)",
                                 (cas, std_id))

            imported += 1

        conn.commit()
        zf.close()
        log(f"[IFRA] Imported {imported} IFRA standards")
    except Exception as e:
        log(f"[IFRA] Error importing: {e}")
    finally:
        conn.close()

def import_ifra_contributions():
    """Import IFRA contributions from other sources (naturals + Schiff bases)"""
    import zipfile
    import xml.etree.ElementTree as ET

    xlsx_path = os.path.join(ASSET_DIR, 'data', 'ifra_annex_contributions.xlsx')
    if not os.path.exists(xlsx_path):
        log("[IFRA] Contributions annex file not found, skipping import")
        return

    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM ifra_contributions").fetchone()[0]
    if count > 0:
        conn.close()
        return

    log("[IFRA] Importing IFRA contributions from other sources...")

    try:
        zf = zipfile.ZipFile(xlsx_path)
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

        # Read shared strings
        shared = []
        try:
            ss_tree = ET.parse(zf.open('xl/sharedStrings.xml'))
            for si in ss_tree.findall('.//s:si', ns):
                parts = []
                for t in si.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'):
                    if t.text:
                        parts.append(t.text)
                shared.append(''.join(parts))
        except:
            pass

        def cell_ref_to_col(ref):
            col = ''
            for ch in ref:
                if ch.isalpha():
                    col += ch
                else:
                    break
            result = 0
            for ch in col:
                result = result * 26 + (ord(ch) - ord('A') + 1)
            return result - 1

        def get_cell_value(cell):
            t = cell.get('t', '')
            v_el = cell.find('s:v', ns)
            if v_el is None or v_el.text is None:
                return ''
            if t == 's':
                idx = int(v_el.text)
                return shared[idx] if idx < len(shared) else ''
            return v_el.text

        imported = 0

        # === Sheet 1: Natural Contributions ===
        # Columns: D=NCS CAS, F=NCS Name, G=Botanical, H=Constituent CAS, I=Constituent Name, J=Concentration %
        sheet1 = ET.parse(zf.open('xl/worksheets/sheet1.xml'))
        rows1 = sheet1.findall('.//s:sheetData/s:row', ns)

        for row_el in rows1:
            row_num = int(row_el.get('r', '0'))
            if row_num < 8:  # Skip header rows (data starts at row 8)
                continue

            cells = {}
            for cell in row_el.findall('s:c', ns):
                ref = cell.get('r', '')
                col_idx = cell_ref_to_col(ref)
                cells[col_idx] = get_cell_value(cell)

            ncs_cas = cells.get(3, '').strip()  # D = col 3
            ncs_name = cells.get(5, '').strip()  # F = col 5
            botanical = cells.get(6, '').strip()  # G = col 6
            constituent_cas = cells.get(7, '').strip()  # H = col 7
            constituent_name = cells.get(8, '').strip()  # I = col 8
            conc_str = cells.get(9, '').strip()  # J = col 9

            if not ncs_cas or not constituent_cas or not conc_str:
                continue

            try:
                concentration = float(conc_str.replace(',', '.'))
            except:
                continue

            conn.execute('''INSERT INTO ifra_contributions
                (source_type, ncs_cas, ncs_name, ncs_botanical, constituent_cas, constituent_name, concentration_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                ('natural', ncs_cas, ncs_name, botanical, constituent_cas, constituent_name, concentration))
            imported += 1

        # === Sheet 3: Schiff Bases ===
        # Columns: A=Aldehyde Name, B=Aldehyde CAS, C=Schiff Base Name, D=Schiff Base CAS, E=Concentration %
        sheet3 = ET.parse(zf.open('xl/worksheets/sheet3.xml'))
        rows3 = sheet3.findall('.//s:sheetData/s:row', ns)

        for row_el in rows3:
            row_num = int(row_el.get('r', '0'))
            if row_num < 5:  # Skip header rows (data starts at row 5)
                continue

            cells = {}
            for cell in row_el.findall('s:c', ns):
                ref = cell.get('r', '')
                col_idx = cell_ref_to_col(ref)
                cells[col_idx] = get_cell_value(cell)

            aldehyde_name = cells.get(0, '').strip()  # A = col 0
            aldehyde_cas = cells.get(1, '').strip()  # B = col 1
            schiff_name = cells.get(2, '').strip()  # C = col 2
            schiff_cas = cells.get(3, '').strip()  # D = col 3
            conc_str = cells.get(4, '').strip()  # E = col 4

            if not schiff_cas or not aldehyde_cas or not conc_str:
                continue

            # Schiff base CAS may have multiple (separated by ;)
            for cas in schiff_cas.split(';'):
                cas = cas.strip()
                if not cas:
                    continue
                try:
                    concentration = float(conc_str.replace(',', '.'))
                except:
                    continue

                conn.execute('''INSERT INTO ifra_contributions
                    (source_type, ncs_cas, ncs_name, ncs_botanical, constituent_cas, constituent_name, concentration_pct)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    ('schiff_base', cas, schiff_name, None, aldehyde_cas, aldehyde_name, concentration))
                imported += 1

        conn.commit()
        zf.close()
        log(f"[IFRA] Imported {imported} contribution entries")
    except Exception as e:
        log(f"[IFRA] Error importing contributions: {e}")
    finally:
        conn.close()

def get_concentration(dilution):
    """
    حساب التركيز (مطابق للإكسل):
    - dilution هو نسبة الزيت الصافي (0 إلى 1)
    - 1 = صافي 100% (لا مذيب)
    - 0.5 = 50% زيت + 50% مذيب
    - 0.1 = 10% زيت + 90% مذيب
    - 0 أو None = صافي 100% (افتراضي)
    
    المعادلة: وزن الزيت صافي = وزن الزيت × نسبة التخفيف
    """
    if dilution is None or dilution == 0:
        return 1.0  # صافي 100%
    return float(dilution)  # النسبة (0 إلى 1)

# ===== المصادقة =====
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ===== الصفحات الأساسية =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
                           (request.form['username'], request.form['password'])).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            # Auto-backup on login
            try:
                create_backup('login')
            except Exception as e:
                log(f"[BACKUP] Auto-backup failed: {e}")
            return redirect('/')
        error = 'خطأ في اسم المستخدم أو كلمة المرور'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
@login_required
def index():
    conn = get_db()
    stats = {
        'materials': conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0],
        'formulas': conn.execute("SELECT COUNT(*) FROM formulas").fetchone()[0],
        'suppliers': conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0],
        'production': conn.execute("SELECT COUNT(*) FROM production_orders WHERE status='pending'").fetchone()[0]
    }
    recent = conn.execute("SELECT * FROM formulas ORDER BY created_at DESC LIMIT 5").fetchall()
    conn.close()
    return render_template('index.html', stats=stats, recent_formulas=recent)

@app.route('/materials')
@login_required
def materials():
    conn = get_db()
    families = conn.execute("SELECT * FROM families ORDER BY name").fetchall()
    suppliers = conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    conn.close()
    return render_template('materials.html', families=families, suppliers=suppliers,
                          h_codes=GHS_H_CODES, p_codes=GHS_P_CODES, pictograms=GHS_PICTOGRAMS,
                          classifications=GHS_CLASSIFICATIONS, signal_words=GHS_SIGNAL_WORDS,
                          ifra_categories=IFRA_CATEGORIES)

@app.route('/formulas')
@login_required
def formulas():
    return render_template('formulas.html')

@app.route('/formula/<int:id>')
@login_required
def formula_detail(id):
    conn = get_db()
    formula = conn.execute("SELECT * FROM formulas WHERE id=?", (id,)).fetchone()
    materials = conn.execute("SELECT id, name, name_ar, cas_number FROM materials ORDER BY name").fetchall()
    conn.close()
    if not formula:
        return redirect('/formulas')
    return render_template('formula.html', formula=formula, materials=materials, ifra_categories=IFRA_CATEGORIES)

@app.route('/formula/<int:id>/print')
@login_required
def formula_print(id):
    conn = get_db()
    formula = conn.execute("SELECT * FROM formulas WHERE id=?", (id,)).fetchone()
    if not formula:
        conn.close()
        return redirect('/formulas')
    notes = conn.execute(
        "SELECT * FROM formula_notes WHERE formula_id=? ORDER BY created_at DESC",
        (id,)
    ).fetchall()
    company = conn.execute("SELECT * FROM company_info WHERE id=1").fetchone()
    conn.close()
    cat_key = formula['ifra_category'] or 'cat4'
    cat = next((c for c in IFRA_CATEGORIES if c['id'] == cat_key), None)
    return render_template(
        'formula_print.html',
        formula=formula,
        notes=notes,
        company=company,
        category_name=(cat['name'] if cat else ''),
        category_desc=(cat['desc'] if cat else ''),
        today=datetime.now().strftime('%Y-%m-%d')
    )

@app.route('/production')
@login_required
def production():
    conn = get_db()
    formulas = conn.execute("SELECT id, name FROM formulas ORDER BY name").fetchall()
    conn.close()
    return render_template('production.html', formulas=formulas)

# ===== المذكرات (Notebook) =====
@app.route('/notebook')
@login_required
def notebook():
    return render_template('notebook.html')

@app.route('/api/notebook/entries', methods=['GET', 'POST'])
@login_required
def api_notebook_entries():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('''
            SELECT id, title, category, tags, body, profile, created_at, updated_at
            FROM notebook_entries ORDER BY updated_at DESC
        ''').fetchall()
        conn.close()
        return jsonify({'success': True, 'data': [dict(r) for r in rows]})

    action = request.form.get('action', 'create')

    if action == 'create':
        title = request.form.get('title', '')
        category = request.form.get('category', 'idea')
        tags = request.form.get('tags', '')
        body = request.form.get('body', '')
        profile = request.form.get('profile', '{}')
        cur = conn.execute('''
            INSERT INTO notebook_entries (title, category, tags, body, profile)
            VALUES (?, ?, ?, ?, ?)
        ''', (title, category, tags, body, profile))
        new_id = cur.lastrowid
        conn.commit()
        row = conn.execute('SELECT * FROM notebook_entries WHERE id=?', (new_id,)).fetchone()
        conn.close()
        return jsonify({'success': True, 'data': dict(row)})

    if action == 'update':
        eid = request.form.get('id')
        fields = []
        params = []
        for col in ('title', 'category', 'tags', 'body', 'profile'):
            if col in request.form:
                fields.append(f"{col}=?")
                params.append(request.form.get(col))
        if fields:
            fields.append("updated_at=CURRENT_TIMESTAMP")
            params.append(eid)
            conn.execute(f"UPDATE notebook_entries SET {', '.join(fields)} WHERE id=?", params)
            conn.commit()
        conn.close()
        return jsonify({'success': True})

    if action == 'delete':
        eid = request.form.get('id')
        conn.execute('DELETE FROM notebook_entries WHERE id=?', (eid,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'تم الحذف'})

    if action == 'duplicate':
        eid = request.form.get('id')
        src = conn.execute('SELECT * FROM notebook_entries WHERE id=?', (eid,)).fetchone()
        if not src:
            conn.close()
            return jsonify({'success': False, 'message': 'غير موجودة'})
        cur = conn.execute('''
            INSERT INTO notebook_entries (title, category, tags, body, profile)
            VALUES (?, ?, ?, ?, ?)
        ''', ((src['title'] or '') + ' (نسخة)', src['category'], src['tags'], src['body'], src['profile']))
        new_id = cur.lastrowid
        conn.commit()
        row = conn.execute('SELECT * FROM notebook_entries WHERE id=?', (new_id,)).fetchone()
        conn.close()
        return jsonify({'success': True, 'data': dict(row)})

    conn.close()
    return jsonify({'success': False, 'message': 'إجراء غير معروف'}), 400

@app.route('/calculator')
@login_required
def calculator():
    conn = get_db()
    materials = conn.execute("SELECT * FROM materials ORDER BY name").fetchall()
    conn.close()
    return render_template('calculator.html', materials=materials)

@app.route('/suppliers')
@login_required
def suppliers():
    return render_template('suppliers.html')

# ===== صفحات التقارير =====
@app.route('/ifra-certificate')
@login_required
def ifra_certificate():
    conn = get_db()
    formulas = conn.execute("SELECT id, name FROM formulas ORDER BY name").fetchall()
    conn.close()
    return render_template('ifra_certificate.html', formulas=formulas, categories=IFRA_CATEGORIES)

@app.route('/msds-generator')
@login_required
def msds_generator():
    conn = get_db()
    formulas = conn.execute("SELECT id, name FROM formulas ORDER BY name").fetchall()
    materials = conn.execute("SELECT id, name FROM materials ORDER BY name").fetchall()
    company = conn.execute("SELECT * FROM company_info WHERE id=1").fetchone()
    conn.close()
    return render_template('msds_generator.html', formulas=formulas, materials=materials, company=company,
                          h_codes=GHS_H_CODES, p_codes=GHS_P_CODES, pictograms=GHS_PICTOGRAMS,
                          signal_words=GHS_SIGNAL_WORDS, classifications=GHS_CLASSIFICATIONS)

@app.route('/settings')
@login_required
def settings():
    conn = get_db()
    company = conn.execute("SELECT * FROM company_info WHERE id=1").fetchone()
    conn.close()
    return render_template('settings.html', company=company)

# ===== Scentree Data Lookup =====
@app.route('/api/scentree-lookup', methods=['GET'])
@login_required
def scentree_lookup():
    """Fetch perfumery data from Scentree.co using material name or CAS"""
    import urllib.request
    import urllib.parse

    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': False, 'message': 'Material name or CAS required'})

    result = {}
    try:
        # Step 1: Search via autocomplete
        url = f"https://www.scentree.co/sliced-names-autocomplete?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            ac_data = json.loads(resp.read().decode())

        results = ac_data.get('results', [])
        if not results:
            return jsonify({'success': False, 'message': f'"{query}" not found on Scentree'})

        # Find first published, known result
        match = None
        for r in results:
            if r.get('is_published') and not r.get('is_unknown'):
                match = r
                break
        if not match:
            match = results[0]

        page_url = match.get('url_en', '')
        if not page_url:
            return jsonify({'success': False, 'message': 'No page URL found'})

        # Basic info from autocomplete
        result['name'] = (match.get('name', {}).get('text', '') or '').replace('\u00ae', '').replace('\u2122', '').strip()
        syn_text = match.get('synonyms', {}).get('text', '') or ''
        if syn_text:
            result['synonyms'] = syn_text.replace(' ; ', '; ')
        cas_text = match.get('cas_number', {}).get('text', '') or ''
        if cas_text:
            result['cas_number'] = cas_text

        # Step 2: Fetch the ingredient page
        encoded_page = urllib.parse.quote(page_url, safe='/.html')
        full_url = f"https://www.scentree.co/en/{encoded_page}"
        req2 = urllib.request.Request(full_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            html = resp2.read().decode('utf-8', errors='replace')

        # Olfactive family path (e.g., "Floral > Fresh Flowers > Zesty > Rosy")
        olf_m = re.search(r'textorange-dark[^>]*>([^<]+)<', html)
        if olf_m:
            result['olfactive_family'] = olf_m.group(1).replace('&gt;', '>').strip()

        # Extract label/value pairs
        def extract_field(label_pattern):
            pattern = rf'{label_pattern}[^<]*</span>\s*(?:</h3>\s*)?<span[^>]*label-info[^>]*>([^<]+)<'
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val and 'indisponible' not in val.lower():
                    return val
            return ''

        # General info
        vol = extract_field('Volatility')
        if vol:
            result['profile'] = vol  # Head/Heart/Base

        # Physical properties
        density = extract_field('Density')
        if density:
            result['specific_gravity'] = _extract_number(density)

        ri = extract_field('Refractive Index')
        if ri:
            result['refractive_index'] = _extract_number(ri)

        fp = extract_field('Flash Point')
        if fp:
            result['flash_point'] = _extract_celsius(fp)

        bp = extract_field('Boiling Point')
        if bp:
            result['boiling_point'] = _extract_celsius(bp)

        mp = extract_field('Fusion Point')
        if mp:
            result['melting_point'] = _extract_celsius(mp)

        vp = extract_field('Vapor pressure')
        if vp:
            result['vapor_pressure'] = _extract_number(vp)

        mw = extract_field('Molecular Weight')
        if mw:
            result['molecular_weight'] = _extract_number(mw)

        logp = extract_field('Log P')
        if logp:
            result['logp'] = _extract_number(logp)

        appear = extract_field('Appearance')
        if appear:
            result['appearance'] = appear

        # Uses in perfumery (longer text block)
        uses_m = re.search(r'Uses in perfumery\s*:?\s*</span>\s*</h3>\s*<p[^>]*label-info[^>]*>(.+?)</p>', html, re.DOTALL | re.IGNORECASE)
        if uses_m:
            uses_text = re.sub(r'<[^>]+>', '', uses_m.group(1)).strip()
            if uses_text and 'indisponible' not in uses_text.lower():
                result['uses_in_perfumery'] = uses_text

        # Kind of ingredient (synthetic/natural) from dataLayer
        kind_m = re.search(r"kind_of_ingredient['\"]?\s*:\s*['\"](\w+)['\"]", html)
        if kind_m:
            result['kind'] = kind_m.group(1)

        result['source_url'] = full_url

        if len(result) <= 2:
            return jsonify({'success': False, 'message': f'No detailed data found for "{query}"'})

        return jsonify({'success': True, 'data': result})

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return jsonify({'success': False, 'message': f'"{query}" not found on Scentree'})
        return jsonify({'success': False, 'message': f'HTTP error: {e.code}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

# ===== Perfumery Data Lookup (The Good Scents Company) =====
@app.route('/api/tgsc-lookup', methods=['GET'])
@login_required
def tgsc_lookup():
    """Fetch perfumery data from The Good Scents Company using CAS number"""
    import urllib.request
    import urllib.parse

    cas = request.args.get('cas', '').strip()
    if not cas:
        return jsonify({'success': False, 'message': 'CAS number required'})

    result = {}
    try:
        # Step 1: Search by CAS number
        search_data = urllib.parse.urlencode({'qName': cas}).encode()
        req = urllib.request.Request(
            'https://www.thegoodscentscompany.com/search.php',
            data=search_data,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            search_html = resp.read().decode('utf-8', errors='replace')

        # Find link - TGSC uses openMainWindow('data/XX123.html') where XX = rw, es, tl, etc.
        data_match = re.search(r"openMainWindow\('(data/[a-z]+\d+\.html)'\)", search_html)
        if not data_match:
            return jsonify({'success': False, 'message': f'CAS {cas} not found on The Good Scents Company'})

        data_url = 'https://www.thegoodscentscompany.com/' + data_match.group(1)

        # Step 2: Fetch the ingredient page
        req2 = urllib.request.Request(data_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            page_html = resp2.read().decode('utf-8', errors='replace')

        # Clean HTML entities
        page_html = page_html.replace('&#176;', '°').replace('&deg;', '°')

        # Odor Type - single cell: class="qinfr2">Odor Type: floral</td>
        odor_type_m = re.search(r'Odor Type:\s*([^<]+)</td>', page_html, re.IGNORECASE)
        if odor_type_m:
            result['odor_type'] = odor_type_m.group(1).strip()

        # Odor Strength - class="radw5">Odor Strength:<span>medium</span>
        odor_str_m = re.search(r'Odor Strength:<span>([^<]*)</span>', page_html, re.IGNORECASE)
        if odor_str_m:
            result['strength_odor'] = odor_str_m.group(1).strip()

        # Odor Description - multiple rows, get first meaningful one
        odor_descs = re.findall(r'Odor Description:<span>[^<]*</span>\s*(?:<span>)?([^<]+)', page_html, re.IGNORECASE)
        for desc in odor_descs:
            clean = desc.strip()
            if clean and len(clean) > 3 and 'at ' not in clean[:5]:
                result['odor_description'] = clean
                break

        # Two-cell properties: <td class="radw4">Label:</td><td class="radw11">value</td>
        def extract_two_cell(label):
            pattern = rf'{label}:</td>\s*<td[^>]*radw11[^>]*>\s*([^<]+)'
            m = re.search(pattern, page_html, re.IGNORECASE)
            return m.group(1).strip() if m else ''

        sg = extract_two_cell('Specific Gravity')
        if sg:
            result['specific_gravity'] = _extract_number(sg)

        ri = extract_two_cell('Refractive Index')
        if ri:
            result['refractive_index'] = _extract_number(ri)

        fp = extract_two_cell('Flash Point')
        if fp:
            result['flash_point'] = _extract_celsius(fp)

        bp = extract_two_cell('Boiling Point')
        if bp:
            result['boiling_point'] = _extract_celsius(bp)

        mp = extract_two_cell('Melting Point')
        if mp:
            result['melting_point'] = _extract_celsius(mp)

        logp = extract_two_cell('logP')
        if logp:
            result['logp'] = _extract_number(logp)

        appear = extract_two_cell('Appearance')
        if appear:
            result['appearance'] = appear

        solub = extract_two_cell('Solubility')
        if solub:
            result['solubility'] = solub

        result['source_url'] = data_url

        if not result or len(result) <= 1:
            return jsonify({'success': False, 'message': f'No perfumery data found for CAS {cas}'})

        return jsonify({'success': True, 'data': result})

    except urllib.error.HTTPError as e:
        return jsonify({'success': False, 'message': f'HTTP error: {e.code}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

# ===== CAS Lookup API =====
def _extract_celsius(text):
    """Extract numeric value in Celsius from PubChem text like '232 °F (111.11 °C)' or '111 °C'"""
    if not text:
        return ''
    # Try to find Celsius value in parentheses like (111.11 °C)
    m = re.search(r'\(?\s*(-?[\d.]+)\s*°?\s*C\s*\)?', text)
    if m:
        return m.group(1) + ' °C'
    # If only Fahrenheit, convert
    m = re.search(r'(-?[\d.]+)\s*°?\s*F', text)
    if m:
        f_val = float(m.group(1))
        c_val = round((f_val - 32) * 5 / 9, 1)
        return str(c_val) + ' °C'
    # Try plain number
    m = re.search(r'(-?[\d.]+)', text)
    if m:
        return m.group(1)
    return text

def _extract_number(text):
    """Extract just the first numeric value from text"""
    if not text:
        return ''
    m = re.search(r'(-?[\d.]+)', text)
    return m.group(1) if m else text

@app.route('/api/cas-lookup', methods=['GET'])
@login_required
def cas_lookup():
    """Fetch material data from PubChem using CAS number"""
    import urllib.request
    import urllib.parse
    cas = request.args.get('cas', '').strip()
    if not cas:
        return jsonify({'success': False, 'message': 'CAS number required'})

    result = {}
    try:
        # Step 1: Get CID from CAS number
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(cas)}/cids/JSON"
        req = urllib.request.Request(url, headers={'User-Agent': 'PerfumeVault/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        cid = data['IdentifierList']['CID'][0]

        # Step 2: Get compound properties
        props = 'MolecularFormula,MolecularWeight,IUPACName,ExactMass'
        url2 = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/{props}/JSON"
        req2 = urllib.request.Request(url2, headers={'User-Agent': 'PerfumeVault/1.0'})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            props_data = json.loads(resp2.read().decode())

        if props_data.get('PropertyTable', {}).get('Properties'):
            p = props_data['PropertyTable']['Properties'][0]
            result['molecular_formula'] = p.get('MolecularFormula', '')
            result['molecular_weight'] = p.get('MolecularWeight', '')
            result['iupac_name'] = p.get('IUPACName', '')

        # Step 3: Get synonyms
        url3 = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
        req3 = urllib.request.Request(url3, headers={'User-Agent': 'PerfumeVault/1.0'})
        with urllib.request.urlopen(req3, timeout=10) as resp3:
            syn_data = json.loads(resp3.read().decode())

        syns = syn_data.get('InformationList', {}).get('Information', [{}])[0].get('Synonym', [])
        result['synonyms'] = '; '.join(syns[:10])

        # Step 4: Get experimental properties
        url4 = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=Experimental+Properties"
        req4 = urllib.request.Request(url4, headers={'User-Agent': 'PerfumeVault/1.0'})
        try:
            with urllib.request.urlopen(req4, timeout=15) as resp4:
                exp_data = json.loads(resp4.read().decode())

            sections = exp_data.get('Record', {}).get('Section', [])
            for sec in sections:
                for subsec in sec.get('Section', []):
                    for item in subsec.get('Section', []):
                        heading = item.get('TOCHeading', '')
                        infos = item.get('Information', [])
                        val = ''
                        if infos:
                            sv = infos[0].get('Value', {}).get('StringWithMarkup', [{}])
                            if sv:
                                val = sv[0].get('String', '')
                            else:
                                nv = infos[0].get('Value', {}).get('Number', [])
                                unit = infos[0].get('Value', {}).get('Unit', '')
                                if nv:
                                    val = f"{nv[0]} {unit}".strip()

                        if not val:
                            continue
                        h = heading.lower()
                        if 'boiling' in h:
                            result['boiling_point'] = _extract_celsius(val)
                        elif 'melting' in h:
                            result['melting_point'] = _extract_celsius(val)
                        elif 'flash' in h:
                            result['flash_point'] = _extract_celsius(val)
                        elif 'density' in h or 'specific gravity' in h:
                            result['specific_gravity'] = _extract_number(val)
                        elif 'refractive' in h:
                            result['refractive_index'] = _extract_number(val)
                        elif 'color' in h or 'colour' in h:
                            result['color'] = val
                        elif 'physical' in h or 'appearance' in h:
                            result['appearance'] = val
                        elif 'solubility' in h:
                            result['solubility'] = val
                        elif 'vapor pressure' in h:
                            result['vapor_pressure'] = _extract_number(val) + ' mmHg' if re.search(r'[\d.]', val) else val
                        elif 'vapor density' in h:
                            result['vapor_density'] = _extract_number(val)
                        elif 'odor' in h or 'smell' in h:
                            result['odor_description'] = val
                        elif 'ph' == h.strip():
                            result['ph'] = _extract_number(val)
        except:
            pass

        result['cid'] = cid
        result['pubchem_url'] = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
        return jsonify({'success': True, 'data': result})

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return jsonify({'success': False, 'message': f'CAS {cas} not found in PubChem'})
        return jsonify({'success': False, 'message': f'PubChem error: {e.code}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

# ===== MSDS/GHS Lookup API =====
# Map PubChem GHS pictogram codes to our pictogram names
_GHS_PICTO_MAP = {
    'GHS01': 'Explosive',
    'GHS02': 'Flammable',
    'GHS03': 'Oxidizing',
    'GHS04': 'Compressed Gas',
    'GHS05': 'Corrosive',
    'GHS06': 'Toxic',
    'GHS07': 'Irritant',
    'GHS08': 'Health Hazard',
    'GHS09': 'Environmentally Damaging',
}

# Map H-code ranges to GHS classifications
def _h_codes_to_classifications(h_codes):
    classes = set()
    for code in h_codes:
        num = int(re.search(r'\d+', code).group()) if re.search(r'\d+', code) else 0
        if 200 <= num <= 205: classes.add('Explosive')
        elif 220 <= num <= 228: classes.add('Flammable')
        elif 270 <= num <= 272: classes.add('Oxidizing')
        elif 280 <= num <= 282: classes.add('Compressed Gas')
        elif 290 <= num <= 290: classes.add('Corrosive')
        elif 300 <= num <= 312: classes.add('Toxic')
        elif 314 <= num <= 318: classes.add('Corrosive')
        elif 315 <= num <= 317: classes.add('Irritant')
        elif 319 <= num <= 319: classes.add('Irritant')
        elif 330 <= num <= 336: classes.add('Toxic')
        elif 340 <= num <= 373: classes.add('Health Hazard')
        elif 400 <= num <= 413: classes.add('Environmentally Damaging')
    return list(classes)

@app.route('/api/msds-lookup', methods=['GET'])
@login_required
def msds_lookup():
    """Fetch GHS/MSDS data from PubChem using CAS number"""
    import urllib.request
    import urllib.parse
    cas = request.args.get('cas', '').strip()
    if not cas:
        return jsonify({'success': False, 'message': 'CAS number required'})

    result = {'h_codes': [], 'p_codes': [], 'pictograms': [], 'signal_word': '', 'classifications': []}
    try:
        # Step 1: Get CID from CAS
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(cas)}/cids/JSON"
        req = urllib.request.Request(url, headers={'User-Agent': 'PerfumeVault/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        cid = data['IdentifierList']['CID'][0]

        # Step 2: Get GHS data from pug_view
        url2 = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=GHS+Classification"
        req2 = urllib.request.Request(url2, headers={'User-Agent': 'PerfumeVault/1.0'})
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            ghs_data = json.loads(resp2.read().decode())

        h_codes_found = set()
        p_codes_found = set()
        pictos_found = set()
        signal_words_found = set()

        # Parse sections recursively
        def parse_section(sec):
            for info in sec.get('Information', []):
                info_name = (info.get('Name') or '').lower()
                val = info.get('Value', {})

                for sv in val.get('StringWithMarkup', []):
                    text = sv.get('String', '')

                    # Signal word - PubChem uses Name="Signal"
                    if info_name == 'signal':
                        if 'danger' in text.lower():
                            signal_words_found.add('Danger')
                        elif 'warning' in text.lower():
                            signal_words_found.add('Warning')

                    # Extract H-codes
                    for m in re.finditer(r'H\d{3}[A-Za-z]?', text):
                        h_codes_found.add(m.group())
                    # Extract P-codes
                    for m in re.finditer(r'P\d{3}', text):
                        p_codes_found.add(m.group())

                    # Pictogram URLs/extras contain GHS01-GHS09
                    for markup in sv.get('Markup', []):
                        extra = (markup.get('Extra', '') + ' ' + markup.get('URL', ''))
                        for m in re.finditer(r'GHS\d{2}', extra):
                            code = m.group()
                            if code in _GHS_PICTO_MAP:
                                pictos_found.add(_GHS_PICTO_MAP[code])

            for child in sec.get('Section', []):
                parse_section(child)

        for sec in ghs_data.get('Record', {}).get('Section', []):
            parse_section(sec)

        # Valid H-codes (only keep ones that exist in our system)
        valid_h = {h['code'] for h in GHS_H_CODES}
        valid_p = {p['code'] for p in GHS_P_CODES}

        result['h_codes'] = sorted([c for c in h_codes_found if c in valid_h])
        result['p_codes'] = sorted([c for c in p_codes_found if c in valid_p])
        result['pictograms'] = sorted(list(pictos_found))
        result['signal_word'] = 'Danger' if 'Danger' in signal_words_found else ('Warning' if 'Warning' in signal_words_found else '')
        result['classifications'] = _h_codes_to_classifications(result['h_codes'])

        total = len(result['h_codes']) + len(result['p_codes']) + len(result['pictograms']) + (1 if result['signal_word'] else 0)
        if total == 0:
            return jsonify({'success': False, 'message': f'لا توجد بيانات GHS لـ CAS {cas} في PubChem'})

        return jsonify({'success': True, 'data': result})

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return jsonify({'success': False, 'message': f'لا توجد بيانات GHS لـ CAS {cas} في PubChem'})
        return jsonify({'success': False, 'message': f'PubChem error: {e.code}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

# ===== IFRA Standards API =====
# IFRA_CATEGORIES already defined at top of file (line 34) as list of dicts

@app.route('/api/ifra/lookup', methods=['GET'])
@login_required
def api_ifra_lookup():
    """Get IFRA standard for a material by CAS number"""
    cas = request.args.get('cas', '').strip()
    if not cas:
        return jsonify({'success': False, 'message': 'CAS required'})

    conn = get_db()
    row = conn.execute('''
        SELECT s.* FROM ifra_standards s
        JOIN ifra_cas_lookup l ON l.ifra_standard_id = s.id
        WHERE l.cas_number = ?
    ''', (cas,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'success': False, 'message': f'No IFRA standard found for CAS {cas}'})

    data = dict(row)
    return jsonify({'success': True, 'data': data})

@app.route('/api/ifra/categories')
@login_required
def api_ifra_categories():
    """Get list of IFRA categories"""
    return jsonify({'success': True, 'categories': IFRA_CATEGORIES})

@app.route('/contributions-test')
@login_required
def contributions_test():
    return render_template('contributions_test.html')

@app.route('/api/ifra/contributions-calc/<int:fid>', methods=['GET'])
@login_required
def api_ifra_contributions_calc(fid):
    """Calculate effective IFRA limits for materials based on their constituent contributions"""
    conn = get_db()

    formula = conn.execute("SELECT * FROM formulas WHERE id=?", (fid,)).fetchone()
    if not formula:
        conn.close()
        return jsonify({'success': False, 'message': 'Formula not found'})

    cat_key = formula['ifra_category'] or 'cat4'

    ingredients = conn.execute('''
        SELECT fi.*, m.name, m.cas_number, m.ifra_limit
        FROM formula_ingredients fi
        JOIN materials m ON fi.material_id = m.id
        WHERE fi.formula_id = ?
    ''', (fid,)).fetchall()

    material_limits = {}

    for i in ingredients:
        cas = i['cas_number'] or ''
        if not cas:
            continue

        contribs = conn.execute(
            'SELECT * FROM ifra_contributions WHERE ncs_cas = ?', (cas,)
        ).fetchall()

        if not contribs:
            continue

        details = []
        min_derived_limit = None
        limiting_constituent = None
        limiting_name = None

        for c in contribs:
            c_cas = c['constituent_cas']
            conc_pct = c['concentration_pct']

            # Look up IFRA limit for the constituent
            row = conn.execute('''
                SELECT s.* FROM ifra_standards s
                JOIN ifra_cas_lookup l ON l.ifra_standard_id = s.id
                WHERE l.cas_number = ?
            ''', (c_cas,)).fetchone()

            constituent_ifra_limit = None
            derived_limit = None

            if row:
                cat_val = row[cat_key]
                if cat_val is not None:
                    if cat_val == 0:
                        # Constituent is prohibited → material effectively prohibited
                        derived_limit = 0
                        constituent_ifra_limit = 0
                    elif cat_val > 0:
                        constituent_ifra_limit = cat_val
                        # Effective limit = constituent limit / (concentration / 100)
                        if conc_pct > 0:
                            derived_limit = cat_val / (conc_pct / 100)
                    # cat_val == -1 means no restriction, skip

            details.append({
                'constituent_cas': c_cas,
                'constituent_name': c['constituent_name'],
                'concentration_pct': conc_pct,
                'constituent_ifra_limit': constituent_ifra_limit,
                'derived_limit': derived_limit,
            })

            if derived_limit is not None:
                if min_derived_limit is None or derived_limit < min_derived_limit:
                    min_derived_limit = derived_limit
                    limiting_constituent = c_cas
                    limiting_name = c['constituent_name']

        material_limits[cas] = {
            'ncs_name': i['name'],
            'effective_limit': round(min_derived_limit, 6) if min_derived_limit is not None else None,
            'limiting_constituent': limiting_constituent,
            'limiting_constituent_name': limiting_name,
            'details': details,
        }

    conn.close()
    return jsonify({
        'success': True,
        'category': cat_key,
        'material_limits': material_limits,
    })

@app.route('/api/ifra/formula-check/<int:fid>', methods=['GET'])
@login_required
def api_ifra_formula_check(fid):
    """Check IFRA compliance for a formula - sums grouped materials"""
    conn = get_db()

    formula = conn.execute("SELECT * FROM formulas WHERE id=?", (fid,)).fetchone()
    if not formula:
        conn.close()
        return jsonify({'success': False, 'message': 'Formula not found'})

    cat_key = formula['ifra_category'] or 'cat4'

    # Get all ingredients with their materials
    ingredients = conn.execute('''
        SELECT fi.*, m.name, m.cas_number, m.ifra_limit
        FROM formula_ingredients fi
        JOIN materials m ON fi.material_id = m.id
        WHERE fi.formula_id = ?
    ''', (fid,)).fetchall()

    total_weight = sum(i['weight'] for i in ingredients)
    if total_weight == 0:
        conn.close()
        return jsonify({'success': True, 'results': [], 'total_weight': 0})

    # For each ingredient, find IFRA limit for the selected category
    results = []
    warnings = []

    for i in ingredients:
        cas = i['cas_number'] or ''
        conc = get_concentration(i['dilution'])
        pure_weight = i['weight'] * conc
        weight_pct = (i['weight'] / total_weight * 100) if total_weight > 0 else 0
        pure_pct = (pure_weight / sum(ing['weight'] * get_concentration(ing['dilution']) for ing in ingredients) * 100) if total_weight > 0 else 0

        # Get IFRA limit for this category
        ifra_data = None
        ifra_limit = None
        if cas:
            row = conn.execute('''
                SELECT s.* FROM ifra_standards s
                JOIN ifra_cas_lookup l ON l.ifra_standard_id = s.id
                WHERE l.cas_number = ?
            ''', (cas,)).fetchone()
            if row:
                ifra_data = dict(row)
                cat_val = row[cat_key]
                if cat_val is not None:
                    if cat_val == -1:
                        ifra_limit = None  # No restriction
                    elif cat_val == 0:
                        ifra_limit = 0  # Prohibited
                    else:
                        ifra_limit = cat_val

        # Fallback to manual ifra_limit if no IFRA standard found
        if ifra_limit is None and ifra_data is None and i['ifra_limit']:
            ifra_limit = i['ifra_limit']

        exceeded = False
        if ifra_limit is not None and ifra_limit >= 0:
            if ifra_limit == 0:
                exceeded = True  # Prohibited
            elif weight_pct > ifra_limit:
                exceeded = True

        result_item = {
            'material_name': i['name'],
            'cas_number': cas,
            'weight_pct': round(weight_pct, 4),
            'pure_pct': round(pure_pct, 4),
            'ifra_limit': ifra_limit,
            'ifra_type': ifra_data['standard_type'] if ifra_data else None,
            'ifra_key': ifra_data['ifra_key'] if ifra_data else None,
            'exceeded': exceeded,
            'no_restriction': (ifra_data and ifra_data.get(cat_key) == -1) if ifra_data else False,
        }
        results.append(result_item)

        if exceeded:
            if ifra_limit == 0:
                warnings.append(f"⛔ {i['name']}: PROHIBITED in {cat_key}")
            else:
                warnings.append(f"⚠️ {i['name']}: {weight_pct:.4f}% exceeds IFRA limit {ifra_limit}%")

    # === Contributions from other sources ===
    # For each ingredient, check if it contains restricted IFRA constituents
    # (from naturals or Schiff bases), sum contributions per constituent, check limits
    contribution_map = {}  # constituent_cas -> {name, sources: [{material, ncs_cas, contributed_pct}], total_pct, ifra_limit, exceeded}

    for i in ingredients:
        cas = i['cas_number'] or ''
        if not cas:
            continue

        weight_pct = (i['weight'] / total_weight * 100) if total_weight > 0 else 0

        # Look up contributions where this material's CAS matches ncs_cas
        contribs = conn.execute('''
            SELECT * FROM ifra_contributions WHERE ncs_cas = ?
        ''', (cas,)).fetchall()

        for c in contribs:
            c_cas = c['constituent_cas']
            contributed_pct = weight_pct * c['concentration_pct'] / 100

            if c_cas not in contribution_map:
                contribution_map[c_cas] = {
                    'constituent_name': c['constituent_name'],
                    'constituent_cas': c_cas,
                    'sources': [],
                    'total_pct': 0,
                    'ifra_limit': None,
                    'exceeded': False,
                    'no_restriction': False,
                }

            contribution_map[c_cas]['sources'].append({
                'material_name': i['name'],
                'ncs_cas': cas,
                'ncs_name': c['ncs_name'],
                'source_type': c['source_type'],
                'concentration_in_ncs': c['concentration_pct'],
                'material_pct_in_formula': round(weight_pct, 4),
                'contributed_pct': round(contributed_pct, 6),
            })
            contribution_map[c_cas]['total_pct'] += contributed_pct

    # Now check IFRA limits for each contributed constituent
    contribution_results = []
    for c_cas, data in contribution_map.items():
        # Also add any direct usage of this constituent from Layer 1
        for r in results:
            if r['cas_number'] == c_cas:
                data['total_pct'] += r['weight_pct']
                data['sources'].insert(0, {
                    'material_name': r['material_name'],
                    'ncs_cas': c_cas,
                    'ncs_name': r['material_name'],
                    'source_type': 'direct',
                    'concentration_in_ncs': 100,
                    'material_pct_in_formula': r['weight_pct'],
                    'contributed_pct': r['weight_pct'],
                })
                break

        data['total_pct'] = round(data['total_pct'], 6)

        # Look up IFRA limit for the constituent
        row = conn.execute('''
            SELECT s.* FROM ifra_standards s
            JOIN ifra_cas_lookup l ON l.ifra_standard_id = s.id
            WHERE l.cas_number = ?
        ''', (c_cas,)).fetchone()

        if row:
            cat_val = row[cat_key]
            if cat_val is not None:
                if cat_val == -1:
                    data['ifra_limit'] = None
                    data['no_restriction'] = True
                elif cat_val == 0:
                    data['ifra_limit'] = 0
                    data['exceeded'] = True
                else:
                    data['ifra_limit'] = cat_val
                    if data['total_pct'] > cat_val:
                        data['exceeded'] = True

        if data['exceeded']:
            if data['ifra_limit'] == 0:
                warnings.append(f"⛔ {data['constituent_name']} (from contributions): PROHIBITED in {cat_key}")
            else:
                warnings.append(f"⚠️ {data['constituent_name']} (from contributions): {data['total_pct']:.4f}% exceeds IFRA limit {data['ifra_limit']}%")

        contribution_results.append(data)

    conn.close()
    return jsonify({
        'success': True,
        'category': cat_key,
        'results': results,
        'contributions': contribution_results,
        'warnings': warnings,
        'total_weight': total_weight
    })

# ===== API المواد =====
@app.route('/api/materials', methods=['GET', 'POST'])
@login_required
def api_materials():
    conn = get_db()
    
    if request.method == 'GET':
        action = request.args.get('action', 'list')
        if action == 'list':
            data = conn.execute('''
                SELECT m.*, f.name as family_name, f.icon as family_icon, s.name as supplier_name
                FROM materials m
                LEFT JOIN families f ON m.family_id = f.id
                LEFT JOIN suppliers s ON m.supplier_id = s.id
                ORDER BY m.name
            ''').fetchall()
            # جلب البروفايل العطري لكل مادة
            olfactive_data = conn.execute("SELECT * FROM material_olfactive").fetchall()
            olf_map = {row['material_id']: {cat: row[cat] or 0 for cat in OLFACTIVE_CATEGORIES} for row in olfactive_data}
            result = []
            for d in data:
                item = dict(d)
                item['olfactive'] = olf_map.get(item['id'], None)
                result.append(item)
            conn.close()
            return jsonify({'success': True, 'data': result})
        elif action == 'get':
            mid = request.args.get('id')
            data = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
            msds = conn.execute("SELECT * FROM material_msds WHERE material_id=?", (mid,)).fetchone()
            olfactive = conn.execute("SELECT * FROM material_olfactive WHERE material_id=?", (mid,)).fetchone()
            result = dict(data) if data else None
            if result and msds:
                result['msds'] = dict(msds)
            if result:
                # Parse manual_ifra_cats JSON into an object for the client
                try:
                    result['manual_ifra_cats'] = json.loads(result.get('manual_ifra_cats') or '{}') or {}
                except Exception:
                    result['manual_ifra_cats'] = {}
                if olfactive:
                    result['olfactive'] = {cat: dict(olfactive).get(cat, 0) or 0 for cat in OLFACTIVE_CATEGORIES}
                else:
                    result['olfactive'] = {cat: 0 for cat in OLFACTIVE_CATEGORIES}
                # IFRA standard data
                if result.get('cas_number'):
                    ifra_row = conn.execute('''
                        SELECT s.* FROM ifra_standards s
                        JOIN ifra_cas_lookup l ON l.ifra_standard_id = s.id
                        WHERE l.cas_number = ?
                    ''', (result['cas_number'],)).fetchone()
                    if ifra_row:
                        result['ifra_standard'] = dict(ifra_row)
            conn.close()
            return jsonify({'success': True, 'data': result})
    
    elif request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save':
            try:
                id = request.form.get('id')
                price = float(request.form.get('purchase_price') or 0)
                qty = float(request.form.get('purchase_quantity') or 1)
                ppg = price / qty if qty > 0 else 0
                name = request.form.get('name')

                # Collect per-category manual IFRA values into a JSON blob.
                # Any field whose name starts with "manual_ifra_" and has a
                # positive value goes into the dict; empty fields are dropped
                # so the column stores only what the user actually overrode.
                manual_cats = {}
                for c in IFRA_CATEGORIES:
                    raw = request.form.get(f"manual_ifra_{c['id']}", '').strip()
                    if raw:
                        try:
                            val = float(raw)
                            if val > 0:
                                manual_cats[c['id']] = val
                        except ValueError:
                            pass
                manual_cats_json = json.dumps(manual_cats) if manual_cats else None

                if id and id != '':
                    conn.execute('''UPDATE materials SET name=?, name_ar=?, cas_number=?, family_id=?,
                        profile=?, supplier_id=?, ifra_limit=?, manual_ifra_cats=?, purchase_price=?, purchase_quantity=?,
                        price_per_gram=?, odor_description=?, notes=?, flash_point=?, specific_gravity=?,
                        color=?, physical_state=?, ph=?, melting_point=?, boiling_point=?,
                        solubility=?, vapor_density=?, appearance=?, refractive_index=?,
                        synonyms=?, lot=?, strength_odor=?, vapor_pressure=?,
                        effect=?, recommended_smell_pct=?, properties=?, in_stock=? WHERE id=?''',
                        (name, request.form.get('name_ar'), request.form.get('cas_number'),
                         request.form.get('family_id') or None, request.form.get('profile', 'Heart'),
                         request.form.get('supplier_id') or None, request.form.get('ifra_limit') or None,
                         manual_cats_json,
                         price, qty, ppg, request.form.get('odor_description'), request.form.get('notes'),
                         request.form.get('flash_point'), request.form.get('specific_gravity'),
                         request.form.get('color'), request.form.get('physical_state'),
                         request.form.get('ph'), request.form.get('melting_point'),
                         request.form.get('boiling_point'), request.form.get('solubility'),
                         request.form.get('vapor_density'), request.form.get('appearance'),
                         request.form.get('refractive_index'),
                         request.form.get('synonyms'), request.form.get('lot'),
                         request.form.get('strength_odor'), request.form.get('vapor_pressure'),
                         request.form.get('effect'), request.form.get('recommended_smell_pct'),
                         request.form.get('properties'),
                         float(request.form.get('in_stock') or 0), id))
                    mat_id = id
                    msg = 'تم التحديث'
                else:
                    cur = conn.execute('''INSERT INTO materials (name, name_ar, cas_number, family_id, profile,
                        supplier_id, ifra_limit, manual_ifra_cats, purchase_price, purchase_quantity, price_per_gram,
                        odor_description, notes, flash_point, specific_gravity, color, physical_state,
                        ph, melting_point, boiling_point, solubility, vapor_density, appearance, refractive_index,
                        synonyms, lot, strength_odor, vapor_pressure, effect, recommended_smell_pct, properties, in_stock)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (name, request.form.get('name_ar'), request.form.get('cas_number'),
                         request.form.get('family_id') or None, request.form.get('profile', 'Heart'),
                         request.form.get('supplier_id') or None, request.form.get('ifra_limit') or None,
                         manual_cats_json,
                         price, qty, ppg, request.form.get('odor_description'), request.form.get('notes'),
                         request.form.get('flash_point'), request.form.get('specific_gravity'),
                         request.form.get('color'), request.form.get('physical_state'),
                         request.form.get('ph'), request.form.get('melting_point'),
                         request.form.get('boiling_point'), request.form.get('solubility'),
                         request.form.get('vapor_density'), request.form.get('appearance'),
                         request.form.get('refractive_index'),
                         request.form.get('synonyms'), request.form.get('lot'),
                         request.form.get('strength_odor'), request.form.get('vapor_pressure'),
                         request.form.get('effect'), request.form.get('recommended_smell_pct'),
                         request.form.get('properties'),
                         float(request.form.get('in_stock') or 0)))
                    mat_id = cur.lastrowid
                    msg = f'تم الإضافة (ID: {mat_id})'
                
                # حفظ بيانات MSDS
                h_codes = request.form.get('h_codes', '')
                p_codes = request.form.get('p_codes', '')
                pictograms = request.form.get('pictograms', '')
                signal_word = request.form.get('signal_word', '')
                ghs_classification = request.form.get('ghs_classification', '')
                
                conn.execute("""INSERT OR REPLACE INTO material_msds
                    (material_id, h_codes, p_codes, pictograms, signal_word, ghs_classification)
                    VALUES (?,?,?,?,?,?)""",
                    (mat_id, h_codes, p_codes, pictograms, signal_word, ghs_classification))

                # حفظ البروفايل العطري
                olf_values = {cat: int(request.form.get(f'olf_{cat}', 0) or 0) for cat in OLFACTIVE_CATEGORIES}
                conn.execute("""INSERT OR REPLACE INTO material_olfactive
                    (material_id, citrus, aldehydic, aromatic, green, marine, floral, fruity,
                     spicy, balsamic, woody, ambery, musky, leathery, animal)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (mat_id, *[olf_values[cat] for cat in OLFACTIVE_CATEGORIES]))

                conn.commit()
                conn.close()
                return jsonify({'success': True, 'message': msg})
            except Exception as e:
                log(f"[ERROR] {e}")
                conn.close()
                return jsonify({'success': False, 'message': str(e)})
        
        elif action == 'delete':
            id = request.form.get('id')
            used = conn.execute("SELECT COUNT(*) FROM formula_ingredients WHERE material_id=?", (id,)).fetchone()[0]
            if used > 0:
                conn.close()
                return jsonify({'success': False, 'message': f'مستخدمة في {used} تركيبة'})
            conn.execute("DELETE FROM material_msds WHERE material_id=?", (id,))
            conn.execute("DELETE FROM material_olfactive WHERE material_id=?", (id,))
            conn.execute("DELETE FROM materials WHERE id=?", (id,))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحذف'})

        elif action == 'delete_all_unused':
            # Delete every material that is not referenced by any formula_ingredients row.
            unused_ids = [r[0] for r in conn.execute("""
                SELECT m.id FROM materials m
                WHERE NOT EXISTS (
                    SELECT 1 FROM formula_ingredients fi WHERE fi.material_id = m.id
                )
            """).fetchall()]
            total = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
            skipped = total - len(unused_ids)
            if unused_ids:
                placeholders = ','.join('?' * len(unused_ids))
                conn.execute(f"DELETE FROM material_msds WHERE material_id IN ({placeholders})", unused_ids)
                conn.execute(f"DELETE FROM material_olfactive WHERE material_id IN ({placeholders})", unused_ids)
                conn.execute(f"DELETE FROM materials WHERE id IN ({placeholders})", unused_ids)
                conn.commit()
            conn.close()
            msg = f'تم حذف {len(unused_ids)} مادة'
            if skipped:
                msg += f' (تم تخطي {skipped} مستخدمة في تركيبات)'
            return jsonify({'success': True, 'message': msg, 'deleted': len(unused_ids), 'skipped': skipped})
    
    conn.close()
    return jsonify({'success': False})

# ===== API التصنيف العطري التلقائي =====
@app.route('/api/olfactive/auto-classify', methods=['POST'])
@login_required
def api_auto_classify():
    description = request.form.get('description', '')
    scores = auto_classify_odor(description)
    return jsonify({'success': True, 'scores': scores})

# ===== API التركيبات =====
@app.route('/api/formulas', methods=['GET', 'POST'])
@login_required
def api_formulas():
    conn = get_db()

    if request.method == 'GET':
        try:
            data = conn.execute('''
                SELECT f.*, COUNT(fi.id) as ingredients_count,
                       COALESCE(SUM(fi.weight), 0) as total_weight
                FROM formulas f
                LEFT JOIN formula_ingredients fi ON f.id = fi.formula_id
                GROUP BY f.id ORDER BY f.created_at DESC
            ''').fetchall()

            result = []
            for f in data:
                total_cost = conn.execute('''
                    SELECT COALESCE(SUM(fi.weight * m.price_per_gram), 0)
                    FROM formula_ingredients fi
                    JOIN materials m ON fi.material_id = m.id
                    WHERE fi.formula_id = ?
                ''', (f['id'],)).fetchone()[0]

                # Get ingredient names
                ingredients = conn.execute('''
                    SELECT m.name FROM formula_ingredients fi
                    JOIN materials m ON fi.material_id = m.id
                    WHERE fi.formula_id = ?
                ''', (f['id'],)).fetchall()
                ingredient_names = [i['name'] for i in ingredients]

                # Calculate olfactive profile
                olf_cats = ['citrus','aldehydic','aromatic','green','marine','floral','fruity','spicy','balsamic','woody','ambery','musky','leathery','animal']
                olf_profile = {}
                fi_rows = conn.execute('''
                    SELECT fi.weight, fi.dilution, fi.material_id
                    FROM formula_ingredients fi
                    WHERE fi.formula_id = ?
                ''', (f['id'],)).fetchall()
                total_pure = sum((row['weight'] * (row['dilution'] or 1)) for row in fi_rows)
                if total_pure > 0:
                    for cat in olf_cats:
                        val = 0
                        for row in fi_rows:
                            olf = conn.execute('SELECT * FROM material_olfactive WHERE material_id=?',
                                (row['material_id'],)).fetchone()
                            if olf and olf[cat]:
                                pure_w = row['weight'] * (row['dilution'] or 1)
                                val += olf[cat] * (pure_w / total_pure)
                        olf_profile[cat] = round(val, 1)

                r = dict(f)
                r['total_cost'] = total_cost
                r['ingredient_names'] = ingredient_names
                r['olfactive_profile'] = olf_profile
                result.append(r)

            conn.close()
            return jsonify({'success': True, 'data': result})
        except Exception as e:
            conn.close()
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    
    elif request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            cur = conn.execute("INSERT INTO formulas (name, description, ifra_category) VALUES (?,?,?)",
                (request.form.get('name'), request.form.get('description'), request.form.get('ifra_category', 'cat4')))
            conn.commit()
            fid = cur.lastrowid
            conn.close()
            return jsonify({'success': True, 'message': 'تم الإنشاء', 'id': fid})
        
        elif action == 'delete':
            id = request.form.get('id')
            # Delete draft ingredients first
            draft_ids = [d['id'] for d in conn.execute("SELECT id FROM formula_drafts WHERE formula_id=?", (id,)).fetchall()]
            for did in draft_ids:
                conn.execute("DELETE FROM draft_ingredients WHERE draft_id=?", (did,))
            conn.execute("DELETE FROM formula_drafts WHERE formula_id=?", (id,))
            conn.execute("DELETE FROM formula_ingredients WHERE formula_id=?", (id,))
            conn.execute("DELETE FROM formulas WHERE id=?", (id,))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحذف'})
        
        elif action == 'duplicate':
            id = request.form.get('id')
            f = conn.execute("SELECT * FROM formulas WHERE id=?", (id,)).fetchone()
            if f:
                cur = conn.execute("INSERT INTO formulas (name, description, ifra_category) VALUES (?,?,?)",
                    (f['name'] + ' (نسخة)', f['description'], f['ifra_category']))
                new_id = cur.lastrowid
                for i in conn.execute("SELECT * FROM formula_ingredients WHERE formula_id=?", (id,)).fetchall():
                    conn.execute("""INSERT INTO formula_ingredients 
                        (formula_id, material_id, weight, dilution, diluent, diluent_other) 
                        VALUES (?,?,?,?,?,?)""",
                        (new_id, i['material_id'], i['weight'], i['dilution'], 
                         i['diluent'] if 'diluent' in i.keys() else '', 
                         i['diluent_other'] if 'diluent_other' in i.keys() else ''))
                conn.commit()
                conn.close()
                return jsonify({'success': True, 'message': 'تم النسخ', 'id': new_id})
    
    conn.close()
    return jsonify({'success': False})

# ===== API مكونات التركيبة =====
@app.route('/api/formula/<int:fid>/ingredients', methods=['GET', 'POST'])
@login_required
def api_formula_ingredients(fid):
    conn = get_db()
    
    if request.method == 'GET':
        # Get formula's IFRA category
        formula = conn.execute("SELECT ifra_category FROM formulas WHERE id=?", (fid,)).fetchone()
        cat_key = formula['ifra_category'] or 'cat4' if formula else 'cat4'

        data = conn.execute('''
            SELECT fi.*, m.name, m.name_ar, m.cas_number, m.ifra_limit, m.manual_ifra_cats,
                   m.price_per_gram, m.profile
            FROM formula_ingredients fi
            JOIN materials m ON fi.material_id = m.id
            WHERE fi.formula_id = ?
        ''', (fid,)).fetchall()

        # الحسابات مطابقة للإكسل:
        # G = وزن الزيت (weight)
        # E = التخفيف (dilution) - 1=صافي، 0.1=10%
        # I = وزن صافي = G × E
        # H = نسبة الزيت = G / ΣG
        # J = نسبة الصافي = I / ΣI
        # N = F / H (حساب IFRA للتصميم)
        # L = F / J (حساب IFRA النهائي)

        total_weight = sum(i['weight'] for i in data)  # ΣG
        total_pure = sum(i['weight'] * get_concentration(i['dilution']) for i in data)  # ΣI

        # J2 = نسبة المادة الفعالة = ΣI / ΣG × 100
        active_ratio = (total_pure / total_weight * 100) if total_weight > 0 else 0

        # حساب N و L لكل مادة أولاً
        temp_results = []
        n_values = []  # قيم N للمواد التي لها IFRA
        l_values = []  # قيم L للمواد التي لها IFRA

        for i in data:
            conc = get_concentration(i['dilution'])  # E
            pure_weight = i['weight'] * conc  # I = G × E
            weight_pct = (i['weight'] / total_weight) if total_weight > 0 else 0  # H (كنسبة 0-1)
            pure_pct = (pure_weight / total_pure) if total_pure > 0 else 0  # J (كنسبة 0-1)

            # F - IFRA limit lookup, priority order:
            #   1. manual_ifra_cats[cat_key]      — per-category manual value
            #   2. materials.ifra_limit           — blanket manual (all cats)
            #   3. IFRA standards table by CAS + category
            #   4. IFRA contributions (derived from constituents of naturals)
            ifra_limit = 0
            ifra_std_name = None
            ifra_std_type = None
            cas = i['cas_number'] or ''
            ifra_contrib_name = None

            # Per-category manual (JSON column on materials)
            manual_cats_raw = i['manual_ifra_cats'] if 'manual_ifra_cats' in i.keys() else None
            manual_cat_value = None
            if manual_cats_raw:
                try:
                    manual_cats = json.loads(manual_cats_raw) or {}
                    v = manual_cats.get(cat_key)
                    if v is not None and v != '' and float(v) > 0:
                        manual_cat_value = float(v)
                except Exception:
                    pass

            manual_mat_ifra = (i['ifra_limit'] or 0)
            if manual_cat_value is not None:
                ifra_limit = manual_cat_value
                ifra_std_name = f'Manual ({cat_key})'
                ifra_std_type = 'manual_category'
            elif manual_mat_ifra > 0:
                # Blanket manual IFRA (all categories) overrides the standards lookup.
                ifra_limit = manual_mat_ifra
                ifra_std_name = 'Manual (material)'
                ifra_std_type = 'manual_material'
            elif cas:
                ifra_row = conn.execute('''
                    SELECT s.* FROM ifra_standards s
                    JOIN ifra_cas_lookup l ON l.ifra_standard_id = s.id
                    WHERE l.cas_number = ?
                ''', (cas,)).fetchone()
                if ifra_row:
                    cat_val = ifra_row[cat_key]
                    ifra_std_name = ifra_row['name']
                    ifra_std_type = ifra_row['standard_type']
                    if cat_val is not None:
                        if cat_val == -1:
                            ifra_limit = -1  # No restriction
                        elif cat_val == 0:
                            ifra_limit = 0  # Prohibited
                        else:
                            ifra_limit = cat_val
                # No direct IFRA standard — derive from contributions (constituents inside naturals/Schiff bases)
                if ifra_limit == 0 and ifra_std_name is None:
                    contribs = conn.execute(
                        'SELECT * FROM ifra_contributions WHERE ncs_cas = ?', (cas,)
                    ).fetchall()
                    min_derived = None
                    for c in contribs:
                        c_row = conn.execute('''
                            SELECT s.* FROM ifra_standards s
                            JOIN ifra_cas_lookup l ON l.ifra_standard_id = s.id
                            WHERE l.cas_number = ?
                        ''', (c['constituent_cas'],)).fetchone()
                        if c_row:
                            c_val = c_row[cat_key]
                            if c_val is not None and c_val >= 0 and c['concentration_pct'] > 0:
                                if c_val == 0:
                                    derived = 0
                                else:
                                    derived = c_val / (c['concentration_pct'] / 100)
                                if min_derived is None or derived < min_derived:
                                    min_derived = derived
                                    ifra_contrib_name = c['constituent_name']
                    if min_derived is not None:
                        ifra_limit = round(min_derived, 6)
                        ifra_std_name = f"Contrib: {ifra_contrib_name}"
                        ifra_std_type = 'contribution'

            # Per-ingredient IFRA override (highest priority)
            ifra_override = i['ifra_override'] if 'ifra_override' in i.keys() and i['ifra_override'] is not None else None
            if ifra_override is not None:
                ifra_limit = ifra_override
                ifra_std_name = ifra_std_name or 'Manual'
                ifra_std_type = 'override'

            # For calculations, treat -1 (no restriction) as no limit
            calc_limit = ifra_limit if ifra_limit > 0 else 0

            # N = F / H (للتصميم)
            ifra_design_calc = (calc_limit / weight_pct) if (calc_limit > 0 and weight_pct > 0) else None
            if ifra_design_calc is not None:
                n_values.append(ifra_design_calc)

            # L = F / J (النهائي)
            ifra_final_calc = (calc_limit / pure_pct) if (calc_limit > 0 and pure_pct > 0) else None
            if ifra_final_calc is not None:
                l_values.append(ifra_final_calc)

            # Get constituents for this material
            constituents = []
            if cas:
                const_rows = conn.execute(
                    'SELECT constituent_name, constituent_cas, concentration_pct FROM ifra_contributions WHERE ncs_cas = ?', (cas,)
                ).fetchall()
                for cr in const_rows:
                    constituents.append({
                        'name': cr['constituent_name'],
                        'cas': cr['constituent_cas'],
                        'pct': cr['concentration_pct']
                    })

            temp_results.append({
                'data': i,
                'conc': conc,
                'pure_weight': pure_weight,
                'weight_pct': weight_pct,
                'pure_pct': pure_pct,
                'ifra_limit': ifra_limit,
                'constituents': constituents,
                'ifra_std_name': ifra_std_name,
                'ifra_std_type': ifra_std_type,
                'ifra_design_calc': ifra_design_calc,
                'ifra_final_calc': ifra_final_calc
            })
        
        # N3 = MIN(N) × 0.99 (حد IFRA للتصميم)
        ifra_design_limit = min(n_values) * 0.99 if n_values else 0
        
        # E3 = MIN(L) × 0.99 (حد IFRA النهائي)
        ifra_final_limit = min(l_values) * 0.99 if l_values else 0
        
        # الآن نحدد التجاوز ونبني النتيجة النهائية
        result = []
        for t in temp_results:
            i = t['data']
            
            # M = تجاوز إذا نسبة الزيت (H%) أكبر من حد IFRA (F%)
            ifra_design_exceeded = False
            if t['ifra_limit'] is not None and t['ifra_limit'] > 0:
                ifra_design_exceeded = (t['weight_pct'] * 100) > t['ifra_limit']

            # K = تجاوز إذا نسبة الصافي (J%) أكبر من حد IFRA (F%)
            ifra_final_exceeded = False
            if t['ifra_limit'] is not None and t['ifra_limit'] > 0:
                ifra_final_exceeded = (t['pure_pct'] * 100) > t['ifra_limit']
            
            result.append({
                **dict(i),
                'concentration': t['conc'],
                'pure_weight': t['pure_weight'],
                'weight_percentage': t['weight_pct'] * 100,  # H بالنسبة المئوية
                'percentage': t['pure_pct'] * 100,  # J بالنسبة المئوية
                'ifra_cat_limit': t['ifra_limit'],  # F from IFRA standards (category-specific)
                'ifra_std_name': t.get('ifra_std_name'),
                'ifra_std_type': t.get('ifra_std_type'),
                'ifra_design_calc': t['ifra_design_calc'],  # N
                'ifra_design_exceeded': ifra_design_exceeded,  # M
                'ifra_final_calc': t['ifra_final_calc'],  # L
                'ifra_final_exceeded': ifra_final_exceeded,  # K
                'constituents': t.get('constituents', []),
                'cost': i['weight'] * (i['price_per_gram'] or 0)
            })
        
        # === IFRA Contributions from other sources ===
        contribution_map = {}
        for t in temp_results:
            cas = t['data']['cas_number'] or ''
            if not cas:
                continue
            weight_pct_100 = t['weight_pct'] * 100  # H as percentage

            contribs = conn.execute(
                'SELECT * FROM ifra_contributions WHERE ncs_cas = ?', (cas,)
            ).fetchall()

            for c in contribs:
                c_cas = c['constituent_cas']
                contributed_pct = weight_pct_100 * c['concentration_pct'] / 100

                if c_cas not in contribution_map:
                    contribution_map[c_cas] = {
                        'constituent_name': c['constituent_name'],
                        'constituent_cas': c_cas,
                        'sources': [],
                        'total_pct': 0,
                        'ifra_limit': None,
                        'exceeded': False,
                        'no_restriction': False,
                    }

                contribution_map[c_cas]['sources'].append({
                    'material_name': t['data']['name'],
                    'ncs_name': c['ncs_name'],
                    'source_type': c['source_type'],
                    'concentration_in_ncs': c['concentration_pct'],
                    'material_pct_in_formula': round(weight_pct_100, 4),
                    'contributed_pct': round(contributed_pct, 6),
                })
                contribution_map[c_cas]['total_pct'] += contributed_pct

        # Check IFRA limits for each contributed constituent
        contribution_warnings = []
        contribution_results = []
        for c_cas, cdata in contribution_map.items():
            # Add direct usage if this constituent is also used directly
            for r in result:
                if r.get('cas_number') == c_cas:
                    cdata['total_pct'] += r.get('weight_percentage', 0)
                    cdata['sources'].insert(0, {
                        'material_name': r['name'],
                        'ncs_name': r['name'],
                        'source_type': 'direct',
                        'concentration_in_ncs': 100,
                        'material_pct_in_formula': r.get('weight_percentage', 0),
                        'contributed_pct': r.get('weight_percentage', 0),
                    })
                    break

            cdata['total_pct'] = round(cdata['total_pct'], 6)

            row = conn.execute('''
                SELECT s.* FROM ifra_standards s
                JOIN ifra_cas_lookup l ON l.ifra_standard_id = s.id
                WHERE l.cas_number = ?
            ''', (c_cas,)).fetchone()

            if row:
                cat_val = row[cat_key]
                if cat_val is not None:
                    if cat_val == -1:
                        cdata['ifra_limit'] = None
                        cdata['no_restriction'] = True
                    elif cat_val == 0:
                        cdata['ifra_limit'] = 0
                        cdata['exceeded'] = True
                    else:
                        cdata['ifra_limit'] = cat_val
                        if cdata['total_pct'] > cat_val:
                            cdata['exceeded'] = True

            if cdata['exceeded']:
                if cdata['ifra_limit'] == 0:
                    contribution_warnings.append(f"⛔ {cdata['constituent_name']}: PROHIBITED in {cat_key}")
                else:
                    contribution_warnings.append(f"⚠️ {cdata['constituent_name']}: {cdata['total_pct']:.4f}% exceeds IFRA limit {cdata['ifra_limit']}%")

            contribution_results.append(cdata)

        # Calculate combined olfactive profile
        olf_cats = ['citrus','aldehydic','aromatic','green','marine','floral','fruity','spicy','balsamic','woody','ambery','musky','leathery','animal']
        formula_olfactive = {c: 0 for c in olf_cats}
        for t in temp_results:
            mat_id = t['data']['material_id']
            olf = conn.execute("SELECT * FROM material_olfactive WHERE material_id=?", (mat_id,)).fetchone()
            if olf:
                pct = t['pure_pct']  # J (0-1)
                for c in olf_cats:
                    formula_olfactive[c] += (olf[c] or 0) * pct
        # Round values
        for c in olf_cats:
            formula_olfactive[c] = round(formula_olfactive[c], 1)

        conn.close()
        return jsonify({
            'success': True,
            'data': result,
            'total_weight': total_weight,
            'total_pure': total_pure,
            'active_ratio': active_ratio,  # J2 محسوب
            'ifra_category': cat_key,
            'ifra_design_limit': ifra_design_limit,  # N3 محسوب
            'ifra_final_limit': ifra_final_limit,  # E3 محسوب
            'olfactive_profile': formula_olfactive,
            'contributions': contribution_results,
            'contribution_warnings': contribution_warnings
        })

    elif request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            mid = request.form.get('material_id')
            exists = conn.execute("SELECT id FROM formula_ingredients WHERE formula_id=? AND material_id=?", (fid, mid)).fetchone()
            if exists:
                conn.close()
                return jsonify({'success': False, 'message': 'موجود مسبقاً'})
            dilution = float(request.form.get('dilution', 0))
            diluent = request.form.get('diluent', '')
            diluent_other = request.form.get('diluent_other', '')
            conn.execute("""INSERT INTO formula_ingredients 
                (formula_id, material_id, weight, dilution, diluent, diluent_other) 
                VALUES (?,?,?,?,?,?)""",
                (fid, mid, request.form.get('weight', 0), dilution, diluent, diluent_other))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الإضافة'})
        
        elif action == 'update':
            dilution = float(request.form.get('dilution', 0))
            diluent = request.form.get('diluent', '')
            diluent_other = request.form.get('diluent_other', '')
            ifra_ov = request.form.get('ifra_override', '')
            ifra_override = float(ifra_ov) if ifra_ov and ifra_ov.strip() else None
            conn.execute("""UPDATE formula_ingredients
                SET weight=?, dilution=?, diluent=?, diluent_other=?, ifra_override=?
                WHERE id=?""",
                (request.form.get('weight'), dilution, diluent, diluent_other, ifra_override, request.form.get('ing_id')))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        
        elif action == 'delete':
            conn.execute("DELETE FROM formula_ingredients WHERE id=?", (request.form.get('ing_id'),))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحذف'})

        elif action == 'delete_all':
            cur = conn.execute("DELETE FROM formula_ingredients WHERE formula_id=?", (fid,))
            affected = cur.rowcount
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': f'تم حذف {affected} مادة', 'affected': affected})

        elif action == 'reset_ifra':
            # Clear all manual ifra_override values for this formula, reverting to standard IFRA limits
            cur = conn.execute(
                "UPDATE formula_ingredients SET ifra_override=NULL WHERE formula_id=? AND ifra_override IS NOT NULL",
                (fid,))
            affected = cur.rowcount
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': f'تم إعادة ضبط {affected} قيمة IFRA', 'affected': affected})
        
        elif action == 'update_formula':
            conn.execute("""UPDATE formulas SET name=?, description=?, status=?, ifra_category=?,
                target_audience=?, age_group=?, gender=?, season=?, occasion=?, scent_type=?, review_notes=?
                WHERE id=?""",
                (request.form.get('name'), request.form.get('description'),
                 request.form.get('status'), request.form.get('ifra_category'),
                 request.form.get('target_audience', ''), request.form.get('age_group', ''),
                 request.form.get('gender', ''), request.form.get('season', ''),
                 request.form.get('occasion', ''), request.form.get('scent_type', ''),
                 request.form.get('review_notes', ''), fid))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحفظ'})
        
        elif action == 'scale':
            target = float(request.form.get('target_weight', 0))
            data = conn.execute('''SELECT fi.*, m.name, m.price_per_gram FROM formula_ingredients fi
                JOIN materials m ON fi.material_id = m.id WHERE fi.formula_id = ?''', (fid,)).fetchall()
            total = sum(i['weight'] for i in data)
            if total <= 0:
                conn.close()
                return jsonify({'success': False, 'message': 'فارغة'})
            factor = target / total
            result = []
            cost = 0
            for i in data:
                w = i['weight'] * factor
                c = w * (i['price_per_gram'] or 0)
                cost += c
                result.append({'name': i['name'], 'original': i['weight'], 'scaled': round(w, 4), 'cost': round(c, 2)})
            conn.close()
            return jsonify({'success': True, 'data': result, 'factor': factor, 'total_cost': cost})
    
    conn.close()
    return jsonify({'success': False})

# ===== API ملاحظات التركيبة =====
@app.route('/api/formula/<int:fid>/notes', methods=['GET', 'POST'])
@login_required
def api_formula_notes(fid):
    conn = get_db()
    if request.method == 'GET':
        notes = conn.execute("SELECT * FROM formula_notes WHERE formula_id=? ORDER BY created_at DESC", (fid,)).fetchall()
        conn.close()
        return jsonify({'success': True, 'data': [dict(n) for n in notes]})
    elif request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            if not title:
                conn.close()
                return jsonify({'success': False, 'message': 'العنوان مطلوب'})
            conn.execute("INSERT INTO formula_notes (formula_id, title, content) VALUES (?,?,?)", (fid, title, content))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم إضافة الملاحظة'})
        elif action == 'delete':
            conn.execute("DELETE FROM formula_notes WHERE id=? AND formula_id=?", (request.form.get('id'), fid))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحذف'})
    conn.close()
    return jsonify({'success': False})

# ===== API مسودات التركيبة =====
@app.route('/api/formula/<int:fid>/drafts', methods=['GET', 'POST'])
@login_required
def api_formula_drafts(fid):
    conn = get_db()

    if request.method == 'GET':
        drafts = conn.execute("""
            SELECT fd.*, COUNT(di.id) as ingredients_count
            FROM formula_drafts fd
            LEFT JOIN draft_ingredients di ON di.draft_id = fd.id
            WHERE fd.formula_id = ?
            GROUP BY fd.id
            ORDER BY fd.draft_number ASC
        """, (fid,)).fetchall()
        conn.close()
        return jsonify({'success': True, 'data': [dict(d) for d in drafts]})

    elif request.method == 'POST':
        action = request.form.get('action')

        if action == 'save':
            # Get next draft number
            last = conn.execute("SELECT MAX(draft_number) as mx FROM formula_drafts WHERE formula_id=?", (fid,)).fetchone()
            next_num = (last['mx'] or 0) + 1
            draft_name = request.form.get('name', '').strip() or f'Draft {next_num}'
            draft_notes = request.form.get('notes', '').strip()

            # Create draft record
            cur = conn.execute("INSERT INTO formula_drafts (formula_id, draft_number, name, notes) VALUES (?,?,?,?)",
                (fid, next_num, draft_name, draft_notes))
            draft_id = cur.lastrowid

            # Copy current ingredients to draft
            ingredients = conn.execute("SELECT * FROM formula_ingredients WHERE formula_id=?", (fid,)).fetchall()
            for ing in ingredients:
                conn.execute("""INSERT INTO draft_ingredients
                    (draft_id, material_id, weight, dilution, diluent, diluent_other, notes, ifra_override)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (draft_id, ing['material_id'], ing['weight'], ing['dilution'],
                     ing['diluent'] if 'diluent' in ing.keys() else '',
                     ing['diluent_other'] if 'diluent_other' in ing.keys() else '',
                     ing['notes'] if 'notes' in ing.keys() else '',
                     ing['ifra_override'] if 'ifra_override' in ing.keys() and ing['ifra_override'] is not None else None))

            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': f'تم حفظ {draft_name}', 'draft_id': draft_id, 'draft_number': next_num})

        elif action == 'load':
            draft_id = request.form.get('draft_id')
            draft = conn.execute("SELECT * FROM formula_drafts WHERE id=? AND formula_id=?", (draft_id, fid)).fetchone()
            if not draft:
                conn.close()
                return jsonify({'success': False, 'message': 'المسودة غير مو��ودة'})

            # Clear current ingredients
            conn.execute("DELETE FROM formula_ingredients WHERE formula_id=?", (fid,))

            # Copy draft ingredients back to formula
            draft_ings = conn.execute("SELECT * FROM draft_ingredients WHERE draft_id=?", (draft_id,)).fetchall()
            for di in draft_ings:
                conn.execute("""INSERT INTO formula_ingredients
                    (formula_id, material_id, weight, dilution, diluent, diluent_other, notes, ifra_override)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (fid, di['material_id'], di['weight'], di['dilution'],
                     di['diluent'] or '', di['diluent_other'] or '',
                     di['notes'] or '', di['ifra_override']))

            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': f'تم تحميل {draft["name"]}'})

        elif action == 'delete':
            draft_id = request.form.get('draft_id')
            draft = conn.execute("SELECT * FROM formula_drafts WHERE id=? AND formula_id=?", (draft_id, fid)).fetchone()
            if not draft:
                conn.close()
                return jsonify({'success': False, 'message': 'المسودة غير موجودة'})
            if draft['is_final']:
                conn.close()
                return jsonify({'success': False, 'message': 'لا يمكن حذف المسودة المعتمدة'})
            conn.execute("DELETE FROM draft_ingredients WHERE draft_id=?", (draft_id,))
            conn.execute("DELETE FROM formula_drafts WHERE id=?", (draft_id,))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم ح��ف المسودة'})

        elif action == 'approve':
            draft_id = request.form.get('draft_id')
            draft = conn.execute("SELECT * FROM formula_drafts WHERE id=? AND formula_id=?", (draft_id, fid)).fetchone()
            if not draft:
                conn.close()
                return jsonify({'success': False, 'message': 'ال��سودة غير موجودة'})

            # Remove previous final flag
            conn.execute("UPDATE formula_drafts SET is_final=0 WHERE formula_id=?", (fid,))
            # Set this draft as final
            conn.execute("UPDATE formula_drafts SET is_final=1 WHERE id=?", (draft_id,))
            # Update formula status to final
            conn.execute("UPDATE formulas SET status='final' WHERE id=?", (fid,))

            # Load this draft's ingredients as current
            conn.execute("DELETE FROM formula_ingredients WHERE formula_id=?", (fid,))
            draft_ings = conn.execute("SELECT * FROM draft_ingredients WHERE draft_id=?", (draft_id,)).fetchall()
            for di in draft_ings:
                conn.execute("""INSERT INTO formula_ingredients
                    (formula_id, material_id, weight, dilution, diluent, diluent_other, notes, ifra_override)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (fid, di['material_id'], di['weight'], di['dilution'],
                     di['diluent'] or '', di['diluent_other'] or '',
                     di['notes'] or '', di['ifra_override']))

            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم اعتماد التركيبة النهائية'})

        elif action == 'rename':
            draft_id = request.form.get('draft_id')
            new_name = request.form.get('name', '').strip()
            if not new_name:
                conn.close()
                return jsonify({'success': False, 'message': 'الاسم م��لوب'})
            conn.execute("UPDATE formula_drafts SET name=? WHERE id=? AND formula_id=?", (new_name, draft_id, fid))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم التحديث'})

    conn.close()
    return jsonify({'success': False})

# ===== API تفاصيل المسودة =====
@app.route('/api/draft/<int:draft_id>/ingredients')
@login_required
def api_draft_ingredients(draft_id):
    conn = get_db()
    draft = conn.execute("SELECT * FROM formula_drafts WHERE id=?", (draft_id,)).fetchone()
    if not draft:
        conn.close()
        return jsonify({'success': False, 'message': 'ا��مسودة غير موجودة'})

    data = conn.execute('''
        SELECT di.*, m.name, m.cas_number, m.ifra_limit, m.price_per_gram, m.profile
        FROM draft_ingredients di
        JOIN materials m ON di.material_id = m.id
        WHERE di.draft_id = ?
    ''', (draft_id,)).fetchall()

    result = []
    total_weight = sum(i['weight'] for i in data)
    for i in data:
        conc = i['dilution'] if i['dilution'] and i['dilution'] > 0 else 1
        pure_weight = i['weight'] * conc
        result.append({
            'name': i['name'],
            'cas_number': i['cas_number'],
            'weight': i['weight'],
            'dilution': i['dilution'],
            'diluent': i['diluent'],
            'weight_pct': (i['weight'] / total_weight * 100) if total_weight > 0 else 0,
            'pure_weight': pure_weight,
            'cost': i['weight'] * (i['price_per_gram'] or 0)
        })

    conn.close()
    return jsonify({'success': True, 'data': result, 'total_weight': total_weight})

# ===== API شهادة IFRA =====
@app.route('/api/ifra-certificate/<int:fid>')
@login_required
def api_ifra_certificate(fid):
    conn = get_db()
    formula = conn.execute("SELECT * FROM formulas WHERE id=?", (fid,)).fetchone()
    if not formula:
        conn.close()
        return jsonify({'success': False, 'message': 'التركيبة غير موجودة'})
    if formula['status'] != 'final':
        conn.close()
        return jsonify({'success': False, 'message': 'شهادة IFRA متاحة فقط للتركيبات المعتمدة (Final). اعتمد مسودة أولاً.'})

    ingredients = conn.execute('''
        SELECT fi.*, m.name, m.cas_number, m.ifra_limit
        FROM formula_ingredients fi
        JOIN materials m ON fi.material_id = m.id
        WHERE fi.formula_id = ?
    ''', (fid,)).fetchall()

    total_weight = sum(i['weight'] for i in ingredients)
    total_pure = sum(i['weight'] * get_concentration(i['dilution']) for i in ingredients)

    # Mark which ingredients are IFRA-regulated (match in ifra_standards or manual ifra_limit > 0)
    regulated_ids = set()
    for ing in ingredients:
        cas = ing['cas_number'] or ''
        if cas:
            hit = conn.execute('SELECT 1 FROM ifra_cas_lookup WHERE cas_number = ?', (cas,)).fetchone()
            if hit:
                regulated_ids.add(ing['id'])
                continue
        if ing['ifra_limit'] and ing['ifra_limit'] > 0:
            regulated_ids.add(ing['id'])

    # For each category, check compliance using ifra_standards table
    category_limits = []
    cat_ids = [c['id'] for c in IFRA_CATEGORIES]

    for cat in IFRA_CATEGORIES:
        cat_id = cat['id']
        max_fragrance_pct = None
        restricted_materials = []

        for ing in ingredients:
            cas = ing['cas_number'] or ''
            # Look up IFRA limit for this category from ifra_standards
            ifra_limit_val = None
            if cas:
                ifra_row = conn.execute('''
                    SELECT s.* FROM ifra_standards s
                    JOIN ifra_cas_lookup l ON l.ifra_standard_id = s.id
                    WHERE l.cas_number = ?
                ''', (cas,)).fetchone()
                if ifra_row:
                    cv = ifra_row[cat_id]
                    if cv is not None and cv >= 0:
                        ifra_limit_val = cv
                    elif cv == -1:
                        ifra_limit_val = None  # No restriction for this category

            # Fallback to manual ifra_limit
            if ifra_limit_val is None and not cas:
                if ing['ifra_limit'] and ing['ifra_limit'] > 0:
                    ifra_limit_val = ing['ifra_limit']

            if ifra_limit_val is not None and ifra_limit_val >= 0:
                conc = get_concentration(ing['dilution'])
                pure_weight = ing['weight'] * conc
                pure_pct_in_formula = (pure_weight / total_pure * 100) if total_pure > 0 else 0

                if ifra_limit_val == 0:
                    restricted_materials.append(f"{ing['name']} (PROHIBITED)")
                elif pure_pct_in_formula > 0:
                    # max fragrance % in final product = ifra_limit / pure_pct_in_formula * 100
                    max_frag = (ifra_limit_val / pure_pct_in_formula) * 100
                    # Cap: anything above 100% is effectively no restriction (can't exceed 100% of the product)
                    if max_frag <= 100:
                        if max_fragrance_pct is None or max_frag < max_fragrance_pct:
                            max_fragrance_pct = max_frag

        limit_value = round(max_fragrance_pct, 3) if max_fragrance_pct else None

        category_limits.append({
            'id': cat_id,
            'name': cat['name'],
            'desc': cat['desc'],
            'limit': limit_value if limit_value else 'No Restriction',
            'compliant': len(restricted_materials) == 0,
            'restricted': restricted_materials
        })

    # Return ONLY regulated materials in the composition table
    regulated_ingredients = [dict(i) for i in ingredients if i['id'] in regulated_ids]

    conn.close()
    return jsonify({
        'success': True,
        'formula': dict(formula),
        'ingredients': regulated_ingredients,
        'categories': category_limits,
        'total_weight': total_weight
    })

# ===== API تقرير MSDS =====
@app.route('/api/msds/<int:fid>')
@login_required
def api_msds_report(fid):
    conn = get_db()
    formula = conn.execute("SELECT * FROM formulas WHERE id=?", (fid,)).fetchone()
    if not formula:
        conn.close()
        return jsonify({'success': False, 'message': 'التركيبة غير موجودة'})
    if formula['status'] != 'final':
        conn.close()
        return jsonify({'success': False, 'message': 'تقرير MSDS متاح فقط للتركيبات المعتمدة (Final). اعتمد مسودة أولاً.'})

    company = conn.execute("SELECT * FROM company_info WHERE id=1").fetchone()
    
    ingredients = conn.execute('''
        SELECT fi.*, m.name, m.cas_number, mm.h_codes, mm.p_codes, mm.pictograms, mm.signal_word, mm.ghs_classification
        FROM formula_ingredients fi
        JOIN materials m ON fi.material_id = m.id
        LEFT JOIN material_msds mm ON m.id = mm.material_id
        WHERE fi.formula_id = ?
    ''', (fid,)).fetchall()
    
    total_weight = sum(i['weight'] for i in ingredients)
    
    # جمع كل H-codes و P-codes من المكونات
    all_h_codes = set()
    all_p_codes = set()
    all_pictograms = set()
    signal_words = set()
    
    ingredient_list = []
    for i in ingredients:
        has_ghs = bool((i['h_codes'] and i['h_codes'].strip())
                       or (i['p_codes'] and i['p_codes'].strip())
                       or (i['pictograms'] and i['pictograms'].strip())
                       or (i['signal_word'] and i['signal_word'].strip()))

        if has_ghs:
            pct = (i['weight'] / total_weight * 100) if total_weight > 0 else 0
            ingredient_list.append({
                'name': i['name'],
                'cas_number': i['cas_number'],
                'percentage': round(pct, 2)
            })

        if i['h_codes']:
            for h in i['h_codes'].split(','):
                if h.strip():
                    all_h_codes.add(h.strip())
        if i['p_codes']:
            for p in i['p_codes'].split(','):
                if p.strip():
                    all_p_codes.add(p.strip())
        if i['pictograms']:
            for pic in i['pictograms'].split(','):
                if pic.strip():
                    all_pictograms.add(pic.strip())
        if i['signal_word']:
            signal_words.add(i['signal_word'])
    
    # تحديد Signal Word (الأقوى)
    final_signal_word = 'Danger' if 'Danger' in signal_words else ('Warning' if 'Warning' in signal_words else '')
    
    conn.close()
    return jsonify({
        'success': True,
        'formula': dict(formula),
        'company': dict(company) if company else {},
        'ingredients': ingredient_list,
        'h_codes': list(all_h_codes),
        'p_codes': list(all_p_codes),
        'pictograms': list(all_pictograms),
        'signal_word': final_signal_word,
        'total_weight': total_weight
    })

# ===== API الموردين =====
@app.route('/api/suppliers', methods=['GET', 'POST'])
@login_required
def api_suppliers():
    conn = get_db()
    
    if request.method == 'GET':
        action = request.args.get('action', 'list')
        if action == 'list':
            data = conn.execute('''SELECT s.*, COUNT(m.id) as materials_count FROM suppliers s
                LEFT JOIN materials m ON s.id = m.supplier_id GROUP BY s.id ORDER BY s.name''').fetchall()
            conn.close()
            return jsonify({'success': True, 'data': [dict(d) for d in data]})
        elif action == 'get':
            data = conn.execute("SELECT * FROM suppliers WHERE id=?", (request.args.get('id'),)).fetchone()
            conn.close()
            return jsonify({'success': True, 'data': dict(data) if data else None})
    
    elif request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save':
            id = request.form.get('id')
            data = (request.form.get('name'), request.form.get('country'), request.form.get('email'),
                   request.form.get('phone'), request.form.get('website'), request.form.get('notes'))
            if id and id != '':
                conn.execute("UPDATE suppliers SET name=?, country=?, email=?, phone=?, website=?, notes=? WHERE id=?", (*data, id))
            else:
                conn.execute("INSERT INTO suppliers (name, country, email, phone, website, notes) VALUES (?,?,?,?,?,?)", data)
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحفظ'})
        
        elif action == 'delete':
            id = request.form.get('id')
            used = conn.execute("SELECT COUNT(*) FROM materials WHERE supplier_id=?", (id,)).fetchone()[0]
            if used > 0:
                conn.close()
                return jsonify({'success': False, 'message': f'مرتبط بـ {used} مادة'})
            conn.execute("DELETE FROM suppliers WHERE id=?", (id,))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحذف'})
    
    conn.close()
    return jsonify({'success': False})

# ===== API الإنتاج =====
@app.route('/api/production', methods=['GET', 'POST'])
@login_required
def api_production():
    conn = get_db()
    
    if request.method == 'GET':
        action = request.args.get('action', 'list')
        if action == 'list':
            data = conn.execute('''SELECT po.*, f.name as formula_name FROM production_orders po
                JOIN formulas f ON po.formula_id = f.id ORDER BY po.created_at DESC''').fetchall()
            conn.close()
            return jsonify({'success': True, 'data': [dict(d) for d in data]})
        elif action == 'get':
            o = conn.execute('''SELECT po.*, f.name as formula_name FROM production_orders po
                JOIN formulas f ON po.formula_id = f.id WHERE po.id=?''', (request.args.get('id'),)).fetchone()
            if o:
                items = conn.execute('''SELECT fi.*, m.name, m.cas_number, m.price_per_gram
                    FROM formula_ingredients fi JOIN materials m ON fi.material_id = m.id
                    WHERE fi.formula_id=?''', (o['formula_id'],)).fetchall()
                result = dict(o)
                total = sum(i['weight'] for i in items)
                factor = o['target_quantity'] / total if total > 0 else 1
                result['items'] = [{'name': i['name'], 'cas': i['cas_number'], 
                                   'weight': round(i['weight'] * factor, 4)} for i in items]
                conn.close()
                return jsonify({'success': True, 'data': result})
            conn.close()
            return jsonify({'success': False, 'message': 'غير موجود'})
    
    elif request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            fid = request.form.get('formula_id')
            total = conn.execute("SELECT COALESCE(SUM(weight),0) FROM formula_ingredients WHERE formula_id=?", (fid,)).fetchone()[0]
            target = float(request.form.get('target_quantity', 0))
            factor = target / total if total > 0 else 1
            
            num = f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            conn.execute('''INSERT INTO production_orders (order_number, formula_id, target_quantity, scale_factor, 
                customer_name, batch_number, notes) VALUES (?,?,?,?,?,?,?)''',
                (num, fid, target, factor, request.form.get('customer_name'), 
                 request.form.get('batch_number'), request.form.get('notes')))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': f'تم إنشاء أمر {num}'})
        
        elif action == 'update_status':
            conn.execute("UPDATE production_orders SET status=? WHERE id=?",
                (request.form.get('status'), request.form.get('id')))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        
        elif action == 'delete':
            conn.execute("DELETE FROM production_orders WHERE id=?", (request.form.get('id'),))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحذف'})
    
    conn.close()
    return jsonify({'success': False})

# ===== API الإعدادات =====
@app.route('/api/settings', methods=['POST'])
@login_required
def api_settings():
    conn = get_db()
    action = request.form.get('action')
    
    if action == 'save_company':
        conn.execute('''UPDATE company_info SET name=?, address=?, phone=?, email=?, website=? WHERE id=1''',
            (request.form.get('name'), request.form.get('address'), request.form.get('phone'),
             request.form.get('email'), request.form.get('website')))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'تم الحفظ'})

    elif action == 'create_backup':
        conn.close()
        try:
            name = create_backup('manual')
            return jsonify({'success': True, 'message': f'تم إنشاء النسخة: {name}'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    elif action == 'list_backups':
        conn.close()
        return jsonify({'success': True, 'data': list_backups()})

    elif action == 'restore_backup':
        conn.close()
        filename = request.form.get('filename', '')
        if not filename or '..' in filename or '/' in filename:
            return jsonify({'success': False, 'message': 'Invalid filename'})
        ok, msg = restore_backup(filename)
        return jsonify({'success': ok, 'message': msg})

    elif action == 'delete_backup':
        conn.close()
        filename = request.form.get('filename', '')
        if not filename or '..' in filename or '/' in filename:
            return jsonify({'success': False, 'message': 'Invalid filename'})
        path = os.path.join(BACKUP_DIR, filename)
        if os.path.exists(path):
            os.remove(path)
            return jsonify({'success': True, 'message': 'تم الحذف'})
        return jsonify({'success': False, 'message': 'Not found'})

    conn.close()
    return jsonify({'success': False})

# ===== API بيانات GHS =====
@app.route('/api/ghs-data')
@login_required
def api_ghs_data():
    return jsonify({
        'success': True,
        'h_codes': GHS_H_CODES,
        'p_codes': GHS_P_CODES,
        'pictograms': GHS_PICTOGRAMS,
        'signal_words': GHS_SIGNAL_WORDS,
        'classifications': GHS_CLASSIFICATIONS
    })

# ===== بطاقة التركيبة =====
@app.route('/formula/<int:id>/card')
@login_required
def formula_card(id):
    conn = get_db()
    formula = conn.execute("SELECT * FROM formulas WHERE id=?", (id,)).fetchone()
    if not formula:
        conn.close()
        return redirect('/formulas')
    company = conn.execute("SELECT * FROM company_info WHERE id=1").fetchone()
    conn.close()
    return render_template('formula_card.html', formula=formula, company=company)

@app.route('/api/formula/<int:fid>/card-settings', methods=['POST'])
@login_required
def api_formula_card_settings(fid):
    conn = get_db()
    settings_json = request.form.get('card_settings', '{}')
    conn.execute("UPDATE formulas SET card_settings=? WHERE id=?", (settings_json, fid))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'تم حفظ إعدادات البطاقة'})

@app.route('/api/formula/<int:fid>/card')
@login_required
def api_formula_card(fid):
    conn = get_db()
    formula = conn.execute("SELECT * FROM formulas WHERE id=?", (fid,)).fetchone()
    if not formula:
        conn.close()
        return jsonify({'success': False, 'message': 'التركيبة غير موجودة'})

    ingredients = conn.execute('''
        SELECT fi.*, m.name, m.name_ar, m.cas_number, m.profile, m.odor_description,
               f.name as family_name, f.name_ar as family_name_ar, f.icon as family_icon
        FROM formula_ingredients fi
        JOIN materials m ON fi.material_id = m.id
        LEFT JOIN families f ON m.family_id = f.id
        WHERE fi.formula_id = ?
        ORDER BY m.profile, fi.weight DESC
    ''', (fid,)).fetchall()

    total_weight = sum(i['weight'] for i in ingredients)

    # تجميع العائلات
    families = {}
    for i in ingredients:
        fname = i['family_name'] or 'Other'
        if fname not in families:
            families[fname] = {
                'name': fname,
                'name_ar': i['family_name_ar'] or '',
                'icon': i['family_icon'] or '',
                'total_weight': 0,
                'count': 0
            }
        families[fname]['total_weight'] += i['weight']
        families[fname]['count'] += 1

    family_list = sorted(families.values(), key=lambda x: x['total_weight'], reverse=True)
    for f in family_list:
        f['percentage'] = round((f['total_weight'] / total_weight * 100) if total_weight > 0 else 0, 1)

    # هرم العطر
    pyramid = {'Top': [], 'Heart': [], 'Base': []}
    for i in ingredients:
        profile = i['profile'] or 'Heart'
        if profile not in pyramid:
            profile = 'Heart'
        pyramid[profile].append({
            'name': i['name'],
            'name_ar': i['name_ar'] or '',
            'family_name': i['family_name'] or '',
            'family_name_ar': i['family_name_ar'] or '',
            'family_icon': i['family_icon'] or '',
            'weight': i['weight'],
            'percentage': round((i['weight'] / total_weight * 100) if total_weight > 0 else 0, 1),
            'odor_description': i['odor_description'] or ''
        })

    company = conn.execute("SELECT * FROM company_info WHERE id=1").fetchone()
    all_families = conn.execute("SELECT id, name, name_ar, icon FROM families ORDER BY name_ar").fetchall()
    conn.close()

    # Parse card_settings JSON
    card_settings = {}
    try:
        cs = formula['card_settings'] if 'card_settings' in formula.keys() else ''
        if cs:
            card_settings = json.loads(cs)
    except:
        pass

    return jsonify({
        'success': True,
        'formula': dict(formula),
        'families': family_list,
        'all_families': [dict(f) for f in all_families],
        'pyramid': pyramid,
        'total_weight': total_weight,
        'ingredients_count': len(ingredients),
        'company': dict(company) if company else {},
        'card_settings': card_settings
    })

# ===== Smart Import - قراءة Excel =====
IMPORT_TEMP_DIR = os.path.join(tempfile.gettempdir(), 'perfume_vault_import')
os.makedirs(IMPORT_TEMP_DIR, exist_ok=True)

def read_xlsx_sheets(filepath):
    """قراءة ملف xlsx عبر XML مباشرة (يتجنب مشاكل openpyxl)"""
    zf = zipfile.ZipFile(filepath)
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

    # Shared strings
    shared = []
    try:
        ss_tree = ET.parse(zf.open('xl/sharedStrings.xml'))
        for si in ss_tree.findall('.//s:si', ns):
            parts = []
            for t in si.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'):
                if t.text:
                    parts.append(t.text)
            shared.append(''.join(parts))
    except:
        pass

    # Sheet names + rId mapping
    wb = ET.parse(zf.open('xl/workbook.xml'))
    sheets_info = []
    for s in wb.findall('.//s:sheet', ns):
        sheets_info.append({
            'name': s.get('name'),
            'rId': s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        })

    rels = ET.parse(zf.open('xl/_rels/workbook.xml.rels'))
    rns = {'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    rid_map = {}
    for r in rels.findall('.//r:Relationship', rns):
        rid_map[r.get('Id')] = r.get('Target')

    return zf, ns, shared, sheets_info, rid_map

def read_xlsx_sheet_data(zf, ns, shared, target, max_rows=None):
    """قراءة بيانات شيت معين"""
    filepath_in_zip = 'xl/' + target if not target.startswith('xl/') else target
    sheet_xml = ET.parse(zf.open(filepath_in_zip))
    rows = sheet_xml.findall('.//s:sheetData/s:row', ns)

    # اكتشاف كل الأعمدة المستخدمة
    all_cols = set()
    data = []
    for i, row in enumerate(rows):
        if max_rows and i >= max_rows:
            break
        cells = {}
        for c in row.findall('s:c', ns):
            ref = c.get('r')
            col = re.match(r'([A-Z]+)', ref).group(1)
            all_cols.add(col)
            typ = c.get('t')
            val_el = c.find('s:v', ns)
            if val_el is not None and val_el.text is not None:
                if typ == 's':
                    try:
                        cells[col] = shared[int(val_el.text)]
                    except:
                        cells[col] = val_el.text
                else:
                    cells[col] = val_el.text
            else:
                cells[col] = ''
        data.append(cells)

    sorted_cols = sorted(all_cols, key=lambda c: (len(c), c))
    return data, sorted_cols

def read_csv_data(filepath, max_rows=None):
    """قراءة ملف CSV"""
    import csv
    data = []
    cols = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if max_rows and i >= max_rows:
                break
            if i == 0:
                cols = [f'C{j}' for j in range(len(row))]
            cells = {}
            for j, val in enumerate(row):
                if j < len(cols):
                    cells[cols[j]] = val
            data.append(cells)
    return data, cols

# حقول النظام المتاحة للربط
IMPORT_FIELDS = [
    {'key': 'name', 'label': 'الاسم (English)', 'required': True},
    {'key': 'name_ar', 'label': 'الاسم (العربي)', 'required': False},
    {'key': 'cas_number', 'label': 'CAS Number', 'required': False},
    {'key': 'family', 'label': 'العائلة العطرية', 'required': False},
    {'key': 'profile', 'label': 'الموقع (Top/Heart/Base)', 'required': False},
    {'key': 'supplier', 'label': 'المورد', 'required': False},
    {'key': 'ifra_limit', 'label': 'IFRA Limit (%)', 'required': False},
    {'key': 'purchase_price', 'label': 'سعر الشراء', 'required': False},
    {'key': 'purchase_quantity', 'label': 'الكمية المشتراه', 'required': False},
    {'key': 'odor_description', 'label': 'وصف الرائحة', 'required': False},
    {'key': 'notes', 'label': 'ملاحظات', 'required': False},
    {'key': 'flash_point', 'label': 'Flash Point', 'required': False},
    {'key': 'specific_gravity', 'label': 'Specific Gravity', 'required': False},
    {'key': 'color', 'label': 'اللون', 'required': False},
    {'key': 'appearance', 'label': 'المظهر', 'required': False},
    {'key': 'physical_state', 'label': 'الحالة الفيزيائية', 'required': False},
    {'key': 'synonyms', 'label': 'Synonyms', 'required': False},
    {'key': 'lot', 'label': 'Lot', 'required': False},
    {'key': 'strength_odor', 'label': 'Strength Odor (High/Mid/Low)', 'required': False},
    {'key': 'melting_point', 'label': 'Melting Point', 'required': False},
    {'key': 'boiling_point', 'label': 'Boiling Point', 'required': False},
    {'key': 'refractive_index', 'label': 'Refractive Index', 'required': False},
    {'key': 'solubility', 'label': 'Solubility', 'required': False},
    {'key': 'vapor_density', 'label': 'Vapor Density', 'required': False},
    {'key': 'ph', 'label': 'pH', 'required': False},
    {'key': 'vapor_pressure', 'label': 'Vapor Pressure', 'required': False},
    {'key': 'effect', 'label': 'Effect (High/Mid/Low)', 'required': False},
    {'key': 'recommended_smell_pct', 'label': 'درجة الشم الموصى بها (%)', 'required': False},
    {'key': 'properties', 'label': 'خصائص', 'required': False},
    {'key': 'in_stock', 'label': 'In Stock', 'required': False},
]

@app.route('/import')
@login_required
def import_page():
    return render_template('import.html')

@app.route('/api/import/upload', methods=['POST'])
@login_required
def api_import_upload():
    """رفع ملف واستخراج الشيتات"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'لم يتم اختيار ملف'})

    f = request.files['file']
    if not f.filename:
        return jsonify({'success': False, 'message': 'لم يتم اختيار ملف'})

    ext = f.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('xlsx', 'xls', 'csv'):
        return jsonify({'success': False, 'message': 'الملف لازم يكون xlsx أو csv'})

    # حفظ مؤقت
    file_id = str(uuid.uuid4())
    save_path = os.path.join(IMPORT_TEMP_DIR, f'{file_id}.{ext}')
    f.save(save_path)
    session['import_file'] = save_path
    session['import_ext'] = ext

    if ext == 'csv':
        return jsonify({'success': True, 'file_id': file_id, 'sheets': [{'name': 'CSV Data', 'index': 0}]})

    try:
        zf, ns, shared, sheets_info, rid_map = read_xlsx_sheets(save_path)
        sheets = [{'name': s['name'], 'index': i} for i, s in enumerate(sheets_info)]
        # حفظ معلومات الشيتات
        session['import_sheets'] = json.dumps([{
            'name': s['name'], 'rId': s['rId'], 'target': rid_map.get(s['rId'], '')
        } for s in sheets_info])
        zf.close()
        return jsonify({'success': True, 'file_id': file_id, 'sheets': sheets})
    except Exception as e:
        return jsonify({'success': False, 'message': f'خطأ في قراءة الملف: {str(e)}'})

@app.route('/api/import/columns', methods=['POST'])
@login_required
def api_import_columns():
    """جلب أعمدة الشيت المختار مع عينات"""
    sheet_index = int(request.form.get('sheet_index', 0))
    filepath = session.get('import_file')
    ext = session.get('import_ext', 'xlsx')

    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'ارفع الملف مرة ثانية'})

    try:
        if ext == 'csv':
            all_data, all_cols = read_csv_data(filepath)
            sample_data = all_data[:10]
            cols = all_cols
        else:
            zf, ns, shared, sheets_info, rid_map = read_xlsx_sheets(filepath)
            target = rid_map.get(sheets_info[sheet_index]['rId'], '')
            all_data, cols = read_xlsx_sheet_data(zf, ns, shared, target)
            sample_data = all_data[:10]
            zf.close()

        if not all_data:
            return jsonify({'success': False, 'message': 'الشيت فاضي'})

        # أول صف = headers
        header_row = all_data[0]
        sample_rows = all_data[1:6]  # 5 صفوف عينة

        columns = []
        for col in cols:
            header = str(header_row.get(col, '')).strip()
            samples = [str(r.get(col, '')).strip() for r in sample_rows if r.get(col, '')]
            if header or samples:
                columns.append({
                    'key': col,
                    'header': header,
                    'samples': samples[:3]
                })

        session['import_sheet_index'] = sheet_index
        return jsonify({
            'success': True,
            'columns': columns,
            'fields': IMPORT_FIELDS,
            'total_rows': len(all_data) - 1
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/import/preview', methods=['POST'])
@login_required
def api_import_preview():
    """معاينة البيانات بعد الربط"""
    mapping = json.loads(request.form.get('mapping', '{}'))
    filepath = session.get('import_file')
    ext = session.get('import_ext', 'xlsx')
    sheet_index = session.get('import_sheet_index', 0)

    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'ارفع الملف مرة ثانية'})

    if 'name' not in mapping.values():
        return jsonify({'success': False, 'message': 'لازم تربط حقل "الاسم (English)" على الأقل'})

    try:
        if ext == 'csv':
            data, cols = read_csv_data(filepath)
        else:
            zf, ns, shared, sheets_info, rid_map = read_xlsx_sheets(filepath)
            target = rid_map.get(sheets_info[sheet_index]['rId'], '')
            data, cols = read_xlsx_sheet_data(zf, ns, shared, target)
            zf.close()

        if len(data) < 2:
            return jsonify({'success': False, 'message': 'لا توجد بيانات'})

        # reverse mapping: system_field -> excel_column
        field_to_col = {}
        for excel_col, sys_field in mapping.items():
            if sys_field:
                field_to_col[sys_field] = excel_col

        rows = data[1:]  # skip header
        preview = []
        # Check existing in DB
        conn = get_db()
        existing_names = set()
        existing_cas = set()
        for row in conn.execute("SELECT name, cas_number FROM materials"):
            existing_names.add((row['name'] or '').lower().strip())
            if row['cas_number']:
                existing_cas.add(row['cas_number'].strip())
        conn.close()

        for row in rows[:30]:
            item = {}
            for sys_field, excel_col in field_to_col.items():
                val = str(row.get(excel_col, '')).strip()
                if val and val != '#DIV/0!':
                    item[sys_field] = val
                else:
                    item[sys_field] = ''

            name = item.get('name', '').strip()
            if not name:
                continue

            cas = item.get('cas_number', '').strip()
            item['_exists'] = (name.lower() in existing_names) or (cas and cas in existing_cas)
            preview.append(item)

        total_valid = 0
        total_existing = 0
        for row in rows:
            name = str(row.get(field_to_col.get('name', ''), '')).strip()
            if name:
                total_valid += 1
                cas = str(row.get(field_to_col.get('cas_number', ''), '')).strip()
                if name.lower() in existing_names or (cas and cas in existing_cas):
                    total_existing += 1

        return jsonify({
            'success': True,
            'preview': preview,
            'total_valid': total_valid,
            'total_existing': total_existing,
            'total_new': total_valid - total_existing
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/import/execute', methods=['POST'])
@login_required
def api_import_execute():
    """تنفيذ الاستيراد"""
    mapping = json.loads(request.form.get('mapping', '{}'))
    update_existing = request.form.get('update_existing', 'false') == 'true'
    auto_olfactive = request.form.get('auto_olfactive', 'true') == 'true'

    # Enriched data from client-side CAS lookups
    enriched_raw = request.form.get('enriched_data', '')
    enriched_by_cas = {}
    enriched_by_name = {}
    if enriched_raw:
        try:
            enriched_list = json.loads(enriched_raw)
            for ed in enriched_list:
                cas_key = (ed.get('cas_number') or '').strip()
                name_key = (ed.get('name') or '').strip().lower()
                if cas_key:
                    enriched_by_cas[cas_key] = ed
                if name_key:
                    enriched_by_name[name_key] = ed
        except:
            pass

    filepath = session.get('import_file')
    ext = session.get('import_ext', 'xlsx')
    sheet_index = session.get('import_sheet_index', 0)

    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'ارفع الملف مرة ثانية'})

    try:
        if ext == 'csv':
            data, cols = read_csv_data(filepath)
        else:
            zf, ns, shared, sheets_info, rid_map = read_xlsx_sheets(filepath)
            target = rid_map.get(sheets_info[sheet_index]['rId'], '')
            data, cols = read_xlsx_sheet_data(zf, ns, shared, target)
            zf.close()

        field_to_col = {}
        for excel_col, sys_field in mapping.items():
            if sys_field:
                field_to_col[sys_field] = excel_col

        rows = data[1:]
        conn = get_db()

        # بناء lookup للموجود
        existing = {}
        for row in conn.execute("SELECT id, name, cas_number FROM materials"):
            existing[(row['name'] or '').lower().strip()] = row['id']
            if row['cas_number']:
                existing[('cas:' + row['cas_number']).strip()] = row['id']

        # بناء lookup للعائلات والموردين
        families = {}
        for row in conn.execute("SELECT id, name FROM families"):
            families[row['name'].lower()] = row['id']

        suppliers = {}
        for row in conn.execute("SELECT id, name FROM suppliers"):
            suppliers[row['name'].lower()] = row['id']

        # خريطة أسماء العائلات المختلفة
        family_aliases = {
            'flower': 'floral', 'flowers': 'floral', 'frutiy': 'fruity', 'fruit': 'fruity',
            'marine': 'aquatic', 'wood': 'woody', 'woods': 'woody', 'spice': 'spicy',
            'balsam': 'balsamic', 'anisic': 'aromatic', 'mint': 'aromatic',
            'musk': 'musk', 'leather': 'leather',
        }

        added = 0
        updated = 0
        skipped = 0

        for row in rows:
            item = {}
            for sys_field, excel_col in field_to_col.items():
                val = str(row.get(excel_col, '')).strip()
                if val and val != '#DIV/0!':
                    item[sys_field] = val
                else:
                    item[sys_field] = ''

            name = item.get('name', '').strip()
            if not name:
                skipped += 1
                continue

            cas = item.get('cas_number', '').strip()

            # Merge enriched data (only fill empty fields)
            enriched = enriched_by_cas.get(cas) or enriched_by_name.get(name.lower()) or {}
            for ekey, eval_ in enriched.items():
                if ekey.startswith('_') or ekey in ('source_url', 'cid', 'pubchem_url', 'kind', 'uses_in_perfumery', 'molecular_formula', 'molecular_weight', 'iupac_name', 'logp', 'olfactive_family'):
                    continue
                if eval_ and not item.get(ekey):
                    item[ekey] = str(eval_)

            # MSDS data from enrichment
            msds_signal = enriched.get('_msds_signal', '')
            msds_h_codes = enriched.get('_msds_h_codes', '')
            msds_p_codes = enriched.get('_msds_p_codes', '')
            msds_pictograms = enriched.get('_msds_pictograms', '')
            msds_classification = enriched.get('_msds_classification', '')

            # تحقق من الموجود
            exist_id = existing.get(name.lower()) or (existing.get('cas:' + cas) if cas else None)

            if exist_id and not update_existing:
                skipped += 1
                continue

            # ربط العائلة
            family_id = None
            family_text = item.get('family', '').strip().lower()
            if family_text:
                resolved = family_aliases.get(family_text, family_text)
                family_id = families.get(resolved) or families.get(family_text)
                if not family_id:
                    # إنشاء عائلة جديدة
                    cur = conn.execute("INSERT INTO families (name, name_ar, icon) VALUES (?, ?, ?)",
                                       (item.get('family', '').strip(), '', '🏷️'))
                    family_id = cur.lastrowid
                    families[family_text] = family_id

            # ربط المورد
            supplier_id = None
            supplier_text = item.get('supplier', '').strip()
            if supplier_text:
                supplier_id = suppliers.get(supplier_text.lower())
                if not supplier_id:
                    cur = conn.execute("INSERT INTO suppliers (name) VALUES (?)", (supplier_text,))
                    supplier_id = cur.lastrowid
                    suppliers[supplier_text.lower()] = supplier_id

            # حساب السعر
            price = 0
            qty = 1
            try:
                price = float(item.get('purchase_price', 0) or 0)
            except: pass
            try:
                qty = float(item.get('purchase_quantity', 1) or 1)
            except: pass
            ppg = price / qty if qty > 0 else 0

            # Profile
            profile = item.get('profile', '').strip()
            if profile and profile.lower() in ('top', 'heart', 'base'):
                profile = profile.capitalize()
            else:
                profile = 'Heart'

            # IFRA
            ifra = None
            try:
                ifra = float(item.get('ifra_limit', '') or 0) or None
            except: pass

            if exist_id and update_existing:
                in_stock_val = 0
                try:
                    in_stock_val = float(item.get('in_stock', 0) or 0)
                except: pass
                conn.execute('''UPDATE materials SET name=?, name_ar=?, cas_number=?, family_id=?,
                    profile=?, supplier_id=?, ifra_limit=?, purchase_price=?, purchase_quantity=?,
                    price_per_gram=?, odor_description=?, notes=?, flash_point=?, specific_gravity=?,
                    color=?, appearance=?, physical_state=?,
                    melting_point=?, boiling_point=?, refractive_index=?, solubility=?,
                    vapor_density=?, ph=?,
                    synonyms=?, lot=?, strength_odor=?, vapor_pressure=?,
                    effect=?, recommended_smell_pct=?, properties=?, in_stock=? WHERE id=?''',
                    (name, item.get('name_ar', ''), cas, family_id,
                     profile, supplier_id, ifra, price, qty, ppg,
                     item.get('odor_description', ''), item.get('notes', ''),
                     item.get('flash_point', ''), item.get('specific_gravity', ''),
                     item.get('color', ''), item.get('appearance', ''),
                     item.get('physical_state', ''),
                     item.get('melting_point', ''), item.get('boiling_point', ''),
                     item.get('refractive_index', ''), item.get('solubility', ''),
                     item.get('vapor_density', ''), item.get('ph', ''),
                     item.get('synonyms', ''), item.get('lot', ''),
                     item.get('strength_odor', ''), item.get('vapor_pressure', ''),
                     item.get('effect', ''), item.get('recommended_smell_pct', ''),
                     item.get('properties', ''), in_stock_val, exist_id))
                mat_id = exist_id
                updated += 1
            else:
                in_stock_val = 0
                try:
                    in_stock_val = float(item.get('in_stock', 0) or 0)
                except: pass
                cur = conn.execute('''INSERT INTO materials (name, name_ar, cas_number, family_id, profile,
                    supplier_id, ifra_limit, purchase_price, purchase_quantity, price_per_gram,
                    odor_description, notes, flash_point, specific_gravity, color, appearance, physical_state,
                    melting_point, boiling_point, refractive_index, solubility, vapor_density, ph,
                    synonyms, lot, strength_odor, vapor_pressure, effect, recommended_smell_pct, properties, in_stock)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (name, item.get('name_ar', ''), cas, family_id,
                     profile, supplier_id, ifra, price, qty, ppg,
                     item.get('odor_description', ''), item.get('notes', ''),
                     item.get('flash_point', ''), item.get('specific_gravity', ''),
                     item.get('color', ''), item.get('appearance', ''),
                     item.get('physical_state', ''),
                     item.get('melting_point', ''), item.get('boiling_point', ''),
                     item.get('refractive_index', ''), item.get('solubility', ''),
                     item.get('vapor_density', ''), item.get('ph', ''),
                     item.get('synonyms', ''), item.get('lot', ''),
                     item.get('strength_odor', ''), item.get('vapor_pressure', ''),
                     item.get('effect', ''), item.get('recommended_smell_pct', ''),
                     item.get('properties', ''), in_stock_val))
                mat_id = cur.lastrowid
                existing[name.lower()] = mat_id
                if cas:
                    existing['cas:' + cas] = mat_id
                added += 1

            # Save MSDS data from enrichment
            if msds_signal or msds_h_codes or msds_p_codes or msds_pictograms:
                conn.execute("""INSERT OR REPLACE INTO material_msds
                    (material_id, h_codes, p_codes, pictograms, signal_word, ghs_classification)
                    VALUES (?,?,?,?,?,?)""",
                    (mat_id, msds_h_codes, msds_p_codes, msds_pictograms, msds_signal, msds_classification))

            # تصنيف عطري تلقائي
            if auto_olfactive and item.get('odor_description'):
                scores = auto_classify_odor(item['odor_description'])
                if any(v > 0 for v in scores.values()):
                    conn.execute("""INSERT OR REPLACE INTO material_olfactive
                        (material_id, citrus, aldehydic, aromatic, green, marine, floral, fruity,
                         spicy, balsamic, woody, ambery, musky, leathery, animal)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (mat_id, *[scores[cat] for cat in OLFACTIVE_CATEGORIES]))

        conn.commit()
        conn.close()

        # حذف الملف المؤقت
        try:
            os.remove(filepath)
        except: pass

        return jsonify({
            'success': True,
            'message': f'تم الاستيراد بنجاح',
            'added': added,
            'updated': updated,
            'skipped': skipped
        })
    except Exception as e:
        log(f"[IMPORT ERROR] {e}")
        return jsonify({'success': False, 'message': str(e)})

def bootstrap():
    """One-shot init used by both the dev entrypoint and the desktop launcher."""
    log("Starting My Perfumery v3...")
    init_db()
    import_ifra_standards()
    import_ifra_contributions()

if __name__ == '__main__':
    bootstrap()
    port = int(os.environ.get('MYPERFUMERY_PORT', '8000'))
    host = os.environ.get('MYPERFUMERY_HOST', '0.0.0.0')
    debug = os.environ.get('MYPERFUMERY_DEBUG', '0' if IS_FROZEN else '1') == '1'
    app.run(host=host, port=port, debug=debug, use_reloader=debug)

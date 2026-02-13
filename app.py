#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Perfume Vault v3 - نظام إدارة التركيبات العطرية مع MSDS و IFRA"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, make_response
import sqlite3
import os
import sys
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'perfume_vault_2024_v3'

# تحديد مسار قاعدة البيانات حسب البيئة
if os.path.exists('/app'):
    # داخل Docker
    DB_PATH = '/app/database/perfume.db'
else:
    # تشغيل مباشر
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database', 'perfume.db')
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

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
        boiling_point TEXT, solubility TEXT, vapor_density TEXT, appearance TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS material_msds (
        id INTEGER PRIMARY KEY, material_id INTEGER UNIQUE,
        h_codes TEXT, p_codes TEXT, pictograms TEXT, signal_word TEXT, ghs_classification TEXT,
        FOREIGN KEY (material_id) REFERENCES materials(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS formulas (
        id INTEGER PRIMARY KEY, name TEXT, description TEXT, ifra_category TEXT DEFAULT 'cat4',
        status TEXT DEFAULT 'draft', notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        active_ratio REAL DEFAULT 0.5, ifra_design_limit REAL DEFAULT 0, 
        ifra_final_limit REAL DEFAULT 0, sample_weight REAL DEFAULT 1000
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS formula_ingredients (
        id INTEGER PRIMARY KEY, formula_id INTEGER, material_id INTEGER,
        weight REAL DEFAULT 0, dilution REAL DEFAULT 0, 
        diluent TEXT DEFAULT '', diluent_other TEXT DEFAULT '',
        notes TEXT,
        FOREIGN KEY (formula_id) REFERENCES formulas(id) ON DELETE CASCADE
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS production_orders (
        id INTEGER PRIMARY KEY, order_number TEXT, formula_id INTEGER, target_quantity REAL,
        scale_factor REAL DEFAULT 1, customer_name TEXT, batch_number TEXT,
        status TEXT DEFAULT 'pending', notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # بيانات افتراضية
    c.execute("INSERT OR IGNORE INTO users (username, password, name, role) VALUES ('admin', 'admin123', 'المدير', 'admin')")
    c.execute("INSERT OR IGNORE INTO company_info (id, name, address, phone, email) VALUES (1, 'Perfume Vault', 'Kuwait', '+965 xxxx xxxx', 'info@perfumevault.com')")
    
    # حذف العوائل القديمة وإعادة إضافتها بدون تكرار
    c.execute("DELETE FROM families")
    families = [
        ('Floral', 'زهري', '🌸'), ('Oriental', 'شرقي', '🌙'), ('Woody', 'خشبي', '🪵'),
        ('Fresh', 'منعش', '🌬️'), ('Citrus', 'حمضي', '🍋'), ('Aromatic', 'عطري', '🌿'),
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
                          classifications=GHS_CLASSIFICATIONS, signal_words=GHS_SIGNAL_WORDS)

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

@app.route('/production')
@login_required
def production():
    conn = get_db()
    formulas = conn.execute("SELECT id, name FROM formulas ORDER BY name").fetchall()
    conn.close()
    return render_template('production.html', formulas=formulas)

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
            conn.close()
            return jsonify({'success': True, 'data': [dict(d) for d in data]})
        elif action == 'get':
            mid = request.args.get('id')
            data = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
            msds = conn.execute("SELECT * FROM material_msds WHERE material_id=?", (mid,)).fetchone()
            result = dict(data) if data else None
            if result and msds:
                result['msds'] = dict(msds)
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
                
                if id and id != '':
                    conn.execute('''UPDATE materials SET name=?, name_ar=?, cas_number=?, family_id=?,
                        profile=?, supplier_id=?, ifra_limit=?, purchase_price=?, purchase_quantity=?,
                        price_per_gram=?, odor_description=?, notes=?, flash_point=?, specific_gravity=?,
                        color=?, physical_state=?, ph=?, melting_point=?, boiling_point=?, 
                        solubility=?, vapor_density=?, appearance=?, refractive_index=? WHERE id=?''',
                        (name, request.form.get('name_ar'), request.form.get('cas_number'),
                         request.form.get('family_id') or None, request.form.get('profile', 'Heart'),
                         request.form.get('supplier_id') or None, request.form.get('ifra_limit') or None,
                         price, qty, ppg, request.form.get('odor_description'), request.form.get('notes'),
                         request.form.get('flash_point'), request.form.get('specific_gravity'),
                         request.form.get('color'), request.form.get('physical_state'),
                         request.form.get('ph'), request.form.get('melting_point'),
                         request.form.get('boiling_point'), request.form.get('solubility'),
                         request.form.get('vapor_density'), request.form.get('appearance'),
                         request.form.get('refractive_index'), id))
                    mat_id = id
                    msg = 'تم التحديث'
                else:
                    cur = conn.execute('''INSERT INTO materials (name, name_ar, cas_number, family_id, profile,
                        supplier_id, ifra_limit, purchase_price, purchase_quantity, price_per_gram,
                        odor_description, notes, flash_point, specific_gravity, color, physical_state,
                        ph, melting_point, boiling_point, solubility, vapor_density, appearance, refractive_index) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (name, request.form.get('name_ar'), request.form.get('cas_number'),
                         request.form.get('family_id') or None, request.form.get('profile', 'Heart'),
                         request.form.get('supplier_id') or None, request.form.get('ifra_limit') or None,
                         price, qty, ppg, request.form.get('odor_description'), request.form.get('notes'),
                         request.form.get('flash_point'), request.form.get('specific_gravity'),
                         request.form.get('color'), request.form.get('physical_state'),
                         request.form.get('ph'), request.form.get('melting_point'),
                         request.form.get('boiling_point'), request.form.get('solubility'),
                         request.form.get('vapor_density'), request.form.get('appearance'),
                         request.form.get('refractive_index')))
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
            conn.execute("DELETE FROM materials WHERE id=?", (id,))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحذف'})
    
    conn.close()
    return jsonify({'success': False})

# ===== API التركيبات =====
@app.route('/api/formulas', methods=['GET', 'POST'])
@login_required
def api_formulas():
    conn = get_db()
    
    if request.method == 'GET':
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
            
            r = dict(f)
            r['total_cost'] = total_cost
            result.append(r)
        
        conn.close()
        return jsonify({'success': True, 'data': result})
    
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
        data = conn.execute('''
            SELECT fi.*, m.name, m.name_ar, m.cas_number, m.ifra_limit, m.price_per_gram, m.profile
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
            
            ifra_limit = i['ifra_limit'] or 0  # F
            
            # N = F / H (للتصميم)
            ifra_design_calc = (ifra_limit / weight_pct) if (ifra_limit > 0 and weight_pct > 0) else None
            if ifra_design_calc is not None:
                n_values.append(ifra_design_calc)
            
            # L = F / J (النهائي)
            ifra_final_calc = (ifra_limit / pure_pct) if (ifra_limit > 0 and pure_pct > 0) else None
            if ifra_final_calc is not None:
                l_values.append(ifra_final_calc)
            
            temp_results.append({
                'data': i,
                'conc': conc,
                'pure_weight': pure_weight,
                'weight_pct': weight_pct,
                'pure_pct': pure_pct,
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
            
            # M = تجاوز إذا N < N3
            ifra_design_exceeded = (t['ifra_design_calc'] < ifra_design_limit) if (t['ifra_design_calc'] is not None and ifra_design_limit > 0) else False
            
            # K = تجاوز إذا L < E3
            ifra_final_exceeded = (t['ifra_final_calc'] < ifra_final_limit) if (t['ifra_final_calc'] is not None and ifra_final_limit > 0) else False
            
            result.append({
                **dict(i),
                'concentration': t['conc'],
                'pure_weight': t['pure_weight'],
                'weight_percentage': t['weight_pct'] * 100,  # H بالنسبة المئوية
                'percentage': t['pure_pct'] * 100,  # J بالنسبة المئوية
                'ifra_design_calc': t['ifra_design_calc'],  # N
                'ifra_design_exceeded': ifra_design_exceeded,  # M
                'ifra_final_calc': t['ifra_final_calc'],  # L
                'ifra_final_exceeded': ifra_final_exceeded,  # K
                'cost': i['weight'] * (i['price_per_gram'] or 0)
            })
        
        conn.close()
        return jsonify({
            'success': True, 
            'data': result, 
            'total_weight': total_weight, 
            'total_pure': total_pure,
            'active_ratio': active_ratio,  # J2 محسوب
            'ifra_design_limit': ifra_design_limit,  # N3 محسوب
            'ifra_final_limit': ifra_final_limit  # E3 محسوب
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
            conn.execute("""UPDATE formula_ingredients 
                SET weight=?, dilution=?, diluent=?, diluent_other=? 
                WHERE id=?""",
                (request.form.get('weight'), dilution, diluent, diluent_other, request.form.get('ing_id')))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        
        elif action == 'delete':
            conn.execute("DELETE FROM formula_ingredients WHERE id=?", (request.form.get('ing_id'),))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'تم الحذف'})
        
        elif action == 'update_formula':
            conn.execute("UPDATE formulas SET name=?, description=?, status=?, ifra_category=? WHERE id=?",
                (request.form.get('name'), request.form.get('description'), 
                 request.form.get('status'), request.form.get('ifra_category'), fid))
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

# ===== API شهادة IFRA =====
@app.route('/api/ifra-certificate/<int:fid>')
@login_required
def api_ifra_certificate(fid):
    conn = get_db()
    formula = conn.execute("SELECT * FROM formulas WHERE id=?", (fid,)).fetchone()
    if not formula:
        conn.close()
        return jsonify({'success': False, 'message': 'التركيبة غير موجودة'})
    
    ingredients = conn.execute('''
        SELECT fi.*, m.name, m.cas_number, m.ifra_limit
        FROM formula_ingredients fi
        JOIN materials m ON fi.material_id = m.id
        WHERE fi.formula_id = ?
    ''', (fid,)).fetchall()
    
    total_weight = sum(i['weight'] for i in ingredients)
    total_pure = sum(i['weight'] * get_concentration(i['dilution']) / 100 for i in ingredients)
    
    category_limits = []
    for cat in IFRA_CATEGORIES:
        if cat['limit'] is None:
            category_limits.append({
                'id': cat['id'],
                'name': cat['name'],
                'desc': cat['desc'],
                'limit': 'No Restriction',
                'compliant': True
            })
            continue
        
        max_fragrance_pct = None
        restricted_materials = []
        
        for ing in ingredients:
            if ing['ifra_limit'] and ing['ifra_limit'] > 0:
                conc = get_concentration(ing['dilution'])
                pure_weight = ing['weight'] * conc / 100
                pure_pct_in_formula = (pure_weight / total_pure * 100) if total_pure > 0 else 0
                
                if pure_pct_in_formula > 0:
                    max_frag = (ing['ifra_limit'] / pure_pct_in_formula) * 100
                    if max_fragrance_pct is None or max_frag < max_fragrance_pct:
                        max_fragrance_pct = max_frag
                        
                    actual_in_product = pure_pct_in_formula * cat['limit'] / 100
                    if actual_in_product > ing['ifra_limit']:
                        restricted_materials.append(ing['name'])
        
        limit_value = round(max_fragrance_pct, 3) if max_fragrance_pct else cat['limit'] * 100
        
        category_limits.append({
            'id': cat['id'],
            'name': cat['name'],
            'desc': cat['desc'],
            'limit': min(limit_value, 100) if max_fragrance_pct else cat['limit'] * 100,
            'compliant': len(restricted_materials) == 0,
            'restricted': restricted_materials
        })
    
    conn.close()
    return jsonify({
        'success': True,
        'formula': dict(formula),
        'ingredients': [dict(i) for i in ingredients],
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
    conn.close()

    return jsonify({
        'success': True,
        'formula': dict(formula),
        'families': family_list,
        'pyramid': pyramid,
        'total_weight': total_weight,
        'ingredients_count': len(ingredients),
        'company': dict(company) if company else {}
    })

if __name__ == '__main__':
    log("Starting Perfume Vault v3...")
    init_db()
    app.run(host='0.0.0.0', port=8000, debug=True)

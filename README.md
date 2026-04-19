# My Perfumery v3

نظام متكامل لإدارة تركيبات العطور مع دعم كامل لـ IFRA و MSDS

## المميزات الرئيسية

### 1. إدارة المواد الخام
- إضافة وتعديل المواد مع بيانات كاملة (CAS, عائلة, مورد, سعر, مخزون)
- **جلب تلقائي للبيانات** من 4 مصادر عبر رقم CAS:
  - PubChem (خصائص فيزيائية)
  - The Good Scents Company (بيانات عطرية)
  - Scentree.co (بيانات عطرية)
  - PubChem GHS/MSDS (بيانات السلامة)
- بيانات MSDS متكاملة (H-Codes, P-Codes, Pictograms, Signal Word)
- تصنيفات GHS كاملة
- **بروفايل عطري** (Olfactive Profile) - 14 محور مع Polar Area Chart
- **تصنيف عطري تلقائي** من وصف الرائحة
- تاب **IFRA** يعرض حدود الفئات الـ 18 تلقائياً من قاعدة بيانات IFRA

### 2. إدارة التركيبات
- إنشاء تركيبات مع بطاقات عرض وعجلة عطرية
- **نظام المسودات (Drafts)** - حفظ نسخ متعددة من التركيبة أثناء التجريب:
  - حفظ مسودات مرقمة (Draft 1, 2, 3...)
  - تحميل أي مسودة سابقة للعمل عليها
  - مقارنة المسودات جنباً إلى جنب
  - اعتماد مسودة كتركيبة نهائية
- مكونات مع نسب الوزن والتخفيف ومادة التخفيف (Diluent)
- حقل التخفيف (Dilution):
  - `1` = نقي/صافي (100%)
  - `0.5` = تركيز 50%
  - `0.1` = تركيز 10%
- حسابات تلقائية: نسبة الزيت (H), نسبة الصافي (J), IFRA تصميم (N), IFRA نهائي (L)
- **حدود IFRA حسب الفئة** - يستخدم بيانات IFRA 51st Amendment (263 مادة مقننة، 18 فئة)
- حاسبة Scale متعددة الكميات
- نسخ التركيبات
- ملاحظات التركيبة

### 3. معايير IFRA
- قاعدة بيانات **IFRA 51st Amendment** (263 مادة مقننة)
- **18 فئة استخدام** (Cat 1 - Cat 12 مع فئات فرعية 5A-5D, 7A-7B, 10A-10B, 11A-11B)
- ربط تلقائي عبر CAS number
- أنواع المعايير: Prohibition, Restriction, Specification
- حساب التوافق لكل فئة بالتركيبة
- شهادة IFRA قابلة للطباعة
- **تقارير IFRA و MSDS متاحة فقط للتركيبات المعتمدة (Final)**

### 4. تقرير MSDS
- توليد تقرير SDS كامل (16 قسم)
- تجميع H-Codes و P-Codes من جميع المكونات
- الرموز التحذيرية (Pictograms)
- كلمة الإشارة (Signal Word)
- طباعة احترافية

### 5. الاستيراد الذكي (Smart Import)
- استيراد مواد من Excel/CSV بـ 4 خطوات:
  1. رفع الملف
  2. ربط الأعمدة
  3. معاينة مع **جلب بيانات ناقصة** من المصادر الأربعة
  4. تنفيذ الاستيراد
- تصنيف عطري تلقائي عند الاستيراد

### 6. أوامر الإنتاج
- إنشاء أوامر إنتاج
- تتبع الحالة
- إدارة الكميات

### 7. إدارة الموردين
- قاعدة بيانات الموردين
- معلومات الاتصال

### 8. النسخ الاحتياطي
- نظام نسخ احتياطي تلقائي مع إمكانية الاستعادة

## التشغيل

### باستخدام Docker (موصى به)

```bash
docker-compose up -d --build
```

### تشغيل مباشر

```bash
pip install flask
python app.py
```

## بيانات الدخول الافتراضية

- **اسم المستخدم:** admin
- **كلمة المرور:** admin123

## هيكل الملفات

```
My-Perfumery/
├── app.py              # التطبيق الرئيسي (Flask) ~3200 سطر
├── Dockerfile
├── docker-compose.yml
├── data/
│   ├── ifra_standards.xlsx   # IFRA 51st Amendment (263 مادة)
│   └── ifra_annex.xlsx       # IFRA Annex (مساهمات المصادر الطبيعية)
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── index.html            # لوحة التحكم
│   ├── materials.html        # إدارة المواد (5 تابات)
│   ├── formulas.html         # قائمة التركيبات (بطاقات)
│   ├── formula.html          # تفاصيل التركيبة + نظام المسودات
│   ├── import.html           # الاستيراد الذكي (4 خطوات)
│   ├── ifra_certificate.html
│   ├── msds_generator.html
│   ├── production.html
│   ├── suppliers.html
│   ├── calculator.html
│   ├── formula_card.html     # بطاقة تعريفية
│   └── settings.html
├── static/
└── database/
    └── perfume.db            # SQLite (ينشأ تلقائياً)
```

## API Endpoints

```
# المواد
GET  /api/materials                    # قائمة المواد
POST /api/materials                    # إضافة/تعديل مادة

# التركيبات
GET  /api/formulas                     # قائمة التركيبات
GET  /api/formula/<id>/ingredients     # مكونات التركيبة مع حسابات IFRA
POST /api/formula/<id>/ingredients     # إضافة/تعديل/حذف مكون

# المسودات
GET  /api/formula/<id>/drafts          # قائمة مسودات التركيبة
POST /api/formula/<id>/drafts          # حفظ/تحميل/حذف/اعتماد مسودة
GET  /api/draft/<id>/ingredients       # مكونات مسودة محددة

# IFRA
GET  /api/ifra/lookup?cas=<cas>        # بحث IFRA بالـ CAS
GET  /api/ifra/categories              # قائمة فئات IFRA الـ 18
GET  /api/ifra/formula-check/<id>      # فحص توافق IFRA للتركيبة
GET  /api/ifra-certificate/<id>        # شهادة IFRA (يتطلب حالة Final)

# MSDS
GET  /api/msds/<id>                    # تقرير MSDS (يتطلب حالة Final)

# جلب بيانات خارجية
GET  /api/cas-lookup?cas=<cas>         # PubChem (خصائص فيزيائية)
GET  /api/tgsc-lookup?cas=<cas>        # The Good Scents Company
GET  /api/scentree-lookup?q=<cas>      # Scentree.co
GET  /api/msds-lookup?cas=<cas>        # PubChem GHS/MSDS

# الاستيراد
POST /api/import/upload                # رفع ملف
POST /api/import/columns               # ربط الأعمدة
POST /api/import/preview               # معاينة
POST /api/import/execute               # تنفيذ

# أخرى
GET  /api/ghs-data                     # بيانات GHS
GET  /api/dashboard                    # إحصائيات
```

## الترخيص

مشروع خاص - جميع الحقوق محفوظة

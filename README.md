# My Perfumery v3

نظام متكامل لإدارة تركيبات العطور مع دعم كامل لـ IFRA و MSDS، بالإضافة إلى **مذكرات العطّار** مع بروفايل عطري 14-محور لكل مذكرة. يعمل عبر المتصفح أو كبرنامج ويندوز مستقل (`MyPerfumery.exe`).

## تحميل نسخة ويندوز (EXE)

- آخر نسخة جاهزة (يُعاد بناؤها تلقائياً عند كل تحديث على `main`):
  https://github.com/Artistkw3d/My-Perfumery/releases/tag/latest
- حمّل `MyPerfumery.exe` وشغّله بدون أي تثبيت. البرنامج يختار أول بورت متاح تلقائياً، فلا يحتاج إعدادات شبكة.
- قاعدة البيانات الخاصة بك تُحفظ محلياً في `%APPDATA%\MyPerfumery\database\perfume.db` مع نسخ احتياطية تلقائية.

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

### 9. المذكرات (Notebook) مع بروفايل عطري
- صفحة `/notebook` مخصّصة لتدوين **قصص، أفكار، ملاحظات، يوميات** العطّار — كل مذكرة مع تصنيف ووسوم ونص حر
- لكل مذكرة **بروفايل عطري كامل** (14 محور، نفس محاور `material_olfactive`) بسلايدرز + **Polar Area Chart**
- الأيقونات مأخوذة من جدول `families` (🍋 حمضي، 🌸 زهري، 🪵 خشبي، 🌊 مائي، ...) لتوحيد الهوية البصرية
- **5 بريسيتات** مبنية على نظرية الألوان:
  - 🌬️ **منعش** — تشابه (analogous)
  - 🌸 **زهري** — تكميل مجزأ (split-complementary)
  - 🌙 **شرقي** — تضاد (complementary)
  - 🪵 **خشبي** — تشابه عميق (analogous-deep)
  - 🍯 **حلو** — ثلاثي (triadic)
- بحث، فلترة بالفئة أو الوسم، ونسخ/حذف، مع حفظ تلقائي (debounced 500ms)

### 10. تجربة مريحة على شاشات اللابتوب
- **كثافة مضغوطة تلقائية**: بين 769px و1400px عرض الشاشة، كل الصفحات تقلّص padding والخطوط وارتفاع صفوف الجدول تلقائياً — بدون تغيير تخطيط، فقط استغلال أفضل للبكسل
- **زر إخفاء/إظهار الأعمدة المتقدمة** في جدول مكونات التركيبة: الافتراضي يخفي 5 أعمدة مشتقة (H، N، M، J، K) فيصير الجدول 10 أعمدة بدال 15 — يتناسب مع شاشات 1366px بدون سكرول أفقي. الاختيار محفوظ في `localStorage`
- **زر طيّ القائمة الجانبية** (الشيفرون على الحافة الداخلية) يخفي قائمة التنقل ويوسّع المنطقة الرئيسية، مع حفظ الحالة

## التشغيل

### نسخة ويندوز الجاهزة (أسهل خيار)

حمّل `MyPerfumery.exe` من صفحة [Releases → latest](https://github.com/Artistkw3d/My-Perfumery/releases/tag/latest) ثم انقر مرتين. البرنامج:
- يختار أول بورت شبكة متاح تلقائياً (لا يتعارض مع أي برنامج آخر)
- يفتح نافذة WebView2 محلية (مو متصفح خارجي)
- يحفظ البيانات في `%APPDATA%\MyPerfumery\database\`

### باستخدام Docker

```bash
docker-compose up -d --build
```

### تشغيل مباشر (Python)

```bash
pip install -r requirements.txt
python app.py                # خادم Flask فقط
# أو
python launcher.py           # Flask داخل نافذة pywebview
```

### بناء الـ EXE محلياً

```bash
build.bat   # ينتج dist\MyPerfumery.exe
```

## بيانات الدخول الافتراضية

- **اسم المستخدم:** admin
- **كلمة المرور:** admin123

## هيكل الملفات

```
My-Perfumery/
├── app.py                      # التطبيق الرئيسي (Flask) ~4000 سطر
├── launcher.py                 # مُشغِّل سطح المكتب (pywebview + port picker)
├── build.bat                   # بناء MyPerfumery.exe محلياً
├── requirements.txt            # flask, pywebview, pyinstaller
├── .github/workflows/
│   └── build-windows.yml       # CI يبني الـ .exe ويرفعه على release "latest"
├── Dockerfile
├── docker-compose.yml
├── data/
│   ├── ifra_standards.xlsx     # IFRA 51st Amendment (263 مادة)
│   └── ifra_annex.xlsx         # IFRA Annex (مساهمات المصادر الطبيعية)
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── index.html              # لوحة التحكم
│   ├── materials.html          # إدارة المواد
│   ├── formulas.html           # قائمة التركيبات (بطاقات)
│   ├── formula.html            # تفاصيل التركيبة + نظام المسودات
│   ├── notebook.html           # المذكرات + بروفايل عطري
│   ├── import.html             # الاستيراد الذكي (4 خطوات)
│   ├── ifra_certificate.html
│   ├── msds_generator.html
│   ├── production.html
│   ├── suppliers.html
│   ├── calculator.html
│   ├── formula_card.html       # بطاقة تعريفية
│   └── settings.html
├── static/
└── database/
    └── perfume.db              # SQLite (ينشأ تلقائياً — أو %APPDATA%\MyPerfumery\ في نسخة الـ .exe)
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

# المذكرات (Notebook)
GET  /notebook                         # صفحة المذكرات
GET  /api/notebook/entries             # قائمة المذكرات
POST /api/notebook/entries             # action=create|update|delete|duplicate

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

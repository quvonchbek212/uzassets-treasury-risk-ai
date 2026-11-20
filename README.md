# UzAssets — Payment Calendar Risk Forecast AI Service

> **Kompaniya haqida:** «UzAssets» investitsiya kompaniyasi AJ davlat ulushi mavjud yirik korxonalarni transformatsiya qilish, xususiylashtirish va kapital bozoriga tayyorlash jarayonlarini amalga oshiruvchi yetakchi investitsiya kompaniyasidir.

Ushbu servis «UzAssets» korxonalari va g'aznachilik boshqaruvi (**Treasury Payment Calendar**) uchun to'lovlar oqimi, kassa uzilishlari va moliyaviy xatarlarni sun'iy intellekt (AI) orqali chuqur tahlil qilib, rahbarlar va moliyachilar uchun **ijroiy tahliliy hisobot (Executive Risk Narrative)** va operatsion tavsiyalarni shakllantiruvchi mikroxizmatdir.

---

## 🎯 Asosiy Vazifasi va Imkoniyatlari

* **Xatar drayverlarini aniqlash (Key Drivers):**
  * `PAYMENT_CONCENTRATION` — Katta hajmdagi to'lovlarning bir kunda jamlanishi;
  * `OVERDUE_PRESSURE` — Muddati o'tgan to'lovlar bosimi va jarimalar xavfi;
  * `APPROVAL_BOTTLENECK` — Tasdiqlash jarayonida qolib ketgan to'lovlar to'siqlari;
  * `BUDGET_LIMIT_STRESS` — Byudjet limitlarining yetishmovchiligi;
  * `CURRENCY_EXPOSURE` — Valyuta kurslari tebranishi xatarlari;
  * `DEBT_SERVICE_STRESS` — Qarzga xizmat ko'rsatish yuki.
* **Operatsion Tavsiyalar (Recommended Actions):** Qaysi to'lovlarni kechiktirish xavfsiz ekanligi, qaysilarini esa zudlik bilan amalga oshirish shartligi bo'yicha darajali (`HIGH`, `MEDIUM`, `LOW`) amaliy tavsiyalar.
* **Ko'p Tilli:** O'zbek, rus va ingliz tillarida to'liq hisobotlar tayyorlaydi.
* **Qat'iy Fallback Kafolati:** AI provayder o'chirilgan yoki tarmoq nosoz bo'lsa ham, tizim to'xtab qolmaydi — `narrative_fallback.py` moduli deterministik qoidalar asosida to'liq xatar tahlilini taqdim etadi.

---

## 🏗 Arxitektura va Texnologiyalar

* **Til va Framework:** Python 3.11+, FastAPI, Pydantic v2
* **AI Provayderlar:**
  * **Google Gemini API** — Murakkab moliyaviy matnlarni tushunish va tahliliy xulosa generatsiyasi;
  * **vLLM (Gemma-31B)** — Korxona ichki serverida lokal inferensiya.
* **Prompt Sanitizer:** Moliyaviy so'rovlardan shaxsiy va konfidensial identifikatorlarni tozalovchi himoya qatlami.
* **Response Validator:** AI generatsiya qilgan javoblar sxemasini qat'iy tekshirish (hallutsinatsiyalarning oldini olish).
* **Circuit Breaker:** Tashqi AI API xatoliklarida yuklamani to'xtatuvchi himoya zanjiri.

---

## 🚀 API Endpointlar

Servis quyidagi asosiy yo'nalishlar bo'yicha ishlaydi:

| Metod | Endpoint | Tavsif |
|---|---|---|
| `POST` | `/api/v1/treasury/payment-calendar/risk-forecast` | Butun davr (oy/hafta) bo'yicha umumiy xatar hisoboti |
| `POST` | `/api/v1/treasury/payment-calendar/risk-forecast/days/{date}` | Tanlangan aniq kun bo'yicha chuqur tahliliy hisobot |
| `POST` | `/api/v1/treasury/payment-calendar/risk-forecast/explain` | Aniq xatar skori va drayveri bo'yicha batafsil izoh |
| `GET` | `/health` | Servis sog'lomligini tekshirish |

---

## 💻 Mahalliy muhitda ishga tushirish

1. Virtual muhitni yarating va bog'liqliklarni o'rnating:
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. `.env` faylini sozlang:
```bash
cp .env.example .env
# .env faylida GEMINI_API_KEY yoki VLLM sozlamalarini belgilang
```

3. Serverni ishga tushiring:
```bash
python main.py
# yoki
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```
Swagger UI: `http://localhost:8002/docs`

4. Testlarni ishga tushirish:
```bash
pytest risk_forecast/tests.py -v
```

---

## 🔒 Xavfsizlik

Barcha maxfiy ma'lumotlar, parollar va API kalitlar faqat lokal `.env` faylida saqlanadi. Loyihada `.gitignore` orqali hech qanday kalitlar ommaviy repozitoriyga chiqib ketmasligi to'liq ta'minlangan.

-- قاعدة بوابة النتائج (Cloudflare D1) — شغّله مرة وحدة بـ D1 ← Console لكل عميل جديد
CREATE TABLE IF NOT EXISTS portal (
  token        TEXT PRIMARY KEY,
  patient_name TEXT,
  status       TEXT,
  lab_name     TEXT,
  eta_text     TEXT,
  results_html TEXT,
  pdf_b64      TEXT,
  updated_at   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_portal_updated ON portal(updated_at);

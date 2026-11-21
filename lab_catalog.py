# -*- coding: utf-8 -*-
"""
كتالوج التحاليل الجاهز: كيمياء، هرمونات، فيتامينات، دلائل ورمية، أمراض الدم.

- name       = الاسم العلمي الكامل (يظهر بالتقارير)
- short_name = المختصر (يظهر باختيار التحاليل بزيارة جديدة)
- القيم الطبيعية هي قيم بالغين شائعة بالوحدات التقليدية، وهي نقطة بداية فقط:
  تختلف حسب جهاز/كِت كل مختبر، فيجب أن يراجعها مسؤول المختبر ويعدّل أي نسبة من أيقونة النسب الطبيعية.
- التثبيت يضيف فقط ولا يعدّل ولا يحذف: أي تحليل موجود أصلاً (بالاسم أو المختصر أو الكود) يُتخطى.
"""

B, M, F = "Both", "Male", "Female"


def r(lo=None, hi=None, g=B, text=None):
    """نسبة طبيعية: (جنس، من، إلى، نص)."""
    if text is None and (lo is None) != (hi is None):
        text = ("> %g" % lo) if hi is None else ("< %g" % hi)
    return (g, lo, hi, text)


def ra(lo, hi, g, af, at, unit="Years"):
    """نسبة طبيعية لفئة عمرية: من af إلى at (بالوحدة unit: Years/Months/Days)."""
    return (g, lo, hi, None, af, at, unit)


def mf(mlo, mhi, flo, fhi):
    return [r(mlo, mhi, M), r(flo, fhi, F)]


def txt(t, g=B):
    return [(g, None, None, t)]


def p(name, unit="", ranges=None, rtype="Numeric"):
    return {"name": name, "unit": unit, "ranges": ranges or [], "type": rtype}


def pt(name, ranges=None):
    return p(name, "", ranges, "Text")


_CATALOG = []


def t(dept, group, name, short, sample, params, aliases=()):
    _CATALOG.append({"dept": dept, "group": group, "name": name, "short": short,
                     "sample": sample, "params": params, "aliases": list(aliases)})


def single(dept, group, name, short, sample, unit, ranges, aliases=()):
    t(dept, group, name, short, sample, [p(name, unit, ranges)], aliases)


# =============================== الكيمياء ===============================
C, CG, S = "Biochemistry", "Biochemistry Tests", "Serum"
single(C, CG, "Fasting Blood Glucose", "FBS", "Serum", "mg/dL", [r(70, 100, text="Normal: Less than 100\nPre-diabetic: 100 - 125\nDiabetic: 126 or more")], ["Blood sugar(F)", "FBG", "Blood Glucose Fasting"])
single(C, CG, "Random Blood Glucose", "RBS", "Serum", "mg/dL", [r(None, 140)], ["Blood sugar(R)", "Random Blood Sugar"])
single(C, CG, "2-Hour Postprandial Blood Glucose", "2HPP", "Serum", "mg/dL", [r(None, 140)], ["2 hr PP", "PPBS"])
single(C, CG, "Fructosamine", "Fructosamine", "Serum", "µmol/L", [r(200, 285)])

single(C, CG, "Blood Urea", "Urea", S, "mg/dL", [r(15, 45)])
single(C, CG, "Blood Urea Nitrogen", "BUN", S, "mg/dL", [r(7, 20)])
single(C, CG, "Serum Creatinine", "Creat", S, "mg/dL", mf(0.7, 1.3, 0.6, 1.1), ["Creatinine"])
single(C, CG, "Serum Uric Acid", "UA", S, "mg/dL", mf(3.5, 7.2, 2.6, 6.0), ["Uric Acid"])
t(C, CG, "Renal Function Tests", "RFT", S, [
    p("Blood Urea", "mg/dL", [r(15, 45)]),
    p("Serum Creatinine", "mg/dL", mf(0.7, 1.3, 0.6, 1.1)),
    p("Serum Uric Acid", "mg/dL", mf(3.5, 7.2, 2.6, 6.0)),
], ["renal function tests", "KFT"])

single(C, CG, "Serum Sodium", "Na", S, "mmol/L", [r(135, 145)])
single(C, CG, "Serum Potassium", "K", S, "mmol/L", [r(3.5, 5.1)])
single(C, CG, "Serum Chloride", "Cl", S, "mmol/L", [r(98, 107)])
single(C, CG, "Serum Bicarbonate", "HCO3", S, "mmol/L", [r(22, 29)])
t(C, CG, "Serum Electrolytes", "Lytes", S, [
    p("Serum Sodium", "mmol/L", [r(135, 145)]),
    p("Serum Potassium", "mmol/L", [r(3.5, 5.1)]),
    p("Serum Chloride", "mmol/L", [r(98, 107)]),
], ["Electrolytes", "Na K Cl"])
single(C, CG, "Total Serum Calcium", "Ca", S, "mg/dL", [r(8.6, 10.2)], ["Calcium"])
single(C, CG, "Ionized Calcium", "iCa", "Serum", "mmol/L", [r(1.12, 1.32)])
single(C, CG, "Serum Inorganic Phosphorus", "PO4", S, "mg/dL", [r(2.5, 4.5)], ["Phosphorus", "Phosphate"])
single(C, CG, "Serum Magnesium", "Mg", S, "mg/dL", [r(1.7, 2.2)], ["Magnesium"])
single(C, CG, "Serum Zinc", "Zn", S, "µg/dL", [r(70, 120)], ["Zinc"])

single(C, CG, "Alanine Aminotransferase", "ALT", S, "U/L", [r(None, 41, M), r(None, 33, F)], ["SGPT", "ALT (SGPT)"])
single(C, CG, "Aspartate Aminotransferase", "AST", S, "U/L", [r(None, 40, M), r(None, 32, F)], ["SGOT", "AST (SGOT)"])
single(C, CG, "Alkaline Phosphatase", "ALP", S, "U/L", [r(35, 129)])
single(C, CG, "Gamma-Glutamyl Transferase", "GGT", S, "U/L", [r(8, 61, M), r(5, 36, F)])
single(C, CG, "Total Serum Bilirubin", "T.Bil", S, "mg/dL", [r(0.1, 1.2)], ["Bilirubin Total", "Total Bilirubin"])
single(C, CG, "Direct Serum Bilirubin", "D.Bil", S, "mg/dL", [r(0.0, 0.3)], ["Bilirubin Direct", "Direct Bilirubin"])
single(C, CG, "Total Serum Protein", "T.Protein", S, "g/dL", [r(6.4, 8.3)], ["Total Protein"])
single(C, CG, "Serum Albumin", "Alb", S, "g/dL", [r(3.5, 5.2)], ["Albumin"])
single(C, CG, "Serum Globulin", "Glob", S, "g/dL", [r(2.0, 3.5)], ["Globulin"])
t(C, CG, "Liver Function Tests", "LFT", S, [
    p("Alanine Aminotransferase (ALT)", "U/L", [r(None, 41, M), r(None, 33, F)]),
    p("Aspartate Aminotransferase (AST)", "U/L", [r(None, 40, M), r(None, 32, F)]),
    p("Alkaline Phosphatase (ALP)", "U/L", [r(35, 129)]),
    p("Total Serum Bilirubin", "mg/dL", [r(0.1, 1.2)]),
    p("Direct Serum Bilirubin", "mg/dL", [r(0.0, 0.3)]),
    p("Total Serum Protein", "g/dL", [r(6.4, 8.3)]),
    p("Serum Albumin", "g/dL", [r(3.5, 5.2)]),
], ["liver function tests", "LFTs"])

t(C, CG, "Lipid Profile", "Lipid", S, [
    p("Total Cholesterol", "mg/dL", [r(None, 200, text="Desirable level: Less than 200\nBorderline high: 200 - 240\nHigh risk: More than 240")]),
    p("Triglycerides", "mg/dL", [r(None, 150, text="Normal: Less than 150\nBorderline high: 150 - 199\nHigh: 200 - 499\nVery high: 500 or more")]),
    p("HDL Cholesterol", "mg/dL", [r(45, None, text="No risk: More than 65\nModerate risk: 45 - 55\nHigh risk: Less than 45")]),
    p("LDL Cholesterol", "mg/dL", [r(None, 100)]),
    p("VLDL Cholesterol", "mg/dL", [r(2, 30)]),
    p("Cholesterol / HDL Ratio", "", [r(None, 5)]),
], ["lipid profil", "Lipid Profile"])
single(C, CG, "Total Cholesterol", "Chol", S, "mg/dL", [r(None, 200, text="Desirable level: Less than 200\nBorderline high: 200 - 240\nHigh risk: More than 240")], ["Cholesterol"])
single(C, CG, "Triglycerides", "TG", S, "mg/dL", [r(None, 150, text="Normal: Less than 150\nBorderline high: 150 - 199\nHigh: 200 - 499\nVery high: 500 or more")])
single(C, CG, "HDL Cholesterol", "HDL", S, "mg/dL", [r(45, None, text="No risk: More than 65\nModerate risk: 45 - 55\nHigh risk: Less than 45")])
single(C, CG, "LDL Cholesterol", "LDL", S, "mg/dL", [r(None, 100)])

single(C, CG, "Serum Amylase", "Amylase", S, "U/L", [r(28, 100)])
single(C, CG, "Serum Lipase", "Lipase", S, "U/L", [r(13, 60)])
single(C, CG, "Lactate Dehydrogenase", "LDH", S, "U/L", [r(140, 280)])
single(C, CG, "Creatine Kinase (Total)", "CK", S, "U/L", [r(39, 308, M), r(26, 192, F)], ["CPK"])
single(C, CG, "Creatine Kinase-MB", "CK-MB", S, "U/L", [r(None, 25)])
single(C, CG, "Troponin I", "Trop I", S, "ng/mL", [r(None, 0.04)])

single(C, CG, "C-Reactive Protein (Quantitative)", "CRP", S, "mg/L", [r(None, 5)], ["CRP"])
single(C, CG, "Rheumatoid Factor", "RF", S, "IU/mL", [r(None, 14)])
single(C, CG, "Anti-Streptolysin O Titre", "ASOT", S, "IU/mL", [r(None, 200)], ["ASO"])
single(C, CG, "Procalcitonin", "PCT", S, "ng/mL", [r(None, 0.5)])
single(C, CG, "Plasma Homocysteine", "Hcy", "Plasma", "µmol/L", [r(5, 15)], ["Homocysteine"])
single(C, CG, "Blood Lactate", "Lactate", "Plasma", "mmol/L", [r(0.5, 2.2)])
single(C, CG, "Plasma Ammonia", "NH3", "Plasma", "µmol/L", [r(15, 45)], ["Ammonia"])
single(C, CG, "24-Hour Urine Protein", "24h Prot", "Urine 24h", "mg/24h", [r(None, 150)])
single(C, CG, "Urine Albumin / Creatinine Ratio", "ACR", "Urine", "mg/g", [r(None, 30)], ["Microalbumin"])

# =============================== الهرمونات ===============================
H, HG = "Hormones", "Hormones Tests"
single(H, HG, "Thyroid Stimulating Hormone", "TSH", S, "µIU/mL", [r(0.27, 4.2)])
single(H, HG, "Free Thyroxine", "FT4", S, "ng/dL", [r(0.93, 1.7)])
single(H, HG, "Free Triiodothyronine", "FT3", S, "pg/mL", [r(2.0, 4.4)])
single(H, HG, "Total Thyroxine", "T4", S, "µg/dL", [r(5.1, 14.1)])
single(H, HG, "Total Triiodothyronine", "T3", S, "ng/dL", [r(80, 200)])
t(H, HG, "Thyroid Function Tests", "TFT", S, [
    p("Thyroid Stimulating Hormone (TSH)", "µIU/mL", [r(0.27, 4.2)]),
    p("Total Triiodothyronine (T3)", "ng/dL", [r(80, 200)]),
    p("Total Thyroxine (T4)", "µg/dL", [r(5.1, 14.1)]),
], ["Thyroid Profile"])
single(H, HG, "Anti-Thyroid Peroxidase Antibodies", "Anti-TPO", S, "IU/mL", [r(None, 34)])
single(H, HG, "Anti-Thyroglobulin Antibodies", "Anti-TG", S, "IU/mL", [r(None, 115)])

single(H, HG, "Follicle Stimulating Hormone", "FSH", S, "mIU/mL",
      [r(1.5, 12.4, M)] + txt("Follicular: 3.5 - 12.5\nMid-cycle: 4.7 - 21.5\nLuteal: 1.7 - 7.7\nPost-menopausal: 25.8 - 134.8", F))
single(H, HG, "Luteinizing Hormone", "LH", S, "mIU/mL",
      [r(1.7, 8.6, M)] + txt("Follicular: 2.4 - 12.6\nMid-cycle: 14.0 - 95.6\nLuteal: 1.0 - 11.4\nPost-menopausal: 7.7 - 58.5", F))
single(H, HG, "Prolactin", "PRL", S, "ng/mL", mf(4.0, 15.2, 4.8, 23.3))
single(H, HG, "Estradiol", "E2", S, "pg/mL",
      [r(7.6, 42.6, M)] + txt("Follicular: 12.5 - 166\nMid-cycle: 85.8 - 498\nLuteal: 43.8 - 211\nPost-menopausal: Less than 54.7", F))
single(H, HG, "Progesterone", "PROG", S, "ng/mL",
      [r(0.2, 1.4, M)] + txt("Follicular: 0.2 - 1.5\nLuteal: 1.7 - 27\nPost-menopausal: 0.1 - 0.8", F))
single(H, HG, "Total Testosterone", "Testo", S, "ng/mL", [r(2.49, 8.36, M), r(0.084, 0.481, F)])
single(H, HG, "Sex Hormone Binding Globulin", "SHBG", S, "nmol/L", mf(18.3, 54.1, 32.4, 128))
single(H, HG, "Dehydroepiandrosterone Sulfate", "DHEA-S", S, "µg/dL", txt("Age dependent"))
single(H, HG, "Anti-Mullerian Hormone", "AMH", S, "ng/mL", [r(1.0, 4.0, F)])
single(H, HG, "Beta Human Chorionic Gonadotropin (Quantitative)", "B-hCG", S, "mIU/mL", [r(None, 5)], ["Beta-HCG", "BHCG"])
single(H, HG, "Serum Cortisol (Morning)", "Cortisol", S, "µg/dL", [r(6.2, 19.4)], ["Cortisol"])
single(H, HG, "Adrenocorticotropic Hormone", "ACTH", "Plasma", "pg/mL", [r(7.2, 63.3)])
single(H, HG, "Growth Hormone", "GH", S, "ng/mL", [r(None, 3, M), r(None, 8, F)])
single(H, HG, "Parathyroid Hormone (Intact)", "PTH", S, "pg/mL", [r(15, 65)])
single(H, HG, "Fasting Serum Insulin", "Insulin", S, "µIU/mL", [r(2.6, 24.9)], ["Insulin"])
single(H, HG, "C-Peptide", "C-Pep", S, "ng/mL", [r(1.1, 4.4)])

# =============================== الفيتامينات ===============================
V, VG = "Vitamins", "Vitamins Tests"
t(V, VG, "Vitamin D (25-Hydroxy)", "Vit D", S, [p("Vitamin D (25-Hydroxy)", "ng/mL", [r(30, 100)])], ["Vitamin D", "25-OH Vitamin D"])
t(V, VG, "Vitamin B12 (Cobalamin)", "B12", S, [p("Vitamin B12 (Cobalamin)", "pg/mL", [r(200, 900)])], ["Vitamin B12"])
t(V, VG, "Folic Acid (Folate)", "Folate", S, [p("Folic Acid (Folate)", "ng/mL", [r(3.0, 17.0)])], ["Folate", "Folic Acid"])

# =============================== الدلائل الورمية ===============================
TM, TG = "Tumor Markers", "Tumor Marker"
single(TM, TG, "Prostate Specific Antigen (Total)", "PSA", S, "ng/mL", [r(None, 4.0, M)], ["PSA Total", "PSA"])
single(TM, TG, "Prostate Specific Antigen (Free)", "fPSA", S, "ng/mL", txt("Interpret with Total PSA", M), ["Free PSA"])
single(TM, TG, "Carcinoembryonic Antigen", "CEA", S, "ng/mL", [r(None, 5.0)])
single(TM, TG, "Alpha-Fetoprotein", "AFP", S, "ng/mL", [r(None, 7.0)])
single(TM, TG, "Cancer Antigen 125", "CA 125", S, "U/mL", [r(None, 35)], ["CA125"])
single(TM, TG, "Cancer Antigen 15-3", "CA 15-3", S, "U/mL", [r(None, 30)], ["CA153"])
single(TM, TG, "Cancer Antigen 19-9", "CA 19-9", S, "U/mL", [r(None, 37)], ["CA199"])
single(TM, TG, "Cancer Antigen 72-4", "CA 72-4", S, "U/mL", [r(None, 6.9)])
single(TM, TG, "Human Epididymis Protein 4", "HE4", S, "pmol/L", [r(None, 70, F)])
single(TM, TG, "Neuron Specific Enolase", "NSE", S, "ng/mL", [r(None, 16.3)])
single(TM, TG, "Cytokeratin 19 Fragment (CYFRA 21-1)", "CYFRA", S, "ng/mL", [r(None, 3.3)])
single(TM, TG, "Beta-2 Microglobulin", "B2M", S, "mg/L", [r(0.8, 2.2)])

# =============================== أمراض الدم ===============================
HM, HMG, WB = "Hematology", "", "Whole Blood (EDTA)"
t(HM, HMG, "Complete Blood Count", "CBC", WB, [
    p("White Blood Cells (WBC)", "x10^9/L", [ra(9.0, 30.0, B, 0, 1, "Months"), ra(6.0, 17.5, B, 1, 12, "Months"),
                                              ra(5.5, 15.5, B, 1, 6), ra(4.5, 13.5, B, 6, 12), ra(4.0, 11.0, B, 12, 120)]),
    p("Neutrophils %", "%", [r(40, 75)]), p("Lymphocytes %", "%", [r(20, 45)]),
    p("Monocytes %", "%", [r(2, 10)]), p("Basophils %", "%", [r(0, 1)]), p("Eosinophils %", "%", [r(1, 6)]),
    p("Neutrophils #", "x10^9/L", [r(2.0, 7.5)]), p("Lymphocytes #", "x10^9/L", [r(1.0, 4.5)]),
    p("Monocytes #", "x10^9/L", [r(0.2, 1.0)]), p("Basophils #", "x10^9/L", [r(0.0, 0.1)]),
    p("Eosinophils #", "x10^9/L", [r(0.0, 0.5)]),
    p("Red Blood Cells (RBC)", "x10^12/L", mf(4.5, 5.9, 4.1, 5.1)),
    p("Hemoglobin (HGB)", "g/dL", [ra(14.0, 24.0, B, 0, 1, "Months"), ra(9.5, 14.0, B, 1, 6, "Months"), ra(10.5, 13.5, B, 6, 24, "Months"),
                                    ra(11.5, 13.5, B, 2, 6), ra(11.5, 15.5, B, 6, 12),
                                    ra(13.0, 16.0, M, 12, 18), ra(12.0, 16.0, F, 12, 18),
                                    ra(13.5, 17.5, M, 18, 120), ra(12.0, 15.5, F, 18, 120)]),
    p("Hematocrit (HCT)", "%", mf(41, 53, 36, 46)),
    p("Mean Corpuscular Volume (MCV)", "fL", [r(80, 100)]),
    p("Mean Corpuscular Hemoglobin (MCH)", "pg", [r(27, 33)]),
    p("Mean Corpuscular Hemoglobin Concentration (MCHC)", "g/dL", [r(32, 36)]),
    p("Red Cell Distribution Width (RDW-CV)", "%", [r(11.5, 14.5)]),
    p("Red Cell Distribution Width (RDW-SD)", "fL", [r(39, 46)]),
    p("Platelets (PLT)", "x10^9/L", [r(150, 450)]),
    p("Mean Platelet Volume (MPV)", "fL", [r(7.5, 11.5)]),
])
t(HM, HMG, "Peripheral Blood Film", "Blood Film", WB, [
    pt("Red Blood Cells Morphology"), pt("White Blood Cells Morphology"),
    pt("Platelets"), pt("Parasites"), pt("Comment")], ["Blood Film", "Blood Film and Retic Count"])
single(HM, HMG, "Hemoglobin", "Hb", WB, "g/dL", mf(13.5, 17.5, 12.0, 15.5))
single(HM, HMG, "Platelet Count", "PLT", WB, "x10^9/L", [r(150, 450)])
single(HM, HMG, "Erythrocyte Sedimentation Rate", "ESR", "Whole Blood (Citrate)", "mm/hr", [r(0, 15, M), r(0, 20, F)])
t(HM, HMG, "Reticulocyte Count", "Retic", WB, [
    p("Reticulocytes", "%", [r(0.5, 2.5)]),
    p("Absolute Reticulocyte Count", "x10^9/L", [r(25, 100)])], ["Retic Count"])
t(HM, HMG, "Hemoglobin H Preparation", "HbH Prep", WB, [pt("Hemoglobin H Inclusion Bodies", txt("Negative"))], ["Hb Preparation", "HB.H.PREPARATION"])
t(HM, HMG, "Hemoglobin Electrophoresis", "Hb Electro", WB, [
    p("Hemoglobin A", "%", [r(95, 98)]), p("Hemoglobin A2", "%", [r(2.0, 3.5)]),
    p("Hemoglobin F", "%", [r(None, 1.0)]), p("Hemoglobin S", "%", txt("Absent")),
    p("Hemoglobin C", "%", txt("Absent")), pt("Comment")], ["HB.ELECTROPHORESIS", "Hb Electrophoresis"])
t(HM, HMG, "Serum Protein Electrophoresis", "S.Protein Electro", S, [
    p("Albumin", "%"), p("Alpha-1 Globulin", "%"), p("Alpha-2 Globulin", "%"),
    p("Beta Globulin", "%"), p("Gamma Globulin", "%"), pt("Comment")], ["S.Protein Electrophoresis", "SPEP"])
t(HM, HMG, "Sickling Test", "Sickling", WB, [pt("Sickling Test", txt("Negative"))], ["Sickling Test"])
t(HM, HMG, "G6PD Assay (Quantitative)", "G6PD", WB, [p("G6PD Activity", "U/g Hb", [r(4.6, 13.5)])], ["G6PD", "G6PD Assay"])
t(HM, HMG, "G6PD Screening (Qualitative)", "G6PD Screen", WB, [pt("G6PD Screening", txt("Normal"))])
t(HM, HMG, "Coagulation Tests", "Coag", "Plasma (Citrate)", [
    p("Prothrombin Time (PT)", "sec", [r(11, 13.5)]),
    p("International Normalized Ratio (INR)", "", [r(0.8, 1.2)]),
    p("Activated Partial Thromboplastin Time (aPTT)", "sec", [r(25, 35)]),
], ["Coagulation Tests", "COAGULATION TEST", "PT"])
single(HM, HMG, "Activated Partial Thromboplastin Time", "aPTT", "Plasma (Citrate)", "sec", [r(25, 35)])
single(HM, HMG, "Thrombin Time", "TT", "Plasma (Citrate)", "sec", [r(14, 21)])
single(HM, HMG, "Fibrinogen", "Fib", "Plasma (Citrate)", "mg/dL", [r(200, 400)])
single(HM, HMG, "D-Dimer", "D-Dimer", "Plasma (Citrate)", "µg/mL FEU", [r(None, 0.5)])
single(HM, HMG, "Bleeding Time", "BT", "", "min", [r(2, 7)])
single(HM, HMG, "Clotting Time", "CT", "Whole Blood", "min", [r(5, 15)])
single(HM, HMG, "Factor VIII Assay", "F VIII", "Plasma (Citrate)", "%", [r(50, 150)])
single(HM, HMG, "Factor IX Assay", "F IX", "Plasma (Citrate)", "%", [r(50, 150)])
single(HM, HMG, "von Willebrand Factor Antigen", "vWF:Ag", "Plasma (Citrate)", "%", [r(50, 150)])
single(HM, HMG, "Protein C Activity", "Protein C", "Plasma (Citrate)", "%", [r(70, 140)])
single(HM, HMG, "Protein S Activity", "Protein S", "Plasma (Citrate)", "%", [r(60, 140)])
single(HM, HMG, "Antithrombin III Activity", "AT III", "Plasma (Citrate)", "%", [r(80, 120)])
t(HM, HMG, "Bone Marrow Aspiration", "BMA", "Bone Marrow", [pt("Bone Marrow Aspiration Report")], ["BMA"])
t(HM, HMG, "Bone Marrow Biopsy (Trephine)", "BMB", "Bone Marrow", [pt("Bone Marrow Biopsy Report")], ["BM Biopsy", "BMB"])
single(HM, HMG, "Serum Iron", "Iron", S, "µg/dL", [r(65, 175, M), r(50, 170, F)])
single(HM, HMG, "Total Iron Binding Capacity", "TIBC", S, "µg/dL", [r(250, 450)])
single(HM, HMG, "Transferrin Saturation", "TSAT", S, "%", [r(20, 50)])
single(HM, HMG, "Serum Ferritin", "Ferritin", S, "ng/mL", [r(30, 400, M), r(13, 150, F)], ["Ferritin"])
t(HM, HMG, "Iron Profile", "Iron Profile", S, [
    p("Serum Iron", "µg/dL", [r(65, 175, M), r(50, 170, F)]),
    p("Total Iron Binding Capacity (TIBC)", "µg/dL", [r(250, 450)]),
    p("Transferrin Saturation", "%", [r(20, 50)]),
    p("Serum Ferritin", "ng/mL", [r(30, 400, M), r(13, 150, F)])])
t(HM, HMG, "ABO Blood Group and Rh Typing", "ABO/Rh", WB, [pt("ABO Group"), pt("Rh (D) Type")], ["Blood Group", "ABO"])
t(HM, HMG, "Direct Coombs Test", "DCT", WB, [pt("Direct Coombs Test", txt("Negative"))])
t(HM, HMG, "Indirect Coombs Test", "ICT", S, [pt("Indirect Coombs Test", txt("Negative"))])
t(HM, HMG, "Osmotic Fragility Test", "OFT", WB, [pt("Osmotic Fragility Test")])
t(HM, HMG, "Lupus Anticoagulant", "LA", "Plasma (Citrate)", [pt("Lupus Anticoagulant", txt("Negative"))])
t(HM, HMG, "Glycated Hemoglobin", "HbA1c", WB, [p("Glycated Hemoglobin (HbA1c)", "%", [r(4.0, 5.6, text="Non-diabetic: Up to 5.7\nPre-diabetic: 5.7 - 6.4\nDiabetic: 6.5 or more")])], ["HbA1c"])

single("Vitamins", "Vitamins", "Homocysteine", "Hcy", "Serum", "µmol/L", [r(5, 15)])
single("Vitamins", "Vitamins", "Vitamin A (Retinol)", "Vit A", "Serum", "µg/dL", [r(30, 80)], ["Retinol"])
single("Vitamins", "Vitamins", "Vitamin E (Alpha-Tocopherol)", "Vit E", "Serum", "mg/L", [r(5.5, 17)], ["Tocopherol"])

# =============================== المصليات والفيروسات والمناعة ===============================
SV, SVG, SS = "Serology", "Serology & Immunology", "Serum"
NEG = txt("Negative")
for nm, sh, al in [
    ("Hepatitis B Surface Antigen (HBsAg)", "HBsAg", ["HBs Ag", "Hepatitis B Surface Antigen"]),
    ("Hepatitis B Surface Antibody (Anti-HBs)", "Anti-HBs", ["HBs Ab", "HBsAb"]),
    ("Hepatitis B e Antigen (HBeAg)", "HBeAg", ["HBe Ag"]),
    ("Hepatitis B e Antibody (Anti-HBe)", "Anti-HBe", ["HBe Ab"]),
    ("Hepatitis B Core Antibody Total (Anti-HBc)", "Anti-HBc", ["HBc Ab", "HBcAb"]),
    ("Hepatitis C Virus Antibody (Anti-HCV)", "HCV Ab", ["HCV", "Anti HCV"]),
    ("Hepatitis A Virus IgM (Anti-HAV IgM)", "HAV IgM", ["HAV"]),
    ("HIV 1/2 Antibody/Antigen", "HIV", ["HIV Ab", "AIDS"]),
    ("Syphilis RPR/VDRL", "VDRL", ["RPR", "Syphilis"]),
    ("Treponema pallidum Hemagglutination (TPHA)", "TPHA", []),
    ("Brucella Antibodies (Rose Bengal)", "Brucella", ["Brucella Ab"]),
    ("Helicobacter pylori Antigen (Stool)", "H.pylori Ag", ["H. pylori", "HP Ag"]),
    ("Helicobacter pylori Antibody", "H.pylori Ab", ["HP Ab"]),
    ("Antinuclear Antibody (ANA)", "ANA", []),
    ("Anti-double Stranded DNA (Anti-dsDNA)", "Anti-dsDNA", ["dsDNA"]),
    ("Toxoplasma IgG", "Toxo IgG", []), ("Toxoplasma IgM", "Toxo IgM", []),
    ("Rubella IgG", "Rubella IgG", []), ("Rubella IgM", "Rubella IgM", []),
    ("Cytomegalovirus IgG (CMV IgG)", "CMV IgG", []), ("Cytomegalovirus IgM (CMV IgM)", "CMV IgM", []),
    ("Herpes Simplex Virus IgG (HSV IgG)", "HSV IgG", []), ("Herpes Simplex Virus IgM (HSV IgM)", "HSV IgM", []),
    ("Epstein-Barr Virus VCA IgM (EBV)", "EBV IgM", ["EBV"]),
    ("Pregnancy Test (hCG, Urine)", "UPT", ["Pregnancy Test", "HCG Urine"]),
    ("Widal Test (Salmonella typhi O/H)", "Widal", ["Widal"]),
]:
    t(SV, SVG, nm, sh, SS, [pt(nm, NEG)], al)
single(SV, SVG, "C-Reactive Protein (CRP)", "CRP", SS, "mg/L", [r(None, 6)], ["CRP"])
single(SV, SVG, "Rheumatoid Factor (RF)", "RF", SS, "IU/mL", [r(None, 14)], ["RF", "Rheumatoid factor"])
single(SV, SVG, "Anti-Streptolysin O Titre (ASO)", "ASO", SS, "IU/mL", [r(None, 200)], ["ASO", "ASOT"])
single(SV, SVG, "Anti-CCP Antibodies", "Anti-CCP", SS, "U/mL", [r(None, 17)], ["CCP"])
t(SV, SVG, "Hepatitis B Profile", "HBV Profile", SS, [
    pt("HBsAg", NEG), pt("Anti-HBs"), pt("HBeAg", NEG), pt("Anti-HBe"), pt("Anti-HBc Total")], ["Hepatitis B Markers"])
t(SV, SVG, "TORCH Screen IgG/IgM", "TORCH", SS, [
    pt("Toxoplasma IgG"), pt("Toxoplasma IgM", NEG), pt("Rubella IgG"), pt("Rubella IgM", NEG),
    pt("CMV IgG"), pt("CMV IgM", NEG), pt("HSV IgG"), pt("HSV IgM", NEG)], ["TORCH"])

# =============================== الأنسجة والخلايا ===============================
HP = "Histopathology"
t(HP, "Histopathology", "Histopathology Report (Biopsy)", "Biopsy", "Tissue", [pt("Specimen"), pt("Gross Description"), pt("Microscopic Description"), pt("Diagnosis")], ["Biopsy", "Histopathology"])
t(HP, "Histopathology", "Cytology Report (FNAC)", "FNAC", "Aspirate", [pt("Specimen"), pt("Microscopic Description"), pt("Diagnosis")], ["FNA", "Cytology"])
t(HP, "Histopathology", "Pap Smear", "Pap", "Cervical Smear", [pt("Adequacy"), pt("Microscopic Description"), pt("Diagnosis")], ["Pap Smear"])
t(HP, "Histopathology", "Immunohistochemistry Report (IHC)", "IHC", "Tissue", [pt("Markers"), pt("Interpretation")], ["IHC"])


# =============== من سجل المرضى (قائمة التحاليل الكاملة) — يُضاف الناقص فقط ===============
single('Hematology', 'Iron Studies', 'Transferrin', 'Transferrin', 'Blood (EDTA)', 'mg/dL', [r(200, 400, B)])
single('Hematology', 'Hemolysis Work-up', 'Haptoglobin', 'Haptoglobin', 'Blood (EDTA)', 'mg/dL', [r(83, 267, B)])
single('Hematology', 'Hemolysis Work-up', 'Plasma Hemoglobin', 'Plasma Hemoglobin', 'Blood (EDTA)', 'mg/dL', [r(None, 5, B)])
single('Hematology', 'Hemolysis Work-up', 'Erythropoietin', 'Erythropoietin', 'Blood (EDTA)', 'mU/mL', [r(4, 26, B)])
single('Coagulation', 'Factor Assays', 'Factor VII', 'Factor VII', 'Citrated Plasma', '%', [r(60, 130, B)])
single('Coagulation', 'Factor Assays', 'Factor X', 'Factor X', 'Citrated Plasma', '%', [r(60, 130, B)])
single('Coagulation', 'Factor Assays', 'Factor XI', 'Factor XI', 'Citrated Plasma', '%', [r(60, 130, B)])
single('Coagulation', 'Factor Assays', 'Factor XII', 'Factor XII', 'Citrated Plasma', '%', [r(60, 130, B)])
single('Coagulation', 'Factor Assays', 'von Willebrand Factor Activity (RCo)', 'von Willebrand Factor Activity (RCo)', 'Citrated Plasma', '%', [r(50, 150, B)])
single('Coagulation', 'Thrombophilia Screen', 'ADAMTS13 Activity', 'ADAMTS13 Activity', 'Citrated Plasma', '%', [r(60, None, B)])
single('Biochemistry', 'Liver function tests', 'Bilirubin Indirect', 'Bilirubin Indirect', 'Serum', 'mg/dl', [r(0.2, 0.7, B)])
single('Biochemistry', 'Electrolytes & Minerals', 'Osmolality (Serum)', 'Osmolality (Serum)', 'Serum', 'mOsm/kg', [r(275, 295, B)])
single('Biochemistry', 'Lipid profile', 'S. VLDL', 'S. VLDL', 'Serum', 'mg/dl', [r(None, 20, B)])
single('Biochemistry', 'Lipid profile', 'Apolipoprotein A-1', 'Apolipoprotein A-1', 'Serum', 'mg/dL', [r(120, None, M), r(140, None, F)])
single('Biochemistry', 'Lipid profile', 'Apolipoprotein B', 'Apolipoprotein B', 'Serum', 'mg/dL', [r(None, 90, B)])
single('Biochemistry', 'Lipid profile', 'Lipoprotein (a)', 'Lipoprotein (a)', 'Serum', 'mg/dL', [r(None, 30, B)])
single('Biochemistry', 'Cardiac markers', 'CK (Total)', 'CK (Total)', 'Serum', 'U/L', [r(55, 170, M), r(30, 135, F)])
t('Biochemistry', 'Cardiac markers', 'Troponin T', 'Troponin T', 'Serum', [pt('Troponin T', [(B, None, None, '≤ 0.01')])])
single('Biochemistry', 'Cardiac markers', 'BNP', 'BNP', 'Serum', 'pg/mL', [r(None, 100, B)])
single('Biochemistry', 'Cardiac markers', 'NT-proBNP', 'NT-proBNP', 'Serum', 'pg/mL', [r(None, 300, B)])
single('Biochemistry', 'Cardiac markers', 'Myoglobin', 'Myoglobin', 'Serum', 'µg/L', [r(None, 100, B)])
single('Biochemistry', 'Other chemistry', 'Ceruloplasmin', 'Ceruloplasmin', 'Serum', 'mg/dL', [r(25, 43, B)])
single('Biochemistry', 'Other chemistry', 'Lead (Blood)', 'Lead (Blood)', 'Serum', 'µg/dL', [r(None, 5, B)])
single('Hormones', 'Thyroid function', 'Thyroglobulin', 'Thyroglobulin', 'Serum', 'ng/mL', [r(None, 20, B)])
t('Hormones', 'Reproductive hormones', '17-OH Progesterone', '17-OH Progesterone', 'Serum', [pt('17-OH Progesterone', [r(None, 220, M), (F, None, None, 'Follicular < 80\nLuteal < 285')])])
single('Hormones', 'Adrenal & pituitary', 'Cortisol (4 PM)', 'Cortisol (4 PM)', 'Serum', 'µg/dL', [r(None, 10, B)])
t('Hormones', 'Adrenal & pituitary', 'Aldosterone', 'Aldosterone', 'Serum', [pt('Aldosterone', [(B, None, None, '≤ 10')])])
single('Hormones', 'Adrenal & pituitary', 'Renin Activity', 'Renin Activity', 'Serum', 'ng/mL/hr', [r(0.3, 2.5, B)])
t('Hormones', 'Calcium & bone', 'Calcitonin', 'Calcitonin', 'Serum', [pt('Calcitonin', [(M, None, None, '≤ 10'), (F, None, None, '≤ 5')])])
t('Hormones', 'Calcium & bone', 'IGF-1', 'IGF-1', 'Serum', [pt('IGF-1', [(B, None, None, 'Age 16-24: 182 - 780\nAge 25-39: 114 - 492\nAge 40-54: 90 - 360\nAge ≥ 55: 71 - 290')])])
single('Vitamins', 'Vitamins', 'Vitamin C', 'Vitamin C', 'Serum', 'mg/dL', [r(0.4, 1.5, B)])
single('Vitamins', 'Vitamins', '1,25-(OH)2 Vitamin D', '1,25-(OH)2 Vitamin D', 'Serum', 'pg/mL', [r(15, 60, B)])
single('Vitamins', 'Minerals & trace elements', 'Copper', 'Copper', 'Serum', 'µg/dL', [r(100, 200, B)])
t('Serology', 'Inflammatory markers', 'hs-CRP', 'hs-CRP', 'Serum', [pt('hs-CRP', [(B, None, None, 'Low risk < 1.0\nAverage risk 1.0 - 3.0\nHigh risk > 3.0')])])
single('Serology', 'Autoimmune', 'Anti-tTG IgA', 'Anti-tTG IgA', 'Serum', 'U/mL', [r(None, 4, B)])
single('Serology', 'Autoimmune', 'Anticardiolipin IgG', 'Anticardiolipin IgG', 'Serum', 'GPL', [r(None, 20, B)])
single('Serology', 'Autoimmune', 'Anticardiolipin IgM', 'Anticardiolipin IgM', 'Serum', 'MPL', [r(None, 20, B)])
single('Serology', 'Immunoglobulins & complement', 'IgG', 'IgG', 'Serum', 'mg/dL', [r(800, 1500, B)])
single('Serology', 'Immunoglobulins & complement', 'IgA', 'IgA', 'Serum', 'mg/dL', [r(90, 325, B)])
single('Serology', 'Immunoglobulins & complement', 'IgM', 'IgM', 'Serum', 'mg/dL', [r(45, 150, B)])
single('Serology', 'Immunoglobulins & complement', 'IgE (Total)', 'IgE (Total)', 'Serum', 'IU/mL', [r(None, 380, B)])
single('Serology', 'Immunoglobulins & complement', 'C3', 'C3', 'Serum', 'mg/dL', [r(100, 233, B)])
single('Serology', 'Immunoglobulins & complement', 'C4', 'C4', 'Serum', 'mg/dL', [r(14, 48, B)])
t('Virology', 'Hepatitis B', 'Anti-HBc IgM', 'Anti-HBc IgM', 'Serum', [pt('Anti-HBc IgM', [(B, None, None, 'Non-reactive')])])
t('Virology', 'Hepatitis B', 'HBV DNA (PCR)', 'HBV DNA (PCR)', 'Serum', [pt('HBV DNA (PCR)', [(B, None, None, 'Not detected')])])
t('Virology', 'Hepatitis C', 'HCV RNA (PCR)', 'HCV RNA (PCR)', 'Serum', [pt('HCV RNA (PCR)', [(B, None, None, 'Not detected')])])
t('Virology', 'Hepatitis A', 'HAV IgG', 'HAV IgG', 'Serum', [pt('HAV IgG', [(B, None, None, 'Non-reactive')])])
t('Virology', 'TORCH & other viruses', 'EBV VCA IgG', 'EBV VCA IgG', 'Serum', [pt('EBV VCA IgG', [(B, None, None, 'Negative')])])
t('Virology', 'TORCH & other viruses', 'COVID-19 Ag', 'COVID-19 Ag', 'Serum', [pt('COVID-19 Ag', [(B, None, None, 'Negative')])])
single('Biochemistry', 'Urine chemistry', 'Creatinine Clearance', 'Creatinine Clearance', 'Urine', 'mL/min/1.73m²', [r(90, 140, B)])
single('Biochemistry', 'Urine chemistry', 'Urine Calcium (24h)', 'Urine Calcium (24h)', 'Urine', 'mg/24h', [r(None, 300, M), r(None, 250, F)])
single('Biochemistry', 'Urine chemistry', 'Urine Uric Acid (24h)', 'Urine Uric Acid (24h)', 'Urine', 'mg/24h', [r(250, 750, B)])
t('Parasitology', 'Stool examination', 'Occult Blood (Stool)', 'Stool', 'Stool', [pt('Occult Blood (Stool)', [(B, None, None, 'Negative')])])
t('Parasitology', 'Stool examination', 'Giardia Ag (Stool)', 'Stool', 'Stool', [pt('Giardia Ag (Stool)', [(B, None, None, 'Negative')])])
t('Parasitology', 'Stool examination', 'Entamoeba histolytica Ag (Stool)', 'Stool', 'Stool', [pt('Entamoeba histolytica Ag (Stool)', [(B, None, None, 'Negative')])])
t('Parasitology', 'Blood parasites', 'Malaria Film', 'Malaria Film', 'Blood', [pt('Malaria Film', [(B, None, None, 'Not seen')])])
t('Parasitology', 'Blood parasites', 'Malaria Ag (Rapid)', 'Malaria Ag (Rapid)', 'Blood', [pt('Malaria Ag (Rapid)', [(B, None, None, 'Negative')])])
t('Parasitology', 'Blood parasites', 'Leishmania rK39', 'Leishmania rK39', 'Blood', [pt('Leishmania rK39', [(B, None, None, 'Negative')])])
t('Urinalysis', 'Urine examination', 'General Urine Examination (GUE)', 'GUE', 'Urine', [
    pt('Urine Color', [(B, None, None, 'Pale yellow')]),
    pt('Urine Appearance', [(B, None, None, 'Clear')]),
    p('Urine Specific Gravity', '', [r(1.002, 1.03, B)]),
    p('Urine pH', '', [r(4.5, 8, B)]),
    pt('Urine Protein', [(B, None, None, 'Negative')]),
    pt('Urine Glucose', [(B, None, None, 'Negative')]),
    pt('Urine Ketones', [(B, None, None, 'Negative')]),
    pt('Urine Blood', [(B, None, None, 'Negative')]),
    pt('Urine Bilirubin', [(B, None, None, 'Negative')]),
    p('Urine Urobilinogen', 'mg/dL', [r(0.2, 1, B)]),
    pt('Urine Nitrite', [(B, None, None, 'Negative')]),
    pt('Urine Leukocyte Esterase', [(B, None, None, 'Negative')]),
    p('Urine Pus Cells', '/HPF', [r(0, 5, B)]),
    p('Urine RBC', '/HPF', [r(0, 2, B)]),
    pt('Urine Epithelial Cells', [(B, None, None, 'Few')]),
    pt('Urine Casts', [(B, None, None, 'None')]),
    pt('Urine Crystals', [(B, None, None, 'None')])])
t('Parasitology', 'Stool examination', 'General Stool Examination (GSE)', 'GSE', 'Stool', [
    pt('Stool Color', [(B, None, None, 'Brown')]),
    pt('Stool Consistency', [(B, None, None, 'Formed')]),
    pt('Stool Mucus', [(B, None, None, 'Absent')]),
    p('Stool Pus Cells', '/HPF', [r(0, 2, B)]),
    pt('Stool RBC', [(B, None, None, 'Nil')]),
    pt('Stool Ova / Cysts / Parasites', [(B, None, None, 'Not seen')])])

CATALOG = _CATALOG


def _norm(s):
    return " ".join((s or "").lower().split())


def _code(base_name, used):
    import re
    base = re.sub(r"[^A-Za-z0-9]+", "", base_name).upper()[:12] or "TEST"
    code, n = base, 1
    while code in used:
        n += 1
        code = "%s%d" % (base, n)
    used.add(code)
    return code


def _existing(db):
    names, codes = set(), set()
    for row in db.execute("SELECT code, name, short_name FROM test_definitions").fetchall():
        names.update({_norm(row["name"]), _norm(row["short_name"]), _norm(row["code"])})
        codes.add(row["code"])
    names.discard("")
    return names, codes


def preview(db):
    """هل كل تحليل جديد أم موجود أصلاً (لشاشة المعاينة)."""
    names, _ = _existing(db)
    out = []
    for e in CATALOG:
        keys = {_norm(e["name"]), _norm(e["short"])} | {_norm(a) for a in e["aliases"]}
        out.append((e, bool(keys & names)))
    return out


def install(db, depts=None):
    """يضيف التحاليل الناقصة فقط. يرجّع {added, skipped, params, ranges}. لا يعمل commit."""
    names, codes = _existing(db)
    added = skipped = nparams = nranges = 0
    for e in CATALOG:
        if depts and e["dept"] not in depts:
            continue
        keys = {_norm(e["name"]), _norm(e["short"])} | {_norm(a) for a in e["aliases"]}
        if keys & names:
            skipped += 1
            continue
        code = _code(e["short"] or e["name"], codes)
        cur = db.execute(
            "INSERT INTO test_definitions (code, name, short_name, department, report_group, sample_type, price, is_active, is_examining_test) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 1, 0)",
            (code, e["name"], e["short"], e["dept"], e["group"], e["sample"]))
        tid = cur.lastrowid
        names.update(keys)
        added += 1
        for i, prm in enumerate(e["params"], start=1):
            pc = db.execute(
                "INSERT INTO test_parameters (test_definition_id, name, unit, result_type, sort_order) VALUES (?, ?, ?, ?, ?)",
                (tid, prm["name"], prm["unit"], prm["type"], i))
            nparams += 1
            for tup in prm["ranges"]:
                g, lo, hi, text = tup[:4]
                af, at, au = (tup[4], tup[5], tup[6]) if len(tup) > 4 else (0, 120, "Years")
                db.execute(
                    "INSERT INTO reference_ranges (test_parameter_id, gender, age_from, age_from_unit, age_to, age_to_unit, low, high, range_text) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (pc.lastrowid, g, af, au, at, au, lo, hi, text))
                nranges += 1
    return {"added": added, "skipped": skipped, "params": nparams, "ranges": nranges}


def auto_install(get_db, after=None, flag="catalog_auto_v2"):
    """مرة واحدة لكل جهاز: بعد بدء البرنامج بـ30 ثانية يثبّت الكتالوج الناقص فقط (لا يعدّل ولا يحذف). يعمل بخيط خلفي ولا يوقف البرنامج."""
    import threading, time

    def run():
        time.sleep(30)
        try:
            db = get_db()
            try:
                r = db.execute("SELECT value FROM settings WHERE key=?", (flag,)).fetchone()
                if r and r["value"] == "1":
                    return
                res = install(db)
                if db.execute("SELECT 1 FROM settings WHERE key=?", (flag,)).fetchone():
                    db.execute("UPDATE settings SET value='1' WHERE key=?", (flag,))
                else:
                    db.execute("INSERT INTO settings (key, value) VALUES (?, '1')", (flag,))
                db.commit()
                if after:
                    try:
                        after(db)
                    except Exception:
                        pass
            finally:
                db.close()
        except Exception:
            pass
    threading.Thread(target=run, name="catalog-auto", daemon=True).start()

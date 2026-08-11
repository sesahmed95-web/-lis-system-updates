(function () {
  const root = document.documentElement;
  const saved = localStorage.getItem("lis-theme");
  if (saved === "dark") root.classList.add("dark");

  window.toggleTheme = function () {
    root.classList.toggle("dark");
    localStorage.setItem("lis-theme", root.classList.contains("dark") ? "dark" : "light");
  };

  window.confirmVerify = function () {
    return confirm("Confirm result verification and approval?");
  };
})();

// ------------------------------------------------------------------
// حقول النتائج النصية (RBC/WBC/Platelets/Conclusion...): تكبير تلقائي
// لصندوق الكتابة حتى يظهر كل النص المكتوب دائمًا، بلا قص أو تمرير مخفي.
// ------------------------------------------------------------------
window.lisAutoResize = function (el) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = (el.scrollHeight + 2) + "px";
};

// ------------------------------------------------------------------
// تدقيق كتابي اختياري لحقول النتائج النصية: يصحح فقط تباعد الأحرف
// وحرف البداية الكبير وعلامة الترقيم بالنهاية — لا يترجم ولا يستبدل أي
// كلمة أبدًا، فتبقى كل المصطلحات الطبية بلغتها اللاتينية الأصلية تمامًا
// متل ما كتبها المستخدم. يُستدعى فقط لما المستخدم يضغط الزر بنفسه.
// ------------------------------------------------------------------
window.lisCleanupText = function (el) {
  if (!el) return;
  var text = el.value;
  if (!text || !text.trim()) return;
  text = text.replace(/\s+/g, " ").trim();
  text = text.charAt(0).toUpperCase() + text.slice(1);
  if (!/[.!?:]$/.test(text)) text += ".";
  el.value = text;
  window.lisAutoResize(el);
};

// ------------------------------------------------------------------
// حساب Corrected Reticulocyte Count تلقائيًا من Reticulocyte count
// وقيمة HCT الخاصة بنفس المريض/الزيارة (من تحليل CBC):
//   Corrected Retic % = Retic % × (HCT المريض ÷ HCT الطبيعي)
//   HCT الطبيعي: 45% للرجال، 42% للنساء.
// القيمة تبقى قابلة للتعديل اليدوي دائمًا؛ بمجرد ما المستخدم يعدلها
// يدويًا يتوقف الحساب التلقائي عن الكتابة فوقها إلا إذا ضغط زر
// "إعادة الحساب" بنفسه.
// ------------------------------------------------------------------
function lisNormalHCT(gender) {
  var g = (gender || "").toString().trim().toLowerCase();
  if (g.indexOf("f") === 0 || g.indexOf("أنث") === 0 || g.indexOf("انث") === 0) return 42;
  return 45;
}

window.lisComputeCorrectedRetic = function (reticVal, hct, gender) {
  var retic = parseFloat(reticVal);
  var h = parseFloat(hct);
  if (isNaN(retic) || isNaN(h) || h <= 0) return null;
  return Math.round(retic * (h / lisNormalHCT(gender)) * 10) / 10;
};

window.lisForceRecalcCorrectedRetic = function (btn) {
  var table = btn.closest("table") || document;
  var reticInput = table.querySelector('[data-param-name="Reticulocyte count"]');
  var correctedInput = table.querySelector('[data-param-name="Corrected Retic count"]');
  if (!reticInput || !correctedInput) return;
  var val = window.lisComputeCorrectedRetic(reticInput.value, window.LIS_PATIENT_HCT, window.LIS_PATIENT_GENDER);
  if (val === null) {
    alert("تأكد من إدخال Reticulocyte count أولاً، ومن توفر قيمة HCT لهذا المريض (من نتيجة CBC بنفس الزيارة).");
    return;
  }
  correctedInput.value = val;
  correctedInput.dataset.autoFilled = "1";
};

document.addEventListener("input", function (e) {
  var el = e.target;
  if (!el || !el.matches) return;
  if (el.classList.contains("lis-autoresize")) window.lisAutoResize(el);
  if (el.matches('[data-param-name="Reticulocyte count"]')) {
    var table = el.closest("table");
    var correctedInput = table && table.querySelector('[data-param-name="Corrected Retic count"]');
    if (correctedInput && correctedInput.dataset.autoFilled !== "0") {
      var val = window.lisComputeCorrectedRetic(el.value, window.LIS_PATIENT_HCT, window.LIS_PATIENT_GENDER);
      if (val !== null) { correctedInput.value = val; correctedInput.dataset.autoFilled = "1"; }
    }
  }
  if (el.matches('[data-param-name="Corrected Retic count"]')) {
    el.dataset.autoFilled = "0"; // المستخدم لمسها يدويًا — نتوقف عن الكتابة فوقها
  }
});

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("textarea.lis-autoresize").forEach(window.lisAutoResize);
  // أول تحميل للصفحة: إذا Reticulocyte count فيها قيمة محفوظة وCorrected
  // Retic count لسا فاضية، نحسبها مباشرة بدون ما ينتظر المستخدم يكتب شي.
  document.querySelectorAll('[data-param-name="Corrected Retic count"]').forEach(function (correctedInput) {
    if (correctedInput.value) return;
    var table = correctedInput.closest("table");
    var reticInput = table && table.querySelector('[data-param-name="Reticulocyte count"]');
    if (reticInput && reticInput.value) {
      var val = window.lisComputeCorrectedRetic(reticInput.value, window.LIS_PATIENT_HCT, window.LIS_PATIENT_GENDER);
      if (val !== null) correctedInput.value = val;
    }
  });
});

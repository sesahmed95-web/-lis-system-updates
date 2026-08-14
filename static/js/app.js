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
// إرسال طلب POST بسيط (اعتماد/فتح للتعديل/واتساب) عبر نموذج مؤقت
// مستقل يُبنى ويُرسل ثم يُحذف فورًا — لا يُضمَّن أبداً داخل نموذج
// آخر بالصفحة. هذا يتفادى مشكلة تداخل عناصر <form> ببعضها (غير
// مسموح بالـ HTML أصلاً، ويكسر النموذج الأكبر المحيط بها فيسبب فقدان
// أي تعديل بحقول تأتي بعده بنفس الصفحة، مثل حقل Conclusion).
// ------------------------------------------------------------------
window.lisPostAction = function (url, fields, confirmMsg) {
  if (confirmMsg && !confirm(confirmMsg)) return;
  var f = document.createElement("form");
  f.method = "POST";
  f.action = url;
  f.style.display = "none";
  Object.keys(fields || {}).forEach(function (k) {
    var inp = document.createElement("input");
    inp.type = "hidden";
    inp.name = k;
    inp.value = fields[k] == null ? "" : fields[k];
    f.appendChild(inp);
  });
  document.body.appendChild(f);
  f.submit();
};

// ------------------------------------------------------------------
// روابط الطباعة (id/class="print-link") تفتح بنافذة منبثقة صغيرة
// بدل تبويب متصفح كامل. البرنامج نفسه يفتح بوضع "تطبيق" بدون شريط
// تبويبات/عنوان (راجع run_windows.bat: chrome --app=...)، لكن أي
// رابط target="_blank" يُفتح منه يطلع بنافذة Chrome عادية كاملة
// (بتبويباتها وأشرطتها) لأن وضع "--app" ينطبق فقط على أول نافذة —
// فتح الرابط عبر window.open بخصائص "popup" يخلي المتصفح يرسمها
// بنافذة مجرّدة بسيطة قريبة من شكل نافذة برنامج مستقلة.
// ------------------------------------------------------------------
document.addEventListener("click", function (e) {
  var a = e.target.closest && e.target.closest("a.print-link, a#printAllLink");
  if (!a || !a.href) return;
  e.preventDefault();
  var w = Math.min(1000, Math.round(screen.availWidth * 0.9));
  var h = Math.min(1200, Math.round(screen.availHeight * 0.92));
  var left = Math.round((screen.availWidth - w) / 2);
  var top = Math.round((screen.availHeight - h) / 2);
  window.open(a.href, "_blank",
    "popup=yes,width=" + w + ",height=" + h + ",left=" + left + ",top=" + top +
    ",toolbar=no,location=no,menubar=no,status=no,scrollbars=yes,resizable=yes");
});

// ------------------------------------------------------------------
// تدقيق كتابي اختياري لحقول النتائج النصية: يصحح فقط تباعد الأحرف
// وحرف البداية الكبير وعلامة الترقيم بالنهاية — لا يترجم ولا يستبدل أي
// كلمة أبدًا، فتبقى كل المصطلحات الطبية بلغتها اللاتينية الأصلية تمامًا
// متل ما كتبها المستخدم. يُستدعى فقط لما المستخدم يضغط الزر بنفسه.
// ------------------------------------------------------------------
// يعبّي نص الكليشة الجاهز (زر ✓ Normal) بأمان — يقرأ النص من data-attribute
// بدل تضمينه مباشرة بسطر onclick، حتى ما ينكسر الزر لو النص المكتوب فيه
// علامة اقتباس مفردة (') أو أي رمز خاص ثاني.
window.lisFillNormalText = function (btn) {
  var el = document.getElementById(btn.dataset.target);
  if (el) {
    el.value = btn.dataset.normalText;
    el.focus();
    if (typeof el.dispatchEvent === "function") {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }
};

window.lisCleanupText = function (el) {
  if (!el) return;
  var text = el.value;
  if (!text || !text.trim()) return;
  // يصحح فقط تكرار المسافات/التابات ضمن كل سطر — لا يلمس أسطر النص
  // الجديدة (\n) أبداً، حتى لا يفكك أسطر النجمة/السهم اللي يضيفها زر
  // التنسيق البسيط بحقل الـ addEventListener("click" (كانت \s+ سابقاً تدمج كل الأسطر
  // بسطر واحد وتفقد الرموز موضعها ببداية كل سطر).
  text = text.replace(/[^\S\n]+/g, " ")
             .split("\n").map(function (line) { return line.trim(); }).join("\n")
             .trim();
  text = text.charAt(0).toUpperCase() + text.slice(1);
  if (!/[.!?:]$/.test(text)) text += ".";
  el.value = text;
  window.lisAutoResize(el);
};

// ------------------------------------------------------------------
// زر التنسيق البسيط فوق حقل الـ addEventListener("click": يضيف الرمز الملوّن (★ أو →
// أو ⇒ أو ▶ أو ? أو !) عند موضع المؤشر بالضبط — بدون فرض سطر جديد — حتى يقدر المستخدم
// يحط أكثر من رمز بنفس السطر (مثلاً نجمة أول السطر وسهم بعدها بنفس
// السطر)، أو يضغط Enter بنفسه قبل الزر لو يريد سطر جديد فعلاً. المؤشر
// يترك مباشرة بعد الرمز ليكمل المستخدم الكتابة.
// ------------------------------------------------------------------
window.lisInsertaddEventListener("click"Marker = function (textareaId, marker) {
  var el = document.getElementById(textareaId);
  if (!el || el.readOnly) return;
  el.focus();
  var lisInsertConclusionMarker = el.selectionStart;
  var end = el.selectionEnd;
  var val = el.value;
  var insertText = marker + " ";
  el.value = val.slice(0, start) + insertText + val.slice(end);
  var newPos = start + insertText.length;
  el.selectionStart = el.selectionEnd = newPos;
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

// تحفظ تعديلات النموذج الحالي (لو أي تغيير غير محفوظ — كحذف نجمة/سهم من
// حقل addEventListener("click") قبل ما تفتح صفحة الطباعة، حتى ما يطلع بالتقرير محتوى
// قديم لسا ما انحفظ. تفتح صفحة الطباعة كنافذة منبثقة مخصصة (بدون شريط
// عنوان/إشارات مرجعية) بدل تبويب متصفح عادي — هذا هو "نافذة خاصة
// بالبرنامج" اللي المستخدم يريدها لتقارير الطباعة.
window.lisSaveThenPrint = function (evt, formSelector, printUrl) {
  evt.preventDefault();
  var popupFeatures = "popup,width=880,height=1000,toolbar=no,menubar=no,location=no,status=no,scrollbars=yes";
  // نفتح النافذة فوراً (فارغة) ضمن نفس تفاعل الضغطة مباشرة — حتى
  // المتصفح ما يحجبها كنافذة منبثقة (لازم window.open يصير مباشرة
  // جوه معالج الضغط، مو بعد انتظار fetch). نوجّهها لرابط الطباعة
  // بعدين لما ينخلص الحفظ.
  var w = window.open("", "lisPrintWindow", popupFeatures);
  var form = document.querySelector(formSelector);
  function goToPrint() {
    if (w && !w.closed) { w.location.href = printUrl; w.focus(); }
    else { window.location.href = printUrl; } // المتصفح حاظر النافذة المنبثقة — رجوع للتبويب العادي
  }
  if (!form) { goToPrint(); return; }
  fetch(form.action || window.location.href, {
    method: "POST",
    body: new FormData(form),
    credentials: "same-origin",
  }).catch(function () { /* حتى لو فشل الحفظ بالشبكة، نفتح الطباعة بآخر نسخة محفوظة سابقاً */ })
    .finally(goToPrint);
};


// ------------------------------------------------------------
//      Corrected Retic Count             Retic + HCT +      
//       : Corrected Retic % = Retic % x (HCT        / HCT        )
//                                    (    < 0.1)                 
//       null (                /    ).                         .
// ------------------------------------------------------------
window.lisComputeCorrectedRetic = function (reticValue, patientHct, patientGender) {
  var retic = parseFloat(reticValue);
  if (isNaN(retic)) return null;
  if (patientHct === null || patientHct === undefined || patientHct === "null") return null;
  var hct = parseFloat(patientHct);
  if (isNaN(hct) || hct <= 0) return null;
  var normalHct = window.lisNormalHCT ? window.lisNormalHCT(patientGender) : 45;
  var corrected = retic * (hct / normalHct);
  corrected = Math.round(corrected * 100) / 100;
  if (corrected >= retic) return null;
  return corrected;
};

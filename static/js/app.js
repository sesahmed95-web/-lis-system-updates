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
  // التنسيق البسيط بحقل الـ Conclusion (كانت \s+ سابقاً تدمج كل الأسطر
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
// زر التنسيق البسيط فوق حقل الـ Conclusion: يضيف الرمز الملوّن (★ أو →
// أو ⇒ أو ▶ أو ? أو !) عند موضع المؤشر بالضبط — بدون فرض سطر جديد — حتى يقدر المستخدم
// يحط أكثر من رمز بنفس السطر (مثلاً نجمة أول السطر وسهم بعدها بنفس
// السطر)، أو يضغط Enter بنفسه قبل الزر لو يريد سطر جديد فعلاً. المؤشر
// يترك مباشرة بعد الرمز ليكمل المستخدم الكتابة.
// ------------------------------------------------------------------
window.lisInsertConclusionMarker = function (textareaId, marker) {
  var el = document.getElementById(textareaId);
  if (!el || el.readOnly) return;
  el.focus();
  var start = el.selectionStart;
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
//   HCT الطبيعي: يُجلب من جدول القيم المرجعية حسب عمر/جنس المريض
//   (window.LIS_HCT_NORMAL، يحقنه الخادم) — وإذا ما توفر، رجوع احتياطي
//   لقيمة ثابتة تقريبية: 45% للرجال، 42% للنساء.
// القيمة تبقى قابلة للتعديل اليدوي دائمًا؛ بمجرد ما المستخدم يعدلها
// يدويًا يتوقف الحساب التلقائي عن الكتابة فوقها إلا إذا ضغط زر
// "إعادة الحساب" بنفسه.
// إذا القيمة المصححة قريبة جداً من الرتك العادي (الفرق بينهما ضئيل)،
// ما فيها فائدة سريرية إضافية — نترك الحقل فاضياً بدل تعبئته، وبالتالي
// يختفي "Corrected Retic count" تلقائيًا من التقرير المطبوع (القوالب
// لا تعرض الحقل أصلاً إذا كان فاضياً).
// ------------------------------------------------------------------
window.lisNormalHCT = function (gender) {
  if (typeof window.LIS_HCT_NORMAL === "number" && !isNaN(window.LIS_HCT_NORMAL) && window.LIS_HCT_NORMAL > 0) {
    return window.LIS_HCT_NORMAL;
  }
  var g = (gender || "").toString().trim().toLowerCase();
  if (g.indexOf("f") === 0 || g.indexOf("أنث") === 0 || g.indexOf("انث") === 0) return 42;
  return 45;
};

window.lisForceRecalcCorrectedRetic = function (btn) {
  var table = btn.closest("table") || document;
  var reticInput = table.querySelector('[data-param-name="Reticulocyte count"]');
  var correctedInput = table.querySelector('[data-param-name="Corrected Retic count"]');
  if (!reticInput || !correctedInput) return;
  var val = window.lisComputeCorrectedRetic(reticInput.value, window.LIS_PATIENT_HCT, window.LIS_PATIENT_GENDER);
  if (val === null) {
    correctedInput.value = "";
    correctedInput.dataset.autoFilled = "1";
    alert("تأكد من إدخال Reticulocyte count أولاً، ومن توفر قيمة HCT لهذا المريض (من نتيجة CBC بنفس الزيارة). لو القيمتان متوفرتان، فالقيمة المصححة قريبة جداً من الرتك العادي ولا داعي لإظهارها.");
    return;
  }
  correctedInput.value = val;
  correctedInput.dataset.autoFilled = "1";
};

// ------------------------------------------------------------------
// حساب القيم المطلقة (Absolute Counts) لأنواع كريات الدم البيضاء
// (LY#/MO#/NE#/EO#/BA#) تلقائيًا من نسبتها المئوية × عدد WBCs الكلي:
//   القيمة المطلقة = (النسبة% ÷ 100) × WBCs
// نفس آلية الحقول الأخرى: تبقى قابلة للتعديل اليدوي، ولمسها من المستخدم
// يوقف الحساب التلقائي عنها.
// ------------------------------------------------------------------
var LIS_DIFF_PAIRS = [
  ["Ly", "LY#"],
  ["MO", "MO#"],
  ["NE", "NE#"],
  ["EO", "EO#"],
  ["BA", "BA#"],
];

function lisRoundAbs(n) {
  return n >= 1 ? Math.round(n * 100) / 100 : Math.round(n * 1000) / 1000;
}

window.lisComputeAbsoluteDiff = function (pctValue, wbcValue) {
  var pct = parseFloat(pctValue);
  var wbc = parseFloat(wbcValue);
  if (isNaN(pct) || isNaN(wbc) || wbc <= 0) return null;
  return lisRoundAbs((pct / 100) * wbc);
};

function lisRecalcAllDiffAbsolutes(table) {
  var wbcInput = table.querySelector('[data-param-name="WBCs"]');
  if (!wbcInput) return;
  LIS_DIFF_PAIRS.forEach(function (pair) {
    var pctInput = table.querySelector('[data-param-name="' + pair[0] + '"]');
    var absInput = table.querySelector('[data-param-name="' + pair[1] + '"]');
    if (!pctInput || !absInput) return;
    if (absInput.dataset.autoFilled === "0") return; // المستخدم عدّلها يدويًا — ما نكتب فوقها
    var val = window.lisComputeAbsoluteDiff(pctInput.value, wbcInput.value);
    if (val !== null) {
      absInput.value = val;
      absInput.dataset.autoFilled = "1";
    }
  });
}

function lisRecalcAllDiffAbsolutesInitial(table) {
  var wbcInput = table.querySelector('[data-param-name="WBCs"]');
  if (!wbcInput || !wbcInput.value) return;
  LIS_DIFF_PAIRS.forEach(function (pair) {
    var pctInput = table.querySelector('[data-param-name="' + pair[0] + '"]');
    var absInput = table.querySelector('[data-param-name="' + pair[1] + '"]');
    if (!pctInput || !absInput || absInput.value || !pctInput.value) return;
    var val = window.lisComputeAbsoluteDiff(pctInput.value, wbcInput.value);
    if (val !== null) absInput.value = val;
  });
}

// ------------------------------------------------------------------
// حساب HCT تقديريًا تلقائيًا من RBC × MCV (المعادلة الطبية القياسية):
//   HCT % = (RBC بوحدة X10^12/uL) × (MCV بوحدة fL) ÷ 10
// نفس آلية الحقول الأخرى: يبقى الحقل قابلاً للتعديل اليدوي، ولمسه من
// المستخدم يوقف الحساب التلقائي عنه.
// ------------------------------------------------------------------
window.lisComputeHct = function (rbcValue, mcvValue) {
  var rbc = parseFloat(rbcValue);
  var mcv = parseFloat(mcvValue);
  if (isNaN(rbc) || isNaN(mcv) || rbc <= 0 || mcv <= 0) return null;
  return Math.round((rbc * mcv / 10) * 10) / 10; // خانة عشرية واحدة
};

function lisRecalcHct(table) {
  var rbcInput = table.querySelector('[data-param-name="RBC"]');
  var mcvInput = table.querySelector('[data-param-name="MCV"]');
  var hctInput = table.querySelector('[data-param-name="HCT"]');
  if (!rbcInput || !mcvInput || !hctInput) return;
  if (hctInput.dataset.autoFilled === "0") return; // المستخدم عدّلها يدويًا — ما نكتب فوقها
  var val = window.lisComputeHct(rbcInput.value, mcvInput.value);
  if (val !== null) {
    hctInput.value = val;
    hctInput.dataset.autoFilled = "1";
  }
}

function lisRecalcHctInitial(table) {
  var rbcInput = table.querySelector('[data-param-name="RBC"]');
  var mcvInput = table.querySelector('[data-param-name="MCV"]');
  var hctInput = table.querySelector('[data-param-name="HCT"]');
  if (!rbcInput || !mcvInput || !hctInput) return;
  if (hctInput.value || !rbcInput.value || !mcvInput.value) return;
  var val = window.lisComputeHct(rbcInput.value, mcvInput.value);
  if (val !== null) hctInput.value = val;
}

// ------------------------------------------------------------------
// حساب VLDL تلقائيًا من Triglycerides (تقرير Lipid Profile):
//   VLDL (mg/dL) = Triglycerides ÷ 5
// نفس آلية الحقول الأخرى: يبقى الحقل قابلاً للتعديل اليدوي، ولمسه من
// المستخدم يوقف الحساب التلقائي عنه.
// ------------------------------------------------------------------
window.lisComputeVldl = function (tgValue) {
  var tg = parseFloat(tgValue);
  if (isNaN(tg) || tg < 0) return null;
  return Math.round(tg / 5);
};

function lisRecalcVldl(table) {
  var tgInput = table.querySelector('[data-param-name="Triglycerides"]');
  var vldlInput = table.querySelector('[data-param-name="VLDL"]');
  if (!tgInput || !vldlInput) return;
  if (vldlInput.dataset.autoFilled === "0") return; // المستخدم عدّلها يدويًا — ما نكتب فوقها
  var val = window.lisComputeVldl(tgInput.value);
  if (val !== null) {
    vldlInput.value = val;
    vldlInput.dataset.autoFilled = "1";
  }
}

function lisRecalcVldlInitial(table) {
  var tgInput = table.querySelector('[data-param-name="Triglycerides"]');
  var vldlInput = table.querySelector('[data-param-name="VLDL"]');
  if (!tgInput || !vldlInput) return;
  if (vldlInput.value || !tgInput.value) return;
  var val = window.lisComputeVldl(tgInput.value);
  if (val !== null) vldlInput.value = val;
}

document.addEventListener("input", function (e) {
  var el = e.target;
  if (!el || !el.matches) return;
  if (el.classList.contains("lis-autoresize")) window.lisAutoResize(el);

  // Corrected Retic count
  if (el.matches('[data-param-name="Reticulocyte count"]')) {
    var table = el.closest("table");
    var correctedInput = table && table.querySelector('[data-param-name="Corrected Retic count"]');
    if (correctedInput && correctedInput.dataset.autoFilled !== "0") {
      var val = window.lisComputeCorrectedRetic(el.value, window.LIS_PATIENT_HCT, window.LIS_PATIENT_GENDER);
      correctedInput.value = val === null ? "" : val;
      correctedInput.dataset.autoFilled = "1";
    }
  }
  if (el.matches('[data-param-name="Corrected Retic count"]')) {
    el.dataset.autoFilled = "0"; // المستخدم لمسها يدويًا — نتوقف عن الكتابة فوقها
  }

  // القيم المطلقة لأنواع الكريات البيضاء (من النسبة% + WBCs)
  if (el.matches('[data-param-name="Ly"], [data-param-name="MO"], [data-param-name="NE"], '
                + '[data-param-name="EO"], [data-param-name="BA"], [data-param-name="WBCs"]')) {
    var diffTable = el.closest("table");
    if (diffTable) lisRecalcAllDiffAbsolutes(diffTable);
  }
  if (el.matches('[data-param-name="LY#"], [data-param-name="MO#"], [data-param-name="NE#"], '
                + '[data-param-name="EO#"], [data-param-name="BA#"]')) {
    el.dataset.autoFilled = "0"; // المستخدم لمسها يدويًا
  }

  // HCT من RBC × MCV
  if (el.matches('[data-param-name="RBC"], [data-param-name="MCV"]')) {
    var hctTable = el.closest("table");
    if (hctTable) lisRecalcHct(hctTable);
  }
  if (el.matches('[data-param-name="HCT"]')) {
    el.dataset.autoFilled = "0"; // المستخدم لمسها يدويًا
  }

  // VLDL من Triglycerides
  if (el.matches('[data-param-name="Triglycerides"]')) {
    var vldlTable = el.closest("table");
    if (vldlTable) lisRecalcVldl(vldlTable);
  }
  if (el.matches('[data-param-name="VLDL"]')) {
    el.dataset.autoFilled = "0"; // المستخدم لمسها يدويًا
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

  // أول تحميل: تعبئة القيم المطلقة الفاضية من النسب المئوية المحفوظة + WBCs
  document.querySelectorAll(".rb-box table").forEach(function (table) {
    lisRecalcAllDiffAbsolutesInitial(table);
    lisRecalcHctInitial(table);
    lisRecalcVldlInitial(table);
  });
});

// تحفظ تعديلات النموذج الحالي (لو أي تغيير غير محفوظ — كحذف نجمة/سهم من
// حقل Conclusion) قبل ما تفتح صفحة الطباعة، حتى ما يطلع بالتقرير محتوى
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
// دالة مساعدة مشتركة لحساب Corrected Retic Count من Retic + HCT +
// جنس المريض: Corrected Retic % = Retic % × (HCT المريض ÷ HCT الطبيعي)
// (النتيجة تُقرَّب لخانتين عشريتين). ترجع null إذا أي قيمة مدخلة
// (رتك/HCT) ناقصة أو غير رقمية، أو إذا التصحيح غير ذي دلالة سريرية
// (HCT المريض قريب من الطبيعي، فالفرق بين الرتك العادي والمصحح ضئيل
// جداً ولا داعي لعرضه أصلاً).
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
  // فرق ضئيل جداً بين الرتك العادي والمصحح (أقل من 0.05) — لا قيمة
  // سريرية إضافية، فنخفي الحقل بدل عرض رقم شبه مطابق للرتك العادي.
  if (Math.abs(retic - corrected) < 0.05) return null;
  return corrected;
};

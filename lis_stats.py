# -*- coding: utf-8 -*-
"""
lis_stats.py (v94) - شاشة «الإحصائيات» داخل الـLIS، نفس تبويبات وتصميم شاشة برنامج سجل المرضى:
  ملخص عام | التقرير النهائي | حساب مختبر | عدد تحليل معيّن | إجمالي التحاليل

القاعدة المطلوبة: أي مختبر أو طبيب ما أرسل ولا تحليل خلال الفترة المختارة ما يظهر اسمه
(لا بجدول «حسب الطبيب المرسل» ولا بجدول «المختبرات المُرسِلة» ولا بقائمة «حساب مختبر»).

الملف إضافة فقط: يُسجَّل من app.py بسطرين (راجع v94-README.md). لا يغيّر أي جدول.
"""
import json
from datetime import datetime, timedelta

from flask import jsonify, request, Response

_AGE_SKIP = ("Cancelled", "Canceled")


def _day_ok(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except Exception:
        return False


def collect_rows(db, d_from, d_to):
    """كل الزيارات غير الملغاة بالفترة، بنفس معنى صفوف السجل السحابي (ledger_sync.collect_day) لكن باستعلامين فقط."""
    vs = db.execute(
        "SELECT v.id, substr(v.created_at,1,10) AS day, v.expenses, "
        "p.full_name, "
        "(SELECT name FROM referral_centers rc WHERE rc.id=v.referral_center_id) AS center, "
        "(SELECT full_name FROM doctors d WHERE d.id=v.doctor_id) AS doctor, "
        "(SELECT COALESCE(SUM(i.paid_amount),0) FROM invoices i WHERE i.visit_id=v.id) AS paid, "
        "(SELECT COALESCE(SUM(i.total_amount-COALESCE(i.discount_amount,0)),0) FROM invoices i WHERE i.visit_id=v.id) AS net "
        "FROM visits v JOIN patients p ON p.id=v.patient_id "
        "WHERE substr(v.created_at,1,10)>=? AND substr(v.created_at,1,10)<=? "
        "AND COALESCE(v.status,'') NOT IN ('Cancelled','Canceled') ORDER BY v.id", (d_from, d_to)).fetchall()
    tests = {}
    try:
        for r in db.execute(
                "SELECT o.visit_id AS vid, td.name AS name FROM orders o "
                "JOIN order_tests ot ON ot.order_id=o.id JOIN test_definitions td ON td.id=ot.test_definition_id "
                "JOIN visits v ON v.id=o.visit_id "
                "WHERE substr(v.created_at,1,10)>=? AND substr(v.created_at,1,10)<=? "
                "AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') "
                "AND COALESCE(ot.hidden_from_log,0)=0 ORDER BY ot.id", (d_from, d_to)).fetchall():
            if r["name"]:
                tests.setdefault(r["vid"], []).append(r["name"])
    except Exception:
        # قاعدة قديمة بدون hidden_from_log
        for r in db.execute(
                "SELECT o.visit_id AS vid, td.name AS name FROM orders o "
                "JOIN order_tests ot ON ot.order_id=o.id JOIN test_definitions td ON td.id=ot.test_definition_id "
                "JOIN visits v ON v.id=o.visit_id "
                "WHERE substr(v.created_at,1,10)>=? AND substr(v.created_at,1,10)<=? "
                "AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') ORDER BY ot.id",
                (d_from, d_to)).fetchall():
            if r["name"]:
                tests.setdefault(r["vid"], []).append(r["name"])
    rows = []
    for v in vs:
        center = (v["center"] or "").strip()
        is_lab = bool(center) and center.lower() not in ("walk-in", "walkin")
        ref = center if is_lab else (v["doctor"] or "").strip()
        amt = float((v["net"] if is_lab else v["paid"]) or 0)         # مختبر محيل: صافي الفاتورة (آجل)، غيره: المدفوع فعلاً
        try:
            exp = float(str(v["expenses"] or 0).replace(",", "") or 0)
        except ValueError:
            exp = 0.0
        rows.append({"id": v["id"], "date": v["day"], "name": (v["full_name"] or "").strip(), "ref": ref,
                     "isLab": is_lab, "amt": amt, "exp": exp, "tests": tests.get(v["id"], [])})
    return rows


_PAGE = r'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>الإحصائيات</title>
<style>
:root{--bg:#F1F5F9;--ink:#0F172A;--mut:#64748B;--brand:#0F4C5C;--line:#E2E8F0;--hero:#BAE6FD}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Tahoma,Arial,sans-serif}
.top{display:flex;gap:8px;align-items:center;padding:10px 16px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.top h1{margin:0 8px 0 auto;font-size:18px}
.btn{cursor:pointer;border:1px solid var(--brand);background:#fff;color:var(--brand);border-radius:9px;padding:7px 14px;font:600 13px Tahoma}
.btn.p{background:var(--brand);color:#fff}
.wrap{max-width:1180px;margin:14px auto;padding:0 12px}
.card{background:#fff;border-radius:14px;box-shadow:0 2px 14px rgba(0,0,0,.07);padding:16px}
.tabs{display:flex;gap:4px;flex-wrap:wrap;border-bottom:1px solid var(--line);margin-bottom:14px}
.tab{cursor:pointer;padding:10px 16px;border:0;background:none;font:600 14px Tahoma;color:var(--mut);border-bottom:3px solid transparent}
.tab.on{color:#B91C1C;border-bottom-color:#B91C1C}
.ctl{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px}
.ctl label{display:block;font-size:12px;color:var(--mut);margin-bottom:3px}
.ctl select,.ctl input{padding:8px 10px;border:1px solid #CBD5E1;border-radius:9px;font:14px Tahoma;min-width:150px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0}
.box{background:#EEF2F6;border-radius:12px;padding:12px 14px}.box .l{font-size:12px;color:var(--mut)}.box .v{font-size:22px;font-weight:700}
.hero{background:var(--hero);border-radius:14px;padding:16px 20px;display:flex;justify-content:space-between;align-items:center;margin:8px 0}
.hero .n{font-size:38px;font-weight:800}.hero .t{font-size:17px;font-weight:700}.hero .s{font-size:13px;color:#334155}
table{width:100%;border-collapse:collapse;margin:8px 0 18px}th,td{border:1px solid var(--line);padding:8px 10px;text-align:center}
th{background:#BAE6FD}tbody tr:nth-child(even){background:#F8FAFC}tfoot td{background:#BAE6FD;font-weight:700}
tr.z td{color:#94A3B8}.sub{font-weight:700;font-size:16px;margin:16px 0 4px}.empty{padding:14px;color:var(--mut)}
.bar{display:inline-block;width:120px;height:8px;background:#E2E8F0;border-radius:6px;vertical-align:middle;margin-inline-start:8px;overflow:hidden}
.bar i{display:block;height:100%;background:#0F4C5C}.hid{display:none}
@media print{.top,.tabs,.ctl,.noprint{display:none!important}body{background:#fff}.card{box-shadow:none}}
</style></head><body>
<div class="top"><button class="btn" onclick="goBack()">↩ رجوع</button><button class="btn" onclick="location.href='/'">🏠 الشاشة الرئيسية</button><h1>📊 الإحصائيات</h1></div>
<div class="wrap"><div class="card">
<div class="tabs" id="tabs">
<button class="tab on" data-p="summary">ملخص عام</button><button class="tab" data-p="final">التقرير النهائي</button>
<button class="tab" data-p="lab">حساب مختبر</button><button class="tab" data-p="tc">عدد تحليل معيّن</button><button class="tab" data-p="all">إجمالي التحاليل</button></div>

<div id="p_summary"><div class="ctl"><div><label>من</label><input type="date" id="sFrom"></div><div><label>إلى</label><input type="date" id="sTo"></div><button class="btn p" onclick="runSummary()">عرض</button></div><div id="sRes"></div></div>

<div id="p_final" class="hid"><div class="ctl"><div><label>طريقة العرض</label><select id="fMode"><option value="day">يومي — أيام الشهر</option><option value="month">شهري — أشهر السنة</option></select></div>
<div><label>الشهر / السنة</label><input type="month" id="fMonth"></div><button class="btn" onclick="shift(-1)">› السابق</button><button class="btn" onclick="shift(1)">التالي ‹</button><button class="btn p" onclick="window.print()">طباعة</button></div>
<div class="ctl"><div style="flex:1"><label>مختبرات تُحاسَب بالآجل (عمود مستقل) — افصل بينها بفاصلة</label><input type="text" id="fCredit" style="width:100%" placeholder="القمة"></div></div><div id="fRes"></div></div>

<div id="p_lab" class="hid"><div class="ctl"><div><label>المختبر (تظهر فقط المختبرات التي أرسلت بالشهر)</label><select id="lLab"></select></div><div><label>الشهر</label><input type="month" id="lMonth"></div>
<button class="btn" onclick="shiftL(-1)">› السابق</button><button class="btn" onclick="shiftL(1)">التالي ‹</button><button class="btn p" onclick="window.print()">طباعة</button></div><div id="lRes"></div></div>

<div id="p_tc" class="hid"><div class="ctl"><div><label>التحليل</label><select id="tSel"></select></div><div><label>من</label><input type="date" id="tFrom"></div><div><label>إلى</label><input type="date" id="tTo"></div><button class="btn p" onclick="runTC()">عرض الإحصائية</button></div>
<div class="ctl noprint"><button class="btn" onclick="preset('t','today')">اليوم</button><button class="btn" onclick="preset('t','week')">هذا الأسبوع</button><button class="btn" onclick="preset('t','month')">هذا الشهر</button><button class="btn" onclick="preset('t','year')">هذه السنة</button></div><div id="tRes"></div></div>

<div id="p_all" class="hid"><div class="ctl"><div><label>من</label><input type="date" id="aFrom"></div><div><label>إلى</label><input type="date" id="aTo"></div>
<div><label>التجميع حسب</label><select id="aGrp"><option value="day">اليوم</option><option value="week">الأسبوع (يبدأ السبت)</option><option value="month">الشهر</option><option value="year">السنة</option></select></div><button class="btn p" onclick="runAll()">عرض الإحصائية</button></div>
<div class="ctl noprint"><button class="btn" onclick="preset('a','today')">اليوم</button><button class="btn" onclick="preset('a','week')">هذا الأسبوع</button><button class="btn" onclick="preset('a','month')">هذا الشهر</button><button class="btn" onclick="preset('a','year')">هذه السنة</button></div><div id="aRes"></div></div>
</div></div>
<script>
var CREDIT=__CREDIT__, MN=['كانون الثاني','شباط','آذار','نيسان','أيار','حزيران','تموز','آب','أيلول','تشرين الأول','تشرين الثاني','كانون الأول'];
var DN=['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'];
function $(i){return document.getElementById(i)}function pad(n){return (n<10?'0':'')+n}
function ymd(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())}
function fmt(n){return Math.round(Number(n)||0).toLocaleString('en-US')}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function norm(s){return String(s||'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/ة/g,'ه').replace(/\s+/g,' ').trim().toLowerCase()}
function goBack(){ if(history.length>1) history.back(); else location.href='/'; }
function isCredit(n){var x=norm(n);return !!x&&CREDIT.some(function(c){c=norm(c);return c&&x.indexOf(c)>=0})}
function dayName(k){var p=k.split('-');return DN[new Date(+p[0],+p[1]-1,+p[2]).getDay()]}
function load(a,b){return fetch('/api/stats/rows?from='+a+'&to='+b,{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(j){return j.rows||[]})}
function empty(t){return '<div class="empty">'+t+'</div>'}
var tabs=document.querySelectorAll('.tab');
tabs.forEach(function(t){t.onclick=function(){tabs.forEach(function(x){x.classList.toggle('on',x===t)});['summary','final','lab','tc','all'].forEach(function(p){$('p_'+p).classList.toggle('hid',p!==t.dataset.p)});({summary:runSummary,final:runFinal,lab:runLab,tc:initTC,all:runAll})[t.dataset.p]()}});
function range(k){var n=new Date(),a=new Date(n),b=new Date(n);
 if(k==='week'){a.setDate(n.getDate()-((n.getDay()+1)%7))} else if(k==='month'){a=new Date(n.getFullYear(),n.getMonth(),1);b=new Date(n.getFullYear(),n.getMonth()+1,0)} else if(k==='year'){a=new Date(n.getFullYear(),0,1);b=new Date(n.getFullYear(),11,31)}
 return {from:ymd(a),to:ymd(b)}}
function preset(w,k){var r=range(k);$(w+'From').value=r.from;$(w+'To').value=r.to;w==='t'?runTC():runAll()}
// ---- summary
function runSummary(){var f=$('sFrom').value,t=$('sTo').value;load(f,t).then(function(rows){
 var by={},tp=0,tn=0;rows.forEach(function(r){var b=by[r.date]=by[r.date]||{p:0,paid:0,net:0};b.p++;var c=isCredit(r.ref);var paid=c?0:r.amt;b.paid+=paid;b.net+=paid-r.exp;tp++;});
 var ks=Object.keys(by).sort(),paid=0,net=0,h='';ks.forEach(function(k){paid+=by[k].paid;net+=by[k].net;h+='<tr><td>'+k+'</td><td>'+by[k].p+'</td><td>'+fmt(by[k].paid)+'</td><td>'+fmt(by[k].net)+'</td></tr>'});
 $('sRes').innerHTML='<div class="grid"><div class="box"><div class="l">عدد الأيام</div><div class="v">'+ks.length+'</div></div><div class="box"><div class="l">عدد المرضى</div><div class="v">'+tp+'</div></div><div class="box"><div class="l">إجمالي المدفوع</div><div class="v">'+fmt(paid)+'</div></div><div class="box"><div class="l">إجمالي الصافي</div><div class="v">'+fmt(net)+'</div></div></div>'+
 '<table><thead><tr><th>التاريخ</th><th>المرضى</th><th>المدفوع</th><th>الصافي</th></tr></thead><tbody>'+(h||'<tr><td colspan="4">لا توجد سجلات</td></tr>')+'</tbody></table>'})}
// ---- final report
function zero(){return {p:0,paid:0,exp:0,sent:0}}
function runFinal(){var ym=$('fMonth').value,mode=$('fMode').value;if(!/^\d{4}-\d{2}$/.test(ym)){$('fRes').innerHTML=empty('اختر الشهر');return}
 CREDIT=$('fCredit').value.split(/[,،]/).map(function(x){return x.trim()}).filter(Boolean);
 fetch('/api/stats/credit',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({labs:CREDIT.join('، ')})});
 var y=+ym.slice(0,4),m=+ym.slice(5,7),from=mode==='month'?y+'-01-01':ym+'-01',to=mode==='month'?y+'-12-31':ymd(new Date(y,m,0));
 load(from,to).then(function(rows){var bk={},docs={},labs={},tot=zero();
  rows.forEach(function(r){var k=mode==='month'?r.date.slice(0,7):r.date,b=bk[k]=bk[k]||zero(),c=isCredit(r.ref),paid=c?0:r.amt,sent=c?r.amt:0;
   [b,tot].forEach(function(x){x.p++;x.paid+=paid;x.exp+=r.exp;x.sent+=sent});
   var key=norm(r.ref||'بدون طبيب مرسل');
   if(r.isLab){var l=labs[key]=labs[key]||{name:r.ref,p:0,amt:0};l.p++;l.amt+=r.amt}
   else{var d=docs[key]=docs[key]||{name:r.ref||'بدون طبيب مرسل',p:0,paid:0,tests:0};d.p++;d.paid+=r.amt;d.tests+=r.tests.length}});
  var net=tot.paid-tot.exp,title=mode==='month'?'سنة '+y:MN[m-1]+' '+y,lt=CREDIT[0]||'الآجل';
  var h='<div class="hero"><div><div class="t">الصافي زائد '+esc(lt)+' — '+esc(title)+'</div><div class="s">'+tot.p+' مريض في الفترة من '+from+' إلى '+to+'</div></div><div class="n">'+fmt(net+tot.sent)+'</div></div>'+
  '<div class="grid"><div class="box"><div class="l">عدد المرضى</div><div class="v">'+tot.p+'</div></div><div class="box"><div class="l">الكلي (المدفوع)</div><div class="v">'+fmt(tot.paid)+'</div></div><div class="box"><div class="l">المصروفات</div><div class="v">'+fmt(tot.exp)+'</div></div><div class="box"><div class="l">الصافي</div><div class="v">'+fmt(net)+'</div></div><div class="box"><div class="l">'+esc(lt)+'</div><div class="v">'+fmt(tot.sent)+'</div></div></div>';
  h+='<div class="sub">'+(mode==='month'?'الحساب الشهري':'الحساب اليومي')+'</div><table><thead><tr><th>'+(mode==='month'?'الشهر':'اليوم')+'</th><th>'+(mode==='month'?'الفترة':'التاريخ')+'</th><th>المرضى</th><th>الكلي</th><th>المصروفات</th><th>الصافي</th><th>'+esc(lt)+'</th><th>الصافي زائد '+esc(lt)+'</th></tr></thead><tbody>';
  var keys=[];if(mode==='month'){for(var i=1;i<=12;i++)keys.push(y+'-'+pad(i))}else{for(var d=1;d<=new Date(y,m,0).getDate();d++)keys.push(ym+'-'+pad(d))}
  keys.forEach(function(k){var b=bk[k]||zero(),n=b.paid-b.exp;h+='<tr class="'+(b.p?'':'z')+'"><td>'+(mode==='month'?MN[+k.slice(5,7)-1]:dayName(k))+'</td><td>'+k+'</td><td>'+b.p+'</td><td>'+fmt(b.paid)+'</td><td>'+fmt(b.exp)+'</td><td>'+fmt(n)+'</td><td>'+fmt(b.sent)+'</td><td><b>'+fmt(n+b.sent)+'</b></td></tr>'});
  h+='</tbody><tfoot><tr><td colspan="2">المجموع</td><td>'+tot.p+'</td><td>'+fmt(tot.paid)+'</td><td>'+fmt(tot.exp)+'</td><td>'+fmt(net)+'</td><td>'+fmt(tot.sent)+'</td><td>'+fmt(net+tot.sent)+'</td></tr></tfoot></table>';
  var dk=Object.keys(docs).sort(function(a,b){return docs[b].p-docs[a].p});h+='<div class="sub">حسب الطبيب المرسل</div>';
  if(!dk.length)h+=empty('لا توجد بيانات في هذه الفترة');else{h+='<table><thead><tr><th>الطبيب المرسل</th><th>عدد المرضى</th><th>النسبة</th><th>المبلغ المدفوع</th><th>عدد التحاليل</th></tr></thead><tbody>';
   dk.forEach(function(k){var d=docs[k],pc=tot.p?Math.round(d.p*1000/tot.p)/10:0;h+='<tr><td>'+esc(d.name)+'</td><td>'+d.p+'</td><td>'+pc+'%<span class="bar"><i style="width:'+pc+'%"></i></span></td><td>'+fmt(d.paid)+'</td><td>'+d.tests+'</td></tr>'});h+='</tbody></table>'}
  var lk=Object.keys(labs).sort(function(a,b){return labs[b].amt-labs[a].amt});h+='<div class="sub">المختبرات التي أرسلت عينات</div>';
  if(!lk.length)h+=empty('لا توجد عينات من مختبرات أخرى في هذه الفترة');else{h+='<table><thead><tr><th>المختبر المُرسِل</th><th>عدد العينات</th><th>المبلغ</th></tr></thead><tbody>';lk.forEach(function(k){h+='<tr><td>'+esc(labs[k].name)+'</td><td>'+labs[k].p+'</td><td>'+fmt(labs[k].amt)+'</td></tr>'});h+='</tbody></table>'}
  $('fRes').innerHTML=h})}
function shift(d){var v=$('fMonth').value||range('month').from.slice(0,7),y=+v.slice(0,4),m=+v.slice(5,7);if($('fMode').value==='month')y+=d;else{m+=d;if(m<1){m=12;y--}if(m>12){m=1;y++}}$('fMonth').value=y+'-'+pad(m);runFinal()}
// ---- lab account: only labs that sent at least one sample in the month
function runLab(){var ym=$('lMonth').value;if(!/^\d{4}-\d{2}$/.test(ym))return;var y=+ym.slice(0,4),m=+ym.slice(5,7);
 load(ym+'-01',ymd(new Date(y,m,0))).then(function(rows){var labs={};rows.forEach(function(r){if(r.isLab){(labs[norm(r.ref)]=labs[norm(r.ref)]||{name:r.ref,rows:[]}).rows.push(r)}});
  var ks=Object.keys(labs).sort(function(a,b){return labs[b].rows.length-labs[a].rows.length}),sel=$('lLab'),prev=sel.value;
  sel.innerHTML=ks.map(function(k){return '<option value="'+esc(k)+'">'+esc(labs[k].name)+' ('+labs[k].rows.length+')</option>'}).join('');if(!ks.length){$('lRes').innerHTML=empty('لا توجد عينات من مختبرات أخرى بهذا الشهر');return}
  if(ks.indexOf(prev)>=0)sel.value=prev;sel.onchange=function(){draw()};
  function draw(){var L=labs[sel.value];if(!L)return;var tot=0,t=0,h='<div class="sub">'+esc(L.name)+' — '+MN[m-1]+' '+y+'</div><table><thead><tr><th>التاريخ</th><th>المريض</th><th>التحاليل</th><th>المبلغ</th></tr></thead><tbody>';
   L.rows.sort(function(a,b){return a.date<b.date?-1:1}).forEach(function(r){tot+=r.amt;t+=r.tests.length;h+='<tr><td>'+r.date+'</td><td>'+esc(r.name)+'</td><td>'+esc(r.tests.join('، '))+'</td><td>'+fmt(r.amt)+'</td></tr>'});
   h+='</tbody><tfoot><tr><td colspan="2">المجموع ('+L.rows.length+' عينة)</td><td>'+t+' تحليل</td><td>'+fmt(tot)+'</td></tr></tfoot></table>';$('lRes').innerHTML=h}draw()})}
function shiftL(d){var v=$('lMonth').value||range('month').from.slice(0,7),y=+v.slice(0,4),m=+v.slice(5,7)+d;if(m<1){m=12;y--}if(m>12){m=1;y++}$('lMonth').value=y+'-'+pad(m);runLab()}
// ---- test count
function initTC(){var r=range('year');if(!$('tFrom').value){$('tFrom').value=r.from;$('tTo').value=r.to}
 load($('tFrom').value,$('tTo').value).then(function(rows){var s={};rows.forEach(function(x){x.tests.forEach(function(n){s[n]=(s[n]||0)+1})});var prev=$('tSel').value;
  $('tSel').innerHTML=Object.keys(s).sort().map(function(n){return '<option>'+esc(n)+'</option>'}).join('');if(prev)$('tSel').value=prev;runTC()})}
function runTC(){var name=$('tSel').value;if(!name){$('tRes').innerHTML=empty('لا توجد تحاليل بهذه الفترة');return}
 load($('tFrom').value,$('tTo').value).then(function(rows){var by={},tot=0;rows.forEach(function(r){var c=r.tests.filter(function(n){return n===name}).length;if(c){by[r.date]=(by[r.date]||0)+c;tot+=c}});
  var ks=Object.keys(by).sort();$('tRes').innerHTML='<div class="grid"><div class="box"><div class="l">'+esc(name)+'</div><div class="v">'+tot+'</div></div><div class="box"><div class="l">عدد الأيام</div><div class="v">'+ks.length+'</div></div></div>'+
  (ks.length?'<table><thead><tr><th>التاريخ</th><th>العدد</th></tr></thead><tbody>'+ks.map(function(k){return '<tr><td>'+k+'</td><td>'+by[k]+'</td></tr>'}).join('')+'</tbody></table>':empty('لا توجد نتائج'))})}
// ---- all tests
function gkey(d,g){var p=d.split('-'),x=new Date(+p[0],+p[1]-1,+p[2]);if(g==='day')return d;if(g==='month')return d.slice(0,7);if(g==='year')return d.slice(0,4);x.setDate(x.getDate()-((x.getDay()+1)%7));return ymd(x)}
function runAll(){var g=$('aGrp').value;load($('aFrom').value,$('aTo').value).then(function(rows){var by={},per={},tot=0;rows.forEach(function(r){var k=gkey(r.date,g);by[k]=by[k]||{v:0,t:0};by[k].v++;by[k].t+=r.tests.length;tot+=r.tests.length;r.tests.forEach(function(n){per[n]=(per[n]||0)+1})});
 var ks=Object.keys(by).sort(),pk=Object.keys(per).sort(function(a,b){return per[b]-per[a]});
 $('aRes').innerHTML='<div class="grid"><div class="box"><div class="l">إجمالي التحاليل</div><div class="v">'+tot+'</div></div><div class="box"><div class="l">عدد الزيارات</div><div class="v">'+rows.length+'</div></div></div>'+
 '<table><thead><tr><th>'+({day:'اليوم',week:'بداية الأسبوع',month:'الشهر',year:'السنة'})[g]+'</th><th>الزيارات</th><th>التحاليل</th></tr></thead><tbody>'+(ks.map(function(k){return '<tr><td>'+k+'</td><td>'+by[k].v+'</td><td>'+by[k].t+'</td></tr>'}).join('')||'<tr><td colspan="3">لا توجد بيانات</td></tr>')+'</tbody></table>'+
 '<div class="sub">حسب التحليل</div><table><thead><tr><th>التحليل</th><th>العدد</th></tr></thead><tbody>'+pk.map(function(n){return '<tr><td>'+esc(n)+'</td><td>'+per[n]+'</td></tr>'}).join('')+'</tbody></table>'})}
(function init(){var r=range('month');$('sFrom').value=r.from;$('sTo').value=r.to;$('fMonth').value=r.from.slice(0,7);$('lMonth').value=r.from.slice(0,7);$('aFrom').value=r.from;$('aTo').value=r.to;$('fCredit').value=CREDIT.join('، ');runSummary()})();
</script></body></html>'''


# أيقونة الإحصائيات تُضاف للقائمة الجانبية بدون لمس base.html
_NAV_JS = ("<script id='lis-stats-nav'>(function(){try{if(window.top!==window.self)return;var nav=document.querySelector('aside nav');"
           "if(!nav||document.getElementById('lisStatsLink'))return;var a=document.createElement('a');a.id='lisStatsLink';a.className='nav-link';"
           "a.href='/stats';a.innerHTML='<span style=\"display:inline-block;width:18px;vertical-align:middle;margin-inline-end:6px\">"
           "<svg viewBox=\"0 0 24 24\" width=\"18\" height=\"18\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.9\" stroke-linecap=\"round\">"
           "<path d=\"M4 20V10M10 20V4M16 20v-7M22 20H2\"/></svg></span>إحصائية';nav.insertBefore(a,nav.firstChild);}catch(e){}})();</script>")


def install(app, get_db, get_setting, set_setting, login_required):
    @app.route("/stats")
    @login_required
    def lis_stats_page():
        db = get_db()
        try:
            raw = get_setting(db, "stats_credit_labs", "القمة") or ""
        finally:
            try:
                db.close()
            except Exception:
                pass
        labs = [x.strip() for x in raw.replace("،", ",").split(",") if x.strip()]
        return Response(_PAGE.replace("__CREDIT__", json.dumps(labs, ensure_ascii=False)), mimetype="text/html")

    @app.route("/api/stats/rows")
    @login_required
    def lis_stats_rows():
        a, b = request.args.get("from", ""), request.args.get("to", "")
        if not (_day_ok(a) and _day_ok(b)):
            return jsonify(rows=[], error="تاريخ غير صالح"), 400
        if (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days > 800:
            return jsonify(rows=[], error="الفترة طويلة جداً"), 400
        db = get_db()
        try:
            return jsonify(rows=collect_rows(db, a, b))
        finally:
            try:
                db.close()
            except Exception:
                pass

    @app.route("/api/stats/credit", methods=["POST"])
    @login_required
    def lis_stats_credit():
        d = request.get_json(silent=True) or {}
        db = get_db()
        try:
            set_setting(db, "stats_credit_labs", str(d.get("labs") or "")[:300])
            db.commit()
            return jsonify(ok=True)
        finally:
            try:
                db.close()
            except Exception:
                pass

    @app.after_request
    def _stats_nav(resp):
        try:
            if resp.status_code != 200 or resp.mimetype != "text/html" or resp.direct_passthrough:
                return resp
            data = resp.get_data()
            if b"<aside" in data and b"lis-stats-nav" not in data and b"</body>" in data and request.path != "/stats":
                resp.set_data(data.replace(b"</body>", _NAV_JS.encode("utf-8") + b"</body>", 1))
        except Exception:
            pass
        return resp

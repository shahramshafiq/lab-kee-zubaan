// Page words in the three languages. English is whatever is written in index.html; Urdu and Roman Urdu are listed here.
// applyUI(lang) swaps the fixed texts of the page, t(key) gives one word for the texts app.js makes later.
// If a key is missing the English text is used, so a gap can never leave the page blank.
(function () {
  const UR = {
    hero: "اپنی لیب رپورٹ سمجھیں",
    lead: "اپنی رپورٹ شامل کریں۔ آپ کو یہ آسان لفظوں میں ملے گی، اور آپ اسے سن بھی سکتے ہیں۔",
    drop1: "اپنی رپورٹ یہاں ڈالیں",
    drop2: "یا فائل چننے کے لیے کلک کریں (PDF، ورڈ، ایکسل، تصویر یا ٹیکسٹ)",
    paste: "ٹیکسٹ پیسٹ کریں", sample: "مثال آزمائیں",
    pasteLabel: "اپنی رپورٹ کا ٹیکسٹ یہاں پیسٹ کریں", pastePh: "عمر، جنس اور ٹیسٹ کے نتائج...",
    sampleLabel: "ایک مثالی رپورٹ چنیں",
    go: "میری رپورٹ سمجھائیں",
    privacy: "AI کو بھیجنے سے پہلے آپ کا نام اور ریکارڈ نمبر ہٹا دیے جاتے ہیں۔ یہ صفحہ بند کرنے کے بعد کچھ محفوظ نہیں رہتا۔",
    again: "← کوئی اور رپورٹ شامل کریں",
    short: "مختصر بات",
    needs: "مجھے تھوڑی مزید معلومات چاہیے", needsP: "نارمل رینج عمر اور جنس پر منحصر ہوتی ہے، اور میں اندازہ نہیں لگاؤں گا۔",
    age: "عمر", sex: "جنس", update: "اپ ڈیٹ",
    results: "آپ کے نتائج", questions: "ڈاکٹر سے پوچھنے کے سوالات",
    chat: "اپنی رپورٹ کے بارے میں پوچھیں", chatPh: "اپنا سوال یہاں لکھیں", send: "بھیجیں",
    micNote: "مائیکروفون دبائیں، سوال پوچھیں، دوبارہ دبائیں۔",
    share: "واٹس ایپ پر شیئر کریں", print: "پرنٹ یا محفوظ کریں",
    foot: "یہ ٹول نمبرز سمجھاتا ہے۔ یہ تشخیص نہیں کر سکتا۔ صرف لائسنس یافتہ ڈاکٹر کر سکتا ہے۔",
    urgent: "فوری: ایک یا زیادہ ویلیوز خطرناک سطح پر ہیں۔ آج ہی ڈاکٹر سے ملیں۔",
    disclaimer: "یہ وضاحت تشخیص نہیں ہے۔ بیماری کی تشخیص یا علاج کا فیصلہ صرف لائسنس یافتہ ڈاکٹر کر سکتا ہے۔ براہ کرم یہ رپورٹ اپنے ڈاکٹر کو دکھائیں۔",
    normalFor: "آپ کے لیے نارمل", typed: "آپ کی دی ہوئی رینج", how: "ہم نے کیسے فیصلہ کیا", conv: "اکائی کی تبدیلی:",
    listen: "سنیں", stop: "روکیں", preparing: "تیاری", attached: "منسلک:", choose: "منتخب کریں",
    female: "خاتون", male: "مرد",
  };
  const RU = {
    hero: "Apni lab report samjhein",
    lead: "Apni report shamil karein. Aap ko yeh aasan lafzon mein milegi, aur aap ise sun bhi sakte hain.",
    drop1: "Apni report yahan daalein",
    drop2: "ya file chunne ke liye click karein (PDF, Word, Excel, photo ya text)",
    paste: "Text paste karein", sample: "Misaal aazmayein",
    pasteLabel: "Apni report ka text yahan paste karein", pastePh: "Umar, jins aur test ke nataij...",
    sampleLabel: "Aik misali report chunein",
    go: "Meri report samjhayein",
    privacy: "AI ko bhejne se pehle aap ka naam aur record number hata diye jate hain. Yeh page band karne ke baad kuch mehfooz nahin rehta.",
    again: "← Koi aur report shamil karein",
    short: "Mukhtasar baat",
    needs: "Mujhe thodi aur maloomat chahiye", needsP: "Normal range umar aur jins par munhasir hoti hai, aur main andaza nahin lagaunga.",
    age: "Umar", sex: "Jins", update: "Update",
    results: "Aap ke nataij", questions: "Doctor se poochne ke sawal",
    chat: "Apni report ke bare mein poochein", chatPh: "Apna sawal yahan likhein", send: "Bhejein",
    micNote: "Microphone dabayein, sawal poochein, dobara dabayein.",
    share: "WhatsApp par share karein", print: "Print ya save karein",
    foot: "Yeh tool numbers samjhata hai. Yeh tashkhees nahin kar sakta. Sirf licensed doctor kar sakta hai.",
    urgent: "Fori: aik ya zyada values khatarnak satah par hain. Aaj hi doctor se milein.",
    disclaimer: "Yeh wazahat tashkhees nahin hai. Bimari ki tashkhees ya ilaj ka faisla sirf licensed doctor kar sakta hai. Meharbani karke yeh report apne doctor ko dikhayein.",
    normalFor: "Aap ke liye normal", typed: "Aap ki di hui range", how: "Hum ne kaise faisla kiya", conv: "Unit ki tabdeeli:",
    listen: "Sunein", stop: "Rokein", preparing: "Tayyari", attached: "Munsalik:", choose: "Chunein",
    female: "Khatoon", male: "Mard",
  };
  const EN = {
    urgent: "URGENT: one or more values are at a dangerous level. See a doctor today.",
    normalFor: "Normal for you", typed: "Range you typed", how: "How we decided", conv: "Unit conversion:",
    listen: "Listen", stop: "Stop", preparing: "Preparing", attached: "Attached:",
  };
  const TABLE = { ur: UR, roman_urdu: RU, en: EN };
  // [selector, index (or -1 for all), key, where: text | placeholder | label (text before an input)]
  const MAP = [
    ["#h-start", -1, "hero"], [".lead", -1, "lead"], ["#drop strong", -1, "drop1"],
    ["#drop > span:not(.drop-icon):not(.file-name)", -1, "drop2"], ["#show-paste", -1, "paste"], ["#show-sample", -1, "sample"],
    ["#paste-box label", -1, "pasteLabel"], ["#paste-text", -1, "pastePh", "placeholder"], ["#sample-box label", -1, "sampleLabel"],
    ["#go", -1, "go"], [".privacy", -1, "privacy"], ["#again", -1, "again"], ["#h-short", -1, "short"],
    ["#h-needs", -1, "needs"], ["#needs > p", -1, "needsP"], ["#need-go", -1, "update"],
    [".sec", 0, "results"], [".sec", 1, "questions"], ["#h-chat", -1, "chat"], ["#chat-input", -1, "chatPh", "placeholder"],
    ["#send", -1, "send"], ["#mic-note", -1, "micNote"], ["#share", -1, "share"], ["#print", -1, "print"], [".foot", -1, "foot"],
  ];
  // the two small labels that hold an input: only the text before the input is replaced
  const LABELS = [["#need-age", "age"], ["#need-sex", "sex"]];

  function t(key) {
    const lang = (window.lzLang && window.lzLang()) || "en";
    return ((TABLE[lang] || {})[key]) || EN[key] || key;
  }

  function applyUI(lang) {
    const words = TABLE[lang] || {};
    const rtl = lang === "ur";
    document.documentElement.setAttribute("data-ui", lang);
    for (const [selector, index, key, where] of MAP) {
      const nodes = document.querySelectorAll(selector);
      nodes.forEach((node, i) => {
        if (index >= 0 && i !== index) return;
        if (where === "placeholder") {
          if (node.dataset.en === undefined) node.dataset.en = node.getAttribute("placeholder") || "";
          node.setAttribute("placeholder", words[key] || node.dataset.en);
        } else {
          if (node.dataset.en === undefined) node.dataset.en = node.textContent;
          node.textContent = words[key] || node.dataset.en;
          node.classList.toggle("rtl", rtl && !!words[key]);
          if (rtl && words[key]) node.setAttribute("lang", "ur"); else node.removeAttribute("lang");
        }
      });
    }
    for (const [id, key] of LABELS) {
      const input = document.querySelector(id);
      const label = input && input.closest("label");
      const text = label && [...label.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim());
      if (text) {
        if (label.dataset.en === undefined) label.dataset.en = text.textContent;
        text.textContent = (words[key] ? words[key] + " " : label.dataset.en);
      }
    }
    const sex = document.getElementById("need-sex");
    if (sex) {
      const names = { "": words.choose, female: words.female, male: words.male };
      [...sex.options].forEach((o) => {
        if (o.dataset.en === undefined) o.dataset.en = o.textContent;
        o.textContent = names[o.value] || o.dataset.en;
      });
    }
  }

  window.t = t;
  window.applyUI = applyUI;
})();

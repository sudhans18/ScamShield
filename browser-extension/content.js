let debounceTimer = null;
let lastAnalyzedText = "";

function extractPageText() {
  return (document.body && document.body.innerText) ? document.body.innerText.trim() : "";
}

function analyzeText(text) {
  fetch("http://localhost:8000/api/analyze", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ text: text, source: "browser_extension" })
  })
    .then((res) => res.json())
    .then((data) => {
      showWarning(data);
    })
    .catch(() => {
      console.log("Backend not running");
    });
}

function scheduleAnalyze(text) {
  const normalized = (text || "").trim();
  if (!normalized || normalized === lastAnalyzedText) {
    return;
  }

  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    if (normalized === lastAnalyzedText) {
      return;
    }
    lastAnalyzedText = normalized;
    analyzeText(normalized);
  }, 500);
}

function showWarning(data) {
  const score = typeof data.risk_score === "number" ? data.risk_score : 0;
  const percent = score > 1 ? Math.round(score) : Math.round(score * 100);
  const level = data.risk_level || (percent > 60 ? "HIGH" : percent >= 30 ? "MEDIUM" : "LOW");
  const reasons = Array.isArray(data.reasons) && data.reasons.length ? data.reasons.join(", ") : "No major red flags";

  if (percent >= 60) {
    alert(
      "Scam Warning\n\n" +
      "Risk Score: " + percent + "%\n" +
      "Risk Level: " + level + "\n" +
      "Reason: " + reasons
    );
  }
}

setTimeout(() => {
  const text = extractPageText();
  scheduleAnalyze(text);
}, 3000);

document.getElementById("scanBtn").addEventListener("click", function () {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      function: scanPage
    });
  });
});

function scanPage() {
  const text = (document.body && document.body.innerText) ? document.body.innerText.trim() : "";
  if (!text) {
    return;
  }

  window.__scamShieldDebounceTimer = window.__scamShieldDebounceTimer || null;
  window.__scamShieldLastText = window.__scamShieldLastText || "";

  clearTimeout(window.__scamShieldDebounceTimer);
  window.__scamShieldDebounceTimer = setTimeout(() => {
    if (!text || text === window.__scamShieldLastText) {
      return;
    }
    window.__scamShieldLastText = text;

    fetch("http://localhost:8000/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ text: text, source: "browser_extension" })
    })
      .then((res) => res.json())
      .then((data) => {
        const score = typeof data.risk_score === "number" ? data.risk_score : 0;
        const percent = score > 1 ? Math.round(score) : Math.round(score * 100);
        const level = data.risk_level || (percent > 60 ? "HIGH" : percent >= 30 ? "MEDIUM" : "LOW");
        const reasons = Array.isArray(data.reasons) && data.reasons.length ? data.reasons.join(", ") : "No major red flags";

        alert(
          "Risk Score: " + percent + "%\n" +
          "Risk Level: " + level + "\n" +
          "Reason: " + reasons
        );
      });
  }, 500);
}

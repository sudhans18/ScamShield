function extractPageText() {
  return document.body.innerText;
}

setTimeout(() => {
  const text = extractPageText();
  chrome.runtime.sendMessage({ type: "ANALYZE", text: text }, (response) => {
    if (response && response.success) {
      const data = response.data;
      console.log("Backend response:", data);
      if (data.risk > 0.7) {
        alert(
          "⚠️ Potential Scam Detected!\n\n" +
          "Risk Score: " + data.risk + "\n" +
          "Reason: " + data.reason
        );
      }
    } else {
      console.log("Backend not reachable", response);
    }
  });
}, 3000);
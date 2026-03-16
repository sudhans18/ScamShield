{
  "manifest_version": 3,
  "name": "Job Scam Detector",
  "version": "1.0",
  "description": "Detects potential job scams on websites",
  "permissions": [
    "activeTab",
    "scripting"
  ],
  "host_permissions": [
    "http://localhost:8000/*"
  ],
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content.js"]
    }
  ],
  "action": {
    "default_popup": "popup.html",
    "default_title": "Job Scam Detector"
  }
}

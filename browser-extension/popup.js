const backendUrlInput = document.getElementById("backend-url");
const connectBtn = document.getElementById("connect-btn");
const statusEl = document.getElementById("status");

function setStatus(message, tone) {
  statusEl.textContent = message;
  statusEl.className = tone || "";
}

chrome.storage.local.get(["backendUrl"], (saved) => {
  if (saved.backendUrl) backendUrlInput.value = saved.backendUrl;
});

// FPL's SPA stores its OIDC token bundle in localStorage under an
// "oidc.user:..." key; the API authenticates with its access_token.
function readTokenFromPage() {
  const key = Object.keys(localStorage).find((k) => k.startsWith("oidc.user:"));
  if (!key) return null;
  try {
    return JSON.parse(localStorage.getItem(key)).access_token || null;
  } catch {
    return null;
  }
}

async function getAccessToken() {
  const tabs = await chrome.tabs.query({ url: "https://fantasy.premierleague.com/*" });
  if (!tabs.length) return { error: "no-tab" };

  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: readTokenFromPage,
  });
  return result ? { token: result } : { error: "not-signed-in" };
}

connectBtn.addEventListener("click", async () => {
  const backendUrl = backendUrlInput.value.trim().replace(/\/$/, "");
  if (!backendUrl) {
    setStatus("Enter the app URL.", "error");
    return;
  }

  chrome.storage.local.set({ backendUrl });
  connectBtn.disabled = true;
  setStatus("Reading your FPL session...", "");

  try {
    const { token, error } = await getAccessToken();

    if (error === "no-tab") {
      setStatus("Open fantasy.premierleague.com in a tab first, then try again.", "error");
      return;
    }
    if (error === "not-signed-in") {
      setStatus("You're not signed into FPL in that tab. Sign in, then try again.", "error");
      return;
    }

    setStatus("Connecting...", "");

    const resp = await fetch(`${backendUrl}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
    });

    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed: ${resp.status}`);
    }

    const data = await resp.json();
    setStatus(`Connected as team ${data.team_id}. You can close this.`, "success");
  } catch (e) {
    setStatus(e.message || "Something went wrong.", "error");
  } finally {
    connectBtn.disabled = false;
  }
});

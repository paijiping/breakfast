(() => {
  const form = document.querySelector("#login-form");
  const usernameInput = document.querySelector("#admin-username");
  const passwordInput = document.querySelector("#admin-password");
  const message = document.querySelector("#login-message");
  const submitButton = document.querySelector("#login-submit");

  function showMessage(text) {
    message.textContent = text;
    message.hidden = !text;
  }

  async function checkExistingSession() {
    try {
      const response = await fetch("/api/admin/session", { credentials: "same-origin" });
      if (response.ok) {
        window.location.replace("/admin");
        return;
      }
      if (response.status === 503) showMessage("店家管理功能尚未啟用。");
    } catch {
      showMessage("目前無法連線，請稍後重試。");
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showMessage("");
    submitButton.disabled = true;
    try {
      const response = await fetch("/api/admin/session", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ username: usernameInput.value, password: passwordInput.value })
      });
      const payload = await response.json();
      if (!response.ok) {
        showMessage(payload.detail || "登入失敗，請檢查密碼後重試。");
        return;
      }
      passwordInput.value = "";
      window.location.assign("/admin");
    } catch {
      showMessage("目前無法連線，請稍後重試。");
    } finally {
      submitButton.disabled = false;
    }
  });

  checkExistingSession();
})();
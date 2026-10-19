(() => {
  const form = document.querySelector("[data-referral-code-form]");
  if (!form) return;

  const username = form.querySelector("[data-referral-username]");
  const code = form.querySelector("[data-referral-code]");
  const updateCode = () => {
    const normalized = username.value
      .replace(/[^a-z0-9._-]/gi, "")
      .toUpperCase()
      .slice(0, 74);
    code.value = normalized ? "MAWIZ-" + normalized : "";
  };

  username.addEventListener("input", updateCode);
  updateCode();
})();

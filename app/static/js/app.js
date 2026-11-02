(() => {
  const form = document.querySelector("[data-referral-code-form]");
  if (!form) return;

  const username = form.querySelector("[data-referral-username]");
  const code = form.querySelector("[data-referral-code]");
  const type = form.querySelector("[name=referral_type]");
  const updateCode = () => {
    const normalized = username.value.replace(/[^a-z0-9._-]/gi, "").toUpperCase().slice(0, 68);
    const prefix = !type || type.value === "normal" ? "MAWIZ-" : (type.value === "sug" ? "SUG-" : "AMB-");
    code.value = normalized ? prefix + normalized : "";
  };
  username.addEventListener("input", updateCode);
  if (type) type.addEventListener("change", updateCode);
  updateCode();
})();

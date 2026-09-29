/* Small, dependency-free enhancements for implemented forms. */
document.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-password-toggle]");
  if (!toggle) return;

  const input = document.getElementById(toggle.dataset.passwordToggle);
  if (!input) return;

  const revealing = input.type === "password";
  input.type = revealing ? "text" : "password";
  toggle.setAttribute("aria-pressed", String(revealing));
  toggle.textContent = revealing ? "Hide" : "Show";
});

/* Confirm destructive submits, then guard against double submission. */
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;

  if (form.hasAttribute("data-confirm-submit")) {
    const prompt = form.getAttribute("data-confirm-text") || "Are you sure?";
    if (!window.confirm(prompt)) {
      event.preventDefault();
      return;
    }
  }

  if (form.hasAttribute("data-disable-on-submit")) {
    const button = form.querySelector('button[type="submit"]');
    if (button && !button.disabled) {
      button.disabled = true;
      const busyText = button.dataset.busyText;
      if (busyText) button.textContent = busyText;
    }
  }
});

/* Fill checkout delivery fields when a saved address is selected. */
document.addEventListener("change", (event) => {
  const choice = event.target.closest(
    'input[name="saved_address"][data-address-json]'
  );
  if (!choice) return;

  let data;
  try {
    data = JSON.parse(choice.dataset.addressJson);
  } catch (error) {
    return;
  }
  for (const [key, value] of Object.entries(data)) {
    const field = document.getElementById(`id_${key}`);
    if (field) field.value = value;
  }
});

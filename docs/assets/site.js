/* Pentool site — the only script on the site.
 *
 * It does exactly three things and nothing when the markup is absent:
 *  1. slot picker on the pricing page (recompute the price);
 *  2. "Buy PRO" dialog (e-mail + slots → invoice → redirect to the provider);
 *  3. nothing else — no fonts, no analytics, no trackers.
 *
 * All money numbers come from data attributes rendered by tools/site/build.py,
 * so the price is defined in exactly one place (tools/site/config.py).
 */
(() => {
  "use strict";

  const body = document.body;
  const firstSlot = Number(body.dataset.priceFirst || 0);
  const extraSlot = Number(body.dataset.priceExtra || 0);
  const checkoutApi = body.dataset.checkout || "";

  const picker = document.querySelector(".slot-picker");
  const priceEl = document.getElementById("plan-price");
  const periodEl = document.getElementById("plan-period");
  const modal = document.getElementById("buy-modal");
  const emailEl = document.getElementById("buy-email");
  const hintEl = document.getElementById("buy-hint");
  const confirmEl = document.getElementById("buy-confirm");
  const slotsEl = document.getElementById("buy-slots");
  const modalPriceEl = document.getElementById("buy-price");

  const activeSlots = () => {
    const active = document.querySelector(".slot-btn.is-active");
    return Number(active?.dataset.slots || 1);
  };

  const totalPrice = (slots) => firstSlot + extraSlot * (slots - 1);

  const paint = (slots) => {
    if (priceEl) priceEl.textContent = "$" + totalPrice(slots);
    if (periodEl && picker) {
      const template = picker.dataset.periodTemplate || "{n}";
      periodEl.textContent = template.replace("{n}", String(slots));
    }
    if (slotsEl) slotsEl.textContent = (body.dataset.msgSlots || "{n}").replace("{n}", String(slots));
    if (modalPriceEl) modalPriceEl.textContent = "$" + totalPrice(slots);
  };

  // ── 1. Slot picker ──────────────────────────────────────────────────────
  document.querySelectorAll(".slot-btn").forEach((button) => {
    button.addEventListener("click", () => {
      document
        .querySelectorAll(".slot-btn")
        .forEach((other) => other.classList.toggle("is-active", other === button));
      paint(Number(button.dataset.slots || 1));
    });
  });

  // ── 2. Checkout dialog ──────────────────────────────────────────────────
  const showHint = (message, isError) => {
    if (!hintEl) return;
    hintEl.textContent = message;
    hintEl.classList.toggle("is-error", Boolean(isError));
  };

  const hintDefault = hintEl ? hintEl.textContent : "";

  const openModal = () => {
    if (!modal) return;
    paint(activeSlots());
    showHint(hintDefault, false);
    if (!modal.open) modal.showModal();
    emailEl?.focus();
  };

  document.querySelectorAll("[data-buy]").forEach((button) => {
    button.addEventListener("click", openModal);
  });

  document.getElementById("buy-cancel")?.addEventListener("click", () => modal?.close());

  // A click on the backdrop lands on the dialog element itself.
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) modal.close();
  });

  const setBusy = (busy) => {
    if (!confirmEl) return;
    if (!confirmEl.dataset.label) confirmEl.dataset.label = confirmEl.textContent;
    confirmEl.disabled = busy;
    confirmEl.textContent = busy ? body.dataset.msgWaiting || confirmEl.dataset.label : confirmEl.dataset.label;
  };

  const startCheckout = async () => {
    if (!emailEl || !confirmEl) return;
    const email = emailEl.value.trim();
    if (!email.includes("@") || email.length < 5) {
      emailEl.setAttribute("aria-invalid", "true");
      showHint(body.dataset.msgEmail || "", true);
      emailEl.focus();
      return;
    }
    emailEl.removeAttribute("aria-invalid");

    if (!checkoutApi) {
      showHint(body.dataset.msgFail || "", true);
      return;
    }

    confirmEl.dataset.label = confirmEl.dataset.label || confirmEl.textContent;
    setBusy(true);
    try {
      const response = await fetch(checkoutApi, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, slots: activeSlots() }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.payment_url) {
        throw new Error(data.error || "HTTP " + response.status);
      }
      window.location.href = data.payment_url;
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      showHint(`${body.dataset.msgFail || "Checkout failed"} (${detail})`, true);
    } finally {
      setBusy(false);
    }
  };

  confirmEl?.addEventListener("click", startCheckout);

  emailEl?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      startCheckout();
    }
  });
})();

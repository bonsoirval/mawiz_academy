// Same-origin bridge to avoid a form-submission redirect chain being blocked
// by browser CSP enforcement. The server validates this URL before rendering.
document.addEventListener('DOMContentLoaded', () => {
  const link = document.querySelector('[data-paystack-checkout-link]');
  if (!link) return;

  let target;
  try {
    target = new URL(link.href, window.location.href);
  } catch (_) {
    console.error('Paystack redirect unavailable: invalid checkout URL.');
    return;
  }

  if (target.protocol !== 'https:' || target.hostname.toLowerCase() !== 'checkout.paystack.com') {
    console.error('Paystack redirect blocked: unexpected checkout host.');
    return;
  }

  window.location.replace(target.href);
});

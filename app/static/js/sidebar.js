/* Collapsible navigation controller. Kept external to comply with the strict CSP. */
(() => {
  "use strict";
  const STORAGE_KEY = "mawiz-sidebar-collapsed";
  const MOBILE_QUERY = "(max-width: 850px)";

  function getSavedCollapsedState() {
    try { return window.localStorage.getItem(STORAGE_KEY) === "1"; }
    catch (_) { return false; }
  }

  function saveCollapsedState(collapsed) {
    try { window.localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0"); }
    catch (_) { /* Continue to work when storage is blocked. */ }
  }

  function initSidebar() {
    const body = document.body;
    const sidebar = document.getElementById("app-sidebar");
    const toggles = Array.from(document.querySelectorAll("[data-sidebar-toggle]"));
    if (!body || !sidebar || !toggles.length) return;
    if (toggles.every((toggle) => toggle.dataset.sidebarInitialized === "1")) return;
    toggles.forEach((toggle) => { toggle.dataset.sidebarInitialized = "1"; });
    const toggle = toggles[0];
    const setTogglePresentation = (label, text, expanded) => {
      toggles.forEach((button) => {
        const icon = button.querySelector(".sidebar-toggle-icon");
        const labelNode = button.querySelector(".sidebar-toggle-label");
        if (icon) icon.textContent = text; else button.textContent = text;
        if (labelNode) labelNode.textContent = label;
        button.setAttribute("aria-label", label + " navigation");
        button.setAttribute("title", label + " navigation");
        button.setAttribute("aria-expanded", String(expanded));
      });
    };

    const mobileQuery = window.matchMedia(MOBILE_QUERY);

    function applyDesktopState(collapsed, persist = true) {
      body.classList.toggle("sidebar-collapsed", Boolean(collapsed));
      setTogglePresentation(collapsed ? "Expand" : "Collapse", collapsed ? "☰" : "‹", !collapsed);
      if (persist) saveCollapsedState(Boolean(collapsed));
    }

    function setMobileOpen(open) {
      body.classList.toggle("sidebar-open", Boolean(open));
      setTogglePresentation(open ? "Close" : "Menu", open ? "×" : "☰", Boolean(open));
    }

    // Apply saved desktop preference before the page is displayed.
    applyDesktopState(getSavedCollapsedState(), false);
    if (mobileQuery.matches) setMobileOpen(false);

    // Capture the click at document level so unrelated page handlers cannot swallow it.
    document.addEventListener("click", function (event) {
      const clickedToggle = event.target && event.target.closest
        ? event.target.closest("[data-sidebar-toggle]") : null;
      if (!clickedToggle || !toggles.includes(clickedToggle)) return;
      event.preventDefault();
      event.stopPropagation();
      if (mobileQuery.matches) {
        setMobileOpen(!body.classList.contains("sidebar-open"));
      } else {
        applyDesktopState(!body.classList.contains("sidebar-collapsed"));
      }
    }, true);

    document.addEventListener("click", function (event) {
      if (!mobileQuery.matches || !body.classList.contains("sidebar-open")) return;
      if (sidebar.contains(event.target) || toggles.some((button) => button.contains(event.target))) return;
      setMobileOpen(false);
    });

    sidebar.querySelectorAll(".sidebar-link").forEach((link) => {
      const icon = link.querySelector("span");
      const textNodes = Array.from(link.childNodes)
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => node.textContent.trim()).filter(Boolean);
      const accessibleLabel = textNodes.join(" ") || link.getAttribute("aria-label") || link.textContent.trim();
      if (accessibleLabel) {
        link.setAttribute("aria-label", accessibleLabel);
        link.setAttribute("title", accessibleLabel);
      }
      if (icon) icon.setAttribute("aria-hidden", "true");
    });

    const handleViewportChange = () => {
      body.classList.remove("sidebar-open");
      if (mobileQuery.matches) setMobileOpen(false);
      else applyDesktopState(getSavedCollapsedState(), false);
    };
    if (typeof mobileQuery.addEventListener === "function") {
      mobileQuery.addEventListener("change", handleViewportChange);
    } else if (typeof mobileQuery.addListener === "function") {
      mobileQuery.addListener(handleViewportChange);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSidebar, { once: true });
  } else {
    initSidebar();
  }
})();

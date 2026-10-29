"use strict";
(() => {
  const menu = document.getElementById("menu");
  const search = document.getElementById("search");
  const toast = document.getElementById("toast");
  let toastTimer;
  function announce(text) {
    toast.textContent = text;
    toast.style.display = "block";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.style.display = "none"; }, 2200);
  }
  menu.addEventListener("click", () => {
    const open = document.body.classList.toggle("nav-open");
    menu.setAttribute("aria-expanded", String(open));
  });
  document.querySelectorAll("nav a").forEach(link => {
    link.addEventListener("click", () => {
      document.body.classList.remove("nav-open");
      menu.setAttribute("aria-expanded", "false");
      if (search.value) { search.value = ""; search.dispatchEvent(new Event("input")); }
      if (link.getAttribute("href") === location.hash) markActive();
    });
  });
  function markActive() {
    const target = location.hash || "#quickstart";
    const sidebar = document.getElementById("sidebar");
    document.querySelectorAll("nav a").forEach(link => {
      const active = link.getAttribute("href") === target;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
    document.querySelectorAll("nav details").forEach(group => {
      const active = !!group.querySelector("a.active");
      group.classList.toggle("contains-active", active);
      if (active) group.open = true;
    });
    const active = document.querySelector("nav a.active");
    if (active && getComputedStyle(sidebar).display !== "none") {
      const bounds = sidebar.getBoundingClientRect();
      const item = active.getBoundingClientRect();
      if (item.top < bounds.top || item.bottom > bounds.bottom) {
        sidebar.scrollTop += item.top - bounds.top - bounds.height / 2;
      }
    }
  }
  window.addEventListener("hashchange", markActive);
  markActive();
  document.querySelectorAll(".tabs").forEach(tabs => {
    function select(button) {
      tabs.querySelectorAll("button").forEach(b => {
        const active = b === button;
        b.setAttribute("aria-selected", String(active));
        b.tabIndex = active ? 0 : -1;
        document.getElementById(b.getAttribute("aria-controls")).hidden = !active;
      });
    }
    tabs.addEventListener("click", e => { if (e.target.matches("button")) select(e.target); });
    tabs.addEventListener("keydown", e => {
      const buttons = Array.from(tabs.querySelectorAll("button"));
      const current = buttons.indexOf(document.activeElement);
      if (current < 0 || !["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const next = e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : (current + (e.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
      select(buttons[next]); buttons[next].focus();
    });
    select(tabs.querySelector("button"));
  });
  document.querySelectorAll(".copy").forEach(button => {
    button.addEventListener("click", async () => {
      const content = button.parentElement.querySelector("code").textContent;
      try {
        if (navigator.clipboard && window.isSecureContext) {
          try { await navigator.clipboard.writeText(content); announce("已复制代码"); return; } catch (_) { /* file:// fallback */ }
        }
        const area = document.createElement("textarea");
        area.value = content;
        area.style.cssText = "position:fixed;left:0;top:0;width:1px;height:1px;opacity:0";
        document.body.appendChild(area); area.focus(); area.select();
        const success = document.execCommand("copy"); area.remove(); button.focus();
        if (!success) throw new Error("clipboard unavailable");
        announce("已复制代码");
      } catch (_) {
        const range = document.createRange();
        range.selectNodeContents(button.parentElement.querySelector("code"));
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        announce("浏览器禁止剪贴板，代码已选中，请按 Ctrl+C");
      }
    });
  });
  const items = Array.from(document.querySelectorAll(".searchable"));
  const index = items.map(item => item.textContent.toLocaleLowerCase());
  search.addEventListener("input", () => {
    const terms = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    let visible = 0;
    items.forEach((item, i) => {
      const match = terms.every(term => index[i].includes(term));
      item.hidden = !match; if (match) visible++;
    });
    document.getElementById("search-status").textContent = terms.length ? `${visible} 个匹配条目` : "按名称、字段和功能搜索";
  });
  search.addEventListener("keydown", e => {
    if (e.key === "Enter") { const first = items.find(i => !i.hidden); if (first) first.scrollIntoView(); }
    if (e.key === "Escape") { search.value = ""; search.dispatchEvent(new Event("input")); }
  });
  search.dispatchEvent(new Event("input"));
})();

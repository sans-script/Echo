// A pretend Echo host: answers the page with DEMO_SNAP / DEMO_CONVS, then opens the view named in ?view=.
(() => {
  const listeners = [];
  const post = data => listeners.forEach(f => f({ data }));
  window.chrome = window.chrome || {};
  window.chrome.webview = {
    addEventListener: (type, f) => { if (type === "message") listeners.push(f); },
    postMessage: m => {
      if (m && m.cmd === "convs" && m.action === "list") setTimeout(() => post({ type: "convs", action: "list", result: DEMO_CONVS }), 0);
    },
  };
  try { localStorage.clear(); } catch (e) {}
  const click = sel => { const el = document.querySelector(sel); if (el) el.click(); };
  window.addEventListener("load", () => {
    post(DEMO_SNAP);
    const [view, arg] = (new URLSearchParams(location.search).get("view") || "").split(":");
    setTimeout(() => {
      const pick = (name, tab) => { state.selected = name; state.tab = tab; $("#teams").dataset.html = ""; render(); renderDrawer(); };
      if (view === "agent") pick(arg, arg === "Aaron" ? "activity" : "usage");
      if (view === "room") click("#room-btn");
      if (view === "settings") openSettings();
      if (view === "chats") { pick(arg, "activity"); openConvs(arg); }
    }, 100);
  });
})();

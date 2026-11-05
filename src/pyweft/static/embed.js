// <pyweft-app>: a PyWeft app inside any web page.
//
//   <script src="https://example.org/my-app/embed.js" defer></script>
//   <pyweft-app data-customer="42" route="/orders" label="Orders"></pyweft-app>
//
// `pyweft build` puts this file next to the app's index.html. The element
// shows the app in an iframe, so its Python, styles and page addresses stay
// apart from the host page's (and two apps on one page don't meet), and
// grows with the app's content. Attributes:
//   src     the app's address; default: the folder this script came from
//   route   the page to open, "/orders/7" (the app's #/ address)
//   height  a fixed height ("600px", "80vh"); default: the content's height
//   label   what the frame is called for screen readers (default "App")
//   data-*  read in Python with pyweft.embed.params()
// Events the app sends with pyweft.embed.send(name, detail) arrive as DOM
// events of that name on the element (detail in event.detail), plus
// "pyweft-ready" once the app is on screen. el.send(name, detail) calls
// the app's pyweft.embed.on_message listeners.
(() => {
  if (customElements.get("pyweft-app")) return;
  const HERE = document.currentScript ? new URL(".", document.currentScript.src).href : document.baseURI;

  class PyWeftApp extends HTMLElement {
    connectedCallback() {
      if (this.frame) return;
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML =
        "<style>:host{display:block}iframe{display:block;width:100%;border:0;height:150px}</style>";
      this.frame = document.createElement("iframe");
      this.frame.title = this.getAttribute("label") || "App";
      this.frame.src = this.frameUrl();
      const fixed = this.getAttribute("height");
      if (fixed) this.frame.style.height = fixed;
      this.growth = [];
      root.appendChild(this.frame);
      instances.add(this);
    }

    disconnectedCallback() {
      instances.delete(this);
      this.frame?.remove();
      this.frame = null;
      this.shadowRoot && this.shadowRoot.replaceChildren();
    }

    frameUrl() {
      const url = new URL(this.getAttribute("src") || HERE, document.baseURI);
      for (const attr of this.attributes) {
        if (attr.name.startsWith("data-")) url.searchParams.set(attr.name.slice(5), attr.value);
      }
      url.searchParams.set("pyweft-embed", "1");
      const route = this.getAttribute("route");
      if (route) url.hash = "#" + (route.startsWith("/") ? route : "/" + route);
      return url.href;
    }

    // To the app's pyweft.embed.on_message listeners.
    send(name, detail = null) {
      if (!this.frame?.contentWindow) return;
      const message = JSON.stringify({ pyweft: "message", name: String(name), detail: JSON.stringify(detail) });
      this.frame.contentWindow.postMessage(message, new URL(this.frame.src).origin);
    }

    resize(height) {
      if (this.getAttribute("height") || this.stopped) return;
      const now = performance.now();
      const current = parseFloat(this.frame.style.height) || 0;
      if (height > current) {
        // Content sized to the frame (min-height: 100vh plus a margin) grows
        // the frame, which grows the content again. Stop such a loop.
        this.growth = this.growth.filter((t) => now - t < 2000).concat(now);
        if (this.growth.length > 30) {
          this.stopped = true;
          console.warn("<pyweft-app>: the app keeps growing with its frame (100vh content?); " +
            'give the element a height, such as height="600px"');
          return;
        }
      }
      this.frame.style.height = `${Math.ceil(height)}px`;
    }
  }

  const instances = new Set();
  window.addEventListener("message", (event) => {
    if (typeof event.data !== "string" || !event.data.startsWith('{"pyweft"')) return;
    const el = [...instances].find((x) => x.frame && x.frame.contentWindow === event.source);
    if (!el) return;
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (data.pyweft === "size") el.resize(Number(data.height) || 0);
    else if (data.pyweft === "ready") el.dispatchEvent(new CustomEvent("pyweft-ready", { bubbles: true }));
    else if (data.pyweft === "event") {
      let detail = null;
      try {
        detail = JSON.parse(data.detail);
      } catch {}
      el.dispatchEvent(new CustomEvent(data.name, { detail, bubbles: true, composed: true }));
    }
  });

  customElements.define("pyweft-app", PyWeftApp);
})();

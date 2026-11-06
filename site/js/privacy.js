/* Aviso de cookies y Meta Pixel. El pixel NO se carga hasta que la persona acepta.
   El ID del pixel lo carga Miriam en el panel (Contacto). Si está vacío, no se instala nada y no se muestra el aviso. */
(function () {
  var V = window.VDV || {}, d = document, KEY = "vdv_cookies";
  var ID = String(V.pixel_id || "").replace(/\D/g, "");
  function leer() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function guardar(v) { try { localStorage.setItem(KEY, v); } catch (e) {} }

  /* El viaje al que pertenece un "?id=slug" (o un link a viaje.html?id=slug) */
  function viajeDe(texto) {
    var m = /[?&]id=([^&#]+)/.exec(texto || "");
    try { return m && V.porId ? V.porId(decodeURIComponent(m[1])) : null; } catch (e) { return null; }
  }
  /* Datos del viaje para los eventos: el de la página, o el de la tarjeta donde se hizo clic */
  function datosViaje(origen, base) {
    var s = viajeDe(location.search);
    if (!s && origen && origen.closest) {
      var card = origen.closest("article, .card"), l = card && card.querySelector("a[href*='viaje.html?id=']");
      s = l && viajeDe(l.getAttribute("href"));
    }
    if (s) { base.content_name = s.destino; base.content_ids = [s.id]; base.content_type = "product"; base.content_category = s.empresa; }
    return base;
  }

  var cargado = false;
  function cargarPixel() {
    if (cargado || !ID) return; cargado = true;
    !function (f, b, e, v, n, t, s) { if (f.fbq) return; n = f.fbq = function () { n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments); };
      if (!f._fbq) f._fbq = n; n.push = n; n.loaded = !0; n.version = "2.0"; n.queue = []; t = b.createElement(e); t.async = !0; t.src = v;
      s = b.getElementsByTagName(e)[0]; s.parentNode.insertBefore(t, s); }(window, d, "script", "https://connect.facebook.net/en_US/fbevents.js");
    fbq("init", ID); fbq("track", "PageView");
    /* Ver un viaje: la página viaje.html?id=... */
    var s = viajeDe(location.search);
    if (s) fbq("track", "ViewContent", { content_name: s.destino, content_ids: [s.id], content_type: "product", content_category: s.empresa });
  }
  function evento(nombre, datos) { if (cargado && window.fbq) window.fbq("track", nombre, datos || {}); }

  /* Consulta enviada (formularios) y clic en WhatsApp */
  d.addEventListener("submit", function (e) {
    var f = e.target; if (f && f.matches && f.matches("form[data-lead]")) evento("Lead", datosViaje(f, { content_name: f.getAttribute("data-origen") || "formulario" }));
  }, true);
  d.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-wa], a[href*='wa.me']");
    if (a) evento("Contact", datosViaje(a, { content_name: location.pathname.replace(/^\//, "") || "inicio" }));
  }, true);

  /* Aviso */
  function css() {
    if (d.getElementById("vdv-ck-css")) return;
    var s = d.createElement("style"); s.id = "vdv-ck-css";
    s.textContent = ".vdv-ck{position:fixed;left:max(16px,env(safe-area-inset-left,0px));right:max(16px,env(safe-area-inset-right,0px));bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:80;max-width:560px;background:#1b1b1f;color:#f2f2f4;border-radius:16px;padding:16px 18px;box-shadow:0 14px 40px rgba(0,0,0,.4);font:14px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif}" +
      ".vdv-ck p{margin:0 0 12px}.vdv-ck a{color:#fff;text-decoration:underline}.vdv-ck .b{display:flex;gap:8px;flex-wrap:wrap}" +
      ".vdv-ck button{font:600 14px inherit;border-radius:10px;padding:10px 16px;border:0;cursor:pointer}.vdv-ck .si{background:#fff;color:#1b1b1f}.vdv-ck .no{background:transparent;color:#fff;border:1.5px solid rgba(255,255,255,.5)}" +
      "@media(min-width:700px){.vdv-ck{right:auto}}";
    d.head.appendChild(s);
  }
  function aviso() {
    if (d.querySelector(".vdv-ck")) return; css();
    var b = d.createElement("div"); b.className = "vdv-ck"; b.setAttribute("role", "dialog"); b.setAttribute("aria-label", "Cookies");
    b.innerHTML = "<p>Usamos cookies de medición (Meta) para saber qué viajes interesan y mejorar nuestros anuncios. Solo se activan si las aceptás. <a href=\"privacidad.html\">Más información</a></p>" +
      "<div class=\"b\"><button class=\"si\" type=\"button\">Aceptar</button><button class=\"no\" type=\"button\">Solo las necesarias</button></div>";
    b.querySelector(".si").onclick = function () { guardar("si"); b.remove(); cargarPixel(); };
    b.querySelector(".no").onclick = function () { guardar("no"); b.remove(); };
    d.body.appendChild(b);
  }

  window.VDVprivacidad = { reabrir: function () { aviso(); } };
  d.addEventListener("click", function (e) { var a = e.target.closest && e.target.closest("[data-cookies]"); if (a) { e.preventDefault(); aviso(); } });

  if (!ID) return;                       /* sin pixel configurado: no hay nada que consentir */
  var c = leer();
  if (c === "si") cargarPixel(); else if (c !== "no") aviso();
})();

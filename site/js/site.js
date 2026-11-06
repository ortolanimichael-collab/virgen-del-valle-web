/* Comportamiento común: menú, apariciones, enlaces de WhatsApp, formularios y listas de salidas. */
(function () {
  var V = window.VDV, d = document;
  d.documentElement.classList.add("js");

  /* Menú móvil */
  var b = d.querySelector(".burger");
  if (b) {
    b.addEventListener("click", function () {
      var o = d.body.classList.toggle("nav-open");
      b.setAttribute("aria-expanded", o ? "true" : "false");
    });
    d.querySelectorAll(".nav a").forEach(function (a) { a.addEventListener("click", function () { d.body.classList.remove("nav-open"); b.setAttribute("aria-expanded", "false"); }); });
  }

  /* Enlaces de WhatsApp: data-wa="texto del mensaje" */
  function wa() {
    d.querySelectorAll("[data-wa]").forEach(function (a) { a.href = V.waLink(a.getAttribute("data-wa")); a.target = "_blank"; a.rel = "noopener"; });
  }
  wa();

  /* Aparición al hacer scroll */
  var io = "IntersectionObserver" in window ? new IntersectionObserver(function (es) {
    es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
  }, { threshold: .12 }) : null;
  function reveal(root) {
    (root || d).querySelectorAll(".rv:not(.in)").forEach(function (el) { if (io) io.observe(el); else el.classList.add("in"); });
  }
  reveal();

  /* Formularios: se arma el mensaje, se guarda la consulta en el navegador (en la Etapa 2 va al panel) y se abre WhatsApp */
  d.querySelectorAll("form[data-lead]").forEach(function (f) {
    f.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var fd = new FormData(f), partes = [], dato = {};
      fd.forEach(function (v, k) { if (String(v).trim()) { dato[k] = String(v).trim(); } });
      var plantilla = f.getAttribute("data-lead");
      var msg = plantilla.replace(/\{(\w+)\}/g, function (_, k) { return dato[k] || "—"; });
      try {
        var lista = JSON.parse(localStorage.getItem("vdv_consultas") || "[]");
        lista.push({ fecha: new Date().toISOString(), origen: f.getAttribute("data-origen") || "", datos: dato });
        localStorage.setItem("vdv_consultas", JSON.stringify(lista));
      } catch (e) {}
      /* Se guarda en el panel de Miriam (si el servidor responde). Si falla, igual se abre WhatsApp. */
      try {
        fetch("/api/consulta", { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
          body: JSON.stringify({ origen: f.getAttribute("data-origen") || "", datos: dato, texto: msg, pagina: location.pathname + location.search }) }).catch(function () {});
      } catch (e) {}
      var url = V.waLink(msg), gracias = f.querySelector(".gracias");
      if (gracias) { gracias.innerHTML = '¡Listo! Si no se abrió WhatsApp, <a href="' + url + '" target="_blank" rel="noopener" style="font-weight:800">tocá acá para enviar tu consulta</a>.'; gracias.hidden = false; }
      try { window.open(url, "_blank", "noopener"); } catch (e) {}
    });
  });

  /* Tarjetas de salidas.  VDVapp.salidas(contenedor, lista, funciónQueDevuelveHTML) */
  window.VDVapp = {
    reveal: reveal,
    salidas: function (el, lista, tpl) {
      if (!el) return;
      el.innerHTML = lista.length ? lista.map(tpl).join("") : '<p class="vacio">No hay salidas con ese filtro por ahora. Escribinos y te avisamos cuando haya.</p>';
      reveal(el); wa();
    },
    filtrar: function (lista, tipo) {
      return tipo && tipo !== "todos" ? lista.filter(function (s) { return s.tipo.indexOf(tipo) > -1; }) : lista;
    },
    badge: function (s) {
      var t = V.estadoTxt[s.estado];
      return t ? '<span class="badge ' + s.estado + '">' + t + '</span>' : "";
    }
  };
})();

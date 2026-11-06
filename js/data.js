/* Contenido de la web. En la Etapa 2 esto lo carga Miriam desde el panel de administración
   (salidas, fechas, precios, cupos, estados y fotos) y este archivo se reemplaza por la base de datos.
   estado: "disponible" | "ultimos" | "agotado" | "preventa". Las salidas con fecha pasada se ocultan solas. */
window.VDV = {
  nombre: "Virgen del Valle",
  legajo: "EVT Legajo 15772",
  direccion: "Obispo Trejo 110",
  ciudad: "Río Tercero, Córdoba",
  telefono: "03571 15-59-3669",
  whatsapp: "5493571593669",
  instagram: "virgendelvalleagencia",
  seguidores: "4.500+",
  empresas: {
    vdv:    { nombre: "Virgen del Valle", rubro: "Agencia de viajes y turismo", url: "index.html" },
    trekia: { nombre: "Trekia", rubro: "Trekking y naturaleza", url: "trekia.html" },
    aula:   { nombre: "Aula Viajera", rubro: "Viajes educativos y de egresados", url: "aula-viajera.html" }
  },
  tipos: [
    { id: "todos", nombre: "Todos" },
    { id: "grupal", nombre: "Grupales en bus" },
    { id: "religioso", nombre: "Religiosos" },
    { id: "naturaleza", nombre: "Trekking y naturaleza" },
    { id: "internacional", nombre: "Internacionales" }
  ],
  salidas: [
    { id: "ballenas", empresa: "vdv", fecha: "2026-11-03", dia: "3 nov", destino: "Ballenas y Glaciares", lugar: "Patagonia", detalle: "Trelew, Puerto Madryn y El Calafate en coche cama", incluye: ["Bus coche cama", "Hoteles", "Excursiones"], precio: "$1.425.000", nota: "3 cuotas sin interés", img: "img/ballenas.jpg", region: "argentina", tipo: ["grupal", "naturaleza"], estado: "ultimos" },
    { id: "lujan", empresa: "vdv", fecha: "2026-11-08", dia: "8 al 11 nov", destino: "Papa León XIV en Luján", lugar: "Buenos Aires", detalle: "Bus desde Río Tercero y zona con coordinación permanente", incluye: ["Bus semi cama", "Asistencia médica", "Coordinador"], precio: "$145.000", nota: "por persona", img: "img/lujan.jpg", region: "argentina", tipo: ["religioso", "grupal"], estado: "ultimos" },
    { id: "cordoba", empresa: "vdv", fecha: "2026-11-10", dia: "10 nov", destino: "Papa León XIV en Córdoba", lugar: "Córdoba", detalle: "Traslado ida y vuelta con asistencia médica a bordo", incluye: ["Traslado", "Refrigerio", "Asistencia médica"], precio: "$55.000", nota: "desde, por persona", img: "img/catedral.jpg", region: "argentina", tipo: ["religioso", "grupal"], estado: "agotado" },
    { id: "buffo", empresa: "trekia", fecha: "2026-11-15", dia: "15 nov", destino: "Capilla Buffo y Los Quebrachitos", lugar: "Sierras de Córdoba", detalle: "Trekking de dificultad media, 10 km ida y vuelta", incluye: ["Bus grupal", "Guía", "Visita al museo"], precio: "$85.000", nota: "por persona", img: "img/capilla.jpg", region: "argentina", tipo: ["naturaleza", "grupal"], estado: "disponible", dificultad: "Media", km: "10 km" },
    { id: "sanluis", empresa: "vdv", fecha: "2026-11-28", dia: "28 nov", destino: "Termas de San Luis y La Carolina", lugar: "San Luis", detalle: "2 días y 1 noche en hotel 3 estrellas con media pensión", incluye: ["Bus semi cama", "Hotel", "Media pensión"], precio: "$255.000", nota: "costo total", img: "img/sierras.jpg", region: "argentina", tipo: ["grupal"], estado: "disponible" },
    { id: "buzios", empresa: "vdv", fecha: "2027-01-03", dia: "ene y feb", destino: "Charter a Buzios", lugar: "Brasil", detalle: "Vuelo directo desde Córdoba, salidas todos los domingos", incluye: ["Vuelo directo", "Hotel", "Traslados"], precio: "USD 889", nota: "desde, base doble", img: "img/buzios.jpg", region: "brasil", tipo: ["internacional"], estado: "preventa", destacado: true },
    { id: "floripa", empresa: "vdv", fecha: "2027-02-03", dia: "feb", destino: "Brasil Joven en Canasvieiras", lugar: "Florianópolis, Brasil", detalle: "7 noches, salidas el 3, 10, 17 y 24 de febrero", incluye: ["Bus", "7 noches", "Coordinación"], precio: "USD 469", nota: "tarifa lanzamiento", img: "img/floripa.jpg", region: "brasil", tipo: ["internacional", "grupal"], estado: "preventa" },
    { id: "galinhas", empresa: "vdv", fecha: "2027-02-06", dia: "6 feb", destino: "Porto de Galinhas", lugar: "Brasil", detalle: "8 noches con pensión completa y vuelo desde Córdoba", incluye: ["Vuelo", "Pensión completa", "Traslados"], precio: "USD 1.699", nota: "desde, plan familia", img: "img/bahia-barcos.jpg", region: "brasil", tipo: ["internacional"], estado: "disponible" },
    { id: "italia", empresa: "vdv", fecha: "2027-05-03", dia: "3 al 19 may", destino: "Sur de Italia: Puglia y Sicilia", lugar: "Italia", detalle: "16 días con salida acompañada, de Roma al Mediterráneo", incluye: ["Aéreo", "14 noches", "Acompañante"], precio: "USD 3.680", nota: "por persona", img: "img/coliseo.jpg", region: "europa", tipo: ["internacional"], estado: "ultimos" },
    /* Ejemplos para mostrar cómo se ve cada empresa. Se reemplazan por las salidas reales en el panel. */
    { id: "uritorco", empresa: "trekia", fecha: "2026-12-06", dia: "6 dic", destino: "Cerro Uritorco", lugar: "Capilla del Monte, Córdoba", detalle: "Ascenso guiado con salida de madrugada. Dificultad media", incluye: ["Guía", "Seguro", "Traslado"], precio: "$70.000", nota: "por persona (ejemplo)", img: "img/trekking-cerro.jpg", region: "argentina", tipo: ["naturaleza", "grupal"], estado: "disponible", dificultad: "Media", km: "9 km" },
    { id: "cascadas", empresa: "trekia", fecha: "2027-01-17", dia: "17 ene", destino: "Selva y cascadas", lugar: "Sierras de Córdoba", detalle: "Caminata por sendero de selva serrana con baño en cascada", incluye: ["Guía", "Seguro", "Merienda"], precio: "$65.000", nota: "por persona (ejemplo)", img: "img/selva-trekking.jpg", region: "argentina", tipo: ["naturaleza"], estado: "ultimos", dificultad: "Baja", km: "6 km" },
    { id: "andes", empresa: "trekia", fecha: "2027-03-13", dia: "13 al 16 mar", destino: "Cordillera de los Andes", lugar: "Mendoza", detalle: "Trekking de montaña con base en Uspallata (ejemplo)", incluye: ["Bus", "Hotel", "Guías de montaña"], precio: "Consultá", nota: "salida en preventa (ejemplo)", img: "img/montana-nieve.jpg", region: "argentina", tipo: ["naturaleza", "grupal"], estado: "preventa", dificultad: "Alta", km: "—" }
  ],
  destinos: [
    { nombre: "Buzios", lugar: "Brasil", desde: "USD 889", img: "img/buzios.jpg", q: "brasil" },
    { nombre: "Patagonia", lugar: "Argentina", desde: "$1.425.000", img: "img/perito-moreno.jpg", q: "argentina" },
    { nombre: "Italia", lugar: "Europa", desde: "USD 3.680", img: "img/venecia.jpg", q: "europa" },
    { nombre: "Cruceros", lugar: "Brasil y Caribe", desde: "Consultá", img: "img/crucero.jpg", q: "crucero" },
    { nombre: "Mendoza", lugar: "Argentina", desde: "Consultá", img: "img/mendoza.jpg", q: "argentina" }
  ],
  /* Aula Viajera: programas de ejemplo, a confirmar con Miriam */
  programas: [
    { id: "egresados", nombre: "Viaje de egresados", lugar: "Bariloche, Brasil y más", detalle: "Salidas para cursos completos, con coordinadores y seguro de viaje.", img: "img/floripa.jpg" },
    { id: "educativo", nombre: "Viajes educativos", lugar: "Córdoba, Buenos Aires, Mendoza", detalle: "Recorridos con contenido curricular para primaria y secundaria.", img: "img/mendoza.jpg" },
    { id: "contingentes", nombre: "Contingentes escolares", lugar: "Desde Río Tercero y zona", detalle: "Bus, coordinación permanente y asistencia médica a bordo.", img: "img/grupo-escalada.jpg" },
    { id: "familias", nombre: "Escapadas de fin de curso", lugar: "Sierras y termas", detalle: "Salidas de 1 o 2 días para cerrar el año con el grupo.", img: "img/sierras.jpg" }
  ]
};
(function (V) {
  V.hoy = function () { var d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  V.diasHasta = function (iso) { return Math.round((new Date(iso + "T00:00:00") - V.hoy()) / 86400000); };
  /* Salidas vigentes: las vencidas desaparecen solas. */
  V.vigentes = function (empresa) {
    return V.salidas.filter(function (s) { return V.diasHasta(s.fecha) >= 0 && (!empresa || s.empresa === empresa); })
      .sort(function (a, b) { return a.fecha < b.fecha ? -1 : 1; });
  };
  V.porId = function (id) { return V.salidas.filter(function (s) { return s.id === id; })[0]; };
  V.waLink = function (texto) { return "https://wa.me/" + V.whatsapp + "?text=" + encodeURIComponent(texto || "Hola! Quiero consultar por un viaje"); };
  V.estadoTxt = { ultimos: "Últimos cupos", agotado: "Agotado", preventa: "Preventa", disponible: "" };
  V.esc = function (t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
})(window.VDV);

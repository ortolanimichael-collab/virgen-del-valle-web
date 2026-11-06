"""Web de Virgen del Valle, Trekia y Aula Viajera + panel de administración (Etapa 2).

* Las páginas públicas están en site/ (HTML, CSS, JS, fotos). Lo único que cambia es /js/data.js, que ahora arma el servidor
  con las salidas cargadas en el panel (en vez de un archivo escrito a mano).
* El panel está en /admin: salidas (alta, edición, estados, fotos, borrado), consultas que llegan de los formularios y datos de contacto.
* Base de datos: DATABASE_URL (Postgres en Render). Sin esa variable usa un archivo SQLite local, para probar en la compu.
"""
import hmac
import io
import json
import os
import re
import secrets
import time
import unicodedata
from datetime import date, datetime, timedelta
from functools import wraps
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for)
from flask_sqlalchemy import SQLAlchemy

AQUI = Path(__file__).resolve().parent
SITE = AQUI / "site"
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

EMPRESAS = {"vdv": "Virgen del Valle", "trekia": "Trekia"}
ESTADOS = {"disponible": "Disponible", "ultimos": "Últimos cupos", "agotado": "Agotado", "preventa": "Preventa"}
TIPOS = {"grupal": "Grupal en bus", "religioso": "Religioso", "naturaleza": "Trekking y naturaleza", "internacional": "Internacional"}
REGIONES = {"argentina": "Argentina", "brasil": "Brasil", "europa": "Europa", "crucero": "Cruceros", "otro": "Otro"}
DIFICULTADES = ["", "Baja", "Media", "Alta"]
ESTADOS_CONSULTA = {"nueva": "Nueva", "contactada": "Contactada", "senia": "Dejó seña", "vendida": "Vendida", "descartada": "Descartada"}
CONTACTO = {"whatsapp": "WhatsApp (solo números, con 549 y código de área)", "telefono": "Teléfono que se muestra", "direccion": "Dirección",
            "ciudad": "Ciudad", "instagram": "Instagram (sin @)", "legajo": "Legajo EVT"}

db = SQLAlchemy()


def hoy():
    return datetime.now(TZ).date()


def ahora():
    return datetime.now(TZ).replace(tzinfo=None)


# ====================================================================== modelos

class Salida(db.Model):
    __tablename__ = "salida"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)      # va en el link: viaje.html?id=<slug>
    empresa = db.Column(db.String(12), nullable=False, default="vdv")
    destino = db.Column(db.String(120), nullable=False)
    lugar = db.Column(db.String(120), default="")
    fecha = db.Column(db.Date, nullable=False, index=True)
    dia = db.Column(db.String(40), default="")                                    # «8 al 11 nov» (si está vacío se arma con la fecha)
    detalle = db.Column(db.String(300), default="")
    incluye = db.Column(db.Text, default="")                                      # una cosa por línea
    precio = db.Column(db.String(40), default="Consultá")
    nota = db.Column(db.String(80), default="")                                   # «3 cuotas sin interés», «por persona»
    img = db.Column(db.String(200), default="img/sierras.jpg")                    # ruta de una foto de la web o /media/<id>
    region = db.Column(db.String(12), default="argentina")
    tipos = db.Column(db.String(120), default="grupal")                           # separados por coma
    estado = db.Column(db.String(12), nullable=False, default="disponible")
    dificultad = db.Column(db.String(10), default="")
    km = db.Column(db.String(20), default="")
    destacado = db.Column(db.Boolean, default=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creada = db.Column(db.DateTime, default=ahora)
    actualizada = db.Column(db.DateTime, default=ahora, onupdate=ahora)

    @property
    def vencida(self):
        return self.fecha < hoy()

    @property
    def lista_incluye(self):
        return [x.strip() for x in (self.incluye or "").splitlines() if x.strip()]

    @property
    def lista_tipos(self):
        return [t for t in (self.tipos or "").split(",") if t]

    def a_json(self):
        d = dict(id=self.slug, empresa=self.empresa, fecha=self.fecha.isoformat(), dia=self.dia or dia_corto(self.fecha), destino=self.destino,
                 lugar=self.lugar or "", detalle=self.detalle or "", incluye=self.lista_incluye, precio=self.precio or "Consultá",
                 nota=self.nota or "", img=self.img or "img/sierras.jpg", region=self.region or "argentina", tipo=self.lista_tipos, estado=self.estado)
        if self.dificultad:
            d["dificultad"] = self.dificultad
        if self.km:
            d["km"] = self.km
        if self.destacado:
            d["destacado"] = True
        return d


class Imagen(db.Model):
    """Fotos subidas desde el panel. Se guardan en la base (el disco de Render no es permanente)."""
    __tablename__ = "imagen"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120))
    datos = db.Column(db.LargeBinary, nullable=False)
    creada = db.Column(db.DateTime, default=ahora)


class Consulta(db.Model):
    __tablename__ = "consulta"
    id = db.Column(db.Integer, primary_key=True)
    creada = db.Column(db.DateTime, default=ahora, index=True)
    origen = db.Column(db.String(60), default="")
    pagina = db.Column(db.String(200), default="")
    nombre = db.Column(db.String(120), default="")
    datos = db.Column(db.Text, default="{}")                                      # JSON con lo que completó la persona
    texto = db.Column(db.Text, default="")                                        # el mensaje que se armó para WhatsApp
    estado = db.Column(db.String(12), nullable=False, default="nueva", index=True)
    recordar = db.Column(db.Date)                                                 # fecha para volver a escribirle
    nota = db.Column(db.String(300), default="")

    @property
    def dict_datos(self):
        try:
            return json.loads(self.datos or "{}")
        except ValueError:
            return {}


class Ajuste(db.Model):
    __tablename__ = "ajuste"
    clave = db.Column(db.String(40), primary_key=True)
    valor = db.Column(db.String(300), default="")


# ====================================================================== utilidades

def dia_corto(f):
    return f"{f.day} {MESES[f.month - 1]}"


def slugify(txt):
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:50] or "viaje"


def slug_unico(destino, fecha, propio_id=None):
    base = f"{slugify(destino)}-{fecha.strftime('%Y%m')}"
    slug, n = base, 2
    while True:
        otro = Salida.query.filter_by(slug=slug).first()
        if otro is None or otro.id == propio_id:
            return slug
        slug, n = f"{base}-{n}", n + 1


def ajustes():
    base = json.loads((AQUI / "contenido.json").read_text(encoding="utf-8"))
    guardados = {a.clave: a.valor for a in Ajuste.query.all()}
    return {k: (guardados.get(k) or base.get(k, "")) for k in CONTACTO}


def datos_publicos():
    """Todo lo que usa la web pública: el contenido fijo + contacto + las salidas activas y no vencidas."""
    d = json.loads((AQUI / "contenido.json").read_text(encoding="utf-8"))
    d.update(ajustes())
    q = Salida.query.filter(Salida.activa.is_(True), Salida.fecha >= hoy()).order_by(Salida.fecha, Salida.id)
    d["salidas"] = [s.a_json() for s in q.all()]
    return d


def imagenes_de_la_web():
    return sorted(p.name for p in (SITE / "img").glob("*.jpg") if not p.name.startswith("logo"))


def reducir_imagen(archivo):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(archivo)).convert("RGB")
    im.thumbnail((1600, 1600))
    b = io.BytesIO()
    im.save(b, format="JPEG", quality=82, optimize=True)
    return b.getvalue()


# ====================================================================== app

def crear_app(config=None):
    app = Flask(__name__, static_folder=str(AQUI / "admin_static"), static_url_path="/admin-static", template_folder=str(AQUI / "templates"))
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    app.config.update(
        SQLALCHEMY_DATABASE_URI=url or f"sqlite:///{AQUI / 'vdv.db'}", SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True}, SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=12 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")), PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        ADMIN_USER=os.environ.get("ADMIN_USER", "miriam"), ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""))
    if config:
        app.config.update(config)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        sembrar()

    # ------------------------------------------------------------------ seguridad básica
    intentos = {}

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return session["csrf"]

    app.jinja_env.globals.update(csrf_token=csrf_token, ESTADOS=ESTADOS, EMPRESAS=EMPRESAS, TIPOS=TIPOS, REGIONES=REGIONES,
                                 ESTADOS_CONSULTA=ESTADOS_CONSULTA, hoy=hoy)

    @app.before_request
    def proteger():
        if request.path.startswith("/admin"):
            if request.method == "POST" and not hmac.compare_digest(request.form.get("_csrf", ""), session.get("csrf", "x")):
                abort(400, "Formulario vencido: volvé a cargar la página.")

    @app.after_request
    def cabeceras(r):
        r.headers.setdefault("X-Content-Type-Options", "nosniff")
        r.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith("/admin"):
            r.headers["Cache-Control"] = "no-store"
            r.headers["X-Robots-Tag"] = "noindex"
            r.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return r

    def admin(fn):
        @wraps(fn)
        def w(*a, **kw):
            if not session.get("admin"):
                return redirect(url_for("login", siguiente=request.path))
            return fn(*a, **kw)
        return w

    # ------------------------------------------------------------------ sitio público
    @app.get("/js/data.js")
    def data_js():
        cuerpo = "window.VDV = " + json.dumps(datos_publicos(), ensure_ascii=False) + ";\n" + (SITE / "js" / "helpers.js").read_text(encoding="utf-8")
        return Response(cuerpo, mimetype="application/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/")
    def inicio():
        return send_from_directory(SITE, "index.html", max_age=0)

    @app.get("/viaje.html")
    def viaje():
        """La página de un viaje. Con ?id= se le agregan los datos para que, al compartir el link (WhatsApp, Meta), salga con foto y título."""
        html = (SITE / "viaje.html").read_text(encoding="utf-8")
        s = Salida.query.filter_by(slug=request.args.get("id", ""), activa=True).first()
        if s is not None and not s.vencida:
            img = s.img if s.img.startswith(("http", "/")) else "/" + s.img
            og = (f'<meta property="og:type" content="website"><meta property="og:title" content="{escape(s.destino)} · {escape(s.dia or dia_corto(s.fecha))} · {escape(s.precio or "")}">'
                  f'<meta property="og:description" content="{escape(s.detalle or "Salida con Virgen del Valle")}">'
                  f'<meta property="og:image" content="{escape(request.url_root.rstrip("/") + img)}"><meta property="og:url" content="{escape(request.url)}">'
                  f'<meta name="twitter:card" content="summary_large_image">')
            html = html.replace("</head>", og + "</head>", 1)
        return Response(html, mimetype="text/html", headers={"Cache-Control": "no-cache"})

    @app.get("/media/<int:iid>")
    def media(iid):
        im = db.session.get(Imagen, iid) or abort(404)
        return Response(im.datos, mimetype="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.post("/api/consulta")
    def api_consulta():
        ip = (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()
        ahora_t = time.time()
        recientes = [t for t in intentos.get(("c", ip), []) if ahora_t - t < 600]
        if len(recientes) >= 10:
            return jsonify(ok=False), 429
        intentos[("c", ip)] = recientes + [ahora_t]
        j = request.get_json(silent=True) or {}
        datos = {str(k)[:40]: str(v)[:300] for k, v in (j.get("datos") or {}).items() if isinstance(j.get("datos"), dict)}
        if not datos:
            return jsonify(ok=False), 400
        c = Consulta(origen=str(j.get("origen") or "")[:60], pagina=str(j.get("pagina") or "")[:200], datos=json.dumps(datos, ensure_ascii=False),
                     texto=str(j.get("texto") or "")[:1500], nombre=(datos.get("nombre") or "")[:120])
        db.session.add(c)
        db.session.commit()
        return jsonify(ok=True)

    @app.get("/<path:ruta>")
    def estatico(ruta):
        if ruta.startswith(("admin", "api/", "media/")) or ".." in ruta:
            abort(404)
        if not (SITE / ruta).is_file():
            abort(404)
        return send_from_directory(SITE, ruta, max_age=3600 if ruta.startswith(("img/", "css/", "js/")) else 0)

    # ------------------------------------------------------------------ login
    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            ip = (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()
            t = time.time()
            fallos = [x for x in intentos.get(("l", ip), []) if t - x < 900]
            if len(fallos) >= 8:
                flash("Demasiados intentos. Esperá unos minutos.", "error")
                return render_template("admin/login.html"), 429
            clave = app.config["ADMIN_PASSWORD"]
            ok = bool(clave) and hmac.compare_digest(request.form.get("password", ""), clave) and \
                hmac.compare_digest(request.form.get("usuario", "").strip().lower(), app.config["ADMIN_USER"].lower())
            if ok:
                session.clear()
                session.permanent = True
                session["admin"] = True
                destino = request.args.get("siguiente", "")
                return redirect(destino if destino.startswith("/admin") else url_for("salidas"))
            intentos[("l", ip)] = fallos + [t]
            flash("Usuario o contraseña incorrectos.", "error")
        return render_template("admin/login.html", sin_clave=not app.config["ADMIN_PASSWORD"])

    @app.post("/admin/salir")
    def salir():
        session.clear()
        return redirect(url_for("login"))

    # ------------------------------------------------------------------ salidas
    @app.get("/admin")
    @admin
    def admin_inicio():
        return redirect(url_for("salidas"))

    @app.get("/admin/salidas")
    @admin
    def salidas():
        q = Salida.query.order_by(Salida.fecha, Salida.id).all()
        proximas = [s for s in q if not s.vencida]
        vencidas = [s for s in q if s.vencida][::-1]
        nuevas = Consulta.query.filter_by(estado="nueva").count()
        return render_template("admin/salidas.html", proximas=proximas, vencidas=vencidas, nuevas=nuevas, base=request.url_root.rstrip("/"))

    def _leer_salida(s, f):
        """Pasa el formulario a la salida. Devuelve un mensaje de error o None."""
        destino = " ".join((f.get("destino") or "").split())[:120]
        try:
            fecha = date.fromisoformat((f.get("fecha") or "").strip())
        except ValueError:
            return "Elegí la fecha de la salida."
        if not destino:
            return "Poné el destino."
        s.destino, s.fecha = destino, fecha
        s.empresa = f.get("empresa") if f.get("empresa") in EMPRESAS else "vdv"
        s.lugar = " ".join((f.get("lugar") or "").split())[:120]
        s.dia = " ".join((f.get("dia") or "").split())[:40]
        s.detalle = " ".join((f.get("detalle") or "").split())[:300]
        s.incluye = "\n".join(x.strip()[:80] for x in (f.get("incluye") or "").splitlines() if x.strip())[:800]
        s.precio = " ".join((f.get("precio") or "").split())[:40] or "Consultá"
        s.nota = " ".join((f.get("nota") or "").split())[:80]
        s.region = f.get("region") if f.get("region") in REGIONES else "argentina"
        s.tipos = ",".join(t for t in f.getlist("tipos") if t in TIPOS)
        s.estado = f.get("estado") if f.get("estado") in ESTADOS else "disponible"
        s.dificultad = f.get("dificultad") if f.get("dificultad") in DIFICULTADES else ""
        s.km = " ".join((f.get("km") or "").split())[:20]
        s.destacado = bool(f.get("destacado"))
        s.activa = bool(f.get("activa"))
        archivo = request.files.get("foto")
        if archivo and archivo.filename:
            try:
                im = Imagen(nombre=archivo.filename[:120], datos=reducir_imagen(archivo.stream))
            except Exception:
                return "No pude leer esa foto. Probá con un JPG o PNG."
            db.session.add(im)
            db.session.flush()
            s.img = f"/media/{im.id}"
        else:
            elegida = f.get("foto_web") or ""
            if elegida in imagenes_de_la_web():
                s.img = f"img/{elegida}"
            elif not s.img:
                s.img = "img/sierras.jpg"
        return None

    @app.route("/admin/salidas/nueva", methods=["GET", "POST"])
    @admin
    def salida_nueva():
        s = Salida(empresa=request.args.get("empresa") if request.args.get("empresa") in EMPRESAS else "vdv", fecha=hoy() + timedelta(days=30),
                   estado="disponible", activa=True, slug="")
        if request.method == "POST":
            error = _leer_salida(s, request.form)
            if error:
                db.session.rollback()
                flash(error, "error")
            else:
                s.slug = slug_unico(s.destino, s.fecha)
                db.session.add(s)
                db.session.commit()
                flash(f"Salida «{s.destino}» cargada. Ya se ve en la web.", "ok")
                return redirect(url_for("salidas"))
        return render_template("admin/salida_form.html", s=s, nueva=True, fotos=imagenes_de_la_web(), DIFICULTADES=DIFICULTADES)

    @app.route("/admin/salidas/<int:sid>", methods=["GET", "POST"])
    @admin
    def salida_editar(sid):
        s = db.session.get(Salida, sid) or abort(404)
        if request.method == "POST":
            error = _leer_salida(s, request.form)
            if error:
                db.session.rollback()
                flash(error, "error")
                s = db.session.get(Salida, sid)
            else:
                db.session.commit()
                flash("Cambios guardados.", "ok")
                return redirect(url_for("salidas"))
        return render_template("admin/salida_form.html", s=s, nueva=False, fotos=imagenes_de_la_web(), DIFICULTADES=DIFICULTADES,
                               base=request.url_root.rstrip("/"))

    @app.post("/admin/salidas/<int:sid>/estado")
    @admin
    def salida_estado(sid):
        """Cambio rápido desde la lista: Disponible / Últimos cupos / Agotado / Preventa."""
        s = db.session.get(Salida, sid) or abort(404)
        if request.form.get("estado") in ESTADOS:
            s.estado = request.form["estado"]
            db.session.commit()
            flash(f"«{s.destino}»: {ESTADOS[s.estado].lower()}.", "ok")
        return redirect(url_for("salidas") + f"#s{sid}")

    @app.post("/admin/salidas/<int:sid>/visible")
    @admin
    def salida_visible(sid):
        s = db.session.get(Salida, sid) or abort(404)
        s.activa = not s.activa
        db.session.commit()
        flash(f"«{s.destino}» " + ("vuelve a verse en la web." if s.activa else "quedó oculta (no se borra)."), "ok")
        return redirect(url_for("salidas") + f"#s{sid}")

    @app.post("/admin/salidas/<int:sid>/duplicar")
    @admin
    def salida_duplicar(sid):
        o = db.session.get(Salida, sid) or abort(404)
        n = Salida(**{c: getattr(o, c) for c in ("empresa", "destino", "lugar", "dia", "detalle", "incluye", "precio", "nota", "img", "region",
                                                  "tipos", "dificultad", "km", "destacado")}, fecha=max(o.fecha, hoy()) + timedelta(days=7), estado="disponible",
                   activa=True, slug="")
        n.dia = ""
        n.slug = slug_unico(n.destino, n.fecha)
        db.session.add(n)
        db.session.commit()
        flash("Copié la salida. Ahora poné la fecha nueva.", "ok")
        return redirect(url_for("salida_editar", sid=n.id))

    @app.post("/admin/salidas/<int:sid>/borrar")
    @admin
    def salida_borrar(sid):
        s = db.session.get(Salida, sid) or abort(404)
        nombre = s.destino
        db.session.delete(s)
        db.session.commit()
        flash(f"Borré «{nombre}».", "ok")
        return redirect(url_for("salidas"))

    # ------------------------------------------------------------------ consultas
    @app.route("/admin/consultas", methods=["GET", "POST"])
    @admin
    def consultas():
        if request.method == "POST":
            c = db.session.get(Consulta, int(request.form.get("id") or 0)) or abort(404)
            if request.form.get("estado") in ESTADOS_CONSULTA:
                c.estado = request.form["estado"]
            try:
                c.recordar = date.fromisoformat(request.form.get("recordar") or "")
            except ValueError:
                c.recordar = None
            c.nota = " ".join((request.form.get("nota") or "").split())[:300]
            db.session.commit()
            flash("Guardado.", "ok")
            return redirect(url_for("consultas", filtro=request.args.get("filtro", "")) + f"#c{c.id}")
        filtro = request.args.get("filtro", "")
        q = Consulta.query
        if filtro == "recordar":
            q = q.filter(Consulta.recordar.isnot(None), Consulta.recordar <= hoy(), Consulta.estado.in_(["nueva", "contactada", "senia"]))
        elif filtro in ESTADOS_CONSULTA:
            q = q.filter_by(estado=filtro)
        lista = q.order_by(Consulta.creada.desc()).limit(300).all()
        cuentas = {k: Consulta.query.filter_by(estado=k).count() for k in ESTADOS_CONSULTA}
        por_recordar = Consulta.query.filter(Consulta.recordar.isnot(None), Consulta.recordar <= hoy(),
                                             Consulta.estado.in_(["nueva", "contactada", "senia"])).count()
        return render_template("admin/consultas.html", lista=lista, filtro=filtro, cuentas=cuentas, por_recordar=por_recordar, ajustes=ajustes())

    # ------------------------------------------------------------------ contacto
    @app.route("/admin/contacto", methods=["GET", "POST"])
    @admin
    def contacto():
        if request.method == "POST":
            for k in CONTACTO:
                v = " ".join((request.form.get(k) or "").split())[:300]
                if k == "whatsapp":
                    v = re.sub(r"\D", "", v)
                a = db.session.get(Ajuste, k) or Ajuste(clave=k)
                a.valor = v
                db.session.add(a)
            db.session.commit()
            flash("Datos de contacto guardados.", "ok")
            return redirect(url_for("contacto"))
        return render_template("admin/contacto.html", valores=ajustes(), CONTACTO=CONTACTO)

    return app


def sembrar():
    """La primera vez, carga las salidas que ya tenía la web (de ejemplo) para que no arranque vacía."""
    if Salida.query.count():
        return
    for x in json.loads((AQUI / "salidas_iniciales.json").read_text(encoding="utf-8")):
        f = date.fromisoformat(x["fecha"])
        db.session.add(Salida(slug=slug_unico(x["destino"], f), empresa=x["empresa"], destino=x["destino"], lugar=x.get("lugar", ""), fecha=f, dia=x.get("dia", ""),
                              detalle=x.get("detalle", ""), incluye="\n".join(x.get("incluye", [])), precio=x.get("precio", ""), nota=x.get("nota", ""),
                              img=x.get("img", ""), region=x.get("region", "argentina"), tipos=",".join(x.get("tipo", [])), estado=x.get("estado", "disponible"),
                              dificultad=x.get("dificultad", ""), km=x.get("km", ""), destacado=bool(x.get("destacado"))))
        db.session.flush()
    db.session.commit()


app = crear_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)

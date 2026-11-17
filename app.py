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

from sqlalchemy import or_
from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for)
from extensiones import db
import modelos4
import portada
import respaldo
import catalogo
import aula
import drive

AQUI = Path(__file__).resolve().parent
SITE = AQUI / "site"
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

EMPRESAS = {"vdv": "Virgen del Valle", "trekia": "Trekia"}
ESTADOS = {"disponible": "Disponible", "ultimos": "Últimos cupos", "agotado": "Agotado", "preventa": "Preventa"}
TIPOS = {"grupal": "Grupal en bus nacional", "individual": "Salida individual (bus nacional)", "bus_internacional": "Grupal en bus internacional",
         "aereo": "Aéreo nacional o internacional", "naturaleza": "Trekking y naturaleza", "internacional": "Internacional (otro)",
         "religioso": "Religioso", "escapada": "Escapada cerca de casa (Trekia)"}
REGIONES = {"argentina": "Argentina", "brasil": "Brasil", "america": "América (Caribe y otros)", "europa": "Europa", "crucero": "Cruceros", "otro": "Otro"}
DIFICULTADES = ["", "Baja", "Media", "Alta"]
ESTADOS_CONSULTA = {"nueva": "Nueva", "contactada": "Contactada", "senia": "Dejó seña", "vendida": "Vendida", "descartada": "Descartada"}
CONTACTO = {"whatsapp": "WhatsApp (solo números, con 549 y código de área)", "telefono": "Teléfono que se muestra", "direccion": "Dirección",
            "ciudad": "Ciudad", "instagram": "Instagram (sin @)", "legajo": "Legajo EVT",
            "razon_social": "Razón social (para la política de privacidad)", "cuit": "CUIT", "email": "Mail de contacto (para pedidos de datos)",
            "pixel_id": "ID del Meta Pixel (solo números; vacío = sin pixel)",
            "resenas_url": "Link para dejar reseñas en Google (vacío = no se muestra el botón)"}

def hoy():
    return datetime.now(TZ).date()


def ahora():
    return datetime.now(TZ).replace(tzinfo=None)


# ====================================================================== modelos

class Salida(db.Model):
    __tablename__ = "vdv_salida"
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
    cupos = db.Column(db.Integer)                                                 # lugares totales (vacío = sin control de cupos)
    a_confirmar = db.Column(db.Boolean, default=False)                            # «Fecha a confirmar»: se muestra aunque la fecha haya pasado
    ficha = db.Column(db.Text, default="")                                        # datos del viaje, uno por línea: «Hotel: Cadi Palace»
    creada = db.Column(db.DateTime, default=ahora)
    actualizada = db.Column(db.DateTime, default=ahora, onupdate=ahora)

    @property
    def vencida(self):
        return not self.a_confirmar and self.fecha < hoy()

    @property
    def dia_txt(self):
        if self.a_confirmar:
            return self.dia or "Fecha a confirmar"
        return self.dia or dia_corto(self.fecha)

    @property
    def lista_incluye(self):
        return [x.strip() for x in (self.incluye or "").splitlines() if x.strip()]

    @property
    def lista_tipos(self):
        return [t for t in (self.tipos or "").split(",") if t]

    def a_json(self):
        d = dict(id=self.slug, empresa=self.empresa, fecha=self.fecha.isoformat(), dia=self.dia_txt, destino=self.destino,
                 lugar=self.lugar or "", detalle=self.detalle or "", incluye=self.lista_incluye, precio=self.precio or "Consultá",
                 nota=self.nota or "", img=self.img or "img/sierras.jpg", region=self.region or "argentina", tipo=self.lista_tipos, estado=self.estado)
        if self.dificultad:
            d["dificultad"] = self.dificultad
        if self.km:
            d["km"] = self.km
        if self.destacado:
            d["destacado"] = True
        if self.a_confirmar:
            d["confirmar"] = True
        if self.lista_ficha:
            d["ficha"] = self.lista_ficha
        return d

    @property
    def lista_ficha(self):
        filas = []
        for linea in (self.ficha or "").splitlines():
            k, sep, v = linea.partition(":")
            if sep and k.strip() and v.strip():
                filas.append([k.strip(), v.strip()])
        return filas


class Imagen(db.Model):
    """Fotos subidas desde el panel. Se guardan en la base (el disco de Render no es permanente)."""
    __tablename__ = "vdv_imagen"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120))
    datos = db.Column(db.LargeBinary, nullable=False)                             # vacío si la foto está en Google Drive
    drive_id = db.Column(db.String(80))                                           # id del archivo en Drive
    creada = db.Column(db.DateTime, default=ahora)


class Consulta(db.Model):
    __tablename__ = "vdv_consulta"
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
    __tablename__ = "vdv_ajuste"
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
    portada.aplicar(d, d)
    q = Salida.query.filter(Salida.activa.is_(True), or_(Salida.fecha >= hoy(), Salida.a_confirmar.is_(True))).order_by(Salida.fecha, Salida.id)
    d["salidas"] = [s.a_json() for s in q.all()]
    d["galeria"] = aula.galeria_publica()
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


def guardar_imagen(nombre, archivo, carpeta=("Varios",)):
    """Achica la foto y la guarda en Google Drive si está conectado; si no (o si Drive falla), en la base.
    Devuelve el objeto Imagen ya agregado a la sesión (con id). Lanza ValueError si no es una imagen."""
    try:
        datos = reducir_imagen(archivo)
    except Exception as e:
        raise ValueError("No es una imagen") from e
    nombre = (nombre or "foto").rsplit(".", 1)[0][:110] + ".jpg"
    im = Imagen(nombre=nombre[:120], datos=datos)
    if drive.conectado():
        try:
            im.drive_id = drive.subir(datos, nombre, "image/jpeg", carpeta)
            im.datos = b""
        except Exception as e:
            print(f"[drive] no se pudo subir {nombre}: {e}", flush=True)
    db.session.add(im)
    db.session.flush()
    return im


def borrar_imagen(im):
    if im.drive_id and drive.conectado():
        drive.borrar(im.drive_id)
    db.session.delete(im)


def montar_drive(app, admin, Imagen):
    def vuelta_url():
        base = os.environ.get("PUBLIC_URL", "").rstrip("/") or request.url_root.rstrip("/")
        if os.environ.get("RENDER") and base.startswith("http://"):
            base = "https://" + base[7:]
        return base + "/admin/drive/vuelta"

    @app.get("/admin/drive")
    @admin
    def drive_panel():
        from sqlalchemy import func
        en_base = db.session.query(func.count(Imagen.id)).filter(Imagen.drive_id.is_(None)).scalar()
        en_drive = db.session.query(func.count(Imagen.id)).filter(Imagen.drive_id.isnot(None)).scalar()
        return render_template("admin/drive.html", configurado=drive.configurado(), cuenta=drive.cuenta(), vuelta=vuelta_url(),
                               en_base=en_base, en_drive=en_drive)

    @app.post("/admin/drive/conectar")
    @admin
    def drive_conectar():
        if not drive.configurado():
            flash("Faltan GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET en Render.", "error")
            return redirect(url_for("drive_panel"))
        session["drive_estado"] = secrets.token_urlsafe(24)
        return redirect(drive.url_autorizar(vuelta_url(), session["drive_estado"]))

    @app.get("/admin/drive/vuelta")
    @admin
    def drive_vuelta():
        estado = session.pop("drive_estado", None)
        if request.args.get("error"):
            flash("Cancelaste la conexión con Google Drive.", "error")
        elif not estado or not hmac.compare_digest(estado, request.args.get("state", "")):
            flash("La conexión venció. Probá de nuevo.", "error")
        else:
            try:
                email = drive.terminar_autorizacion(request.args.get("code", ""), vuelta_url())
                drive.carpeta()
                flash(f"Google Drive conectado{' (' + email + ')' if email else ''}. Desde ahora las fotos y videos se guardan ahí.", "ok")
            except Exception as e:
                db.session.rollback()
                flash(str(e) if isinstance(e, drive.DriveError) else "No se pudo conectar con Google Drive.", "error")
        return redirect(url_for("drive_panel"))

    @app.post("/admin/drive/desconectar")
    @admin
    def drive_desconectar():
        drive.desconectar()
        flash("Google Drive desconectado. Lo que ya estaba en Drive se sigue viendo hasta que lo vuelvas a conectar; lo nuevo va a la base.", "ok")
        return redirect(url_for("drive_panel"))

    @app.post("/admin/drive/pasar")
    @admin
    def drive_pasar():
        """Pasa a Drive las fotos que están en la base, de a 25 por vez (para no cortar por tiempo)."""
        if not drive.conectado():
            abort(400)
        pasadas = 0
        for im in Imagen.query.filter(Imagen.drive_id.is_(None)).order_by(Imagen.id).limit(25).all():
            try:
                im.drive_id = drive.subir(im.datos, im.nombre or f"foto-{im.id}.jpg", "image/jpeg", ("Fotos anteriores",))
                im.datos = b""
                db.session.commit()
                pasadas += 1
            except Exception as e:
                db.session.rollback()
                flash(f"Se cortó: {e}", "error")
                break
        quedan = Imagen.query.filter(Imagen.drive_id.is_(None)).count()
        flash(f"Pasé {pasadas} fotos a Drive." + (f" Quedan {quedan}: tocá el botón otra vez." if quedan else " ¡Ya están todas!"), "ok")
        return redirect(url_for("drive_panel"))


# ====================================================================== app

def crear_app(config=None):
    app = Flask(__name__, static_folder=str(AQUI / "admin_static"), static_url_path="/admin-static", template_folder=str(AQUI / "templates"))
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    app.config.update(
        SQLALCHEMY_DATABASE_URI=url or f"sqlite:///{AQUI / 'vdv.db'}", SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True}, SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=(aula.MAX_VIDEO_MB + 2) * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")), PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        ADMIN_USER=os.environ.get("ADMIN_USER", "miriam"), ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""))
    if config:
        app.config.update(config)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        migrar()
        sembrar()
        sembrar_temporada_2027()
        sembrar_temporada_2027b()
        aula.sembrar_escuelas(Ajuste)

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
            enviado = request.headers.get("X-CSRF") or request.form.get("_csrf", "")
            if request.method == "POST" and not hmac.compare_digest(enviado, session.get("csrf", "x")):
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
        datos = im.datos
        if not datos and im.drive_id:
            try:
                datos = drive.bajar(im.drive_id)
            except Exception:
                abort(503)
        return Response(datos, mimetype="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})

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
        from sqlalchemy import func
        ocup = dict(db.session.query(modelos4.Pasajero.salida_id, func.count(modelos4.Pasajero.id))
                    .filter(modelos4.Pasajero.estado != "cancelado").group_by(modelos4.Pasajero.salida_id).all())
        return render_template("admin/salidas.html", proximas=proximas, vencidas=vencidas, nuevas=nuevas, ocup=ocup, base=request.url_root.rstrip("/"))

    def _leer_salida(s, f):
        """Pasa el formulario a la salida. Devuelve un mensaje de error o None."""
        destino = " ".join((f.get("destino") or "").split())[:120]
        try:
            fecha = date.fromisoformat((f.get("fecha") or "").strip())
        except ValueError:
            if not f.get("a_confirmar"):
                return "Elegí la fecha de la salida (o marcá «Fecha a confirmar»)."
            fecha = s.fecha or hoy()
        if not destino:
            return "Poné el destino."
        s.destino, s.fecha = destino, fecha
        s.a_confirmar = bool(f.get("a_confirmar"))
        s.empresa = f.get("empresa") if f.get("empresa") in EMPRESAS else "vdv"
        s.lugar = " ".join((f.get("lugar") or "").split())[:120]
        s.dia = " ".join((f.get("dia") or "").split())[:40]
        s.detalle = " ".join((f.get("detalle") or "").split())[:300]
        s.incluye = "\n".join(x.strip()[:80] for x in (f.get("incluye") or "").splitlines() if x.strip())[:800]
        s.ficha = "\n".join(x.strip()[:400] for x in (f.get("ficha") or "").splitlines() if ":" in x)[:4000]
        s.precio = " ".join((f.get("precio") or "").split())[:40] or "Consultá"
        s.nota = " ".join((f.get("nota") or "").split())[:80]
        s.region = f.get("region") if f.get("region") in REGIONES else "argentina"
        s.tipos = ",".join(t for t in f.getlist("tipos") if t in TIPOS)
        s.estado = f.get("estado") if f.get("estado") in ESTADOS else "disponible"
        s.dificultad = f.get("dificultad") if f.get("dificultad") in DIFICULTADES else ""
        s.km = " ".join((f.get("km") or "").split())[:20]
        s.destacado = bool(f.get("destacado"))
        try:
            c = int((f.get("cupos") or "").strip())
            s.cupos = c if 0 < c <= 5000 else None
        except ValueError:
            s.cupos = None
        s.activa = bool(f.get("activa"))
        archivo = request.files.get("foto")
        if archivo and archivo.filename:
            try:
                im = guardar_imagen(archivo.filename, archivo.stream, ("Salidas", EMPRESAS.get(s.empresa, s.empresa)))
            except Exception:
                return "No pude leer esa foto. Probá con un JPG o PNG."
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

    @app.route("/admin/salidas/importar", methods=["GET", "POST"])
    @admin
    def salidas_importar():
        """Carga muchos paquetes de una vez desde un archivo .json (el que se arma a partir de la planilla).
        Si un paquete ya existe (misma empresa, destino y fecha) lo actualiza en vez de duplicarlo."""
        if request.method == "GET":
            return render_template("admin/importar.html")
        arch = request.files.get("archivo")
        if not arch or not arch.filename:
            flash("Elegí el archivo .json.", "error")
            return redirect(url_for("salidas_importar"))
        try:
            datos = json.loads(arch.read().decode("utf-8-sig"))
            lista = datos["salidas"] if isinstance(datos, dict) else datos
            assert isinstance(lista, list)
        except Exception:
            flash("Ese archivo no es un paquete de salidas válido (.json).", "error")
            return redirect(url_for("salidas_importar"))

        def t(v, n):
            return " ".join(str(v or "").split())[:n]

        nuevas = actualizadas = 0
        errores = []
        for i, x in enumerate(lista, 1):
            try:
                destino = t(x.get("destino"), 120)
                fecha = date.fromisoformat(str(x.get("fecha")))
                empresa = x.get("empresa") if x.get("empresa") in EMPRESAS else "vdv"
                if not destino:
                    raise ValueError("sin destino")
            except Exception:
                errores.append(f"fila {i}")
                continue
            s = Salida.query.filter_by(empresa=empresa, destino=destino, fecha=fecha).first()
            if s is None:
                s = Salida(empresa=empresa, destino=destino, fecha=fecha, slug=slug_unico(destino, fecha))
                db.session.add(s)
                nuevas += 1
            else:
                actualizadas += 1
            tipos = [k for k in (x.get("tipo") or []) if k in TIPOS] or ["grupal"]
            s.lugar, s.dia, s.detalle = t(x.get("lugar"), 120), t(x.get("dia"), 40), t(x.get("detalle"), 300)
            s.incluye = "\n".join(t(k, 80) for k in (x.get("incluye") or []) if t(k, 80))[:800]
            s.ficha = "\n".join(f"{t(k, 60)}: {t(v, 400)}" for k, v in (x.get("ficha") or []) if t(k, 60) and t(v, 400))[:4000]
            s.precio, s.nota = t(x.get("precio"), 40) or "Consultá", t(x.get("nota"), 80)
            s.img = t(x.get("img"), 200) or s.img or "img/sierras.jpg"
            s.region = x.get("region") if x.get("region") in REGIONES else "argentina"
            s.tipos = ",".join(dict.fromkeys(tipos))
            s.estado = x.get("estado") if x.get("estado") in ESTADOS else "disponible"
            s.a_confirmar = bool(x.get("a_confirmar"))
            s.activa = bool(x.get("activa", True))
            s.destacado = bool(x.get("destacado"))
            db.session.flush()
        ocultas = 0
        if request.form.get("ocultar_ejemplos"):
            # Solo las salidas de ejemplo que este archivo reemplaza con datos reales (las demás quedan como están)
            reemplazadas = {"Mar del Plata", "Las Grutas", "Puerto Madryn y Península Valdés", "Bariloche y Circuito Chico",
                            "El Calafate y Glaciar Perito Moreno", "Crucero por Brasil", "Brasil: el Caribe brasileño", "Europa clásica"}
            for s in Salida.query.filter(Salida.activa.is_(True), Salida.empresa == "vdv", Salida.precio == "Consultá",
                                         Salida.destino.in_(reemplazadas), Salida.fecha >= date(2027, 1, 1)).all():
                s.activa = False
                ocultas += 1
            # Salidas originales de la web que también quedan reemplazadas (mismo producto, datos viejos)
            for destino, fecha in (("Charter a Buzios", date(2027, 1, 3)), ("Porto de Galinhas", date(2027, 2, 6))):
                for s in Salida.query.filter_by(empresa="vdv", destino=destino, fecha=fecha, activa=True).all():
                    s.activa = False
                    ocultas += 1
        db.session.commit()
        msg = f"Listo: {nuevas} salidas nuevas y {actualizadas} actualizadas."
        if ocultas:
            msg += f" Oculté {ocultas} salidas de ejemplo (siguen en el panel, por si querés volver a mostrarlas)."
        if errores:
            msg += f" No pude leer: {', '.join(errores)}."
        flash(msg, "ok" if not errores else "error")
        return redirect(url_for("salidas"))

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
        if modelos4.Pasajero.query.filter_by(salida_id=sid).count():
            flash("Esa salida tiene pasajeros anotados, así que no la borro para no perder la lista. Podés ocultarla de la web.", "error")
            return redirect(url_for("salida_editar", sid=sid))
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
                if k in ("whatsapp", "pixel_id"):
                    v = re.sub(r"\D", "", v)[:20]
                if k == "resenas_url" and v and not re.match(r"https://\S+$", v):
                    flash("El link de reseñas tiene que empezar con https:// (copialo entero desde Google). No se guardó ese dato.", "error")
                    continue
                a = db.session.get(Ajuste, k) or Ajuste(clave=k)
                a.valor = v
                db.session.add(a)
            db.session.commit()
            flash("Datos de contacto guardados.", "ok")
            return redirect(url_for("contacto"))
        return render_template("admin/contacto.html", valores=ajustes(), CONTACTO=CONTACTO)

    aula.montar(app, admin, Imagen, guardar_imagen, borrar_imagen)
    portada.montar(app, admin, lambda: json.loads((AQUI / "contenido.json").read_text(encoding="utf-8")), imagenes_de_la_web, reducir_imagen, Imagen,
                   guardar_imagen)
    montar_drive(app, admin, Imagen)
    @app.route("/admin/respaldo")
    @admin
    def respaldo_pagina():
        return render_template("admin/respaldo.html", n=respaldo.resumen(respaldo.exportar()) if request.args.get("ver") else None)

    @app.post("/admin/respaldo/descargar")
    @admin
    def respaldo_descargar():
        d = respaldo.exportar()
        return Response(json.dumps(d, ensure_ascii=False), mimetype="application/json",
                        headers={"Content-Disposition": f"attachment; filename=respaldo-virgen-del-valle-{hoy().isoformat()}.json"})

    catalogo.montar(app, admin, Salida, hoy)
    import gestion
    gestion.montar(app, admin, dict(Salida=Salida, Consulta=Consulta, hoy=hoy, ahora=ahora, ajustes=ajustes, dia_corto=dia_corto, EMPRESAS=EMPRESAS,
                                    ESTADOS=ESTADOS, ESTADOS_CONSULTA=ESTADOS_CONSULTA, MESES=MESES))
    return app


def migrar():
    """Agrega columnas nuevas a tablas que ya existían (create_all no toca tablas existentes)."""
    from sqlalchemy import inspect, text
    nuevas = [("vdv_salida", "cupos", "INTEGER"), ("vdv_salida", "a_confirmar", "BOOLEAN DEFAULT FALSE"), ("vdv_salida", "ficha", "TEXT DEFAULT ''"),
              ("vdv_imagen", "drive_id", "VARCHAR(80)"), ("vdvx_aula_video", "drive_id", "VARCHAR(80)"), ("vdvx_aula_video", "tamano", "BIGINT")]
    insp = inspect(db.engine)
    tablas = insp.get_table_names()
    for tabla, col, tipo in nuevas:
        if tabla in tablas and col not in {c["name"] for c in insp.get_columns(tabla)}:
            db.session.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}"))
            db.session.commit()


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


def sembrar_temporada_2027():
    """Una sola vez: suma los viajes de la temporada 2027 (como si Miriam los hubiera cargado en el panel),
    agrega los destinos nuevos a la portada si ya la había editado y saca los «10 km» de Capilla Buffo.
    Queda marcado en vdv_ajuste, así que si después borra o cambia algo no vuelve a aparecer."""
    marca = "semilla_2027"
    if db.session.get(Ajuste, marca):
        return
    for x in json.loads((AQUI / "salidas_2027.json").read_text(encoding="utf-8")):
        f = date.fromisoformat(x["fecha"])
        db.session.add(Salida(slug=slug_unico(x["destino"], f), empresa=x["empresa"], destino=x["destino"], lugar=x.get("lugar", ""), fecha=f, dia=x.get("dia", ""),
                              detalle=x.get("detalle", ""), incluye="\n".join(x.get("incluye", [])), precio=x.get("precio", "Consultá"), nota=x.get("nota", ""),
                              img=x.get("img", ""), region=x.get("region", "argentina"), tipos=",".join(x.get("tipo", [])), estado=x.get("estado", "disponible"),
                              dificultad=x.get("dificultad", ""), km=x.get("km", ""), destacado=bool(x.get("destacado")), activa=True))
        db.session.flush()
    for s in Salida.query.filter(Salida.km == "10 km").all():
        s.km = ""
        s.detalle = (s.detalle or "").replace(", 10 km ida y vuelta", "").replace("10 km ida y vuelta", "").strip(" ,")
    guardados = portada.guardado("destinos")
    if guardados is not None:
        fabrica = json.loads((AQUI / "contenido.json").read_text(encoding="utf-8")).get("destinos", [])
        nombres = {(d.get("nombre") or "").strip().lower() for d in guardados}
        for d in fabrica:
            if d["nombre"].strip().lower() not in nombres and len(guardados) < portada.SECCIONES["destinos"]["maximo"]:
                guardados.append(d)
        b = db.session.get(portada.Bloque, "destinos")
        b.datos = json.dumps(guardados, ensure_ascii=False)
    db.session.add(Ajuste(clave=marca, valor=hoy().isoformat()))
    db.session.commit()


def sembrar_temporada_2027b():
    """Una sola vez: paquetes internacionales (Chile, Perú, Uruguay, Brasil, Europa), nuevas categorías
    (aéreos, bus internacional, individuales) para las salidas que ya estaban y destinos internacionales nuevos en la portada."""
    marca = "semilla_2027b"
    if db.session.get(Ajuste, marca):
        return
    for x in json.loads((AQUI / "salidas_2027b.json").read_text(encoding="utf-8")):
        f = date.fromisoformat(x["fecha"])
        db.session.add(Salida(slug=slug_unico(x["destino"], f), empresa=x["empresa"], destino=x["destino"], lugar=x.get("lugar", ""), fecha=f, dia=x.get("dia", ""),
                              detalle=x.get("detalle", ""), incluye="\n".join(x.get("incluye", [])), precio=x.get("precio", "Consultá"), nota=x.get("nota", ""),
                              img=x.get("img", ""), region=x.get("region", "argentina"), tipos=",".join(x.get("tipo", [])), estado=x.get("estado", "disponible"),
                              activa=True))
        db.session.flush()
    for s in Salida.query.filter(Salida.empresa == "vdv").all():
        tipos = s.lista_tipos
        texto = " ".join([s.destino or "", s.detalle or "", s.incluye or ""]).lower()
        if "internacional" in tipos or s.region in ("brasil", "europa", "america"):
            if re.search(r"a[eé]reo|vuelo", texto):
                tipos.append("aereo")
            elif re.search(r"\bbus\b", texto):
                tipos.append("bus_internacional")
        if s.destino in ("Mar del Plata", "Las Grutas", "Bariloche y Circuito Chico") and "grupal" in tipos:
            tipos.append("individual")
        s.tipos = ",".join(dict.fromkeys(tipos))
    guardados = portada.guardado("destinos")
    if guardados is not None:
        fabrica = json.loads((AQUI / "contenido.json").read_text(encoding="utf-8")).get("destinos", [])
        nombres = {(d.get("nombre") or "").strip().lower() for d in guardados}
        for d in fabrica:
            if d["q"] != "argentina" and d["nombre"].strip().lower() not in nombres and len(guardados) < portada.SECCIONES["destinos"]["maximo"]:
                guardados.append(d)
        db.session.get(portada.Bloque, "destinos").datos = json.dumps(guardados, ensure_ascii=False)
    db.session.add(Ajuste(clave=marca, valor=hoy().isoformat()))
    db.session.commit()


app = crear_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)

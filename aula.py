"""Galería de Aula Viajera: escuelas → viajes que ya hicimos → fotos, flyers y videos.

* Panel: /admin/aula. Miriam carga las escuelas, a cada escuela le suma sus viajes (destino, año, texto)
  y a cada viaje le sube fotos, flyers y videos.
* Fotos y flyers van a la tabla de imágenes de siempre (vdv_imagen), achicadas a 1600 px.
* Videos: se puede pegar un link (YouTube, Google Drive, Instagram, Facebook, TikTok) o subir un MP4 corto.
  Los MP4 se guardan en su propia tabla (vdvx_aula_video) para que el respaldo .json no pese cientos de MB.
  Recomendado para videos largos: subirlos a YouTube (como «no listado») y pegar el link.
* Web pública: aula-viajera.html → sección «Viajes que ya hicimos». Los datos salen en /js/data.js (VDV.galeria).
"""
import json
import re
from urllib.parse import parse_qs, urlparse

from flask import Response, abort, flash, jsonify, redirect, render_template, request, url_for

from extensiones import db

MAX_VIDEO_MB = 30
CLASES = {"foto": "Fotos", "flyer": "Flyers", "video": "Videos"}

ESCUELAS_INICIALES = [
    ("Instituto Dr. Abraham Molina (IDAM)", "Los Cóndores"),
    ("Escuela Primaria Remedios Escalada de San Martín", "Río Tercero"),
    ("Escuela General Manuel Belgrano", "Río Tercero"),
    ("El Mundo de los Chicos", "Santa Rosa de Calamuchita"),
    ("Colegio Sagrado Corazón", "Villa General Belgrano"),
]


class Escuela(db.Model):
    __tablename__ = "vdv_escuela"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    localidad = db.Column(db.String(80), default="")
    orden = db.Column(db.Integer, default=0)
    activa = db.Column(db.Boolean, default=True)


class AulaViaje(db.Model):
    __tablename__ = "vdv_aula_viaje"
    id = db.Column(db.Integer, primary_key=True)
    escuela_id = db.Column(db.Integer, db.ForeignKey("vdv_escuela.id"), nullable=False, index=True)
    destino = db.Column(db.String(120), nullable=False)
    anio = db.Column(db.String(20), default="")
    tipo = db.Column(db.String(60), default="")
    texto = db.Column(db.String(600), default="")
    orden = db.Column(db.Integer, default=0)
    activo = db.Column(db.Boolean, default=True)


class AulaMedia(db.Model):
    __tablename__ = "vdv_aula_media"
    id = db.Column(db.Integer, primary_key=True)
    viaje_id = db.Column(db.Integer, db.ForeignKey("vdv_aula_viaje.id"), nullable=False, index=True)
    clase = db.Column(db.String(10), nullable=False)          # foto | flyer | video
    imagen_id = db.Column(db.Integer)                        # foto / flyer → vdv_imagen
    video_id = db.Column(db.Integer)                         # video subido → vdvx_aula_video
    url = db.Column(db.String(400), default="")              # video por link
    titulo = db.Column(db.String(120), default="")
    orden = db.Column(db.Integer, default=0)


class AulaVideo(db.Model):
    """MP4 subidos. Prefijo vdvx_ a propósito: queda fuera del respaldo .json (sería enorme)."""
    __tablename__ = "vdvx_aula_video"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120))
    tipo = db.Column(db.String(40), default="video/mp4")
    datos = db.Column(db.LargeBinary, nullable=False)


# ---------------------------------------------------------------- videos por link

def leer_link(url):
    """Devuelve {'red':..., 'embed':..., 'url':...} o None si no es un link válido."""
    url = (url or "").strip()
    if not re.match(r"^https?://", url):
        return None
    u = urlparse(url)
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    vid = ""
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [""])[0]
        else:
            m = re.match(r"^/(shorts|embed|live)/([\w-]+)", u.path)
            vid = m.group(2) if m else ""
    if vid and re.fullmatch(r"[\w-]{6,20}", vid):
        return {"red": "youtube", "embed": f"https://www.youtube-nocookie.com/embed/{vid}", "url": url, "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}
    if host == "drive.google.com":
        m = re.search(r"/file/d/([\w-]+)", u.path)
        if m:
            return {"red": "drive", "embed": f"https://drive.google.com/file/d/{m.group(1)}/preview", "url": url}
    for clave, nombre in (("instagram.com", "instagram"), ("facebook.com", "facebook"), ("fb.watch", "facebook"), ("tiktok.com", "tiktok")):
        if host.endswith(clave):
            return {"red": nombre, "embed": "", "url": url}
    return {"red": "link", "embed": "", "url": url}


# ---------------------------------------------------------------- datos públicos

def galeria_publica():
    escuelas = Escuela.query.filter_by(activa=True).order_by(Escuela.orden, Escuela.id).all()
    viajes = AulaViaje.query.filter_by(activo=True).order_by(AulaViaje.orden, AulaViaje.id).all()
    medias = AulaMedia.query.order_by(AulaMedia.orden, AulaMedia.id).all()
    por_viaje = {}
    for m in medias:
        por_viaje.setdefault(m.viaje_id, []).append(m)
    por_escuela = {}
    for v in viajes:
        fotos, flyers, videos = [], [], []
        for m in por_viaje.get(v.id, []):
            if m.clase == "foto" and m.imagen_id:
                fotos.append(f"/media/{m.imagen_id}")
            elif m.clase == "flyer" and m.imagen_id:
                flyers.append(f"/media/{m.imagen_id}")
            elif m.clase == "video":
                if m.video_id:
                    videos.append({"red": "archivo", "src": f"/media/video/{m.video_id}", "titulo": m.titulo})
                else:
                    info = leer_link(m.url)
                    if info:
                        videos.append({**info, "titulo": m.titulo})
        por_escuela.setdefault(v.escuela_id, []).append({"id": v.id, "destino": v.destino, "anio": v.anio, "tipo": v.tipo, "texto": v.texto,
                                                         "fotos": fotos, "flyers": flyers, "videos": videos})
    return [{"id": e.id, "nombre": e.nombre, "localidad": e.localidad, "viajes": por_escuela.get(e.id, [])} for e in escuelas]


def sembrar_escuelas(Ajuste):
    """Una sola vez: carga las escuelas con las que ya viajó Aula Viajera."""
    marca = "semilla_escuelas"
    if db.session.get(Ajuste, marca):
        return
    if not Escuela.query.count():
        for i, (n, loc) in enumerate(ESCUELAS_INICIALES):
            db.session.add(Escuela(nombre=n, localidad=loc, orden=i))
    db.session.add(Ajuste(clave=marca, valor="ok"))
    db.session.commit()


# ---------------------------------------------------------------- panel

def montar(app, admin, Imagen, reducir_imagen):
    def txt(v, n):
        return " ".join((v or "").split())[:n]

    def borrar_media(m):
        if m.imagen_id:
            im = db.session.get(Imagen, m.imagen_id)
            if im:
                db.session.delete(im)
        if m.video_id:
            vd = db.session.get(AulaVideo, m.video_id)
            if vd:
                db.session.delete(vd)
        db.session.delete(m)

    def borrar_viaje(v):
        for m in AulaMedia.query.filter_by(viaje_id=v.id).all():
            borrar_media(m)
        db.session.delete(v)

    def mover(lista, obj, paso):
        lista = list(lista)
        i = lista.index(obj)
        j = i + paso
        if 0 <= j < len(lista):
            lista[i], lista[j] = lista[j], lista[i]
        for k, x in enumerate(lista):
            x.orden = k

    @app.get("/media/video/<int:vid>")
    def media_video(vid):
        v = db.session.get(AulaVideo, vid) or abort(404)
        r = Response(v.datos, mimetype=v.tipo or "video/mp4", headers={"Cache-Control": "public, max-age=31536000, immutable"})
        return r.make_conditional(request, accept_ranges=True, complete_length=len(v.datos))

    @app.route("/admin/aula", methods=["GET", "POST"])
    @admin
    def aula_inicio():
        if request.method == "POST":
            f = request.form
            acc = f.get("accion", "")
            if acc == "nueva":
                n = txt(f.get("nombre"), 120)
                if n:
                    db.session.add(Escuela(nombre=n, localidad=txt(f.get("localidad"), 80), orden=Escuela.query.count()))
                    flash("Escuela agregada.", "ok")
            else:
                e = db.session.get(Escuela, int(f.get("id") or 0)) or abort(404)
                todas = Escuela.query.order_by(Escuela.orden, Escuela.id).all()
                if acc == "guardar":
                    e.nombre = txt(f.get("nombre"), 120) or e.nombre
                    e.localidad = txt(f.get("localidad"), 80)
                    e.activa = bool(f.get("activa"))
                    flash("Guardado.", "ok")
                elif acc in ("subir", "bajar"):
                    mover(todas, e, -1 if acc == "subir" else 1)
                elif acc == "borrar":
                    for v in AulaViaje.query.filter_by(escuela_id=e.id).all():
                        borrar_viaje(v)
                    db.session.delete(e)
                    flash("Escuela borrada con sus viajes, fotos y videos.", "ok")
            db.session.commit()
            return redirect(url_for("aula_inicio"))
        escuelas = Escuela.query.order_by(Escuela.orden, Escuela.id).all()
        viajes = AulaViaje.query.order_by(AulaViaje.orden, AulaViaje.id).all()
        cuenta = {}
        for m in AulaMedia.query.all():
            c = cuenta.setdefault(m.viaje_id, {"foto": 0, "flyer": 0, "video": 0})
            c[m.clase] = c.get(m.clase, 0) + 1
        portadas = {}
        for m in AulaMedia.query.filter_by(clase="foto").order_by(AulaMedia.orden, AulaMedia.id).all():
            portadas.setdefault(m.viaje_id, f"/media/{m.imagen_id}")
        return render_template("admin/aula.html", escuelas=escuelas, viajes=viajes, cuenta=cuenta, portadas=portadas)

    @app.post("/admin/aula/escuela/<int:eid>/viaje")
    @admin
    def aula_viaje_nuevo(eid):
        e = db.session.get(Escuela, eid) or abort(404)
        destino = txt(request.form.get("destino"), 120)
        if not destino:
            flash("Poné a dónde fue el viaje.", "error")
            return redirect(url_for("aula_inicio") + f"#e{eid}")
        v = AulaViaje(escuela_id=e.id, destino=destino, anio=txt(request.form.get("anio"), 20), orden=AulaViaje.query.filter_by(escuela_id=e.id).count())
        db.session.add(v)
        db.session.commit()
        flash("Viaje creado. Ahora subile las fotos, flyers y videos.", "ok")
        return redirect(url_for("aula_viaje", vid=v.id))

    @app.route("/admin/aula/viaje/<int:vid>", methods=["GET", "POST"])
    @admin
    def aula_viaje(vid):
        v = db.session.get(AulaViaje, vid) or abort(404)
        e = db.session.get(Escuela, v.escuela_id)
        if request.method == "POST":
            f = request.form
            acc = f.get("accion", "guardar")
            if acc == "guardar":
                v.destino = txt(f.get("destino"), 120) or v.destino
                v.anio = txt(f.get("anio"), 20)
                v.tipo = txt(f.get("tipo"), 60)
                v.texto = " ".join((f.get("texto") or "").split())[:600]
                v.activo = bool(f.get("activo"))
                flash("Guardado.", "ok")
            elif acc == "link":
                info = leer_link(f.get("url"))
                if not info:
                    flash("Ese link no parece válido. Copialo entero, empezando con https://", "error")
                else:
                    db.session.add(AulaMedia(viaje_id=v.id, clase="video", url=info["url"][:400], titulo=txt(f.get("titulo"), 120),
                                             orden=AulaMedia.query.filter_by(viaje_id=v.id).count()))
                    flash("Video agregado.", "ok")
            elif acc == "video":
                arch = request.files.get("archivo")
                if not arch or not arch.filename:
                    flash("Elegí un video.", "error")
                else:
                    datos = arch.read()
                    if len(datos) > MAX_VIDEO_MB * 1024 * 1024:
                        flash(f"El video pesa más de {MAX_VIDEO_MB} MB. Subilo a YouTube como «no listado» y pegá el link.", "error")
                    elif not (arch.mimetype or "").startswith("video/"):
                        flash("Eso no parece un video. Probá con un MP4.", "error")
                    else:
                        vd = AulaVideo(nombre=arch.filename[:120], tipo=arch.mimetype[:40], datos=datos)
                        db.session.add(vd)
                        db.session.flush()
                        db.session.add(AulaMedia(viaje_id=v.id, clase="video", video_id=vd.id, titulo=txt(f.get("titulo"), 120),
                                                 orden=AulaMedia.query.filter_by(viaje_id=v.id).count()))
                        flash("Video subido.", "ok")
            elif acc.startswith(("borrar:", "portada:", "izq:", "der:")):
                m = db.session.get(AulaMedia, int(acc.split(":")[1]))
                if m and m.viaje_id == v.id:
                    hermanos = AulaMedia.query.filter_by(viaje_id=v.id, clase=m.clase).order_by(AulaMedia.orden, AulaMedia.id).all()
                    if acc.startswith("borrar:"):
                        borrar_media(m)
                    elif acc.startswith("portada:"):
                        hermanos.remove(m)
                        for k, x in enumerate([m] + hermanos):
                            x.orden = k
                        flash("Esa foto ahora es la portada del viaje.", "ok")
                    else:
                        mover(hermanos, m, -1 if acc.startswith("izq:") else 1)
            elif acc == "borrar_viaje":
                borrar_viaje(v)
                db.session.commit()
                flash("Viaje borrado.", "ok")
                return redirect(url_for("aula_inicio") + f"#e{e.id}")
            db.session.commit()
            return redirect(url_for("aula_viaje", vid=v.id) + (f"#{f.get('volver')}" if f.get("volver") in CLASES else ""))
        medias = AulaMedia.query.filter_by(viaje_id=v.id).order_by(AulaMedia.orden, AulaMedia.id).all()
        grupos = {k: [m for m in medias if m.clase == k] for k in CLASES}
        links = {m.id: leer_link(m.url) for m in grupos["video"] if m.url}
        return render_template("admin/aula_viaje.html", v=v, e=e, grupos=grupos, links=links, CLASES=CLASES, MAX_VIDEO_MB=MAX_VIDEO_MB)

    @app.post("/admin/aula/viaje/<int:vid>/imagen")
    @admin
    def aula_subir_imagen(vid):
        """Recibe UNA foto o flyer por vez (el navegador ya la achica y las manda de a una)."""
        v = db.session.get(AulaViaje, vid) or abort(404)
        clase = request.form.get("clase")
        if clase not in ("foto", "flyer"):
            abort(400)
        arch = request.files.get("archivo")
        if not arch or not arch.filename:
            return jsonify(ok=False, error="Sin archivo"), 400
        try:
            im = Imagen(nombre=arch.filename[:120], datos=reducir_imagen(arch.stream))
        except Exception:
            return jsonify(ok=False, error=f"No pude leer «{arch.filename}». Probá con JPG o PNG."), 400
        db.session.add(im)
        db.session.flush()
        db.session.add(AulaMedia(viaje_id=v.id, clase=clase, imagen_id=im.id, orden=AulaMedia.query.filter_by(viaje_id=v.id, clase=clase).count()))
        db.session.commit()
        return jsonify(ok=True)

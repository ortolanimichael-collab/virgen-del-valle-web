"""Editor de la portada: los destinos de la home y los programas de Aula Viajera.

Se guardan en la tabla vdv_bloque como JSON. Si no hay nada guardado, la web usa lo de contenido.json (los de fábrica).
"""
import json
import re
import unicodedata

from flask import abort, flash, redirect, render_template, request, url_for

from extensiones import db

SECCIONES = {
    "destinos": dict(titulo="Destinos de la portada", maximo=12, campos=("nombre", "lugar", "desde", "q", "img"),
                     nuevo=dict(nombre="Nuevo destino", lugar="", desde="Consultá", q="", img="img/sierras.jpg")),
    "programas": dict(titulo="Programas de Aula Viajera", maximo=8, campos=("nombre", "lugar", "detalle", "img"),
                      nuevo=dict(nombre="Nuevo programa", lugar="", detalle="", img="img/sierras.jpg")),
}
LARGOS = dict(nombre=60, lugar=80, desde=40, q=20, detalle=200, img=200)
FILTROS = {"": "No filtra (va a todos los viajes)", "argentina": "Viajes por Argentina", "brasil": "Viajes a Brasil", "europa": "Viajes a Europa"}


class Bloque(db.Model):
    __tablename__ = "vdv_bloque"
    clave = db.Column(db.String(40), primary_key=True)
    datos = db.Column(db.Text, default="[]")


def _slug(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40] or "item"


def guardado(clave):
    b = db.session.get(Bloque, clave)
    if b is None:
        return None
    try:
        v = json.loads(b.datos)
        return v if isinstance(v, list) else None
    except ValueError:
        return None


def aplicar(d, base_fabrica):
    """Pisa destinos/programas del contenido de fábrica con lo guardado en el panel (si hay)."""
    for clave in SECCIONES:
        g = guardado(clave)
        if g is not None:
            d[clave] = g
        else:
            d[clave] = base_fabrica.get(clave, [])
    return d


def montar(app, admin, fabrica, imagenes_de_la_web, reducir_imagen, Imagen):
    def filas(clave):
        g = guardado(clave)
        return g if g is not None else fabrica().get(clave, [])

    def img_valida(v):
        if re.fullmatch(r"/media/\d+", v or ""):
            return v
        if (v or "").startswith("img/") and v[4:] in imagenes_de_la_web():
            return v
        return SECCIONES_IMG_DEFECTO

    @app.route("/admin/portada")
    @admin
    def portada():
        return render_template("admin/portada.html", secciones=SECCIONES, filas={k: filas(k) for k in SECCIONES}, fotos=imagenes_de_la_web(),
                               personalizado={k: guardado(k) is not None for k in SECCIONES}, FILTROS=FILTROS)

    @app.post("/admin/portada/<clave>")
    @admin
    def portada_guardar(clave):
        cfg = SECCIONES.get(clave) or abort(404)
        f = request.form
        n = len(f.getlist("nombre"))
        archivos = request.files.getlist("foto")
        items = []
        for i in range(n):
            it = {}
            for c in cfg["campos"]:
                if c == "img":
                    continue
                it[c] = " ".join((f.getlist(c)[i] if i < len(f.getlist(c)) else "").split())[:LARGOS[c]]
            actual = f.getlist("img_actual")[i] if i < len(f.getlist("img_actual")) else ""
            elegida = f.getlist("foto_web")[i] if i < len(f.getlist("foto_web")) else ""
            arch = archivos[i] if i < len(archivos) else None
            if arch and arch.filename:
                try:
                    im = Imagen(nombre=arch.filename[:120], datos=reducir_imagen(arch.stream))
                except Exception:
                    flash(f"No pude leer la foto de «{it['nombre'] or 'una fila'}». Probá con un JPG o PNG.", "error")
                    return redirect(url_for("portada") + f"#{clave}")
                db.session.add(im)
                db.session.flush()
                it["img"] = f"/media/{im.id}"
            elif elegida and elegida != "__actual__" and elegida in imagenes_de_la_web():
                it["img"] = f"img/{elegida}"
            else:
                it["img"] = img_valida(actual)
            items.append(it)
        accion = f.get("accion", "guardar")
        if accion.startswith("borrar:"):
            i = int(accion.split(":")[1])
            if 0 <= i < len(items):
                items.pop(i)
        elif accion.startswith(("subir:", "bajar:")):
            i = int(accion.split(":")[1])
            j = i - 1 if accion.startswith("subir") else i + 1
            if 0 <= i < len(items) and 0 <= j < len(items):
                items[i], items[j] = items[j], items[i]
        elif accion == "agregar":
            if len(items) < cfg["maximo"]:
                items.append(dict(cfg["nuevo"]))
            else:
                flash(f"Podés tener hasta {cfg['maximo']}. Borrá alguno para sumar otro.", "error")
        vacios = [it for it in items if not it["nombre"]]
        items = [it for it in items if it["nombre"]][:cfg["maximo"]]
        if clave == "programas":
            usados = set()
            for it in items:
                base, k = _slug(it["nombre"]), 2
                s = base
                while s in usados:
                    s, k = f"{base}-{k}", k + 1
                usados.add(s)
                it["id"] = s
        b = db.session.get(Bloque, clave) or Bloque(clave=clave)
        b.datos = json.dumps(items, ensure_ascii=False)
        db.session.add(b)
        db.session.commit()
        if vacios:
            flash("Las filas sin nombre se descartaron.", "error")
        flash("Guardado. Ya se ve en la web." if accion == "guardar" else "Listo, mirá cómo quedó y tocá Guardar si cambiás algo más.", "ok")
        return redirect(url_for("portada") + f"#{clave}")

    @app.post("/admin/portada/<clave>/restaurar")
    @admin
    def portada_restaurar(clave):
        SECCIONES.get(clave) or abort(404)
        b = db.session.get(Bloque, clave)
        if b:
            db.session.delete(b)
            db.session.commit()
        flash("Volvió a los de fábrica.", "ok")
        return redirect(url_for("portada") + f"#{clave}")


SECCIONES_IMG_DEFECTO = "img/sierras.jpg"

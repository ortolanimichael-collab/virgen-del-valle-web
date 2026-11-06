"""Catálogo de viajes para Meta (anuncios dinámicos / carrusel de varios viajes).

El archivo /feed/meta.csv se arma solo con las salidas activas y no vencidas que cargó Miriam. Meta lo lee cada tanto
(configurado una vez en el Administrador de comercio) y los anuncios se mantienen al día sin que ella haga nada.
El id de cada fila es el mismo que manda el Pixel en content_ids, así Meta une «quién miró qué» con el catálogo.
"""
import csv
import io
import re

from flask import Response, render_template, request

COLUMNAS = ["id", "title", "description", "availability", "condition", "price", "link", "image_link", "brand"]
MARCAS = {"vdv": "Virgen del Valle", "trekia": "Trekia"}


def precio_meta(txt):
    """'$1.425.000' -> '1425000.00 ARS', 'USD 889' -> '889.00 USD'. None si no hay un número (ej: «Consultá»)."""
    t = (txt or "").strip()
    m = re.search(r"\d[\d.,]*", t)
    if not m:
        return None
    num = m.group(0).rstrip(".,")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", num):
        num = re.sub(r"[.,]", "", num)
    elif "." in num and "," in num:                      # 85.500,50 o 85,500.50: el último separador es el decimal
        dec = max(num.rfind("."), num.rfind(","))
        num = re.sub(r"[.,]", "", num[:dec]) + "." + num[dec + 1:]
    elif "," in num:
        num = num.replace(",", ".")
    try:
        v = float(num)
    except ValueError:
        return None
    if v <= 0:
        return None
    moneda = "USD" if re.search(r"usd|u\$s|us\$|dolar|dólar", t, re.I) else "ARS"
    return f"{v:.2f} {moneda}"


def base_https():
    b = request.url_root.rstrip("/")
    if b.startswith("http://") and "localhost" not in b and "127.0.0.1" not in b:
        b = "https://" + b[len("http://"):]
    return b


def armar(Salida, hoy):
    """(filas, excluidas): lo que va al catálogo y lo que quedó afuera con el motivo."""
    base = base_https()
    filas, afuera = [], []
    for s in Salida.query.filter(Salida.activa.is_(True), Salida.fecha >= hoy()).order_by(Salida.fecha, Salida.id).all():
        p = precio_meta(s.precio)
        if not p:
            afuera.append((s, "no tiene un precio con número (dice «%s»)" % (s.precio or "vacío")))
            continue
        img = s.img or "img/sierras.jpg"
        img = img if img.startswith("http") else base + ("" if img.startswith("/") else "/") + img
        desc = " · ".join(x for x in [s.detalle, ("Incluye: " + ", ".join(s.lista_incluye)) if s.lista_incluye else "", s.nota] if x) or s.destino
        filas.append(dict(id=s.slug, title=f"{s.destino} · {s.dia or ''}".strip(" ·")[:150], description=desc[:5000],
                          availability="out of stock" if s.estado == "agotado" else "in stock", condition="new", price=p,
                          link=f"{base}/viaje.html?id={s.slug}", image_link=img, brand=MARCAS.get(s.empresa, "Virgen del Valle")))
    return filas, afuera


def montar(app, admin, Salida, hoy):
    @app.get("/feed/meta.csv")
    def feed_meta():
        filas, _ = armar(Salida, hoy)
        b = io.StringIO()
        w = csv.DictWriter(b, fieldnames=COLUMNAS, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
        return Response(b.getvalue(), mimetype="text/csv", headers={"Content-Type": "text/csv; charset=utf-8", "X-Robots-Tag": "noindex",
                                                                  "Cache-Control": "public, max-age=300"})

    @app.route("/admin/catalogo")
    @admin
    def catalogo_pagina():
        filas, afuera = armar(Salida, hoy)
        return render_template("admin/catalogo.html", filas=filas, afuera=afuera, url=base_https() + "/feed/meta.csv")

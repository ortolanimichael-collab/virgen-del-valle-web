import io
import json
import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app as A


@pytest.fixture()
def cli(tmp_path):
    ap = A.crear_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}", "TESTING": True, "ADMIN_PASSWORD": "clave-test", "SECRET_KEY": "x"})
    return ap, ap.test_client()


def entrar(c):
    c.get("/admin/login")
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    return c.post("/admin/login", data={"usuario": "miriam", "password": "clave-test", "_csrf": "tok"})


def post(c, url, **datos):
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    datos["_csrf"] = "tok"
    return c.post(url, data=datos)


def test_la_web_publica_y_los_datos_salen_de_la_base(cli):
    ap, c = cli
    assert c.get("/").status_code == 200 and c.get("/trekia.html").status_code == 200 and c.get("/css/base.css").status_code == 200
    js = c.get("/js/data.js").get_data(as_text=True)
    assert js.startswith("window.VDV = {") and "V.vigentes" in js
    datos = json.loads(js.split("window.VDV = ", 1)[1].split(";\n", 1)[0])
    ids = [s["id"] for s in datos["salidas"]]
    assert datos["whatsapp"] == "5493571593669" and ids and all(s["fecha"] >= A.hoy().isoformat() for s in datos["salidas"])
    assert c.get("/admin-static/admin.css").status_code == 200 and c.get("/nada.html").status_code == 404 and c.get("/../app.py").status_code == 404


def test_el_panel_pide_clave_y_no_entra_con_una_mala(cli):
    ap, c = cli
    assert c.get("/admin/salidas").status_code == 302
    assert c.get("/admin/consultas").status_code == 302
    r = c.post("/admin/login", data={"usuario": "miriam", "password": "mala"})
    assert r.status_code == 400                                   # sin token de formulario
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    r = c.post("/admin/login", data={"usuario": "miriam", "password": "mala", "_csrf": "tok"})
    assert r.status_code == 200 and "incorrectos" in r.get_data(as_text=True)
    assert entrar(c).status_code == 302 and c.get("/admin/salidas").status_code == 200


def test_sin_contrasena_configurada_nadie_entra(tmp_path):
    ap = A.crear_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'s.db'}", "ADMIN_PASSWORD": ""})
    c = ap.test_client()
    c.get("/admin/login")
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    r = c.post("/admin/login", data={"usuario": "miriam", "password": "", "_csrf": "tok"})
    assert r.status_code == 200 and not c.get("/admin/salidas").status_code == 200


def test_cargar_editar_estado_ocultar_copiar_y_borrar_una_salida(cli):
    ap, c = cli
    entrar(c)
    futuro = (A.hoy() + timedelta(days=20)).isoformat()
    r = post(c, "/admin/salidas/nueva", empresa="trekia", destino="Cerro Champaquí", fecha=futuro, lugar="Traslasierra", detalle="Trekking de 2 días", incluye="Guía\nSeguro\n",
             precio="$90.000", nota="por persona", region="argentina", tipos=["naturaleza"], estado="disponible", dificultad="Alta", km="14 km", activa="1", foto_web="trekker.jpg")
    assert r.status_code == 302
    with ap.app_context():
        s = A.Salida.query.filter_by(destino="Cerro Champaquí").one()
        sid, slug = s.id, s.slug
        assert s.lista_incluye == ["Guía", "Seguro"] and s.img == "img/trekker.jpg" and slug.startswith("cerro-champaqui-")
    def pub():
        j = c.get("/js/data.js").get_data(as_text=True)
        return json.loads(j.split("window.VDV = ", 1)[1].split(";\n", 1)[0])["salidas"]
    mia = [x for x in pub() if x["id"] == slug][0]
    assert mia["empresa"] == "trekia" and mia["dificultad"] == "Alta" and mia["incluye"] == ["Guía", "Seguro"] and mia["dia"].endswith(A.MESES[(A.hoy() + timedelta(days=20)).month - 1])
    post(c, f"/admin/salidas/{sid}/estado", estado="agotado")
    assert [x for x in pub() if x["id"] == slug][0]["estado"] == "agotado"
    post(c, f"/admin/salidas/{sid}/visible")
    assert slug not in [x["id"] for x in pub()]                          # oculta: no se ve
    post(c, f"/admin/salidas/{sid}/visible")
    r = post(c, f"/admin/salidas/{sid}/duplicar")
    assert r.status_code == 302
    with ap.app_context():
        assert A.Salida.query.filter_by(destino="Cerro Champaquí").count() == 2
    r = post(c, f"/admin/salidas/{sid}", empresa="trekia", destino="Cerro Champaquí", fecha="no-es-fecha")
    assert "Elegí la fecha" in c.get("/admin/salidas/%d" % sid).get_data(as_text=True) or r.status_code == 200
    post(c, f"/admin/salidas/{sid}/borrar")
    with ap.app_context():
        assert A.db.session.get(A.Salida, sid) is None


def test_las_vencidas_se_ocultan_solas_pero_quedan_en_el_panel(cli):
    ap, c = cli
    entrar(c)
    ayer = (A.hoy() - timedelta(days=1)).isoformat()
    post(c, "/admin/salidas/nueva", empresa="vdv", destino="Salida Vieja", fecha=ayer, estado="disponible", activa="1")
    j = c.get("/js/data.js").get_data(as_text=True)
    assert "Salida Vieja" not in j
    h = c.get("/admin/salidas").get_data(as_text=True)
    assert "Salida Vieja" in h and "Vencida" in h
    with ap.app_context():
        slug = A.Salida.query.filter_by(destino="Salida Vieja").one().slug
    assert c.get(f"/viaje.html?id={slug}").status_code == 200 and "og:title" not in c.get(f"/viaje.html?id={slug}").get_data(as_text=True)


def test_la_pagina_del_viaje_sale_con_foto_y_titulo_para_compartir(cli):
    ap, c = cli
    with ap.app_context():
        s = A.Salida.query.filter(A.Salida.fecha >= A.hoy()).order_by(A.Salida.fecha).first()
        slug, destino = s.slug, s.destino
    h = c.get(f"/viaje.html?id={slug}").get_data(as_text=True)
    assert 'property="og:title"' in h and destino in h and 'property="og:image" content="http://localhost/img/' in h
    assert 'property="og:title"' not in c.get("/viaje.html?id=inexistente").get_data(as_text=True)


def test_foto_propia_se_reduce_y_se_sirve(cli):
    from PIL import Image
    ap, c = cli
    entrar(c)
    b = io.BytesIO()
    Image.new("RGB", (3000, 2000), (200, 30, 90)).save(b, "PNG")
    b.seek(0)
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    r = c.post("/admin/salidas/nueva", data={"_csrf": "tok", "empresa": "vdv", "destino": "Con Foto", "fecha": (A.hoy() + timedelta(days=9)).isoformat(),
                                             "estado": "disponible", "activa": "1", "foto": (b, "mi.png")}, content_type="multipart/form-data")
    assert r.status_code == 302
    with ap.app_context():
        img = A.Salida.query.filter_by(destino="Con Foto").one().img
    assert img.startswith("/media/")
    m = c.get(img)
    assert m.status_code == 200 and m.mimetype == "image/jpeg" and Image.open(io.BytesIO(m.data)).width == 1600
    with ap.app_context():
        # un archivo que no es imagen no rompe nada
        pass
    r = c.post("/admin/salidas/nueva", data={"_csrf": "tok", "empresa": "vdv", "destino": "Mala Foto", "fecha": (A.hoy() + timedelta(days=9)).isoformat(),
                                             "foto": (io.BytesIO(b"no soy una imagen"), "x.png")}, content_type="multipart/form-data")
    assert r.status_code == 200 and "No pude leer esa foto" in r.get_data(as_text=True)


def test_las_consultas_llegan_al_panel_y_se_gestionan(cli):
    ap, c = cli
    r = c.post("/api/consulta", json={"origen": "promos", "datos": {"nombre": "Laura", "telefono": "3571 123456"}, "texto": "Hola!", "pagina": "/"})
    assert r.status_code == 200
    assert c.post("/api/consulta", json={"origen": "x", "datos": {}}).status_code == 400
    assert c.post("/api/consulta", data="basura").status_code == 400
    entrar(c)
    assert "Tenés <b>1</b> consulta nueva" in c.get("/admin/salidas").get_data(as_text=True)
    h = c.get("/admin/consultas").get_data(as_text=True)
    assert "Laura" in h and "3571 123456" in h and "wa.me/3571123456" in h
    with ap.app_context():
        cid = A.Consulta.query.first().id
    post(c, "/admin/consultas", id=str(cid), estado="contactada", recordar=(A.hoy() - timedelta(days=1)).isoformat(), nota="Llamarla")
    h = c.get("/admin/consultas?filtro=recordar").get_data(as_text=True)
    assert "Laura" in h and "Había que escribirle" in h
    assert "Laura" not in c.get("/admin/consultas?filtro=nueva").get_data(as_text=True)


def test_las_consultas_tienen_tope_por_persona(cli):
    ap, c = cli
    cod = [c.post("/api/consulta", json={"datos": {"nombre": "Spam"}}).status_code for _ in range(12)]
    assert cod[:10] == [200] * 10 and cod[10] == 429


def test_cambiar_el_whatsapp_actualiza_toda_la_web(cli):
    ap, c = cli
    entrar(c)
    post(c, "/admin/contacto", whatsapp="+54 9 3571 11-2233", telefono="03571 11-2233", direccion="Otra calle 1", ciudad="Río Tercero", instagram="vdv", legajo="EVT 1")
    d = json.loads(c.get("/js/data.js").get_data(as_text=True).split("window.VDV = ", 1)[1].split(";\n", 1)[0])
    assert d["whatsapp"] == "5493571112233" and d["direccion"] == "Otra calle 1"

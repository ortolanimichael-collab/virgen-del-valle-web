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


def test_pixel_politica_y_aviso_de_cookies(cli):
    ap, c = cli
    for pagina in ("/", "/trekia.html", "/aula-viajera.html", "/viaje.html"):
        h = c.get(pagina).get_data(as_text=True)
        assert 'src="js/privacy.js"' in h and "privacidad.html" in h, pagina
    assert c.get("/privacidad.html").status_code == 200 and "Ley 25.326" in c.get("/privacidad.html").get_data(as_text=True)
    assert c.get("/js/privacy.js").status_code == 200
    datos = lambda: json.loads(c.get("/js/data.js").get_data(as_text=True).split("window.VDV = ", 1)[1].split(";\n", 1)[0])
    assert datos()["pixel_id"] == ""                                        # sin pixel configurado no se instala nada
    entrar(c)
    post(c, "/admin/contacto", whatsapp="5493571593669", pixel_id="  1234-5678 90abc", razon_social="Virgen del Valle S.R.L.", cuit="30-11111111-1", email="hola@vdv.com.ar")
    d = datos()
    assert d["pixel_id"] == "1234567890" and d["razon_social"] == "Virgen del Valle S.R.L." and d["email"] == "hola@vdv.com.ar"


# ====================================================================== Etapa 4
def _salida_con_cupos(ap, c, cupos=5, nombre="Salida Cupos"):
    post(c, "/admin/salidas/nueva", empresa="vdv", destino=nombre, fecha=(A.hoy() + timedelta(days=15)).isoformat(), estado="disponible", activa="1", cupos=str(cupos))
    with ap.app_context():
        return A.Salida.query.filter_by(destino=nombre).one().id


def test_pasajeros_cupos_senia_y_estado_automatico(cli):
    ap, c = cli
    entrar(c)
    sid = _salida_con_cupos(ap, c, cupos=5)
    assert "Pasajeros (0/5)" in c.get("/admin/salidas").get_data(as_text=True)
    for i in range(1, 3):
        post(c, f"/admin/salidas/{sid}/pasajeros", nombre=f"Pasajero {i}", telefono=f"3571 10000{i}", total="145.000", pagado="50000", estado="reservado")
    with ap.app_context():
        assert A.db.session.get(A.Salida, sid).estado == "ultimos"                 # quedan 3 lugares: pasa sola a «últimos cupos»
    h = c.get(f"/admin/salidas/{sid}/pasajeros").get_data(as_text=True)
    assert "Pasajero 1" in h and "$ 290.000" in h and "$ 100.000" in h and "debe $ 95.000" in h and "Quedan 3 libres" in h
    pid = None
    with ap.app_context():
        pid = A.modelos4.Pasajero.query.filter_by(nombre="Pasajero 1").one().id
    post(c, f"/admin/pasajeros/{pid}/pago", monto="95.000")
    with ap.app_context():
        assert A.modelos4.Pasajero.query.get(pid).pagado == 145000
    for i in range(3, 6):
        post(c, f"/admin/salidas/{sid}/pasajeros", nombre=f"Pasajero {i}", total="1000", pagado="0")
    with ap.app_context():
        assert A.db.session.get(A.Salida, sid).estado == "agotado"
    d = json.loads(c.get("/js/data.js").get_data(as_text=True).split("window.VDV = ", 1)[1].split(";\n", 1)[0])
    assert [x for x in d["salidas"] if x["destino"] == "Salida Cupos"][0]["estado"] == "agotado"        # la web se entera sola
    # cancelar libera el lugar y no suma a los cobros
    post(c, f"/admin/pasajeros/{pid}", nombre="Pasajero 1", total="145000", pagado="145000", estado="cancelado")
    assert "Quedan 1 libres" in c.get(f"/admin/salidas/{sid}/pasajeros").get_data(as_text=True)
    r = c.get(f"/admin/salidas/{sid}/pasajeros.csv")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"] and r.get_data(as_text=True).startswith("﻿Nombre;DNI")
    assert "Cancelado" in r.get_data(as_text=True)
    assert post(c, f"/admin/pasajeros/99999/borrar").status_code == 404
    # no se borra una salida con pasajeros
    post(c, f"/admin/salidas/{sid}/borrar")
    with ap.app_context():
        assert A.db.session.get(A.Salida, sid) is not None


def test_montos_invalidos_no_se_guardan(cli):
    ap, c = cli
    entrar(c)
    sid = _salida_con_cupos(ap, c)
    post(c, f"/admin/salidas/{sid}/pasajeros", nombre="Mal Monto", total="abc", pagado="10")
    post(c, f"/admin/salidas/{sid}/pasajeros", nombre="Negativo", total="-5", pagado="0")
    with ap.app_context():
        assert A.modelos4.Pasajero.query.count() == 0


def test_clientes_se_reconocen_por_telefono_y_tienen_etiquetas(cli):
    ap, c = cli
    entrar(c)
    s1, s2 = _salida_con_cupos(ap, c, nombre="Viaje Uno"), _salida_con_cupos(ap, c, nombre="Viaje Dos")
    post(c, f"/admin/salidas/{s1}/pasajeros", nombre="Laura Gómez", telefono="+54 9 3571 12-3456", total="1000", pagado="0")
    post(c, f"/admin/salidas/{s2}/pasajeros", nombre="Laura G.", telefono="3571123456", total="2000", pagado="0")
    with ap.app_context():
        assert A.modelos4.Cliente.query.count() == 1                                 # la misma persona, aunque escriba distinto el teléfono
        cid = A.modelos4.Cliente.query.one().id
    post(c, f"/admin/clientes/{cid}", nombre="Laura Gómez", telefono="3571123456", etiquetas="VIP, Escuelas, vip; ", localidad="Río Tercero")
    h = c.get("/admin/clientes?etiqueta=vip").get_data(as_text=True)
    assert "Laura Gómez" in h and "2 viajes" in h and "escuelas" in h
    assert "Laura" not in c.get("/admin/clientes?etiqueta=brasil").get_data(as_text=True)
    assert "Laura" in c.get("/admin/clientes?q=rio+ter").get_data(as_text=True) or "Laura" in c.get("/admin/clientes?q=3571").get_data(as_text=True)
    h = c.get(f"/admin/clientes/{cid}").get_data(as_text=True)
    assert "Viaje Uno" in h and "Viaje Dos" in h
    assert c.get("/admin/clientes.csv").get_data(as_text=True).startswith("﻿Nombre;")
    post(c, f"/admin/clientes/{cid}/borrar")
    with ap.app_context():
        assert A.modelos4.Cliente.query.count() == 0 and A.modelos4.Pasajero.query.filter(A.modelos4.Pasajero.cliente_id.isnot(None)).count() == 0
        assert A.modelos4.Pasajero.query.count() == 2                                # los viajes anotados se conservan


def test_consulta_pasa_a_clientes(cli):
    ap, c = cli
    c.post("/api/consulta", json={"origen": "promos", "datos": {"nombre": "Marta", "telefono": "3571 777888"}, "texto": "Hola"})
    entrar(c)
    with ap.app_context():
        kid = A.Consulta.query.one().id
    r = post(c, f"/admin/consultas/{kid}/a-cliente")
    assert r.status_code == 302
    post(c, f"/admin/consultas/{kid}/a-cliente")                                     # dos veces no duplica
    with ap.app_context():
        assert A.modelos4.Cliente.query.count() == 1 and "consulta" in A.modelos4.Cliente.query.one().lista_etiquetas


def test_sorteo_numeros_ganador_y_pagina_publica(cli):
    ap, c = cli
    entrar(c)
    assert post(c, "/admin/sorteos", nombre="Rifa", cantidad="1").status_code == 200           # muy pocos números
    r = post(c, "/admin/sorteos", nombre="Rifa Beneficio", premio="Fin de semana en San Luis", cantidad="20", precio="$2.000")
    assert r.status_code == 302
    with ap.app_context():
        s = A.modelos4.Sorteo.query.one()
        sid, token = s.id, s.token
    post(c, f"/admin/sorteos/{sid}/sortear")                                         # sin pagados no hay sorteo
    with ap.app_context():
        assert A.modelos4.Sorteo.query.get(sid).ganador_numero is None
    post(c, f"/admin/sorteos/{sid}/numeros", numeros="3, 5-7, 99", nombre="Laura", telefono="3571 111", estado="pagado")
    post(c, f"/admin/sorteos/{sid}/numeros", numeros="10", nombre="Pedro", estado="reservado")
    with ap.app_context():
        nums = {n.numero: n.estado for n in A.modelos4.SorteoNumero.query.all()}
        assert nums == {3: "pagado", 5: "pagado", 6: "pagado", 7: "pagado", 10: "reservado"}          # el 99 queda afuera
    pub = app_pub = c.get(f"/sorteo/{token}").get_data(as_text=True)
    assert "Rifa Beneficio" in pub and "Laura" not in pub and "3571 111" not in pub and "<b>15</b> números libres" in pub
    assert c.get("/sorteo/token-falso").status_code == 404
    post(c, f"/admin/sorteos/{sid}/sortear")
    with ap.app_context():
        g = A.modelos4.Sorteo.query.get(sid).ganador_numero
    assert g in (3, 5, 6, 7)                                                         # solo entre los pagados, nunca el reservado
    post(c, f"/admin/sorteos/{sid}/sortear")
    with ap.app_context():
        assert A.modelos4.Sorteo.query.get(sid).ganador_numero == g                  # no se sortea dos veces
    assert "Ganó el número" in c.get(f"/admin/sorteos/{sid}").get_data(as_text=True) or "Ganó" in c.get(f"/admin/sorteos/{sid}").get_data(as_text=True)
    post(c, f"/admin/sorteos/{sid}/anular")
    post(c, f"/admin/sorteos/{sid}/numeros", numeros="5-6", estado="libre")
    with ap.app_context():
        assert A.modelos4.SorteoNumero.query.count() == 3
    post(c, f"/admin/sorteos/{sid}/borrar")
    with ap.app_context():
        assert A.modelos4.Sorteo.query.count() == 0 and A.modelos4.SorteoNumero.query.count() == 0


def test_flyers_y_reporte(cli):
    ap, c = cli
    assert c.get("/admin/flyers").status_code == 302 and c.get("/admin/reporte").status_code == 302
    entrar(c)
    h = c.get("/admin/flyers").get_data(as_text=True)
    assert "Generador de flyers" in h and "Papa León XIV" in h or "Charter a Buzios" in h
    sid = _salida_con_cupos(ap, c, nombre="Salida Reporte")
    post(c, f"/admin/salidas/{sid}/pasajeros", nombre="Ana", total="100000", pagado="30000")
    c.post("/api/consulta", json={"origen": "promos", "datos": {"nombre": "X", "telefono": "1"}})
    h = c.get("/admin/reporte").get_data(as_text=True)
    assert "Reporte de " in h and "$ 100.000" in h and "$ 30.000" in h and "$ 70.000" in h and "Resumen de" in h
    assert c.get("/admin/reporte?mes=2024-01").status_code == 200 and c.get("/admin/reporte?mes=basura").status_code == 200


def test_migracion_agrega_cupos_a_una_base_vieja(tmp_path):
    import sqlite3
    ruta = tmp_path / "vieja.db"
    cx = sqlite3.connect(ruta)
    cx.execute("CREATE TABLE vdv_salida (id INTEGER PRIMARY KEY, slug VARCHAR(80), empresa VARCHAR(12), destino VARCHAR(120), lugar VARCHAR(120), fecha DATE, dia VARCHAR(40), detalle VARCHAR(300), incluye TEXT, precio VARCHAR(40), nota VARCHAR(80), img VARCHAR(200), region VARCHAR(12), tipos VARCHAR(120), estado VARCHAR(12), dificultad VARCHAR(10), km VARCHAR(20), destacado BOOLEAN, activa BOOLEAN, creada DATETIME, actualizada DATETIME)")
    cx.execute("INSERT INTO vdv_salida (id, slug, empresa, destino, fecha, estado, activa) VALUES (1, 'x-202701', 'vdv', 'Vieja', '2027-01-10', 'disponible', 1)")
    cx.commit(); cx.close()
    ap = A.crear_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{ruta}", "ADMIN_PASSWORD": "x"})
    with ap.app_context():
        assert A.Salida.query.filter_by(destino="Vieja").one().cupos is None


def test_editor_de_portada(cli):
    ap, c = cli
    assert c.get("/admin/portada").status_code == 302
    entrar(c)
    pag = c.get("/admin/portada").get_data(as_text=True)
    assert "Buzios" in pag and "Viaje de egresados" in pag

    def enviar(form, clave="destinos"):
        f = dict(form)
        f["foto"] = [(io.BytesIO(x[0].getvalue()), x[1]) for x in form["foto"]]
        return c.post(f"/admin/portada/{clave}", data=f, content_type="multipart/form-data")

    def datos(): return json.loads(c.get("/js/data.js").get_data(as_text=True).split("window.VDV = ", 1)[1].split(";\n", 1)[0])
    antes = datos()
    assert antes["destinos"][0]["nombre"] == "Buzios"
    n = len(antes["destinos"])
    # editar nombre, cambiar foto y subir uno nuevo
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    form = {"_csrf": "tok", "accion": "guardar", "nombre": ["Cabo Frío", "Patagonia"], "lugar": ["Brasil", "Argentina"], "desde": ["USD 1", "$2"],
            "q": ["brasil", "argentina"], "img_actual": ["img/buzios.jpg", "img/perito-moreno.jpg"], "foto_web": ["__actual__", "glaciar.jpg"],
            "foto": [(io.BytesIO(b""), ""), (io.BytesIO(b""), "")]}
    r = enviar(form)
    assert r.status_code == 302
    d = datos()["destinos"]
    assert [x["nombre"] for x in d] == ["Cabo Frío", "Patagonia"] and d[0]["img"] == "img/buzios.jpg" and d[1]["img"] == "img/glaciar.jpg"
    # subir / agregar / borrar
    form["accion"] = "subir:1"
    enviar(form)
    assert [x["nombre"] for x in datos()["destinos"]] == ["Patagonia", "Cabo Frío"]
    form["accion"] = "agregar"
    enviar(form)
    assert len(datos()["destinos"]) == 3
    form["accion"] = "borrar:2"
    enviar(form)
    assert len(datos()["destinos"]) == 2
    # foto subida por la usuaria + foto inválida no entra
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (40, 30), "red").save(b, "PNG"); b.seek(0)
    form["accion"] = "guardar"; form["img_actual"] = ["../../etc/passwd", "img/glaciar.jpg"]; form["foto"] = [(b, "x.png"), (io.BytesIO(b""), "")]
    enviar(form)
    d = datos()["destinos"]
    assert d[0]["img"].startswith("/media/") and c.get(d[0]["img"]).status_code == 200
    form["img_actual"] = ["../../etc/passwd", "img/glaciar.jpg"]; form["foto"] = [(io.BytesIO(b""), ""), (io.BytesIO(b""), "")]
    enviar(form)
    assert datos()["destinos"][0]["img"] == "img/sierras.jpg"
    # programas
    r = c.post("/admin/portada/programas", data={"_csrf": "tok", "accion": "guardar", "nombre": ["Egresados", ""], "lugar": ["Bariloche", ""], "detalle": ["x", ""],
                                                  "img_actual": ["img/floripa.jpg", ""], "foto_web": ["__actual__", "__actual__"], "foto": [(io.BytesIO(b""), ""), (io.BytesIO(b""), "")]},
               content_type="multipart/form-data")
    p = datos()["programas"]
    assert len(p) == 1 and p[0]["id"] == "egresados"
    assert c.get("/aula-viajera.html").status_code == 200
    # restaurar
    post(c, "/admin/portada/destinos/restaurar")
    assert len(datos()["destinos"]) == n and datos()["destinos"][0]["nombre"] == "Buzios"
    assert c.post("/admin/portada/otra", data={"_csrf": "tok"}).status_code == 404


def test_boton_de_resenas(cli):
    ap, c = cli
    entrar(c)
    def datos(): return json.loads(c.get("/js/data.js").get_data(as_text=True).split("window.VDV = ", 1)[1].split(";\n", 1)[0])
    assert not datos().get("resenas_url")
    base = {k: "" for k in A.CONTACTO}
    post(c, "/admin/contacto", **{**base, "whatsapp": "5493571593669", "resenas_url": "javascript:alert(1)"})
    assert not datos().get("resenas_url")
    post(c, "/admin/contacto", **{**base, "whatsapp": "5493571593669", "resenas_url": "https://g.page/r/ABC123/review"})
    assert datos()["resenas_url"] == "https://g.page/r/ABC123/review"
    assert "resenas_url" in c.get("/admin/contacto").get_data(as_text=True)


def test_respaldo_y_restauracion(cli, tmp_path):
    import respaldo
    ap, c = cli
    assert c.get("/admin/respaldo").status_code == 302
    entrar(c)
    assert c.get("/admin/respaldo").status_code == 200
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (20, 20), "blue").save(b, "PNG"); b.seek(0)
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    c.post("/admin/portada/programas", data={"_csrf": "tok", "accion": "guardar", "nombre": ["Mi programa"], "lugar": ["x"], "detalle": ["y"], "img_actual": [""],
                                             "foto_web": ["__actual__"], "foto": (b, "f.png")}, content_type="multipart/form-data")
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    r = c.post("/admin/respaldo/descargar", data={"_csrf": "tok"})
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    copia = json.loads(r.get_data(as_text=True))
    assert copia["tablas"]["vdv_salida"] and copia["tablas"]["vdv_imagen"] and "vdv_cliente" in copia["tablas"]
    with ap.app_context():
        n_sal = A.Salida.query.count()
        A.db.session.query(A.Salida).delete(); A.db.session.query(A.Imagen).delete(); A.db.session.commit()
        assert A.Salida.query.count() == 0
        res = respaldo.restaurar(copia)
        assert res["vdv_salida"] == n_sal and A.Salida.query.count() == n_sal and A.Imagen.query.count() == 1
        assert A.Salida.query.first().fecha is not None
        with pytest.raises(ValueError):
            respaldo.restaurar({"version": 9})
        with pytest.raises(ValueError):
            respaldo.restaurar({"version": 1, "tablas": {"otra_tabla": []}})
    assert c.get("/media/1").status_code == 200

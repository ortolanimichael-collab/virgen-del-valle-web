"""Etapa 4 del panel: clientes con etiquetas, pasajeros por salida (seña, cupos, exportar), sorteos con números,
generador de flyers y reporte mensual."""
import csv
import io
import json
import re
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Response, abort, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, or_

from extensiones import db
from modelos4 import Cliente, Pasajero, Sorteo, SorteoNumero, tel_norm

ESTADOS_PASAJERO = {"reservado": "Reservado", "confirmado": "Confirmado", "cancelado": "Cancelado"}
UMBRAL_ULTIMOS = 3          # con tantos lugares libres o menos, la salida pasa sola a «Últimos cupos»
MAX_SORTEO = 1000


def _dinero(txt):
    """«1.500,50» / «1500.5» / «$ 1.500» → Decimal. Vacío = 0. Inválido o negativo = None."""
    crudo = str(txt or "").strip()
    if crudo and not re.search(r"\d", crudo):
        return None
    t = re.sub(r"[^\d,.\-]", "", crudo)
    if not t:
        return Decimal(0)
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    return v.quantize(Decimal("0.01")) if 0 <= v <= Decimal("99999999") else None


def _pesos(v):
    v = Decimal(v or 0).quantize(Decimal("1"))
    return "$ " + f"{int(v):,}".replace(",", ".")


def _txt(v, n):
    return " ".join((v or "").split())[:n]


def _etiquetas(txt):
    vistas, res = set(), []
    for e in re.split(r"[,;\n]", txt or ""):
        e = _txt(e, 30).lower()
        if e and e not in vistas:
            vistas.add(e)
            res.append(e)
    return ",".join(res[:12])[:200]


def montar(app, admin, C):
    Salida, Consulta, hoy, ahora, ajustes = C["Salida"], C["Consulta"], C["hoy"], C["ahora"], C["ajustes"]
    app.jinja_env.globals.update(ESTADOS_PASAJERO=ESTADOS_PASAJERO, pesos=_pesos)

    # ================================================================== clientes
    def buscar_o_crear_cliente(nombre, telefono="", dni="", etiqueta=None):
        """La misma persona (por teléfono o DNI) no queda dos veces. Devuelve el cliente."""
        nombre, telefono, dni = _txt(nombre, 120), _txt(telefono, 40), _txt(dni, 20)
        tn = tel_norm(telefono)
        cli = None
        if tn and len(tn) >= 7:
            cli = Cliente.query.filter_by(tel_norm=tn).first()
        if cli is None and dni:
            cli = Cliente.query.filter_by(dni=dni).first()
        if cli is None:
            cli = Cliente(nombre=nombre, telefono=telefono, tel_norm=tn, dni=dni, etiquetas=etiqueta or "")
            db.session.add(cli)
            db.session.flush()
        else:
            if not cli.telefono and telefono:
                cli.telefono, cli.tel_norm = telefono, tn
            if not cli.dni and dni:
                cli.dni = dni
            if etiqueta and etiqueta not in cli.lista_etiquetas:
                cli.etiquetas = _etiquetas((cli.etiquetas or "") + "," + etiqueta)
        return cli

    @app.get("/admin/clientes", endpoint="clientes")
    @admin
    def clientes():
        q, et = _txt(request.args.get("q"), 60), _txt(request.args.get("etiqueta"), 30).lower()
        qs = Cliente.query
        if q:
            like = f"%{q}%"
            qs = qs.filter(or_(Cliente.nombre.ilike(like), Cliente.telefono.ilike(like), Cliente.dni.ilike(like), Cliente.localidad.ilike(like)))
        if et:
            qs = qs.filter(or_(Cliente.etiquetas == et, Cliente.etiquetas.like(f"{et},%"), Cliente.etiquetas.like(f"%,{et}"), Cliente.etiquetas.like(f"%,{et},%")))
        lista = qs.order_by(Cliente.nombre).limit(500).all()
        todas = sorted({e for (x,) in db.session.query(Cliente.etiquetas).all() for e in (x or "").split(",") if e})
        viajes = dict(db.session.query(Pasajero.cliente_id, func.count(Pasajero.id)).filter(Pasajero.estado != "cancelado").group_by(Pasajero.cliente_id).all())
        return render_template("admin/clientes.html", lista=lista, q=q, et=et, todas=todas, viajes=viajes, total=Cliente.query.count())

    @app.get("/admin/clientes.csv", endpoint="clientes_csv")
    @admin
    def clientes_csv():
        filas = [["Nombre", "Teléfono", "DNI", "Mail", "Localidad", "Etiquetas", "Notas"]] + \
                [[c.nombre, c.telefono, c.dni, c.email, c.localidad, c.etiquetas.replace(",", ", "), c.notas] for c in Cliente.query.order_by(Cliente.nombre).all()]
        return _csv(filas, "clientes.csv")

    def _leer_cliente(c, f):
        nombre = _txt(f.get("nombre"), 120)
        if not nombre:
            return "Poné el nombre."
        c.nombre, c.telefono, c.dni = nombre, _txt(f.get("telefono"), 40), _txt(f.get("dni"), 20)
        c.tel_norm = tel_norm(c.telefono)
        c.email, c.localidad = _txt(f.get("email"), 120), _txt(f.get("localidad"), 80)
        c.etiquetas, c.notas = _etiquetas(f.get("etiquetas")), _txt(f.get("notas"), 500)
        return None

    @app.route("/admin/clientes/nuevo", methods=["GET", "POST"], endpoint="cliente_nuevo")
    @admin
    def cliente_nuevo():
        c = Cliente(nombre="")
        if request.method == "POST":
            error = _leer_cliente(c, request.form)
            if error:
                flash(error, "error")
            else:
                db.session.add(c)
                db.session.commit()
                flash("Cliente guardado.", "ok")
                return redirect(url_for("cliente_editar", cid=c.id))
        return render_template("admin/cliente_form.html", c=c, nuevo=True, viajes=[], etiquetas_usadas=_todas_etiquetas())

    def _todas_etiquetas():
        return sorted({e for (x,) in db.session.query(Cliente.etiquetas).all() for e in (x or "").split(",") if e})

    @app.route("/admin/clientes/<int:cid>", methods=["GET", "POST"], endpoint="cliente_editar")
    @admin
    def cliente_editar(cid):
        c = db.session.get(Cliente, cid) or abort(404)
        if request.method == "POST":
            error = _leer_cliente(c, request.form)
            if error:
                db.session.rollback()
                flash(error, "error")
                c = db.session.get(Cliente, cid)
            else:
                db.session.commit()
                flash("Cambios guardados.", "ok")
                return redirect(url_for("cliente_editar", cid=cid))
        viajes = Pasajero.query.filter_by(cliente_id=cid).join(Salida).order_by(Salida.fecha.desc()).all()
        consultas = [k for k in Consulta.query.order_by(Consulta.creada.desc()).limit(300).all()
                     if c.tel_norm and tel_norm(k.dict_datos.get("telefono") or k.dict_datos.get("whatsapp") or "") == c.tel_norm]
        return render_template("admin/cliente_form.html", c=c, nuevo=False, viajes=viajes, consultas=consultas, etiquetas_usadas=_todas_etiquetas())

    @app.post("/admin/clientes/<int:cid>/borrar", endpoint="cliente_borrar")
    @admin
    def cliente_borrar(cid):
        c = db.session.get(Cliente, cid) or abort(404)
        Pasajero.query.filter_by(cliente_id=cid).update({"cliente_id": None})      # los pasajeros conservan nombre y datos
        nombre = c.nombre
        db.session.delete(c)
        db.session.commit()
        flash(f"Borré a «{nombre}» de la base de clientes.", "ok")
        return redirect(url_for("clientes"))

    @app.post("/admin/consultas/<int:kid>/a-cliente", endpoint="consulta_a_cliente")
    @admin
    def consulta_a_cliente(kid):
        k = db.session.get(Consulta, kid) or abort(404)
        d = k.dict_datos
        cli = buscar_o_crear_cliente(d.get("nombre") or k.nombre or "Sin nombre", d.get("telefono") or d.get("whatsapp") or "", etiqueta="consulta")
        db.session.commit()
        flash("Listo: quedó en tu base de clientes.", "ok")
        return redirect(url_for("cliente_editar", cid=cli.id))

    # ================================================================== pasajeros
    def ocupados(sid):
        return Pasajero.query.filter(Pasajero.salida_id == sid, Pasajero.estado != "cancelado").count()

    def ajustar_estado(s):
        """Con cupos cargados: sin lugares libres → Agotado; con pocos → Últimos cupos. Solo sube de nivel, nunca baja solo."""
        if not s.cupos or s.estado == "preventa":
            return None
        libres = s.cupos - ocupados(s.id)
        nuevo = "agotado" if libres <= 0 else ("ultimos" if libres <= UMBRAL_ULTIMOS and s.estado == "disponible" else None)
        if nuevo and s.estado != nuevo:
            s.estado = nuevo
            return nuevo
        return None

    def resumen_salida(s):
        pas = Pasajero.query.filter_by(salida_id=s.id).order_by(Pasajero.creado).all()
        activos = [p for p in pas if p.estado != "cancelado"]
        total = sum((p.total or 0 for p in activos), Decimal(0))
        pagado = sum((p.pagado or 0 for p in activos), Decimal(0))
        return dict(pas=pas, ocupados=len(activos), libres=(s.cupos - len(activos)) if s.cupos else None, total=total, pagado=pagado, saldo=total - pagado)

    @app.get("/admin/salidas/<int:sid>/pasajeros", endpoint="pasajeros")
    @admin
    def pasajeros(sid):
        s = db.session.get(Salida, sid) or abort(404)
        return render_template("admin/pasajeros.html", s=s, r=resumen_salida(s))

    @app.post("/admin/salidas/<int:sid>/pasajeros", endpoint="pasajero_alta")
    @admin
    def pasajero_alta(sid):
        s = db.session.get(Salida, sid) or abort(404)
        f = request.form
        nombre = _txt(f.get("nombre"), 120)
        total, pagado = _dinero(f.get("total")), _dinero(f.get("pagado"))
        if not nombre:
            flash("Poné el nombre del pasajero.", "error")
        elif total is None or pagado is None:
            flash("Revisá los montos: tienen que ser números en pesos.", "error")
        else:
            estado = f.get("estado") if f.get("estado") in ESTADOS_PASAJERO else "reservado"
            cli = buscar_o_crear_cliente(nombre, f.get("telefono"), f.get("dni"), etiqueta=None)
            db.session.add(Pasajero(salida_id=sid, cliente_id=cli.id, nombre=nombre, dni=_txt(f.get("dni"), 20), telefono=_txt(f.get("telefono"), 40),
                                    total=total, pagado=pagado, estado=estado, nota=_txt(f.get("nota"), 300)))
            db.session.flush()
            nuevo = ajustar_estado(s)
            db.session.commit()
            flash(f"Anoté a {nombre}." + (f" La salida pasó sola a «{C['ESTADOS'][nuevo]}»." if nuevo else ""), "ok")
        return redirect(url_for("pasajeros", sid=sid))

    @app.route("/admin/pasajeros/<int:pid>", methods=["GET", "POST"], endpoint="pasajero_editar")
    @admin
    def pasajero_editar(pid):
        p = db.session.get(Pasajero, pid) or abort(404)
        if request.method == "POST":
            f = request.form
            nombre, total, pagado = _txt(f.get("nombre"), 120), _dinero(f.get("total")), _dinero(f.get("pagado"))
            if not nombre or total is None or pagado is None:
                flash("Revisá el nombre y los montos.", "error")
            else:
                p.nombre, p.dni, p.telefono = nombre, _txt(f.get("dni"), 20), _txt(f.get("telefono"), 40)
                p.total, p.pagado, p.nota = total, pagado, _txt(f.get("nota"), 300)
                p.estado = f.get("estado") if f.get("estado") in ESTADOS_PASAJERO else p.estado
                db.session.flush()
                ajustar_estado(p.salida)
                db.session.commit()
                flash("Cambios guardados.", "ok")
                return redirect(url_for("pasajeros", sid=p.salida_id))
        return render_template("admin/pasajero_form.html", p=p)

    @app.post("/admin/pasajeros/<int:pid>/pago", endpoint="pasajero_pago")
    @admin
    def pasajero_pago(pid):
        """Suma un pago a lo que ya pagó (desde la lista)."""
        p = db.session.get(Pasajero, pid) or abort(404)
        monto = _dinero(request.form.get("monto"))
        if not monto:
            flash("Poné cuánto pagó.", "error")
        else:
            p.pagado = (p.pagado or 0) + monto
            db.session.commit()
            flash(f"{p.nombre}: sumé {_pesos(monto)}. Debe {_pesos(max(p.saldo, 0))}.", "ok")
        return redirect(url_for("pasajeros", sid=p.salida_id) + f"#p{pid}")

    @app.post("/admin/pasajeros/<int:pid>/borrar", endpoint="pasajero_borrar")
    @admin
    def pasajero_borrar(pid):
        p = db.session.get(Pasajero, pid) or abort(404)
        sid, nombre = p.salida_id, p.nombre
        db.session.delete(p)
        db.session.commit()
        flash(f"Saqué a {nombre} de la lista.", "ok")
        return redirect(url_for("pasajeros", sid=sid))

    @app.get("/admin/salidas/<int:sid>/pasajeros.csv", endpoint="pasajeros_csv")
    @admin
    def pasajeros_csv(sid):
        s = db.session.get(Salida, sid) or abort(404)
        r = resumen_salida(s)
        filas = [["Nombre", "DNI", "Teléfono", "Estado", "Total", "Pagado", "Saldo", "Nota"]] + \
                [[p.nombre, p.dni, p.telefono, ESTADOS_PASAJERO[p.estado], f"{p.total:.2f}", f"{p.pagado:.2f}", f"{p.saldo:.2f}", p.nota] for p in r["pas"]]
        return _csv(filas, f"pasajeros-{s.slug}.csv")

    def _csv(filas, nombre):
        b = io.StringIO()
        csv.writer(b, delimiter=";").writerows(filas)                       # «;» y BOM: se abre bien en el Excel en español
        return Response("﻿" + b.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

    # ================================================================== sorteos
    def _numeros(txt, cantidad):
        """«5, 7-10, 22» → {5, 7, 8, 9, 10, 22} (solo dentro del sorteo)."""
        res = set()
        for parte in re.split(r"[,\s;]+", txt or ""):
            m = re.fullmatch(r"(\d{1,4})(?:-(\d{1,4}))?", parte)
            if not m:
                continue
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            res.update(n for n in range(min(a, b), max(a, b) + 1) if 1 <= n <= cantidad)
        return res

    @app.route("/admin/sorteos", methods=["GET", "POST"], endpoint="sorteos")
    @admin
    def sorteos():
        if request.method == "POST":
            f = request.form
            nombre = _txt(f.get("nombre"), 120)
            try:
                cantidad = int(f.get("cantidad") or 0)
            except ValueError:
                cantidad = 0
            if not nombre or not 2 <= cantidad <= MAX_SORTEO:
                flash(f"Poné el nombre y una cantidad de números entre 2 y {MAX_SORTEO}.", "error")
            else:
                try:
                    fecha = date.fromisoformat(f.get("fecha") or "")
                except ValueError:
                    fecha = None
                s = Sorteo(token=secrets.token_urlsafe(9), nombre=nombre, premio=_txt(f.get("premio"), 200), cantidad=cantidad, precio=_txt(f.get("precio"), 40), fecha=fecha)
                db.session.add(s)
                db.session.commit()
                flash("Sorteo creado.", "ok")
                return redirect(url_for("sorteo_ver", sid=s.id))
        cuentas = dict(db.session.query(SorteoNumero.sorteo_id, func.count(SorteoNumero.id)).group_by(SorteoNumero.sorteo_id).all())
        return render_template("admin/sorteos.html", lista=Sorteo.query.order_by(Sorteo.creado.desc()).all(), cuentas=cuentas)

    def _datos_sorteo(s):
        nums = {n.numero: n for n in SorteoNumero.query.filter_by(sorteo_id=s.id).all()}
        pagados = sum(1 for n in nums.values() if n.estado == "pagado")
        return nums, dict(vendidos=len(nums), pagados=pagados, reservados=len(nums) - pagados, libres=s.cantidad - len(nums))

    @app.get("/admin/sorteos/<int:sid>", endpoint="sorteo_ver")
    @admin
    def sorteo_ver(sid):
        s = db.session.get(Sorteo, sid) or abort(404)
        nums, st = _datos_sorteo(s)
        return render_template("admin/sorteo.html", s=s, nums=nums, st=st, base=request.url_root.rstrip("/"),
                               ganador=nums.get(s.ganador_numero) if s.ganador_numero else None)

    @app.post("/admin/sorteos/<int:sid>/numeros", endpoint="sorteo_numeros")
    @admin
    def sorteo_numeros(sid):
        s = db.session.get(Sorteo, sid) or abort(404)
        f = request.form
        quedan = _numeros(f.get("numeros"), s.cantidad)
        accion = f.get("estado")
        if not quedan:
            flash(f"No entendí los números. Ejemplo: 5, 7-10, 22 (del 1 al {s.cantidad}).", "error")
        elif accion == "libre":
            SorteoNumero.query.filter(SorteoNumero.sorteo_id == sid, SorteoNumero.numero.in_(quedan)).delete(synchronize_session=False)
            db.session.commit()
            flash(f"Liberé {len(quedan)} número{'s' if len(quedan) != 1 else ''}.", "ok")
        elif accion in ("reservado", "pagado"):
            existentes = {n.numero: n for n in SorteoNumero.query.filter(SorteoNumero.sorteo_id == sid, SorteoNumero.numero.in_(quedan)).all()}
            for n in sorted(quedan):
                fila = existentes.get(n) or SorteoNumero(sorteo_id=sid, numero=n)
                fila.estado = accion
                if f.get("nombre") or not fila.nombre:
                    fila.nombre = _txt(f.get("nombre"), 120)
                if f.get("telefono") or not fila.telefono:
                    fila.telefono = _txt(f.get("telefono"), 40)
                db.session.add(fila)
            db.session.commit()
            flash(f"Anoté {len(quedan)} número{'s' if len(quedan) != 1 else ''} como {accion}{'s' if len(quedan) != 1 else ''}.", "ok")
        return redirect(url_for("sorteo_ver", sid=sid))

    @app.post("/admin/sorteos/<int:sid>/sortear", endpoint="sorteo_sortear")
    @admin
    def sorteo_sortear(sid):
        s = db.session.get(Sorteo, sid) or abort(404)
        if s.ganador_numero:
            flash("Este sorteo ya tiene ganador. Para repetirlo, primero tocá «Anular el sorteo».", "error")
        else:
            pagados = [n.numero for n in SorteoNumero.query.filter_by(sorteo_id=sid, estado="pagado").all()]
            if not pagados:
                flash("Todavía no hay números pagados: el sorteo se hace solo entre los pagados.", "error")
            else:
                s.ganador_numero, s.sorteado_en = secrets.choice(pagados), ahora()
                db.session.commit()
                flash(f"¡Salió el número {s.ganador_numero}!", "ok")
        return redirect(url_for("sorteo_ver", sid=sid))

    @app.post("/admin/sorteos/<int:sid>/anular", endpoint="sorteo_anular")
    @admin
    def sorteo_anular(sid):
        s = db.session.get(Sorteo, sid) or abort(404)
        s.ganador_numero = s.sorteado_en = None
        db.session.commit()
        flash("Anulé el resultado. Podés volver a sortear.", "ok")
        return redirect(url_for("sorteo_ver", sid=sid))

    @app.post("/admin/sorteos/<int:sid>/borrar", endpoint="sorteo_borrar")
    @admin
    def sorteo_borrar(sid):
        s = db.session.get(Sorteo, sid) or abort(404)
        SorteoNumero.query.filter_by(sorteo_id=sid).delete(synchronize_session=False)
        db.session.delete(s)
        db.session.commit()
        flash("Sorteo borrado.", "ok")
        return redirect(url_for("sorteos"))

    @app.get("/sorteo/<token>", endpoint="sorteo_publico")
    def sorteo_publico(token):
        """Página para compartir: muestra qué números están libres y ocupados, sin nombres ni teléfonos."""
        s = Sorteo.query.filter_by(token=token).first() or abort(404)
        nums, st = _datos_sorteo(s)
        r = render_template("sorteo_publico.html", s=s, ocupados=set(nums), st=st, c=ajustes())
        return Response(r, mimetype="text/html", headers={"Cache-Control": "no-cache", "X-Robots-Tag": "noindex"})

    # ================================================================== flyers
    @app.get("/admin/flyers", endpoint="flyers")
    @admin
    def flyers():
        q = Salida.query.filter(Salida.activa.is_(True), Salida.fecha >= hoy()).order_by(Salida.fecha).all()
        datos = [dict(id=x.id, destino=x.destino, dia=x.dia or C["dia_corto"](x.fecha), lugar=x.lugar or "", precio=x.precio or "", nota=x.nota or "",
                      estado=x.estado, empresa=x.empresa, img=(x.img if x.img.startswith(("/", "http")) else "/" + x.img)) for x in q]
        return render_template("admin/flyers.html", salidas=datos, c=ajustes(), elegida=request.args.get("salida", type=int))

    # ================================================================== reporte mensual
    @app.get("/admin/reporte", endpoint="reporte")
    @admin
    def reporte():
        try:
            y, m = (int(x) for x in (request.args.get("mes") or hoy().strftime("%Y-%m")).split("-"))
            desde = date(y, m, 1)
        except ValueError:
            desde = hoy().replace(day=1)
        hasta = (desde + timedelta(days=32)).replace(day=1)
        ant, sig = (desde - timedelta(days=1)).replace(day=1), hasta
        d0, d1 = datetime.combine(desde, datetime.min.time()), datetime.combine(hasta, datetime.min.time())

        cons = Consulta.query.filter(Consulta.creada >= d0, Consulta.creada < d1).all()
        por_origen, por_estado = {}, {}
        for k in cons:
            por_origen[k.origen or "web"] = por_origen.get(k.origen or "web", 0) + 1
            por_estado[k.estado] = por_estado.get(k.estado, 0) + 1
        ventas = sum(por_estado.get(e, 0) for e in ("senia", "vendida"))
        res = Pasajero.query.filter(Pasajero.creado >= d0, Pasajero.creado < d1, Pasajero.estado != "cancelado").all()
        canceladas = Pasajero.query.filter(Pasajero.creado >= d0, Pasajero.creado < d1, Pasajero.estado == "cancelado").count()
        total = sum((p.total or 0 for p in res), Decimal(0))
        pagado = sum((p.pagado or 0 for p in res), Decimal(0))
        salidas = Salida.query.filter(Salida.fecha >= desde, Salida.fecha < hasta).order_by(Salida.fecha).all()
        filas_sal = []
        for s in salidas:
            r = resumen_salida(s)
            filas_sal.append(dict(s=s, ocupados=r["ocupados"], total=r["total"], pagado=r["pagado"], saldo=r["saldo"]))
        nuevos = Cliente.query.filter(Cliente.creado >= d0, Cliente.creado < d1).count()
        por_cobrar = db.session.query(func.coalesce(func.sum(Pasajero.total - Pasajero.pagado), 0)).join(Salida).filter(
            Pasajero.estado != "cancelado", Salida.fecha >= hoy()).scalar() or 0
        mes_txt = f"{['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'][desde.month - 1]} de {desde.year}"
        resumen = (f"Resumen de {mes_txt}\n• Consultas: {len(cons)} ({ventas} terminaron en seña o venta)\n• Pasajeros nuevos: {len(res)}"
                   f"\n• Facturado en reservas: {_pesos(total)} · cobrado {_pesos(pagado)}\n• Clientes nuevos: {nuevos}\n• Salidas del mes: {len(salidas)}")
        return render_template("admin/reporte.html", desde=desde, mes_txt=mes_txt, ant=ant.strftime("%Y-%m"), sig=sig.strftime("%Y-%m"), es_actual=desde == hoy().replace(day=1),
                               cons=len(cons), por_origen=sorted(por_origen.items(), key=lambda x: -x[1]), por_estado=por_estado, ventas=ventas,
                               conv=(round(100 * ventas / len(cons)) if cons else 0), res=len(res), canceladas=canceladas, total=total, pagado=pagado,
                               filas_sal=filas_sal, nuevos=nuevos, por_cobrar=por_cobrar, resumen=resumen)

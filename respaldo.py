"""Respaldo y restauración de todas las tablas de la agencia (las que empiezan con vdv_).

* Desde el panel: Respaldo → «Descargar respaldo» baja un archivo .json con todo (salidas, consultas, clientes, pasajeros,
  sorteos, portada, fotos subidas y datos de contacto).
* Para restaurar (lo hace Michael, desde una terminal con DATABASE_URL apuntando a la base):
      python respaldo.py restaurar respaldo-AAAA-MM-DD.json
  Borra lo que haya en las tablas vdv_ y carga el contenido del archivo. No toca las tablas de Facturea.
* Para hacer un respaldo desde la terminal:  python respaldo.py guardar [archivo.json]
"""
import base64
import json
import sys
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, LargeBinary, text

from extensiones import db

PREFIJO = "vdv_"
VERSION = 1


def tablas():
    return [t for t in db.metadata.sorted_tables if t.name.startswith(PREFIJO)]


def _a_json(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"__b64__": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _de_json(col, v):
    if v is None:
        return None
    if isinstance(col.type, LargeBinary):
        return base64.b64decode(v["__b64__"])
    if isinstance(col.type, DateTime):
        return datetime.fromisoformat(v)
    if isinstance(col.type, Date):
        return date.fromisoformat(v)
    if isinstance(col.type, Boolean):
        return bool(v)
    return v


def exportar():
    out = {"version": VERSION, "creado": datetime.now().isoformat(timespec="seconds"), "tablas": {}}
    for t in tablas():
        filas = db.session.execute(t.select()).mappings().all()
        out["tablas"][t.name] = [{k: _a_json(v) for k, v in f.items()} for f in filas]
    return out


def resumen(datos):
    return {k: len(v) for k, v in datos["tablas"].items()}


def restaurar(datos):
    """Reemplaza el contenido de las tablas vdv_ por el del respaldo. Todo o nada."""
    if not isinstance(datos, dict) or datos.get("version") != VERSION or "tablas" not in datos:
        raise ValueError("Ese archivo no es un respaldo de la agencia.")
    ts = tablas()
    desconocidas = [n for n in datos["tablas"] if n not in {t.name for t in ts}]
    if desconocidas:
        raise ValueError("El respaldo trae tablas que no existen acá: " + ", ".join(desconocidas))
    try:
        for t in reversed(ts):
            db.session.execute(t.delete())
        for t in ts:
            filas = datos["tablas"].get(t.name, [])
            cols = {c.name: c for c in t.columns}
            lote = [{k: _de_json(cols[k], v) for k, v in f.items() if k in cols} for f in filas]
            if lote:
                db.session.execute(t.insert(), lote)
        if db.engine.dialect.name == "postgresql":      # que los próximos ids sigan después del último
            for t in ts:
                pk = [c for c in t.primary_key.columns if c.type.python_type is int]
                if pk:
                    db.session.execute(text(f"SELECT setval(pg_get_serial_sequence('{t.name}', '{pk[0].name}'), "
                                            f"COALESCE((SELECT MAX({pk[0].name}) FROM {t.name}), 0) + 1, false)"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return resumen(datos)


if __name__ == "__main__":
    import app as A
    ap = A.crear_app()
    uso = "Uso: python respaldo.py guardar [archivo.json]  |  python respaldo.py restaurar archivo.json"
    if len(sys.argv) < 2:
        sys.exit(uso)
    with ap.app_context():
        if sys.argv[1] == "guardar":
            nombre = sys.argv[2] if len(sys.argv) > 2 else f"respaldo-{date.today().isoformat()}.json"
            d = exportar()
            open(nombre, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
            print("Guardado", nombre, resumen(d))
        elif sys.argv[1] == "restaurar" and len(sys.argv) > 2:
            print("Restaurado:", restaurar(json.load(open(sys.argv[2], encoding="utf-8"))))
        else:
            sys.exit(uso)

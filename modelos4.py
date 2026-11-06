"""Tablas de la Etapa 4: clientes, pasajeros por salida y sorteos con números."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from extensiones import db

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _ahora():
    return datetime.now(TZ).replace(tzinfo=None)


def tel_norm(t):
    """Los últimos 10 dígitos del teléfono: sirve para reconocer a la misma persona aunque lo escriba distinto."""
    return re.sub(r"\D", "", t or "")[-10:]


class Cliente(db.Model):
    __tablename__ = "vdv_cliente"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    telefono = db.Column(db.String(40), default="")
    tel_norm = db.Column(db.String(12), default="", index=True)
    dni = db.Column(db.String(20), default="")
    email = db.Column(db.String(120), default="")
    localidad = db.Column(db.String(80), default="")
    etiquetas = db.Column(db.String(200), default="")                 # separadas por coma: «vip, escuelas, religioso»
    notas = db.Column(db.String(500), default="")
    creado = db.Column(db.DateTime, default=_ahora)

    @property
    def lista_etiquetas(self):
        return [e.strip() for e in (self.etiquetas or "").split(",") if e.strip()]


class Pasajero(db.Model):
    __tablename__ = "vdv_pasajero"
    id = db.Column(db.Integer, primary_key=True)
    salida_id = db.Column(db.Integer, db.ForeignKey("vdv_salida.id"), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("vdv_cliente.id"), index=True)
    nombre = db.Column(db.String(120), nullable=False)
    dni = db.Column(db.String(20), default="")
    telefono = db.Column(db.String(40), default="")
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0)    # lo que tiene que pagar
    pagado = db.Column(db.Numeric(12, 2), nullable=False, default=0)   # seña + pagos hechos
    estado = db.Column(db.String(12), nullable=False, default="reservado")   # reservado | confirmado | cancelado
    nota = db.Column(db.String(300), default="")
    creado = db.Column(db.DateTime, default=_ahora)

    salida = db.relationship("Salida")
    cliente = db.relationship("Cliente")

    @property
    def saldo(self):
        return (self.total or 0) - (self.pagado or 0)


class Sorteo(db.Model):
    __tablename__ = "vdv_sorteo"
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(24), unique=True, nullable=False, index=True)   # el link público no usa el id
    nombre = db.Column(db.String(120), nullable=False)
    premio = db.Column(db.String(200), default="")
    cantidad = db.Column(db.Integer, nullable=False, default=100)
    precio = db.Column(db.String(40), default="")
    fecha = db.Column(db.Date)
    ganador_numero = db.Column(db.Integer)
    sorteado_en = db.Column(db.DateTime)
    creado = db.Column(db.DateTime, default=_ahora)


class SorteoNumero(db.Model):
    """Solo existen los números vendidos o reservados; el resto está libre."""
    __tablename__ = "vdv_sorteo_numero"
    id = db.Column(db.Integer, primary_key=True)
    sorteo_id = db.Column(db.Integer, db.ForeignKey("vdv_sorteo.id"), nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(10), nullable=False, default="reservado")   # reservado | pagado
    nombre = db.Column(db.String(120), default="")
    telefono = db.Column(db.String(40), default="")
    __table_args__ = (db.UniqueConstraint("sorteo_id", "numero", name="uq_vdv_sorteo_numero"),)

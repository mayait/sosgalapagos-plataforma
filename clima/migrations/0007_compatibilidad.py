"""Vistas con la forma de la base SQLite del recolector anterior, para que su código corra sobre PostgreSQL.

obs, estaciones y corridas se leen y se escriben como antes; los disparadores llevan cada
INSERT y DELETE a los modelos de Django. date(texto, intervalo) imita la función de SQLite.
"""
from django.db import migrations

CREAR = r"""
CREATE OR REPLACE VIEW obs AS
  SELECT e.fuente, e.codigo AS estacion, o.variable,
         to_char(o.ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS ts, o.valor
  FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id;

CREATE OR REPLACE FUNCTION obs_insertar() RETURNS trigger AS $$
DECLARE est integer;
BEGIN
  SELECT id INTO est FROM clima_estacion WHERE fuente = NEW.fuente AND codigo = NEW.estacion;
  IF est IS NULL THEN
    INSERT INTO clima_estacion (fuente, codigo, nombre, isla, operador) VALUES (NEW.fuente, NEW.estacion, NEW.estacion, '', '')
    ON CONFLICT (fuente, codigo) DO UPDATE SET fuente = EXCLUDED.fuente RETURNING id INTO est;
  END IF;
  INSERT INTO clima_observacion (estacion_id, variable, ts, valor) VALUES (est, NEW.variable, NEW.ts::timestamptz, NEW.valor)
  ON CONFLICT (estacion_id, variable, ts) DO UPDATE SET valor = EXCLUDED.valor;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER obs_insertar INSTEAD OF INSERT ON obs FOR EACH ROW EXECUTE FUNCTION obs_insertar();

CREATE OR REPLACE FUNCTION obs_borrar() RETURNS trigger AS $$
BEGIN
  DELETE FROM clima_observacion o USING clima_estacion e
  WHERE e.id = o.estacion_id AND e.fuente = OLD.fuente AND e.codigo = OLD.estacion AND o.variable = OLD.variable AND o.ts = OLD.ts::timestamptz;
  RETURN OLD;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER obs_borrar INSTEAD OF DELETE ON obs FOR EACH ROW EXECUTE FUNCTION obs_borrar();

-- Las zonas que mide el satélite no son estaciones: en la base original tampoco estaban en esta tabla.
CREATE OR REPLACE VIEW estaciones AS
  SELECT fuente, codigo AS estacion, nombre, isla, ST_Y(punto) AS lat, ST_X(punto) AS lon, altitud_m, operador,
         NULL::text AS url, NULL::text AS meta
  FROM clima_estacion WHERE fuente <> 'goes';

CREATE OR REPLACE FUNCTION estaciones_insertar() RETURNS trigger AS $$
BEGIN
  INSERT INTO clima_estacion (fuente, codigo, nombre, isla, punto, altitud_m, operador)
  VALUES (NEW.fuente, NEW.estacion, coalesce(NEW.nombre, ''), coalesce(NEW.isla, ''),
          CASE WHEN NEW.lat IS NULL OR NEW.lon IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(NEW.lon, NEW.lat), 4326) END,
          NEW.altitud_m, coalesce(NEW.operador, ''))
  ON CONFLICT (fuente, codigo) DO UPDATE SET nombre = EXCLUDED.nombre, isla = EXCLUDED.isla, punto = EXCLUDED.punto,
    altitud_m = EXCLUDED.altitud_m, operador = EXCLUDED.operador;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER estaciones_insertar INSTEAD OF INSERT ON estaciones FOR EACH ROW EXECUTE FUNCTION estaciones_insertar();

CREATE OR REPLACE VIEW corridas AS
  SELECT to_char(ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS ts, fuente, ok::int AS ok, registros, segundos, error
  FROM clima_corrida;

CREATE OR REPLACE FUNCTION corridas_insertar() RETURNS trigger AS $$
BEGIN
  INSERT INTO clima_corrida (ts, fuente, ok, registros, segundos, error)
  VALUES (NEW.ts::timestamptz, NEW.fuente, coalesce(NEW.ok, 0) <> 0, NEW.registros, NEW.segundos, coalesce(NEW.error, ''))
  ON CONFLICT (fuente, ts) DO UPDATE SET ok = EXCLUDED.ok, registros = EXCLUDED.registros, segundos = EXCLUDED.segundos, error = EXCLUDED.error;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER corridas_insertar INSTEAD OF INSERT ON corridas FOR EACH ROW EXECUTE FUNCTION corridas_insertar();

-- date('2026-11-21T03:00:00Z', '-6 hours') de SQLite: la fecha tras sumar el intervalo.
CREATE OR REPLACE FUNCTION date(text, text) RETURNS text AS $$
  SELECT to_char((replace($1, 'Z', '')::timestamp + $2::interval)::date, 'YYYY-MM-DD')
$$ LANGUAGE sql IMMUTABLE;
"""

QUITAR = """
DROP VIEW IF EXISTS obs; DROP VIEW IF EXISTS estaciones; DROP VIEW IF EXISTS corridas;
DROP FUNCTION IF EXISTS obs_insertar(); DROP FUNCTION IF EXISTS obs_borrar();
DROP FUNCTION IF EXISTS estaciones_insertar(); DROP FUNCTION IF EXISTS corridas_insertar(); DROP FUNCTION IF EXISTS date(text, text);
"""


class Migration(migrations.Migration):
    dependencies = [("clima", "0006_nivel")]
    operations = [migrations.RunSQL(CREAR, QUITAR)]

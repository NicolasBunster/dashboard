-- Schema PostgreSQL para I_Site Dashboard
-- Ejecutar una vez al crear la base de datos en Railway

CREATE TABLE IF NOT EXISTS golpes (
    id          BIGSERIAL PRIMARY KEY,
    cliente     VARCHAR(100) NOT NULL,
    maquina     VARCHAR(100),
    nro_flota   VARCHAR(50),
    familia     VARCHAR(100),
    modelo      VARCHAR(100),
    marca       VARCHAR(100),
    site        VARCHAR(200),
    conductor   VARCHAR(200),
    nivel       VARCHAR(20),
    hora_golpe  VARCHAR(30),
    descarga_bateria FLOAT,
    velocidad   FLOAT
);
CREATE INDEX IF NOT EXISTS idx_golpes_cliente ON golpes(cliente);
CREATE INDEX IF NOT EXISTS idx_golpes_fecha   ON golpes(hora_golpe);
CREATE INDEX IF NOT EXISTS idx_golpes_cl_fec  ON golpes(cliente, hora_golpe);

CREATE TABLE IF NOT EXISTS utilizacion (
    id              BIGSERIAL PRIMARY KEY,
    cliente         VARCHAR(100) NOT NULL,
    maquina         VARCHAR(100),
    nro_flota       VARCHAR(50),
    familia         VARCHAR(100),
    modelo          VARCHAR(100),
    marca           VARCHAR(100),
    site            VARCHAR(200),
    conductor       VARCHAR(200),
    inicio          VARCHAR(30),
    seg_llave       FLOAT,
    seg_funcionam   FLOAT,
    seg_traccion    FLOAT,
    seg_elevacion   FLOAT,
    ratio_func_llave FLOAT,
    metodo_apagado  VARCHAR(100),
    claves_compartidas INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_util_cliente ON utilizacion(cliente);
CREATE INDEX IF NOT EXISTS idx_util_fecha   ON utilizacion(inicio);
CREATE INDEX IF NOT EXISTS idx_util_cl_fec  ON utilizacion(cliente, inicio);

-- ====================================
-- Inicialización de la base de datos
-- Tablas: registros_detalle y resumen_diario
-- ====================================

-- Tabla de detalle: guarda cada chequeo realizado
CREATE TABLE IF NOT EXISTS registros_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    servidor TEXT NOT NULL,
    fecha_hora TEXT NOT NULL,
    estado TEXT NOT NULL
);

-- Tabla de resumen diario: guarda un estado final por servidor y día
CREATE TABLE IF NOT EXISTS resumen_diario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    servidor TEXT NOT NULL,
    fecha TEXT NOT NULL,
    estado_final TEXT NOT NULL,
    UNIQUE(servidor, fecha)  -- asegura que haya solo un registro diario por servidor
);


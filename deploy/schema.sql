-- ==============================================================================
-- SCHEMA SQL: SIGECI - Sistema de Gestión de Congresos / Eventos e Investigaciones
-- Generado a partir de: desarrollo-1-db.drawio.svg
-- Motor de Base de Datos: PostgreSQL (Supabase Compatible)
-- ==============================================================================

-- Extensiones útiles para UUIDs y funciones criptográficas si son requeridas
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==============================================================================
-- 1. TABLA: profile
-- Roles o perfiles del sistema (e.g., ADMIN, MEMBER, AUTHOR)
-- ==============================================================================
CREATE TABLE profile(
    profile_id SERIAL PRIMARY KEY,
    profile_name VARCHAR(60) NOT NULL,
    profile_active BOOLEAN NOT NULL DEFAULT TRUE,
    profile_delete BOOLEAN NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE profile IS 'Perfiles/Roles del sistema (ADMIN, MEMBER, AUTHOR)';

-- ==============================================================================
-- 2. TABLA: users
-- Usuarios del sistema con soporte para autenticación local o externa (GMAIL | ACCOUNT)
-- ==============================================================================
CREATE TABLE users(
    user_id SERIAL PRIMARY KEY,
    user_name VARCHAR(60) NOT NULL,
    user_lastname VARCHAR(60) NOT NULL,
    user_password TEXT NOT NULL,
    user_email VARCHAR(120) NOT NULL UNIQUE,
    user_provider VARCHAR(60) NOT NULL DEFAULT 'ACCOUNT' CHECK (user_provider IN ('GMAIL', 'ACCOUNT')),
    profile_id INT NOT NULL REFERENCES profile (profile_id),
    user_active BOOLEAN NOT NULL DEFAULT TRUE,
    user_delete BOOLEAN NOT NULL DEFAULT FALSE,

    -- Columnas de Auditoría (Definición: ...)
    user_created_by INT REFERENCES users (user_id),
    user_created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_updated_by INT REFERENCES users (user_id),
    user_updated_at timestamp with time zone
);

COMMENT ON TABLE users IS 'Usuarios registrados con método de autenticación y auditoría';

-- ==============================================================================
-- 3. TABLA: profile_action
-- Permisos y acciones asignadas a cada perfil sobre los módulos
-- Módulos (action): 'article', 'event', 'application'
-- Permisos (permissions): 'view|create|update|delete|active|inactive|download'
-- ==============================================================================
CREATE TABLE profile_action(
    profile_action_id SERIAL PRIMARY KEY,
    profile_id INT NOT NULL REFERENCES profile (profile_id),
    profile_action_action VARCHAR(60) NOT NULL,      -- 'article' | 'event' | 'application'
    profile_action_visibility BOOLEAN NOT NULL DEFAULT TRUE,
    profile_action_permissions VARCHAR(60) NOT NULL, -- 'view|create|update|delete|active|inactive|download'
    profile_active BOOLEAN NOT NULL DEFAULT TRUE,
    profile_delete BOOLEAN NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE profile_action IS 'Permisos y acciones matriciales por perfil';

-- ==============================================================================
-- 4. TABLA: topic
-- Áreas temáticas / tópicos para clasificar artículos y agendas
-- ==============================================================================
CREATE TABLE topic(
    topic_id SERIAL PRIMARY KEY,
    topic_subject VARCHAR(150) NOT NULL,
    topic_description TEXT,

    -- Columnas de Auditoría (Definición: ...)
    topic_created_by INT REFERENCES users (user_id),
    topic_created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    topic_updated_by INT REFERENCES users (user_id),
    topic_updated_at timestamp with time zone
);

COMMENT ON TABLE topic IS 'Tópicos o áreas temáticas de investigación';

INSERT INTO topic (topic_id, topic_subject, topic_description, topic_active, topic_created_at)
VALUES 
    (1, 'Inteligencia Artificial', 'Redes neuronales y visión por computadora', true, CURRENT_TIMESTAMP),
    (2, 'Ciberseguridad', 'Criptografía y seguridad en sistemas distribuidos', true, CURRENT_TIMESTAMP),
    (3, 'Ingeniería de Software', 'Metodologías ágiles y gestión de proyectos', true, CURRENT_TIMESTAMP)
ON CONFLICT (topic_id) DO NOTHING;

-- ==============================================================================
-- 5. TABLA: article
-- Artículos o ponencias científicas enviadas por los autores
-- ==============================================================================
CREATE TABLE article(
    article_id SERIAL PRIMARY KEY,
    article_subject VARCHAR(255) NOT NULL,
    article_description TEXT,
    topic_id INT NOT NULL REFERENCES topic (topic_id),
    article TEXT NOT NULL,                           -- Contenido o cuerpo del artículo
    article_date timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Columnas de Auditoría (Definición: ...)
    article_created_by INT REFERENCES users (user_id), -- Autor / creador del artículo
    article_created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    article_updated_by INT REFERENCES users (user_id),
    article_updated_at timestamp with time zone
);

COMMENT ON TABLE article IS 'Artículos científicos postulados';

-- ==============================================================================
-- 6. TABLA: article_attached
-- Versiones y adjuntos (documentos/archivos PDF/Word) del artículo
-- ==============================================================================
CREATE TABLE article_attached(
    article_attached_id SERIAL PRIMARY KEY,
    article_id INT NOT NULL REFERENCES article (article_id),
    article_attached_url TEXT NOT NULL,
    article_attached_version VARCHAR(20) NOT NULL DEFAULT '1.0'
);

COMMENT ON TABLE article_attached IS 'Archivos adjuntos y control de versiones del artículo';

-- ==============================================================================
-- 7. TABLA: article_reviewer
-- Evaluaciones asignadas a revisores sobre un artículo y su adjunto
-- Estado: 'REJECTED' | 'APPROVED' | 'IN_REVIEW' | 'PENDING'
-- ==============================================================================
CREATE TABLE article_reviewer(
    article_reviewer_id SERIAL PRIMARY KEY,
    article_id INT NOT NULL REFERENCES article (article_id),
    article_attached_id INT REFERENCES article_attached (article_attached_id),
    user_id INT NOT NULL REFERENCES users (user_id),
    status VARCHAR(50) NOT NULL DEFAULT 'IN_REVIEW' CHECK (status IN ('REJECTED', 'APPROVED', 'IN_REVIEW', 'PENDING')),
    comment TEXT
);

COMMENT ON TABLE article_reviewer IS 'Asignaciones de revisión y veredictos de artículos';

-- ==============================================================================
-- 8. TABLA: event
-- Congresos, conferencias o eventos académicos
-- ==============================================================================
CREATE TABLE event(
    event_id SERIAL PRIMARY KEY,
    event_name VARCHAR(200) NOT NULL,
    event_description TEXT,
    event_address VARCHAR(255),
    event_date timestamp with time zone NOT NULL,

    -- Columnas de Auditoría (Definición: ...)
    event_created_by INT REFERENCES users (user_id),
    event_created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_updated_by INT REFERENCES users (user_id),
    event_updated_at timestamp with time zone
);

COMMENT ON TABLE event IS 'Eventos y congresos';

-- ==============================================================================
-- 9. TABLA: application
-- Convocatoria / Aplicación del artículo a revisión con ventanas de fechas
-- ==============================================================================
CREATE TABLE application(
    application_id SERIAL PRIMARY KEY,
    article_id INT NOT NULL REFERENCES article (article_id),
    application_end_date timestamp with time zone NOT NULL,
    application_review_end_date timestamp with time zone NOT NULL,
    application_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',

    -- Columnas de Auditoría (Definición: ...)
    application_created_by INT REFERENCES users (user_id),
    application_created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    application_updated_by INT REFERENCES users (user_id),
    application_updated_at timestamp with time zone
);

COMMENT ON TABLE application IS 'Postulaciones/Aplicaciones de artículos a eventos o convocatorias';

-- ==============================================================================
-- 10. TABLA: schedule
-- Cronograma y programación de presentaciones en el evento
-- ==============================================================================
CREATE TABLE schedule(
    schedule_id SERIAL PRIMARY KEY,
    event_id INT NOT NULL REFERENCES event (event_id),
    topic_id INT REFERENCES topic (topic_id),
    application_id INT REFERENCES application (application_id),
    schedule_hour TIME NOT NULL
);

COMMENT ON TABLE schedule IS 'Cronograma y agenda horaria de presentaciones';

-- ==============================================================================
-- ÍNDICES DE RENDIMIENTO (Performance Indexes)
-- ==============================================================================
CREATE INDEX IF NOT EXISTS idx_users_email ON users(user_email);
CREATE INDEX IF NOT EXISTS idx_users_profile ON users(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_action_profile ON profile_action(profile_id);
CREATE INDEX IF NOT EXISTS idx_article_topic ON article(topic_id);
CREATE INDEX IF NOT EXISTS idx_article_attached_article ON article_attached(article_id);
CREATE INDEX IF NOT EXISTS idx_article_reviewer_article ON article_reviewer(article_id);
CREATE INDEX IF NOT EXISTS idx_article_reviewer_user ON article_reviewer(user_id);
CREATE INDEX IF NOT EXISTS idx_application_article ON application(article_id);
CREATE INDEX IF NOT EXISTS idx_schedule_event ON schedule(event_id);
CREATE INDEX IF NOT EXISTS idx_schedule_application ON schedule(application_id);

-- ==============================================================================
-- TRIGGERS Y FUNCIONES RECOMENDADAS (Según notas del diagrama)
-- ==============================================================================

-- 1. Trigger para actualizar el estado del artículo a 'REVISIÓN' al agregar nueva versión adjunta
-- (Nota del diagrama: "Actualicemos la version - Articulo lo debemos actualizar a revision")
CREATE OR REPLACE FUNCTION fn_on_new_article_attached()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE application
    SET application_status = 'IN_REVIEW',
        application_updated_at = CURRENT_TIMESTAMP
    WHERE article_id = NEW.article_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_new_article_attached ON article_attached;
CREATE TRIGGER trg_new_article_attached
AFTER INSERT ON article_attached
FOR EACH ROW
EXECUTE FUNCTION fn_on_new_article_attached();

-- 2. Trigger de actualización de estados de la aplicación
-- (Nota del diagrama: "Disparar trigger de actualizacion de estados de la aplicacion")
CREATE OR REPLACE FUNCTION fn_update_application_status()
RETURNS TRIGGER AS $$
BEGIN
    NEW.application_updated_at = CURRENT_TIMESTAMP;
    
    IF CURRENT_TIMESTAMP > NEW.application_review_end_date AND NEW.application_status = 'IN_REVIEW' THEN
        NEW.application_status := 'REVIEW_CLOSED';
    ELSIF CURRENT_TIMESTAMP > NEW.application_end_date AND NEW.application_status = 'PENDING' THEN
        NEW.application_status := 'SUBMISSION_CLOSED';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_application_status ON application;
CREATE TRIGGER trg_update_application_status
BEFORE UPDATE OR INSERT ON application
FOR EACH ROW
EXECUTE FUNCTION fn_update_application_status();

-- SCRUM-129 · Registrar el permiso "me:delete" en la matriz (profile_action)
-- El endpoint POST /api/users/me/delete/ FALLA CERRADO: si el rol no tiene "me:delete", responde 403.
-- Ejecutar en Supabase (SQL editor) DESPUÉS de desplegar la migración 0005 (python manage.py migrate).
-- Antes de nada revisa las columnas reales:   \d profile_action
--
-- OJO: NO uses `seed_accounts` en producción para esto: sobrescribe los permisos de TODOS los recursos
-- con la matriz del código y puede pisar cambios que el equipo hizo a mano en la BD.

-- 0) Estado actual de la fila "me"
SELECT pa.profile_action_id, p.profile_name, pa.profile_action_permissions
FROM profile_action pa
JOIN profile p ON p.profile_id = pa.profile_id
WHERE pa.profile_action_action = 'me'
ORDER BY p.profile_name;

-- 1) Si la fila "me" ya existe (Login.me exige me:view): agregar "delete" sin tocar lo demás
UPDATE profile_action
SET profile_action_permissions = profile_action_permissions || '|delete'
WHERE profile_action_action = 'me'
  AND position('delete' IN profile_action_permissions) = 0;

-- 2) Si algún perfil NO tiene fila "me": crearla con view|delete
INSERT INTO profile_action (profile_id, profile_action_action, profile_action_permissions, profile_action_active, profile_action_delete)
SELECT p.profile_id, 'me', 'view|delete', TRUE, FALSE
FROM profile p
WHERE p.profile_name IN ('ADMIN', 'MEMBER', 'AUTHOR')
  AND NOT EXISTS (
      SELECT 1 FROM profile_action pa
      WHERE pa.profile_id = p.profile_id AND pa.profile_action_action = 'me'
  );
-- Si tu tabla tiene columnas extra NOT NULL del menú (profile_action_order, profile_action_visibility...),
-- agrégalas al INSERT con profile_action_visibility = FALSE: "me" NO debe aparecer como ítem del menú lateral.

-- 3) Verificación: los tres perfiles deben mostrar delete
SELECT p.profile_name, pa.profile_action_permissions
FROM profile_action pa
JOIN profile p ON p.profile_id = pa.profile_id
WHERE pa.profile_action_action = 'me'
ORDER BY p.profile_name;

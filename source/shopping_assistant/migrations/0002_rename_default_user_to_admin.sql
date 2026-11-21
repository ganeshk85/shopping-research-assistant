-- The single default user is called 'admin' (user decision 2026-11-20). 0001 seeded 'owner';
-- rename it in place so its id, and everything it owns, stay the same.
UPDATE users
SET username = 'admin', display_name = 'Admin'
WHERE username = 'owner'
  AND NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');

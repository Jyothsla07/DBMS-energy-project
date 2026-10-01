-- 04_readonly_user.sql  (MySQL 8.0+)
-- Optional: a SELECT-only account for the question-answering app (python/ask_app.py).
-- The app already rejects anything but SELECT and runs queries in a read-only
-- transaction; this account means the database itself also refuses writes.
--
-- Replace the password before running, then put the same user and password
-- in your .env file (MYSQL_USER / MYSQL_PWD).
--   mysql -u root -p -e "source sql/04_readonly_user.sql"

CREATE USER IF NOT EXISTS 'energy_reader'@'localhost' IDENTIFIED BY 'change_this_password';
GRANT SELECT ON energydb.* TO 'energy_reader'@'localhost';

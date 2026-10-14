# Sourced (not executed) by the MySQL image's entrypoint once, when the data
# volume is first initialised -- see docker-compose.yml. Being sourced gives it
# the entrypoint's docker_process_sql, which runs as root with the root
# password the entrypoint itself generated, so nothing here needs a root
# password from .env.
#
# Django's test runner creates and drops test_<database>; MYSQL_USER only gets
# rights on MYSQL_DATABASE by default, so grant that one extra name -- nothing wider.
docker_process_sql --database=mysql <<SQL
GRANT ALL PRIVILEGES ON \`test_${MYSQL_DATABASE}\`.* TO '${MYSQL_USER}'@'%';
FLUSH PRIVILEGES;
SQL

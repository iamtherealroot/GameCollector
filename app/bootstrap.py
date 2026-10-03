"""One startup job before Gunicorn workers and the scheduler.

Importing the app must not initialize the DB in this process until the
PostgreSQL advisory lock is held. Native SQLite tests keep auto-bootstrap.
"""
import os
os.environ['BIBO_SKIP_BOOTSTRAP'] = '1'


def main():
    from sqlalchemy import text
    from app.app import app, db, initialize_database

    with app.app_context():
        if db.engine.dialect.name == 'postgresql':
            with db.engine.connect() as connection:
                print('[init] Warte auf Datenbank-Initialisierungssperre …', flush=True)
                connection.execute(text('SELECT pg_advisory_lock(714502601)'))
                try:
                    print('[init] Initialisiere Schema und Grunddaten einmalig …', flush=True)
                    initialize_database()
                finally:
                    db.session.remove()
                    connection.execute(text('SELECT pg_advisory_unlock(714502601)'))
        else:
            initialize_database()
        db.engine.dispose()
    print('[init] Datenbank bereit. Webserver und Scheduler dürfen starten.', flush=True)


if __name__ == '__main__':
    main()

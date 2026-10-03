"""Explicit test-only UI and login policy; never enables production bypass."""
import os
from flask import request


def setup_test_environment(app, db):
    app.config['BIBO_TEST_MODE'] = os.environ.get('BIBO_TEST_MODE') == '1'
    app.config['BIBO_TEST_PASSWORDLESS'] = os.environ.get('BIBO_TEST_PASSWORDLESS') == '1'

    def passwordless():
        # A test flag alone is insufficient: require the isolated DB name and
        # explicit test-admin configuration. SQLite is allowed only in tests.
        test_database = (db.engine.dialect.name == 'postgresql' and db.engine.url.database == 'bibo_test')
        if app.testing and db.engine.dialect.name == 'sqlite':
            test_database = True
        return bool(app.config['BIBO_TEST_MODE'] and app.config['BIBO_TEST_PASSWORDLESS']
                    and os.environ.get('ADMIN_USERNAME') == 'test-admin' and test_database)

    @app.context_processor
    def context():
        return dict(bibo_test_mode=app.config['BIBO_TEST_MODE'], test_passwordless=passwordless(),
                    dashboard_home=request.endpoint == 'collector_home')
    return passwordless

"""Test-only approval ledger; no remote deployment or GitHub publication."""
import hashlib
import os
from pathlib import Path
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature

CHECKS = {'crud': 'Anlegen, Bearbeiten und Löschen geprüft', 'images': 'Bilder und Anhänge geprüft',
          'prices': 'Preise und Sammlungswerte geprüft', 'rights': 'Nutzerrechte und Datenschutz geprüft',
          'feedback': 'Feedback und Nachrichten geprüft', 'navigation': 'Navigation und Tutorial geprüft'}


def code_fingerprint(root):
    digest = hashlib.sha256()
    base = Path(root).parent
    files = list(Path(root).rglob('*')) + list((base/'scripts').rglob('*'))
    files += [base/name for name in ('install.sh', 'docker-compose.yml', 'docker-compose.test.yml', 'Dockerfile', 'Dockerfile.test', 'requirements.txt')]
    for file in sorted(files):
        relative = file.relative_to(base)
        if file.is_file() and not file.is_symlink() and 'uploads' not in relative.parts and '__pycache__' not in relative.parts and file.suffix not in {'.pyc', '.db', '.sqlite', '.zip'}:
            digest.update(str(relative).encode() + b'\0' + file.read_bytes() + b'\0')
    return digest.hexdigest()


def setup_test_release(app, db, version, utc_now, admin_required):
    bp = Blueprint('test_release', __name__)

    class TestReleaseApproval(db.Model):
        __tablename__ = 'test_release_approval'
        id = db.Column(db.Integer, primary_key=True)
        version = db.Column(db.String(32), nullable=False, index=True)
        fingerprint = db.Column(db.String(64), nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
        reviewer = db.Column(db.String(160), nullable=False)
        action = db.Column(db.String(16), nullable=False)
        notes = db.Column(db.Text, nullable=False, default='')
        created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def available():
        test_db = db.engine.dialect.name == 'postgresql' and db.engine.url.database == 'bibo_test'
        if app.testing and db.engine.dialect.name == 'sqlite':
            test_db = True
        return bool(app.config['BIBO_TEST_MODE'] and test_db)

    app.config['TU_RELEASE_AVAILABLE'] = available
    app.config['TU_APPROVAL_MODEL'] = TestReleaseApproval

    @app.context_processor
    def context():
        return {'tu_release_available': available() if current_user.is_authenticated and current_user.is_admin else False}

    @bp.after_request
    def no_cache(response):
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @bp.route('/admin/test-release', methods=['GET', 'POST'])
    @admin_required
    def index():
        if not available():
            abort(404)
        fingerprint = code_fingerprint(Path(app.root_path))
        signer = URLSafeTimedSerializer(app.secret_key, salt='bibo-test-release')
        binding = [current_user.id, session.get('_id'), version, fingerprint]
        if request.method == 'POST':
            try:
                supplied = signer.loads(request.form.get('token', ''), max_age=3600)
            except BadSignature:
                abort(400)
            if supplied != binding or request.form.get('version') != version:
                abort(400)
            action = request.form.get('action')
            notes = request.form.get('notes', '').strip()
            if action not in ('approve', 'revoke') or len(notes) > 2000:
                abort(400)
            if action == 'approve' and any(request.form.get(key) != '1' for key in CHECKS):
                flash('Bitte alle Prüfpunkte bewusst bestätigen.', 'danger')
                return redirect(url_for('test_release.index'))
            db.session.add(TestReleaseApproval(version=version, fingerprint=fingerprint, user_id=current_user.id,
                reviewer=current_user.display_name or current_user.username, action=action, notes=notes))
            db.session.commit()
            flash('Testfreigabe dokumentiert. Keine Produktion geändert und nichts veröffentlicht.' if action == 'approve'
                  else 'Testfreigabe zurückgenommen.', 'success')
            return redirect(url_for('test_release.index'))
        history = TestReleaseApproval.query.filter_by(version=version).order_by(TestReleaseApproval.id.desc()).limit(20).all()
        latest = history[0] if history else None
        approved = bool(latest and latest.action == 'approve' and latest.fingerprint == fingerprint)
        command = production_command(version, fingerprint) if approved else None
        return render_template('test_release.html', checks=CHECKS, history=history, approved=approved,
            fingerprint=fingerprint, token=signer.dumps(binding), command=command)

    app.register_blueprint(bp)


def production_command(version, fingerprint):
    # Version/fingerprint are application-owned, never user-controlled input.
    return f'''(
set -e
test "$(id -u)" = 0 || {{ echo "Als root auf dem Produktionsserver ausführen."; exit 1; }}
test -f /opt/gamecollector/.env
test -f /opt/gamecollector/docker-compose.yml
read -r -p "Absoluter Pfad zu Bibo-v{version}.zip: " PAKET
test -f "$PAKET"
ZIEL="$(mktemp -d /root/bibo-produktiv-XXXXXXXX)"
python3 - "$PAKET" "$ZIEL" <<'PY'
import ast, pathlib, stat, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    prefix = 'Bibo-v{version}'
    assert sum(i.file_size for i in z.infolist()) < 512*1024*1024
    for i in z.infolist():
        p = pathlib.PurePosixPath(i.filename)
        assert p.parts and p.parts[0] == prefix and not p.is_absolute() and '..' not in p.parts and '\\\\' not in i.filename
        assert not stat.S_ISLNK(i.external_attr >> 16)
        assert p.suffix not in {{'.py', '.pyc', '.so', '.pth'}} or (len(p.parts)>2 and p.parts[1] in {{'app', 'scripts'}}), 'Unerwarteter ausführbarer Paketinhalt'
    z.extractall(sys.argv[2])
root = pathlib.Path(sys.argv[2])/prefix/'app'
import hashlib
digest = hashlib.sha256()
base = root.parent
files = list(root.rglob('*')) + list((base/'scripts').rglob('*'))
files += [base/name for name in ('install.sh', 'docker-compose.yml', 'docker-compose.test.yml', 'Dockerfile', 'Dockerfile.test', 'requirements.txt')]
for file in sorted(files):
    relative = file.relative_to(base)
    if file.is_file() and not file.is_symlink() and 'uploads' not in relative.parts and '__pycache__' not in relative.parts and file.suffix not in {{'.pyc', '.db', '.sqlite', '.zip'}}:
        digest.update(str(relative).encode() + b'\\0' + file.read_bytes() + b'\\0')
assert digest.hexdigest() == '{fingerprint}', 'Paket entspricht nicht dem freigegebenen App-Stand'
PY
cd "$ZIEL/Bibo-v{version}"
BIBO_INSTALL_DIR=/opt/gamecollector BIBO_ALLOW_PRERELEASE=1 bash ./install.sh
)'''

from flask import Blueprint, abort, jsonify, request, session
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

def setup_release_news(app,db,version,utc_now):
    bp=Blueprint('release_news',__name__)
    class ReleaseAcknowledgement(db.Model):
        __tablename__='release_acknowledgement'
        user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),primary_key=True)
        version=db.Column(db.String(32),primary_key=True)
        acknowledged_at=db.Column(db.DateTime,nullable=False,default=utc_now)
    class TutorialAcknowledgement(db.Model):
        __tablename__='dashboard_tutorial_acknowledgement'
        user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),primary_key=True)
        acknowledged_at=db.Column(db.DateTime,nullable=False,default=utc_now)
    def token_for(purpose):
        # GET does not change the session cookie. Parallel page/API requests can
        # otherwise overwrite a newly generated session token before the POST.
        return URLSafeTimedSerializer(app.secret_key,salt='bibo-personal-notices').dumps(
            [current_user.id,session.get('_id'),purpose])
    def verify(data,purpose):
        if not isinstance(data,dict) or not isinstance(data.get('token'),str):abort(400)
        try:
            value=URLSafeTimedSerializer(app.secret_key,salt='bibo-personal-notices').loads(data['token'],max_age=3600)
        except (BadSignature,SignatureExpired):abort(400)
        if value != [current_user.id,session.get('_id'),purpose]:abort(400)
    @bp.after_request
    def no_cache(response):
        response.headers['Cache-Control']='private, no-store'
        return response
    @bp.route('/api/release-news')
    @login_required
    def current():
        shown=db.session.get(ReleaseAcknowledgement,(current_user.id,version)) is None
        return jsonify(show=shown,version=version,token=token_for('release:'+version) if shown else None,
            highlights=['Geführte Einführung direkt im Dashboard mit hervorgehobenen Bereichen.',
                        'Warmes, farbiges Bücherregal und verständliche Leer-/Top-10-Hinweise.',
                        'Gekennzeichnete Testumgebung: test-admin ohne Passwort und Bash-Starter.',
                        'Docker-Start korrigiert: Initialisierung vor Webserver und Scheduler.',
                        'Robustere Bestätigung des „Was ist neu?“-Fensters.',
                        'Einführungstutorial mit Überspringen und erneutem Start unter Hilfe.',
                        'Privates Feedback mit Bildern, Antworten und Admin-Verwaltung.',
                        'Freiwillige globale Top 10 je Bereich mit persönlichem Schalter.',
                        'Docker-Testumgebung mit Kopierbefehl für Datenbank und Bilder.'])
    @bp.route('/api/release-news/ack',methods=['POST'])
    @login_required
    def acknowledge():
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict):abort(400)
        if data.get('version')!=version:abort(400)
        verify(data,'release:'+version)
        key=(current_user.id,version)
        if db.session.get(ReleaseAcknowledgement,key) is None:
            db.session.add(ReleaseAcknowledgement(user_id=current_user.id,version=version))
            try:db.session.commit()
            except IntegrityError:
                db.session.rollback()
                if db.session.get(ReleaseAcknowledgement,key) is None:raise
        return jsonify(ok=True)
    @bp.route('/api/tutorial')
    @login_required
    def tutorial():
        groups=app.config['NAVIGATION_GROUPS']()
        steps=[dict(title='Dein Dashboard',description='Das bunte Bücherregal bringt dich jederzeit zu dieser Übersicht zurück.',
                    selector='.bibo-nav-home, .bibo-quickbar > a[aria-label="Startseite"]'),
               dict(title='Suchen statt durchklicken',description='Hier findest du Titel, EAN / UPC und Geräte. Auf dem Desktop öffnet Strg+K die Suche.',selector='[data-tour="search"]'),
               dict(title='Aktive Sammlung & Konto',description='Öffne dein Kontomenü, um die aktive Sammlung zu wechseln. Hier findest du auch dein Profil und die Abmeldung.',selector='[data-tour="account"] > summary'),
               dict(title='Deine Sammlungsbereiche',description='Diese Kacheln öffnen Games, Filme, Serien und deine eigenen Kategorien. Jede Kachel zeigt Bestand und Wert; leere Bereiche helfen beim ersten Objekt.',selector='.collector-module-grid .collector-module:first-child'),
               dict(title='Gesamter Sammlungswert',description='Der Wert berücksichtigt deine Sammlungsobjekte einschließlich Hardware und Zubehör. Fixierte Werte haben Vorrang, danach automatische Bewertungen und eigene Schätzungen.',selector='.collector-total')]
        if any(g['title']=='Hinzufügen' for g in groups):
            steps.insert(3,dict(title='Ein neues Objekt erfassen',description='Starte mit „Objekt hinzufügen“ oder nutze die Kamera zum Barcode-Scan. Vorhandene EANs können als weiteres Exemplar erfasst werden.',selector='.collector-hero-actions > a:first-child'))
        for index,group in enumerate(groups):
            steps.append(dict(title=group['title'],description=group['description'],
                selector=f'.bibo-nav [data-tour-group="{index}"] > summary, .bibo-mobile-panel [data-tour-group="{index}"] > summary',
                menu=True,items=[dict(title=i['title'],description=i['description']) for i in group['items'][:4]]))
        return jsonify(show=db.session.get(TutorialAcknowledgement,current_user.id) is None,
            token=token_for('tutorial'),steps=steps)
    @bp.route('/api/tutorial/ack',methods=['POST'])
    @login_required
    def tutorial_ack():
        verify(request.get_json(silent=True),'tutorial')
        if db.session.get(TutorialAcknowledgement,current_user.id) is None:
            db.session.add(TutorialAcknowledgement(user_id=current_user.id))
            try:db.session.commit()
            except IntegrityError:
                db.session.rollback()
                if db.session.get(TutorialAcknowledgement,current_user.id) is None:raise
        return jsonify(ok=True)
    app.register_blueprint(bp)
    return ReleaseAcknowledgement

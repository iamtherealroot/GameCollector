import json
import re
from flask import Blueprint, abort, jsonify, request, session, render_template, redirect, url_for, flash
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

def setup_release_news(app,db,version,utc_now):
    from .release_catalog import RELEASES
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
    class TutorialPreference(db.Model):
        __tablename__='tutorial_preference'
        user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),primary_key=True)
        disabled=db.Column(db.Boolean,nullable=False,default=False)
    app.config['TUTORIAL_PREFERENCE_MODEL']=TutorialPreference
    class ReleaseLoginState(db.Model):
        __tablename__='release_login_state'
        user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),primary_key=True)
        last_version=db.Column(db.String(32))
        last_login_at=db.Column(db.DateTime)
        previous_version=db.Column(db.String(32))
        previous_login_at=db.Column(db.DateTime)
        pending=db.Column(db.Text,nullable=False,default='[]')
    app.config['RELEASE_LOGIN_MODEL']=ReleaseLoginState
    def version_key(value):
        match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?',value or '')
        if not match:return (-1,-1,-1,0,0)
        return tuple(map(int,match.groups()[:3]))+(1 if match[4] is None else 0,int(match[4] or 0))
    def baseline(user_id):
        acknowledgements=ReleaseAcknowledgement.query.filter_by(user_id=user_id).all()
        known=[row.version for row in acknowledgements if version_key(row.version)<=version_key(version)]
        return max(known,key=version_key) if known else None
    def changed_after(before):
        if before is None:return [version]
        return [v for v,_,_ in RELEASES if version_key(before)<version_key(v)<=version_key(version)]
    def pending_versions(state):
        try:
            data=json.loads(state.pending) if state else []
            return [v for v in data if isinstance(v,str)] if isinstance(data,list) else []
        except (ValueError,TypeError):return []
    def updates():
        state=db.session.get(ReleaseLoginState,current_user.id)
        before=state.previous_version if state else baseline(current_user.id)
        versions=set(pending_versions(state)+changed_after(state.last_version if state else before))
        seen={r.version for r in ReleaseAcknowledgement.query.filter_by(user_id=current_user.id).all()}
        rows=[dict(version=v,title=title,description=description) for v,title,description in RELEASES
              if v in versions and v not in seen and version_key(v)<=version_key(version)]
        rows.sort(key=lambda row:version_key(row['version']))
        return dict(releases=rows,since_version=before,
                    since_login=state.previous_login_at.isoformat() if state and state.previous_login_at else None)
    def record_login(user_id):
        state=db.session.get(ReleaseLoginState,user_id)
        if state is None:
            state=ReleaseLoginState(user_id=user_id,pending='[]')
            db.session.add(state)
        before=state.last_version or baseline(user_id)
        state.pending=json.dumps(sorted(set(pending_versions(state)+changed_after(before)),key=version_key))
        state.previous_version=before
        state.previous_login_at=state.last_login_at
        state.last_version=version
        state.last_login_at=utc_now()
        db.session.commit()
    app.config['RELEASE_RECORD_LOGIN']=record_login
    app.config['RELEASE_UPDATES']=updates
    def save_preference(disabled):
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        insert=pg_insert if db.engine.dialect.name=='postgresql' else sqlite_insert
        statement=insert(TutorialPreference).values(user_id=current_user.id,disabled=disabled)
        db.session.execute(statement.on_conflict_do_update(index_elements=['user_id'],set_={'disabled':disabled}))
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
        missed=updates()
        shown=bool(missed['releases'])
        if shown:
            return jsonify(show=True,version=version,token=token_for('release:'+version),
                updates=missed['releases'],since_version=missed['since_version'],since_login=missed['since_login'],
                highlights=[f"Bibo {row['version']} · {row['title']}: {row['description']}" for row in missed['releases']])
        return jsonify(show=shown,version=version,token=token_for('release:'+version) if shown else None,
            highlights=['Meldungen für dich abschließen, ohne die Admin-Aufgabe zu erledigen.',
                        'Eigene offene Meldungen und Admin-Aufgaben mit getrennten Übersichten.',
                        'Tutorial dauerhaft für dein Konto ausschalten oder bewusst wieder starten.',
                        'Automatische, korrigierbare Meldungseinstufung nach Kategorie und Dringlichkeit.',
                        'Dauerhafter Admin-Zähler für offene Meldungen und persönlicher Nachrichteneingang.',
                        'Öffentliche Antworten und Statusänderungen erzeugen private Nutzer-Nachrichten.',
                        'TU-Testfreigabe mit Prüfliste und geprüftem Produktionsbefehl – kein automatischer Transfer.',
                        'Einheitliche Versionierung: Hauptversion.Nebenversion.Korrektur und rc-Prüfstände.',
                        'Geführte Einführung direkt im Dashboard mit hervorgehobenen Bereichen.',
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
        versions={version,*[row['version'] for row in updates()['releases']]}
        with db.session.no_autoflush:
            for release_version in versions:
                if db.session.get(ReleaseAcknowledgement,(current_user.id,release_version)) is None:
                    db.session.add(ReleaseAcknowledgement(user_id=current_user.id,version=release_version))
        try:db.session.commit()
        except IntegrityError:
            db.session.rollback()
            # A parallel confirmation may have stored only a subset; preserve
            # every missed entry rather than silently losing older updates.
            for release_version in versions:
                if db.session.get(ReleaseAcknowledgement,(current_user.id,release_version)) is None:
                    db.session.add(ReleaseAcknowledgement(user_id=current_user.id,version=release_version))
            db.session.commit()
        return jsonify(ok=True)
    @bp.route('/api/tutorial')
    @login_required
    def tutorial():
        groups=app.config['NAVIGATION_GROUPS']()
        cards=app.config.get('DASHBOARD_STYLE_FOR_USER',lambda _: 'shelf')(current_user.id)=='cards'
        steps=[dict(title='Dein Dashboard',description='Das bunte Bücherregal bringt dich jederzeit zu dieser Übersicht zurück.',
                    selector='.bibo-nav-home, .bibo-quickbar > a[aria-label="Startseite"]'),
               dict(title='Suchen statt durchklicken',description='Hier findest du Titel, EAN / UPC und Geräte. Auf dem Desktop öffnet Strg+K die Suche.',selector='[data-tour="search"]'),
               dict(title='Aktive Sammlung & Konto',description='Öffne dein Kontomenü, um die aktive Sammlung zu wechseln. Hier findest du auch dein Profil und die Abmeldung.',selector='[data-tour="account"] > summary'),
               dict(title='Deine Sammlungskacheln' if cards else 'Dein Sammlungsregal',description=('Die Kacheln öffnen deine Sammlungskategorien und zeigen Bestand und Wert. In deinen Kontoeinstellungen wechselst du jederzeit zum Holzregal.' if cards else 'Beschriftete Rücken öffnen direkt das Medium. Der letzte, unbeschriftete Rücken und das Schild unter dem Fach öffnen die Kategorie. In deinen Kontoeinstellungen wechselst du zu Kacheln. Ein freies Fach führt zum Anlegen einer neuen Kategorie.'),selector='.collector-module-grid .collector-module:first-child'),
               dict(title='Gesamter Sammlungswert',description='Der Wert berücksichtigt deine Sammlungsobjekte einschließlich Hardware und Zubehör. Fixierte Werte haben Vorrang, danach automatische Bewertungen und eigene Schätzungen.',selector='.collector-total')]
        if any(g['title']=='Hinzufügen' for g in groups):
            steps.insert(3,dict(title='Ein neues Objekt erfassen',description='Starte mit „Objekt hinzufügen“ oder nutze die Kamera zum Barcode-Scan. Vorhandene EANs können als weiteres Exemplar erfasst werden.',selector='.collector-hero-actions > a:first-child'))
        for index,group in enumerate(groups):
            steps.append(dict(title=group['title'],description=group['description'],
                selector=f'.bibo-nav [data-tour-group="{index}"] > summary, .bibo-mobile-panel [data-tour-group="{index}"] > summary',
                menu=True,items=[dict(title=i['title'],description=i['description']) for i in group['items'][:4]]))
        preference=db.session.get(TutorialPreference,current_user.id)
        disabled=bool(preference and preference.disabled)
        return jsonify(show=not disabled and db.session.get(TutorialAcknowledgement,current_user.id) is None, disabled=disabled,
            token=token_for('tutorial'),steps=steps)
    @bp.route('/api/tutorial/ack',methods=['POST'])
    @login_required
    def tutorial_ack():
        data=request.get_json(silent=True)
        verify(data,'tutorial')
        if 'disabled' in data and not isinstance(data['disabled'],bool):abort(400)
        if db.session.get(TutorialAcknowledgement,current_user.id) is None:
            db.session.add(TutorialAcknowledgement(user_id=current_user.id))
            try:db.session.commit()
            except IntegrityError:
                db.session.rollback()
                if db.session.get(TutorialAcknowledgement,current_user.id) is None:raise
        if data.get('disabled') is True:save_preference(True)
        db.session.commit()
        return jsonify(ok=True)
    @bp.route('/help/tutorial-settings',methods=['GET','POST'])
    @login_required
    def tutorial_settings():
        preference=db.session.get(TutorialPreference,current_user.id)
        if request.method=='POST':
            verify({'token':request.form.get('token')},'tutorial-settings')
            disabled=request.form.get('enabled')!='1'
            save_preference(disabled)
            if not disabled:
                acknowledgement=db.session.get(TutorialAcknowledgement,current_user.id)
                if acknowledgement:db.session.delete(acknowledgement)
            db.session.commit()
            flash('Tutorial dauerhaft ausgeschaltet.' if disabled else 'Tutorial wieder aktiviert.', 'success')
            return redirect(url_for('release_news.tutorial_settings'))
        return render_template('tutorial_settings.html',disabled=bool(preference and preference.disabled),
                               token=token_for('tutorial-settings'))
    app.register_blueprint(bp)
    return ReleaseAcknowledgement

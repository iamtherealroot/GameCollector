"""Opt-out leaderboards expose limited summaries with neutral default aliases."""
import math
import secrets
from types import SimpleNamespace
from urllib.parse import urlsplit
from .price_quality import valuation_warnings
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

CATEGORIES={'games':'Games','hardware':'Konsolen & Hardware','accessories':'Zubehör',
            'movies':'Filme','tv':'Serien','books':'Bücher','music':'Musik','cards':'Sammelkarten','custom':'Weitere Sammlungen'}

def setup_top10(app,db,m):
    bp=Blueprint('top10',__name__)
    class Top10Consent(db.Model):
        __tablename__='top10_consent'
        collection_id=db.Column(db.Integer,db.ForeignKey('collection_space.id',ondelete='CASCADE'),primary_key=True)
        enabled=db.Column(db.Boolean,nullable=False,default=True)
        collection_alias=db.Column(db.String(80),nullable=False,default='')
        collector_alias=db.Column(db.String(80),nullable=False,default='')
        updated_at=db.Column(db.DateTime,nullable=False,default=m['utc_now'])
    class Top10UserPreference(db.Model):
        __tablename__='top10_user_preference'
        user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),primary_key=True)
        enabled=db.Column(db.Boolean,nullable=False,default=True)

    def available():
        return m['CollectionSpace'].query.count()>1

    def user_enabled():
        pref=db.session.get(Top10UserPreference,current_user.id)
        return available() and (pref is None or pref.enabled)

    def shared_spaces():
        return (db.session.query(m['CollectionSpace'],Top10Consent)
                .outerjoin(Top10Consent,Top10Consent.collection_id==m['CollectionSpace'].id)
                .filter(db.or_(Top10Consent.collection_id.is_(None),Top10Consent.enabled.is_(True))).all())

    def public_share(space,consent):
        return SimpleNamespace(enabled=True if consent is None else consent.enabled,
            collection_alias=(consent.collection_alias if consent else '') or f'Sammlung {space.id}',
            collector_alias=(consent.collector_alias if consent else '') or f'Sammler {space.id}')

    def owner_names(space):
        # Inventory user_id is normally a technical collection account, not a
        # person. Only use administrators actually assigned to this collection.
        def personal(user):
            return not user.is_system and user.username.casefold() not in {'admin','test-admin'}
        if space.owner and personal(space.owner):
            return [space.owner.username]
        managers=(m['User'].query.join(m['CollectionPermission'],m['CollectionPermission'].user_id==m['User'].id)
            .filter(m['CollectionPermission'].collection_id==space.id,
                    m['CollectionPermission'].role=='manager',m['User'].is_system.is_(False))
            .order_by(m['User'].username,m['User'].id).all())
        managers=[user for user in managers if personal(user)]
        admins=[user for user in managers if user.is_admin or user.role=='admin']
        return [user.username for user in (admins or managers)]

    def cover_url(raw):
        value=str(raw or '').strip()
        if not value or any(ord(c)<32 for c in value):return None
        try:parsed=urlsplit(value)
        except ValueError:return None
        if parsed.scheme in {'http','https'} and parsed.hostname and not parsed.username and not parsed.password:
            return value
        if value.startswith('/static/') and not parsed.scheme and not parsed.netloc and '..' not in parsed.path.split('/'):
            return value
        return None

    @bp.app_context_processor
    def context():
        if not current_user.is_authenticated:return {}
        ready=available();enabled=user_enabled()
        participants=len(shared_spaces()) if ready else 0
        if not ready:message='Noch nicht verfügbar: Es müssen mindestens zwei Sammlungsdatenbanken in dieser Installation angelegt sein.'
        elif not enabled:message='Deine globale Top-10-Ansicht ist deaktiviert. Ansicht und Teilnahme deiner Sammlung lassen sich getrennt verwalten.'
        elif not participants:message='Anzeige aktiviert, aber noch keine Sammlung hat ihre Teilnahme freigegeben.'
        else:message=f'Anzeige aktiviert · {participants} teilnehmende Sammlungen. Teilnahme ist standardmäßig aktiv und jederzeit abwählbar.'
        return dict(top10_available=ready,top10_user_enabled=enabled,top10_status_message=message)

    @bp.route('/top10/preferences',methods=['GET','POST'])
    @login_required
    def preferences():
        key=f'top10-preference-token-{current_user.id}'
        if key not in session:session[key]=secrets.token_urlsafe(32)
        pref=db.session.get(Top10UserPreference,current_user.id)
        if request.method=='POST':
            supplied=request.form.get('top10_token','')
            if not supplied or not secrets.compare_digest(supplied,session[key]):abort(400)
            enabled=request.form.get('enabled')=='1'
            if enabled and not available():abort(400,'Mindestens zwei Sammlungsdatenbanken erforderlich.')
            if not pref:pref=Top10UserPreference(user_id=current_user.id);db.session.add(pref)
            pref.enabled=enabled;db.session.commit()
            return redirect(url_for('top10.index' if enabled else 'top10.preferences'))
        return render_template('top10_preferences.html',pref=pref,top10_token=session[key])

    @bp.after_request
    def private_response(response):
        response.headers['Cache-Control']='private, no-store'
        return response

    def manager_space():
        space=m['active_collection_space']()
        if not space or not m['collection_capability']('manage_users'):
            abort(403)
        return space

    def form_token(space):
        key=f'top10-token-{current_user.id}-{space.id}'
        if key not in session:session[key]=secrets.token_urlsafe(32)
        return session[key]

    @bp.route('/top10/settings',methods=['GET','POST'])
    @login_required
    def settings():
        space=manager_space()
        consent=db.session.get(Top10Consent,space.id)
        if request.method=='POST':
            supplied=request.form.get('top10_token','')
            expected=session.get(f'top10-token-{current_user.id}-{space.id}','')
            if not supplied or not expected or not secrets.compare_digest(supplied,expected):abort(400)
            enabled=request.form.get('enabled')=='1'
            if enabled and not available():abort(400,'Mindestens zwei Sammlungsdatenbanken erforderlich.')
            collection_alias=request.form.get('collection_alias','').strip()
            collector_alias=request.form.get('collector_alias','').strip()
            if enabled and (not 2<=len(collection_alias)<=80 or not 2<=len(collector_alias)<=80):
                flash('Bitte zwei öffentliche Anzeigenamen mit je 2–80 Zeichen eingeben.','danger')
                return render_template('top10_settings.html',space=space,consent=request.form,top10_token=form_token(space)),400
            if not consent:consent=Top10Consent(collection_id=space.id);db.session.add(consent)
            consent.enabled=enabled
            consent.collection_alias=collection_alias[:80] if enabled else ''
            consent.collector_alias=collector_alias[:80] if enabled else ''
            consent.updated_at=m['utc_now']()
            db.session.commit()
            flash('Teilnahme gespeichert.' if enabled else 'Teilnahme beendet. Die Sammlung erscheint nicht mehr in den globalen Top 10.','success')
            return redirect(url_for('top10.index'))
        return render_template('top10_settings.html',space=space,consent=public_share(space,consent),top10_token=form_token(space))

    @bp.route('/top10')
    @login_required
    def index():
        category=request.args.get('category','games')
        if category not in CATEGORIES:abort(404)
        if not user_enabled():
            return render_template('top10_preferences.html',pref=db.session.get(Top10UserPreference,current_user.id),top10_token=None)
        owners={}
        for space,consent in shared_spaces():
            share=public_share(space,consent)
            share.owner_names=owner_names(space)
            owners[space.owner_user_id]=share
        rows=[]
        if owners:
            if category in {'games','hardware','accessories'}:
                Model=m[{'games':'CollectionItem','hardware':'HardwareItem','accessories':'AccessoryItem'}[category]]
                value=db.func.coalesce(Model.fixed_value_eur,Model.auto_value_eur,Model.estimated_value)
                query=Model.query.filter(Model.user_id.in_(owners),Model.status=='owned',value>0)
                if category=='games':query=query.filter(Model.ownership_format=='physical').options(joinedload(Model.game))
                if category=='hardware':query=query.options(joinedload(Model.model))
                if category=='accessories':query=query.filter(Model.included_in_parent_value.is_(False))
                candidates=query.order_by(value.desc(),Model.id).yield_per(100)
            else:
                Model=m['CollectorItem']
                # Generic status/physical flags live in JSON; filter them before limiting.
                value=db.func.coalesce(Model.fixed_value_eur,Model.auto_value_eur,Model.estimated_value_eur)
                candidates=Model.query.filter(Model.user_id.in_(owners),Model.category==category,value>0).order_by(value.desc(),Model.id).yield_per(100)
            for item in candidates:
                if category=='games':
                    cover=cover_url(item.game.cover_url)
                    title=item.game.title;variant=' · '.join(str(v) for v in (item.game.console.name,item.game.region,item.game.edition) if v)
                    amount=m['effective_value'](item);condition=f'{item.media_condition}/10';complete=item.completeness
                elif category=='hardware':
                    cover=cover_url(item.model.reference_image)
                    title=item.model.name;variant=' · '.join(str(v) for v in (item.model.model_number,item.model.region,item.model.edition) if v)
                    amount=m['effective_hardware_value'](item);condition=f'{item.condition}/10';complete=item.completeness
                elif category=='accessories':
                    cover=cover_url(item.reference_image)
                    title=item.name;variant=item.model_number or item.category
                    amount=m['effective_accessory_value'](item);condition=f'{item.condition}/10';complete='Mit Verpackung' if item.boxed else 'Lose'
                else:
                    cover=cover_url(item.cover_url)
                    meta=m['collector_metadata'](item)
                    if meta.get('status','owned')!='owned' or meta.get('ownership_format','physical')=='digital' or str(item.media_type or '').lower()=='digital':continue
                    title=item.title;variant=' · '.join(str(v) for v in (item.media_type,item.edition,item.card_variant) if v)
                    amount=m['collector_effective_value'](item);condition=item.condition or 'Nicht angegeben';complete=item.completeness or 'Nicht angegeben'
                if amount is None or not math.isfinite(float(amount)) or amount<=0:continue
                # Keep every exemplar. Equal-price entries share their rank;
                # include ties at position 10 instead of dropping an owner.
                if len(rows)>=10 and amount<rows[-1]['value']:break
                rank=rows[-1]['rank'] if rows and amount==rows[-1]['value'] else len(rows)+1
                share=owners[item.user_id]
                fixed=item.fixed_value_eur is not None
                automatic=item.auto_value_eur is not None
                rows.append(dict(title=title,variant=variant,value=amount,condition=condition,completeness=complete,
                    rank=rank,cover_url=cover,owner_names=share.owner_names,warnings=valuation_warnings(item,m['utc_now']()),
                    collection=share.collection_alias,collector=share.collector_alias,
                    source='Manuell fixiert' if fixed else (item.auto_value_source or 'Automatischer Marktwert') if automatic else 'Eigene Schätzung',
                    updated_at=item.fixed_value_at if fixed else item.auto_value_updated_at if automatic else None))
        return render_template('top10.html',rows=rows,category=category,categories=CATEGORIES,participants=len(owners))
    app.register_blueprint(bp)
    return Top10Consent,Top10UserPreference,user_enabled

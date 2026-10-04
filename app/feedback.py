"""Account-scoped feedback, independent of collection permissions."""
import io
import os
import re
import secrets
import warnings
from datetime import timedelta
from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for, send_file
from flask_login import current_user, login_required
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import case

STATUSES = {'submitted': 'Eingereicht', 'review': 'In Prüfung', 'planned': 'Geplant',
            'working': 'In Arbeit', 'done': 'Erledigt', 'rejected': 'Abgelehnt', 'duplicate': 'Duplikat'}
PRIORITIES = {'normal': 'Normal', 'low': 'Niedrig', 'high': 'Hoch', 'urgent': 'Kritisch'}
CATEGORIES = {'bug': 'Fehler', 'quality': 'Qualitätsverbesserung', 'feature': 'Neue Funktion',
              'change': 'Änderung bestehender Funktionen', 'unclear': 'Unklar'}
CLOSED = ('done', 'rejected', 'duplicate')


def classify_feedback(title, description, kind):
    """Explainable local suggestion, never an automatic workflow decision."""
    text = (title + ' ' + description).casefold()
    critical = ('datenverlust', 'daten verloren', 'sicherheitslücke', 'fremde daten',
                'unberechtigter zugriff', 'alle daten gelöscht')
    if kind == 'bug':
        category = 'bug'
    elif any(word in text for word in ('neue funktion', 'neues feature', 'funktion hinzufügen')):
        category = 'feature'
    elif any(word in text for word in ('qualität', 'übersichtlich', 'verständlicher', 'layout', 'symbol', 'menü', 'darstellung')):
        category = 'quality'
    elif kind == 'improvement':
        category = 'change'
    else:
        category = 'unclear'
    hit = next((word for word in critical if word in text and
                not re.search(r'(?:kein\w*|ohne|nicht)\s+(?:\w+\s+){0,2}' + re.escape(word), text)), None)
    if hit and category == 'bug':
        return category, 'urgent', f'Kritischer Hinweis im Text: „{hit}“. Bitte manuell prüfen.'
    if kind == 'bug' and any(word in text for word in ('nicht anmelden', 'login geht nicht', 'absturz', 'nicht erreichbar')):
        return category, 'high', 'Hinweis auf blockierte Anmeldung, Ausfall oder Absturz.'
    return category, 'normal', 'Vorschlag aus Meldungstyp und Text; keine automatische Statusänderung.'
KINDS = {'bug': 'Fehler', 'improvement': 'Verbesserung'}
AREAS = ['Allgemein', 'Navigation', 'Spiele', 'Hardware & Zubehör', 'Weitere Sammlungen',
         'Preise & Bewertungen', 'Scanner & Import', 'Nutzer & Rechte']


def setup_feedback(app, db, User, utc_now, version, admin_required):
    bp = Blueprint('feedback', __name__)

    class FeedbackTicket(db.Model):
        __tablename__ = 'feedback_ticket'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
        title = db.Column(db.String(160), nullable=False)
        description = db.Column(db.Text, nullable=False)
        kind = db.Column(db.String(20), nullable=False)
        area = db.Column(db.String(80), nullable=False)
        app_version = db.Column(db.String(32), nullable=False)
        status = db.Column(db.String(20), nullable=False, default='submitted', index=True)
        priority = db.Column(db.String(20), nullable=False, default='normal')
        target_version = db.Column(db.String(32), default='')
        created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
        updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)
        revision = db.Column(db.Integer, nullable=False, default=1)
        __mapper_args__ = {'version_id_col': revision}
        user = db.relationship(User)

    class FeedbackMessage(db.Model):
        __tablename__ = 'feedback_message'
        id = db.Column(db.Integer, primary_key=True)
        ticket_id = db.Column(db.Integer, db.ForeignKey('feedback_ticket.id'), nullable=False, index=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
        body = db.Column(db.Text, nullable=False)
        internal = db.Column(db.Boolean, nullable=False, default=False)
        created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
        user = db.relationship(User)

    class FeedbackAttachment(db.Model):
        __tablename__ = 'feedback_attachment'
        id = db.Column(db.Integer, primary_key=True)
        ticket_id = db.Column(db.Integer, db.ForeignKey('feedback_ticket.id'), nullable=False, index=True)
        message_id = db.Column(db.Integer, db.ForeignKey('feedback_message.id'))
        storage_name = db.Column(db.String(64), nullable=False, unique=True)
        internal = db.Column(db.Boolean, nullable=False, default=False)
        created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    class FeedbackTriage(db.Model):
        __tablename__ = 'feedback_triage'
        ticket_id = db.Column(db.Integer, db.ForeignKey('feedback_ticket.id'), primary_key=True)
        category = db.Column(db.String(20), nullable=False)
        suggested_category = db.Column(db.String(20), nullable=False)
        suggested_priority = db.Column(db.String(20), nullable=False)
        reason = db.Column(db.Text, nullable=False)
        overridden = db.Column(db.Boolean, nullable=False, default=False)

    class FeedbackNotification(db.Model):
        __tablename__ = 'feedback_notification'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
        message_id = db.Column(db.Integer, db.ForeignKey('feedback_message.id'), nullable=False)
        created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
        read_at = db.Column(db.DateTime)
        message = db.relationship(FeedbackMessage)
        __table_args__ = (db.UniqueConstraint('user_id', 'message_id'),)

    FeedbackTicket.triage = db.relationship(FeedbackTriage, uselist=False)

    class FeedbackUserCompletion(db.Model):
        __tablename__ = 'feedback_user_completion'
        ticket_id = db.Column(db.Integer, db.ForeignKey('feedback_ticket.id'), primary_key=True)
        completed_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    FeedbackTicket.user_completion = db.relationship(FeedbackUserCompletion, uselist=False)
    app.config['FEEDBACK_COMPLETION_MODEL'] = FeedbackUserCompletion

    def own_open_query():
        return FeedbackTicket.query.filter_by(user_id=current_user.id).outerjoin(FeedbackUserCompletion).filter(
            ~FeedbackTicket.status.in_(CLOSED), FeedbackUserCompletion.ticket_id.is_(None))

    def triage_ticket(ticket, assign_priority=False):
        category, priority, reason = classify_feedback(ticket.title, ticket.description, ticket.kind)
        row = FeedbackTriage(ticket_id=ticket.id, category=category, suggested_category=category,
                             suggested_priority=priority, reason=reason,
                             overridden=not assign_priority and ticket.priority != priority)
        db.session.add(row)
        if assign_priority:
            ticket.priority = priority
        return row

    def backfill():
        # Existing admin priorities are preserved. Historical answers are not
        # replayed as a flood of new notifications.
        for ticket in FeedbackTicket.query.outerjoin(FeedbackTriage).filter(FeedbackTriage.ticket_id.is_(None)).all():
            triage_ticket(ticket)
        db.session.commit()

    app.config['FEEDBACK_BACKFILL'] = backfill
    app.config['FEEDBACK_NOTIFICATION_MODEL'] = FeedbackNotification
    app.config['FEEDBACK_TRIAGE_MODEL'] = FeedbackTriage

    def notify_owner(ticket, message):
        if ticket.user_id and ticket.user_id != current_user.id and not message.internal:
            db.session.flush()
            db.session.add(FeedbackNotification(user_id=ticket.user_id, message_id=message.id))

    def token(action):
        key = f'feedback-token-{current_user.id}-{action}'
        if key not in session:
            session[key] = secrets.token_urlsafe(32)
        return session[key]

    def check_token(action):
        supplied = request.form.get('feedback_token', '')
        expected = session.get(f'feedback-token-{current_user.id}-{action}', '')
        if not supplied or not expected or not secrets.compare_digest(supplied, expected):
            abort(400, 'Ungültige Formularbestätigung. Bitte Seite neu laden.')

    def ticket_for_user(ticket_id):
        ticket = db.session.get(FeedbackTicket, ticket_id)
        if not ticket or (not current_user.is_admin and ticket.user_id != current_user.id):
            abort(404)
        return ticket

    def upload_root():
        return Path(app.config.get('FEEDBACK_UPLOAD_DIR') or os.environ.get('FEEDBACK_UPLOAD_DIR')
                    or Path(app.instance_path) / 'feedback-uploads')

    def save_images(ticket, message, internal, written):
        uploads = [f for f in request.files.getlist('images') if f.filename]
        total = FeedbackAttachment.query.filter_by(ticket_id=ticket.id).count()
        if len(uploads) > 4 or total + len(uploads) > 20:
            raise ValueError('Maximal 4 Bilder pro Beitrag und 20 Bilder pro Meldung.')
        for upload in uploads:
            raw = upload.stream.read(5 * 1024 * 1024 + 1)
            if len(raw) > 5 * 1024 * 1024:
                raise ValueError('Ein Bild darf maximal 5 MB groß sein.')
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(raw)) as source:
                        if source.format not in {'PNG', 'JPEG', 'WEBP'} or source.width * source.height > 12_000_000:
                            raise ValueError('Nur PNG, JPEG oder WebP bis 12 Megapixel sind erlaubt.')
                        source.load()
                        image = ImageOps.exif_transpose(source).convert('RGB')
                        image.thumbnail((2400, 2400))
                        # Fresh image strips EXIF and other embedded metadata.
                        clean = Image.new('RGB', image.size)
                        clean.paste(image)
                        output = io.BytesIO()
                        clean.save(output, format='JPEG', quality=88)
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise ValueError('Das Bild ist ungültig oder zu groß.') from None
            root = upload_root()
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            name = secrets.token_hex(24) + '.jpg'
            destination = root / name
            with destination.open('xb') as target:
                written.append(destination)
                target.write(output.getvalue())
            destination.chmod(0o600)
            db.session.add(FeedbackAttachment(ticket_id=ticket.id, message_id=message.id if message else None,
                                              storage_name=name, internal=internal))

    def rollback_files(written):
        db.session.rollback()
        for path in written:
            path.unlink(missing_ok=True)

    def commit_or_conflict(written):
        try:
            db.session.commit()
        except StaleDataError:
            rollback_files(written)
            abort(409, 'Die Meldung wurde inzwischen geändert. Bitte neu laden.')
        except Exception:
            rollback_files(written)
            raise

    @bp.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @bp.app_context_processor
    def feedback_context():
        return dict(feedback_statuses=STATUSES, feedback_priorities=PRIORITIES,
                    feedback_kinds=KINDS, feedback_areas=AREAS, feedback_categories=CATEGORIES,
                    feedback_open_count=FeedbackTicket.query.filter(~FeedbackTicket.status.in_(CLOSED)).count()
                        if current_user.is_authenticated and current_user.is_admin else 0,
                    feedback_own_open_count=own_open_query().count() if current_user.is_authenticated else 0,
                    feedback_unread_count=FeedbackNotification.query.filter_by(user_id=current_user.id, read_at=None).count()
                        if current_user.is_authenticated else 0)

    @bp.route('/feedback/messages', methods=['GET', 'POST'])
    @login_required
    def inbox():
        if request.method == 'POST':
            check_token('inbox')
            notification = db.session.get(FeedbackNotification, request.form.get('notification_id', type=int))
            if not notification or notification.user_id != current_user.id:
                abort(404)
            if not notification.read_at:
                notification.read_at = utc_now()
                db.session.commit()
            return redirect(url_for('feedback.inbox'))
        page = FeedbackNotification.query.filter_by(user_id=current_user.id).order_by(
            FeedbackNotification.read_at.is_not(None), FeedbackNotification.id.desc()).paginate(
                page=max(1, request.args.get('page', 1, type=int) or 1), per_page=25, error_out=False)
        return render_template('feedback_inbox.html', pagination=page, feedback_token=token('inbox'))

    def list_page(admin=False):
        query = FeedbackTicket.query if admin else FeedbackTicket.query.filter_by(user_id=current_user.id)
        status = request.args.get('status', '')
        kind = request.args.get('kind', '')
        category = request.args.get('category', '')
        priority = request.args.get('priority', '')
        if request.args.get('open') == '1':
            query = query.filter(~FeedbackTicket.status.in_(CLOSED)) if admin else own_open_query()
        if category in CATEGORIES:
            query = query.join(FeedbackTriage).filter(FeedbackTriage.category == category)
        if priority in PRIORITIES and admin:
            query = query.filter(FeedbackTicket.priority == priority)
        search = request.args.get('q', '').strip()[:160]
        if status in STATUSES:
            query = query.filter(FeedbackTicket.status == status)
        if kind in KINDS:
            query = query.filter(FeedbackTicket.kind == kind)
        if search:
            query = query.filter(FeedbackTicket.title.ilike('%' + search.replace('%', r'\%').replace('_', r'\_') + '%', escape='\\'))
        pagination = query.order_by(FeedbackTicket.status.in_(CLOSED),
            case((FeedbackTicket.priority == 'urgent', 0), (FeedbackTicket.priority == 'high', 1),
                 (FeedbackTicket.priority == 'normal', 2), else_=3) if admin else FeedbackTicket.updated_at.desc(),
            FeedbackTicket.updated_at.desc(), FeedbackTicket.id.desc()).paginate(
            page=max(1, request.args.get('page', 1, type=int) or 1), per_page=25, error_out=False)
        return render_template('feedback_list.html', pagination=pagination, admin_view=admin,
                               status_filter=status, kind_filter=kind, search=search,
                               category_filter=category, priority_filter=priority, open_filter=request.args.get('open', ''))

    @bp.route('/feedback')
    @login_required
    def index():
        return list_page()

    @bp.route('/admin/feedback')
    @admin_required
    def admin_index():
        return list_page(True)

    @bp.route('/feedback/new', methods=['GET', 'POST'])
    @login_required
    def create():
        values = request.form if request.method == 'POST' else {}
        error = None
        if request.method == 'POST':
            check_token('create')
            title = values.get('title', '').strip()
            description = values.get('description', '').strip()
            kind = values.get('kind', '')
            area = values.get('area', '')
            if not 4 <= len(title) <= 160 or not 10 <= len(description) <= 10000 or kind not in KINDS or area not in AREAS:
                error = 'Bitte Titel (4–160 Zeichen), Beschreibung (10–10.000 Zeichen), Typ und Bereich prüfen.'
            elif FeedbackTicket.query.filter(FeedbackTicket.user_id == current_user.id,
                                             FeedbackTicket.created_at >= utc_now() - timedelta(days=1)).count() >= 10:
                abort(429, 'Maximal 10 neue Meldungen innerhalb von 24 Stunden.')
            else:
                written = []
                try:
                    ticket = FeedbackTicket(user_id=current_user.id, title=title, description=description,
                                            kind=kind, area=area, app_version=version)
                    db.session.add(ticket)
                    db.session.flush()
                    triage_ticket(ticket, assign_priority=True)
                    save_images(ticket, None, False, written)
                    commit_or_conflict(written)
                    flash('Deine Meldung wurde eingereicht.', 'success')
                    return redirect(url_for('feedback.detail', ticket_id=ticket.id))
                except ValueError as exc:
                    rollback_files(written)
                    error = str(exc)
                except Exception:
                    rollback_files(written)
                    raise
        return render_template('feedback_create.html', values=values, error=error, feedback_token=token('create')), 400 if error else 200

    @bp.route('/feedback/<int:ticket_id>', methods=['GET', 'POST'])
    @login_required
    def detail(ticket_id):
        ticket = ticket_for_user(ticket_id)
        if request.method == 'POST':
            check_token(f'ticket-{ticket.id}')
            action = request.form.get('action', '')
            if action in ('personal_complete', 'personal_reopen'):
                if ticket.user_id != current_user.id:
                    abort(403)
                record = db.session.get(FeedbackUserCompletion, ticket.id)
                if action == 'personal_complete' and record is None:
                    db.session.add(FeedbackUserCompletion(ticket_id=ticket.id))
                elif action == 'personal_reopen' and record:
                    db.session.delete(record)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    if action != 'personal_complete' or db.session.get(FeedbackUserCompletion, ticket.id) is None:
                        raise
                flash('Für dich abgeschlossen. Die Admin-Aufgabe bleibt unverändert.' if action == 'personal_complete'
                      else 'Wieder in deinen offenen Meldungen.', 'success')
                return redirect(url_for('feedback.detail', ticket_id=ticket.id))
            if request.form.get('revision', type=int) != ticket.revision:
                abort(409, 'Die Meldung wurde inzwischen geändert. Bitte neu laden.')
            written = []
            try:
                if action == 'reply':
                    body = request.form.get('body', '').strip()
                    internal = request.form.get('internal') == '1'
                    if internal and not current_user.is_admin:
                        abort(403)
                    if not 2 <= len(body) <= 10000:
                        raise ValueError('Eine Antwort muss 2–10.000 Zeichen enthalten.')
                    if FeedbackMessage.query.filter(FeedbackMessage.user_id == current_user.id,
                                                     FeedbackMessage.created_at >= utc_now() - timedelta(hours=1)).count() >= 30:
                        abort(429, 'Maximal 30 Antworten pro Stunde.')
                    message = FeedbackMessage(ticket_id=ticket.id, user_id=current_user.id, body=body, internal=internal)
                    db.session.add(message)
                    db.session.flush()
                    save_images(ticket, message, internal, written)
                    notify_owner(ticket, message)
                elif action == 'manage':
                    if not current_user.is_admin:
                        abort(403)
                    status = request.form.get('status', '')
                    priority = request.form.get('priority', '')
                    target = request.form.get('target_version', '').strip()
                    category = request.form.get('category', ticket.triage.category if ticket.triage else 'unclear')
                    if category not in CATEGORIES:
                        raise ValueError('Ungültige Kategorie.')
                    if status not in STATUSES or priority not in PRIORITIES or (target and not re.fullmatch(r'v?\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?', target)) or len(target) > 32:
                        raise ValueError('Status, Priorität oder Zielversion (z. B. 5.0.1) ungültig.')
                    # Record public status history without disclosing internal priority.
                    if ticket.status != status or (ticket.target_version or '') != target:
                        message = FeedbackMessage(ticket_id=ticket.id, user_id=current_user.id,
                            body=f'Status: {STATUSES[status]}. Geplante Version: {target or "Noch offen"}.', internal=False)
                        db.session.add(message)
                        notify_owner(ticket, message)
                    triage = ticket.triage or triage_ticket(ticket)
                    triage.category = category
                    triage.overridden = category != triage.suggested_category or priority != triage.suggested_priority
                    ticket.status, ticket.priority, ticket.target_version = status, priority, target
                else:
                    abort(400)
                ticket.updated_at = utc_now()
                commit_or_conflict(written)
                flash('Meldung aktualisiert.', 'success')
            except ValueError as exc:
                rollback_files(written)
                flash(str(exc) + ' Bilder bitte erneut auswählen.', 'danger')
            except Exception:
                rollback_files(written)
                raise
            return redirect(url_for('feedback.detail', ticket_id=ticket.id))
        messages = FeedbackMessage.query.filter_by(ticket_id=ticket.id)
        attachments = FeedbackAttachment.query.filter_by(ticket_id=ticket.id)
        if not current_user.is_admin:
            messages = messages.filter_by(internal=False)
            attachments = attachments.filter_by(internal=False)
        return render_template('feedback_detail.html', ticket=ticket,
            messages=messages.order_by(FeedbackMessage.created_at, FeedbackMessage.id).all(),
            attachments=attachments.order_by(FeedbackAttachment.id).all(), feedback_token=token(f'ticket-{ticket.id}'))

    @bp.route('/feedback/images/<int:attachment_id>')
    @login_required
    def image(attachment_id):
        attachment = db.session.get(FeedbackAttachment, attachment_id)
        if not attachment:
            abort(404)
        ticket_for_user(attachment.ticket_id)
        if attachment.internal and not current_user.is_admin:
            abort(404)
        if not re.fullmatch(r'[0-9a-f]{48}\.jpg', attachment.storage_name):
            abort(404)
        path = upload_root() / attachment.storage_name
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype='image/jpeg', download_name=f'bibo-feedback-{attachment.id}.jpg', conditional=False)

    app.register_blueprint(bp)
    return FeedbackTicket, FeedbackMessage, FeedbackAttachment

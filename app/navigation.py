"""One explained navigation catalogue for desktop, mobile and help."""
from flask import render_template, request, url_for
from flask_login import current_user, login_required


def setup_navigation(app, can_collection, custom_categories):
    def groups():
        def item(icon, title, description, endpoint, capability=None, **params):
            if capability and not can_collection(capability):
                return None
            active = request.endpoint == endpoint and all(str(request.args.get(k, (request.view_args or {}).get(k, ''))) == str(v) for k,v in params.items())
            category = params.get('section') or {
                'collection':'games', 'hardware':'games', 'accessories':'games',
                'games':'games', 'standalone_games':'games', 'consoles':'games',
                'retro_lookup':'games', 'collection_bulk':'games',
            }.get(endpoint, '')
            return dict(icon=icon,title=title,description=description,url=url_for(endpoint,**params),active=active,category=category)
        rows = [
          ('📚','Meine Sammlung','Spiele, Medien und eigene Kategorien',[
            item('🗂️','Reihen & Sammlungen','Zusammengehörige Objekte und Reihen','collector_collections'),
            item('⭐','Wunschliste','Was du noch sammeln möchtest','wishlist')]),
          ('＋','Hinzufügen','Suche, Barcode und Import',[
            item('📥','Stapel-Erfassung','Mehrere Objekte nacheinander erfassen','capture_batches','edit_items'),
            item('📄','CSV importieren','Objekte aus einer Datei übernehmen','import_csv','run_imports'),
            item('☁','Offline-Erfassungen','Ausstehende Erfassungen synchronisieren','offline_queue','edit_items')]),
          ('📊','Werte & Preise','Gesamtwert, Bewertung und Verlauf',[
            item('🔐','Top-10-Teilnahme','Eigene Sammlung freiwillig freigeben','top10.settings','manage_users'),
            item('💶','Preise prüfen & neu bewerten','Marktwerte und offene Prüfhinweise','price_center'),
            item('📈','Wertentwicklung','Sammlungswert im zeitlichen Verlauf','price_history_page'),
            item('🔄','Preisänderungen','Neue und geänderte Bewertungen','price_activity'),
            item('💡','Sammlungsassistent','Hinweise und Auswertungen','insights')]),
          ('🗃️','Verwalten','Lagerorte, Planung und Datenpflege',[
            item('📍','Lagerorte & Inventur','Aufbewahrung und Bestandskontrolle','storage_locations'),
            item('🤝','Ausleihen','Verliehene Objekte im Blick behalten','loans'),
            item('🧹','Datenqualität','Fehlende oder widersprüchliche Daten','quality'),
            item('📬','Daten prüfen','Vorgeschlagene Änderungen kontrollieren','review_inbox'),
            item('✏️','Mehrere Spiele bearbeiten','Gemeinsame Änderungen durchführen','collection_bulk','edit_items'),
            item('🗓️','Planungszentrale','Sammlungsausbau planen','collection_planner'),
            item('🎯','Ziele','Persönliche Sammlungsziele','goals'),
            item('🛠️','Projekte','Sammlungsprojekte verwalten','collection_projects'),
            item('🕒','Aktivitätsverlauf','Änderungen in deiner Sammlung','activity'),
            item('⌛','Sammlungschronik','Zeitliche Übersicht deiner Sammlung','timeline'),
            item('🎮','Spielekatalog','Katalogtitel und Metadaten','games'),
            item('▦','Einzelspiele im Katalog','Titel ohne Reihen durchsuchen','standalone_games'),
            item('🕹️','Plattformkatalog','Konsolen und Plattformen nachschlagen','consoles'),
            item('🔍','Retro-Suche','Retrospiele im Katalog suchen','retro_lookup')]),
          ('💬','Hilfe & Feedback','Funktionen finden und Verbesserungen senden',[
            item('🎓','Einführungstutorial starten','Schritt für Schritt durch die verfügbaren Menüs','collector_home',tutorial=1),
            item('⚙️','Tutorial-Einstellungen','Automatische Tutorials dauerhaft aus- oder einschalten','release_news.tutorial_settings'),
            item('📨','Meine Meldungen','Antworten und Bearbeitungsstatus verfolgen','feedback.index'),
            item('🔔','Meine Nachrichten','Öffentliche Antworten und Statusänderungen lesen','feedback.inbox'),
            item('✨','Was ist neu?','Änderungen der aktuellen Version','whats_new'),
            item('⚙️','Mein Konto','Profil, Passwort und Einstellungen','account'),
            item('🔑','Sammlungszugriff anfragen','Zugang zu einer Sammlung beantragen','collection_access_request')])]
        admin = [item('🛡️','Sammlungsrechte','Mitglieder der aktiven Sammlung verwalten','collection_access','manage_users')]
        if current_user.is_admin:
            if app.config['TU_RELEASE_AVAILABLE']():
                admin.append(item('🧪','Test freigeben','Prüfergebnis speichern und Produktionsbefehl anzeigen','test_release.index'))
            admin += [item('📬','Feedback verwalten','Alle Meldungen und interne Notizen','feedback.admin_index'),
                item('👥','Systemnutzer','Benutzerkonten und Systemrechte','admin_users'),
                item('🩺','Systemdiagnose','Betrieb und Hintergrundaufgaben prüfen','operations_center'),
                item('🖼️','Bildarchiv','Gespeicherte Sammlungsbilder verwalten','admin_images'),
                item('💾','Backups','Datenbank und Bilder sichern','admin_backup'),
                item('🗄️','Datenbankstatus','Technischer Datenbankzustand','data_health')]
        rows.append(('🛡️','Administration','Nur Funktionen mit deiner Berechtigung',admin))
        return [dict(icon=icon,title=title,description=desc,items=items,active=any(i['active'] for i in items))
                for icon,title,desc,values in rows if (items := [v for v in values if v])]

    @app.context_processor
    def context():
        return {'navigation_groups':groups() if current_user.is_authenticated else []}

    app.config['NAVIGATION_GROUPS']=groups

    @app.route('/help/navigation')
    @login_required
    def navigation_help():
        return render_template('navigation_help.html')

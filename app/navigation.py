"""One explained navigation catalogue for desktop, mobile and help."""
from flask import render_template, request, url_for
from flask_login import current_user, login_required


def setup_navigation(app, can_collection, custom_categories):
    def groups():
        def item(icon, title, description, endpoint, capability=None, **params):
            if capability and not can_collection(capability):
                return None
            active = request.endpoint == endpoint and all(str(request.args.get(k, (request.view_args or {}).get(k, ''))) == str(v) for k,v in params.items())
            return dict(icon=icon,title=title,description=description,url=url_for(endpoint,**params),active=active)
        rows = [
          ('📚','Meine Sammlung','Spiele, Medien und eigene Kategorien',[
            item('▤','Alle Sammlungsobjekte','Bibliothek durchsuchen und filtern','bibo_library'),
            item('🎮','Spiele','Deine vorhandenen Spiele und Exemplare','collection'),
            item('🕹️','Konsolen & Hardware','Geräte, Modelle und Exemplare','hardware'),
            item('🎧','Zubehör','Controller, Kabel und weitere Extras','accessories'),
            *[item(icon,title,'Deine Sammlung öffnen','collector_section',section=section) for section,icon,title in [('movies','🎬','Filme'),('tv','📺','Serien'),('books','📖','Bücher'),('music','💿','Musik'),('cards','🃏','Sammelkarten'),('custom','📦','Weitere Sammlungen')]],
            item('🗂️','Reihen & Sammlungen','Zusammengehörige Objekte und Reihen','collector_collections'),
            item('⭐','Wunschliste','Was du noch sammeln möchtest','wishlist'),
            item('✦','Ähnliche Titel entdecken','Passende Vorschläge zur Sammlung','discovery_center')]),
          ('＋','Hinzufügen','Suche, Barcode und Import',[
            item('🔎','Objekt hinzufügen','Titel, EAN oder Produktcode erkennen','collector_identify_start','edit_items'),
            item('📷','Barcode scannen','Objekte mit der Kamera erkennen','scanner','edit_items'),
            item('📥','Stapel-Erfassung','Mehrere Objekte nacheinander erfassen','capture_batches','edit_items'),
            item('📄','CSV importieren','Objekte aus einer Datei übernehmen','import_csv','run_imports'),
            item('☁','Offline-Erfassungen','Ausstehende Erfassungen synchronisieren','offline_queue','edit_items')]),
          ('📊','Werte & Preise','Gesamtwert, Bewertung und Verlauf',[
            item('📊','Bewertungsdashboard','Gesamtwert und Gewinner / Verlierer','dashboard'),
            item('🏆','Globale Top 10','Wertvollste Produkte freigegebener Sammlungen','top10.index') if app.config['TOP10_USER_ENABLED']() else None,
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
            item('🧭','Welche Funktion finde ich wo?','Alle Bereiche mit kurzen Erklärungen','navigation_help'),
            item('💬','Feedback senden','Fehler oder Verbesserung mit Bildern melden','feedback.create'),
            item('📨','Meine Meldungen','Antworten und Bearbeitungsstatus verfolgen','feedback.index'),
            item('🔔','Meine Nachrichten','Öffentliche Antworten und Statusänderungen lesen','feedback.inbox'),
            item('✨','Was ist neu?','Änderungen der aktuellen Version','whats_new'),
            item('⚙️','Mein Konto','Profil, Passwort und Einstellungen','account'),
            item('🏆','Globale Top 10 einstellen','Persönliche Ansicht aktivieren oder deaktivieren','top10.preferences'),
            item('🔑','Sammlungszugriff anfragen','Zugang zu einer Sammlung beantragen','collection_access_request')])]
        for category in custom_categories():
            rows[0][3].append(item(category.get('icon','📦'),category['title'],'Eigene Sammlungskategorie','collector_section',section='custom',custom_category=category['id']))
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

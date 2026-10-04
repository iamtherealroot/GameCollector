# Bibo 5.1.0-rc.3 – Top-10-Standardfreigabe und OVP-Feld

Unveröffentlichter Prüfentwurf, enthält rc.1 und rc.2. Keine Veröffentlichung ohne erneute Freigabe.

- Globale Top-10-Ansicht und Teilnahme einer Sammlung sind standardmäßig aktiv, sobald mindestens zwei Sammlungsdatenbanken angelegt sind. Zuvor bleibt die Funktion gesperrt. Explizit gespeicherte Ausschaltungen bleiben erhalten, auch nach Updates.
- Ohne eigene Anzeigenamen erscheinen „Sammlung <ID>“ und „Sammler <ID>“, nicht echte Konto- oder Sammlungsnamen. Nur die bisher definierten Produktzusammenfassungen sind sichtbar. Notizen, Lagerorte, Kaufpreise und private Objektlinks bleiben verborgen. Ansicht ausschalten und Sammlung abmelden sind getrennte Entscheidungen; die Teilnahme verwaltet ein Sammlungsverwalter.
- Tutorial-Einstellungen mit ausgerichtetem Schalter, erklärtem Bestätigungsschritt und großer hervorgehobener Speicheraktion.
- Bei der Erfassung einer Spielekopie ist OVP-Zustand ohne vorhandene OVP/Hülle deaktiviert, ebenso Medium-Zustand ohne Medium. Umschalten erfolgt unmittelbar. „Original versiegelt“ aktiviert die Bestandteile; Entfernen eines Bestandteils hebt die Versiegelung auf. Digitale Exemplare haben keine aktiven physischen Zustandsfelder.
- Der zentrale Speicherpfad ignoriert OVP-Zustand ohne OVP, auch bei manipulierten Formularen. Ein vorheriger Zustandswert wird nicht gelöscht und spielt ohne OVP keine Rolle bei der Bewertung.
- Falscher Hilfetext zur Schätzwert-Priorität korrigiert: Automatischer Marktwert vor eigener Schätzung.

Lokale Backend-, Rechte-, Datenschutz-, Formular- und JavaScript-Vertragstests bestanden. Tatsächlicher Docker-Lauf und visuelle Prüfung sind in der TU erforderlich; Docker ist hier nicht verfügbar. Produktion und GitHub unverändert. Diese Änderung korrigiert das gemeldete OVP-Zustandsfeld, nicht pauschal sämtliche übrigen Bewertungsprobleme.

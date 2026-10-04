"""Informational checks: never silently change a stored valuation."""
from datetime import timezone, timedelta

def valuation_warnings(item, now, stale_days=45):
    warnings=[]
    if getattr(item,'auto_value_eur',None) is None:return warnings
    updated=getattr(item,'auto_value_updated_at',None)
    if updated is None:
        warnings.append('Bewertungsdatum fehlt: Aktualität nicht nachweisbar.')
    else:
        if updated.tzinfo is None:updated=updated.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:now=now.replace(tzinfo=timezone.utc)
        if updated<now-timedelta(days=stale_days):
            warnings.append(f'Bewertung älter als {stale_days} Tage; bitte erneut prüfen.')
    confidence=str(getattr(item,'auto_value_confidence','') or '').casefold()
    if confidence in {'niedrig','vorläufig','low'}:
        warnings.append('Unsichere Bewertung: wenige oder schwach vergleichbare Referenzen.')
    source=str(getattr(item,'auto_value_source','') or '').casefold()
    if 'ebay' in source and 'angebot' in source:
        warnings.append('Angebotspreise, keine nachgewiesenen abgeschlossenen Verkäufe. Region und Ausgabe bei der Quelle prüfen.')
    if getattr(item,'auto_value_status',None)=='price_jump_pending':
        warnings.append('Preissprung wartet auf Bestätigung; der bisherige Marktwert bleibt erhalten.')
    return warnings

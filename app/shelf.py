"""Decorative shelf cases, sampled only from the active collection."""
import secrets

CASE_HEIGHTS = {'bluray':208,'dvd':242,'dvd-game':242,'uhd':208,'vhs':238,
    'switch':222,'xbox360':242,'ps1':166,'ps3':208,'ps-blue':208,'game':226,
    'cd':166,'vinyl':236,'cassette':130,'album':231,'archive':220,'book':228,
    'ds':170,'retro-box':210,'gb-cartridge':99,'n64-cartridge':95,
    'snes-cartridge':115,'nes-cartridge':180}


def case_style(category, media="", box_present=None):
    name = str(media or "").casefold().replace("-", " ")
    if category == "games":
        if box_present is False:
            if any(token in name for token in ('game boy', 'gameboy')): return 'gb-cartridge'
            if 'nintendo 64' in name or name.strip() == 'n64': return 'n64-cartridge'
            if 'super nintendo' in name or name.strip() == 'snes': return 'snes-cartridge'
            if name.strip() in {'nes', 'nintendo entertainment system'}: return 'nes-cartridge'
        if any(token in name for token in ('game boy', 'gameboy', 'super nintendo', 'nintendo 64')) or name.strip() in {'snes','nes','n64'}:
            return 'retro-box'
        if 'nintendo ds' in name or '3ds' in name: return 'ds'
        if 'gamecube' in name: return 'dvd-game'
        if name.strip() in {'xbox', 'microsoft xbox'}: return 'xbox360'
        if name.strip() in {'playstation', 'sony playstation', 'ps'}:
            return 'ps1'
        for tokens, style in [(('switch',), 'switch'), (('xbox 360', 'ps2', 'playstation 2'), 'dvd-game'),
                              (('ps1', 'playstation 1', 'psx'), 'ps1'),
                              (('ps3', 'playstation 3'), 'ps3'),
                              (('ps4', 'ps5', 'playstation 4', 'playstation 5'), 'ps-blue')]:
            if any(token in name for token in tokens):
                return 'xbox360' if 'xbox 360' in name else style
        return 'game'
    if category in {'movies', 'tv'}:
        if '4k' in name or 'uhd' in name: return 'uhd'
        if 'blu' in name: return 'bluray'
        if 'vhs' in name: return 'vhs'
        return 'dvd'
    if category == 'music':
        if 'vinyl' in name: return 'vinyl'
        if 'kassette' in name or 'cassette' in name: return 'cassette'
        return 'cd'
    return {'books': 'book', 'cards': 'album'}.get(category, 'archive')


def shelf_cases(category, entries, slots=48):
    cases = []
    for title, media, *details in entries:
        if str(title or '').strip():
            cases.append({'title': str(title).strip(), 'style': case_style(category, media, details[2] if len(details)>2 else None),
                          'format': str(media or ''), 'href': details[0] if details else '',
                          'cover': details[1] if len(details) > 1 else ''})
    random = secrets.SystemRandom()
    # Spread formats across the visible shelf instead of putting every short
    # Blu-ray before every tall DVD. The inventory count remains independent.
    by_style = {}
    for case in cases:
        by_style.setdefault(case['style'], []).append(case)
    for group in by_style.values():
        random.shuffle(group)
    selected = []
    styles = list(by_style)
    random.shuffle(styles)
    while len(selected) < slots and any(by_style.values()):
        for style in styles:
            if by_style[style] and len(selected) < slots:
                selected.append(by_style[style].pop())
    # Repeat existing titles only for the decorative display when fewer than
    # eight copies exist; no product or inventory row is created.
    originals = list(selected)
    while len(selected) < min(8, slots):
        selected.append(dict(originals[len(selected) % len(originals)]) if originals else
                        {'title': '', 'style': case_style(category), 'href': '', 'cover': '', 'format': ''})
    for case in selected:
        case['height'] = CASE_HEIGHTS.get(case['style'],218)
        if case['style']=='book':
            case['height']=(217,228,239)[sum(map(ord,case['title']))%3]
    return [case for start in range(0, len(selected), 8)
            for case in sorted(selected[start:start+8], key=lambda case:case['height'])]

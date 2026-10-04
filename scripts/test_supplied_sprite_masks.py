"""Guard against the whole-sheet/adjacent-body regression from RC.2."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'
files = list(Path('app/templates').glob('_sprite_profession-*.html'))
files += list(Path('app/templates').glob('_sprite_class-*.html'))
files += [Path('app/templates/_sprite_falconer-ranger.html')]
assert len(files) == 15
frames = 0
for file in files:
    text = re.sub(r"\{\{ url_for\('static', filename='([^']+)'\) \}\}", r'/static/\1', file.read_text())
    root = ET.fromstring('<root>' + text + '</root>')
    ids = [node.attrib['id'] for node in root.iter() if 'id' in node.attrib]
    assert len(ids) == len(set(ids)), file
    parents = {child: parent for parent in root.iter() for child in parent}
    for svg in root.iter(NS + 'svg'):
        assert parents[svg] is root, (file, 'nested SVG could inherit overflow/size rules')
    for defs in root.iter(NS + 'defs'):
        assert parents[defs].tag == NS + 'svg', (file, 'clip resources must stay outside hidden/animated pose groups')
    for image in root.iter(NS + 'image'):
        group = parents[image]
        assert group.attrib.get('clip-path', '').startswith('url(#'), file
        clip_id = group.attrib['clip-path'][5:-1]
        clip = next(node for node in root.iter(NS + 'clipPath') if node.attrib['id'] == clip_id)
        path = clip.find(NS + 'path')
        assert path is not None, file
        runs = [tuple(map(int, run)) for run in re.findall(r'M(\d+),(\d+)h(\d+)v1h-\d+z', path.attrib['d'])]
        assert runs, file
        width = max(x + w for x, y, w in runs) - min(x for x, y, w in runs)
        height = max(y for x, y, w in runs) - min(y for x, y, w in runs) + 1
        assert 20 <= width <= 190 and 20 <= height <= 210, (file, clip_id, width, height)
        frames += 1
    poses = [node.attrib.get('class') for node in root.iter(NS + 'g')]
    assert all(f'sport-pose sport-pose-{i}' in poses for i in range(14)), file
css = Path('app/static/collection-shelf.css').read_text()
assert '.regal-helper>svg{display:block;width:100%;height:100%}' in css
assert '.regal-helper .regal-bird-template{display:none!important}' in css
assert '.regal-helper svg{display:block;width:100%;height:100%}' not in css
print(f'OK: {frames} masked frames, bounded silhouettes, unique clip IDs, no nested viewports and hidden bird source')

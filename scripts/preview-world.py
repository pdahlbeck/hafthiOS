#!/usr/bin/env python3
"""Render the actual wallpaper and check motion, pause and quiet sky."""
from pathlib import Path
import runpy
import time
from PIL import Image, ImageChops, ImageStat
try:
    import cairo
except ImportError:
    import cairocffi as cairo

root = Path(__file__).resolve().parents[1]
world = runpy.run_path(str(root / 'live/usr/local/bin/hafthios-world'))
village = world['Village'](cairo)
assert 0 < village.ship_ink_width < village.ship.get_width() * .7, 'Ship margins were included in its scale'
out = root / 'out'
out.mkdir(exist_ok=True)

def render(t, load=.12, heat=None, network=0):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1440, 900)
    village.draw(cairo.Context(surface), 1440, 900, t, load, heat, network)
    return surface

start = time.monotonic()
for i in range(24):
    render(900 + i / 12)
average_ms = (time.monotonic() - start) * 1000 / 24
for name, t, load, heat, network in [('village-start', 0, .12, None, 0),
                                    ('village', 900, .12, None, 0),
                                    ('village-moving', 905, .12, None, 0),
                                    ('village-paused', 900, .12, None, 0),
                                    ('village-docked', 335, .35, None, .5),
                                    ('village-shipbuilding', 220, .5, None, 0),
                                    ('village-expanded', 2300, .3, None, 0),
                                    ('village-forging', 155, .3, None, 0),
                                    ('village-tool-delivery', 240, .3, None, 0),
                                    ('village-trade', 340, .3, None, .5),
                                    ('village-supper', 1100, .12, None, 0),
                                    ('village-evening', 1450, .08, None, 0),
                                    ('village-busy', 900, .85, 85, .9)]:
    render(t, load, heat, network).write_to_png(str(out / (name + '.png')))
a = Image.open(out / 'village.png').convert('RGB')
b = Image.open(out / 'village-moving.png').convert('RGB')
paused = Image.open(out / 'village-paused.png').convert('RGB')
assert ImageChops.difference(a, b).getbbox(), 'Animation is stationary'
assert ImageChops.difference(a, paused).getbbox() is None, 'Paused scene changes'
assert ImageStat.Stat(a.crop((0, 0, 1440, 200))).mean[0] < 30, 'Sky too bright behind windows'
assert ImageChops.difference(a, Image.open(out / 'village-busy.png').convert('RGB')).getbbox(), 'Telemetry has no effect'
message = f'Village rendering OK: motion, stable pause, telemetry, quiet sky; {average_ms:.1f} ms/frame at 1440x900\n'
(out / 'village.log').write_text(message)
print(message, end='')

"""SF2 lab competition runner

Usage:
  cued_sf2_lab_compete <module_name> <img_name>... [--output=<dir>]

Options:
  -h --help       Show this screen.
  --version       Show version.
  --output=<dir>  Set the directory to write images to
"""

from docopt import docopt, parse_defaults

from cued_sf2_lab import __version__
from cued_sf2_lab.familiarisation import load_mat_img, plot_image
from cued_sf2_lab.jpeg import vlctest
from typing import NamedTuple, Callable, Tuple, Any, List, Dict
from types import ModuleType
from pathlib import Path
import importlib
import sys
import numpy as np
import imageio
import pickle
import functools
import html
import base64
from matplotlib.colors import LinearSegmentedColormap

error_cm = LinearSegmentedColormap(
    'seismic_alpha',
    dict(red=np.array([[0.  , 0.  , 0.  ],
                    [0.25, 0.  , 0.  ],
                    [0.5 , 1.  , 1.  ],
                    [0.75, 1.  , 1.  ],
                    [1.  , 0.5 , 0.5 ]]),
        green=np.array([[0.  , 0.  , 0.  ],
                    [0.25, 0.  , 0.  ],
                    [0.5 , 1.  , 1.  ],
                    [0.75, 0.  , 0.  ],
                    [1.  , 0.  , 0.  ]]),
        blue=np.array([[0.  , 0.3 , 0.3 ],
                    [0.25, 1.  , 1.  ],
                    [0.5 , 1.  , 1.  ],
                    [0.75, 0.  , 0.  ],
                    [1.  , 0.  , 0.  ]]),
        alpha=np.array([[0.  , 1.  , 1.  ],
                    [0.5 , 0.  , 0.  ],
                    [1.  , 1.  , 1.  ]])),
    N=256)


def diff_image(X, Z):
    cols = error_cm(X - Z + 128)
    return (cols * 255).astype(np.uint8)


default_options = {o.name: o.value for o in parse_defaults(__doc__)}


class Submission(NamedTuple):
    module: ModuleType
    header_bits: Callable[[Any], int]
    encode: Callable[[np.ndarray], Tuple[np.ndarray, Any]]
    decode: Callable[[Tuple[np.ndarray, Any]], np.ndarray]


class EncodeOutput(NamedTuple):
    vlc: np.ndarray
    header: Any
    n_header_bits: int

def load(module_name: str) -> Submission:
    print(sys.path)
    mod = importlib.import_module(module_name)
    try:
        header_bits = mod.header_bits
    except AttributeError:
        raise RuntimeError("No `header_bits` function found")
    try:
        encode = mod.encode
    except AttributeError:
        raise RuntimeError("No `encode` function found")
    try:
        decode = mod.decode
    except AttributeError:
        raise RuntimeError("No `decode` function found")
    return Submission(mod, header_bits, encode, decode)


def run_encoder(mod: Submission, X: np.ndarray) -> EncodeOutput:
    # TODO: run in separate process?
    vlc, header = mod.encode(X)
    h_bits = mod.header_bits(header)
    return EncodeOutput(vlc, header, h_bits)

def run_decoder(mod: Submission, x: EncodeOutput) -> np.ndarray:
    # TODO: run in separate process?
    return mod.decode(x.vlc, x.header)

def collect(mod: Submission, imgs: List[str]) -> List[Dict]:
    data = [dict(errors=[]) for _ in imgs]
    for i, img in enumerate(imgs):
        X, _ = load_mat_img(img=f'{img}.mat', img_info='X')
        data[i]['name'] = img
        data[i]['X'] = X
        X.flags.writeable = False
        data[i]['enc'] = run_encoder(mod, X)
    for row in data:
        row['Z'] = run_decoder(mod, row['enc'])

        row['Z_actual'] = np.clip(row['Z'], 0, 255).astype(np.uint8)
        row['rms'] = np.std(row['X'] - row['Z_actual'] )

        try:
            row['vlc_bits'] = vlctest(row['enc'].vlc)
        except ValueError as e:
            total_bits = 0
            row['vlc_bits'] = None
            row['total_bits'] = None
            row['vlc_error'] = e
        else:
            row['total_bits'] = row['vlc_bits'] + row['enc'].n_header_bits

    return data


def asbase64(img: Path) -> str:
    with img.open('rb') as f:
        img_data = f.read()
    return 'data:image/png; base64, ' + base64.b64encode(img_data).decode('utf-8')


def main(module_name, imgs, out_dir=None):
    mod = load(module_name)
    if out_dir is None:
        out_dir = Path(mod.module.__file__).parent / 'outputs'
    else:
        out_dir = Path(out_dir)
    if not out_dir.is_dir():
        raise SystemExit(f"Cannot find output directory {out_dir!r}")

    fail = False

    with (Path(__file__).parent / 'show_image.svg').open('r') as f:
        svg_template = f.read()

    with (out_dir / 'summary.md').open('w') as f:
        pr = functools.partial(print, file=f)
        pr("<h1>Submission results</h1>")
        pr()

        data = collect(mod, imgs)
        pr()
        pr("<table>")
        pr("<tr>")
        for i, row in enumerate(data):
            this_fail = False
            if row['vlc_bits'] is None:
                this_fail = True
            if row['total_bits'] is not None and row['total_bits'] > 40960:
                this_fail = True
            pr("<td>")
            pr(f"<h2>{row['name']} {'❌' if this_fail else '✔️'}</h2>")
            imageio.imwrite(out_dir / f"{row['name']}.png", data[i]['Z_actual'])
            imageio.imwrite(out_dir / f"{row['name']}-diff.png",
                diff_image(data[i]['X'], data[i]['Z_actual']))
            with (out_dir / f"{row['name']}.svg").open('w') as f:
                f.write(svg_template
                    .replace('$DATA', asbase64(out_dir / f"{row['name']}.png"))
                    .replace('$DIFF_DATA', asbase64(out_dir / f"{row['name']}-diff.png")))

            with (out_dir / f"{row['name']}.pkl").open('wb') as f:
                pickle.dump(row['enc'], f)

            pr(f'<img src="./{row["name"]}.svg?raw=true" alt="{row["name"]} (output)">')
            pr("<table>")
            pr(f"<tr><th rowspan='3' scope='row'>Bit counts</th><th scope='row'>header</th><td>{row['enc'].n_header_bits}</td></tr>")
            if row['vlc_bits'] is None:
                pr(f"<tr><th scope='row'>vlc</th><td>❌ INVALID!<br />{row['vlc_error']}</td></tr>")
                pr(f"<tr><th scope='row'>total</th><td>&mdash;</td></tr>")
            else:
                pr(f"<tr><th scope='row'>vlc</th><td>{row['vlc_bits']}</td></tr>")
                pr(f"<tr><th scope='row'>total</th><td>{row['total_bits']}</td></tr>")
            pr(f"<tr><th colspan='2' scope='row'>RMS Error</th><td>{row['rms']:.3f}</td></tr>")
            pr("</table>")
            if row['total_bits'] is not None and row['total_bits'] > 40960:
                pr("<p><b>❌ TOO LARGE!</b> Must be at most 40960 bits</p>")
            if row['enc'].header is not None:
                pr("<details><summary>Header contents</summary><pre>")
                pr(html.escape(repr(row['enc'].header)))
                pr("</pre></details>")
            pr(f'<a href="./{row["name"]}.pkl?raw=true" download>🗄️ Download encoded data</a>')
            pr("</td>")
            fail = fail or this_fail

    if fail:
        raise SystemExit("Some images failed the tests")


def cli():
    args = docopt(__doc__, version=__version__)
    main(args['<module_name>'], imgs=args['<img_name>'], out_dir=args['--output'])


if __name__ == '__main__':
    cli()

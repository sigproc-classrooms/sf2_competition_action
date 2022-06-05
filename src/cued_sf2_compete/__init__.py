"""SF2 lab competition runner

Usage:
  cued_sf2_lab_compete <module_name>
    [--required=<req_img>]... <img_name>... [--output=<dir>]

Options:
  -h --help       Show this screen.
  --version       Show version.
  --required=<req_img>  Other images which must pass
  --output=<dir>         Set the directory to write images to
"""
import concurrent.futures
import base64
import functools
import html
import importlib
import json
import os
import pickle
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, NamedTuple, Tuple

import imageio
import numpy as np
from cued_sf2_lab import __version__
from cued_sf2_lab.familiarisation import load_mat_img, plot_image
from cued_sf2_lab.jpeg import vlctest
from docopt import docopt, parse_defaults
from matplotlib.colors import LinearSegmentedColormap
import multiprocessing

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

def encode_process(mod: str, X: np.array) -> EncodeOutput:
    mod = load(mod)
    vlc, header = mod.encode(X)
    h_bits = mod.header_bits(header)
    return EncodeOutput(vlc, header, h_bits)

def encode_msg_text_for_github(msg):
    # even though this is probably url quoting, we match the implementation at
    # https://github.com/actions/toolkit/blob/af821474235d3c5e1f49cee7c6cf636abb0874c4/packages/core/src/command.ts#L36-L94
    return msg.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')

if 'GITHUB_ACTIONS' in os.environ:
    def run_isolated(func, *args):
        import traceback
        try:
            return func(*args)
        except Exception as e:
            tb = traceback.TracebackException.from_exception(e)
            e_msg = encode_msg_text_for_github(''.join(tb.format_exception_only()))
            msg = encode_msg_text_for_github(''.join(traceback.format_list(tb.stack)))
            for s in tb.stack:
                print(f'::error file={s.filename},line={s.lineno},title={e_msg}::{msg}')
            raise
else:
    def run_isolated(func, *args):
        return func(*args)

def run_encoder(mod: Submission, X: np.ndarray) -> EncodeOutput:
    with concurrent.futures.ProcessPoolExecutor() as executor:
        return executor.submit(run_isolated, encode_process, mod.module.__name__, X).result()

def decode_process(mod: str, x: EncodeOutput) -> np.ndarray:
    mod = load(mod)
    return mod.decode(x.vlc, x.header)

def run_decoder(mod: Submission, x: EncodeOutput) -> np.ndarray:
    with concurrent.futures.ProcessPoolExecutor() as executor:
        return executor.submit(run_isolated, decode_process, mod.module.__name__, x).result()

def collect(mod: Submission, imgs: List[str]) -> List[Dict]:
    data = [dict(errors=[]) for _ in imgs]
    for i, img in enumerate(imgs):
        if img.startswith('cued-sf2://'):
            img = img.removeprefix('cued-sf2://')
            fname = str((Path(__file__).parent / 'images') / img)
            img = img.removesuffix('.mat')
        elif not img.endswith('.mat'):
            fname = f'{img}.mat'
        else:
            fname = img
        X, _ = load_mat_img(img=fname, img_info='X')
        data[i]['name'] = img
        data[i]['X'] = X
        X.flags.writeable = False
        data[i]['enc'] = run_encoder(mod, X)
    for row in data:
        row['Z'] = run_decoder(mod, row['enc'])

        row['Z_actual'] = np.clip(row['Z'], 0, 255).astype(np.uint8)
        row['rms'] = np.std(row['X'].astype(np.double) - row['Z_actual'].astype(np.double))

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


def main(module_name, imgs, req_imgs, out_dir=None):
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

    all_imgs = req_imgs + imgs

    with (out_dir / 'summary.md').open('w') as f:
        pr = functools.partial(print, file=f)

        req_data = collect(mod, req_imgs)
        extra_data = collect(mod, imgs)
        all_json = dict(required={}, extra={})
        for header, data, required, this_json in [('Submission results', req_data, True, all_json['required']), ('Other images', extra_data, False, all_json['extra'])]:
            if not data:
                continue
            if header:
                pr(f"<h1>{header}</h1>")
                pr()
            pr("<table>")
            pr("<tr>")
            for i, row in enumerate(data):
                this_fail = False
                if row['vlc_bits'] is None:
                    this_fail = True
                if row['total_bits'] is not None and row['total_bits'] > 40960:
                    this_fail = True
                
                this_json[row['name']] = dict(
                    rms=float(row['rms']),
                    fail=this_fail,
                    total_bits=int(row['total_bits'])
                )
                pr("<td>")
                pr(f"<h2>{row['name']} {'❌' if this_fail else '✔️'}</h2>")
                out_name = f"{row['name']}"
                Path(out_dir / f"{out_name}").parent.mkdir(parents=True, exist_ok=True)
                imageio.imwrite(out_dir / f"{out_name}.png", data[i]['Z_actual'])
                imageio.imwrite(out_dir / f"{out_name}-diff.png",
                    diff_image(data[i]['X'], data[i]['Z_actual']))
                with (out_dir / f"{out_name}.svg").open('w') as f:
                    f.write(svg_template
                        .replace('$DATA', asbase64(out_dir / f"{out_name}.png"))
                        .replace('$DIFF_DATA', asbase64(out_dir / f"{out_name}-diff.png")))

                with (out_dir / f"{out_name}.pkl").open('wb') as f:
                    pickle.dump(row['enc'], f)

                pr(f'<img src="./{out_name}.svg?raw=true" alt="{out_name} (output)">')
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
                pr(f'<a href="./{out_name}.pkl?raw=true" download>🗄️ Download encoded data</a>')
                pr("</td>")
                if required:
                    fail = fail or this_fail
            pr("</tr>")
            pr("</table>")
    all_json['failed'] = fail
    with (out_dir / f"summary.json").open('w') as f:
        json.dump(all_json, f, indent=2)

    if 'GITHUB_ACTIONS' in os.environ:
        rms = {row['name']: row['rms'] for row in req_data}
        print("::set-output name=RMS::" + json.dumps(rms))

    if fail:
        raise SystemExit("Some images failed the tests")


def cli():
    sys.path.insert(0, os.getcwd())
    args = docopt(__doc__, version=__version__)
    main(args['<module_name>'],
        req_imgs=args['--required'],
        imgs=args['<img_name>'], out_dir=args['--output'])


if __name__ == '__main__':
    cli()

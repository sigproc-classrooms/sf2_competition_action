#!/usr/bin/env python
from setuptools import setup, find_packages
from os import path

this_directory = path.abspath(path.dirname(__file__))

# could add encoding='utf-8' if needed
with open(path.join(this_directory, 'src/cued_sf2_compete', '_version.py')) as f:
    exec(f.read())

with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='cued_sf2_compete',
    version=__version__,  # noqa: F821
    license='MIT',
    description='IIA Engineering SF2 Lab Competition tool',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Eric Wieser',
    maintainer='Eric Wieser',
    maintainer_email='efw27@cam.ac.uk',
    packages=find_packages(where='src'),
    install_requires=[
        'cued_sf2_lab@git+https://github.com/sigproc/cued_sf2_lab.git',
        'docopt',
        'imageio',
        'jinja2',
    ],
    # {'package_name': 'folder_with_its_source'}
    package_dir={'': 'src'},
    package_data={'cued_sf2_compete': ['*.svg', 'images/*.mat', 'images/competition/*.mat']},

    classifiers=[
        # 'Intended Audience :: Science/Research',
        # 'Topic :: Scientific/Engineering :: Mathematics',

        # 'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    entry_points={
        "console_scripts": ["cued_sf2_compete=cued_sf2_compete:cli"]
    },

    python_requires='>=3.8',
)
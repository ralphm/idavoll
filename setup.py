#!/usr/bin/env python

# Copyright (c) Ralph Meijer.
# See LICENSE for details.

import sys
from setuptools import setup
from idavoll import __version__

install_requires = [
    'wokkel >= 0.5.0',
    'simplejson',
]

if sys.version_info < (2, 5):
    install_requires.append('uuid')

# Make sure 'twisted' doesn't appear in top_level.txt

try:
    from setuptools.command import egg_info
    egg_info.write_toplevel_names
except (ImportError, AttributeError):
    pass
else:
    def _top_level_package(name):
        return name.split('.', 1)[0]

    def _hacked_write_toplevel_names(cmd, basename, filename):
        pkgs = dict.fromkeys(
            [_top_level_package(k)
                for k in cmd.distribution.iter_distribution_names()
                if _top_level_package(k) != "twisted"
            ]
        )
        cmd.write_file("top-level names", filename, '\n'.join(pkgs) + '\n')

    egg_info.write_toplevel_names = _hacked_write_toplevel_names

setup(name='idavoll',
      version=__version__,
      description='Jabber Publish-Subscribe Service Component',
      author='Ralph Meijer',
      author_email='ralphm@ik.nu',
      url='http://idavoll.ik.nu/',
      license='MIT',
      packages=[
          'idavoll',
          'idavoll.test',
          'twisted.plugins',
      ],
      package_data={'twisted.plugins': ['twisted/plugins/idavoll.py',
                                        'twisted/plugins/idavoll_http.py']},
      data_files=[('share/idavoll', ['db/pubsub.sql',
                                     'db/gateway.sql',
                                     'db/to_idavoll_0.8.sql',
                                     'doc/examples/idavoll.tac',
                                     ])],
      zip_safe=False,
      install_requires=install_requires,
)

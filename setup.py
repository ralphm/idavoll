#!/usr/bin/env python

# Copyright (c) 2003-2011 Ralph Meijer
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

#!/usr/bin/env python

# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

import sys
from setuptools import setup

install_requires = ['wokkel >= 0.3.1']

if sys.version_info < (2, 5):
    install_requires.append('uuid')

setup(name='idavoll',
      version='0.7.2',
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
      zip_safe=False,
      install_requires=install_requires,
)

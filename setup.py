#!/usr/bin/env python

# Copyright (c) 2003-2006 Ralph Meijer
# See LICENSE for details.

from distutils.core import setup

setup(name='idavoll',
      version='0.6.0',
      description='Jabber Publish-Subscribe Service Component',
      author='Ralph Meijer',
      author_email='ralphm@ik.nu',
      url='http://idavoll.ik.nu/',
      license='MIT',
      packages=[
          'idavoll',
          'twisted.plugins',
      ],
      package_data={'twisted.plugins': ['twisted/plugins/idavoll.py']}
)

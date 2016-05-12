#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='lib-esendex',
      use_scm_version={
          'version_scheme': 'post-release'
      },
      setup_requires=['setuptools_scm'],
      install_requires=['arrow', 'requests'],
      description='Esendex services helper library',
      author='Eric Pascual (CSTB)',
      author_email='eric.pascual@cstb.fr',
      package_dir={'': 'src'},
      packages=find_packages('src'),
      )

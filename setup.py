from setuptools import setup

setup(name='tyme',
      version='0.0',
      description='Command line todo list and time tracker.',
      keywords='time todo productivity'
      url='https://github.com/fredcallaway/tyme',
      author='Fred Callaway',
      author_email='fredc@llaway.com',
      license='MIT',
      packages=['tyme'],
      install_requires=['fuzzyfinder'],
      scripts=['bin/tyme'],
      include_package_data=False,
      zip_safe=False)
from distutils.core import setup

setup(
    name='pyosm',
    version='0.1',
    author='Ian Dees',
    author_email='ian.dees@gmail.com',
    packages=['pyosm'],
    url='http://github.com/iandees/pyosm',
    license='LICENSE.txt',
    description='Parses OSM XML files in a fast and reliable way.',
    long_description=open('README.md').read(),
    install_requires=[
        'lxml==3.2.3'
    ]
)


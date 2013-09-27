import os
import sys
import mozilla_sphinx_theme


extensions = []
templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'index'
project = u'Loads'

copyright = u'2013, Mozilla Services'

CURDIR = os.path.abspath(os.path.dirname(__file__))
sys.path.append(os.path.join(CURDIR, '..', '..'))
sys.path.append(os.path.join(CURDIR, '..'))

import loads
version = release = loads.__version__
exclude_patterns = []


html_theme_path = [os.path.dirname(mozilla_sphinx_theme.__file__)]

html_theme = 'mozilla'
html_static_path = ['_static']
htmlhelp_basename = 'Loadsdoc'

latex_elements = {
}

latex_documents = [
    ('index', 'Loads.tex', u'Loads Documentation',
     u'Mozilla Services', 'manual'),
]
man_pages = [
    ('index', 'loads', u'Loads Documentation',
     [u'Mozilla Services'], 1)
]

texinfo_documents = [
    ('index', 'Loads', u'Loads Documentation',
     u'Mozilla Services', 'Loads', 'One line description of project.',
     'Miscellaneous'),
]

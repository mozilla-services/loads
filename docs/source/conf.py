extensions = []
templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'index'
project = u'Loads'
copyright = u'2013, Mozilla Services'
version = '0.1'
release = '0.1'
exclude_patterns = []
pygments_style = 'sphinx'

html_theme = 'default'
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

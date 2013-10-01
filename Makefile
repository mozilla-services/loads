HERE = $(shell pwd)
BIN = $(HERE)/bin
PYTHON = $(BIN)/python

INSTALL = $(BIN)/pip install --no-deps
VTENV_OPTS ?= --distribute -p `which python2.7 python2.6 | head -n 1`

BUILD_DIRS = bin build include lib lib64 man share


.PHONY: all test docs build_extras

all: build

$(PYTHON):
	virtualenv $(VTENV_OPTS) .

build: $(PYTHON)
	CYTHON=`pwd`/bin/cython $(BIN)/pip install -r test-requirements.txt
	$(PYTHON) setup.py develop

build_extras: build
	$(BIN)/pip install circus

clean:
	rm -rf $(BUILD_DIRS)

test:
	$(BIN)/pip install tox
	$(BIN)/tox

coverage: build build_extras
	$(BIN)/pip install nose coverage circus mock flake8 paramiko boto unittest2
	$(BIN)/flake8 loads
	LONG=1 $(BIN)/nosetests -s -d -v --cover-html --cover-html-dir=html --with-coverage --cover-erase --cover-package loads loads/tests

bin/sphinx-build:
	bin/pip install Sphinx mozilla_sphinx_theme


docs:  bin/sphinx-build
	cd docs; make html

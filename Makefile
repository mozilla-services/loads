HERE = $(shell pwd)
BIN = $(HERE)/bin
PYTHON = $(BIN)/python

INSTALL = $(BIN)/pip install --no-deps
VTENV_OPTS ?= --distribute

BUILD_DIRS = bin build include lib lib64 man share


.PHONY: all test docs

all: build

$(PYTHON):
	virtualenv $(VTENV_OPTS) .

build: $(PYTHON)
	$(PYTHON) setup.py develop

clean:
	rm -rf $(BUILD_DIRS)

test: build
	$(BIN)/nosetests -s -d -v --with-coverage --cover-package loads loads/tests

bin/sphinx-build:
	bin/pip install Sphinx


docs:  bin/sphinx-build
	cd docs; make html

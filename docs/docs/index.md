# Welcome to FastAPI-Muck
![Logo](img/logo.png)

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI Testing](https://github.com/dtiesling/flask-muck/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/dtiesling/flask-muck/actions/workflows/test.yml)
[![CodeQL](https://github.com/dtiesling/flask-muck/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/dtiesling/flask-muck/actions/workflows/github-code-scanning/codeql)
[![Docs Deploy](https://github.com/dtiesling/flask-muck/actions/workflows/docs.yml/badge.svg)](https://github.com/dtiesling/flask-muck/actions/workflows/docs.yml)
[![types - Mypy](https://img.shields.io/badge/types-Mypy-blue.svg)](https://github.com/python/mypy)
[![Static Badge](https://img.shields.io/badge/FastAPI-v0.100%2B-red)](https://fastapi.tiangolo.com/)
[![License - MIT](https://img.shields.io/badge/license-MIT-9400d3.svg)](https://spdx.org/licenses/)
![downloads](https://img.shields.io/pypi/dm/fastapi-muck)
[![pypi version](https://img.shields.io/pypi/v/fastapi-muck)](https://pypi.org/project/FastAPI-Muck/)

FastAPI-Muck is a batteries-included framework for automatically generating RESTful APIs with Create, Read, 
Update and Delete (CRUD) endpoints in a FastAPI/SqlAlchemy application stack. 

*With FastAPI-Muck you don't have to worry about the CRUD.*

## Features
- Uses a declarative and modular approach to automatically generate CRUD endpoints.
- Built-in search, filter, sort and pagination when listing resources.
- Support for APIs with nested resources (i.e. /api/class/\<ID\>/students).
- Fully compatible with any other FastAPI path operations or routers. Mix & match with your existing views.
- Pre and post callbacks configurable on all manipulation endpoints that allow for arbitrary logic before and after Create, Update or Delete operations.
- Supports Marshmallow and Pydantic for schema definitions.

## License
FastAPI-Muck is distributed under the [MIT](https://spdx.org/licenses/MIT.html) license.


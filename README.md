[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI Testing](https://github.com/dtiesling/flask-muck/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/dtiesling/flask-muck/actions/workflows/test.yml)
[![CodeQL](https://github.com/dtiesling/flask-muck/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/dtiesling/flask-muck/actions/workflows/github-code-scanning/codeql)
[![Docs Deploy](https://github.com/dtiesling/flask-muck/actions/workflows/docs.yml/badge.svg)](https://github.com/dtiesling/flask-muck/actions/workflows/docs.yml)
[![types - Mypy](https://img.shields.io/badge/types-Mypy-blue.svg)](https://github.com/python/mypy)
[![Static Badge](https://img.shields.io/badge/FastAPI-v0.100%2B-red)](https://fastapi.tiangolo.com/)
[![License - MIT](https://img.shields.io/badge/license-MIT-9400d3.svg)](https://spdx.org/licenses/)
![downloads](https://img.shields.io/pypi/dm/fastapi-muck)
[![pypi version](https://img.shields.io/pypi/v/fastapi-muck)](https://pypi.org/project/FastAPI-Muck/)
[![All Contributors](https://img.shields.io/badge/all_contributors-1-orange.svg?style=flat-square)](#contributors-)


# FastAPI-Muck [![Tweet](https://img.shields.io/twitter/url/http/shields.io.svg?style=social)](https://twitter.com/intent/tweet?text=Looking%20for%20a%20FastAPI%20REST%20framework%20that%20generates%20CRUD%20APIs%20and%20Swagger%20docs%20for%20your%20SQLAlchemy%20models%3F%20Check%20out%20FastAPI-Muck&url=https://github.com/dtiesling/flask-muck&via=FastAPIMuck&hashtags=python,fastapi,sqlalchemy,developers)

![Logo](https://dtiesling.github.io/flask-muck/img/logo.png)

With FastAPI-Muck you don't have to worry about the CRUD.

FastAPI-Muck is a declarative framework for automatically generating RESTful APIs with Create, Read, 
Update and Delete (CRUD) endpoints in a FastAPI, SqlAlchemy, Marshmallow/Pydantic application stack in as little as 9 lines of code. Below is example code you might find in a FastAPI app. Please see the [docs](https://dtiesling.github.io/flask-muck/) for full working examples


```python
from fastapi import APIRouter, FastAPI
from fastapi_muck import FastAPIMuckApiView, FastAPIMuck, install_error_pages
import marshmallow as ma
from marshmallow import fields as mf
from sqlalchemy import Column, Integer, String

from myapp import Base, db_session


class MyModel(Base):
    __tablename__ = "my_model"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)


class MyModelSchema(ma.Schema):
    id = mf.Integer(dump_only=True)
    name = mf.String()


class MyModelApiView(FastAPIMuckApiView):
    api_name = "my-model"
    session = db_session
    Model = MyModel
    ResponseSchema = MyModelSchema
    CreateSchema = MyModelSchema
    PatchSchema = MyModelSchema
    UpdateSchema = MyModelSchema
    searchable_columns = [MyModel.name]


app = FastAPI(MUCK_API_URL_PREFIX="/api/")

# Initialize the FastAPIMuck extension if you want all batteries included. 
# Using the extension will autogenerate a Swagger UI browsable api documentation at /apidocs/
muck = FastAPIMuck()
muck.init_app(app)
muck.register_muck_views([MyModelApiView], app=app)

# OR add CRUD views to an existing FastAPI APIRouter for greater flexibility
router = APIRouter(prefix="/api")
MyModelApiView.add_rules_to_router(router)
app.include_router(router)
# Without the extension, install the error pages and url handling the generated views rely on.
install_error_pages(app)


# Either option generates the following endpoints:
# CREATE             | curl -X POST "/api/v1/my-model" -H "Content-Type: application/json" \-d "{\"name\": \"Ayla\"}"
# LIST ALL           | curl -X GET "/api/v1/my-model" -d "Accept: application/json"
# LIST ALL PAGINATED | curl -X GET "/api/v1/my-model?limit=100&offset=50" -d "Accept: application/json"
# SEARCH             | curl -X GET "/api/v1/my-model?search=ayla" -d "Accept: application/json"
# FILTER             | curl -X GET "/api/v1/my-model?filter={\"name\": \"Ayla\"}" -d "Accept: application/json"
# SORT               | curl -X GET "/api/v1/my-model?sort=name" -d "Accept: application/json"
# FETCH              | curl -X GET "/api/v1/my-model/1" -d "Accept: application/json"
# UPDATE             | curl -X PUT "/api/v1/my-model" -H "Content-Type: application/json" \-d "{\"name\": \"Ayla\"}"
# PATCH              | curl -X PATCH "/api/v1/my-model" -H "Content-Type: application/json" \-d "{\"name\": \"Ayla\"}"
# DELETE             | curl -X DELETE "/api/v1/my-model/1"
```

## Features

- Uses a declarative and modular approach to automatically generate CRUD endpoints.
- Built-in search, filter, sort and pagination when listing resources.
- Support for APIs with nested resources (i.e. /api/classrooms/12345/students).
- Fully compatible with any other FastAPI path operations or routers. Mix & match with your existing views.
- Pre and post callbacks configurable on all manipulation endpoints. Allow for adding arbitrary logic before and after Create, Update or Delete operations.
- Supports Marshmallow and Pydantic for schema definitions.
- Dynamically generates OpenAPI specification and Swagger UI. 

## Documentation

Please visit the docs at [https://dtiesling.github.io/flask-muck/](https://dtiesling.github.io/flask-muck/) for explanation of all features and 
advanced usage guides.

There are also examples of complete FastAPI apps using FastAPI-Muck in the [examples](./examples) directory.

## Install

FastAPI-Muck is in Beta and does not have a standard version available for install yet. A standard release on PyPi is coming soon.

`pip install fastapi-muck`

FastAPI-Muck supports Python >= 3.9

## Bug Reports

Submit any issues you may encounter as a  [GitHub issue](https://github.com/dtiesling/flask-muck/issues). Please search for 
similar issues before submitting a new one.

## Questions, Concerns, Ideas, Support, Feature Requests

All non-bug-related discussions such as support or feature requests should be submitted as a
[GitHub Discussion](https://github.com/dtiesling/flask-muck/discussions). 

## License

MIT licensed. See the [LICENSE](./LICENSE) file for more details.

## Contributing

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!

### Development Environment

The development environment is simple and straightforward. Dependencies are managed by Poetry and tests are run 
with pytest. If you would like to test any changes against a live server you can use any apps in the `/examples` directory.

Prerequisites:
- [Python >= 3.9](https://www.python.org/downloads/)
- [Poetry](https://python-poetry.org/docs/#installation)

Install dependencies.
```bash
poetry install
```

Run tests.
```bash
poetry run pytest
```

### Code Style

- Code is formatted using [black](https://black.readthedocs.io/en/stable/).
- Typing is enforced with [mypy](https://mypy.readthedocs.io/en/stable/).


### How should I write my commits?

This project uses [release please](https://github.com/googleapis/release-please) and [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/) for versioning releases.

Per [release-please-action](https://github.com/google-github-actions/release-please-action):

> The most important prefixes you should have in mind are:
>
> - `fix``: which represents bug fixes, and correlates to a SemVer patch.
> - `feat``: which represents a new feature, and correlates to a SemVer minor.
> - `feat!``:, or fix!:, refactor!:, etc., which represent a breaking change (indicated by the !) and will result in a SemVer major.

Any PR with `fix`, `feat`, `docs`, or a conventional commit with an `!` will trigger a release PR when merged.

Other conventional commits such as `chore`, `ci`, `test`, `refactor`, etc will not trigger a release but are encouraged to form a standard around conventional commits in the commit history.

## Contributors ✨

Thanks goes to these wonderful people ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/samdatkins"><img src="https://avatars.githubusercontent.com/u/20110283?v=4?s=100" width="100px;" alt="atkins"/><br /><sub><b>atkins</b></sub></a><br /><a href="https://github.com/dtiesling/flask-muck/commits?author=samdatkins" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/bt-macole"><img src="https://avatars.githubusercontent.com/u/117116981?v=4?s=100" width="100px;" alt="Mason Cole"/><br /><sub><b>Mason Cole</b></sub></a><br /><a href="#infra-bt-macole" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

## Support 

Thanks for the stars! They mean nothing but bring me immense satisfaction. Keep 'em coming.

[![Star History Chart](https://api.star-history.com/svg?repos=dtiesling/flask-muck&type=Date)](https://star-history.com/#dtiesling/flask-muck&Date)

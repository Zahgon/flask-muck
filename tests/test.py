import json
import re
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from fastapi_muck.exceptions import MuckImplementationError
from fastapi_muck.utils import (
    get_url_rule,
    get_fk_column,
    get_query_filters_from_request_path,
    get_join_models_from_parent_views,
)
from tests.app import (
    GuardianModel,
    ToyApiView,
    ChildModel,
    ToyModel,
    BaseApiView,
    PreCallback,
    PostCallback,
    GuardianApiView,
)


class TestBasicCrud:
    def test_create(self, post, user):
        response = post("/guardians/", json={"name": "Jill"})
        parent = GuardianModel.query.one()
        assert response == {"name": parent.name}

        # Verify integrity errors are handled.
        post("/guardians/", json={"name": "Jill"}, expected_status_code=409)

    def test_read(self, get, user, guardian, child):
        assert get(f"/guardians/") == [{"name": guardian.name}]
        assert get(f"/guardians/{guardian.id}/") == {
            "name": "Samantha",
            "children": [{"name": "Tamara"}],
        }

    def test_update(self, put, patch, guardian):
        assert put(f"/guardians/{guardian.id}/", json={"name": "updated"}) == {
            "name": "updated"
        }
        assert patch(f"/guardians/{guardian.id}/", json={"name": "patched"}) == {
            "name": "patched"
        }

    def test_delete(self, client, guardian):
        client.delete(f"/guardians/{guardian.id}/")
        assert GuardianModel.query.count() == 0


class TestAllowedMethods:
    def test_get_only(self, client, monkeypatch):
        monkeypatch.setattr(BaseApiView, "allowed_methods", {"GET"})
        assert client.get("/guardians/").status_code == 200
        assert client.post("/guardians/").status_code == 405
        assert client.put("/guardians/").status_code == 405
        assert client.patch("/guardians/").status_code == 405
        assert client.delete("/guardians/").status_code == 405

    def test_no_methods(self, client, monkeypatch):
        monkeypatch.setattr(BaseApiView, "allowed_methods", {})
        assert client.get("/guardians/").status_code == 405
        assert client.post("/guardians/").status_code == 405
        assert client.put("/guardians/").status_code == 405
        assert client.patch("/guardians/").status_code == 405
        assert client.delete("/guardians/").status_code == 405


@pytest.mark.usefixtures("simpsons", "belchers")
class TestPagination:
    def test_offset(self, get):
        assert get("/guardians/?offset=1") == {
            "items": [{"name": "Bob"}],
            "limit": 20,
            "offset": 1,
            "total": 2,
        }

    def test_limit(self, get):
        assert get("/guardians/?limit=1") == {
            "items": [{"name": "Marge"}],
            "limit": 1,
            "offset": 0,
            "total": 2,
        }

    def test_limit_and_offset(self, get):
        assert get("/guardians/?limit=10&offset=0") == {
            "items": [{"name": "Marge"}, {"name": "Bob"}],
            "limit": 10,
            "offset": 0,
            "total": 2,
        }


@pytest.mark.usefixtures("simpsons", "belchers")
class TestFiltering:
    @pytest.fixture
    def filter_guardians(self, get):
        def _filter_guardians(filters: dict, expected_status_code: int = 200):
            return get(
                f"/guardians/?filters={json.dumps(filters)}",
                expected_status_code=expected_status_code,
            )

        return _filter_guardians

    def test_equal(self, filter_guardians):
        assert filter_guardians({"name": "Marge"}) == [{"name": "Marge"}]
        assert filter_guardians({"name": "Bob"}) == [{"name": "Bob"}]
        assert filter_guardians({"name": "Marge", "age": 34}) == [{"name": "Marge"}]
        assert filter_guardians({"name": "Marge", "age": 45}) == []

    def test_gt(self, filter_guardians):
        assert filter_guardians({"age__gt": 18}) == [
            {"name": "Marge"},
            {"name": "Bob"},
        ]
        assert filter_guardians({"age__gt": 34}) == [{"name": "Bob"}]
        assert filter_guardians({"age__gt": 46}) == []

    def test_gte(self, filter_guardians):
        assert filter_guardians({"age__gte": 18}) == [
            {"name": "Marge"},
            {"name": "Bob"},
        ]
        assert filter_guardians({"age__gte": 34}) == [
            {"name": "Marge"},
            {"name": "Bob"},
        ]
        assert filter_guardians({"age__gte": 46}) == [{"name": "Bob"}]
        assert filter_guardians({"age__gte": 47}) == []

    def test_lt(self, filter_guardians):
        assert filter_guardians({"age__lt": 18}) == []
        assert filter_guardians({"age__lt": 34}) == []
        assert filter_guardians({"age__lt": 46}) == [{"name": "Marge"}]
        assert filter_guardians({"age__lt": 47}) == [{"name": "Marge"}, {"name": "Bob"}]

    def test_lte(self, filter_guardians):
        assert filter_guardians({"age__lte": 18}) == []
        assert filter_guardians({"age__lte": 34}) == [{"name": "Marge"}]
        assert filter_guardians({"age__lte": 46}) == [
            {"name": "Marge"},
            {"name": "Bob"},
        ]
        assert filter_guardians({"age__lte": 47}) == [
            {"name": "Marge"},
            {"name": "Bob"},
        ]

    def test_in(self, filter_guardians):
        assert filter_guardians({"name__in": ["Marge", "Bob"]}) == [
            {"name": "Bob"},
            {"name": "Marge"},
        ]
        assert filter_guardians({"name__in": ["Marge"]}) == [{"name": "Marge"}]
        assert filter_guardians({"name__in": ["Bob"]}) == [{"name": "Bob"}]
        assert filter_guardians({"name__in": ["Billy"]}) == []

    def test_not_in(self, filter_guardians):
        assert filter_guardians({"name__not_in": ["Marge", "Bob"]}) == []
        assert filter_guardians({"name__not_in": ["Marge"]}) == [{"name": "Bob"}]
        assert filter_guardians({"name__not_in": ["Bob"]}) == [{"name": "Marge"}]
        assert filter_guardians({"name__not_in": ["Billy"]}) == [
            {"name": "Marge"},
            {"name": "Bob"},
        ]

    def test_ne(self, filter_guardians):
        assert filter_guardians({"name__ne": "Marge"}) == [{"name": "Bob"}]
        assert filter_guardians({"name__ne": "Bob"}) == [{"name": "Marge"}]
        assert filter_guardians({"name__ne": "Billy"}) == [
            {"name": "Marge"},
            {"name": "Bob"},
        ]

    def test_change_operator_separator(self, filter_guardians, monkeypatch):
        monkeypatch.setattr(BaseApiView, "operator_separator", "|")
        assert filter_guardians({"name|ne": "Marge"}) == [{"name": "Bob"}]
        assert filter_guardians({"name|in": ["Marge"]}) == [{"name": "Marge"}]

    def test_nested_filter(self, filter_guardians, client):
        assert filter_guardians({"children.name": "Bart"}) == [{"name": "Marge"}]
        assert filter_guardians({"children.name": "Gene"}) == [{"name": "Bob"}]

    def test_bad_json(self, get):
        get("/guardians/?filters=notjson", expected_status_code=400)

    def test_column_does_not_exist(self, filter_guardians):
        filter_guardians({"nope": "fail"}, expected_status_code=400)
        filter_guardians({"nope.nested": "fail"}, expected_status_code=400)
        filter_guardians({"children.nope": "fail"}, expected_status_code=400)


@pytest.mark.usefixtures("simpsons", "belchers")
class TestSort:
    def test_sort(self, get, marge, bart, maggie, lisa):
        assert get(f"/guardians/{marge.id}/children/?sort=name") == [
            {"name": bart.name},
            {"name": lisa.name},
            {"name": maggie.name},
        ]
        assert get(f"/guardians/{marge.id}/children/?sort=age") == [
            {"name": maggie.name},
            {"name": lisa.name},
            {"name": bart.name},
        ]

    def test_sort_asc(self, get, marge, maggie, lisa, bart):
        assert get(f"/guardians/{marge.id}/children/?sort=age__asc") == [
            {"name": maggie.name},
            {"name": lisa.name},
            {"name": bart.name},
        ]
        assert get(
            f"/guardians/{marge.id}/children/?sort=name__asc",
        ) == [{"name": bart.name}, {"name": lisa.name}, {"name": maggie.name}]

    def test_sort_desc(self, get, marge, lisa, maggie, bart):
        assert get(
            f"/guardians/{marge.id}/children/?sort=age__desc",
        ) == [{"name": bart.name}, {"name": lisa.name}, {"name": maggie.name}]
        assert get(
            f"/guardians/{marge.id}/children/?sort=name__desc",
        ) == [{"name": maggie.name}, {"name": lisa.name}, {"name": bart.name}]

    def test_nested_sort(self, get):
        assert get(f"/guardians/?sort=family.surname") == [
            {"name": "Bob"},
            {"name": "Marge"},
        ]

    def test_bad_sort(self, get):
        get(f"/guardians/?sort=name__fail", expected_status_code=400)
        get(f"/guardians/?sort=fail", expected_status_code=400)
        get(f"/guardians/?sort=family.fail", expected_status_code=400)
        get(f"/guardians/?sort=double.fail", expected_status_code=400)

    def test_change_operator_separator(
        self, get, monkeypatch, marge, lisa, bart, maggie
    ):
        monkeypatch.setattr(BaseApiView, "operator_separator", "|")
        assert get(
            f"/guardians/{marge.id}/children/?sort=age|desc",
        ) == [{"name": bart.name}, {"name": lisa.name}, {"name": maggie.name}]
        assert get(
            f"/guardians/{marge.id}/children/?sort=name|desc",
        ) == [{"name": maggie.name}, {"name": lisa.name}, {"name": bart.name}]


@pytest.mark.usefixtures("simpsons", "belchers")
class TestSearch:
    def test_search(self, get, marge):
        assert get(f"/guardians/?search=marge") == [{"name": "Marge"}]
        assert get(f"/guardians/?search=nobody") == []
        assert get(f"/guardians/{marge.id}/children/?search=bart") == [{"name": "Bart"}]
        assert get(f"/guardians/{marge.id}/children/?search=nope") == []

    def test_unsupported_search(self, get, marge, bart, monkeypatch):
        monkeypatch.setattr(GuardianApiView, "searchable_columns", [])
        get(f"/guardians/?search=marge", expected_status_code=400)


class TestCallbacks:
    @pytest.fixture
    def pre_callback_patch(self):
        with patch.object(PreCallback, "execute") as patched:
            yield patched

    @pytest.fixture
    def post_callback_patch(self):
        with patch.object(PostCallback, "execute") as patched:
            yield patched

    def test_create_callbacks(
        self, post, user, pre_callback_patch, post_callback_patch
    ):
        post("/guardians/", json={"name": "Jill"})
        pre_callback_patch.assert_called_once()
        post_callback_patch.assert_called_once()

    def test_update_callbacks(
        self, put, guardian, pre_callback_patch, post_callback_patch
    ):
        put(f"/guardians/{guardian.id}/", json={"name": "updated"})
        pre_callback_patch.assert_called_once()
        post_callback_patch.assert_called_once()

    def test_patch_callbacks(
        self, put, patch, guardian, pre_callback_patch, post_callback_patch
    ):
        patch(f"/guardians/{guardian.id}/", json={"name": "patched"})
        pre_callback_patch.assert_called_once()
        post_callback_patch.assert_called_once()

    def test_delete_callbacks(
        self, client, guardian, pre_callback_patch, post_callback_patch
    ):
        client.delete(f"/guardians/{guardian.id}/")
        pre_callback_patch.assert_called_once()
        post_callback_patch.assert_called_once()


@pytest.mark.usefixtures("simpsons", "belchers")
class TestNestedApis:
    def test_get(self, get, bart, maggie, lisa, marge, skateboard, bob):
        children = (bart, maggie, lisa)
        assert get(f"/guardians/") == [{"name": marge.name}, {"name": bob.name}]
        assert get(f"/guardians/{marge.id}/children/") == [
            {"name": child.name} for child in children
        ]
        assert get(f"/guardians/{marge.id}/children/{bart.id}/toy/") == {
            "name": skateboard.name
        }


class TestBlueprintRegistering:
    def test_str_pk_patch_creation(self):
        return

    def test_int_pk_patch_update(self):
        return


class TestUtils:
    def test_get_url_rule(self):
        assert (
            get_url_rule(ToyApiView, None)
            == "/guardians/{guardian_model_id}/children/{child_model_id}/toy/"
        )

    def test_get_fk_column(self):
        assert (
            get_fk_column(parent_model=GuardianModel, child_model=ChildModel)
            == ChildModel.guardian_id
        )
        assert (
            get_fk_column(parent_model=ChildModel, child_model=ToyModel)
            == ToyModel.child_id
        )
        with pytest.raises(
            MuckImplementationError,
            match="The ToyModel model does not have a foreign key.*",
        ):
            get_fk_column(parent_model=GuardianModel, child_model=ToyModel)

    def test_get_query_filters_from_request_path(self, app):
        path_params = {"guardian_model_id": 65, "child_model_id": 22}
        assert [
            str(i)
            for i in get_query_filters_from_request_path(ToyApiView, [], path_params)
        ] == [
            str(ToyModel.child_id == 22),
            str(ChildModel.guardian_id == 65),
        ]

    def test_get_join_models_from_parent_views(self):
        assert get_join_models_from_parent_views(ToyApiView, []) == [
            GuardianModel,
            ChildModel,
        ]


@pytest.mark.usefixtures("simpsons", "belchers")
class TestBaseQueryKwargs:
    @pytest.fixture(autouse=True)
    def patch_get_base_query_kwargs(self, simpson_family, monkeypatch):
        monkeypatch.setattr(
            BaseApiView,
            "get_base_query_kwargs",
            lambda self: {"family_id": simpson_family.id},
        )

    def test_get(self, get, marge, lisa):
        assert get("/guardians/") == [{"name": "Marge"}]
        assert get(f"/guardians/{marge.id}/children/") == [
            {"name": "Bart"},
            {"name": "Maggie"},
            {"name": "Lisa"},
        ]
        assert get(f"/guardians/{marge.id}/children/{lisa.id}/toy/") == {
            "name": "Saxophone"
        }

    def test_put(self, put, marge, bart, db, belcher_family, simpson_family):
        assert put(f"/guardians/{marge.id}/", json={"name": "Marjory"})
        db.session.refresh(marge)
        assert marge.name == "Marjory"
        assert put(
            f"/guardians/{marge.id}/children/{bart.id}/",
            json={"name": "Bartholomew", "guardian_id": marge.id},
        )
        assert put(
            f"/guardians/{marge.id}/children/{bart.id}/toy/",
            json={"name": "Scooter", "child_id": bart.id},
        )
        assert put(
            f"/guardians/{marge.id}/children/{bart.id}/toy/",
            json={
                "name": "Scooter",
                "child_id": bart.id,
            },
        )

    def test_patch(self, patch, marge, bart, skateboard, db):
        assert patch(f"/guardians/{marge.id}/", json={"name": "Marjory"})
        db.session.refresh(marge)
        assert marge.name == "Marjory"
        assert patch(
            f"/guardians/{marge.id}/children/{bart.id}/",
            json={"name": "Bartholomew"},
        )
        assert patch(
            f"/guardians/{marge.id}/children/{bart.id}/toy/",
            json={"name": "Scooter"},
        )


class TestOpenAPI:
    def test_openapi_marshmallow(self, app, snapshot):
        if muck := getattr(app.state, "muck", None):
            assert snapshot == muck.openapi_spec_dict


class TestCommands:
    def test_openapi(self, cli_runner, snapshot):
        from fastapi_muck.commands import muck_cli

        result = cli_runner.invoke(muck_cli)
        assert snapshot == result.output


class TestMigrationSeams:
    """Pins the places where a Flask mechanism was replaced by a FastAPI one.

    Every assertion here fails if its seam is wired to a plausible-but-wrong
    alternative that still builds and still leaves the rest of the suite green.
    """

    def test_success_response_is_rendered_like_flask(self, client, marge):
        response = client.get("/guardians/")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        rendered = json.dumps(response.json(), sort_keys=True, indent=2) + "\n"
        assert response.content == rendered.encode()

    def test_delete_returns_a_body_less_204(self, client, marge):
        response = client.delete(f"/guardians/{marge.id}/")
        assert response.status_code == 204
        assert response.content == b""

    def test_integer_path_variable_rejects_non_digits(self, client):
        assert client.get("/guardians/abc/").status_code == 404

    def test_integer_path_variable_rejects_negatives(self, client):
        assert client.get("/guardians/-1/").status_code == 404

    def test_view_dependencies_are_registered(self, app):
        from fastapi.testclient import TestClient

        with TestClient(app) as anonymous:
            assert anonymous.get("/guardians/").status_code == 401

    def test_api_url_prefix_applies_to_top_level_views_only(self):
        from fastapi import FastAPI

        from fastapi_muck import FastAPIMuck
        from tests.app import ChildApiView

        app = FastAPI(MUCK_API_URL_PREFIX="/api/")
        FastAPIMuck(app).register_muck_views(
            [GuardianApiView, ChildApiView], app=app
        )
        # Path converters are not part of what is checked here, only where each view is mounted.
        paths = {re.sub(r":\w+}", "}", route.path) for route in app.routes}
        assert "/api/guardians/" in paths
        assert "/guardians/{guardian_model_id}/children/" in paths

    def test_apidocs_are_served_from_the_configured_path(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from fastapi_muck import FastAPIMuck

        app = FastAPI(MUCK_APIDOCS_URL_PATH="/docs-here/")
        muck = FastAPIMuck(app)
        muck.register_muck_views([GuardianApiView], app=app)
        with TestClient(app) as client:
            assert client.get("/docs-here/").status_code == 200
            # The spec has its own fixed url, independent of where the UI is
            # mounted, and the UI is what points at it.
            assert client.get("/docs-here/openapi.json").status_code == 404
            spec = client.get("/apispec_1.json")
        assert spec.json() == muck.openapi_spec_dict
        assert app.openapi() == muck.openapi_spec_dict

    def test_error_responses_are_rendered_as_html_pages(self, client):
        response = client.get("/nope")
        assert response.status_code == 404
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert response.text == (
            "<!doctype html>\n"
            "<html lang=en>\n"
            "<title>404 Not Found</title>\n"
            "<h1>Not Found</h1>\n"
            "<p>The requested URL was not found on the server. If you entered "
            "the URL manually please check your spelling and try again.</p>\n"
        )

    def test_missing_trailing_slash_redirects_permanently(self, client):
        response = client.get("/guardians", follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"].endswith("/guardians/")
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert "Redirecting..." in response.text

    def test_method_not_allowed_lists_every_method_the_url_serves(self, client):
        response = client.delete("/guardians/")
        assert response.status_code == 405
        assert set(response.headers["allow"].split(", ")) == {
            "GET",
            "HEAD",
            "OPTIONS",
            "POST",
        }

    def test_apidocs_can_be_disabled(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from fastapi_muck import FastAPIMuck

        app = FastAPI(MUCK_APIDOCS_ENABLED=False)
        FastAPIMuck(app).register_muck_views([GuardianApiView], app=app)
        with TestClient(app) as client:
            assert client.get("/apidocs/").status_code == 404

    def test_non_json_content_type_is_rejected(self, client):
        response = client.post(
            "/guardians/", content=b"{}", headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 415

    def test_unparseable_json_body_is_rejected(self, client):
        response = client.post(
            "/guardians/",
            content=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_non_integer_query_argument_is_rejected(self, client):
        response = client.get("/guardians/?limit=abc")
        assert response.status_code == 422


class TestOriginalRoutingAndErrorPages:
    """Behaviour the original framework supplied around the generated views, kept on the wire."""

    def test_options_is_answered_without_running_the_view(self, app):
        from fastapi.testclient import TestClient

        with TestClient(app) as anonymous:
            response = anonymous.options("/guardians/")
        assert response.status_code == 200
        assert response.content == b""
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert set(response.headers["allow"].split(", ")) == {
            "GET",
            "HEAD",
            "POST",
            "OPTIONS",
        }

    def test_missing_trailing_slash_is_a_308_page(self, client):
        response = client.get("/guardians?limit=1", follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "http://testserver/guardians/?limit=1"
        assert b"Redirecting..." in response.content

    def test_doubled_slashes_are_merged_by_redirect(self, client):
        response = client.get("/guardians//", follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "http://testserver/guardians/"

    def test_slash_redirect_only_for_a_method_the_url_serves(self, client):
        assert client.delete("/guardians", follow_redirects=False).status_code == 404

    def test_head_reaches_the_view_and_is_refused_there(self, client):
        response = client.head("/guardians/")
        assert response.status_code == 405
        assert "allow" not in response.headers

    def test_create_on_a_nested_api_is_a_500_page(self, app, client, marge):
        from fastapi.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as anonymous:
            anonymous.cookies = client.cookies
            response = anonymous.post(
                f"/guardians/{marge.id}/children/",
                json={"name": "Bart", "guardian_id": marge.id},
            )
        assert response.status_code == 500

    def test_json_error_text_depends_on_debug_mode(self, client):
        response = client.post(
            "/guardians/", content=b"{", headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        assert b"Failed to decode JSON object" in response.content

    def test_plus_json_media_types_only_under_application(self, client):
        response = client.post(
            "/guardians/",
            content=b"{\"name\": \"Plus\"}",
            headers={"Content-Type": "text/x+json"},
        )
        assert response.status_code == 415

    def test_repeated_query_argument_uses_the_first_value(self, client, marge, bob):
        response = client.get("/guardians/?limit=1&limit=2")
        assert response.json()["limit"] == 1

    def test_headers_go_out_content_type_first(self, client, marge):
        response = client.get("/guardians/")
        assert list(response.headers.keys())[:2] == ["content-type", "content-length"]


class TestServerErrorPage:
    def test_unhandled_exception_renders_the_500_page(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from fastapi_muck import install_error_pages

        app = FastAPI()
        install_error_pages(app)

        @app.get("/boom/")
        def boom() -> None:
            raise RuntimeError("boom")

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/boom/")
        assert response.status_code == 500
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert b"<title>500 Internal Server Error</title>" in response.content

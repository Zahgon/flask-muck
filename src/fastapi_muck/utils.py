from __future__ import annotations

from typing import Optional, TYPE_CHECKING, Union, Literal

import humps
from apispec import APISpec
from fastapi import APIRouter, FastAPI
from marshmallow import Schema
from pydantic import BaseModel, create_model
from sqlalchemy import Column, inspect
from starlette.convertors import Convertor, register_url_convertor

from fastapi_muck.exceptions import MuckImplementationError
from fastapi_muck.types import SqlaModelType, SqlaModel, JsonDict, SerializerType

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import BinaryExpression

    from fastapi_muck.views import FastAPIMuckApiView


def get_url_path_variable(muck_view: type[FastAPIMuckApiView]) -> str:
    """Generates the string to use for primary key variable in a FastAPI url path."""
    return f"{humps.decamelize(muck_view.Model.__name__)}_id"


def get_url_rule(
    muck_view: type[FastAPIMuckApiView],
    append_rule: Optional[str],
    url_prefix: str = "/",
) -> str:
    """Recursively build the url rule for a MuckApiView by looking at its parent if it exists."""
    rule = muck_view.api_name
    if append_rule:
        rule = f"{rule}/{append_rule}"
    if muck_view.parent:
        rule = f"{{{get_url_path_variable(muck_view.parent)}}}/{rule}"
        return get_url_rule(muck_view.parent, rule)
    if not rule.endswith("/"):
        rule = rule + "/"
    return f"{url_prefix}{rule}"


def get_path_variable_types(
    muck_view: type[FastAPIMuckApiView],
    variable_types: Optional[dict[str, Literal["str", "int"]]] = None,
) -> dict[str, Literal["str", "int"]]:
    """Maps every parent path variable a MuckApiView's url contains to the type its value must be converted to.

    Flask url rules carried the converter in the rule itself; FastAPI paths do not, so the view has to keep the
    mapping around and convert path values itself.
    """
    variable_types = variable_types if variable_types is not None else {}
    if muck_view.parent:
        variable_types[get_url_path_variable(muck_view.parent)] = get_pk_type(
            muck_view.parent.Model
        )
        return get_path_variable_types(muck_view.parent, variable_types)
    return variable_types


def get_fk_column(
    parent_model: SqlaModelType, child_model: SqlaModelType
) -> Optional[Column]:
    """Get the foreign key column for a child model."""
    for column in inspect(child_model).columns:
        if column.foreign_keys:
            for fk in column.foreign_keys:
                if fk.column.table == parent_model.__table__:
                    return column
    raise MuckImplementationError(
        f"The {child_model.__name__} model does not have a foreign key to the {parent_model.__name__} model. "
        "Your MuckApiView parents are not configured correctly."
    )


def get_pk_column(model: SqlaModelType) -> Column:
    """Returns the Primary Key column for a model."""
    return model.__table__.primary_key.columns.values()[0]


def get_pk_type(model: SqlaModelType) -> Literal["str", "int"]:
    """Returns either "int" or "str" to describe the Primary Key type for a model. Used for building URL rules."""
    pk_column = get_pk_column(model)
    if issubclass(pk_column.type.python_type, (int, float)):
        return "int"
    else:
        return "str"


def get_query_filters_from_request_path(
    view: Union[type[FastAPIMuckApiView], FastAPIMuckApiView],
    query_filters: list[BinaryExpression],
    path_params: JsonDict,
) -> list[BinaryExpression]:
    """Recursively builds query kwargs from the request path based on nested MuckApiViews. If the view has no parent
    then nothing is done and original query_kwargs are returned.
    """
    if view.parent:
        child_model = view.Model
        parent_model = view.parent.Model
        fk_column = get_fk_column(parent_model, child_model)
        query_filters.append(
            fk_column == path_params[get_url_path_variable(view.parent)]
        )
        return get_query_filters_from_request_path(
            view.parent, query_filters, path_params
        )
    return query_filters


def get_join_models_from_parent_views(
    view: Union[type[FastAPIMuckApiView], FastAPIMuckApiView],
    join_models: list[SqlaModelType],
) -> list[SqlaModelType]:
    """Recursively builds a list of models that need to be joined in queries based on the view's parents.."""
    if view.parent:
        join_models.append(view.parent.Model)
        return get_join_models_from_parent_views(view.parent, join_models)
    join_models.reverse()
    return join_models


def serialize_model_instance(
    instance: SqlaModel, serializer: SerializerType
) -> JsonDict:
    """Serializes a SQLAlchemy model instance using a Marshmallow schema or Pydantic model."""
    if issubclass(serializer, Schema):
        return serializer().dump(instance)
    elif issubclass(serializer, BaseModel):
        return serializer.model_validate(instance, from_attributes=True).model_dump()
    else:
        raise TypeError(
            f"Schemas must be Marshmallow Schemas or Pydantic BaseModels. {serializer} is a {type(serializer)}"
        )


def pydantic_model_to_optional(model: type[BaseModel]) -> type[BaseModel]:
    """Returns a new model where all fields are Optional. Used for PATCH JSON payload validation."""
    return create_model(  # type: ignore
        model.__class__.__name__,
        **{
            name: (Optional[type_], None)
            for name, type_ in model.__annotations__.items()
        },
    )


def validate_payload(
    payload: JsonDict, serializer: SerializerType, partial: bool = False
) -> JsonDict:
    """Validates JSON payload data and returns it if valid."""
    if issubclass(serializer, Schema):
        return serializer(partial=partial).load(payload)
    elif issubclass(serializer, BaseModel):
        if partial:
            serializer = pydantic_model_to_optional(serializer)
        serializer.model_config["from_attributes"] = True
        return serializer.model_validate(payload).model_dump()
    else:
        raise TypeError(
            f"Schemas must be Marshmallow Schemas or Pydantic BaseModels. {serializer} is a {type(serializer)}"
        )


class _IntegerConvertor(Convertor[int]):
    """Matches a path segment the way the original ``int`` url converter did: one or more digits, no sign."""

    regex = r"\d+"

    def convert(self, value: str) -> int:
        return int(value)

    def to_string(self, value: int) -> str:
        return str(value)


#: Name of the path converter the generated routes use for integer primary keys.
INTEGER_CONVERTER = "muck_int"
register_url_convertor(INTEGER_CONVERTER, _IntegerConvertor())


def _with_converters(
    url_rule: str, variable_types: dict[str, Literal["str", "int"]]
) -> str:
    """Adds the integer converter to every integer path variable of a url rule."""
    for name, type_ in variable_types.items():
        if type_ == "int":
            url_rule = url_rule.replace(f"{{{name}}}", f"{{{name}:{INTEGER_CONVERTER}}}")
    return url_rule


def register_muck_view(
    muck_view: type[FastAPIMuckApiView],
    api: Union[FastAPI, APIRouter],
    api_spec: Optional[APISpec] = None,
    url_prefix: str = "",
) -> None:
    """Registers necessary CRUD endpoints on a given FastAPI app or APIRouter based on the configuration of a
    FastAPIMuckApiView class.

    The routes mirror the original url rules: a ``GET`` route also answers ``HEAD``, path variables of integer keys
    only match digits, and the list and one-to-one routes pass ``resource_id=None`` to the view.
    """
    from fastapi_muck.open_api import update_spec_from_muck_view

    url_rule = get_url_rule(muck_view, None, url_prefix=url_prefix)
    # An APIRouter prefix may not end in "/", so a router cannot carry the root
    # prefix a Blueprint used to supply; the leading slash is restored here.
    if not url_rule.startswith("/"):
        url_rule = f"/{url_rule}"
    update_spec_from_muck_view(
        api_spec=api_spec, url_prefix=url_prefix, muck_view=muck_view
    )
    dependencies = list(muck_view.dependencies)
    variable_types = get_path_variable_types(muck_view)
    collection_rule = _with_converters(url_rule, variable_types)
    variable_types = dict(variable_types)
    variable_types["resource_id"] = get_pk_type(muck_view.Model)
    detail_rule = _with_converters(f"{url_rule}{{resource_id}}/", variable_types)
    name = f"{muck_view.api_name}_api"

    # In the special case that this API represents a ONE-TO-ONE relationship, use / for all methods.
    if muck_view.one_to_one_api:
        api.add_api_route(
            collection_rule,
            muck_view.as_view(defaults={"resource_id": None}),
            name=name,
            methods=["POST", "GET", "HEAD", "PUT", "PATCH", "DELETE"],
            dependencies=dependencies,
            include_in_schema=False,
        )
    else:
        # Create endpoint - POST on /
        api.add_api_route(
            collection_rule,
            muck_view.as_view(),
            name=name,
            methods=["POST"],
            dependencies=dependencies,
            include_in_schema=False,
        )

        # List endpoint - GET on /
        api.add_api_route(
            collection_rule,
            muck_view.as_view(defaults={"resource_id": None}),
            name=name,
            methods=["GET", "HEAD"],
            dependencies=dependencies,
            include_in_schema=False,
        )

        # Detail, Update, Patch, Delete endpoints - GET, PUT, PATCH, DELETE on /<resource_id>
        api.add_api_route(
            detail_rule,
            muck_view.as_view(),
            name=name,
            methods=["GET", "HEAD", "PUT", "PATCH", "DELETE"],
            dependencies=dependencies,
            include_in_schema=False,
        )

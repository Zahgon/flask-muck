from __future__ import annotations

import json
from json import JSONDecodeError
from logging import getLogger
from typing import Optional, Union, Any, Callable, Coroutine

from fastapi import APIRouter, HTTPException, Request, Response, params
from marshmallow import Schema
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, scoped_session
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import (
    BinaryExpression,
    UnaryExpression,
    BooleanClauseList,
    or_,
)

from fastapi_muck.callback import CallbackType
from fastapi_muck.callback import FastAPIMuckCallback
from fastapi_muck.responses import MuckJSONResponse, empty_response
from fastapi_muck.types import (
    SqlaModelType,
    JsonDict,
    ResourceId,
    SqlaModel,
    SerializerType,
)
from fastapi_muck.utils import (
    get_query_filters_from_request_path,
    get_pk_column,
    serialize_model_instance,
    validate_payload,
    register_muck_view,
)

logger = getLogger(__name__)

METHOD_OPERATION_MAP = {
    "POST": "create",
    "PUT": "update",
    "PATCH": "patch",
    "DELETE": "delete",
}


class FastAPIMuckApiView:
    """
    Class representing a FastAPI API view for handling CRUD operations on a SQLAlchemy model.

    Attributes:
        session (scoped_session): The SQLAlchemy scoped session used for database operations.
        api_name (str): The name of the API.
        Model (SqlaModelType): The SQLAlchemy model for the API.
        parent (Optional[type[FastAPIMuckApiView]]): The parent API view if this view is a child API view.

        ResponseSchema (type[Serializer]): The marshmallow schema or Pydantic model  for serializing the response data.
        CreateSchema (Optional[type[Serializer]]): The marshmallow schema or Pydantic model  for validating and serializing create data.
        UpdateSchema (Optional[type[Serializer]]): The marshmallow schema or Pydantic model  for validating and serializing update data.
        PatchSchema (Optional[type[Serializer]]): The marshmallow schema or Pydantic model  for validating and serializing patch data.
        DeleteSchema (Optional[type[Serializer]]): The marshmallow schema or Pydantic model  for validating and serializing delete data.
        DetailSchema (Optional[type[Serializer]]): The marshmallow schema or Pydantic model  for serializing detail data.

        dependencies (list): FastAPI dependencies applied to every route the view registers.

        pre_create_callbacks (list[type[FastAPIMuckCallback]]): A list of pre-create callbacks.
        pre_update_callbacks (list[type[FastAPIMuckCallback]]): A list of pre-update callbacks.
        pre_patch_callbacks (list[type[FastAPIMuckCallback]]): A list of pre-patch callbacks.
        pre_delete_callbacks (list[type[FastAPIMuckCallback]]): A list of pre-delete callbacks.

        post_create_callbacks (list[type[FastAPIMuckCallback]]): A list of post-create callbacks.
        post_update_callbacks (list[type[FastAPIMuckCallback]]): A list of post-update callbacks.
        post_patch_callbacks (list[type[FastAPIMuckCallback]]): A list of post-patch callbacks.
        post_delete_callbacks (list[type[FastAPIMuckCallback]]): A list of post-delete callbacks.

        searchable_columns (list[InstrumentedAttribute]): A list of columns that can be searched.
        default_pagination_limit (int): The default pagination limit.
        one_to_one_api (bool): Indicates whether the API represents a one-to-one relationship.
        allowed_methods (set[str]): A set of allowed HTTP methods.
        operator_separator (str): The separator used in filter operators.
    """

    session: scoped_session
    api_name: str
    Model: SqlaModelType
    parent: Optional[type[FastAPIMuckApiView]] = None

    ResponseSchema: SerializerType
    CreateSchema: Optional[type[Schema]] = None
    UpdateSchema: Optional[type[Schema]] = None
    PatchSchema: Optional[type[Schema]] = None
    DeleteSchema: Optional[type[Schema]] = None
    DetailSchema: Optional[type[Schema]] = None

    dependencies: list[params.Depends] = []

    pre_create_callbacks: list[type[FastAPIMuckCallback]] = []
    pre_update_callbacks: list[type[FastAPIMuckCallback]] = []
    pre_patch_callbacks: list[type[FastAPIMuckCallback]] = []
    pre_delete_callbacks: list[type[FastAPIMuckCallback]] = []

    post_create_callbacks: list[type[FastAPIMuckCallback]] = []
    post_update_callbacks: list[type[FastAPIMuckCallback]] = []
    post_patch_callbacks: list[type[FastAPIMuckCallback]] = []
    post_delete_callbacks: list[type[FastAPIMuckCallback]] = []

    searchable_columns: list[InstrumentedAttribute] = []
    default_pagination_limit: int = 20
    one_to_one_api: bool = False
    allowed_methods: set[str] = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    operator_separator: str = "__"

    def __init__(self, request: Request) -> None:
        self.request = request
        # Path variables arrive already converted: the routes match them with the integer converter the original
        # url rules used, so a value that is not a number never reaches the view.
        self.path_params: JsonDict = dict(request.path_params)

    @classmethod
    def as_view(
        cls, defaults: Optional[JsonDict] = None
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Builds the endpoint FastAPI will call for this view.

        FastAPI resolves its handler arguments from an annotated signature, which a view whose url path is only known
        at registration time cannot provide. The endpoint therefore takes the raw request and the view pulls path
        variables, query arguments and the JSON body out of it by hand.

        As with the original class-based views, the matched path variables plus the route's ``defaults`` are passed
        on to the method handler as keyword arguments.
        """

        async def endpoint(request: Request) -> Response:
            view = cls(request)
            view_args = dict(request.path_params)
            if defaults:
                view_args.update(defaults)
            return await view.dispatch_request(**view_args)

        endpoint.__name__ = f"{cls.api_name}_api"
        return endpoint

    @property
    def query(self) -> Query:
        return self.session.query(self.Model)

    async def dispatch_request(self, **kwargs: Any) -> Response:
        request = self.request
        if request.method.lower() not in [m.lower() for m in self.allowed_methods]:
            raise HTTPException(status_code=405)
        method = request.method.lower()
        handler = getattr(self, method, None)
        if handler is None:
            raise AssertionError(f"Unimplemented method {request.method!r}")
        if method == "get":
            limit, offset, filters, sort, search = self._get_query_arguments()
            result = self.get(
                limit=limit,
                offset=offset,
                filters=filters,
                sort=sort,
                search=search,
                **kwargs,
            )
        else:
            result = await handler(**kwargs)
        data, status_code = result
        if isinstance(data, str):
            # A bare string body went out as an html document, whatever it held.
            return empty_response(data, status_code)
        return MuckJSONResponse(
            content=data, status_code=status_code, debug=request.app.debug
        )

    def _execute_callbacks(
        self,
        resource: SqlaModel,
        kwargs: JsonDict,
        callback_type: CallbackType,
    ) -> None:
        attr = (
            f"{callback_type.value}_{METHOD_OPERATION_MAP[self.request.method]}"
            "_callbacks"
        )
        for callback in getattr(self, attr):
            callback(resource, kwargs).execute()

    def get_base_query_kwargs(self) -> JsonDict:
        """Returns a set of base query args. This can be overridden to add additional kwargs to the base query.
        Useful for multi-tenant apps that need to logically separate resources by client.
        """
        return {}

    def _get_base_query(self) -> Query:
        base_query: Query = self.query
        base_query = base_query.filter(
            *get_query_filters_from_request_path(self, [], self.path_params)
        )
        if query_kwargs := self.get_base_query_kwargs():
            base_query = base_query.filter_by(**query_kwargs)
        return base_query

    def _get_resource(cls, resource_id: Optional[ResourceId]) -> SqlaModel:
        query = cls._get_base_query()
        if cls.one_to_one_api:
            return query.one()
        return query.filter(get_pk_column(cls.Model) == resource_id).one()

    def _get_clean_filter_data(self, filters: str) -> JsonDict:
        try:
            return json.loads(filters)
        except JSONDecodeError:
            raise HTTPException(
                status_code=400, detail=f"Filters [{filters}] is not valid json."
            )

    def _get_query_arguments(
        self,
    ) -> tuple[Optional[int], Optional[int], Optional[str], Optional[str], Optional[str]]:
        """Pulls the list endpoint's query arguments off the request, converting the numeric ones."""
        query_params = self.request.query_params

        def _first(name: str) -> Optional[str]:
            # A repeated argument counts with its first value, as the original argument parser read it.
            values = query_params.getlist(name)
            return values[0] if values else None

        def _integer_argument(name: str) -> Optional[int]:
            raw = _first(name)
            if raw is None:
                return None
            try:
                return int(raw)
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail={"query": {name: ["Not a valid integer."]}},
                )

        return (
            _integer_argument("limit"),
            _integer_argument("offset"),
            _first("filters"),
            _first("sort"),
            _first("search"),
        )

    async def _get_request_json(self) -> Any:
        """Returns the request's JSON body, refusing anything that is not declared and encoded as JSON.

        The body counts as JSON when its media type is ``application/json`` or an ``application/*+json`` type. A body
        that does not decode is a 400 whose page names the decoding error only when the app runs in debug mode.
        """
        content_type = self.request.headers.get("content-type", "")
        mimetype = content_type.split(";")[0].strip().lower()
        is_json = mimetype == "application/json" or (
            mimetype.startswith("application/") and mimetype.endswith("+json")
        )
        if not is_json:
            raise HTTPException(
                status_code=415,
                detail=(
                    "Did not attempt to load JSON data because the request "
                    "Content-Type was not 'application/json'."
                ),
            )
        body = await self.request.body()
        try:
            return json.loads(body)
        except ValueError as e:
            if self.request.app.debug:
                raise HTTPException(
                    status_code=400, detail=f"Failed to decode JSON object: {e}"
                )
            raise HTTPException(status_code=400)

    async def _get_kwargs_from_request_payload(self) -> JsonDict:
        """Creates the correct schema based on request method and returns a sanitized dictionary of kwargs from the
        request json.
        """
        serializer_method_map = {
            "POST": self.CreateSchema,
            "PUT": self.UpdateSchema,
            "PATCH": self.PatchSchema or self.UpdateSchema,
            "DELETE": self.DeleteSchema,
        }
        serializer = serializer_method_map[self.request.method]
        if not serializer:
            raise NotImplementedError
        kwargs = validate_payload(
            payload=await self._get_request_json() or {},
            serializer=serializer,
            partial=self.request.method == "PATCH",
        )
        kwargs.update(self.get_base_query_kwargs())
        return kwargs

    def get(
        self,
        resource_id: Optional[ResourceId],
        limit: Optional[int],
        offset: Optional[int],
        filters: Optional[str],
        sort: Optional[str],
        search: Optional[str],
        **kwargs: Any,
    ) -> tuple[Union[JsonDict, list[JsonDict]], int]:
        if resource_id or self.one_to_one_api:
            resource = self._get_resource(resource_id)
            if hasattr(self, "DetailSchema") and self.DetailSchema:
                return serialize_model_instance(resource, self.DetailSchema), 200
            else:
                return (
                    serialize_model_instance(resource, self.ResponseSchema),
                    200,
                )
        else:
            query = self._get_base_query()
            query_filters: list[Any] = []
            join_models: set[SqlaModelType] = set()
            if filters:
                _filters = self._get_clean_filter_data(filters)
                query_filters, _join_models = self._get_query_filters(_filters)
                join_models.update(_join_models)

            # Get order by from request
            order_by = None
            if sort:
                order_by, _join_models = self._get_query_order_by(sort)
                join_models.update(_join_models)

            if search:
                search_filter, _join_models = self._get_query_search_filter(search)
                join_models.update(_join_models)
                if search_filter is not None:
                    query_filters.append(search_filter)

            # Apply joins, filters and order by to the query.
            for model in join_models:
                if model != self.Model:
                    query = query.outerjoin(model)
            if query_filters:
                query = query.filter(*query_filters)
            if order_by is not None:
                query = query.order_by(order_by)
            query = query.distinct()

            # If offset or limit were included in the query params return paginated response object else return a flat
            # list of all items.
            response_data: Union[JsonDict, list[JsonDict]]
            if offset or limit:
                query_limit = limit or self.default_pagination_limit
                query_offset = offset or 0
                resources = query.limit(query_limit).offset(query_offset).all()
                response_data = {
                    "limit": query_limit,
                    "offset": query_offset,
                    "total": query.count(),
                    "items": [
                        serialize_model_instance(r, self.ResponseSchema)
                        for r in resources
                    ],
                }
            else:
                resources = query.all()
                response_data = [
                    serialize_model_instance(r, self.ResponseSchema) for r in resources
                ]
            return response_data, 200

    def _create_resource(self, kwargs: JsonDict) -> SqlaModel:
        resource = self.Model(**kwargs)
        self.session.add(resource)
        self.session.flush()
        return resource

    def _update_resource(self, resource: SqlaModel, kwargs: JsonDict) -> SqlaModel:
        for attr, value in kwargs.items():
            setattr(resource, attr, value)
        return resource

    async def post(self) -> tuple[JsonDict, int]:
        if not self.CreateSchema:
            raise NotImplementedError()
        kwargs = self.get_base_query_kwargs()
        data = await self._get_kwargs_from_request_payload()
        kwargs.update(data)
        try:
            resource = self._create_resource(kwargs)
        except IntegrityError as e:
            self.session.rollback()
            raise HTTPException(status_code=409, detail=str(e))
        self._execute_callbacks(resource, kwargs, CallbackType.pre)
        self.session.commit()
        self._execute_callbacks(resource, kwargs, CallbackType.post)
        return serialize_model_instance(resource, self.ResponseSchema), 201

    async def put(self, resource_id: ResourceId, **kwargs: Any) -> tuple[JsonDict, int]:
        if not self.UpdateSchema:
            raise NotImplementedError()
        resource = self._get_resource(resource_id)
        kwargs = await self._get_kwargs_from_request_payload()
        resource = self._update_resource(resource, kwargs)
        self._execute_callbacks(resource, kwargs, CallbackType.pre)
        self.session.commit()
        self._execute_callbacks(resource, kwargs, CallbackType.post)
        return serialize_model_instance(resource, self.ResponseSchema), 200

    async def patch(
        self, resource_id: ResourceId, **kwargs: Any
    ) -> tuple[JsonDict, int]:
        if not self.PatchSchema:
            raise NotImplementedError()
        resource = self._get_resource(resource_id)
        kwargs = await self._get_kwargs_from_request_payload()
        resource = self._update_resource(resource, kwargs)
        self._execute_callbacks(resource, kwargs, CallbackType.pre)
        self.session.commit()
        self._execute_callbacks(resource, kwargs, CallbackType.post)
        return serialize_model_instance(resource, self.ResponseSchema), 200

    async def delete(self, resource_id: ResourceId, **kwargs: Any) -> tuple[str, int]:
        resource = self._get_resource(resource_id)
        kwargs = {}
        if self.DeleteSchema:
            kwargs = await self._get_kwargs_from_request_payload()
        self.session.delete(resource)
        self._execute_callbacks(resource, kwargs, CallbackType.pre)
        self.session.commit()
        self._execute_callbacks(resource, kwargs, CallbackType.post)
        return "", 204

    def _get_query_filters(
        self, filters: JsonDict
    ) -> tuple[list[BinaryExpression], set[SqlaModelType]]:
        """Translates a dictionary of column names and values into a list of SQLA query filters.
        Also returns a list of models that should be joined to the base query.
        """
        query_filters: list[BinaryExpression] = []
        join_models: set[SqlaModelType] = set()
        for column_name, value in filters.items():
            # Get operator.
            operator = None
            if self.operator_separator in column_name:
                column_name, operator = column_name.split(self.operator_separator)

            # Handle nested filters.
            if "." in column_name:
                relationship_name, column_name = column_name.split(".")
                field = getattr(self.Model, relationship_name, None)
                if not field:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{column_name} is not a valid filter field. The relationship does not exist.",
                    )
                _Model = field.property.mapper.class_
                join_models.add(_Model)
            else:
                _Model = self.Model

            if not (column := getattr(_Model, column_name, None)):
                raise HTTPException(
                    status_code=400,
                    detail=f"{column_name} is not a valid filter field.",
                )

            if operator == "gt":
                _filter = column > value
            elif operator == "gte":
                _filter = column >= value
            elif operator == "lt":
                _filter = column < value
            elif operator == "lte":
                _filter = column <= value
            elif operator == "ne":
                _filter = column != value
            elif operator == "in":
                _filter = column.in_(value)
            elif operator == "not_in":
                _filter = column.not_in(value)
            else:
                _filter = column == value
            query_filters.append(_filter)
        return query_filters, join_models

    def _get_query_order_by(
        self, sort: str
    ) -> tuple[Optional[UnaryExpression], set[SqlaModelType]]:
        if self.operator_separator in sort:
            column_name, direction = sort.split(self.operator_separator)
        else:
            column_name, direction = sort, "asc"

        # Handle nested fields.
        join_models = set()
        if "." in column_name:
            relationship_name, column_name = column_name.split(".")
            field = getattr(self.Model, relationship_name, None)
            if not field:
                raise HTTPException(
                    status_code=400,
                    detail=f"{column_name} is not a valid sort field.",
                )
            _Model = field.property.mapper.class_
            join_models.add(_Model)
        else:
            _Model = self.Model

        if hasattr(_Model, column_name):
            column = getattr(_Model, column_name)
            if direction == "asc":
                order_by = column.asc()
            elif direction == "desc":
                order_by = column.desc()
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sort direction: {direction}. Must asc or desc",
                )
        else:
            raise HTTPException(
                status_code=400, detail=f"{column_name} is not a valid sort field."
            )
        return order_by, join_models

    def _get_query_search_filter(
        self, search_string: str
    ) -> tuple[Optional[BooleanClauseList], set[SqlaModelType]]:
        """Returns SQLA full text search filters for the search_term provided."""
        if not self.searchable_columns:
            raise HTTPException(
                status_code=400, detail="Search is not supported on this endpoint."
            )
        searches = []
        join_models = set()
        for column in self.searchable_columns:
            join_models.add(column.parent.class_)
            searches.append(column.ilike(f"%{search_string}%"))
        if len(searches) == 1:
            return searches[0], join_models
        else:
            return or_(*searches), join_models

    @classmethod
    def add_rules_to_router(cls, router: APIRouter) -> None:
        """Registers necessary CRUD endpoints on an APIRouter based on the configuration of a FastAPIMuckApiView class."""
        register_muck_view(muck_view=cls, api=router, api_spec=None)

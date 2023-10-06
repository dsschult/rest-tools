"""Test server/arghandler.py."""

# pylint: disable=W0212,W0621

import json
from typing import Any, Dict, List, Tuple
from unittest.mock import Mock

import pytest
import requests
import tornado.web
from rest_tools.server.arghandler import ArgumentHandler, ArgumentSource
from rest_tools.server.handler import RestHandler
from tornado import httputil
from wipac_dev_tools import strtobool

QUERY_ARGUMENTS = "query-arguments"
JSON_BODY_ARGUMENTS = "json-body-arguments"


def setup_argument_handler(
    argument_source: str,
    args: Dict[str, Any] | List[Tuple[Any, Any]],
) -> ArgumentHandler:
    """Load data and return `ArgumentHandler` instance."""
    if argument_source == QUERY_ARGUMENTS:
        req = requests.Request(url="https://foo.aq/all", params=args).prepare()
        print("\n request:")
        print(req.url)
        print()
        rest_handler = RestHandler(
            application=Mock(),
            request=httputil.HTTPServerRequest(
                uri=req.url,
                headers=req.headers,
            ),
        )
        return ArgumentHandler(ArgumentSource.QUERY_ARGUMENTS, rest_handler)

    elif argument_source == JSON_BODY_ARGUMENTS:
        req = requests.Request(url="https://foo.aq/all", json=args).prepare()
        print("\n request:")
        print(req.url)
        print(req.body)
        print(req.headers)
        print()
        rest_handler = RestHandler(
            application=Mock(),
            request=httputil.HTTPServerRequest(
                uri=req.url,
                body=req.body,
                headers=req.headers,
            ),
        )
        rest_handler.request._parse_body()  # normally called when request REST method starts
        print("\n rest-handler:")
        print(rest_handler.request.body)
        print(json.loads(rest_handler.request.body))
        print()
        return ArgumentHandler(ArgumentSource.JSON_BODY_ARGUMENTS, rest_handler)

    else:
        raise ValueError(f"Invalid argument_source: {argument_source}")


########################################################################################


@pytest.mark.parametrize(
    "argument_source",
    [QUERY_ARGUMENTS, JSON_BODY_ARGUMENTS],
)
def test_100__defaults(argument_source: str) -> None:
    """Test `argument_source` arguments with default."""
    default: Any

    for default in [None, "a-string", 100, 50.5]:
        print(default)
        arghand = setup_argument_handler(argument_source, {})
        arghand.add_argument("myarg", default=default)
        args = arghand.parse_args()
        assert default == args.myarg

    # w/ typing
    for default in ["a-string", 100, 50.5]:
        print(default)
        arghand = setup_argument_handler(argument_source, {})
        arghand.add_argument("myarg", default=default, type=type(default))
        args = arghand.parse_args()
        assert default == args.myarg


@pytest.mark.parametrize(
    "argument_source",
    [QUERY_ARGUMENTS, JSON_BODY_ARGUMENTS],
)
def test_110__no_default_no_typing(argument_source: str) -> None:
    """Test `argument_source` arguments."""
    args = {
        "foo": "-10",
        "bar": "True",
        "bat": "2.5",
        "baz": "Toyota Corolla",
        "boo": "False",
    }
    if argument_source == JSON_BODY_ARGUMENTS:
        args.update(
            {
                "dicto": {"abc": 123},
                "listo": [1, 2, 3],
                "compoundo": [{"apple": True}, {"banana": 951}, {"cucumber": False}],
            }
        )

    # set up ArgumentHandler
    arghand = setup_argument_handler(argument_source, args)

    for arg, _ in args.items():
        print()
        print(arg)
        arghand.add_argument(arg)
    outargs = arghand.parse_args()

    # grab each
    for arg, val in args.items():
        print()
        print(arg)
        print(val)
        assert val == getattr(outargs, arg.replace("-", "_"))


@pytest.mark.parametrize(
    "argument_source",
    [QUERY_ARGUMENTS, JSON_BODY_ARGUMENTS],
)
def test_111__no_default_with_typing(argument_source: str) -> None:
    """Test `request.arguments` arguments."""

    def custom_type(_: Any) -> Any:
        return "this could be anything but it's just a string"

    args = {
        "foo": ("-10", int),
        #
        "bar": ("True", bool),
        "boo": ("False", bool),
        "ghi": ("no", bool),
        "jkl": ("1", bool),
        "mno": ("0", bool),
        #
        "bat": ("2.5", float),
        "abc": ("2", float),
        #
        "baz": ("Toyota Corolla", str),
        "def": ("1000", str),
        #
        "zzz": ("yup", custom_type),
    }
    if argument_source == JSON_BODY_ARGUMENTS:
        args.update(
            {
                "dicto": ({"abc": 123}, dict),
                "dicto-as-list": ({"def": 456}, list),
                "listo": ([1, 2, 3], list),
                "compoundo": (
                    [{"apple": True}, {"banana": 951}, {"cucumber": False}],
                    list,
                ),
                "sure": (
                    [{"apple": True}, {"banana": 951}, {"cucumber": False}],
                    custom_type,
                ),
            }
        )

    # set up ArgumentHandler
    arghand = setup_argument_handler(
        argument_source, {arg: val for arg, (val, _) in args.items()}
    )
    for arg, (_, typ) in args.items():
        print()
        print(arg)
        arghand.add_argument(arg, type=typ)
    outargs = arghand.parse_args()

    # grab each
    for arg, (val, typ) in args.items():
        print()
        print(arg)
        print(val)
        print(typ)
        if typ == bool:
            assert getattr(outargs, arg.replace("-", "_")) == strtobool(val)
        else:
            assert getattr(outargs, arg.replace("-", "_")) == typ(val)


@pytest.mark.parametrize(
    "argument_source",
    [QUERY_ARGUMENTS, JSON_BODY_ARGUMENTS],
)
def test_112__no_default_with_typing__error(argument_source: str) -> None:
    """Test `argument_source` arguments."""

    def custom_type(val: Any) -> Any:
        raise ValueError("x")

    args = {
        "foo": ("hank", int),
        "bat": ("2.5", int),
        "baz": ("9e-33", int),
        #
        "bar": ("idk", bool),
        "boo": ("2", bool),
        #
        "abc": ("222.111.333", float),
        #
        "zzz": ("yup", custom_type),
    }
    if argument_source == JSON_BODY_ARGUMENTS:
        args.update(
            {
                "dicto": ({"abc": 123}, int),
                "listo": ([1, 2, 3], int),
                "compoundo": (
                    [{"apple": True}, {"banana": 951}, {"cucumber": False}],
                    object,
                ),
                "nope": (
                    [{"apple": True}, {"banana": 951}, {"cucumber": False}],
                    custom_type,
                ),
            }
        )

    for arg, (val, typ) in args.items():
        print()
        print(arg)
        print(val)
        print(typ)
        arghand = setup_argument_handler(argument_source, {arg: val})
        arghand.add_argument(arg, type=typ)
        with pytest.raises(tornado.web.HTTPError) as e:
            arghand.parse_args()
        assert str(e.value) == f"HTTP 400: argument {arg}: invalid type"


@pytest.mark.parametrize(
    "argument_source",
    [QUERY_ARGUMENTS, JSON_BODY_ARGUMENTS],
)
def test_120__missing_argument(argument_source: str) -> None:
    """Test `argument_source` arguments error case."""

    # set up ArgumentHandler
    arghand = setup_argument_handler(argument_source, {})
    arghand.add_argument("reqd")

    # Missing Required Argument
    with pytest.raises(tornado.web.HTTPError) as e:
        arghand.parse_args()
    assert str(e.value) == "HTTP 400: the following arguments are required: reqd"


@pytest.mark.parametrize(
    "argument_source",
    [QUERY_ARGUMENTS, JSON_BODY_ARGUMENTS],
)
def test_121__missing_argument(argument_source: str) -> None:
    """Test `argument_source` arguments error case."""

    # set up ArgumentHandler
    arghand = setup_argument_handler(argument_source, {"foo": "val"})
    arghand.add_argument("reqd")
    arghand.add_argument("foo")
    arghand.add_argument("bar")

    # Missing Required Argument
    with pytest.raises(tornado.web.HTTPError) as e:
        arghand.parse_args()
    assert str(e.value) == "HTTP 400: the following arguments are required: reqd, bar"


@pytest.mark.parametrize(
    "argument_source",
    [QUERY_ARGUMENTS, JSON_BODY_ARGUMENTS],
)
def test_130__duplicates(argument_source: str) -> None:
    """Test `argument_source` arguments with duplicate keys."""

    args = [
        ("foo", "22"),
        ("foo", "44"),
        ("foo", "66"),
        ("foo", "88"),
        ("bar", "abc"),
        ("baz", "hello world!"),
        ("baz", "hello mars!"),
    ]
    if argument_source == JSON_BODY_ARGUMENTS:
        pass  # no special data since duplicates not allowed for json

    # set up ArgumentHandler
    arghand = setup_argument_handler(argument_source, args)
    arghand.add_argument("foo", type=int, nargs="*")
    arghand.add_argument("baz", type=str, nargs="*")
    arghand.add_argument("bar")

    # duplicates not allowed for json
    if argument_source == JSON_BODY_ARGUMENTS:
        with pytest.raises(tornado.web.HTTPError) as e:
            arghand.parse_args()
        assert str(e.value) == "HTTP 400: JSON-encoded requests body must be a 'dict'"
    # but they are for query args!
    else:
        outargs = arghand.parse_args()
        print(outargs)
        # grab each
        assert outargs.foo == [22, 44, 66, 88]
        assert outargs.baz == ["hello world!", "hello mars!"]
        assert outargs.bar == "abc"


@pytest.mark.parametrize(
    "argument_source",
    [QUERY_ARGUMENTS, JSON_BODY_ARGUMENTS],
)
def test_140__extra_argument(argument_source: str) -> None:
    """Test `argument_source` arguments error case."""

    # set up ArgumentHandler
    args = {
        "foo": "val",
        "reqd": "2",
        "xtra": 1,
        "another": True,
    }
    if argument_source == JSON_BODY_ARGUMENTS:
        args["another"] = [{"apple": True}, {"banana": 951}, {"cucumber": False}]

    arghand = setup_argument_handler(argument_source, args)
    arghand.add_argument("reqd")
    arghand.add_argument("foo")

    # Missing Required Argument
    with pytest.raises(tornado.web.HTTPError) as e:
        arghand.parse_args()
    assert str(e.value) == "HTTP 400: unrecognized arguments: xtra, another"


@pytest.mark.parametrize(
    "argument_source",
    [QUERY_ARGUMENTS, JSON_BODY_ARGUMENTS],
)
def test_141__extra_argument_with_duplicates(argument_source: str) -> None:
    """Test `argument_source` arguments error case."""

    # set up ArgumentHandler
    args = [
        ("foo", "val"),
        ("reqd", "2"),
        ("xtra", 1),
        ("another", True),
        ("another", False),
        ("another", "who knows"),
    ]
    if argument_source == JSON_BODY_ARGUMENTS:
        pass  # no special data since duplicates not allowed for json

    arghand = setup_argument_handler(argument_source, args)
    arghand.add_argument("reqd")
    arghand.add_argument("foo")

    # Missing Required Argument...

    # duplicates not allowed for json
    if argument_source == JSON_BODY_ARGUMENTS:
        with pytest.raises(tornado.web.HTTPError) as e:
            arghand.parse_args()
        assert str(e.value) == "HTTP 400: JSON-encoded requests body must be a 'dict'"
    # but they are for query args!
    else:
        with pytest.raises(tornado.web.HTTPError) as e:
            arghand.parse_args()
        assert str(e.value) == "HTTP 400: unrecognized arguments: xtra, another"

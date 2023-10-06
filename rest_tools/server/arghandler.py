"""Handle argument parsing, defaulting, and casting."""


import argparse
import contextlib
import io
import json
import logging
import re
import time
from itertools import chain
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union, cast

import tornado.web
from tornado.escape import to_unicode
from wipac_dev_tools import strtobool

from ..utils.json_util import json_decode

T = TypeVar("T")

LOGGER = logging.getLogger(__name__)


class _NoDefaultValue:  # pylint: disable=R0903
    """Signal no default value, AKA argument is required."""


NO_DEFAULT = _NoDefaultValue()


def _parse_json_body_arguments(request_body: bytes) -> Dict[str, Any]:
    """Return the request-body JSON-decoded, but only if it's a `dict`."""
    json_body = json_decode(request_body)

    if isinstance(json_body, dict):
        return cast(Dict[str, Any], json_body)
    return {}


class _InvalidArgumentError(Exception):
    """Raise when an argument-validation fails."""


def _make_400_error(arg_name: str, error: Exception) -> tornado.web.HTTPError:
    if isinstance(error, tornado.web.MissingArgumentError):
        error.reason = (
            f"`{arg_name}`: (MissingArgumentError) required argument is missing"
        )
        error.log_message = ""
        return error
    else:
        return tornado.web.HTTPError(400, reason=f"`{arg_name}`: {error}")


ARGUMENTS_REQUIRED_PATTERN = re.compile(
    r".+: error: (the following arguments are required: .+)"
)
UNRECOGNIZED_ARGUMENTS_PATTERN = re.compile(r".+ error: (unrecognized arguments:) (.+)")
INVALID_VALUE_PATTERN = re.compile(r"(argument .+: invalid) .+ value: '.+'")


class ArgumentHandler(argparse.ArgumentParser):
    """Helper class for argument parsing, defaulting, and casting.

    Like argparse.ArgumentParser, but for REST & JSON-body arguments.
    """

    def __init__(self, source: dict[str, Any] | bytes) -> None:
        super().__init__(exit_on_error=False)
        self.source = source

    def add_argument(  # type: ignore[override]
        self,
        name: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Add an argument -- like argparse.add_argument with additions.

        See https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
        """
        if kwargs.get("type") == bool:
            kwargs["type"] = strtobool

        if "default" not in kwargs:
            if "required" not in kwargs:
                # no default? then it's required
                kwargs["required"] = True
            elif not kwargs["required"]:
                raise ValueError(
                    f"Argument '{name}' marked as not required but no default was provided."
                )

        super().add_argument(f"--{name}", *args, **kwargs)

    @staticmethod
    def _translate_error(
        exc: Union[Exception, SystemExit],
        captured_stderr: str,
    ) -> str:
        """Translate argparse-style error to a message str for HTTPError."""
        print(exc)  # TODO
        print(captured_stderr)  # TODO

        # errors not covered by 'exit_on_error=False' (in __init__)
        if isinstance(exc, SystemExit):
            # MISSING ARG
            if match := ARGUMENTS_REQUIRED_PATTERN.search(captured_stderr):
                return match.group(1).replace(" --", " ")
            # EXTRA ARG
            elif match := UNRECOGNIZED_ARGUMENTS_PATTERN.search(captured_stderr):
                args = (
                    k.replace("--", "")
                    for k in match.group(2).split()
                    if k.startswith("--")
                )
                return f"{match.group(1)} {', '.join(args)}"

        # INVALID VALUE -- not a system error bc 'exit_on_error=False' (in __init__)
        elif isinstance(exc, argparse.ArgumentError):
            if match := INVALID_VALUE_PATTERN.search(str(exc)):
                return f"{match.group(1).replace('--', '')} type"

        # fall-through -- log unknown exception
        ts = time.time()  # log timestamp to aid debugging
        LOGGER.exception(exc)
        LOGGER.error(f"error timestamp: {ts}")
        LOGGER.error(captured_stderr)
        return f"Unknown argument-handling error ({ts})"

    def parse_args(self) -> argparse.Namespace:  # type: ignore[override]
        """Get the args -- like argparse.parse_args but parses a dict."""
        if isinstance(self.source, bytes):
            # TODO - does putting in values verbatim work? or do we need to filter primitive_types?
            # args_dict: dict[str, Any] = json.loads(self.source)
            arg_strings = []
            for key, val in json.loads(self.source).items():
                arg_strings.append(f"--{key}")
                arg_strings.append(val)
        else:
            # args_dict = {
            #     k: " ".join(to_unicode(v) for v in vlist)
            #     for k, vlist in self.source.items()
            # }
            arg_strings = []
            for key, vlist in self.source.items():
                arg_strings.append(f"--{key}")
                arg_strings.extend(to_unicode(v) for v in vlist)

        # args_tuples = [(f"--{k}", v) for k, v in args_dict.items()]
        # arg_strings = " ".join(list(chain.from_iterable(args_tuples))).split()
        print(arg_strings)  # TODO

        # parse
        with contextlib.redirect_stderr(io.StringIO()) as f:
            try:
                return super().parse_args(args=arg_strings)
            except (Exception, SystemExit) as e:
                exc = e
                captured_stderr = f.getvalue()
        # handle exception outside of context manager
        msg = self._translate_error(exc, captured_stderr)
        raise tornado.web.HTTPError(400, reason=msg)

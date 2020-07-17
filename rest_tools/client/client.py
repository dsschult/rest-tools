"""
A simple REST json client using `requests`_ for the http connection.

.. _requests: http://docs.python-requests.org

The REST protocol is built on http(s), with the body containing
a json-encoded dictionary as necessary.
"""

import os
import logging
import asyncio

import requests

from .session import AsyncSession,Session
from .json_util import json_encode,json_decode

from ..server import OpenIDAuth

def to_str(s):
    if isinstance(s, bytes):
        return s.decode('utf-8')
    return s

class RestClient:
    def __init__(self, address, token=None, timeout=60.0, retries=10, **kwargs):
        self.address = address
        self.token = token
        self.timeout = timeout
        self.retries = retries
        self.kwargs = kwargs
        self.session = None

        self.open() # start session

    def open(self, sync=False):
        """Open the http session"""
        logging.info('establish REST http session')
        if sync:
            self.session = Session(self.retries)
        else:
            self.session = AsyncSession(self.retries)
        self.session.headers = {
            'Content-Type': 'application/json',
        }
        if self.token:
            self.session.headers['Authorization'] = 'Bearer '+to_str(self.token)
        if 'username' in self.kwargs and 'password' in self.kwargs:
            self.session.auth = (self.kwargs['username'], self.kwargs['password'])
        if 'sslcert' in self.kwargs:
            if 'sslkey' in self.kwargs:
                self.session.cert = (self.kwargs['sslcert'], self.kwargs['sslkey'])
            else:
                self.session.cert = self.kwargs['sslcert']
        if 'cacert' in self.kwargs:
            self.session.verify = self.kwargs['cacert']

    def close(self):
        """Close the http session"""
        logging.info('close REST http session')
        if self.session:
            self.session.close()

    def _prepare(self, method, path, args=None):
        """Internal method for preparing requests"""
        if not args:
            args = {}
        if path.startswith('/'):
            path = path[1:]
        url = os.path.join(self.address, path)
        kwargs = {
            'timeout': self.timeout,
        }
        if method in ('GET','HEAD'):
            # args should be urlencoded
            kwargs['params'] = args
        else:
            kwargs['json'] = args
        return (url, kwargs)

    def _decode(self, content):
        """Internal method for translating response from json"""
        if not content:
            logging.info('request returned empty string')
            return None
        try:
           return json_decode(content)
        except Exception:
            logging.info('json data: %r', content)
            raise

    async def request(self, method, path, args=None):
        """
        Send request to REST Server.

        Async request - use with coroutines.

        Args:
            method (str): the http method
            path (str): the url path on the server
            args (dict): any arguments to pass

        Returns:
            dict: json dict or raw string
        """
        url, kwargs = self._prepare(method, path, args)
        try:
            r = await asyncio.wrap_future(self.session.request(method, url, **kwargs))
            r.raise_for_status()
            return self._decode(r.content)
        except requests.exceptions.HTTPError as e:
            if method == 'DELETE' and e.response.status_code == 404:
                raise # skip the logging for an expected error
            logging.info('bad request: %s %s %r', method, path, args, exc_info=True)
            raise

    def request_seq(self, method, path, args=None):
        """
        Send request to REST Server.

        Sequential version of `request`.

        Args:
            method (str): the http method
            path (str): the url path on the server
            args (dict): any arguments to pass

        Returns:
            dict: json dict or raw string
        """
        url, kwargs = self._prepare(method, path, args)
        s = self.session
        try:
            self.open(sync=True)
            r = self.session.request(method, url, **kwargs)
            r.raise_for_status()
            return self._decode(r.content)
        finally:
            self.session = s

class OpenIDRestClient(RestClient):
    """
    A REST client that can handle token refresh using OpenID .well-known auto-discovery.

    Args:
        address (str): base address of REST API
        token_url (str): base address of token service
        refresh_token (str): initial refresh token
        client_id (str): client id
        client_secret (str): client secret
        timeout (int): request timeout
        retries (int): number of retries to attempt
    """
    def __init__(self, address, token_url, refresh_token, client_id, client_secret, **kwargs):
        super().__init__(address, **kwargs)
        self.auth = OpenIDAuth(token_url)
        self.client_id = client_id
        self.client_secret = client_secret

        self.access_token = None
        self.refresh_token = refresh_token
        self._get_token()

    def _get_token(self):
        if self.access_token:
            # check if expired
            try:
                self.auth.validate(self.access_token)
                return
            except Exception:
                self.access_token = None
                logging.debug('OpenID token expired')

        if self.refresh_token:
            # try the refresh token
            args = {
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
            }

            try:
                r = requests.post(self.auth.token_url, data=args)
                r.raise_for_status()
                req = r.json()
            except Exception:
                self.refresh_token = None
            else:
                logging.debug('OpenID token refreshed')
                self.access_token = req['access_token']
                self.refresh_token = req['refresh_token'] if 'refresh_token' in req else None
                return

        raise Exception('No token available')

    def _prepare(self, *args, **kwargs):
        self._get_token()
        if self.access_token:
            self.session.headers['Authorization'] = 'Bearer '+to_str(self.access_token)
        return super()._prepare(*args, **kwargs)

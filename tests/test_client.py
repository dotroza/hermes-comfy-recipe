import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from plugin import comfy_client as cc

class ClientTests(unittest.TestCase):
    def test_http_error_body_is_closed(self):
        body=io.BytesIO(b'conflict')
        error=HTTPError('http://test/',409,'Conflict',{},body)
        with patch.object(cc.request,'urlopen',side_effect=error):
            with self.assertRaises(cc.ComfyError): cc.get_json('http://test','/api/userdata')
        self.assertTrue(body.closed, 'HTTP error response leaked an open body')

    def test_fresh_install_without_workflows_dir_lists_nothing(self):
        # A brand-new ComfyUI has no user/default/workflows yet: it answers 404 "Directory not found".
        error=HTTPError('http://test/',404,'Not Found',{},io.BytesIO(b'Directory not found'))
        with patch.object(cc.request,'urlopen',side_effect=error):
            self.assertEqual(cc.list_workflows('http://test'), [])

    def test_other_listing_errors_still_raise(self):
        error=HTTPError('http://test/',500,'Server Error',{},io.BytesIO(b'boom'))
        with patch.object(cc.request,'urlopen',side_effect=error):
            with self.assertRaises(cc.ComfyError): cc.list_workflows('http://test')

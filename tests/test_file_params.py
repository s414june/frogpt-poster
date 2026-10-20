import base64
import io
import os
import unittest
from unittest.mock import patch
from urllib.error import URLError

from PIL import Image
from gpt_package import mcp_http as mcp
from gpt_package.errors import ValidationError


class FileParamsTests(unittest.TestCase):
    def setUp(self):
        stream = io.BytesIO()
        Image.new('RGBA', (48, 64), (20, 40, 60, 120)).save(stream, format='PNG')
        self.raw = stream.getvalue()
        self.file = {'download_url': 'https://files.oaiusercontent.com/input.png?token=secret',
                     'file_id': 'file_test'}

    def response(self):
        return io.BytesIO(self.raw)

    def call(self, args):
        return mcp.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                             'params': {'name': 'prepare_poster', 'arguments': args}})

    def test_discovery_declares_complete_official_file_schemas(self):
        tools = mcp.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})['result']['tools']
        tool = next(t for t in tools if t['name'] == 'prepare_poster')
        self.assertEqual(len(tool['_meta']['openai/fileParams']), 5)
        for key in tool['_meta']['openai/fileParams']:
            schema = tool['inputSchema']['properties'][key]
            self.assertEqual(set(schema['required']), {'download_url', 'file_id'})
            self.assertEqual(set(schema['properties']), {'download_url', 'file_id', 'mime_type', 'file_name'})
        self.assertTrue(tool['annotations']['openWorldHint'])

    def test_chat_attachment_reaches_render_without_store_tool(self):
        output = {'ok': True, 'rendered': False, 'status': {'code': 'completed'}}
        with patch.object(mcp, 'urlopen', return_value=self.response()), patch.object(
                mcp, '_run_staged_call', return_value=output) as render:
            result = self.call({'intake_confirmed': True, 'subject_image': self.file})
        self.assertNotIn('error', result)
        args = render.call_args.args[0]
        self.assertEqual(base64.b64decode(args['subject_image_base64'][0].split(',')[1]), self.raw)
        self.assertNotIn('subject_image', args)
        self.assertNotIn('token=secret', str(result))

    def test_draft_and_geometry_are_scalar_and_keep_approval_flags(self):
        with patch.object(mcp, 'urlopen', side_effect=lambda *a, **kw: self.response()):
            args = mcp._materialize_attachment_file_inputs({'draft_image': self.file,
                'geometry_image': self.file, 'typography_confirmed': False})
        self.assertIsInstance(args['generated_background_base64'], str)
        self.assertIsInstance(args['geometry_image_base64'], str)
        self.assertFalse(args['typography_confirmed'])

    def test_cloud_paths_disabled_without_overriding_local_development(self):
        with patch.dict(os.environ, {'VERCEL': '1'}, clear=True):
            self.assertFalse(mcp._local_path_inputs_allowed())
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(mcp._local_path_inputs_allowed())

    def test_untrusted_download_is_rejected_before_network(self):
        with patch.object(mcp, 'urlopen') as network:
            for url in ('https://127.0.0.1/a', 'https://files.oaiusercontent.com.evil.test/a',
                        'http://files.oaiusercontent.com/a', 'https://files.oaiusercontent.com:8443/a'):
                with self.assertRaises(ValidationError):
                    mcp._download_attachment_as_data_url({**self.file, 'download_url': url})
            network.assert_not_called()

    def test_expired_download_is_actionable_and_does_not_leak_url(self):
        with patch.object(mcp, 'urlopen', side_effect=URLError(self.file['download_url'])):
            result = self.call({'subject_image': self.file})
        output = result['result']['structuredContent']
        self.assertEqual(output['pipeline_stage'], 'attachment_preflight')
        self.assertIn('fresh file reference', output['user_friendly_hint']['what_happened'])
        self.assertNotIn('token=secret', str(result))

    def test_nested_ref_conflict_does_not_download(self):
        with patch.object(mcp, 'urlopen') as network:
            with self.assertRaises(ValidationError):
                mcp._materialize_attachment_file_inputs({'subject_image': self.file,
                    'poster_request': {'asset_refs': {'subjects': ['existing']}}})
            network.assert_not_called()

    def test_unexpected_failure_returns_jsonrpc_diagnostic_without_secret(self):
        with patch.object(mcp, '_run_staged_call', side_effect=RuntimeError('token=secret')):
            result = self.call({'intake_confirmed': True})
        self.assertEqual(result['error']['code'], -32603)
        self.assertTrue(result['error']['data']['diagnostic_id'])
        self.assertNotIn('token=secret', str(result))

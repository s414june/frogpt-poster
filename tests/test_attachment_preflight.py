import unittest
from api.mcp import dispatch, _rewrite_failed_output_for_retry
from gpt_package.workflow import assistant_execution_contract


class AttachmentPreflightTests(unittest.TestCase):
    def test_host_preflight_and_missing_file_recovery_are_advertised(self):
        result = dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})['result']
        self.assertIn('No such file or directory', result['instructions'])
        self.assertIn('附件讀取失敗，尚未傳入套件', result['instructions'])
        self.assertIn('原因尚未確認', result['instructions'])
        contract = assistant_execution_contract()
        self.assertTrue(contract['attachment_preflight']['required_before_render_call'])
        self.assertEqual(contract['error_reporting']['attachment_read'], 'before_tool_call')

    def test_runtime_failure_is_not_rewritten_as_base64_retry(self):
        for error in ('font load failed', 'failed to encode base64 output'):
            out = _rewrite_failed_output_for_retry({'ok': False, 'rendered': False,
                'status': {'code': 'failed', 'message': 'poster_render_failed_internal'},
                'error_type': 'RuntimeError', 'error': error})
            self.assertFalse(out['ok'])
            self.assertEqual(out['status']['code'], 'failed')
            self.assertEqual(out['error'], error)
            self.assertEqual(out['failure_stage'], 'server_processing')
            self.assertNotEqual(out['next_action'], 'retry_with_base64_only')

    def test_known_base64_validation_error_remains_recoverable(self):
        out = _rewrite_failed_output_for_retry({'ok': False, 'rendered': False,
            'status': {'code': 'failed'}, 'error_type': 'ValidationError', 'error': 'invalid base64 image'})
        self.assertEqual(out['status']['code'], 'needs_input')
        self.assertEqual(out['failure_stage'], 'image_input_validation')

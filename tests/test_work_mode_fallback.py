import unittest
from gpt_package.mcp_http import dispatch
from gpt_package.workflow import assistant_execution_contract


class WorkModeFallbackTests(unittest.TestCase):
    def test_mcp_advertises_conditional_work_mode_fallback(self):
        initialize = dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})['result']
        tools = dispatch({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})['result']['tools']
        for instructions in (initialize['instructions'], tools[0]['description']):
            self.assertIn('「工作」', instructions)
            self.assertIn('「對話」', instructions)
            self.assertIn('重新附上', instructions)
            self.assertIn('重試一次', instructions)
            self.assertIn('不能保證', instructions)
            self.assertIn('已在「工作」', instructions)

    def test_contract_limits_retry_and_does_not_guarantee_fix(self):
        fallback = assistant_execution_contract()['work_mode_fallback']
        self.assertEqual(fallback['max_corrected_retries'], 1)
        self.assertTrue(fallback['retry_requires_changed_input_or_recovered_bytes'])
        self.assertFalse(fallback['guarantees_resolution'])
        self.assertTrue(fallback['reattach_original_image_in_new_work'])

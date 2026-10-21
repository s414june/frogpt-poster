import unittest
from unittest.mock import patch
from gpt_package.workflow import workflow_gate
from gpt_package.mcp_http import dispatch, _run_staged_call
from gpt_package.openai_tool import handle_tool_call, build_tool_definition

class RequiredWorkflowTests(unittest.TestCase):
    def brief(self):
        return dict(intake_confirmed=True, intake_answers={'images':'AI', 'copy':'AI', 'purpose':'brunch', 'size':'portrait', 'style':'warm'},
                    composition_proposal={'subject':'brunch plate', 'background':'warm white'})

    def approve(self, args):
        return dict(args, composition_confirmed=True,
                    approved_composition_sha256=workflow_gate(args)['composition_sha256'])

    def test_intake_flag_and_legacy_approval_cannot_skip_questions(self):
        args=dict(intake_confirmed=True, typography_confirmed=True, preview_only=False)
        for fn in (handle_tool_call, lambda a: _run_staged_call(a, True)):
            result=fn(args)
            self.assertFalse(result['rendered'])
            self.assertEqual(result['next_action'], 'ask_user_intake_questions_then_stop')

    def test_proposal_always_waits_for_separate_approval(self):
        args=self.brief()
        args['composition_confirmed']=True
        result=workflow_gate(args)
        self.assertEqual(result['next_action'], 'show_composition_ask_user_then_stop')
        self.assertFalse(result['rendered'])
        self.assertIn('brunch plate', result['confirmation_question'])

    def test_changed_proposal_or_answers_invalidates_approval(self):
        approved=self.approve(self.brief())
        self.assertIsNone(workflow_gate(approved))
        for field in ('composition_proposal', 'intake_answers'):
            args={**approved, field:{**approved[field], 'background':'blue'}}
            self.assertIsNotNone(workflow_gate(args))

    def test_gate_blocks_storage_and_renderer(self):
        with patch('gpt_package.mcp_http.run_with_storage') as storage:
            _run_staged_call(self.brief(), True)
        storage.assert_not_called()
        with patch('gpt_package.openai_tool._handle_tool_call') as render:
            handle_tool_call(self.brief())
        render.assert_not_called()

    def test_approved_request_reaches_pipeline_after_restart(self):
        args=self.approve(self.brief())
        with patch('gpt_package.mcp_http.run_with_storage', return_value={'rendered': True}) as storage:
            self.assertTrue(_run_staged_call(args, True)['rendered'])
        storage.assert_called_once()

    def test_mcp_exposes_questions_and_proposal_without_render(self):
        def call(args):
            return dispatch({'jsonrpc':'2.0','id':1,'method':'tools/call',
                             'params':{'name':'prepare_poster','arguments':args}})['result']['structuredContent']
        self.assertIn('intake_questions', call({}))
        proposal=call(self.brief())
        self.assertIn('composition_sha256', proposal)
        self.assertEqual(proposal['status']['message'], 'composition_confirmation_required')

    def test_both_tool_schemas_expose_approval_fields(self):
        from gpt_package.mcp_http import SCHEMA
        for schema in (SCHEMA, build_tool_definition()['parameters']):
            for field in ('composition_proposal','composition_confirmed','approved_composition_sha256'):
                self.assertIn(field,schema['properties'])

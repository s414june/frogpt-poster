"""Explicit completed questionnaire/approval fixtures for downstream renderer tests."""
from gpt_package.workflow import workflow_gate


def approved_arguments(args):
    args = dict(args)
    if args.get('request_intake_only'):
        return args
    args.update(intake_confirmed=True,
                intake_answers={'copy_ready':'AI', 'image_ready':'AI', 'purpose':'test', 'size':'portrait', 'style':'warm'},
                composition_proposal={'subject':'test subject', 'background':'warm white'})
    proposal = workflow_gate(args)
    args.update(composition_confirmed=True, approved_composition_sha256=proposal['composition_sha256'])
    return args


def approved_call(fn):
    def call(args, *rest, **kwargs):
        return fn(approved_arguments(args) if args else args, *rest, **kwargs)
    return call


def approved_dispatch(fn, always=False):
    def call(message):
        params = message.get('params', {})
        args = params.get('arguments', {})
        nested = args.get('poster_request') or {}
        if (message.get('method') == 'tools/call' and params.get('name') == 'prepare_poster'
                and (always or args.get('intake_confirmed') is True or nested.get('intake_confirmed') is True)):
            message = dict(message, params=dict(params, arguments=approved_arguments(args)))
        return fn(message)
    return call

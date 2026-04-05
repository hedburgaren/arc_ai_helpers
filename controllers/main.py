# -*- coding: utf-8 -*-
"""
API Controllers for AI Helpers.
Provides webhook endpoints for n8n integration.
"""
import functools
import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

API_KEY_PARAM = 'arc_ai_helpers.api_bearer_token'


def _get_json_params():
    """Extract params from JSON-RPC body or raw JSON body."""
    raw = json.loads(request.httprequest.get_data(as_text=True) or '{}')
    # JSON-RPC wraps data in params key
    return raw.get('params', raw)


def require_bearer_token(func):
    """Decorator: validate Bearer token from ir.config_parameter."""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return {'success': False, 'error': 'Missing Bearer token'}
        token = auth_header[7:]
        expected = request.env['ir.config_parameter'].sudo().get_param(API_KEY_PARAM)
        if not expected or token != expected:
            return {'success': False, 'error': 'Invalid Bearer token'}
        return func(self, *args, **kwargs)
    return wrapper


class AiHelpersController(http.Controller):
    """API endpoints for AI Helpers."""

    @http.route('/api/ai/task/callback', type='json', auth='public', methods=['POST'], csrf=False)
    @require_bearer_token
    def task_callback(self, **kwargs):
        """
        Callback endpoint for n8n to report task results.

        Expected payload:
        {
            "task_id": 123,
            "output": "AI generated response",
            "confidence": "high",
            "confidence_score": 0.95,
            "error": null
        }
        """
        try:
            data = _get_json_params()
            task_id = data.get('task_id')

            if not task_id:
                return {'success': False, 'error': 'task_id required'}

            task = request.env['ai.task'].sudo().browse(task_id)
            if not task.exists():
                return {'success': False, 'error': 'Task not found'}

            task.receive_n8n_result(data)

            return {'success': True, 'task_id': task_id}

        except Exception as e:
            _logger.error("Task callback error: %s", str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/api/ai/task/create', type='json', auth='public', methods=['POST'], csrf=False)
    @require_bearer_token
    def create_task(self, **kwargs):
        """
        Create a new AI task.

        Expected payload:
        {
            "assistant_id": 1,
            "task_type": "chat",
            "input_text": "Hello, I need help with...",
            "source": "api",
            "metadata": {}
        }
        """
        try:
            data = _get_json_params()

            required = ['assistant_id', 'input_text']
            for field in required:
                if not data.get(field):
                    return {'success': False, 'error': f'{field} required'}

            task = request.env['ai.task'].sudo().create({
                'assistant_id': data['assistant_id'],
                'task_type': data.get('task_type', 'chat'),
                'input_text': data['input_text'],
                'source': data.get('source', 'api'),
                'metadata': json.dumps(data.get('metadata', {})),
                'res_model': data.get('res_model'),
                'res_id': data.get('res_id'),
            })

            # Auto-process if requested
            if data.get('auto_process', True):
                task.action_process()

            return {
                'success': True,
                'task_id': task.id,
                'task_name': task.name,
                'state': task.state,
            }

        except Exception as e:
            _logger.error("Create task error: %s", str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/api/ai/task/<int:task_id>', type='json', auth='public', methods=['GET'], csrf=False)
    @require_bearer_token
    def get_task(self, task_id, **kwargs):
        """Get task status and result."""
        try:
            task = request.env['ai.task'].sudo().browse(task_id)
            if not task.exists():
                return {'success': False, 'error': 'Task not found'}

            return {
                'success': True,
                'task': {
                    'id': task.id,
                    'name': task.name,
                    'state': task.state,
                    'task_type': task.task_type,
                    'input_text': task.input_text,
                    'output_text': task.output_text,
                    'confidence': task.confidence,
                    'confidence_score': task.confidence_score,
                    'error_message': task.error_message,
                    'created': task.create_date.isoformat() if task.create_date else None,
                    'completed': task.completed_at.isoformat() if task.completed_at else None,
                }
            }

        except Exception as e:
            _logger.error("Get task error: %s", str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/api/ai/assistant/<int:assistant_id>/message', type='json', auth='public', methods=['POST'], csrf=False)
    @require_bearer_token
    def send_message(self, assistant_id, **kwargs):
        """
        Send a message to an assistant.

        Expected payload:
        {
            "message": "Hello!",
            "context_type": "session",
            "session_id": "abc123"
        }
        """
        try:
            data = _get_json_params()

            assistant = request.env['ai.assistant'].sudo().browse(assistant_id)
            if not assistant.exists():
                return {'success': False, 'error': 'Assistant not found'}

            # Get or create context
            context = request.env['ai.context'].sudo().get_or_create(
                context_type=data.get('context_type', 'session'),
                session_id=data.get('session_id'),
                user_id=data.get('user_id'),
                partner_id=data.get('partner_id'),
                assistant_id=assistant_id,
            )

            # Add user message to context
            context.add_message('user', data.get('message', ''))

            # Create task
            task = request.env['ai.task'].sudo().create({
                'assistant_id': assistant_id,
                'task_type': 'chat',
                'input_text': data.get('message', ''),
                'source': 'api',
                'metadata': json.dumps({
                    'context_id': context.id,
                    'session_id': context.session_id,
                }),
            })

            # Process
            task.action_process()

            return {
                'success': True,
                'task_id': task.id,
                'context_id': context.id,
                'state': task.state,
            }

        except Exception as e:
            _logger.error("Send message error: %s", str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/api/ai/assistants', type='json', auth='public', methods=['GET'], csrf=False)
    @require_bearer_token
    def list_assistants(self, **kwargs):
        """List all active assistants for the current company."""
        try:
            assistants = request.env['ai.assistant'].sudo().search([
                ('active', '=', True),
            ])

            return {
                'success': True,
                'assistants': [{
                    'id': a.id,
                    'name': a.name,
                    'email': a.email,
                    'specialization': a.specialization,
                    'language': a.language,
                } for a in assistants]
            }

        except Exception as e:
            _logger.error("List assistants error: %s", str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/api/ai/webhook/email', type='json', auth='public', methods=['POST'], csrf=False)
    @require_bearer_token
    def email_webhook(self, **kwargs):
        """
        Webhook for incoming emails to AI assistants.

        Expected payload:
        {
            "to": "alex@plastshop.se",
            "from": "customer@example.com",
            "subject": "Question about...",
            "body": "Hello, I have a question...",
            "message_id": "<abc123@mail.example.com>"
        }
        """
        try:
            data = _get_json_params()
            to_email = data.get('to', '').lower()

            # Find assistant by email
            assistant = request.env['ai.assistant'].sudo().search([
                ('email', '=ilike', to_email),
                ('active', '=', True),
            ], limit=1)

            if not assistant:
                return {'success': False, 'error': f'No assistant found for {to_email}'}

            # Process email
            task = assistant.process_incoming_email(data)

            return {
                'success': True,
                'task_id': task.id,
                'assistant_id': assistant.id,
                'assistant_name': assistant.name,
            }

        except Exception as e:
            _logger.error("Email webhook error: %s", str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/api/ai/webhook/slack', type='json', auth='public', methods=['POST'], csrf=False)
    @require_bearer_token
    def slack_webhook(self, **kwargs):
        """
        Webhook for Slack events.

        Expected payload (Slack event):
        {
            "type": "message",
            "channel": "C123456",
            "user": "U123456",
            "text": "@alex help me with...",
            "ts": "1234567890.123456"
        }
        """
        try:
            data = _get_json_params()

            # Handle Slack URL verification
            if data.get('type') == 'url_verification':
                return {'challenge': data.get('challenge')}

            event = data.get('event', data)

            # Find assistant mentioned or by channel
            text = event.get('text', '')
            channel = event.get('channel')

            # Try to find assistant by Slack user ID mention or channel
            assistant = None

            # Check all assistants for matching Slack config
            assistants = request.env['ai.assistant'].sudo().search([
                ('active', '=', True),
            ])

            for a in assistants:
                if a.slack_user_id and f'<@{a.slack_user_id}>' in text:
                    assistant = a
                    break
                if a.slack_channel_ids and channel in (a.slack_channel_ids or '').split(','):
                    assistant = a
                    break

            if not assistant:
                return {'success': False, 'error': 'No matching assistant found'}

            # Process Slack message
            task = assistant.process_slack_message(event)

            return {
                'success': True,
                'task_id': task.id,
                'assistant_id': assistant.id,
            }

        except Exception as e:
            _logger.error("Slack webhook error: %s", str(e))
            return {'success': False, 'error': str(e)}

# -*- coding: utf-8 -*-
"""
API Controllers for AI Helpers.
Provides webhook endpoints for n8n integration.
"""
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _company_domain():
    """Return company filter domain for tenant isolation."""
    return [('company_id', 'in', [request.env.company.id, False])]


class AiHelpersController(http.Controller):
    """API endpoints for AI Helpers."""

    @http.route('/api/ai/task/callback', type='json', auth='api_key', methods=['POST'])
    def task_callback(self, **kwargs):
        """Callback endpoint for n8n to return task results."""
        try:
            data = request.jsonrequest
            task_id = data.get('task_id')

            if not task_id:
                return {'success': False, 'error': 'task_id required'}

            task = request.env['ai.task'].sudo().search([
                ('id', '=', task_id),
            ] + _company_domain(), limit=1)
            if not task:
                return {'success': False, 'error': 'Task not found'}

            task.receive_n8n_result(data)

            return {'success': True, 'task_id': task_id}

        except Exception as e:
            _logger.error("Task callback error: %s", str(e), exc_info=True)
            return {'success': False, 'error': 'Internal server error'}

    @http.route('/api/ai/task/create', type='json', auth='api_key', methods=['POST'])
    def create_task(self, **kwargs):
        """Create a new AI task."""
        try:
            data = request.jsonrequest

            required = ['assistant_id', 'input_text']
            for field in required:
                if not data.get(field):
                    return {'success': False, 'error': f'{field} required'}

            # Validate assistant belongs to current company
            assistant = request.env['ai.assistant'].sudo().search([
                ('id', '=', data['assistant_id']),
            ] + _company_domain(), limit=1)
            if not assistant:
                return {'success': False, 'error': 'Assistant not found'}

            task = request.env['ai.task'].sudo().create({
                'assistant_id': assistant.id,
                'task_type': data.get('task_type', 'chat'),
                'input_text': data['input_text'][:50000],  # limit input size
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
            _logger.error("Create task error: %s", str(e), exc_info=True)
            return {'success': False, 'error': 'Internal server error'}

    @http.route('/api/ai/task/<int:task_id>', type='json', auth='api_key', methods=['GET'])
    def get_task(self, task_id, **kwargs):
        """Get task status and result."""
        try:
            task = request.env['ai.task'].sudo().search([
                ('id', '=', task_id),
            ] + _company_domain(), limit=1)
            if not task:
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
            _logger.error("Get task error: %s", str(e), exc_info=True)
            return {'success': False, 'error': 'Internal server error'}

    @http.route('/api/ai/assistant/<int:assistant_id>/message', type='json', auth='api_key', methods=['POST'])
    def send_message(self, assistant_id, **kwargs):
        """Send a message to an assistant."""
        try:
            data = request.jsonrequest

            assistant = request.env['ai.assistant'].sudo().search([
                ('id', '=', assistant_id),
            ] + _company_domain(), limit=1)
            if not assistant:
                return {'success': False, 'error': 'Assistant not found'}

            # Get or create context — derive user from authenticated API key, not from payload
            context = request.env['ai.context'].sudo().get_or_create(
                context_type=data.get('context_type', 'session'),
                session_id=data.get('session_id'),
                user_id=request.env.uid,
                partner_id=request.env.user.partner_id.id,
                assistant_id=assistant_id,
            )

            # Add user message to context
            message = data.get('message', '')[:50000]  # limit input size
            context.add_message('user', message)

            # Create task
            task = request.env['ai.task'].sudo().create({
                'assistant_id': assistant_id,
                'task_type': 'chat',
                'input_text': message,
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
            _logger.error("Send message error: %s", str(e), exc_info=True)
            return {'success': False, 'error': 'Internal server error'}

    @http.route('/api/ai/assistants', type='json', auth='api_key', methods=['GET'])
    def list_assistants(self, **kwargs):
        """List all active assistants for the current company."""
        try:
            assistants = request.env['ai.assistant'].sudo().search([
                ('active', '=', True),
            ] + _company_domain())

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
            _logger.error("List assistants error: %s", str(e), exc_info=True)
            return {'success': False, 'error': 'Internal server error'}

    @http.route('/api/ai/webhook/email', type='json', auth='api_key', methods=['POST'])
    def email_webhook(self, **kwargs):
        """Webhook for incoming emails to AI assistants."""
        try:
            data = request.jsonrequest
            to_email = data.get('to', '').lower()

            # Find assistant by email within current company
            assistant = request.env['ai.assistant'].sudo().search([
                ('email', '=ilike', to_email),
                ('active', '=', True),
            ] + _company_domain(), limit=1)

            if not assistant:
                return {'success': False, 'error': 'No assistant found for this email'}

            # Process email
            task = assistant.process_incoming_email(data)

            return {
                'success': True,
                'task_id': task.id,
                'assistant_id': assistant.id,
                'assistant_name': assistant.name,
            }

        except Exception as e:
            _logger.error("Email webhook error: %s", str(e), exc_info=True)
            return {'success': False, 'error': 'Internal server error'}

    @http.route('/api/ai/webhook/slack', type='json', auth='api_key', methods=['POST'])
    def slack_webhook(self, **kwargs):
        """Webhook for Slack events."""
        try:
            data = request.jsonrequest

            # Handle Slack URL verification
            if data.get('type') == 'url_verification':
                return {'challenge': data.get('challenge')}

            event = data.get('event', data)

            # Find assistant mentioned or by channel
            text = event.get('text', '')
            channel = event.get('channel')

            # Check assistants within current company
            assistant = None
            assistants = request.env['ai.assistant'].sudo().search([
                ('active', '=', True),
            ] + _company_domain())

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
            _logger.error("Slack webhook error: %s", str(e), exc_info=True)
            return {'success': False, 'error': 'Internal server error'}

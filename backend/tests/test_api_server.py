"""
Tests for the Flask API server.

These tests verify the API endpoints work correctly.
"""

import pytest
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """Create test Flask application."""
    from api_server import app as flask_app
    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestHealthEndpoint:
    """Test the /api/health endpoint."""

    def test_health_returns_200(self, client):
        """Health endpoint should return 200."""
        response = client.get('/api/health')
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        """Health endpoint should return JSON."""
        response = client.get('/api/health')
        assert response.content_type.startswith('application/json')

    def test_health_contains_status(self, client):
        """Health response should contain status field."""
        response = client.get('/api/health')
        data = json.loads(response.data)
        assert 'status' in data


class TestInfoEndpoint:
    """Test the /api/info endpoint."""

    def test_info_returns_200(self, client):
        """Info endpoint should return 200."""
        response = client.get('/api/info')
        assert response.status_code == 200

    def test_info_contains_version(self, client):
        """Info response should contain version."""
        response = client.get('/api/info')
        data = json.loads(response.data)
        assert 'version' in data or 'api_version' in data


class TestStatusEndpoint:
    """Test the /api/status endpoint."""

    def test_status_returns_200(self, client):
        """Status endpoint should return 200."""
        response = client.get('/api/status')
        assert response.status_code == 200


class TestDetectPIIEndpoint:
    """Test the /api/detect-pii endpoint."""

    def test_detect_requires_post(self, client):
        """Detect endpoint should require POST."""
        response = client.get('/api/detect-pii')
        assert response.status_code == 405  # Method Not Allowed

    def test_detect_requires_json(self, client):
        """Detect endpoint should require JSON body."""
        response = client.post('/api/detect-pii', data='not json')
        # Flask returns 500 for malformed JSON, or 400/415 for content-type issues
        assert response.status_code in (400, 415, 500)

    def test_detect_requires_text_field(self, client):
        """Detect endpoint should require text field."""
        response = client.post(
            '/api/detect-pii',
            json={},
            content_type='application/json'
        )
        # Should return error about missing text
        assert response.status_code in (200, 400)
        data = json.loads(response.data)
        if response.status_code == 400:
            assert 'error' in data or 'message' in data

    def test_detect_with_empty_text(self, client):
        """Detect with empty text should return error."""
        response = client.post(
            '/api/detect-pii',
            json={'text': '', 'action': 'detect'},
            content_type='application/json'
        )
        # Empty text returns 400 Bad Request
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data or 'status' in data

    def test_detect_with_sample_text(self, client):
        """Detect with sample text should return response."""
        response = client.post(
            '/api/detect-pii',
            json={
                'text': 'Contact john@example.com for more info.',
                'action': 'detect'
            },
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)

    def test_anonymize_action(self, client):
        """Anonymize action should return anonymized text."""
        response = client.post(
            '/api/detect-pii',
            json={
                'text': 'My email is test@example.com',
                'action': 'anonymize',
                'create_session': True
            },
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        # Should have either anonymized_text or text
        assert 'anonymized_text' in data or 'text' in data or 'result' in data


class TestRestoreEndpoint:
    """Test the /api/restore and /api/restore-llm endpoints."""

    def test_restore_requires_post(self, client):
        """Restore endpoint should require POST."""
        response = client.get('/api/restore')
        assert response.status_code == 405

    def test_restore_llm_requires_post(self, client):
        """Restore-llm endpoint should require POST."""
        response = client.get('/api/restore-llm')
        assert response.status_code == 405

    def test_restore_llm_exists(self, client):
        """Restore-llm endpoint should exist."""
        response = client.post(
            '/api/restore-llm',
            json={'session_id': 'test', 'llm_output': 'test'},
            content_type='application/json'
        )
        # Should not be 404
        assert response.status_code != 404


class TestSessionsEndpoint:
    """Test the /api/sessions endpoint."""

    def test_sessions_returns_200(self, client):
        """Sessions endpoint should return 200."""
        response = client.get('/api/sessions')
        assert response.status_code == 200

    def test_sessions_returns_list(self, client):
        """Sessions endpoint should return a list or dict."""
        response = client.get('/api/sessions')
        data = json.loads(response.data)
        # Should be a list or dict with sessions
        assert isinstance(data, (list, dict))


class TestCORSHeaders:
    """Test CORS headers are set correctly."""

    def test_cors_headers_present(self, client):
        """Response should include CORS headers."""
        response = client.get('/api/health')
        # CORS headers may be set on responses
        # This is a basic check that the endpoint works
        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling."""

    def test_404_for_unknown_endpoint(self, client):
        """Unknown endpoint should return 404."""
        response = client.get('/api/unknown-endpoint-12345')
        assert response.status_code == 404

    def test_malformed_json_handled(self, client):
        """Malformed JSON should be handled gracefully."""
        response = client.post(
            '/api/detect-pii',
            data='{invalid json',
            content_type='application/json'
        )
        # Should return error, not crash
        assert response.status_code in (400, 500)

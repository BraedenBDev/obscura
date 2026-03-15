"""
Obscura API Server
Updated to use the new PIIDetector with unified pipeline.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os
import json

# Ensure imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obscura.detector import PIIDetector
from obscura.entity_types import ENTITY_LABELS, DISPLAY_NAMES

app = Flask(__name__)
CORS(app)

# Global detector instance
detector = PIIDetector(
    db_path="obscura.db",
    load_model=False  # Load on first request or explicit call
)

# Legacy alias for backward compatibility
model_handler = None

# Extension toggle state
extension_enabled = True
extension_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extension_config.json')

def load_extension_config():
    """Load extension enabled state from config file"""
    global extension_enabled
    try:
        if os.path.exists(extension_config_file):
            with open(extension_config_file, 'r') as f:
                config = json.load(f)
                extension_enabled = config.get('enabled', True)
                print(f"[CONFIG] Extension enabled: {extension_enabled}")
    except Exception as e:
        print(f"[CONFIG] Error loading config: {e}")
        extension_enabled = True

def save_extension_config():
    """Save extension enabled state to config file"""
    try:
        with open(extension_config_file, 'w') as f:
            json.dump({'enabled': extension_enabled}, f)
        print(f"[CONFIG] Saved extension state: {extension_enabled}")
    except Exception as e:
        print(f"[CONFIG] Error saving config: {e}")

# Load config on startup
load_extension_config()




def initialize_model():
    """Initialize the PIIDetector model"""
    global detector, model_handler
    try:
        print("[Obscura] Loading GLiNER model...")
        detector.load_model()
        print("[Obscura] + Model loaded successfully")

        # Set legacy alias for backward compatibility
        model_handler = detector
        return True

    except Exception as e:
        print(f"[Obscura] x Error loading model: {e}")
        import traceback
        traceback.print_exc()
        return False


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'message': 'API is online',
        'model_loaded': detector is not None and detector.is_loaded,
        'version': '5.0'
    }), 200


@app.route('/api/extension-status', methods=['GET'])
def get_extension_status():
    """Get extension enabled/disabled status"""
    return jsonify({
        'status': 'success',
        'enabled': extension_enabled
    }), 200


@app.route('/api/extension-toggle', methods=['POST', 'OPTIONS'])
def toggle_extension():
    """Toggle extension on/off"""
    global extension_enabled
    
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json() or {}
        
        # If 'enabled' is provided, set to that value; otherwise toggle
        if 'enabled' in data:
            extension_enabled = bool(data['enabled'])
        else:
            extension_enabled = not extension_enabled
        
        save_extension_config()
        
        return jsonify({
            'status': 'success',
            'enabled': extension_enabled,
            'message': f"Extension {'enabled' if extension_enabled else 'disabled'}"
        }), 200
        
    except Exception as e:
        print(f"[Obscura] x Toggle error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/detect-pii', methods=['POST', 'OPTIONS'])
def detect_pii():
    """
    Main PII detection endpoint

    Request body:
    {
        "text": "string to analyze",
        "action": "detect" or "anonymize",
        "threshold": 0.25 (optional, default 0.25),
        "create_session": true/false (deprecated, sessions always created for anonymize)
    }
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        # Validate input
        if not data or 'text' not in data:
            return jsonify({
                'status': 'error',
                'error': 'Missing required field: text'
            }), 400

        text = data.get('text', '').strip()
        action = data.get('action', 'detect')
        threshold = data.get('threshold', 0.25)

        if not text:
            return jsonify({
                'status': 'error',
                'error': 'Text cannot be empty'
            }), 400

        if len(text) > 50000:
            return jsonify({
                'status': 'error',
                'error': 'Text too long (max 50k characters)'
            }), 400

        # Load model on first request if not already loaded
        if not detector.is_loaded:
            print("[Obscura] Loading model on first request...")
            detector.load_model()

        print(f"\n[Obscura] Processing: {len(text)} characters, action: {action}")

        if action == 'detect':
            # Detection only
            entities = detector.detect(text, threshold=threshold)
            result = {
                'status': 'success',
                'entities': [
                    {
                        'text': e.text,
                        'label': e.type,
                        'start': e.start,
                        'end': e.end,
                        'score': e.confidence
                    }
                    for e in entities
                ],
                'entity_count': len(entities)
            }

        elif action == 'anonymize':
            # Anonymization with session
            anon_result = detector.anonymize(text, threshold=threshold)
            result = {
                'status': 'success',
                'anonymized_text': anon_result.anonymized_text,
                'replacement_map': anon_result.mappings,
                'session_id': anon_result.session_id,
                'entity_count': anon_result.entity_count,
                'entities': [
                    {
                        'text': e.text,
                        'label': e.type,
                        'start': e.start,
                        'end': e.end,
                        'score': e.confidence
                    }
                    for e in anon_result.entities
                ]
            }

        else:
            return jsonify({
                'status': 'error',
                'error': f'Unknown action: {action}. Use "detect" or "anonymize".'
            }), 400

        print(f"[Obscura] + Success: {result.get('entity_count', 0)} entities")
        return jsonify(result), 200

    except Exception as e:
        print(f"[Obscura] x Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/restore', methods=['POST', 'OPTIONS'])
def restore_pii():
    """
    Restore PII from anonymized text using session

    Request body:
    {
        "text": "anonymized text",
        "session_id": "session identifier"
    }
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        if not data or 'text' not in data or 'session_id' not in data:
            return jsonify({
                'status': 'error',
                'error': 'Missing required fields: text and session_id'
            }), 400

        text = data.get('text', '').strip()
        session_id = data.get('session_id', '').strip()

        if not text or not session_id:
            return jsonify({
                'status': 'error',
                'error': 'Text and session_id cannot be empty'
            }), 400

        print(f"\n[Obscura] Restore: session={session_id[:8]}..., text={len(text)} chars")

        result = detector.restore(text, session_id)

        return jsonify({
            'status': 'success',
            'restored_text': result.restored_text,
            'statistics': {
                'total': result.mappings_applied,
                'restored': result.mappings_applied,
                'session_id': result.session_id
            }
        }), 200

    except Exception as e:
        print(f"[Obscura] x Restore error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/restore-llm', methods=['POST', 'OPTIONS'])
def restore_llm():
    """
    Smart restore for LLM-generated output
    Handles case variations, modified content, multiple occurrences

    Request body:
    {
        "session_id": "session identifier",
        "llm_output": "text from LLM with placeholders"
    }
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'error': 'Missing request body'
            }), 400

        session_id = data.get('session_id', '').strip()
        llm_output = data.get('llm_output', '').strip()

        if not session_id or not llm_output:
            return jsonify({
                'status': 'error',
                'error': 'Both session_id and llm_output are required'
            }), 400

        print(f"\n[Obscura] LLM Restore: session={session_id[:8]}..., text={len(llm_output)} chars")

        # Use the unified restore method - it handles LLM output the same way
        result = detector.restore(llm_output, session_id)

        print(f"[Obscura] + LLM Restore: {result.mappings_applied} placeholders restored")

        return jsonify({
            'status': 'success',
            'restored_text': result.restored_text,
            'statistics': {
                'total': result.mappings_applied,
                'restored': result.mappings_applied,
                'session_id': result.session_id
            }
        }), 200

    except ValueError as e:
        print(f"[Obscura] x LLM Restore error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 404

    except Exception as e:
        print(f"[Obscura] x LLM Restore error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/restore-global', methods=['POST', 'OPTIONS'])
def restore_global():
    """
    Restore PII using ANY available session history
    Useful when session ID is lost (e.g. fresh page reload, different tab)
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({
                'status': 'error',
                'error': 'Missing required field: text'
            }), 400

        text = data.get('text', '').strip()

        print(f"\n[Obscura] Global Restore Request: {len(text)} chars")

        # Use restore without session_id for global lookup
        result = detector.restore(text, session_id=None)

        return jsonify({
            'status': 'success',
            'restored_text': result.restored_text,
            'statistics': {
                'total': result.mappings_applied,
                'restored': result.mappings_applied
            }
        }), 200

    except Exception as e:
        print(f"[Obscura] x Global Restore error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """List all active sessions"""
    try:
        # Get stats which includes session info
        stats = detector.get_stats()

        return jsonify({
            'status': 'success',
            'sessions': [],  # Individual session list not exposed for privacy
            'count': stats.get('session_count', 0)
        }), 200

    except Exception as e:
        print(f"[Obscura] x Sessions error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/status', methods=['GET'])
def status():
    """Get application status"""
    return jsonify({
        'status': 'success',
        'model_loaded': detector is not None and detector.is_loaded,
        'model_name': 'urchade/gliner_small-v2.1',
        'device': detector._detect_device() if detector else None,
        'handler_type': 'PIIDetector'
    }), 200


@app.route('/api/info', methods=['GET'])
def info():
    """Get API information"""
    return jsonify({
        'name': 'Obscura',
        'version': '1.0.0',
        'description': 'Advanced PII detection with validation pipeline and local learning',
        'features': [
            'AI-powered detection using GLiNER',
            'Format validators (Luhn, SSN, Aadhaar, etc.)',
            'Context-aware confidence adjustment',
            'User corrections for local learning',
            'Session-based anonymization',
            'Smart restoration (handles modified text)',
            'SQLite persistence for corrections and sessions',
            'Unified detection pipeline'
        ],
        'pii_types': ENTITY_LABELS,
        'pii_type_names': DISPLAY_NAMES,
        'endpoints': {
            '/api/health': 'Health check',
            '/api/detect-pii': 'Detect and/or anonymize PII',
            '/api/restore': 'Restore PII from session',
            '/api/restore-llm': 'Smart restore for LLM output',
            '/api/restore-global': 'Restore without session ID',
            '/api/sessions': 'List active sessions',
            '/api/status': 'Get model status',
            '/api/info': 'API information',
            '/api/stats': 'Get database statistics',
            '/api/corrections/reject': 'Mark detection as false positive',
            '/api/corrections/relabel': 'Change entity type',
            '/api/corrections/add-missed': 'Add missed PII pattern',
            '/api/wipe': 'Clear all data (requires confirmation)'
        }
    }), 200


# ==================== Statistics & Management Endpoints ====================


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get database statistics"""
    try:
        stats = detector.get_stats()

        return jsonify({
            'status': 'success',
            'stats': stats
        }), 200

    except Exception as e:
        print(f"[Obscura] x Stats error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/wipe', methods=['POST', 'OPTIONS'])
def wipe_all():
    """
    Completely reset the database.

    Request body:
    {
        "confirm": true
    }
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        if not data or not data.get('confirm', False):
            return jsonify({
                'status': 'error',
                'error': 'Must include {"confirm": true} to wipe all data'
            }), 400

        result = detector.wipe_all()

        return jsonify({
            'status': 'success',
            'message': 'All data wiped',
            'deleted': result
        }), 200

    except Exception as e:
        print(f"[Obscura] x Wipe error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/cleanup', methods=['POST', 'OPTIONS'])
def cleanup():
    """Run cleanup operations (remove expired sessions and old logs)"""
    if request.method == 'OPTIONS':
        return '', 204

    try:
        detector.cleanup()

        return jsonify({
            'status': 'success',
            'message': 'Cleanup completed'
        }), 200

    except Exception as e:
        print(f"[Obscura] x Cleanup error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


# ==================== Correction Endpoints ====================


@app.route('/api/corrections/reject', methods=['POST', 'OPTIONS'])
def add_rejection():
    """
    Mark a detection as a false positive.

    Request body:
    {
        "text": "the text that was incorrectly detected",
        "detected_type": "the type GLiNER assigned",
        "context_before": "text before the detection (optional)",
        "context_after": "text after the detection (optional)"
    }
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        if not data or 'text' not in data or 'detected_type' not in data:
            return jsonify({
                'status': 'error',
                'error': 'Missing required fields: text and detected_type'
            }), 400

        text = data.get('text', '').strip()
        detected_type = data.get('detected_type', '').strip()
        context_before = data.get('context_before', '').strip()
        context_after = data.get('context_after', '').strip()

        correction_id = detector.corrections.add_rejection(
            text=text,
            detected_type=detected_type,
            context_before=context_before,
            context_after=context_after
        )

        print(f"[Obscura] + Added rejection: '{text}' (type: {detected_type})")

        return jsonify({
            'status': 'success',
            'message': f'Rejection added for "{text}"',
            'correction_id': correction_id
        }), 200

    except Exception as e:
        print(f"[Obscura] x Rejection error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/corrections/relabel', methods=['POST', 'OPTIONS'])
def add_relabel():
    """
    Change the type of a detection.

    Request body:
    {
        "text": "the detected text",
        "original_type": "the type GLiNER assigned",
        "corrected_type": "the correct type",
        "context_before": "text before (optional)",
        "context_after": "text after (optional)"
    }
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        required_fields = ['text', 'original_type', 'corrected_type']
        if not data or not all(f in data for f in required_fields):
            return jsonify({
                'status': 'error',
                'error': f'Missing required fields: {required_fields}'
            }), 400

        text = data.get('text', '').strip()
        original_type = data.get('original_type', '').strip()
        corrected_type = data.get('corrected_type', '').strip()
        context_before = data.get('context_before', '').strip()
        context_after = data.get('context_after', '').strip()

        correction_id = detector.corrections.add_relabel(
            text=text,
            original_type=original_type,
            corrected_type=corrected_type,
            context_before=context_before,
            context_after=context_after
        )

        print(f"[Obscura] + Added relabel: '{text}' ({original_type} -> {corrected_type})")

        return jsonify({
            'status': 'success',
            'message': f'Relabel added: {original_type} -> {corrected_type}',
            'correction_id': correction_id
        }), 200

    except Exception as e:
        print(f"[Obscura] x Relabel error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/corrections/add-missed', methods=['POST', 'OPTIONS'])
def add_missed_pii():
    """
    Add a PII pattern that was missed by detection.

    Request body:
    {
        "text": "the PII text that was missed",
        "entity_type": "the type of PII",
        "context_before": "text before (optional)",
        "context_after": "text after (optional)"
    }
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        if not data or 'text' not in data or 'entity_type' not in data:
            return jsonify({
                'status': 'error',
                'error': 'Missing required fields: text and entity_type'
            }), 400

        text = data.get('text', '').strip()
        entity_type = data.get('entity_type', '').strip()
        context_before = data.get('context_before', '').strip()
        context_after = data.get('context_after', '').strip()

        correction_id = detector.corrections.add_missed_pii(
            text=text,
            entity_type=entity_type,
            context_before=context_before,
            context_after=context_after
        )

        print(f"[Obscura] + Added missed PII: '{text}' (type: {entity_type})")

        return jsonify({
            'status': 'success',
            'message': f'Missed PII added: "{text}" as {entity_type}',
            'correction_id': correction_id
        }), 200

    except Exception as e:
        print(f"[Obscura] x Add missed error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/corrections/boundary', methods=['POST', 'OPTIONS'])
def add_boundary_fix():
    """
    Fix entity boundaries.

    Request body:
    {
        "original_text": "the text GLiNER detected",
        "corrected_text": "the full/correct text",
        "entity_type": "the entity type",
        "context_before": "text before (optional)",
        "context_after": "text after (optional)"
    }
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        required_fields = ['original_text', 'corrected_text', 'entity_type']
        if not data or not all(f in data for f in required_fields):
            return jsonify({
                'status': 'error',
                'error': f'Missing required fields: {required_fields}'
            }), 400

        original_text = data.get('original_text', '').strip()
        corrected_text = data.get('corrected_text', '').strip()
        entity_type = data.get('entity_type', '').strip()
        context_before = data.get('context_before', '').strip()
        context_after = data.get('context_after', '').strip()

        correction_id = detector.corrections.add_boundary_fix(
            original_text=original_text,
            corrected_text=corrected_text,
            entity_type=entity_type,
            context_before=context_before,
            context_after=context_after
        )

        print(f"[Obscura] + Added boundary fix: '{original_text}' -> '{corrected_text}'")

        return jsonify({
            'status': 'success',
            'message': f'Boundary fix added',
            'correction_id': correction_id
        }), 200

    except Exception as e:
        print(f"[Obscura] x Boundary fix error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


def run_api_server(host='127.0.0.1', port=5001, debug=False):
    """Run the Flask API server"""
    print(f"\n[Obscura] Starting server on {host}:{port}")
    print("[Obscura] Press Ctrl+C to stop\n")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    initialize_model()
    run_api_server(debug=False)

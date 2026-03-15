# API Reference

## Endpoints

### GET /api/health

Check if API is online

Response: `{"status":"success","model_loaded":true}`

### POST /api/detect-pii

Detect PII in text

Body:

```json
{
  "text": "content to analyze",
  "labels": ["email", "phone"],
  "threshold": 0.3,
  "action": "detect"
}
```

Response:

```json
{
  "status": "success",
  "entities": [
    {
      "text": "john@example.com",
      "label": "email",
      "score": 0.99
    }
  ]
}
```

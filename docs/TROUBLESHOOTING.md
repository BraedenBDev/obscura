# Troubleshooting

## Common Issues

### Desktop app not running

- Ensure desktop app is started
- Check Flask API is running on localhost:5000
- Test: curl http://localhost:5000/api/health

### No results detected

- Lower confidence threshold
- Enable Hybrid Mode
- Check model loaded in app

### Connection refused

- Check firewall settings
- Verify port is correct
- Restart browser and app

### Extension won't load

- Check manifest.json is valid JSON
- Verify all files are created
- Check file paths are correct

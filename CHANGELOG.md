# Changelog

All notable changes to Obscura will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-15

### Added
- Open-source release under MIT License
- Comprehensive README with installation and usage guide
- AI Declaration documenting all generative AI tools used, including GLiNER model attribution
- Contributing guide for open-source contributors
- GitHub issue templates (bug report, feature request)
- Pull request template
- Centralized documentation in `docs/`

### Changed
- Rebranded from "PII Shield" to "Obscura"
- Restructured repository: `backend/` and `extension/` top-level directories
- Renamed Python package from `pii_shield` to `obscura`
- Unified version to 1.0.0 across all components
- Renamed Chrome extension widget file for cross-platform compatibility

### Fixed
- Chrome manifest: added missing `storage` and `sidePanel` permissions
- Chrome manifest: fixed content script filename case mismatch (broke on Linux)
- Luhn credit card validator: was checking wrong entity type, never triggered
- Options page: default port was 5000, should be 5001
- Side panel: `DEBUG` flag left as `true` in production
- Desktop GUI: Reset History looked for deleted `sessions.json` instead of SQLite DB
- Backend launcher: `api_running` shutdown flag set local variable instead of module-level

### Removed
- Dead code: `config.py`, `model_handler.py`, unused utility scripts
- Dead code: `utils/api-client.js`, `utils/constants.js`, `utils/storage-manager.js`
- Design prototypes (not source code)
- Stale audit documents and internal dev notes

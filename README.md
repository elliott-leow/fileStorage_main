# File Server

A modern, modular Flask-based file server with semantic search, folder protection, and a clean web interface.

## Features

- **File Browsing**: Navigate directories and download files
- **Semantic Search**: AI-powered content search using sentence transformers
- **Filename Search**: Filter files by name with recursive option
- **Folder Protection**: Password-protect specific folders
- **Hidden Folders**: Hide folders from listings (accessible via direct link)
- **File Upload**: Upload files and folders via web interface or API
- **File Deletion**: Delete files/folders with confirmation
- **Dark Mode**: Toggle between light and dark themes

## Project Structure

```
fileStorage_main/
├── app/                          # Main application package
│   ├── __init__.py              # Flask app factory
│   ├── config.py                # Configuration management
│   ├── routes/                  # Route blueprints
│   │   ├── __init__.py         # Blueprint registration
│   │   ├── main.py             # Main file serving routes
│   │   ├── api.py              # API endpoints
│   │   └── upload.py           # Upload functionality
│   ├── services/                # Business logic services
│   │   ├── __init__.py
│   │   ├── auth_service.py     # Authentication/authorization
│   │   ├── file_service.py     # File operations
│   │   ├── visibility_service.py # Hidden folder management
│   │   └── search_service.py   # Semantic search
│   └── utils/                   # Utility modules
│       ├── __init__.py
│       ├── path_utils.py       # Path manipulation
│       └── file_utils.py       # File info utilities
├── templates/                   # Jinja2 templates
│   ├── index.html              # Main file browser
│   ├── upload.html             # Upload interface
│   ├── error.html              # Error pages
│   └── partials/               # Reusable template parts
│       └── modals.html         # Modal dialogs
├── static/                      # Static assets
│   ├── css/
│   │   └── styles.css          # Custom styles
│   └── js/
│       ├── theme.js            # Theme management
│       ├── modals.js           # Modal utilities
│       └── file-browser.js     # Main browser logic
├── public/                      # Served files directory
├── folder_keys.json            # Protected folders config
├── folder_visibility.json      # Hidden folders config
├── run.py                      # Application entry point
├── requirements.txt            # Python dependencies
└── README.md
```

## Installation

1. Clone the repository:
```bash
git clone <repo-url>
cd fileStorage_main
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file from the example config:
```bash
cp config.example .env
# Edit .env to customize settings (especially PUBLIC_DIR for root file path)
```

5. Run the application:
```bash
python run.py
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `FLASK_SECRET_KEY` | Secret key for sessions | Yes (for production) |
| `KEY` | Global upload API key | Yes |
| `DELETE_KEY` | Key for deletion feature | No |
| `HIDDEN_KEY` | Key for folder hiding | No |
| `PUBLIC_DIR` | Directory to serve files from | No (default: `./public`) |
| `FLASK_ENV` | Environment (development/production) | No |
| `HOST` | Server host | No (default: `0.0.0.0`) |
| `PORT` | Server port | No (default: `8000`) |

### Protected Folders (`folder_keys.json`)

```json
{
    "protected_paths": [
        {"path": "private", "key": "secret123"},
        {"path": "docs/confidential", "key": "another-key"}
    ]
}
```

### Hidden Folders (`folder_visibility.json`)

```json
{
    "hidden_paths": ["hidden-folder", "another/hidden"]
}
```

## API Endpoints

### File Operations

#### Browse/Download Files
```bash
# Browse root directory
curl http://localhost:8000/

# Browse specific directory
curl http://localhost:8000/docs/

# Download a file
curl -O http://localhost:8000/docs/report.pdf

# Search by filename (recursive)
curl "http://localhost:8000/?search=report&recursive=true"

# Smart/semantic search
curl "http://localhost:8000/?smart_query=machine%20learning"
```

#### Upload Files
```bash
# Upload a single file
curl -X POST http://localhost:8000/upload/docs/newfile.pdf \
  -H "X-Upload-Key: your-api-key" \
  --data-binary @localfile.pdf

# Upload to a protected folder (use folder-specific key)
curl -X POST http://localhost:8000/upload/private/secret.txt \
  -H "X-Upload-Key: folder-specific-key" \
  --data-binary @secret.txt
```

### API Endpoints (`/api/`)

#### List Subdirectories
```bash
curl -X POST http://localhost:8000/api/list-dirs \
  -H "Content-Type: application/json" \
  -d '{"path": "docs"}'
```

#### Create New Folder
```bash
# Basic folder creation
curl -X POST http://localhost:8000/api/create-folder \
  -H "Content-Type: application/json" \
  -d '{
    "parent_path": "docs",
    "folder_name": "new-folder",
    "key": "your-api-key"
  }'

# Create with password protection
curl -X POST http://localhost:8000/api/create-folder \
  -H "Content-Type: application/json" \
  -d '{
    "parent_path": "docs",
    "folder_name": "private-folder",
    "key": "your-api-key",
    "protection_password": "folder-access-password"
  }'
```

#### Delete Files/Folders
```bash
curl -X POST http://localhost:8000/api/delete-items \
  -H "Content-Type: application/json" \
  -H "X-Delete-Key: your-delete-key" \
  -d '{
    "items_to_delete": ["docs/old-file.txt", "docs/old-folder"]
  }'
```

#### Set Folder Protection
```bash
curl -X POST http://localhost:8000/api/set-path-protection \
  -H "Content-Type: application/json" \
  -d '{
    "path": "docs/confidential",
    "password": "access-password",
    "key": "your-api-key"
  }'
```

#### Hide/Unhide Folder
```bash
# Hide a folder
curl -X POST http://localhost:8000/api/toggle-hidden \
  -H "Content-Type: application/json" \
  -d '{
    "path": "docs/internal",
    "key": "your-hidden-key",
    "hide": true
  }'

# Unhide a folder
curl -X POST http://localhost:8000/api/toggle-hidden \
  -H "Content-Type: application/json" \
  -d '{
    "path": "docs/internal",
    "key": "your-hidden-key",
    "hide": false
  }'
```

#### Toggle View Hidden (Session)
```bash
curl -X POST http://localhost:8000/api/toggle-view-hidden \
  -H "Content-Type: application/json" \
  -d '{"key": "your-hidden-key"}'
```

### Utility Endpoints

#### Health Check
```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00",
  "public_dir": "./public",
  "disk_total": "500 GiB",
  "disk_used": "200 GiB",
  "disk_free": "300 GiB",
  "disk_percent_used": "40.0%"
}
```

#### Rebuild Semantic Search Index
```bash
curl -X POST http://localhost:8000/rebuild-index \
  -H "X-Upload-Key: your-api-key"
```

#### Validate Folder Access Key
```bash
curl -X POST http://localhost:8000/validate-key \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/private",
    "key": "folder-access-key"
  }'
```

## Development

### Running in Development Mode

```bash
FLASK_ENV=development python run.py
```

### Running in Production

```bash
FLASK_ENV=production python run.py
```

For production, consider using:
- Gunicorn: `gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"`
- nginx as a reverse proxy
- HTTPS/TLS certificates

### Code Organization

- **Routes**: Handle HTTP requests, delegate to services
- **Services**: Business logic, stateful operations
- **Utils**: Stateless helper functions
- **Config**: Environment-based configuration

## Legacy Support

The original monolithic `serve_public_modern.py` is kept for reference but the new modular structure in `app/` is recommended for development.

## License

MIT License

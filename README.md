# Sales RAG Slack Bot

A powerful Slack bot that integrates Salesforce data with Slack conversations using Retrieval-Augmented Generation (RAG) to provide intelligent, context-aware responses to sales questions.

## Features

- **Slack Integration**: Responds to `/sales` slash commands and mentions
- **Salesforce Integration**: Automatically syncs and searches Accounts, Opportunities, Contacts, and Cases
- **RAG-Powered Responses**: Uses OpenAI embeddings and GPT-4 for intelligent answers
- **Context-Aware**: Prioritizes thread context and conversation history
- **Continuous Learning**: Indexes Slack messages for improved context
- **Real-time Data**: Keeps Salesforce data synchronized

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Slack       │    │   FastAPI App   │    │   Salesforce    │
│                 │◄──►│                 │◄──►│                 │
│ /sales command  │    │ Slack Handler   │    │ REST API        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Vector DB     │◄──►│   RAG Engine    │◄──►│   OpenAI API    │
│  (ChromaDB)     │    │                 │    │ Embeddings/GPT  │
│ Embeddings      │    │ Search/Generate │    └─────────────────┘
└─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   SQLite DB     │
                       │ Conversations   │
                       │ Document Meta   │
                       └─────────────────┘
```

## Setup

### 1. Prerequisites

- Python 3.8+
- Slack App with Bot permissions
- Salesforce Developer Account
- OpenAI API Key

### 2. Environment Setup

1. Clone this repository:
```bash
git clone https://github.com/cdonel707/sales-rag.git
cd sales-rag
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create `.env` file:
```bash
cp .env.example .env
```

4. Configure environment variables in `.env`:

```env
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# Salesforce Configuration
SALESFORCE_USERNAME=your-salesforce-username
SALESFORCE_PASSWORD=your-salesforce-password
SALESFORCE_SECURITY_TOKEN=your-security-token
SALESFORCE_DOMAIN=  # Leave empty for standard Salesforce

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key

# Application Configuration
HOST=0.0.0.0
PORT=3000
DEBUG=false
```

### 3. Slack App Setup

1. Create a new Slack app at https://api.slack.com/apps
2. Enable the following Bot Token Scopes:
   - `app_mentions:read`
   - `channels:history`
   - `chat:write`
   - `commands`
   - `im:history`
   - `users:read`

3. Create a slash command `/sales`:
   - Command: `/sales`
   - Request URL: `https://your-domain.com/slack/events`
   - Description: "Ask sales questions using AI"
   - Usage Hint: "What opportunities are closing this month?"

4. Enable Event Subscriptions:
   - Request URL: `https://your-domain.com/slack/events`
   - Subscribe to: `app_mention`, `message.im`, `message.channels`

5. Install the app to your workspace

### 4. Salesforce Setup

1. Get your Salesforce credentials:
   - Username: Your Salesforce username
   - Password: Your Salesforce password
   - Security Token: From Setup → Personal Information → Reset My Security Token

2. Ensure your Salesforce user has API access and permissions to read:
   - Accounts
   - Opportunities
   - Contacts
   - Cases

### 5. Running the Application

1. Sync Salesforce data (first time):
```bash
python sync_data.py
```

2. Start the application:
```bash
python -m app.main
```

Or using uvicorn directly:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

3. For production, use Docker:
```bash
docker-compose up -d
```

## Usage

### Slash Command
```
/sales What opportunities are closing this month?
/sales Show me all accounts in the technology sector
/sales Who are the contacts at Acme Corp?
```

### Thread Conversations
After using the `/sales` command, you can continue the conversation in the thread:
```
User: Tell me more about the largest opportunity
Bot: Based on the context from our previous discussion...

User: What's the contact information for that account?
Bot: Here are the contacts for [Account Name]...
```

### Direct Messages
You can also DM the bot directly or mention it in channels:
```
@SalesBot What's the status of my deals?
```

## API Endpoints

- `GET /health` - Health check
- `POST /slack/events` - Slack events webhook
- `POST /sync/salesforce` - Manual data sync
- `POST /search` - Direct search (for testing)

## Data Synchronization

The bot automatically syncs Salesforce data on startup. You can also:

1. **Manual sync via API**:
```bash
curl -X POST http://localhost:3000/sync/salesforce
```

2. **Force resync**:
```bash
curl -X POST "http://localhost:3000/sync/salesforce?force=true"
```

3. **Scheduled sync** (recommended):
```bash
# Add to crontab for daily sync at 2 AM
0 2 * * * /path/to/python /path/to/sync_data.py
```

## Development

### Project Structure
```
app/
├── __init__.py
├── main.py              # FastAPI application
├── config.py            # Configuration settings
├── services.py          # Business logic services
├── database/
│   ├── __init__.py
│   └── models.py        # SQLAlchemy models
├── salesforce/
│   ├── __init__.py
│   └── client.py        # Salesforce API client
├── slack/
│   ├── __init__.py
│   └── handlers.py      # Slack event handlers
└── rag/
    ├── __init__.py
    ├── embeddings.py    # Vector embeddings
    └── generation.py    # AI response generation
```

### Adding New Salesforce Objects

1. Add query method in `app/salesforce/client.py`
2. Add processing logic in `app/services.py`
3. Update the sync method to include new objects

### Modifying Response Format

Edit the `_format_response` method in `app/slack/handlers.py`

### Adjusting Search Parameters

Modify search parameters in `app/rag/embeddings.py`:
- `n_results`: Number of documents to retrieve
- Embedding model settings
- Search filters

## Docker Deployment

Build and run with Docker:
```bash
# Build the image
docker build -t sales-rag .

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f
```

## Troubleshooting

### Common Issues

1. **Slack verification failed**
   - Check `SLACK_SIGNING_SECRET` is correct
   - Ensure request URL is accessible from internet
   - Verify ngrok tunnel is active for development

2. **Salesforce connection failed**
   - Verify credentials and security token
   - Check IP restrictions in Salesforce
   - Ensure API access is enabled
   - Leave `SALESFORCE_DOMAIN` empty for standard Salesforce

3. **OpenAI API errors**
   - Verify API key is valid
   - Check rate limits and usage
   - Monitor token consumption

4. **Database errors**
   - Check file permissions for SQLite
   - Verify ChromaDB directory is writable
   - Ensure sufficient disk space

5. **Slack timeout errors**
   - Bot responds with immediate acknowledgment
   - Processing happens asynchronously
   - Check logs for background processing errors

### Logging

Enable debug logging by setting `DEBUG=true` in `.env`

### Health Check

Monitor application health:
```bash
curl http://localhost:3000/health
```

## Production Deployment

### Using ngrok for development:
```bash
ngrok http 3000
```

### Production considerations:
1. Use a proper domain with SSL certificate
2. Set up monitoring and logging
3. Configure auto-restart (PM2, systemd)
4. Set up regular data synchronization
5. Monitor OpenAI API usage and costs

## Security Considerations

1. **Environment Variables**: Never commit `.env` file to version control
2. **Network Security**: Use HTTPS for production deployments
3. **Data Privacy**: Be mindful of Salesforce data in logs
4. **Access Control**: Limit Slack app permissions to necessary scopes
5. **API Keys**: Rotate keys regularly and monitor usage

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests if applicable
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review application logs for error details
3. Open an issue on GitHub with:
   - Description of the problem
   - Steps to reproduce
   - Relevant log excerpts
   - Environment details

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Slack integration via [Slack Bolt for Python](https://slack.dev/bolt-python/)
- Salesforce integration using [simple-salesforce](https://github.com/simple-salesforce/simple-salesforce)
- Vector embeddings powered by [OpenAI](https://openai.com/) and [ChromaDB](https://www.trychroma.com/)

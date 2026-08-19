# ✈️ AI Travel MCP Server

An MCP (Model Context Protocol) server that provides travel-related tools for AI assistants and LLM-powered applications.

The server exposes flight, hotel, airport, price analysis, and weather tools through the MCP protocol, allowing compatible AI clients to dynamically discover and use these tools for travel planning.


## 📦 Tech Stack

- Python 3.11+
- FastMCP
- SerpApi (Google Flights)
- RapidAPI / AeroDataBox (Airport Search)
- Open-Meteo (Weather, no API key required)
- Trivago MCP (Hotels)
## 🛠️ Available Tools

| Tool | Description |
|---|---|
| `search_flights_tool` | Search for available flights between destinations |
| `search_multi_city_tool` | Search for multi-city flight itineraries |
| `search_airport_tool` | Search for airports by city, airport name, or airport code |
| `cheapest_date_range_tool` | Find the cheapest travel dates within a specified date range |
| `analyze_price_insights_tool` | Analyze flight prices and determine whether a fare is relatively cheap or expensive |
| `search_hotels_tool` | Search for hotels based on destination, dates, and preferences |
| `get_weather_tool` | Retrieve weather information for a destination |
## 🏗️ Architecture

The project follows the Model Context Protocol (MCP) architecture and integrates both custom-built APIs and third-party MCP servers.

```text
┌─────────────────────────┐
│          User           │
│                         │
│ "Find cheap flights     │
│  from KL to Tokyo"      │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│      AI Client / LLM    │
│                         │
│  Understands the user's │
│  request and selects    │
│  the appropriate tools  │
└────────────┬────────────┘
             │
             │ MCP
             ▼
┌─────────────────────────────────────────┐
│        AI Travel MCP Server             │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │        Custom APIs                │  │
│  │                                   │  │
│  │  search_flights                   │  │
│  │  search_airport                   │  │
│  │  search_multi_city                │  │
│  │  analyze_price_insights           │  │
│  │  cheapest_date_range              │  │
│  │  get_weather                      │  │
│  │                                   │  │
│  │  Built and maintained by this     │  │
│  │  project                          │  │
│  └───────────────────────────────────┘  │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │     Integrated MCP Servers        │  │
│  │                                   │  │
│  │  search_hotels                    │  │
│  │                                   │  │
│  │  Provided by third-party MCP      │  │
│  │  servers                          │  │
│  └───────────────────────────────────┘  │
└──────────────────┬──────────────────────┘
                   │
          ┌────────┴─────────┐
          │                  │
          ▼                  ▼
┌──────────────────┐  ┌──────────────────────┐
│  Custom APIs     │  │ Third-Party MCP      │
│                  │  │ Servers              │
│  SerpAPI         │  │                      │
│  RapidAPI        │  │  Trivago             │
│  Open-Meteo API  │  │                      │
└──────────────────┘  └──────────────────────┘
```
## Environment Variables (required)
Create a `.env` file in the project root:
```bash
GEMINI_API_KEY=your_google_gemini_api_key
SERPAPI_API_KEY=your_serpapi_api_key
RAPIDAPI_KEY=your_rapidapi_key
```
| API | Source |
|---|---|
| Gemini API | Google AI Studio |
| SerpApi | SerpApi.com |
| RapidAPI | RapidAPI / AeroDataBox |
## 🚀 How to Run
## Option 1: Local Python

### 1. Clone this repo
```bash
git clone https://github.com/stupidFLOWERch/Ai_Travel_Agent.git
cd Ai_Travel_Agent
```

### 2. Create and activate virtual environment
```bash
python -m venv venv
venv/Scripts/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Start the mcp server (stdio mode)
```bash
python mcp_server.py
```

### 5. In another terminal, start the chat client (optional)
```bash
python mcp_client.py
```

## Option 2: Docker

### 1. Build the image
``` bash
docker compose build
```

### 2. Start the MCP server (HTTP mode, port 8000)
``` bash
docker compose up
```

### 3. Start the chat client (optional)
``` bash
docker compose --profile client run mcp-client
```

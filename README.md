# ✈️ AI Travel Agent

A multi-agent AI travel assistant that helps users plan trips through natural conversation.

The system uses a Supervisor architecture with three specialist agents (flight, hotel, weather) and integrates with external APIs through the MCP protocol. It includes a Chainlit-based web UI and can also be used as a standalone MCP server.

## 📦 Tech Stack

**Core**
- Python 3.12
- FastMCP (MCP Server)
- LangGraph (Multi-Agent Orchestration)
- Google Gemini (LLM)

**APIs / Data Sources**
- SerpAPI / Google Flights (Flight Search)
- RapidAPI / AeroDataBox (Airport Search)
- Open-Meteo (Weather, no API key required)
- Trivago MCP (Hotel Search)

**Frontend**
- Chainlit (Web Chat UI)

## 🛠️ Available Tools

The tools are distributed across three specialist agents:

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
```text
┌─────────────────────────────────────────────────────────────────────┐
│                              User                                   │
│                 "Find cheap flights from KL to Tokyo"               │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Chainlit Web UI                               │
│                  (Browser-based Chat Interface)                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Supervisor Node                                 │
│                                                                     │
│             Analyzes request → breaks into tasks                    │
│             Outputs: {"tasks": [...]}                               │
│             No tool calls — routing only                            │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Dispatcher Node                                 │
│                                                                     │
│             Routes each task to the right agent                     │
│             Controls which tools each agent can use                 │
└─────────────────────────────────────────┬───────────────────────────┘
                                          │
        ┌─────────────────────────────────┼────────────────────────┐
        │                                 │                        │
        ▼                                 ▼                        ▼
┌────────────────────────┐        ┌────────────────┐        ┌───────────────┐
│  FlightAgent           │        │  HotelAgent    │        │ WeatherAgent  │
│  (5 tools)             │        │  (1 tool)      │        │  (1 tool)     │
│                        │        │                │        │               │
│ search_flights         │        │ search_hotels  │        │ get_weather   │
│ search_multi_city      │        │ (Trivago MCP)  │        │ (Open-Meteo)  │
│ cheapest_date_range    │        │                │        │               │
│ analyze_price_insights |        │                │        │               │
│ search_airport         │        │                │        │               │
└───────┬────────────────┘        └───────┬────────┘        └───────┬───────┘
        │                                 │                         │
        └─────────────────────────────────┼─────────────────────────┘
                                          │
                                          │ MCP
                                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      AI Travel MCP Server                           │
│                     (Tool Execution Layer)                          │
│                                                                     │
│   FastMCP → SerpAPI | RapidAPI | Open-Meteo | Trivago MCP           │
└─────────────────────────────────────────────────────────────────────┘
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
## Option 1: Local Python with Web UI

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

### 4. Start the Chainlit web UI
```bash
chainlit run app.py
```

## Option 2: MCP Server Only (for Cursor / Claude Desktop)
``` bash
python mcp_server.py
```
Then configure in Cursor:
``` bash
{
  "mcpServers": {
    "travel-agent": {
      "command": "python",
      "args": ["mcp_server.py"]
    }
  }
}
```

## Option 3: Docker

### 1. Build the image
``` bash
docker compose build
```

### 2. Start the MCP Server + Chainlit UI
``` bash
docker compose up
```

### 3. Start the MCP Server only
``` bash
docker compose up mcp-server
```

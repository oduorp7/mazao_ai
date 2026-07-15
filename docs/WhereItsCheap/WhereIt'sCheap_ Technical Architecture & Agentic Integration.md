# WhereIt'sCheap: Technical Architecture & Agentic Integration

This document outlines the recommended technical architecture for integrating the "WhereIt'sCheap" Telegram bot with the Manus agentic ecosystem. This approach prioritizes real-time accuracy, minimal maintenance, and token optimization.

## 1. The "Agentic" Advantage

Traditional bots rely on static databases populated by fragile web scrapers. The Manus agentic approach fundamentally changes this paradigm:

*   **Real-Time Accuracy**: The agent acts as a live researcher, navigating supermarket websites at the exact moment a user requests a price comparison. This eliminates the risk of providing stale data.
*   **Zero Scraper Maintenance**: Traditional scrapers break when website HTML changes. Manus uses visual understanding and reasoning to navigate sites dynamically, adapting to layout changes automatically.
*   **Complex Reasoning**: The agent can handle nuanced requests (e.g., "Find the cheapest 2kg sugar, but only if they also have Fresha milk in stock") that would require complex, custom logic in a traditional bot.

## 2. High-Level Architecture Flow: The Mazao AI Integration

To enforce the **Zero Token Waste (DR-021)** policy and avoid tool fragmentation, "WhereIt'sCheap" is integrated directly into the **Mazao AI** ecosystem rather than building a standalone backend from scratch or using the Wakala OS n8n baseline.

Wakala OS was rejected for this specific use case because its n8n architecture routes all initial Telegram messages through an LLM (Mistral), violating the Zero Token Waste policy for simple price lookups. By embedding within Mazao AI, we leverage a native Python backend that can intercept requests programmatically and query the database *before* spending any AI tokens.

### 2.1. Component Breakdown

| Component | Description | Role |
| :--- | :--- | :--- |
| **User Interface** | Telegram Bot API (via Mazao AI) | Receives user queries (e.g., "/compare 2kg sugar") through the existing Mazao AI Telegram interface. |
| **Backend Service** | Mazao AI (Python `python-telegram-bot`) | Acts as the orchestrator. Intercepts the query via regex/handlers, bypassing the LangGraph AI pipeline. It checks the Supabase cache and only invokes the Manus Agent on a cache miss. |
| **The "Brain"** | Manus Agentic Ecosystem | Triggered asynchronously via `httpx` from Mazao AI. Navigates live supermarket sites (Naivas, Carrefour, Quickmart), extracts prices, performs brand matching, and returns JSON data. |
| **Database** | Supabase (Shared with Mazao AI) | Stores user profiles, handles Pro-tier billing flags (via Daraja), and serves as the primary **Smart Cache** for prices to eliminate token wastage. |

### 2.2. Core Design Principles

**1. B2C Single-Bot Topology (No Middleware)**
Unlike the Wakala OS Agency model which required spinning up new bots for new clients, this integration is a strict B2C SaaS. A single Telegram bot (`@MazaoAIBot`) serves all users concurrently. Because the backend is a native Python app using `python-telegram-bot` hosted on Fly.io, Telegram communicates **directly** with our webhook. There is zero overhead—no n8n, no Publora, and no middleware subscriptions required.

**2. Vendor Agnosticism**
While Manus AI is currently recommended for browser interactions, integrating via a custom Python backend ensures we are not locked into any single vendor. If OpenAI releases a cheaper browsing agent, or Anthropic's "Computer Use" becomes more viable, we simply swap the API call in our Python code. The core bot interface, Supabase caching, and Daraja billing remain entirely untouched.

### 2.3. Step-by-Step Data Flow

1.  **User Request**: A user sends a message to the Telegram bot: "I need 500ml Fresha milk and 1kg Mumias sugar."
2.  **Backend Processing**: The Telegram Bot API forwards the message to the Backend Service via a webhook. The backend verifies the user's subscription status.
3.  **Agent Invocation**: The Backend Service formulates a structured prompt and triggers the Manus Agent via the API (or MCP CLI).
    *   *Prompt Example*: "Navigate to Naivas and Carrefour online stores. Find the current prices for '500ml Fresha milk' and '1kg Mumias sugar'. Return a JSON object comparing the prices and identifying the cheapest option for each."
4.  **Agent Execution**: The Manus Agent autonomously navigates the specified websites, extracts the requested data, and performs the comparison logic.
5.  **Data Return**: The Agent returns the structured comparison data to the Backend Service.
6.  **Response Formatting**: The Backend Service formats the data into a user-friendly Telegram message (similar to the itemized list we generated earlier).
7.  **Delivery**: The Telegram Bot sends the final comparison list back to the user.

## 3. Token Optimization & Cost Management

When building an agentic application, managing the cost of agent invocations (tokens) is crucial. Here are strategies to optimize the "WhereIt'sCheap" architecture:

### 3.1. The "Smart Cache" Strategy

Do not trigger the agent for every single request. Implement a caching layer in your Backend Service.

*   **How it works**: When User A asks for the price of "500ml Fresha milk," the agent fetches it, and the backend stores that price in the database with a timestamp. If User B asks for the same item 30 minutes later, the backend serves the cached price instead of triggering the agent again.
*   **Benefit**: Drastically reduces agent invocations for popular items, saving tokens and improving response time.

### 3.2. Batch Processing

Encourage users to submit their entire shopping list at once, rather than asking for items one by one.

*   **How it works**: The backend aggregates the list and sends a single, comprehensive prompt to the agent (e.g., "Find prices for items X, Y, and Z").
*   **Benefit**: The agent can often find multiple items on a single page or within a single browsing session, optimizing the token usage per item.

### 3.3. Subscription Tiers (Monetization)

To offset the costs of the agentic ecosystem, implement a tiered subscription model:

*   **Free Tier**: Access to cached prices only (updated perhaps once a day). Slower response times.
*   **Premium Tier**: "Live Search" capability. The user can force the agent to fetch real-time prices. Access to advanced features like "Price Drop Alerts" (where the backend periodically triggers the agent to check specific items).

## 4. Conclusion

By utilizing the Manus agentic ecosystem as the core data engine and embedding it within the **Mazao AI** Python architecture, "WhereIt'sCheap" bypasses the traditional hurdles of web scraping while strictly adhering to the **Zero Token Waste** policy. We avoid burning LLM tokens on the "front door" (a flaw in the Wakala OS conversational baseline) by using standard Python regex to query the Supabase cache. This hybrid approach creates a "Super App" for users—managing their M-Pesa, taxes, utilities, and grocery shopping all in one place—without building redundant infrastructure.

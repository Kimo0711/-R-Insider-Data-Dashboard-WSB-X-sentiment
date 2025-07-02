├── insider_dashboard/        # Code & assets for insider-data dashboard
│   ├── app.py                # Streamlit/FastAPI entrypoint
│   ├── data_fetch.py         # Quiver API client wrappers
│   ├── requirements.txt      # Dependencies
│   └── utils/                # Helper functions & visualizations
│
├── retail_dashboard/         # Code & assets for retail-sentiment dashboard
│   ├── app.py                # Streamlit/FastAPI entrypoint
│   ├── data_fetch.py         # Quiver API client wrappers
│   ├── requirements.txt      # Dependencies
│   └── utils/                # Helper functions & visuals
│
├── shared/                   # Shared modules (authentication, config)
│   ├── config.py             # Loads and validates environment variables
│   └── quiver_client.py      # Low‑level HTTP client for Quiver endpoints
│
├── .env.example              # Example environment variables
└── README.md                 # This file


🔑 Configuration

1.Copy .env.example to .env in the project root.

2.Add your Quiver Quant API access token:
QAPI_TOKEN=your_quiver_quant_access_token_here

(Optional) Configure other settings in shared/config.py if needed.

🖥️ Running the Dashboards

Insider Data Dashboard

cd insider_dashboard
python app.py

Open a browser at http://localhost:8501 (Streamlit) or the printed FastAPI URL.

Retail Sentiment Dashboard

cd retail_dashboard
python app.py

Browse to the local URL to explore WSB & X sentiment charts.

🔍 API Endpoints Used

Congress/Senate Trades: /insider/congress & /insider/senate

Government Contracts: /contracts

WSB Mentions: /social/wsb

X (Twitter) Sentiment: /social/twitter

Refer to Quiver API docs for full details.


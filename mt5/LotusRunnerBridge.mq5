#property strict

input string RunnerUrl = "http://127.0.0.1:1111/decision";
input string RunnerApiKey = "";
input string StrategyId = "zigzag-v7";
input string StrategySymbol = "XAUUSD";
input string StrategyTimeframe = "M5";
input int PollIntervalSeconds = 5;
input bool EnableOrderExecution = false;
input long AllowedAccountLogin = 0;

int OnInit()
{
   if(EnableOrderExecution)
   {
      Print("LotusRunnerBridge refuses execution: this bridge release is telemetry/shadow only.");
      return(INIT_FAILED);
   }
   EventSetTimer(PollIntervalSeconds);
   Print("LotusRunnerBridge initialized in shadow mode. Add the runner URL to MT5 WebRequest allowlist.");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }

void OnTimer()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick)) return;
   string payload = BuildPayload(tick);
   char data[], result[];
   string headers = "Content-Type: application/json\r\n";
   if(RunnerApiKey != "") headers += "X-Lotus-Api-Key: " + RunnerApiKey + "\r\n";
   StringToCharArray(payload, data, 0, WHOLE_ARRAY, CP_UTF8);
   string response_headers = "";
   int status = WebRequest("POST", RunnerUrl, headers, 3000, data, result, response_headers);
   if(status != 200) PrintFormat("Lotus runner request failed. status=%d error=%d", status, GetLastError());
}

string BuildPayload(const MqlTick &tick)
{
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string mode = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL ? "real" : "demo";
   return "{\"bot_id\":\"" + StrategyId + "\",\"symbol\":\"" + _Symbol + "\",\"timeframe\":\"" + StrategyTimeframe +
      "\",\"bid\":" + DoubleToString(tick.bid, _Digits) + ",\"ask\":" + DoubleToString(tick.ask, _Digits) +
      ",\"account\":{\"login\":" + IntegerToString(login) + ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2) +
      ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2) + ",\"margin_free\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2) +
      ",\"server\":\"" + AccountInfoString(ACCOUNT_SERVER) + "\",\"currency\":\"" + AccountInfoString(ACCOUNT_CURRENCY) +
      "\",\"trade_mode\":\"" + mode + "\"}}";
}

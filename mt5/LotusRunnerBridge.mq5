#property strict

input string RunnerUrl = "http://127.0.0.1:1111/decision";
input string RunnerApiKey = "";
input string StrategyId = "zigzag-v7";
input string StrategySymbol = "XAUUSD";
input string StrategyTimeframe = "M5";
input int PollIntervalSeconds = 30;
// V7 needs 205 completed H1 candles; 3,000 M5 candles allow the H1 gate to warm up.
input int HistoryBars = 3000;
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
   // Exclude MQL5's trailing NUL byte; it is not part of the JSON body.
   StringToCharArray(payload, data, 0, StringLen(payload), CP_UTF8);
   string response_headers = "";
   int status = WebRequest("POST", RunnerUrl, headers, 3000, data, result, response_headers);
   if(status != 200) PrintFormat("Lotus runner request failed. status=%d error=%d", status, GetLastError());
}

string BuildPayload(const MqlTick &tick)
{
   MqlRates rates[];
   int copied = CopyRates(StrategySymbol, PERIOD_M5, 1, HistoryBars, rates);
   if(copied <= 0)
      PrintFormat("LotusRunnerBridge failed to copy M5 history. error=%d", GetLastError());
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string mode = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL ? "real" : "demo";
   return "{\"bot_id\":\"" + StrategyId + "\",\"timestamp_utc\":\"" + ToIsoUtc(TimeGMT()) + "\",\"symbol\":\"" + _Symbol + "\",\"timeframe\":\"" + StrategyTimeframe +
      "\",\"bid\":" + DoubleToString(tick.bid, _Digits) + ",\"ask\":" + DoubleToString(tick.ask, _Digits) +
      ",\"point_size\":" + DoubleToString(_Point, _Digits) + ",\"candles\":" + SerializeRates(rates, copied) +
      ",\"account\":{\"login\":" + IntegerToString(login) + ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2) +
      ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2) + ",\"margin_free\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2) +
      ",\"server\":\"" + AccountInfoString(ACCOUNT_SERVER) + "\",\"currency\":\"" + AccountInfoString(ACCOUNT_CURRENCY) +
      "\",\"trade_mode\":\"" + mode + "\"}}";
}

string SerializeRates(const MqlRates &rates[], const int count)
{
   string json = "[";
   int digits = (int)SymbolInfoInteger(StrategySymbol, SYMBOL_DIGITS);
   for(int index = 0; index < count; index++)
   {
      if(index > 0) json += ",";
      json += "{\"timestamp_utc\":\"" + ToIsoUtc(rates[index].time) + "\",";
      json += "\"open\":" + DoubleToString(rates[index].open, digits) + ",\"high\":" + DoubleToString(rates[index].high, digits);
      json += ",\"low\":" + DoubleToString(rates[index].low, digits) + ",\"close\":" + DoubleToString(rates[index].close, digits);
      json += ",\"volume\":" + IntegerToString((long)rates[index].tick_volume) + "}";
   }
   return json + "]";
}

string ToIsoUtc(const datetime value)
{
   MqlDateTime stamp;
   TimeToStruct(value, stamp);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", stamp.year, stamp.mon, stamp.day, stamp.hour, stamp.min, stamp.sec);
}

#property strict
#include <Trade\Trade.mqh>

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
input double MaxOrderLot = 0.01;
input int MaxOpenPositions = 1;
input double MaxDailyLossCurrency = 5.0;
input long MagicNumber = 1077001;

CTrade Trade;

int OnInit()
{
   if(EnableOrderExecution)
   {
      if(AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
      {
         Print("LotusRunnerBridge refuses execution: only demo accounts are allowed.");
         return(INIT_FAILED);
      }
      if(AllowedAccountLogin <= 0 || AccountInfoInteger(ACCOUNT_LOGIN) != AllowedAccountLogin)
      {
         PrintFormat("LotusRunnerBridge refuses execution: login %I64d is not the allowed demo login %I64d.", AccountInfoInteger(ACCOUNT_LOGIN), AllowedAccountLogin);
         return(INIT_FAILED);
      }
      if(MaxOrderLot <= 0 || MaxOrderLot > 0.01 || MaxOpenPositions != 1 || MaxDailyLossCurrency <= 0)
      {
         Print("LotusRunnerBridge refuses execution: unsafe risk limits.");
         return(INIT_FAILED);
      }
      Trade.SetExpertMagicNumber(MagicNumber);
      Trade.SetDeviationInPoints(30);
      Trade.SetTypeFillingBySymbol(StrategySymbol);
      Print("LotusRunnerBridge initialized in DEMO EXECUTION mode. Risk limits are active.");
   }
   else
   {
      Print("LotusRunnerBridge initialized in shadow mode. Add the runner URL to MT5 WebRequest allowlist.");
   }
   EventSetTimer(PollIntervalSeconds);
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
   if(status != 200)
   {
      PrintFormat("Lotus runner request failed. status=%d error=%d", status, GetLastError());
      return;
   }
   if(EnableOrderExecution)
      ExecuteDecision(CharArrayToString(result));
}

void ExecuteDecision(const string response)
{
   string action = JsonString(response, "action");
   if(action != "buy" && action != "sell") return;
   if(CountOwnPositions() >= MaxOpenPositions || DailyLossExceeded()) return;
   double volume = MathMin(JsonNumber(response, "size"), MaxOrderLot);
   double sl = JsonNumber(response, "stop_loss_price");
   double tp = JsonNumber(response, "take_profit_price");
   if(volume <= 0 || sl <= 0 || tp <= 0) return;
   volume = NormalizeVolume(volume);
   if(volume <= 0) return;
   bool sent = action == "buy" ? Trade.Buy(volume, StrategySymbol, 0.0, sl, tp, "Lotus V7 demo") : Trade.Sell(volume, StrategySymbol, 0.0, sl, tp, "Lotus V7 demo");
   PrintFormat("Lotus demo order %s sent=%s retcode=%u comment=%s", action, sent ? "true" : "false", Trade.ResultRetcode(), Trade.ResultRetcodeDescription());
}

int CountOwnPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) == StrategySymbol && PositionGetInteger(POSITION_MAGIC) == MagicNumber) count++;
   }
   return count;
}

bool DailyLossExceeded()
{
   MqlDateTime now;
   TimeToStruct(TimeCurrent(), now);
   now.hour = 0; now.min = 0; now.sec = 0;
   datetime start = StructToTime(now);
   if(!HistorySelect(start, TimeCurrent())) return true;
   double pnl = 0.0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != StrategySymbol || HistoryDealGetInteger(ticket, DEAL_MAGIC) != MagicNumber) continue;
      pnl += HistoryDealGetDouble(ticket, DEAL_PROFIT) + HistoryDealGetDouble(ticket, DEAL_SWAP) + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
   }
   return pnl <= -MaxDailyLossCurrency;
}

double NormalizeVolume(const double requested)
{
   double step = SymbolInfoDouble(StrategySymbol, SYMBOL_VOLUME_STEP);
   double minimum = SymbolInfoDouble(StrategySymbol, SYMBOL_VOLUME_MIN);
   double maximum = MathMin(SymbolInfoDouble(StrategySymbol, SYMBOL_VOLUME_MAX), MaxOrderLot);
   if(step <= 0 || minimum <= 0 || maximum < minimum) return 0.0;
   double volume = MathFloor(MathMin(requested, maximum) / step) * step;
   return volume < minimum ? 0.0 : NormalizeDouble(volume, 2);
}

string JsonString(const string json, const string key)
{
   string needle = "\"" + key + "\":\"";
   int start = StringFind(json, needle);
   if(start < 0) return "";
   start += StringLen(needle);
   int end = StringFind(json, "\"", start);
   return end < 0 ? "" : StringSubstr(json, start, end - start);
}

double JsonNumber(const string json, const string key)
{
   string needle = "\"" + key + "\":";
   int start = StringFind(json, needle);
   if(start < 0) return 0.0;
   start += StringLen(needle);
   int end = start;
   while(end < StringLen(json))
   {
      ushort c = StringGetCharacter(json, end);
      if((c >= '0' && c <= '9') || c == '.' || c == '-' || c == '+') end++; else break;
   }
   return StringToDouble(StringSubstr(json, start, end - start));
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

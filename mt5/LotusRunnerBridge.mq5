#property strict
#include <Trade\Trade.mqh>

input string RunnerUrl = "http://127.0.0.1:1111/decision";
input string RunnerApiKey = "";
input string StrategyId = "zigzag-v7";
input string StrategySymbol = "XAUUSD";
input string StrategyTimeframe = "M5";
input string CollectorId = "lotus-runner-bridge-01";
input int SendIntervalMilliseconds = 50;
input int HistoryRefreshSeconds = 30;
// V7 needs 205 completed H1 candles; 3,000 M5 candles allow the H1 gate to warm up.
input int HistoryBars = 3000;
input bool EnableOrderExecution = false;
input long AllowedAccountLogin = 0;
input double MaxOrderLot = 0.01;
input int MaxOpenPositions = 1;
input double MaxDailyLossCurrency = 5.0;
input long MagicNumber = 1077001;
input int MinOrderIntervalSeconds = 5;

CTrade Trade;

struct CollectedTick
{
   long time_msc;
   ulong sequence;
   double bid;
   double ask;
   double last;
   ulong volume;
   double volume_real;
   uint flags;
};

CollectedTick TickBuffer[];
ulong TickSequence = 0;
datetime LastHistoryRefresh = 0;
datetime LastOrderAt = 0;
string LatestBookJson = "[]";
bool BookAvailable = false;

int OnInit()
{
   if(_Symbol != StrategySymbol || SendIntervalMilliseconds < 10 || SendIntervalMilliseconds > 1000)
   {
      Print("LotusRunnerBridge requires the configured symbol chart and a 10-1000 ms send interval.");
      return(INIT_PARAMETERS_INCORRECT);
   }
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
   BookAvailable = MarketBookAdd(StrategySymbol);
   if(!BookAvailable)
      Print("LotusRunnerBridge order book unavailable; structural entries will remain blocked.");
   EventSetMillisecondTimer(SendIntervalMilliseconds);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(BookAvailable) MarketBookRelease(StrategySymbol);
}

void OnTick()
{
   MqlTick tick;
   if(!SymbolInfoTick(StrategySymbol, tick)) return;
   int count = ArraySize(TickBuffer);
   if(count >= 2000)
   {
      for(int index = 1; index < count; index++) TickBuffer[index - 1] = TickBuffer[index];
      ArrayResize(TickBuffer, count - 1);
      count--;
   }
   ArrayResize(TickBuffer, count + 1);
   TickBuffer[count].time_msc = tick.time_msc;
   TickBuffer[count].sequence = TickSequence++;
   TickBuffer[count].bid = tick.bid;
   TickBuffer[count].ask = tick.ask;
   TickBuffer[count].last = tick.last;
   TickBuffer[count].volume = tick.volume;
   TickBuffer[count].volume_real = tick.volume_real;
   TickBuffer[count].flags = tick.flags;
}

void OnBookEvent(const string &symbol)
{
   if(symbol != StrategySymbol) return;
   LatestBookJson = SerializeBook();
   BookAvailable = LatestBookJson != "[]";
}

void OnTimer()
{
   if(ArraySize(TickBuffer) == 0) return;
   MqlTick tick;
   if(!SymbolInfoTick(StrategySymbol, tick)) return;
   bool includeHistory = LastHistoryRefresh == 0 || TimeCurrent() - LastHistoryRefresh >= HistoryRefreshSeconds;
   string payload = BuildPayload(tick, includeHistory);
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
   ArrayResize(TickBuffer, 0);
   if(includeHistory) LastHistoryRefresh = TimeCurrent();
   if(EnableOrderExecution)
      ExecuteDecision(CharArrayToString(result));
}

void ExecuteDecision(const string response)
{
   string action = JsonString(response, "action");
   string requestId = JsonString(response, "request_id");
   if(action != "buy" && action != "sell") return;
   if(CountOwnPositions() >= MaxOpenPositions || DailyLossExceeded()) return;
   if(LastOrderAt > 0 && TimeCurrent() - LastOrderAt < MinOrderIntervalSeconds) return;
   double volume = MathMin(JsonNumber(response, "size"), MaxOrderLot);
   double sl = JsonNumber(response, "stop_loss_price");
   double tp = JsonNumber(response, "take_profit_price");
   if(volume <= 0 || sl <= 0 || tp <= 0) return;
   volume = NormalizeVolume(volume);
   if(volume <= 0) return;
   bool sent = action == "buy" ? Trade.Buy(volume, StrategySymbol, 0.0, sl, tp, "Lotus V7 demo") : Trade.Sell(volume, StrategySymbol, 0.0, sl, tp, "Lotus V7 demo");
   if(sent) LastOrderAt = TimeCurrent();
   PrintFormat("Lotus demo order %s sent=%s retcode=%u comment=%s", action, sent ? "true" : "false", Trade.ResultRetcode(), Trade.ResultRetcodeDescription());
   ReportExecution(requestId, action, sent, Trade.ResultRetcode());
}

void ReportExecution(const string requestId, const string action, const bool sent, const uint retcode)
{
   if(requestId == "") return;
   string url = RunnerUrl;
   StringReplace(url, "/decision", "/execution");
   string payload = "{\"request_id\":\"" + requestId + "\",\"action\":\"" + action + "\",\"sent\":" + (sent ? "true" : "false") + ",\"retcode\":" + IntegerToString((int)retcode) + "}";
   char data[], result[];
   StringToCharArray(payload, data, 0, StringLen(payload), CP_UTF8);
   string headers = "Content-Type: application/json\r\n";
   if(RunnerApiKey != "") headers += "X-Lotus-Api-Key: " + RunnerApiKey + "\r\n";
   string responseHeaders = "";
   int status = WebRequest("POST", url, headers, 3000, data, result, responseHeaders);
   if(status != 200) PrintFormat("Lotus execution audit failed. status=%d error=%d", status, GetLastError());
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

string BuildPayload(const MqlTick &tick, const bool includeHistory)
{
   MqlRates rates[];
   int copied = includeHistory ? CopyRates(StrategySymbol, PERIOD_M5, 1, HistoryBars, rates) : 0;
   if(includeHistory && copied <= 0)
      PrintFormat("LotusRunnerBridge failed to copy M5 history. error=%d", GetLastError());
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string mode = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL ? "real" : "demo";
   int lastIndex = ArraySize(TickBuffer) - 1;
   string requestId = CollectorId + "-" + IntegerToString(TickBuffer[lastIndex].time_msc) + "-" + IntegerToString((long)TickBuffer[lastIndex].sequence);
   return "{\"bot_id\":\"" + StrategyId + "\",\"collector_id\":\"" + CollectorId + "\",\"request_id\":\"" + requestId + "\",\"timestamp_utc\":\"" + ToIsoUtc(TimeGMT()) + "\",\"symbol\":\"" + StrategySymbol + "\",\"timeframe\":\"" + StrategyTimeframe +
      "\",\"bid\":" + DoubleToString(tick.bid, _Digits) + ",\"ask\":" + DoubleToString(tick.ask, _Digits) +
      ",\"spread_points\":" + DoubleToString((tick.ask - tick.bid) / _Point, 3) +
      ",\"point_size\":" + DoubleToString(_Point, _Digits) + ",\"ticks\":" + SerializeTicks() + ",\"order_book\":" + LatestBookJson + ",\"candles\":" + SerializeRates(rates, copied) +
      ",\"account\":{\"login\":" + IntegerToString(login) + ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2) +
      ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2) + ",\"margin_free\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2) +
      ",\"server\":\"" + AccountInfoString(ACCOUNT_SERVER) + "\",\"currency\":\"" + AccountInfoString(ACCOUNT_CURRENCY) +
      "\",\"trade_mode\":\"" + mode + "\"}}";
}

string SerializeTicks()
{
   string json = "[";
   int digits = (int)SymbolInfoInteger(StrategySymbol, SYMBOL_DIGITS);
   for(int index = 0; index < ArraySize(TickBuffer); index++)
   {
      if(index > 0) json += ",";
      CollectedTick item = TickBuffer[index];
      json += "{\"time_msc\":" + IntegerToString(item.time_msc) + ",\"sequence\":" + IntegerToString((long)item.sequence);
      json += ",\"bid\":" + DoubleToString(item.bid, digits) + ",\"ask\":" + DoubleToString(item.ask, digits) + ",\"last\":" + DoubleToString(item.last, digits);
      json += ",\"volume\":" + IntegerToString((long)item.volume) + ",\"volume_real\":" + DoubleToString(item.volume_real, 8) + ",\"flags\":" + IntegerToString((int)item.flags) + "}";
   }
   return json + "]";
}

string SerializeBook()
{
   MqlBookInfo book[];
   if(!MarketBookGet(StrategySymbol, book)) return "[]";
   string json = "[";
   int written = 0;
   int digits = (int)SymbolInfoInteger(StrategySymbol, SYMBOL_DIGITS);
   for(int index = 0; index < ArraySize(book); index++)
   {
      string side = "";
      if(book[index].type == BOOK_TYPE_BUY || book[index].type == BOOK_TYPE_BUY_MARKET) side = "bid";
      if(book[index].type == BOOK_TYPE_SELL || book[index].type == BOOK_TYPE_SELL_MARKET) side = "ask";
      if(side == "") continue;
      if(written++ > 0) json += ",";
      double volume = book[index].volume_real > 0 ? book[index].volume_real : (double)book[index].volume;
      json += "{\"side\":\"" + side + "\",\"price\":" + DoubleToString(book[index].price, digits) + ",\"volume\":" + DoubleToString(volume, 8) + "}";
   }
   return json + "]";
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

"""Plain language explanations shown under each table and chart ("How to read it").

Keys: notebook name -> index of the code cell (0 is the setup cell) -> text.
"""
NOTES = {
"01_nvda_preview": {
 1: "The share price today, the record it reached in October and how far below it the stock is now. The analyst target is the "
    "average price that brokers expect in 12 months; a large upside to target with a falling share price means analysts are "
    "far more positive than the market.",
 2: "Each bar is the change in the share price on the trading day after a results release. Blue bars are rises, red bars are "
    "falls. Most bars are red even though NVIDIA usually beats estimates: good results are already expected, so beating them "
    "is not enough to lift the stock.",
 3: "The Build-out Index measures how close the customers' AI data centres are to receiving NVIDIA chips, from 0% (empty site) "
    "to 100% (halls running). Each campus counts in proportion to its planned power. GW in fit-out is the capacity already "
    "at the stage where chips are installed. A rising index means more demand is about to turn into revenue. These "
    "satellite readings are prototype data.",
 4: "A simple line through three past quarters: how much revenue NVIDIA made for each gigawatt of data centre capacity that "
    "was ready for chips one quarter earlier. Applied to today's capacity it gives a first estimate of next quarter's revenue. "
    "If that estimate is well above what the market expects, the outlook is the surprise to watch.",
 5: "Our probability that NVIDIA beats earnings estimates, against the price of the same question on Polymarket (a price of "
    "94 cents means the market sees a 94% chance). The gap is our number minus the market's. Within 3 points we call it "
    "priced in: there is no edge. The table shows the live Polymarket contract we compare with.",
 6: "Left: how the Polymarket probability of a beat moved in the weeks before the report. Right: Kalshi markets on words "
    "the CEO will say on the results call. A high price on 'Rubin' means traders expect the new chip to be a main topic.",
 7: "Each row is a Polymarket contract that pays out if NVIDIA closes November above a given price. Reading down the table "
    "gives the market's view of where the stock will be after the results: the price of each contract is the probability.",
 8: "Share of posts about NVIDIA on X by topic over the last 30 days, and whether each topic is positive or negative for the "
    "stock. It shows what investors are worried about. Topic shares are prototype outputs of a language model.",
 10: "Left: weekly memory cargo flown to US server assembly sites (prototype). Right: Micron's share price, the market's "
     "read on memory prices. More cargo without a jump in memory prices points to easing costs, which supports margins.",
 11: "How much the stock moved in the week, month and three months before the release, against the chip sector (SMH) "
     "and the S&P 500 (SPY). A big run-up raises the bar: the result has to beat what the price already assumes.",
 12: "Valuation multiples against peers and against NVIDIA's own past: forward P/E is the price over next year's expected "
     "earnings. A premium to peers or to its own median means more good news is already in the price. The second table "
     "is the analysts' consensus and the range of their price targets.",
 13: "The few figures that will move the stock this quarter, why, and whether our data can observe each one. Where the "
     "answer is no, the report relies on markets and attention instead of the satellite layer.",
 14: "What could make our reading wrong and what we do about it, then where every figure comes from and whether it is "
     "real data or a prototype output.",
 9: "What the share price is likely to do for each possible result, from a miss to a beat with strong guidance. The last line "
    "sums up the report: the beat is priced in, the stronger Q4 outlook suggested by the satellite data is not.",
},
"02_brent_preview": {
 1: "Brent crude over 2026. The spike in spring is the closure of the Strait of Hormuz; the recent fall is the market "
    "betting on a US Iran deal. The line above the chart gives the price today, the weekly move and the distance from the "
    "high and the low of the year.",
 2: "Left: oil passing through the Strait of Hormuz, in million barrels a day, before the war and in the last two months: "
    "flows are recovering but still well below normal. Right and in the table: how full the main storage hubs are, measured "
    "from the shadows inside floating roof tanks (prototype data). Falling levels mean buyers are using stocks to replace "
    "lost supply.",
 3: "Left: on Kalshi, each contract pays if Brent closes November above a given price, so the line shows the market's "
    "probability for every level; the dashed line marks $96, the level of our call. Right: how the probability of a close "
    "above $96 changed day by day; the dotted line is its value on 9 November, when the report was written.",
 4: "Left: the Kalshi probability that traffic through Hormuz returns to normal before each date. Right: Polymarket "
    "probabilities that WTI touches each price before December (red: falls to that level, blue: rises to it). The lines above "
    "compare today's Polymarket prices on the ceasefire and on Hormuz with those of 9 November.",
 5: "Our probability comes from three scenarios for 30 November. Each has a weight (how likely we think it is) and a price "
    "range. The last column is the chance that Brent ends above $96 in that scenario. Weighted together they give our "
    "probability, which we compare with the market's on 9 November and today.",
 6: "Each cell is the gap between our probability and Kalshi's on 9 November if we had chosen different weights for the "
    "deal and collapse scenarios. Blue cells mean we are more bullish than the market, red cells less. The call only flips "
    "if we give the deal scenario a much larger weight than we did.",
 7: "How much Brent and energy stocks moved, on average, when a prediction market probability rose by 10 points. The beta is "
    "the move in %, t is how reliable it is (above 2 in absolute value is statistically significant), r2 how much of the "
    "daily moves it explains and n the number of days used.",
 9: "The pricing check: the Brent premium over US crude, the premium of a physical Gulf grade (Murban) over Brent, US "
    "stocks against their 5 year average from the EIA weekly report, and the EIA's own price outlook. Low stocks and a "
    "physical premium say the market is still short of barrels.",
 10: "Left: the price of each Brent futures contract for the next 12 months. Right: the near contract minus the sixth. "
     "Above zero (backwardation) buyers pay more for oil now than later, a sign supply is tight; below zero the opposite.",
 11: "The factors that will move Brent this month, why, and whether our data can observe each one.",
 12: "What could make our reading wrong and what we do about it, then the source of every figure and whether it is real "
     "data, a prototype output or our own view.",
 8: "Share of oil posts on X by topic over the last week, and whether each topic points to lower or higher prices. Most of "
    "the attention is on the talks, little on the tankers still waiting: this is the gap the report points to. Prototype data.",
},
"03_event_betas": {
 1: "The events we test and how many trading days of data each one has. Events that started recently, such as the Hormuz "
    "market, have fewer days and less reliable results.",
 2: "Each cell is the average return of an asset (rows) on a day when the probability of an event (columns) rose by 10 points. "
    "Blue means the asset tends to rise, red that it tends to fall; the darker the colour, the more reliable the result. "
    "One star means significant at 5%, two stars at 1%. For example, Brent futures fall when the odds of Hormuz reopening "
    "rise, and rise when the odds of a US invasion of Iran rise.",
 3: "A test on data the model had not seen: betas estimated before January 2026 are used to predict returns on later days "
    "with large moves in the odds. A hit rate near 50% and a correlation near zero mean they do not predict returns, so we "
    "use them as a map of risk, not as a trading signal.",
 4: "Three model portfolios. The first columns show how much each portfolio moves for a 10 point rise in each event "
    "probability; the last two show the total move under two scenarios: a deal signed (Hormuz reopens) and talks "
    "collapsing. This is how a fund sees which events it is exposed to.",
},
"04_track_record": {
 1: "The two calls made in the reports of 9 November: our probability, the market's and where the market price comes from. "
    "The Brier score measures how good a probability was once the outcome is known: 0 is perfect, 0.25 is a coin toss, so "
    "lower is better. It stays 'pending' until the event happens.",
 2: "What the scores would be for each of the four possible outcomes. Skill compares us with the market: above 0 means our "
    "probabilities were closer to what happened than the market's, below 0 that the market was better.",
},
"05_dashboard": {
 1: "The gap ranking that heads the dashboard: for each live call, our probability, the market's, the gap in points and how "
    "much the market moved in the last week. The biggest gaps come first.",
 2: "Key dates in the next two weeks for every company and commodity we cover, plus the later dates of the two live "
    "calls: results, official inventory and crop reports, OPEC+ meetings and settlement of prediction market contracts. "
    "The same report for several names (for example USDA Crop Progress) is one row.",
 3: "The alerts a client would have received in the last month: a gap above 5 points, a prediction market moving 10 points "
    "in a day, or a price moving more than 4% in a day.",
 4: "Writes the dashboard page (dashboard.html) from the tables above. The page has filters by sector, region and size "
    "of the gap, and each name links to its signal page.",
 5: "One signal page per covered name: index histories, prediction market odds, attention and the supply chain map. The "
    "table counts what each page shows; live alerts are earthquakes within 100 km or fires within 30 km of a place.",
 6: "What each tier gets. Free users see the calendar, headline odds, attention and a basic search; live satellite "
    "readings, the gap ranking and monitors are for institutional clients only.",
},
"06_ticker_search": {
 1: "The page a client sees after typing a ticker. Top: price and recent moves. Left: every Kalshi and Polymarket contract "
    "linked to the name, with the probability the market gives it. Right: the gap and the next event, analyst consensus, "
    "the assets that move with it (corr is the correlation of daily returns over a year: 1 means they move together) and "
    "the signals we track, each of which can be turned into a monitor. Below: the history of each satellite index, the "
    "supply chain map with live alerts and attention on X.",
 2: "The same page for Brent crude: most linked markets are about Hormuz traffic and the US Iran talks, which drive the price.",
 3: "The same page for copper: Kalshi month-end price contracts and the mining stocks most exposed to the copper price.",
 4: "Corn: the map shows the growing regions and the export port; the weather table compares rain over the last 30 days "
    "with the usual amount for the time of year. Very dry or very wet regions are what moves crop prices.",
 5: "Coffee: the Brazilian, Vietnamese and Colombian growing regions. Dry weather in Minas Gerais during flowering is the "
    "classic driver of coffee price spikes.",
 6: "The free version of the NVIDIA page: locked boxes mark what only institutional clients see.",
},
"07_monitors": {
 1: "The copper mines the monitor watches, with their location and the share of each company's copper output that comes "
    "from them (illustrative figures). A problem at a mine that is a large share of a company's output is what moves its shares.",
 2: "The live check: earthquakes of magnitude 4.5 or more in the last 30 days (from the US Geological Survey) and how far "
    "each one was from a watched mine. An alert needs a quake within 30 km; the wider distances show that the feed works.",
 3: "Replay of the Grasberg incident. The monitor fires on the day activity at the mine falls more than 20% below its usual "
    "level. The row shows the mine, why the alert fired, which company is exposed, how much the company's shares and "
    "copper prices moved in the following 30 days, and who is likely to gain (other producers) or lose (the owner and "
    "copper users such as cable makers).",
 4: "Freeport shares (red) and copper futures (blue), both set to 100 on the alert day (dashed line). Freeport fell about 20% "
    "when it declared force majeure two weeks later, while copper rose on fears of lower supply: a monitor gives a fund "
    "time to act before that move.",
 5: "Days when a prediction market we follow moved by 10 points or more. These are the moments a client with a monitor "
    "on that event would have been alerted.",
 6: "Fires detected by NASA satellites near the places we cover. Most are farm or bush fires near growing regions; a fire "
    "next to a mine or a plant is what would trigger a monitor.",
 7: "A portfolio monitor: each holding is mapped to the mines, ports and plants it depends on, and every place is checked "
    "against the live earthquake and fire feeds.",
},
}

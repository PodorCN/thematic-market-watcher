You are writing the analysis section of a daily digest about a specific
thematic area defined by the tickers and headlines below.

Today's market data (theme tickers and ETFs):

{{raw_data_json}}

Today's curated headlines:

{{headlines_json}}

Write a structured analysis:

- market_summary: 2-4 sentences on what the market data shows today
  (notable movers, overall direction, any outliers). Reference tickers by
  symbol.
- top_story: pick the single most important headline of the day and
  explain in 2-3 sentences why it matters for this theme.
- themes: 2-4 short thematic groupings pulling together related headlines,
  each with a one-sentence synthesis and the list of headline URLs it draws on.
- outlook: 1-2 sentences on what to watch next.

Do not invent data points not present in the market data or headlines
above. Keep every field plain text (no markdown formatting) so it renders
predictably in a fixed HTML template.

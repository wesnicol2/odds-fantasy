import json
from refactored import aggregator
from predicted_stats import predict_stats_for_player

with open('tests/resources/odds-api-responses/example-qb-response.json','r',encoding='utf-8') as f:
    event = json.load(f)

for alias in ['Dak Prescott','Daniel Jones']:
    per_player_odds, per_player_summaries = aggregator.aggregate_players_from_event(event, {alias})
    by_book = per_player_odds.get(alias)
    market_summ = per_player_summaries.get(alias)
    print('\nPlayer:', alias)
    if not by_book:
        print('  No markets found in example for this player.')
        continue
    means = predict_stats_for_player(by_book)
    print('  Means per market:', means)
    if market_summ:
        for k,v in market_summ.items():
            print('  Summary', k, v)

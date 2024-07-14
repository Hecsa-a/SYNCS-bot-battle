from collections import defaultdict, deque
import random
from typing import Optional, Tuple, Union, cast
from risk_helper.game import Game
from risk_shared.models.card_model import CardModel
from risk_shared.queries.query_attack import QueryAttack
from risk_shared.queries.query_claim_territory import QueryClaimTerritory
from risk_shared.queries.query_defend import QueryDefend
from risk_shared.queries.query_distribute_troops import QueryDistributeTroops
from risk_shared.queries.query_fortify import QueryFortify
from risk_shared.queries.query_place_initial_troop import QueryPlaceInitialTroop
from risk_shared.queries.query_redeem_cards import QueryRedeemCards
from risk_shared.queries.query_troops_after_attack import QueryTroopsAfterAttack
from risk_shared.queries.query_type import QueryType
from risk_shared.records.moves.move_attack import MoveAttack
from risk_shared.records.moves.move_attack_pass import MoveAttackPass
from risk_shared.records.moves.move_claim_territory import MoveClaimTerritory
from risk_shared.records.moves.move_defend import MoveDefend
from risk_shared.records.moves.move_distribute_troops import MoveDistributeTroops
from risk_shared.records.moves.move_fortify import MoveFortify
from risk_shared.records.moves.move_fortify_pass import MoveFortifyPass
from risk_shared.records.moves.move_place_initial_troop import MovePlaceInitialTroop
from risk_shared.records.moves.move_redeem_cards import MoveRedeemCards
from risk_shared.records.moves.move_troops_after_attack import MoveTroopsAfterAttack
from risk_shared.records.record_attack import RecordAttack
from risk_shared.records.types.move_type import MoveType
import time
import math
# We will store our enemy in the bot state.
class BotState():
    def __init__(self):
        self.enemy: Optional[int] = None


def main():
    
    # Get the game object, which will connect you to the engine and
    # track the state of the game.
    game = Game()
    bot_state = BotState()
   
    # Respond to the engine's queries with your moves.
    while True:

        # Get the engine's query (this will block until you receive a query).
        query = game.get_next_query()

        # Based on the type of query, respond with the correct move.
        def choose_move(query: QueryType) -> MoveType:
            match query:
                case QueryClaimTerritory() as q:
                    return handle_claim_territory(game, bot_state, q)

                case QueryPlaceInitialTroop() as q:
                    return handle_place_initial_troop(game, bot_state, q)

                case QueryRedeemCards() as q:
                    return handle_redeem_cards(game, bot_state, q)

                case QueryDistributeTroops() as q:
                    return handle_distribute_troops(game, bot_state, q)

                case QueryAttack() as q:
                    return handle_attack(game, bot_state, q)

                case QueryTroopsAfterAttack() as q:
                    return handle_troops_after_attack(game, bot_state, q)

                case QueryDefend() as q:
                    return handle_defend(game, bot_state, q)

                case QueryFortify() as q:
                    return handle_fortify(game, bot_state, q)
        
        # Send the move to the engine.
        game.send_move(choose_move(query))
    
def handle_claim_territory(game: Game, bot_state: BotState, query: QueryClaimTerritory) -> MoveClaimTerritory:
    """At the start of the game, you can claim a single unclaimed territory every turn 
    until all the territories have been claimed by players."""
    
    # General information used
    unclaimed_territories = game.state.get_territories_owned_by(None)
    my_territories = game.state.get_territories_owned_by(game.state.me.player_id)
    all_territories = [territory for territory in game.state.territories]
    enemy_territories = list((set(all_territories) - set(unclaimed_territories)) - set(my_territories))
    adjacent_territories = game.state.get_all_adjacent_territories(my_territories)
    continents = game.state.map.get_continents()

    # Gives number of friendly territories adjacent 
    def count_adjacent_friendly(territory: int) -> int:
        return len(set(my_territories) & set(game.state.map.get_adjacent_to(territory)))
    
    # Gives the proportion of a continent owned by you that the territory is from
    def proportion_continent_of_territory(territory: int) -> float:
        for continent in continents:
            if territory in continents[continent]:
                return len(set(my_territories) & set(continents[continent]))/len(continents[continent])
        else:
            return 0

    # Returns 1 or 0 whether the territory will break an enemy continent
    def almost_completed_enemy_continent(territory: int) -> int:
        for continent in continents:
            if territory in continents[continent]:
                for player in game.state.players:
                    if len(set(continents[continent]) & set(game.state.get_territories_owned_by(player))) == len(continents[continent]) - 1:
                        return 1
        else:
            return 0
        
    # Gives the proportion of a continent owned by enemies that the territory is from
    def proportion_of_enemy_competing_continent(territory: int) -> float:
        for continent in continents:
            if territory in continents[continent]:
                return len((set(continents[continent]) - (set(my_territories))) - set(unclaimed_territories))/len(continents[continent]) 

    # Gives from 0 to 3 based on how close the nearest enemy territory is, 3 being highest        
    def aggresively_guarding(territory: int) -> float:
        edges_to_enemy = 0
        if territory in adjacent_territories:
            next_edges = list(set(game.state.map.get_adjacent_to(territory)) - set(my_territories))
            checked_edges = [territory]
            while (len(next_edges) != 0):
                edges_to_enemy += 1
                if len(set(enemy_territories) & set(next_edges)) > 0:
                    return 1/edges_to_enemy
                else:
                    checked_edges.extend(next_edges)
                    next_edges = list((set(game.state.get_all_adjacent_territories(next_edges)) - set(my_territories)) - set(checked_edges))
            return 0
        else:
            return 0
    
    # Favouring specific continents
    def favourable_continent(territory: int) -> float:
        continent_weightings = [0.7, 0.5, 0.5, 0.8, 0.8, 0.7]
        for continent in continents:
            if territory in continents[continent]:
                return continent_weightings[continent]
        return 0

    # Claiming territories that are sealed so that enemies do not take it 
    def enclose(territory: int) -> int:
        if (set(game.state.map.get_adjacent_to(territory)) & set(my_territories)) == set(game.state.map.get_adjacent_to(territory)):
            return 1
        else: 
            return 0
        
    # For weightings
    territory_weights = defaultdict(lambda: 0.0)

    # Coefficients for weightings
    adjacent = 2
    same_continent = 6
    swap_continent = 0.05
    break_continent = 2
    guarding = 0.6
    enclose_territory = 5
    favouring = 1

    # Calculating each territory weight
    for territory in unclaimed_territories:
        territory_weights[territory] = \
            adjacent*count_adjacent_friendly(territory)*len(my_territories) \
            + same_continent*proportion_continent_of_territory(territory) \
            - swap_continent*proportion_of_enemy_competing_continent(territory)*(9 - len(my_territories))**3 \
            + favouring*favourable_continent(territory) \
            + break_continent*almost_completed_enemy_continent(territory) \
            + guarding*aggresively_guarding(territory)*proportion_continent_of_territory(territory)*(9 - len(my_territories)) \
            + enclose_territory*enclose(territory)

    # Sorting and selecting the territories
    territory_weights = sorted(territory_weights, key=lambda x: territory_weights[x], reverse=True)
    selected_territory = list(territory_weights)[0]

    return game.move_claim_territory(query, selected_territory)            

def handle_place_initial_troop(game: Game, bot_state: BotState, query: QueryPlaceInitialTroop) -> MovePlaceInitialTroop:
    """After all the territories have been claimed, you can place a single troop on one
    of your territories each turn until each player runs out of troops."""
    
    # General information
    unclaimed_territories = game.state.get_territories_owned_by(None)
    my_territories = game.state.get_territories_owned_by(game.state.me.player_id)
    all_territories = [territory for territory in game.state.territories]
    enemy_territories = list((set(all_territories) - set(unclaimed_territories)) - set(my_territories))
    continents = game.state.map.get_continents()
    border_territories = game.state.get_all_border_territories(my_territories)

    # Gives the proportion of a continent owned by you that the territory is from
    def proportion_continent_of_territory(territory: int) -> float:
        for continent in continents:
            if territory in continents[continent]:
                return len(set(my_territories) & set(continents[continent]))/len(continents[continent])
        else:
            return 0
    
    # Ratio of enemies near the territory to the number of friendly troops near those enemies
    def difference_number_enemy(territory: int) -> float:
        adjacent_enemies = list(set(game.state.map.get_adjacent_to(territory)) & set(enemy_territories))
        adjacent_friendlies = list(set(my_territories) & set(game.state.get_all_adjacent_territories(adjacent_enemies)))
        friendlies = 0.1
        for friendly in adjacent_friendlies:
            friendlies += game.state.territories[friendly].troops - 1
        adjacent_enemy_troops = 1
        for adjacent_enemy in adjacent_enemies:
            adjacent_enemy_troops += game.state.territories[adjacent_enemy].troops - 1
        return adjacent_enemy_troops/friendlies
    
    # Returns the number of adjacent friendly territories
    def count_adjacent_friendly(territory: int) -> int:
        return len(set(my_territories) & set(game.state.map.get_adjacent_to(territory)))

    # This measures how many connected territories there would be with this territory claimed
    def favour_territory_groups(territory: int) -> int:
        if len(set(my_territories) & set(game.state.map.get_adjacent_to(territory))) > 0:
            blob_territories = []
            next_edge = list(set(my_territories) & set(game.state.map.get_adjacent_to(territory)))
            while len(next_edge) != 0:
                blob_territories.extend(next_edge)
                next_edge = list((set(game.state.get_all_adjacent_territories(next_edge)) & set(my_territories)) - set(blob_territories))
            return len(blob_territories)
        else:
            return 0

    # For weightings
    territory_weights = defaultdict(lambda: 0.0)
    # Coefficients for weightings
    same_continent = 9
    enemies_close = 1
    adjacency = 1
    blobiness = 1

    # Calculating the weight for each border territory
    for territory in border_territories:
        territory_weights[territory] = same_continent*proportion_continent_of_territory(territory) \
            + enemies_close*difference_number_enemy(territory) \
            + adjacency*count_adjacent_friendly(territory)**0.5 \
            + blobiness*favour_territory_groups(territory)

    # Sorting and selecting the territories
    territory_weights = sorted(territory_weights, key=lambda x: territory_weights[x], reverse=True)
    selected_territory = list(territory_weights)[0]

    return game.move_place_initial_troop(query, selected_territory)


def handle_redeem_cards(game: Game, bot_state: BotState, query: QueryRedeemCards) -> MoveRedeemCards:
    """After the claiming and placing initial troops phases are over, you can redeem any
    cards you have at the start of each turn, or after killing another player."""

    # We will always redeem the minimum number of card sets we can until the 5th card set has been redeemed.
    # This is just an arbitrary choice to try and save our cards for the mid game.

    # We always have to redeem enough cards to reduce our card count below five.
    card_sets: list[Tuple[CardModel, CardModel, CardModel]] = []
    cards_remaining = game.state.me.cards.copy()

    while len(cards_remaining) >= 5:
        card_set = game.state.get_card_set(cards_remaining)
        # According to the pigeonhole principle, we should always be able to make a set
        # of cards if we have at least 5 cards.
        assert card_set != None
        card_sets.append(card_set)
        cards_remaining = [card for card in cards_remaining if card not in card_set]

    # Remember we can't redeem any more than the required number of card sets if 
    # we have just eliminated a player.
    if game.state.card_sets_redeemed > 5 and query.cause == "turn_started":
        card_set = game.state.get_card_set(cards_remaining)
        while card_set != None:
            card_sets.append(card_set)
            cards_remaining = [card for card in cards_remaining if card not in card_set]
            card_set = game.state.get_card_set(cards_remaining)

    return game.move_redeem_cards(query, [(x[0].card_id, x[1].card_id, x[2].card_id) for x in card_sets])


def handle_distribute_troops(game: Game, bot_state: BotState, query: QueryDistributeTroops) -> MoveDistributeTroops:
    """After you redeem cards (you may have chosen to not redeem any), you need to distribute
    all the troops you have available across your territories. This can happen at the start of
    your turn or after killing another player.
    """
    # General information
    unclaimed_territories = game.state.get_territories_owned_by(None)
    my_territories = game.state.get_territories_owned_by(game.state.me.player_id)
    all_territories = [territory for territory in game.state.territories]
    enemy_territories = list((set(all_territories) - set(unclaimed_territories)) - set(my_territories))
    continents = game.state.map.get_continents()
    border_territories = game.state.get_all_border_territories(my_territories)

    # Troop distribution setup
    total_troops = game.state.me.troops_remaining
    distributions = defaultdict(lambda: 0)

    # Place troops from territory bonus
    if len(game.state.me.must_place_territory_bonus) != 0:
        assert total_troops >= 2
        distributions[game.state.me.must_place_territory_bonus[0]] += 2
        total_troops -= 2

    # Gives the proportion of a continent owned by you that the territory is from
    def proportion_continent_of_territory(territory: int) -> float:
        for continent in continents:
            if territory in continents[continent]:
                return len(set(my_territories) & set(continents[continent]))/len(continents[continent])
        else:
            return 0
    
    # Provides a ratio between nearby friendly and enemy troops except returns 0 when is deemed to difficult to defend
    def difference_number_enemy(territory: int) -> float:
        adjacent_enemies = list(set(game.state.map.get_adjacent_to(territory)) & set(enemy_territories))
        adjacent_friendlies = list(set(my_territories) & set(game.state.get_all_adjacent_territories(adjacent_enemies)))
        friendlies = 1
        for friendly in adjacent_friendlies:
            friendlies += game.state.territories[friendly].troops
        adjacent_enemy_troops = 0
        for adjacent_enemy in adjacent_enemies:
            adjacent_enemy_troops += game.state.territories[adjacent_enemy].troops - 1
        if (adjacent_enemy_troops/(friendlies + total_troops)) > 1.5:
            return 0
        return adjacent_enemy_troops/friendlies
    
    # Returns the number of adjacent friendly territories
    def count_adjacent_friendly(territory: int) -> int:
        return len(set(my_territories) & set(game.state.map.get_adjacent_to(territory)))

    # This measures how many connected territories there would be with this territory claimed
    def favour_territory_groups(territory: int) -> int:
        if len(list(set(my_territories) & set(game.state.map.get_adjacent_to(territory)))) > 0:
            blob_territories = []
            next_edge = list(set(my_territories) & set(game.state.map.get_adjacent_to(territory)))
            while len(next_edge) != 0:
                blob_territories.extend(next_edge)
                next_edge = list((set(game.state.get_all_adjacent_territories(next_edge)) & set(my_territories)) - set(blob_territories))
            return len(blob_territories)
        else:
            return 0
    
    # Gives more weight to already large armies
    def prioritise_large_army(territory: int) -> int:
        return game.state.territories[territory].troops

    # Coefficients for weightings
    territory_weights = defaultdict(lambda: 0.0)
    same_continent = 7
    same_continent2 = 4
    adjacency = 1
    blobiness = 2
    troopiness = 0.1

    # Calculating weights for each territory
    for territory in border_territories:
        territory_weights[territory] = same_continent*proportion_continent_of_territory(territory)*difference_number_enemy(territory) \
            + same_continent2*proportion_continent_of_territory(territory)\
            + adjacency*count_adjacent_friendly(territory)**0.5 \
            + blobiness*favour_territory_groups(territory)\
            + troopiness*prioritise_large_army(territory)

    # Matching the weighting distribution to the troop distribution
    total_weight = sum([territory_weights[territory] for territory in territory_weights])
    leftover = total_troops
    for territory in border_territories:
        distributions[territory] += math.floor((territory_weights[territory]/total_weight)*total_troops)
        leftover -= math.floor((territory_weights[territory]/total_weight)*total_troops)
    distributions[border_territories[0]] += leftover

    return game.move_distribute_troops(query, distributions)


def handle_attack(game: Game, bot_state: BotState, query: QueryAttack) -> Union[MoveAttack, MoveAttackPass]:
    """After the troop phase of your turn, you may attack any number of times until you decide to
    stop attacking (by passing). After a successful attack, you may move troops into the conquered
    territory. If you eliminated a player you will get a move to redeem cards and then distribute troops."""
    # General information
    all_territories = [territory for territory in game.state.territories]
    my_territories = game.state.get_territories_owned_by(game.state.me.player_id)
    unclaimed_territories = game.state.get_territories_owned_by(None)   
    enemy_territories = list((set(all_territories) - set(unclaimed_territories)) - set(my_territories))
    border_territories = game.state.get_all_border_territories(my_territories)
    bordering_territories = game.state.get_all_adjacent_territories(my_territories)
    continents = game.state.map.get_continents()

    # Finding the troop count for each player
    all_troop_counts = defaultdict(lambda: 0)
    for territory in all_territories:
        all_troop_counts[game.state.territories[territory].occupier] += game.state.territories[territory].troops

    # Finding which players have fewer troops that you and how many cards they have
    enemy_card_counts = defaultdict(lambda: 0)
    enemy_with_cards_lower_troops = []
    for player in all_troop_counts:
        if (all_troop_counts[player] != game.state.me.player_id) and (all_troop_counts[player] < all_troop_counts[game.state.me.player_id]):
            enemy_card_counts[player] = game.state.players[player].card_count
            enemy_with_cards_lower_troops.append(player)

    # Compares the number of enemy troops in the continent to the number of friendly troops bordering the territory
    def continent_strength(territory: int) -> float:
        strength = 0
        for continent in continents:
            if territory in continents[continent]:
                for region in list(set(continents[continent]) - set(my_territories)):
                    strength += game.state.territories[region].troops
        friendly_adjacent = list(set(game.state.map.get_adjacent_to(territory)) & set(my_territories))
        friendly_adjacent_troops = sum(game.state.territories[x].troops - 1 for x in friendly_adjacent)
        return friendly_adjacent_troops/strength

    # Returns the number of adjacent friendly territories
    def adjacency(territory: int) -> int:
        return len(list(set(my_territories) & set(game.state.map.get_adjacent_to(territory))))

    # Gives the proportion of a continent owned by you that the territory is from
    def proportion_continent_of_territory(territory: int) -> float:
        for continent in continents:
            if territory in continents[continent]:
                return len(set(my_territories) & set(continents[continent]))/len(continents[continent])
        else:
            return 0
    
    # Provides a ratio between nearby friendly and enemy troops
    def troop_comparison(territory: int) -> float:
        adjacent_enemies = list((set(game.state.map.get_adjacent_to(territory)) & set(enemy_territories)) | set([territory]))
        adjacent_friendlies = list((set(my_territories) & set(game.state.get_all_adjacent_territories(adjacent_enemies))))
        friendlies = 1
        for friendly in adjacent_friendlies:
            friendlies += game.state.territories[friendly].troops - 1
        adjacent_enemy_troops = 1
        for adjacent_enemy in adjacent_enemies:
            adjacent_enemy_troops += game.state.territories[adjacent_enemy].troops
        return friendlies/adjacent_enemy_troops
    
    # Determines whether the territory is a choke point 
    def choke_point(territory: int) -> int:
        if territory in choke_points:
            return 1
        else:
            return 0

    # Determines whether taking this territory would leave a choke point
    def hold_choke_point(territory: int) -> int:
        if (len((set(game.state.map.get_adjacent_to(territory)) & set(choke_points)) & set(my_territories)) > 0):
            return 1
        else:
            return 0   

    # Gives a weighting for how many cards you could get by eliminating this opponent
    def get_cards(territory: int) -> int:
        if game.state.territories[territory].occupier in enemy_with_cards_lower_troops:
            return enemy_card_counts[game.state.territories[territory].occupier]
        else:
            return 0
    
    # Finds how many vulnerable the attacking army would leave their territory if they took this territory
    def stay_put(territory: int) -> int:
        adjacent_friend = list(set(game.state.map.get_adjacent_to(territory)) & set(my_territories))
        other_enemies = list(set(game.state.get_all_adjacent_territories(adjacent_friend)) - set([territory]))
        friend_troops = sum(game.state.territories[territory].troops for territory in adjacent_friend)
        other_enemy_troops = sum(game.state.territories[territory].troops for territory in other_enemies)
        return friend_troops - other_enemy_troops

    # Finds how much the size of border territories would change by taking this territory
    def border_size_change(territory: int) -> int:
        return len(border_territories) - len(game.state.get_all_border_territories(list(set(my_territories) | set([territory]))))

    # Coefficients for weightings
    choke_points = [40, 24, 29, 36, 30, 2, 4, 10, 0, 21]
    same_continent = 4
    chokehold = 1.5
    staychoke = 0.5
    cardwant = 2
    adjacencybonus = 0.1
    borderincrease = 0.5
    keep_border_safe = 0
    threshold = 2.5
    weak_continent = 3.5

    # Calculating weights for each bordering territory 
    territory_weights = defaultdict(lambda: 0.0)
    for territory in bordering_territories:
        territory_weights[territory] = \
              same_continent*proportion_continent_of_territory(territory)*troop_comparison(territory)\
            + chokehold*choke_point(territory)*proportion_continent_of_territory(territory)\
            - staychoke*hold_choke_point(territory)\
            + cardwant*get_cards(territory)*game.state.card_sets_redeemed\
            + adjacencybonus*adjacency(territory)\
            + borderincrease*border_size_change(territory)\
            + keep_border_safe*stay_put(territory)\
            + weak_continent*continent_strength(territory)
        
    # Sorting the territories
    territory_weights_order = sorted(territory_weights, key=lambda x: territory_weights[x], reverse=True)

    # Firsly determining which territories have a weighting that reach the threshold
    for territory in territory_weights_order:
        if territory_weights[territory] > threshold:
            # Using the attacker with the most troops
            attacking_canditates = sorted(list(set(game.state.map.get_adjacent_to(territory)) & set(my_territories)), key=lambda x: game.state.territories[x].troops, reverse=True)
            attacker = attacking_canditates[0]
            # Instead using an attacker that would otherwise be left in an internal territory
            for potential_attacker in attacking_canditates:
                if (len(list(set(game.state.map.get_adjacent_to(potential_attacker)) - set(my_territories))) == 1) and (game.state.territories[potential_attacker].troops > 1):
                    attacker = potential_attacker
                    break
            
            if game.state.territories[attacker].troops > 1: 
                return game.move_attack(query, attacker, territory, min(3, game.state.territories[attacker].troops - 1))
        else:
            return game.move_attack_pass(query)   

    return game.move_attack_pass(query)


def handle_troops_after_attack(game: Game, bot_state: BotState, query: QueryTroopsAfterAttack) -> MoveTroopsAfterAttack:
    """After conquering a territory in an attack, you must move troops to the new territory."""
    # General information
    unclaimed_territories = game.state.get_territories_owned_by(None)
    my_territories = game.state.get_territories_owned_by(game.state.me.player_id)
    all_territories = [territory for territory in game.state.territories]
    enemy_territories = list((set(all_territories) - set(unclaimed_territories)) - set(my_territories))
    record_attack = cast(RecordAttack, game.state.recording[query.record_attack_id])
    move_attack = cast(MoveAttack, game.state.recording[record_attack.move_attack_id])
    continents = game.state.map.get_continents()

    # Which territory is attacking and which is defending
    from_territory = move_attack.attacking_territory
    to_territory = move_attack.defending_territory

    # Finding the ratio of enemies and friendly troops for each territory and then finding the ratio between those ratios. 
    # If the continent largely owned then the troops will be distributed defensively otherwise all troops will go forward                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    
    for continent in continents:
        if (from_territory in continents[continent]) and (len(set(continents[continent]) & set(my_territories))/len(set(continents[continent])) > 0.5):

            adjacent_enemies_from = list(set(game.state.map.get_adjacent_to(from_territory)) & set(enemy_territories))
            adjacent_friendlies_from = list(set(game.state.map.get_adjacent_to(from_territory)) & set(my_territories) - set([to_territory]))
            
            adjacent_enemies_to = list(set(game.state.map.get_adjacent_to(to_territory)) & set(enemy_territories))
            adjacent_friendlies_to = list((set(game.state.map.get_adjacent_to(to_territory)) & set(my_territories)) - set([from_territory]))

            friendlies_from = 0.1
            for friendly in adjacent_friendlies_from:
                friendlies_from += game.state.territories[friendly].troops - 1

            enemies_from = 0.1
            for adjacent_enemy in adjacent_enemies_from:
                enemies_from += game.state.territories[adjacent_enemy].troops
            
            ratio_from = friendlies_from/enemies_from 


            friendlies_to = 0.1
            for friendly in adjacent_friendlies_to:
                friendlies_to += game.state.territories[friendly].troops - 1

            enemies_to = 0.1
            for adjacent_enemy in adjacent_enemies_to:
                enemies_to += game.state.territories[adjacent_enemy].troops
            
            ratio_to = friendlies_to/enemies_to 

            ratio = ratio_from/ratio_to
            troops_available = game.state.territories[from_territory].troops
            sending_troops = math.floor((troops_available/(ratio + 1)) * ratio)

            # Need to ensure that the number of troops attacking go to the territory
            if troops_available < 4:
                return game.move_troops_after_attack(query, troops_available - 1)
            return game.move_troops_after_attack(query, max(sending_troops, 3))
        
    return game.move_troops_after_attack(query, game.state.territories[from_territory].troops - 1)

def handle_defend(game: Game, bot_state: BotState, query: QueryDefend) -> MoveDefend:
    """If you are being attacked by another player, you must choose how many troops to defend with."""

    # We will always defend with the most troops that we can.

    # First we need to get the record that describes the attack we are defending against.
    move_attack = cast(MoveAttack, game.state.recording[query.move_attack_id])
    defending_territory = move_attack.defending_territory

    # We can only defend with up to 2 troops, and no more than we have stationed on the defending
    # territory.
    defending_troops = min(game.state.territories[defending_territory].troops, 2)
    return game.move_defend(query, defending_troops)


def handle_fortify(game: Game, bot_state: BotState, query: QueryFortify) -> Union[MoveFortify, MoveFortifyPass]:
    """At the end of your turn, after you have finished attacking, you may move a number of troops between
    any two of your territories (they must be adjacent)."""
    
    # General information
    my_territories = game.state.get_territories_owned_by(game.state.me.player_id)
    border_territories = game.state.get_all_border_territories(my_territories)
    
    # Will always try to fortify an internal army to the border
    candidate_territories = list(set(my_territories) - set(border_territories))
    if len(candidate_territories) == 0:
        return game.move_fortify_pass(query)
    
    # Finding the largest internal army
    max_troops = game.state.territories[candidate_territories[0]].troops
    max_territory = candidate_territories[0]

    for territory in candidate_territories:
        if game.state.territories[territory].troops > max_troops:
            max_territory = territory
            max_troops = game.state.territories[territory].troops

    # To find the shortest path, we will use a custom function.
    shortest_path = find_shortest_path_from_vertex_to_set(game, max_territory, set(border_territories))
    # We will move our troops along this path (we can only move one step, and we have to leave one troop behind).
    # We have to check that we can move any troops though, if we can't then we will pass our turn.
    if len(shortest_path) > 0 and game.state.territories[max_territory].troops > 1:
        return game.move_fortify(query, shortest_path[0], shortest_path[1], game.state.territories[max_territory].troops - 1)
    else:
        return game.move_fortify_pass(query)


def find_shortest_path_from_vertex_to_set(game: Game, source: int, target_set: set[int]) -> list[int]:
    """Used in move_fortify()."""

    # We perform a BFS search from our source vertex, stopping at the first member of the target_set we find.
    queue = deque()
    queue.appendleft(source)

    parent = {}
    seen = {source: True}
    while len(queue) != 0:
        current = queue.pop()
        if current in target_set:
            break

        for neighbour in game.state.map.get_adjacent_to(current):
            if neighbour not in seen:
                seen[neighbour] = True
                parent[neighbour] = current
                queue.appendleft(neighbour)
    path = []
    while current in parent:
        path.append(current)
        current = parent[current]
    path.append(source)
    return path[::-1]

if __name__ == "__main__":
    main()

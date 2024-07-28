#!/usr/bin/env python

import asyncio
import json
import os
import secrets
import websockets

#Possible Edge Case of client disconnection and then reconnecting, allowing them to vote again -> Make a set of unique ids that already voted -> in disconnect case if unique id already in set, client wil not be able to revote
CLIENTS = set()

#Think about making Question class -> Having (x) Data Structure of Questions in GameState -> Allow ability to revote and change 
#questions with ease

#Think about saving results for all question in a list as well to keep record
class GameState():
    #Class Vars
    vote_tally ={
        "yes": 0,
        "no": 0
    }

    def __init__(self,curr_question="",game_started=False,voting_allowed=False):
        self.curr_question = curr_question
        self.game_started = game_started
        self.voting_allowed = voting_allowed

OFFICIAL_GAME_STATE = GameState()

class ClientSession():
    def __init__(self, websocket):
        self.websocket = websocket
        self.is_admin = False

#Sending an error back to the client
async def error(websocket, message):
    error_message = {
        "type": "error",
        "message": message,
    }
    await websocket.send(json.dumps(error_message))

#Helper for send
async def send(websocket,message):
    try:
        await websocket.send(message)
    except websockets.ConnectionClosed:
        pass

#Concurrent Broadcast
async def broadcast(message):
    for client in CLIENTS:
        asyncio.create_task(send(client.websocket,message))

async def handler(websocket):
    """
    Full-Duplex Handle
    """    
    #Authenticate somewhere up here on initial connection

    client = ClientSession(websocket)

    if client not in CLIENTS:
        CLIENTS.add(client)

    try:
        while True:
            async for message in client.websocket:
                message = await client.websocket.recv()
                data = json.loads(message)

                #admin_client or client
                match(data['is_admin']):
                    case True:
                        match(data['type']):
                            case "reset_vote":
                                reset_all_client_vote(client)
                                break
                            case "update_curr_question":
                                update_question(message,client)
                                break
                            case "next_question_reset":
                                next_question_reset()
                                break
                            case "no_vote_allowed":
                                no_vote_allowed(client)
                                break
                            case "vote_allowed":
                                vote_allowed(client)
                                break
                            case "replay":
                                replay(client)
                                break
                            case _:
                                break
                    case False:
                        match(data['type']):
                            case "vote":
                                client_vote(message,client)
                                break
                            case _:
                                break
                    case _:
                        break
                
    except websockets.exceptions.ConnectionClosed:
        error(client.websocket, "Something went wrong, contact your administrator")
    
async def reset_all_client_vote():
    message = {
        "voted" : False
    }
    await broadcast(message)

async def next_question_reset(client):
    #Reset vote_tally, voting allowed to False
    next_vote_tally = {"yes" : 0, "no" : 0}

    OFFICIAL_GAME_STATE.vote_tally = next_vote_tally
    OFFICIAL_GAME_STATE.voting_allowed = False

    #return some state to let admin know they can start new vote
    start_next_vote = {"can_next_vote" : True}

    await client.websocket.send(json.dumps(start_next_vote))

async def no_vote_allowed(client):
    OFFICIAL_GAME_STATE.voting_allowed = False

    no_vote_allowed = {"vote_allowed" : False}

    await client.websocket.send(json.dumps(no_vote_allowed))

async def vote_allowed(client):
    OFFICIAL_GAME_STATE.voting_allowed = True

    vote_allowed = {"vote_allowed" : True}

    await client.websocket.send(json.dumps(vote_allowed))


async def client_vote(message,client):
    vote_message = json.loads(message)
    vote_decision = vote_message['vote_decision']
    vote_weight = vote_message['vote_weight']

    OFFICIAL_GAME_STATE.vote_tally[vote_decision] += vote_weight

    voted = {"voted" : True}

    await client.websocket.send(json.dumps(voted))

async def update_question(message,client):
    update_question_message = json.loads(message)

    OFFICIAL_GAME_STATE.curr_question = update_question_message['update_question']

    curr_question_message = {"curr_question" : OFFICIAL_GAME_STATE.curr_question}

    await client.websocket.send(json.dumps(curr_question_message))

#Client joins -> update them with the latest state -> need to grab some incoming id to replay back to specific client
async def replay(client):
    await client.websocket.send(json.dumps(OFFICIAL_GAME_STATE))

#Re-write
async def update_global_question_score(websocket, poll_hub,attendee):
    """
    Receive and process score in generic_poll_state.

    """
    async for message in websocket:
        """"
    poll_decision obj = {
        did_vote: bool,
        weighted_score: int,
        attendee: string
        decision: string
    }
    """
        generic_poll_state = {}
        #No more polling allowed at this moment
        if not generic_poll_state["polling_allowed"]:
            return
        #receive incoming message from attendee
        poll_decision = json.loads(message)

        decision = poll_decision['decision']
        weighted_score = poll_decision['weighted_score']
        attendee = poll_decision['attendee']
        
        #Check user hasn't voted yet -> check user is an attendee
        assert decision == False
        assert attendee in generic_poll_state["attendees"]

        try:
            #Update the current global_question_score in generic_poll_state + mark the attendee as voted
            if decision.lower() == 'yes':
                new_score = generic_poll_state['global_question_score'] + weighted_score 
                generic_poll_state['global_question_score'] = new_score
            poll_decision["did_vote"] = True
        except RuntimeError as e:
            # Send an "error" event if the move was illegal.
            await error(websocket, str(e))
            continue

        # Send state back to Main UI + Send state back to attendee client
        await websockets.broadcast(poll_hub, json.dumps(OFFICIAL_GAME_STATE))
        await websockets.broadcast(attendee, json.dump(poll_decision))

#Re-write for Auth
async def generate_join_key(websocket):
    #Route to hit to send the client a join key for auth
    
        #start the socket and turn state to true
        join_key = secrets.token_urlsafe(12)
        # JOIN_KEYS.append(join_key)
        await websocket.send(json.dumps({"secret" : join_key}))
        
#Re-Write
async def join(websocket):
    """
    Implement for attendees to join
    Multiple joins at the same time -> we await for each message hitting this route
    """
    generic_poll_state = {}
    async for message in websocket:
        message = json.loads(message)
        print("Client Message", message)
        if message['secret'] == os.getenv('SECRET_KEY'):
             generic_poll_state['attendees'].append(message['attendee'])
        generic_poll_event = {
            "type": "joined",
            "message": "You have successfully joined the game"
        }
        await websocket.send(json.dumps(generic_poll_event))

async def main():
    async with websockets.serve(handler, "", 8001):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
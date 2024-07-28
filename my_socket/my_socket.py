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
    error_message = {"type": "error", "message": message}
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

    try:
        CLIENTS.add(client)

        async for message in websocket:
            try:
                print("raw message",message)
                data = json.loads(message)
                print("json message", message)
                
                if data['is_admin']:
                    await handle_admin_message(data, client)
                else:
                    await handle_client_message(data, client)
            except json.JSONDecodeError:
                print(f"Invalid JSON received: {message}")

    except websockets.exceptions.ConnectionClosed:
        print(f"Connection closed for client: {client}")
    finally:
        CLIENTS.remove(client)

async def handle_admin_message(data,client):
    match data['type']:
        case "reset_vote":
            await reset_all_client_vote(client)
        case "update_curr_question":
            await update_question(data, client)
        case "next_question_reset":
            await next_question_reset()
        case "no_vote_allowed":
            await no_vote_allowed(client)
        case "vote_allowed":
            await vote_allowed(client)
        case "replay":
            await replay(client)
        case _:
            print(f"Unknown admin message type: {data['type']}")

async def handle_client_message(data,client):
    match data['type']:
        case "vote":
            await client_vote(data, client)
        case _:
            print(f"Unknown client message type: {data['type']}")

async def reset_all_client_vote():
    message = { "voted" : False}
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
    vote_decision = message['vote_decision']
    vote_weight = message['vote_weight']

    OFFICIAL_GAME_STATE.vote_tally[vote_decision] += vote_weight

    voted = {"voted" : True}

    await client.websocket.send(json.dumps(voted))

async def update_question(message,client):
    question = message['update_question']

    OFFICIAL_GAME_STATE.curr_question = question

    curr_question_message = {"curr_question" : OFFICIAL_GAME_STATE.curr_question}

    await client.websocket.send(json.dumps(curr_question_message))

#Client joins -> update them with the latest state -> need to grab some incoming id to replay back to specific client
async def replay(client):
    await client.websocket.send(json.dumps(OFFICIAL_GAME_STATE))
        
async def main():
    server = await websockets.serve(handler, "localhost", 8001)
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python

import asyncio
import json
import os
import signal
import secrets
import websockets

""""
Broadcast for all subscribers -> websocket.broadcast(subscribers, json.dumps(some event))
"""


generic_poll_state = {
    "attendees" : [],
    "global_question_score" : None,
    "current_question": None,
    "all_questions" : [],
    "polling_allowed": False,
    "is_started" : False
}

JOIN_KEYS =  []


#Sending an error back to the client
async def error(websocket, message):
    """
    Send an error message.

    """
    generic_poll_event = {
        "type": "error",
        "message": message,
    }
    await websocket.send(json.dumps(generic_poll_event))

#Client joins -> update them with the latest state -> need to grab some incoming id to replay back to specific client
async def replay(websocket, attendee, id=None):
    """
    Send Most Recent State

    Client has to handle the event

    """
    generic_poll_event = {
        "type": "replay",
        "attendee": attendee,
        "current_question" : generic_poll_state['current_question']
    }
    await websocket.send(json.dumps(generic_poll_event))


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
        await websockets.broadcast(poll_hub, json.dumps(generic_poll_state))
        await websockets.broadcast(attendee, json.dump(poll_decision))

async def generate_join_key(websocket):
    #Route to hit to send the client a join key for auth
    
        #start the socket and turn state to true
        join_key = secrets.token_urlsafe(12)
        JOIN_KEYS.append(join_key)
        await websocket.send(json.dumps({"secret" : join_key}))

async def join(websocket):
    """
    Implement for attendees to join
    Multiple joins at the same time -> we await for each message hitting this route
    """
    
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


async def handler(websocket):
    """
    Handle a connection and dispatch it according to who is connecting.
    join_poll {
       client_secret: string,
       attendee: string
    }
    """
    # Receive and authenticate new join
    async for message in websocket:
        message = await websocket.recv()
        join_poll = json.loads(message)
        client_secret, attendee = join_poll['client_secret'], join_poll['attendee']
        print(f"Join Poll {join_poll}")
        if client_secret ==  os.getenv('SECRET_KEY'):
            # Add to attendeees and estbalish connection
            if attendee not in generic_poll_state["attendees"]:
                generic_poll_state['attendees'].append(attendee)
                await join(websocket)
        else:
            error(websocket,"Something Went Wrong, contact your administrator")

async def main():
    async with websockets.serve(handler, "", 8001):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
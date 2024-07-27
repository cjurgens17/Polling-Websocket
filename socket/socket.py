#!/usr/bin/env python

import asyncio
import json
import os
import secrets
import signal

import websockets


generic_poll_state = {
    "attendees" : [],
    "global_question_score" : None,
    "current_question": None,
    "all_questions" : [],
    "polling_allowed": False
}


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

#Client joins -> update them with the latest state
async def replay(websocket):
    """
    Send Most Recent State

    Client has to handle the event

    """
    for attendee in generic_poll_state['attendees']:
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

async def start():
    #Implement to start the websocket
    return 

async def join(websocket, join_key):
    """
    Implement for attendees to join

    """
    return

async def handler(websocket):
    """
    Handle a connection and dispatch it according to who is connecting.
    join_poll {
       client_secret: string,
       attendee: string
    }
    """
    # Receive and authenticate new join
    message = await websocket.recv()
    join_poll = json.loads(message)
    client_secret, attendee = join_poll['client_secret'], join_poll['attendee']

    if client_secret ==  os.getenv('SECRET_KEY'):
        # Add to attendeees and estbalish connection
        if attendee not in generic_poll_state["attendees"]:
            generic_poll_state['attendees'].append(attendee)
            await join(websocket)
    elif generic_poll_state["attendees"].length <= 0:
        await start(websocket)
    else:
        error(websocket,"Something Went Wrong, contact your administrator")

async def main():
    # Set the stop condition when receiving SIGTERM.
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    port = int(os.environ.get("PORT", "8001"))
    async with websockets.serve(handler, "", port):
        await stop


if __name__ == "__main__":
    asyncio.run(main())
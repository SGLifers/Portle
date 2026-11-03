"""Pure game rules. Client views never contain an unsolved answer or raw portals."""
import random

MAX_TURNS=6
REVEALS=(1,2,4,8,16)


class GameError(ValueError):pass


def portal_order(portals,seed):
    """Deterministic nested clues, spreading hints across real placements."""
    rng=random.Random(seed);remaining=list(range(len(portals)));first=rng.choice(remaining)
    order=[first];remaining.remove(first)
    xs=[p['position'][0] for p in portals];ys=[p['position'][1] for p in portals];zs=[p['position'][2] for p in portals]
    spans=[max(max(xs)-min(xs),1),max(max(ys)-min(ys),1),max(max(zs)-min(zs),1)]
    def distance(a,b):return sum(((portals[a]['position'][i]-portals[b]['position'][i])/spans[i])**2*(.25 if i==2 else 1) for i in range(3))
    nearest={i:distance(i,first) for i in remaining}
    while remaining:
        nxt=max(remaining,key=lambda i:(nearest[i],-i));order.append(nxt);remaining.remove(nxt)
        for i in remaining:nearest[i]=min(nearest[i],distance(i,nxt))
    return order


def new_state(round_id,user_id,puzzle,mode):
    return {'id':round_id,'user_id':str(user_id),'puzzle':puzzle,'mode':mode,'version':0,'status':'playing','attempts':[]}


def clue_count(state):
    total=len(state['puzzle']['map']['portals'])
    if state['status']!='playing':return total
    turn=len(state['attempts'])
    return total if turn>=5 else min(total,REVEALS[turn])


def apply_action(state,resolved=None,skip=False):
    if state['status']!='playing':raise GameError('This round is finished. Start a practice round or return for the next daily puzzle.')
    if not skip and resolved is None:raise GameError('Choose a map name.')
    if not skip and any(a.get('map_id')==resolved['id'] for a in state['attempts']):raise GameError('You already tried that map; this did not use a guess.')
    correct=not skip and resolved['id']==state['puzzle']['map']['id']
    state['attempts'].append({'kind':'skip' if skip else 'guess','name':None if skip else resolved['name'],'map_id':None if skip else resolved['id'],'correct':correct})
    state['version']+=1
    if correct:state['status']='won'
    elif len(state['attempts'])>=MAX_TURNS:state['status']='lost'
    return state


def share_text(state):
    if state['status']=='playing':raise GameError('Finish the round before sharing your result.')
    score=str(len(state['attempts'])) if state['status']=='won' else 'X'
    boxes=''.join('🟩' if a['correct'] else '⬜' if a['kind']=='skip' else '🟥' for a in state['attempts'])
    boxes+='⬛'*(MAX_TURNS-len(state['attempts']))
    label=state['puzzle']['day'] if state['mode']=='daily' else 'Practice'
    return f'Portle {label} {score}/{MAX_TURNS}\n{boxes}\nGuess the arena from its portals.'


def public_view(state):
    turn=len(state['attempts'])+(state['status']=='playing')
    result={'id':state['id'],'version':state['version'],'mode':state['mode'],'day':state['puzzle']['day'],
        'status':state['status'],'turn':max(1,min(MAX_TURNS,turn)),'maxTurns':MAX_TURNS,
        'portalCount':clue_count(state),'attempts':[{'name':a['name'],'kind':a['kind'],'correct':a['correct']} for a in state['attempts']]}
    if state['status']!='playing':result.update(answer=state['puzzle']['map']['name'],share=share_text(state))
    return result
